import json
import unittest
from unittest.mock import Mock

from sample_data import sample_extraction
from schemas import ConfirmationState
from src.config import Settings
from src.demo import run_offline_demo
from src.domain.product_models import Stage4Result
from src.workflow.orchestrator import (
    WorkflowOrchestrator,
    WorkflowRequest,
)
from src.workflow.result import StageStatus
from validators import apply_deterministic_review_state


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = run_offline_demo()

    def _confirmed_state(self, orchestrator=None):
        workflow = orchestrator or WorkflowOrchestrator(settings=Settings())
        return workflow.initialize(
            mode="OFFLINE",
            extraction=self.demo["extraction"],
            validation=self.demo["validation"],
            confirmation=self.demo["confirmation"],
        )

    def _request(self, **updates):
        values = {
            "stage2_input": self.demo["stage2_input"],
            "manual_base_rate": "1400",
            "stage1_mode": "MANUAL_STRESS",
            "product_search_mode": "OFFLINE_KB",
        }
        values.update(updates)
        return WorkflowRequest(**values)

    def test_offline_orchestrator_runs_without_streamlit(self):
        orchestrator = WorkflowOrchestrator(settings=Settings())
        state = orchestrator.run(
            self._confirmed_state(orchestrator),
            self._request(),
        )

        self.assertEqual(state.final_status, StageStatus.SUCCEEDED)
        self.assertIsNotNone(state.cashflow.data)
        self.assertEqual(len(state.hedge.data.candidates), 3)
        self.assertTrue(state.product_search.data.candidates)
        self.assertEqual(
            state.report.status,
            StageStatus.FALLBACK,
        )
        self.assertEqual(
            [event.stage for event in state.trace],
            [
                "intake",
                "market_risk",
                "cashflow",
                "hedge",
                "product_search",
                "report",
            ],
        )

    def test_cashflow_is_blocked_before_human_confirmation(self):
        extraction, validation = apply_deterministic_review_state(
            sample_extraction("BUYER"),
            company_role="BUYER",
            company_country="KR",
            confirmations=ConfirmationState(),
        )
        cashflow_runner = Mock()
        orchestrator = WorkflowOrchestrator(
            settings=Settings(),
            cashflow_runner=cashflow_runner,
        )
        state = orchestrator.initialize(
            mode="OFFLINE",
            extraction=extraction,
            validation=validation,
        )

        state = orchestrator.run_cashflow(
            state,
            self.demo["stage2_input"],
        )

        self.assertEqual(
            state.cashflow.status,
            StageStatus.WAITING_FOR_USER,
        )
        self.assertEqual(state.final_status, StageStatus.WAITING_FOR_USER)
        cashflow_runner.assert_not_called()

    def test_missing_required_field_waits_for_user(self):
        extraction = sample_extraction("BUYER").model_copy(
            update={"currency": None},
        )
        extraction, validation = apply_deterministic_review_state(
            extraction,
            company_role="BUYER",
            company_country="KR",
            confirmations=ConfirmationState(),
        )
        state = WorkflowOrchestrator(settings=Settings()).initialize(
            mode="OFFLINE",
            extraction=extraction,
            validation=validation,
        )

        self.assertEqual(state.intake.status, StageStatus.WAITING_FOR_USER)
        self.assertIn("currency", validation.missing_required_fields)
        self.assertFalse(state.user_confirmed)
        self.assertEqual(
            state.extraction_confidence,
            "REVIEW_REQUIRED",
        )

    def test_stage1_adapter_failure_uses_manual_stress_fallback(self):
        def fail_loader(**unused_kwargs):
            raise RuntimeError("external adapter unavailable")

        orchestrator = WorkflowOrchestrator(
            settings=Settings(),
            stage1_loader=fail_loader,
        )
        state = orchestrator.run_market_risk(
            self._confirmed_state(orchestrator),
            stage2_input=self.demo["stage2_input"],
            manual_base_rate="1400",
            mode="EXTERNAL_STAGE1",
        )

        self.assertEqual(
            state.market_risk.status,
            StageStatus.FALLBACK,
        )
        self.assertTrue(state.market_risk.fallback_used)
        self.assertEqual(
            [item.name for item in state.market_risk.data.scenario_set.scenarios],
            [
                "STRESS_-10.00PCT",
                "STRESS_-5.00PCT",
                "STRESS_-3.00PCT",
                "BASE",
                "STRESS_+3.00PCT",
                "STRESS_+5.00PCT",
                "STRESS_+10.00PCT",
            ],
        )

    def test_official_product_failure_falls_back_to_offline_kb(self):
        def fail_official(**unused_kwargs):
            raise RuntimeError("official search unavailable")

        offline_search = Mock(return_value=self.demo["stage4"])
        orchestrator = WorkflowOrchestrator(
            settings=Settings(
                openai_api_key="test-only",
                enable_official_web_search=True,
            ),
            official_product_search=fail_official,
            offline_product_search=offline_search,
        )
        state = orchestrator.run(
            self._confirmed_state(orchestrator),
            self._request(product_search_mode="OFFICIAL_WEB_SEARCH"),
        )

        self.assertEqual(
            state.product_search.status,
            StageStatus.FALLBACK,
        )
        self.assertTrue(state.product_search.fallback_used)
        offline_search.assert_called_once()
        self.assertEqual(state.final_status, StageStatus.SUCCEEDED)

    def test_empty_official_product_result_stays_empty(self):
        empty = Stage4Result(
            mode="OFFLINE_KB",
            query="no grounded result",
        )
        offline_search = Mock(return_value=empty)
        orchestrator = WorkflowOrchestrator(
            settings=Settings(),
            offline_product_search=offline_search,
        )
        state = orchestrator.run(
            self._confirmed_state(orchestrator),
            self._request(product_query="no grounded result"),
        )

        self.assertEqual(state.product_search.data.candidates, [])
        self.assertIn(
            "공식 출처가 확인된 후보가 없습니다.",
            state.final_report.markdown,
        )
        self.assertTrue(state.critic_result.passed)

    def test_cashflow_failure_is_explicit_and_stops_later_stages(self):
        def fail_cashflow(unused_input, unused_scenarios):
            raise ValueError("deterministic input invalid")

        orchestrator = WorkflowOrchestrator(
            settings=Settings(),
            cashflow_runner=fail_cashflow,
        )
        state = orchestrator.run(
            self._confirmed_state(orchestrator),
            self._request(),
        )

        self.assertEqual(state.cashflow.status, StageStatus.FAILED)
        self.assertEqual(state.final_status, StageStatus.FAILED)
        self.assertIsNone(state.hedge)
        self.assertIsNone(state.final_report)

    def test_trace_excludes_document_content_and_financial_payloads(self):
        state = WorkflowOrchestrator(settings=Settings()).run(
            self._confirmed_state(),
            self._request(),
        )
        serialized = json.dumps(
            [item.model_dump(mode="json") for item in state.trace],
            ensure_ascii=False,
        )

        self.assertNotIn("source_text", serialized)
        self.assertNotIn("confirmed_values", serialized)
        self.assertNotIn(
            self.demo["stage2"].total_foreign_amount,
            serialized,
        )
        self.assertNotIn("data", serialized)

    def test_reported_amount_is_the_cashflow_engine_amount(self):
        state = WorkflowOrchestrator(settings=Settings()).run(
            self._confirmed_state(),
            self._request(),
        )

        amount = state.cashflow.data.base_required_or_proceeds_krw
        self.assertIn(amount, state.final_report.markdown)
        self.assertEqual(
            amount,
            state.final_report.report_json[
                "stage2"
            ]["base_required_or_proceeds_krw"],
        )

    def test_stage_results_have_timing_provider_and_case_id(self):
        state = WorkflowOrchestrator(settings=Settings()).run(
            self._confirmed_state(),
            self._request(),
        )

        self.assertTrue(state.case_id.startswith("case_"))
        for event in state.trace:
            self.assertIsNotNone(event.started_at)
            self.assertIsNotNone(event.finished_at)
            self.assertGreaterEqual(event.duration_ms, 0)
            self.assertTrue(event.provider)
            self.assertEqual(event.case_id, state.case_id)

    def test_intake_trace_preserves_adapter_timing_and_retry_count(self):
        state = WorkflowOrchestrator(settings=Settings()).initialize(
            mode="ONLINE",
            extraction=self.demo["extraction"],
            validation=self.demo["validation"],
            confirmation=self.demo["confirmation"],
            intake_provider="openai:test-model",
            intake_duration_ms=1250,
            intake_retry_count=1,
        )

        self.assertEqual(state.intake.provider, "openai:test-model")
        self.assertEqual(state.intake.duration_ms, 1250)
        self.assertEqual(state.intake.retry_count, 1)
        self.assertEqual(
            state.extraction_confidence,
            "HUMAN_CONFIRMED",
        )
        self.assertEqual(state.trace[0].duration_ms, 1250)
        self.assertEqual(state.trace[0].retry_count, 1)


if __name__ == "__main__":
    unittest.main()
