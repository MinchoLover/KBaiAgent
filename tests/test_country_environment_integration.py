import json
import unittest

from src.application.consultation_service import build_decision_support
from src.config import Settings
from src.country_environment.assessment import (
    assess_country_trade_environment,
)
from src.demo import run_decision_support_demo
from src.workflow.orchestrator import WorkflowOrchestrator
from src.workflow.state import WorkflowState


class CountryEnvironmentIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = run_decision_support_demo("SELLER")
        cls.us_input = cls.demo["country_environment_input"]
        cls.us_assessment = cls.demo["country_environment_assessment"]
        cls.br_input = cls.us_input.model_copy(
            update={"counterparty_country": "BR"}
        )
        cls.br_assessment = assess_country_trade_environment(cls.br_input)

    def _decision(self, assessment):
        return build_decision_support(
            case_id=self.demo["workflow_state"].case_id,
            extraction=self.demo["extraction"],
            confirmation=self.demo["confirmation"],
            stage1=self.demo["stage1"],
            stage2_input=self.demo["stage2_input"],
            stage2_result=self.demo["stage2"],
            trade_settlement_risk=self.demo[
                "trade_risk_assessment"
            ],
            country_environment=assessment,
            official_candidate_shortlist=self.demo[
                "official_candidate_shortlist"
            ],
            generated_at="2026-07-23T09:00:00+09:00",
        )

    def test_packet_binds_country_assessment_and_topics(self):
        us_decision = self._decision(self.us_assessment)
        br_decision = self._decision(self.br_assessment)

        self.assertEqual(
            us_decision.consultation_packet.packet.country_environment,
            self.us_assessment,
        )
        self.assertEqual(
            br_decision.consultation_packet.packet.country_environment,
            self.br_assessment,
        )
        self.assertNotEqual(
            us_decision.consultation_packet.packet.input_hash,
            br_decision.consultation_packet.packet.input_hash,
        )
        self.assertTrue(
            any(
                item.country_environment_review_needs
                for item in br_decision.consultation_topics
            )
        )
        self.assertTrue(
            any(
                "PAYMENT_TRANSFER_PROTECTION_REVIEW"
                in item.country_environment_review_needs
                for item in br_decision.consultation_topics
            )
        )
        repeated = self._decision(self.br_assessment)
        self.assertEqual(
            [item.model_dump() for item in br_decision.consultation_topics],
            [item.model_dump() for item in repeated.consultation_topics],
        )

    def test_auxiliary_country_step_preserves_stages_one_to_four(self):
        state = WorkflowState.model_validate(
            self.demo["workflow_state"].model_dump()
        )
        before = {
            "market_risk": state.market_risk.model_dump(),
            "cashflow": state.cashflow.model_dump(),
            "hedge": state.hedge.model_dump(),
            "product_search": state.product_search.model_dump(),
            "selected_strategy": (
                state.selected_strategy.model_dump()
                if state.selected_strategy is not None
                else None
            ),
        }

        updated = WorkflowOrchestrator(
            settings=Settings()
        ).run_country_environment(state, self.br_input)

        self.assertEqual(
            updated.market_risk.model_dump(),
            before["market_risk"],
        )
        self.assertEqual(
            updated.cashflow.model_dump(),
            before["cashflow"],
        )
        self.assertEqual(
            updated.hedge.model_dump(),
            before["hedge"],
        )
        self.assertEqual(
            updated.product_search.model_dump(),
            before["product_search"],
        )
        self.assertEqual(
            (
                updated.selected_strategy.model_dump()
                if updated.selected_strategy is not None
                else None
            ),
            before["selected_strategy"],
        )
        self.assertEqual(
            updated.country_environment.data.country,
            "BR",
        )
        self.assertIsNone(updated.report)
        self.assertIsNone(updated.final_report)

    def test_workflow_trace_is_safe_and_source_ids_only(self):
        state = WorkflowState.model_validate(
            self.demo["workflow_state"].model_dump()
        )
        updated = WorkflowOrchestrator(
            settings=Settings()
        ).run_country_environment(state, self.br_input)
        result = updated.country_environment
        serialized = json.dumps(
            {
                "evidence": result.evidence,
                "trace": updated.trace[-1].model_dump(),
            },
            ensure_ascii=False,
            default=str,
        )

        self.assertIn("snapshot_id=", serialized)
        self.assertIn("source_record_ids=", serialized)
        self.assertNotIn("official_url", serialized)
        self.assertNotIn("raw_value", serialized)
        self.assertNotIn("api_key", serialized.lower())
        self.assertNotIn("2.2857464902475", serialized)

    def test_country_signal_does_not_change_product_contract(self):
        stage4_before = [
            (
                item.product_id,
                item.eligibility,
                item.approval_status,
                item.relevance_score,
            )
            for item in self.demo["stage4"].candidates
        ]
        self._decision(self.br_assessment)
        stage4_after = [
            (
                item.product_id,
                item.eligibility,
                item.approval_status,
                item.relevance_score,
            )
            for item in self.demo["stage4"].candidates
        ]

        self.assertEqual(stage4_after, stage4_before)
        self.assertLessEqual(
            len(
                self.demo[
                    "official_candidate_shortlist"
                ].candidates
            ),
            3,
        )
        for item in self.demo[
            "official_candidate_shortlist"
        ].candidates:
            self.assertEqual(item.eligibility, "unknown")
            self.assertEqual(
                item.approval_status,
                "consultation_required",
            )

    def test_country_change_does_not_change_cashflow_or_hedge(self):
        before_stage2 = self.demo["stage2"].model_dump()
        before_stage3 = self.demo["stage3"].model_dump()

        self._decision(self.br_assessment)

        self.assertEqual(
            self.demo["stage2"].model_dump(),
            before_stage2,
        )
        self.assertEqual(
            self.demo["stage3"].model_dump(),
            before_stage3,
        )


if __name__ == "__main__":
    unittest.main()
