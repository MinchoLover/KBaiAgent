import unittest
from types import SimpleNamespace

from src.config import Settings
from src.demo import run_decision_support_demo
from src.stage5.critic import critique_report
from src.stage5.report_agent import generate_report


class Stage5DecisionReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.import_demo = run_decision_support_demo("BUYER")
        cls.export_demo = run_decision_support_demo("SELLER")

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
        topic = self.import_demo[
            "consultation_packet"
        ].packet.consultation_topics[0]
        unsafe = report.markdown.replace(
            topic.title,
            "임의 금융상품 승인",
            1,
        )
        critique = self._critique(unsafe)
        self.assertFalse(critique.passed)
        self.assertIn(
            "금융 대응 제목이 인용한 상담 항목과 일치하지 않습니다.",
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


if __name__ == "__main__":
    unittest.main()
