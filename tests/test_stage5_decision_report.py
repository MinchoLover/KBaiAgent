import copy
import unittest
from types import SimpleNamespace

from src.application.consultation_service import build_decision_support
from src.config import Settings
from src.consultation.review_area import (
    project_consultation_presentation,
)
from src.country_environment.assessment import (
    assess_country_trade_environment,
)
from src.demo import run_decision_support_demo
from src.stage5.critic import critique_report
from src.stage5.report_agent import generate_report


class Stage5DecisionReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.import_demo = run_decision_support_demo("BUYER")
        cls.export_demo = run_decision_support_demo("SELLER")
        cls.br_assessment = assess_country_trade_environment(
            cls.export_demo[
                "country_environment_input"
            ].model_copy(update={"counterparty_country": "BR"})
        )
        cls.br_decision = build_decision_support(
            case_id=cls.export_demo["workflow_state"].case_id,
            extraction=cls.export_demo["extraction"],
            confirmation=cls.export_demo["confirmation"],
            stage1=cls.export_demo["stage1"],
            stage2_input=cls.export_demo["stage2_input"],
            stage2_result=cls.export_demo["stage2"],
            trade_settlement_risk=cls.export_demo[
                "trade_risk_assessment"
            ],
            country_environment=cls.br_assessment,
            official_candidate_shortlist=cls.export_demo[
                "official_candidate_shortlist"
            ],
            generated_at="2026-07-23T09:00:00+09:00",
        )
        cls.br_report = generate_report(
            extraction=cls.export_demo["extraction"],
            confirmation=cls.export_demo["confirmation"],
            stage1=cls.export_demo["stage1"],
            stage2=cls.export_demo["stage2"],
            stage3=cls.export_demo["stage3"],
            stage4=cls.export_demo["stage4"],
            consultation_packet=(
                cls.br_decision.consultation_packet.packet
            ),
            settings=Settings(enable_llm_report=False),
        )

    def _critique(self, markdown):
        report = self.import_demo["report"]
        return critique_report(
            markdown=markdown,
            source_bundle=report.report_json,
            scenario_kind=self.import_demo["stage1"].kind,
            probability_valid=(
                self.import_demo["stage1"].probability_valid
            ),
        )

    def _critique_brazil(self, markdown):
        return critique_report(
            markdown=markdown,
            source_bundle=self.br_report.report_json,
            scenario_kind=self.export_demo["stage1"].kind,
            probability_valid=(
                self.export_demo["stage1"].probability_valid
            ),
        )

    def _critique_export(self, markdown):
        report = self.export_demo["report"]
        return critique_report(
            markdown=markdown,
            source_bundle=report.report_json,
            scenario_kind=self.export_demo["stage1"].kind,
            probability_valid=(
                self.export_demo["stage1"].probability_valid
            ),
        )

    def _report_with_supporting_check(self):
        demo = self.export_demo
        packet = demo["consultation_packet"].packet
        priorities = [
            packet.consultation_priorities[0],
            packet.consultation_priorities[1].model_copy(
                update={
                    "category": "COUNTRY_MACRO_ENVIRONMENT_MONITORING"
                }
            ),
            packet.consultation_priorities[2].model_copy(
                update={"category": "FX_RISK_MANAGEMENT"}
            ),
        ]
        presentation = project_consultation_presentation(
            priorities=priorities,
            priority_fingerprint=(
                packet.consultation_priority_fingerprint
            ),
        )
        supporting_packet = packet.model_copy(
            update={
                "consultation_priorities": priorities,
                "consultation_review_areas": (
                    presentation.review_areas
                ),
                "consultation_supporting_checks": (
                    presentation.supporting_checks
                ),
            }
        )
        return generate_report(
            extraction=demo["extraction"],
            confirmation=demo["confirmation"],
            stage1=demo["stage1"],
            stage2=demo["stage2"],
            stage3=demo["stage3"],
            stage4=demo["stage4"],
            consultation_packet=supporting_packet,
            settings=Settings(enable_llm_report=False),
        )

    def test_import_report_contains_trade_risk_and_shortlist(self):
        report = self.import_demo["report"]
        assessment = self.import_demo["trade_risk_assessment"]
        shortlist = self.import_demo[
            "official_candidate_shortlist"
        ]
        self.assertTrue(report.critique.passed)
        self.assertEqual(
            report.report_json["consultation"][
                "trade_settlement_risk"
            ]["input_fingerprint"],
            assessment.input_fingerprint,
        )
        self.assertIn(
            "수입 선지급·계약이행 위험",
            report.markdown,
        )
        self.assertIn(shortlist.candidates[0].name, report.markdown)
        self.assertIn(
            "[source: consultation.official_candidate_shortlist."
            "candidates.0]",
            report.markdown,
        )

    def test_export_report_contains_collection_risk(self):
        report = self.export_demo["report"]
        self.assertTrue(report.critique.passed)
        self.assertIn("수출대금 회수 위험", report.markdown)
        self.assertIn(
            self.export_demo[
                "official_candidate_shortlist"
            ].candidates[0].name,
            report.markdown,
        )

    def test_country_report_has_separate_axes_and_provenance(self):
        report = self.import_demo["report"]
        self.assertTrue(report.critique.passed)
        self.assertIn("국가·무역환경 검토", report.markdown)
        self.assertIn("지급·이전 환경", report.markdown)
        self.assertIn("거시환경", report.markdown)
        self.assertIn("무역·시장접근", report.markdown)
        self.assertIn("관측기간", report.markdown)
        self.assertIn("한계:", report.markdown)
        for reference in self.import_demo[
            "country_environment_assessment"
        ].official_source_references:
            self.assertIn(reference.official_url, report.markdown)

    def test_brazil_fallback_preserves_raw_policy(self):
        self.assertTrue(self.br_report.critique.passed)
        self.assertEqual(
            self.br_report.fallback_reason,
            "DETERMINISTIC_POLICY",
        )
        self.assertIn(
            "OECD 공식 원자료 분류는 4",
            self.br_report.markdown,
        )
        self.assertIn(
            "KBaiAgent 자체 국가등급이 아닙니다",
            self.br_report.markdown,
        )
        self.assertIn(
            "합산 점수로 만들지 않았고",
            self.br_report.markdown,
        )

    def test_report_uses_at_most_three_shortlist_candidates(self):
        report = self.export_demo["report"]
        candidates = report.report_json["consultation"][
            "official_candidate_shortlist"
        ]["candidates"]
        self.assertLessEqual(len(candidates), 3)
        raw_only = next(
            item
            for item in self.export_demo["stage4"].candidates
            if item.product_id
            not in {
                candidate.product_id
                for candidate in self.export_demo[
                    "official_candidate_shortlist"
                ].candidates
            }
        )
        self.assertNotIn(raw_only.name, report.markdown)

    def test_empty_shortlist_blocks_raw_stage4_product_invention(self):
        demo = self.import_demo
        packet = demo["consultation_packet"].packet
        shortlist = demo["official_candidate_shortlist"].model_copy(
            update={
                "candidates": [],
                "unmatched_consultation_categories": [
                    "IMPORT_ADVANCE_PAYMENT_PROTECTION"
                ],
            }
        )
        empty_packet = packet.model_copy(
            update={"official_candidate_shortlist": shortlist}
        )
        calls = []

        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text="가상 승인 상품")

        result = generate_report(
            extraction=demo["extraction"],
            confirmation=demo["confirmation"],
            stage1=demo["stage1"],
            stage2=demo["stage2"],
            stage3=demo["stage3"],
            stage4=demo["stage4"],
            consultation_packet=empty_packet,
            settings=Settings(openai_api_key="test-only"),
            client=SimpleNamespace(
                responses=SimpleNamespace(create=create)
            ),
        )
        self.assertEqual(calls, [])
        self.assertEqual(
            result.fallback_reason,
            "DETERMINISTIC_POLICY",
        )
        self.assertNotIn(
            demo["stage4"].candidates[0].name,
            result.markdown,
        )
        self.assertIn(
            "직접 연결되지 않은 상품을 임의로 만들지 않았습니다",
            result.markdown,
        )

    def test_critic_rejects_raw_stage4_product_citation(self):
        report = self.import_demo["report"]
        unsafe = report.markdown.replace(
            "consultation.official_candidate_shortlist.candidates.0",
            "stage4.candidates.0",
            1,
        )
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertTrue(
            any(
                "현재 상담과 연결된 공식 근거" in item
                for item in critique.issues
            )
        )

    def test_critic_rejects_invented_name_with_valid_source_path(self):
        report = self.import_demo["report"]
        candidate = self.import_demo[
            "official_candidate_shortlist"
        ].candidates[0]
        unsafe = report.markdown.replace(
            candidate.name,
            "가상 확정승인 상품",
            1,
        )
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "상품명이 인용한 공식 후보와 일치하지 않습니다.",
            critique.issues,
        )

    def test_critic_rejects_changed_official_url(self):
        report = self.import_demo["report"]
        official_url = self.import_demo[
            "official_candidate_shortlist"
        ].candidates[0].source.url
        unsafe = report.markdown.replace(
            official_url,
            "https://example.com/fake-product",
            1,
        )
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "상품 링크가 인용한 공식 후보 URL과 일치하지 않습니다.",
            critique.issues,
        )

    def test_critic_rejects_non_catalogue_candidate(self):
        report = self.export_demo["report"]
        source_bundle = copy.deepcopy(report.report_json)
        candidate = source_bundle["consultation"][
            "official_candidate_shortlist"
        ]["candidates"][0]
        candidate["catalogue_id"] = "not_in_catalogue"
        candidate["product_id"] = "not_in_catalogue"
        critique = critique_report(
            markdown=report.markdown,
            source_bundle=source_bundle,
            scenario_kind=self.export_demo["stage1"].kind,
            probability_valid=(
                self.export_demo["stage1"].probability_valid
            ),
        )
        self.assertFalse(critique.passed)
        self.assertIn(
            "최종 후보가 active catalogue stable ID에 연결되지 않았습니다.",
            critique.issues,
        )

    def test_critic_rejects_changed_candidate_order(self):
        report = self.export_demo["report"]
        lines = report.markdown.splitlines()
        first = next(
            index
            for index, line in enumerate(lines)
            if "official_candidate_shortlist.candidates.0" in line
        )
        second = next(
            index
            for index, line in enumerate(lines)
            if "official_candidate_shortlist.candidates.1" in line
        )
        lines[first], lines[second] = lines[second], lines[first]
        critique = self._critique_export("\n".join(lines))
        self.assertFalse(critique.passed)
        self.assertIn(
            "공식 후보 순서가 packet shortlist와 다르게 변경됐습니다.",
            critique.issues,
        )

    def test_critic_rejects_policy_candidate_without_policy_area(self):
        report = self.export_demo["report"]
        source_bundle = copy.deepcopy(report.report_json)
        candidate = source_bundle["consultation"][
            "official_candidate_shortlist"
        ]["candidates"][0]
        candidate.update(
            {
                "catalogue_id": "kosmes_export_funding",
                "product_id": "kosmes_export_funding",
                "name": "신시장진출지원자금 검토",
                "official_name": "신시장진출지원자금",
                "institution": "중소벤처기업진흥공단",
                "category": "POLICY_FINANCE",
                "candidate_family": (
                    "POLICY_MARKET_EXPANSION_FINANCE"
                ),
                "source": {
                    "title": "중소벤처기업진흥공단 정책자금 안내",
                    "url": (
                        "https://www.kosmes.or.kr/nsh/SH/SBI/"
                        "SHSBI006M0.do"
                    ),
                    "verified_at": "2026-08-02",
                    "evidence_summary": "공식 페이지",
                },
            }
        )
        critique = critique_report(
            markdown=report.markdown,
            source_bundle=source_bundle,
            scenario_kind=self.export_demo["stage1"].kind,
            probability_valid=(
                self.export_demo["stage1"].probability_valid
            ),
        )
        self.assertFalse(critique.passed)
        self.assertIn(
            "정책자금 검토 분야 없이 정책자금 후보가 생성됐습니다.",
            critique.issues,
        )

    def test_critic_rejects_eligibility_claim(self):
        report = self.import_demo["report"]
        safe_phrase = "자격·승인 조건은 상담 필요"
        self.assertIn(safe_phrase, report.markdown)
        unsafe = report.markdown.replace(
            safe_phrase,
            "가입 가능합니다",
            1,
        )
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "공식 후보의 이용 자격이나 승인 가능성을 확정했습니다.",
            critique.issues,
        )

    def test_critic_rejects_ungrounded_trade_risk(self):
        report = self.import_demo["report"]
        unsafe = report.markdown.replace(
            "[source: consultation.trade_settlement_risk]",
            "",
        )
        for index in range(
            len(self.import_demo["trade_risk_assessment"].factors)
        ):
            unsafe = unsafe.replace(
                "[source: consultation.trade_settlement_risk."
                "factors.{}]".format(index),
                "",
            )
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "거래·결제조건 위험 주장에 확인된 위험평가 근거가 없습니다.",
            critique.issues,
        )

    def test_critic_rejects_changed_trade_risk_priority(self):
        report = self.import_demo["report"]
        unsafe = report.markdown.replace(
            "우선 검토 필요",
            "일반 검토",
            1,
        )
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "검토 우선도가 인용한 거래위험 결과와 일치하지 않습니다.",
            critique.issues,
        )

    def test_critic_rejects_changed_consultation_topic_title(self):
        report = self.import_demo["report"]
        review_area = self.import_demo[
            "consultation_packet"
        ].packet.consultation_review_areas[0]
        unsafe = report.markdown.replace(
            review_area.display_name,
            "임의 금융상품 승인",
            1,
        )
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "상담 검토 분야 표시명이 구조화 결과와 일치하지 않습니다.",
            critique.issues,
        )

    def test_critic_rejects_official_rating_claim(self):
        unsafe = "{}\n공식 심사등급으로 확정했습니다. ".format(
            self.import_demo["report"].markdown
        )
        unsafe += (
            "[source: consultation.trade_settlement_risk]"
        )
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertTrue(
            any(
                "공식 등급" in item
                for item in critique.issues
            )
        )

    def test_critic_rejects_trade_risk_changing_hedge_ratio(self):
        unsafe = (
            "{}\n결제 위험이 높아 선물환 비율을 높였습니다. "
            "[source: consultation.trade_settlement_risk]"
        ).format(self.import_demo["report"].markdown)
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "결제·회수 위험이 환헤지 비율을 직접 변경한다고 "
            "표현했습니다.",
            critique.issues,
        )

    def test_critic_rejects_brazil_raw_as_internal_rating(self):
        unsafe = self.br_report.markdown.replace(
            "OECD 공식 원자료 분류는 4이며 KBaiAgent 자체 국가등급이 "
            "아닙니다",
            "KBaiAgent 국가등급 4입니다",
            1,
        )
        critique = self._critique_brazil(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "Brazil OECD raw 4를 자체 국가등급으로 표현했습니다.",
            critique.issues,
        )

    def test_critic_rejects_us_unclassified_as_low_or_zero(self):
        report = self.import_demo["report"]
        unsafe = report.markdown.replace(
            "고소득 OECD 회원국 미분류이며 0 또는 낮은 위험으로 "
            "변환하지 않았습니다",
            "고소득 OECD 회원국 미분류이므로 LOW 0 안전입니다",
            1,
        )
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "US OECD 미분류를 LOW·0·안전으로 표현했습니다.",
            critique.issues,
        )

    def test_critic_rejects_country_composite_score(self):
        report = self.import_demo["report"]
        unsafe = report.markdown.replace(
            "OECD·World Bank·WTO는 합산 점수로 만들지 않았고",
            "OECD·World Bank·WTO를 합산해 0~100 종합점수 73점을 "
            "만들었고",
            1,
        )
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "세 국가 신호를 하나의 숫자 점수로 합산했습니다.",
            critique.issues,
        )

    def test_critic_rejects_country_signal_changing_hedge(self):
        unsafe = (
            "{}\n국가 신호로 환헤지 비율을 높여 조정했습니다. "
            "[source: consultation.country_environment]"
        ).format(self.import_demo["report"].markdown)
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "국가 신호로 환헤지 비율을 변경했습니다.",
            critique.issues,
        )

    def test_critic_rejects_country_signal_changing_cashflow(self):
        unsafe = (
            "{}\nOECD 신호로 Stage 2 현금흐름을 감소시켰습니다. "
            "[source: consultation.country_environment]"
        ).format(self.import_demo["report"].markdown)
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "국가 신호로 Stage 2 현금흐름을 변경했습니다.",
            critique.issues,
        )

    def test_critic_rejects_country_based_product_approval(self):
        unsafe = (
            "{}\n국가 신호로 이 보험 가입은 승인됩니다. "
            "[source: consultation.country_environment]"
        ).format(self.import_demo["report"].markdown)
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertTrue(
            any(
                "승인" in item
                for item in critique.issues
            )
        )

    def test_critic_rejects_changed_country_source_url_and_value(self):
        report = self.import_demo["report"]
        oecd_url = self.import_demo[
            "country_environment_assessment"
        ].official_source_references[0].official_url
        unsafe_url = report.markdown.replace(
            oecd_url,
            "https://example.com/fake-country-source",
            1,
        )
        url_critique = self._critique(unsafe_url)
        self.assertFalse(url_critique.passed)
        self.assertIn(
            "국가·무역환경 URL이 snapshot 공식 출처와 일치하지 않습니다.",
            url_critique.issues,
        )

        unsafe_value = report.markdown.replace(
            "원값/status 3.4 %",
            "원값/status 99.9 %",
            1,
        )
        value_critique = self._critique(unsafe_value)
        self.assertFalse(value_critique.passed)
        self.assertTrue(
            any(
                "근거 JSON에 없는 숫자" in item
                for item in value_critique.issues
            )
        )

    def test_stage5_preserves_consultation_top3_order_and_numbers(self):
        report = self.export_demo["report"]
        packet = self.export_demo["consultation_packet"].packet
        positions = [
            report.markdown.index(
                "{}순위 {}".format(item.rank, item.display_name)
            )
            for item in packet.consultation_review_areas
        ]

        self.assertEqual(positions, sorted(positions))
        self.assertEqual(
            [
                item.category
                for item in packet.consultation_priorities
            ],
            [
                "EXPORT_RECEIVABLE_PROTECTION",
                "FX_RISK_MANAGEMENT",
                "EXPORT_LIQUIDITY_REVIEW",
            ],
        )
        self.assertIn("7000000.00 KRW", report.markdown)
        self.assertIn("2000000.00 KRW", report.markdown)
        self.assertIn("cash deficit 0.00 KRW", report.markdown)
        self.assertIn(
            "payment/post-credit deficit 0.00 KRW",
            report.markdown,
        )
        self.assertTrue(report.critique.passed)

    def test_stage5_separates_supporting_check_without_renumbering(self):
        report = self._report_with_supporting_check()
        self.assertTrue(report.critique.passed, report.critique.issues)
        self.assertIn("## 10. 상담 우선순위", report.markdown)
        self.assertIn("## 10A. 추가 확인사항", report.markdown)
        self.assertIn("1순위 수출대금 회수 보호", report.markdown)
        self.assertIn("3순위 환율 관리", report.markdown)
        self.assertNotIn("2순위 환율 관리", report.markdown)
        self.assertIn("거래국 거시환경 모니터링", report.markdown)
        self.assertIn("원본 priority rank: 2", report.markdown)
        supporting_section = report.markdown.split(
            "## 10A. 추가 확인사항",
            1,
        )[1].split("## 11.", 1)[0]
        self.assertNotIn("정책자금 검토", supporting_section)
        self.assertNotIn("공식 후보", supporting_section)

    def test_critic_rejects_supporting_check_policy_rewrite_or_move(self):
        report = self._report_with_supporting_check()
        changed_name = report.markdown.replace(
            "**거래국 거시환경 모니터링**",
            "**정책자금 검토**",
            1,
        )
        name_critique = critique_report(
            markdown=changed_name,
            source_bundle=report.report_json,
            scenario_kind=self.export_demo["stage1"].kind,
            probability_valid=(
                self.export_demo["stage1"].probability_valid
            ),
        )
        self.assertFalse(name_critique.passed)
        self.assertIn(
            "추가 확인사항 표시명이 구조화 결과와 일치하지 않습니다.",
            name_critique.issues,
        )

        moved = report.markdown.replace(
            "## 10A. 추가 확인사항",
            "## 10A. 정책자금 검토",
            1,
        )
        moved_critique = critique_report(
            markdown=moved,
            source_bundle=report.report_json,
            scenario_kind=self.export_demo["stage1"].kind,
            probability_valid=(
                self.export_demo["stage1"].probability_valid
            ),
        )
        self.assertFalse(moved_critique.passed)
        self.assertIn("추가 확인사항", moved_critique.missing_sections)

    def test_critic_rejects_changed_or_mixed_review_area(self):
        report = self.export_demo["report"]
        changed_name = report.markdown.replace(
            "1순위 수출대금 회수 보호",
            "1순위 정책자금 검토",
            1,
        )
        name_critique = self._critique_export(changed_name)
        self.assertFalse(name_critique.passed)
        self.assertIn(
            "상담 검토 분야 표시명이 구조화 결과와 일치하지 않습니다.",
            name_critique.issues,
        )

        candidate = self.export_demo[
            "official_candidate_shortlist"
        ].candidates[0]
        mixed = report.markdown.replace(
            "[source: consultation.consultation_review_areas.0]",
            "공식 후보 {}. [source: consultation."
            "consultation_review_areas.0]".format(candidate.name),
            1,
        )
        mixed_critique = self._critique_export(mixed)
        self.assertFalse(mixed_critique.passed)
        self.assertIn(
            "상담 검토 분야와 공식 금융지원 후보가 한 섹션에 혼합됐습니다.",
            mixed_critique.issues,
        )

        invented = report.markdown.replace(
            "\n## 11. 공식 출처 상담 후보",
            "\n- **4순위 정책자금 검토** — 입력에 없는 분야입니다."
            "\n\n## 11. 공식 출처 상담 후보",
            1,
        )
        invented_critique = self._critique_export(invented)
        self.assertFalse(invented_critique.passed)
        self.assertIn(
            "존재하지 않는 상담 검토 분야가 추가됐거나 기존 분야가 "
            "삭제됐습니다.",
            invented_critique.issues,
        )

    def test_critic_rejects_projection_not_bound_to_priorities(self):
        report = self.export_demo["report"]
        source_bundle = copy.deepcopy(report.report_json)
        source_bundle["consultation"][
            "consultation_review_areas"
        ][0]["display_name"] = "정책자금 검토"
        critique = critique_report(
            markdown=report.markdown,
            source_bundle=source_bundle,
            scenario_kind=self.export_demo["stage1"].kind,
            probability_valid=(
                self.export_demo["stage1"].probability_valid
            ),
        )
        self.assertFalse(critique.passed)
        self.assertIn(
            "상담 검토 분야 projection이 기존 priority와 일치하지 않습니다.",
            critique.issues,
        )

    def test_critic_rejects_priority_as_approval_grade(self):
        unsafe = (
            "{}\n상담 1순위는 대출 승인등급입니다. "
            "[source: consultation.consultation_priorities.0]"
        ).format(self.br_report.markdown)
        critique = self._critique_brazil(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "상담 검토 순위를 승인·인수·대출 등급으로 표현했습니다.",
            critique.issues,
        )

    def test_critic_rejects_buffer_shortfall_as_insolvency(self):
        unsafe = (
            "{}\nbuffer 부족 때문에 지급불능이며 대출이 필요합니다. "
            "[source: consultation.consultation_priorities.2]"
        ).format(self.br_report.markdown)
        critique = self._critique_brazil(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "buffer shortfall을 지급불능 또는 대출 필요성으로 표현했습니다.",
            critique.issues,
        )

    def test_critic_rejects_scheduled_exposure_as_actual_receivable(self):
        unsafe = (
            "{}\n예정 수취 노출액 USD 100000.00은 실제 현재 "
            "미수잔액입니다. [source: stage2.total_foreign_amount]"
        ).format(self.br_report.markdown)
        critique = self._critique_brazil(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "예정 결제 노출액을 실제 현재 미수·미지급잔액으로 "
            "표현했습니다.",
            critique.issues,
        )

    def test_critic_rejects_stage3_optimal_recommendation(self):
        unsafe = (
            "{}\nStage 3 후보는 최적 헤지 추천입니다. "
            "[source: stage3.status]"
        ).format(self.br_report.markdown)
        critique = self._critique_brazil(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "Stage 3 계산상 후보를 최적 추천 또는 실행 지시로 "
            "표현했습니다.",
            critique.issues,
        )

    def test_critic_rejects_download_as_rm_transfer(self):
        unsafe = (
            "{}\nMarkdown 다운로드가 RM에게 전송 완료되었습니다. "
            "[source: consultation.input_hash]"
        ).format(self.br_report.markdown)
        critique = self._critique_brazil(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "다운로드 또는 상담 준비를 실제 RM 전송·예약·신청으로 "
            "표현했습니다.",
            critique.issues,
        )


if __name__ == "__main__":
    unittest.main()
