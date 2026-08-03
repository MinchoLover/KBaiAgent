import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from src.config import Settings
from src.demo import run_offline_demo
from src.domain.product_models import Stage4Result
from src.domain.report_models import (
    Stage5NarrativeDraft,
    Stage5NarrativeItem,
)
from src.stage3.optimizer import generate_strategy_candidates
from src.stage4.local_kb import load_official_kb, search_offline_kb
from src.stage4.official_search import is_official_url, search_official_web
from src.stage5.critic import critique_report
from src.stage5.grounding import build_grounding_registry
from src.stage5.report_agent import generate_report


class Stage3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = run_offline_demo()

    def test_returns_top_three_candidates(self):
        result = generate_strategy_candidates(self.demo["stage2"])
        self.assertEqual(len(result.candidates), 3)
        self.assertEqual(result.status, "CANDIDATES_NOT_ADVICE")

    def test_candidate_ratios_sum_to_one(self):
        result = generate_strategy_candidates(self.demo["stage2"])
        for candidate in result.candidates:
            total = (
                Decimal(candidate.forward_ratio)
                + Decimal(candidate.staged_conversion_ratio)
                + Decimal(candidate.unhedged_ratio)
            )
            self.assertEqual(total, Decimal("1"))
            self.assertEqual(
                candidate.liquidity_impact,
                candidate.estimated_buffer_shortfall,
            )
            self.assertEqual(
                candidate.acceptable_loss_exceeded,
                Decimal(candidate.worst_case_loss)
                > Decimal(
                    self.demo["stage2"].stage3_constraints[
                        "acceptable_fx_loss"
                    ]
                ),
            )
            self.assertGreaterEqual(
                Decimal(candidate.held_fx_ratio),
                Decimal("0"),
            )
            self.assertLessEqual(
                Decimal(candidate.held_fx_ratio),
                Decimal("1"),
            )
            self.assertTrue(candidate.limitations)

    def test_no_probabilities_uses_robust_objective(self):
        result = generate_strategy_candidates(self.demo["stage2"])
        self.assertEqual(result.objective_mode, "WORST_CASE_ROBUST")

    def test_invalid_grid_rejected(self):
        with self.assertRaises(ValueError):
            generate_strategy_candidates(
                self.demo["stage2"],
                grid_step_percent=7,
            )

    def test_candidate_cost_ignores_already_settled_base_cashflow(self):
        original = generate_strategy_candidates(self.demo["stage2"])
        changed_base_flow = self.demo["stage2"].model_copy(
            update={"base_required_or_proceeds_krw": "999999999999.00"}
        )
        changed = generate_strategy_candidates(changed_base_flow)
        self.assertEqual(original.candidates, changed.candidates)


class Stage4Tests(unittest.TestCase):
    def test_allowlist_accepts_subdomain(self):
        self.assertTrue(
            is_official_url("https://www.ksure.or.kr/rh-fx/example")
        )

    def test_allowlist_rejects_lookalike_and_blog(self):
        self.assertFalse(
            is_official_url("https://ksure.or.kr.evil.example/product")
        )
        self.assertFalse(
            is_official_url("https://private-blog.example/forward")
        )
        self.assertFalse(
            is_official_url("http://www.ksure.or.kr/insecure")
        )
        self.assertFalse(
            is_official_url(
                "https://www.ksure.or.kr/product",
                allowed_domains=[],
            )
        )

    def test_offline_kb_has_only_official_sources(self):
        records = load_official_kb()
        self.assertGreaterEqual(len(records), 8)
        self.assertTrue(
            all(is_official_url(item.source.url) for item in records)
        )
        categories = {item.category for item in records}
        self.assertTrue(
            {
                "FORWARD",
                "FX_RISK_INSURANCE",
                "FX_DEPOSIT",
                "TRADE_FINANCE_LOAN",
                "POLICY_FINANCE",
                "EXPORT_CREDIT_GUARANTEE",
            }.issubset(categories)
        )

    def test_offline_search_returns_candidates_with_unknown_eligibility(self):
        result = search_offline_kb(
            query="선물환 환변동보험",
            trade_type="IMPORT",
        )
        self.assertTrue(result.candidates)
        self.assertTrue(
            all(item.eligibility == "unknown" for item in result.candidates)
        )
        self.assertTrue(
            all("IMPORT" in item.trade_types for item in result.candidates)
        )
        for candidate in result.candidates:
            self.assertTrue(candidate.target_customers)
            self.assertTrue(candidate.key_conditions)
            self.assertTrue(candidate.required_documents)
            self.assertTrue(candidate.strategy_connection_reason)
            self.assertEqual(
                candidate.verification_status,
                "OFFICIAL_SOURCE_VERIFIED",
            )
            self.assertTrue(candidate.limitations)

    def test_offline_search_does_not_return_unrelated_records(self):
        result = search_offline_kb(
            query="완전히무관한검색어",
            trade_type="IMPORT",
        )
        self.assertEqual(result.candidates, [])

    def test_unofficial_source_is_filtered(self):
        record = {
            "product_id": "bad",
            "name": "광고 상품",
            "institution": "Unknown",
            "category": "FORWARD",
            "trade_types": ["IMPORT"],
            "keywords": ["선물환"],
            "summary": "Unofficial",
            "eligibility": "unknown",
            "approval_status": "consultation_required",
            "source": {
                "title": "Blog",
                "url": "https://blog.invalid/product",
                "verified_at": "2026-07-23",
                "evidence_summary": "Unofficial",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kb.json"
            path.write_text(
                json.dumps([record]),
                encoding="utf-8",
            )
            self.assertEqual(load_official_kb(path), [])

    def test_web_search_mock_keeps_only_allowlisted_sources(self):
        calls = []

        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output_text="공식 후보이며 기관 상담이 필요합니다.",
                output=[
                    SimpleNamespace(
                        action=SimpleNamespace(
                            sources=[
                                {
                                    "title": "K-SURE",
                                    "url": (
                                        "https://www.ksure.or.kr/"
                                        "rh-kr/cntnts/i-166/web.do"
                                    ),
                                },
                                {
                                    "title": "Blog",
                                    "url": "https://blog.invalid/ad",
                                },
                            ]
                        ),
                        content=[],
                    )
                ],
            )

        client = SimpleNamespace(
            responses=SimpleNamespace(create=create)
        )
        result = search_official_web(
            query="수출신용보증",
            trade_type="EXPORT",
            settings=Settings(
                openai_api_key="test-only",
                enable_official_web_search=True,
            ),
            client=client,
            use_cache=False,
        )
        self.assertEqual(len(result.candidates), 1)
        self.assertIn("ksure.or.kr", result.candidates[0].source.url)
        self.assertFalse(calls[0]["store"])
        self.assertIn(
            "allowed_domains",
            calls[0]["tools"][0]["filters"],
        )

    def test_fresh_web_search_cache_avoids_second_api_call(self):
        calls = []

        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output_text="공식 후보이며 기관 상담이 필요합니다.",
                output=[
                    SimpleNamespace(
                        action=SimpleNamespace(
                            sources=[
                                {
                                    "title": "K-SURE",
                                    "url": (
                                        "https://www.ksure.or.kr/"
                                        "rh-kr/cntnts/i-166/web.do"
                                    ),
                                }
                            ]
                        ),
                        content=[],
                    )
                ],
            )

        client = SimpleNamespace(
            responses=SimpleNamespace(create=create)
        )
        settings = Settings(
            openai_api_key="test-only",
            enable_official_web_search=True,
            official_search_cache_ttl_hours=24,
        )
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            first = search_official_web(
                query="수출신용보증",
                trade_type="EXPORT",
                settings=settings,
                client=client,
                cache_dir=cache_dir,
            )
            second = search_official_web(
                query="수출신용보증",
                trade_type="EXPORT",
                settings=settings,
                client=client,
                cache_dir=cache_dir,
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(first.candidates, second.candidates)
        self.assertTrue(
            any("캐시 사용" in item for item in second.warnings)
        )

    def test_stale_web_search_cache_forces_refresh(self):
        calls = []

        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output_text="공식 후보이며 기관 상담이 필요합니다.",
                output=[
                    SimpleNamespace(
                        action=SimpleNamespace(
                            sources=[
                                {
                                    "title": "K-SURE",
                                    "url": (
                                        "https://www.ksure.or.kr/"
                                        "rh-kr/cntnts/i-166/web.do"
                                    ),
                                }
                            ]
                        ),
                        content=[],
                    )
                ],
            )

        client = SimpleNamespace(
            responses=SimpleNamespace(create=create)
        )
        settings = Settings(
            openai_api_key="test-only",
            enable_official_web_search=True,
            official_search_cache_ttl_hours=24,
        )
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            search_official_web(
                query="수출신용보증",
                trade_type="EXPORT",
                settings=settings,
                client=client,
                cache_dir=cache_dir,
            )
            cache_path = next(cache_dir.glob("*.json"))
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            payload["cached_at"] = "2020-01-01T00:00:00+00:00"
            cache_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            refreshed = search_official_web(
                query="수출신용보증",
                trade_type="EXPORT",
                settings=settings,
                client=client,
                cache_dir=cache_dir,
            )

        self.assertEqual(len(calls), 2)
        self.assertTrue(
            any("TTL" in item for item in refreshed.warnings)
        )


class Stage5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = run_offline_demo()

    def _narrative_draft(self, explanation=None):
        registry = build_grounding_registry(
            self.demo["report"].report_json
        )
        text = explanation or (
            "확정된 입력의 의미를 확인하고 기관 상담에서 적용 범위를 "
            "점검해야 합니다."
        )
        return Stage5NarrativeDraft(
            narratives=[
                Stage5NarrativeItem(
                    source_id=item.source_id,
                    explanation=text,
                )
                for item in registry
            ]
        )

    def test_no_key_uses_deterministic_fallback(self):
        report = self.demo["report"]
        self.assertEqual(report.status, "DETERMINISTIC_FALLBACK")
        self.assertTrue(report.critique.passed)
        self.assertEqual(report.revision_count, 0)
        self.assertEqual(report.fallback_reason, "NO_API_KEY")

    def test_report_has_traceable_json_paths(self):
        report = self.demo["report"]
        self.assertGreaterEqual(report.markdown.count("[source:"), 5)
        self.assertIn(
            self.demo["stage2"].base_required_or_proceeds_krw,
            report.markdown,
        )
        for index in range(3):
            self.assertIn(
                "[source: stage3.candidates.{}]".format(index),
                report.markdown,
            )

    def test_critic_rejects_invented_number(self):
        report = self.demo["report"]
        critique = critique_report(
            markdown=report.markdown + "\n근거 없는 금액 987654321원",
            source_bundle=report.report_json,
            scenario_kind=self.demo["stage1"].kind,
            probability_valid=self.demo["stage1"].probability_valid,
        )
        self.assertFalse(critique.passed)
        self.assertTrue(
            any("987654321" in issue for issue in critique.issues)
        )
        self.assertFalse(critique.numeric_consistency)
        self.assertLess(critique.score, 100)
        self.assertTrue(critique.revision_instructions)

    def test_critic_rejects_probability_without_probabilities(self):
        report = self.demo["report"]
        critique = critique_report(
            markdown=report.markdown + "\n부족 확률은 77% 확률입니다.",
            source_bundle=report.report_json,
            scenario_kind="STRESS",
            probability_valid=False,
        )
        self.assertFalse(critique.passed)

    def test_critic_rejects_nonexistent_source_path(self):
        report = self.demo["report"]
        critique = critique_report(
            markdown=report.markdown
            + "\n추가 주장 [source: stage2.does_not_exist]",
            source_bundle=report.report_json,
            scenario_kind="STRESS",
            probability_valid=False,
        )
        self.assertFalse(critique.passed)
        self.assertTrue(
            any("존재하지 않는 JSON path" in item for item in critique.issues)
        )

    def test_critic_rejects_number_cited_to_unrelated_path(self):
        report = self.demo["report"]
        amount = self.demo["stage2"].total_foreign_amount
        critique = critique_report(
            markdown=report.markdown
            + "\n금액 {} [source: stage2.currency]".format(amount),
            source_bundle=report.report_json,
            scenario_kind="STRESS",
            probability_valid=False,
        )
        self.assertFalse(critique.passed)
        self.assertTrue(
            any("뒷받침하지 않는 숫자" in item for item in critique.issues)
        )

    def test_stress_is_not_called_prediction(self):
        self.assertIn(
            "예측이 아니라 스트레스 가정",
            self.demo["report"].markdown,
        )

    def test_valid_llm_explanation_passes_critic(self):
        calls = []

        def parse(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output_parsed=self._narrative_draft()
            )

        client = SimpleNamespace(
            responses=SimpleNamespace(parse=parse)
        )
        result = generate_report(
            extraction=self.demo["extraction"],
            confirmation=self.demo["confirmation"],
            stage1=self.demo["stage1"],
            stage2=self.demo["stage2"],
            stage3=self.demo["stage3"],
            stage4=self.demo["stage4"],
            confirmed_transaction=(
                self.demo["workflow_state"].confirmed_transaction
            ),
            consultation_packet=self.demo[
                "consultation_packet"
            ].packet,
            settings=Settings(openai_api_key="test-only"),
            client=client,
        )
        self.assertEqual(result.status, "LLM_PASS")
        self.assertEqual(result.revision_count, 0)
        self.assertEqual(result.generation_provider, "OPENAI")
        self.assertTrue(result.critique.passed, result.critique.issues)
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0]["store"])
        self.assertIs(
            calls[0]["text_format"],
            Stage5NarrativeDraft,
        )
        self.assertIn("검증된 AI 설명", result.markdown)

    def test_critic_feedback_is_used_by_exactly_one_revision(self):
        calls = []
        invalid = self._narrative_draft("가입 가능합니다.")
        valid = self._narrative_draft()

        def parse(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return SimpleNamespace(output_parsed=invalid)
            return SimpleNamespace(output_parsed=valid)

        client = SimpleNamespace(
            responses=SimpleNamespace(parse=parse)
        )
        result = generate_report(
            extraction=self.demo["extraction"],
            confirmation=self.demo["confirmation"],
            stage1=self.demo["stage1"],
            stage2=self.demo["stage2"],
            stage3=self.demo["stage3"],
            stage4=self.demo["stage4"],
            confirmed_transaction=(
                self.demo["workflow_state"].confirmed_transaction
            ),
            consultation_packet=self.demo[
                "consultation_packet"
            ].packet,
            settings=Settings(openai_api_key="test-only"),
            client=client,
            max_revisions=1,
        )

        self.assertEqual(result.status, "LLM_REVISED_PASS")
        self.assertEqual(result.revision_count, 1)
        self.assertEqual(len(calls), 2)
        self.assertIn(
            "validation_feedback",
            calls[1]["input"][1]["content"],
        )

    def test_report_api_failure_uses_fallback_without_raising(self):
        def parse(**unused_kwargs):
            raise RuntimeError("provider unavailable")

        client = SimpleNamespace(
            responses=SimpleNamespace(parse=parse)
        )
        result = generate_report(
            extraction=self.demo["extraction"],
            confirmation=self.demo["confirmation"],
            stage1=self.demo["stage1"],
            stage2=self.demo["stage2"],
            stage3=self.demo["stage3"],
            stage4=self.demo["stage4"],
            confirmed_transaction=(
                self.demo["workflow_state"].confirmed_transaction
            ),
            settings=Settings(openai_api_key="test-only"),
            client=client,
        )

        self.assertEqual(result.status, "DETERMINISTIC_FALLBACK")
        self.assertEqual(result.fallback_reason, "API_FAILURE")
        self.assertEqual(result.revision_count, 0)

    def test_empty_retrieval_blocks_llm_product_invention(self):
        empty_stage4 = Stage4Result(
            mode="OFFLINE_KB",
            query="no grounded products",
        )
        invented = self.demo["report"].markdown.replace(
            "\n".join(
                [
                    line
                    for line in self.demo["report"].markdown.splitlines()
                    if line.startswith("- 환변동보험 검토")
                ]
            ),
            "- 가상은행 확정승인상품",
        )

        calls = []

        def parse(**unused_kwargs):
            calls.append(unused_kwargs)
            return SimpleNamespace(
                output_parsed=self._narrative_draft()
            )

        client = SimpleNamespace(
            responses=SimpleNamespace(parse=parse)
        )
        result = generate_report(
            extraction=self.demo["extraction"],
            confirmation=self.demo["confirmation"],
            stage1=self.demo["stage1"],
            stage2=self.demo["stage2"],
            stage3=self.demo["stage3"],
            stage4=empty_stage4,
            confirmed_transaction=(
                self.demo["workflow_state"].confirmed_transaction
            ),
            settings=Settings(openai_api_key="test-only"),
            client=client,
        )

        self.assertEqual(result.status, "DETERMINISTIC_FALLBACK")
        self.assertEqual(calls, [])
        self.assertEqual(result.fallback_reason, "DETERMINISTIC_POLICY")
        self.assertNotIn("가상은행", result.markdown)
        self.assertIn("공식 출처가 확인된 후보가 없습니다.", result.markdown)

    def test_two_critic_failures_use_deterministic_fallback(self):
        calls = []
        invalid = self._narrative_draft("가입 가능합니다.")

        def parse(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_parsed=invalid)

        client = SimpleNamespace(
            responses=SimpleNamespace(parse=parse)
        )
        result = generate_report(
            extraction=self.demo["extraction"],
            confirmation=self.demo["confirmation"],
            stage1=self.demo["stage1"],
            stage2=self.demo["stage2"],
            stage3=self.demo["stage3"],
            stage4=self.demo["stage4"],
            confirmed_transaction=(
                self.demo["workflow_state"].confirmed_transaction
            ),
            settings=Settings(openai_api_key="test-only"),
            client=client,
        )
        self.assertEqual(result.status, "DETERMINISTIC_FALLBACK")
        self.assertEqual(len(calls), 2)
        self.assertTrue(result.critique.passed)
        self.assertEqual(result.revision_count, 1)
        self.assertEqual(result.fallback_reason, "CRITIC_REJECTED")


if __name__ == "__main__":
    unittest.main()
