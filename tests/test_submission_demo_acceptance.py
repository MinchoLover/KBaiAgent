import unittest
from decimal import Decimal
from typing import Any, Dict, List

from scripts.verify_golden_user_flow import build_golden_user_flow_artifacts
from src.application.official_candidate_service import (
    project_auxiliary_service_candidates,
    project_official_candidate_signals,
    shortlist_official_candidates,
)
from src.consultation.trade_settlement_risk import (
    create_trade_risk_confirmation,
)
from src.domain.product_models import (
    OfficialCandidateInputProfile,
    assess_official_candidate_input_profile,
)
from src.domain.trade_risk_models import TradeSettlementRiskInput
from src.stage4.local_kb import active_official_catalogue_by_id


class SubmissionDemoAcceptanceTests(unittest.TestCase):
    """Freeze the five submission scenarios on the canonical Golden trade."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = build_golden_user_flow_artifacts()
        cls.golden = cls.artifacts["golden"]
        cls.workflow = cls.artifacts["workflow"]
        cls.transaction = cls.workflow.confirmed_transaction
        cls.decision = cls.artifacts["decision"]
        cls.packet = cls.decision.consultation_packet.packet
        trade_input = TradeSettlementRiskInput(
            confirmed_trade_sha256=cls.transaction.source_sha256,
            trade_type="EXPORT",
            **cls.golden["demo_inputs"]["user_confirmed_trade_inputs"]
        )
        cls.trade_risk_confirmation = create_trade_risk_confirmation(
            confirmed_input=trade_input,
            confirmed_by="submission-acceptance",
            confirmed_at="2026-08-03T09:00:00+09:00",
        )

    def _profile(self, **values: Any) -> OfficialCandidateInputProfile:
        field_sources: Dict[str, str] = {
            field_name: (
                "COMPANY_PROFILE_CONFIRMED"
                if field_name in {"sme_status", "annual_export_band"}
                else "USER_CONFIRMED"
            )
            for field_name in values
        }
        return OfficialCandidateInputProfile(
            **values,
            field_sources=field_sources,
            confirmed_at="2026-08-03T09:00:00+09:00",
            confirmed_by="submission-acceptance",
            bound_transaction_fingerprint=(
                self.transaction.input_fingerprint
            ),
        )

    def _shortlist(self, profile: OfficialCandidateInputProfile):
        return shortlist_official_candidates(
            stage4_result=self.workflow.product_search.data,
            trade_type="EXPORT",
            consultation_topics=self.decision.consultation_topics,
            consultation_packet=self.packet,
            confirmed_transaction=self.transaction,
            trade_risk_confirmation=self.trade_risk_confirmation,
            official_candidate_input_profile=profile,
        )

    def _auxiliary(self, profile: OfficialCandidateInputProfile):
        signals = project_official_candidate_signals(
            trade_type="EXPORT",
            consultation_categories=[
                item.category for item in self.decision.consultation_topics
            ],
            consultation_packet=self.packet,
            confirmed_transaction=self.transaction,
            trade_risk_confirmation=self.trade_risk_confirmation,
            official_candidate_input_profile=profile,
        )
        return project_auxiliary_service_candidates(
            trade_type="EXPORT",
            signals=signals,
            official_candidate_input_profile=profile,
            confirmed_transaction=self.transaction,
        )

    @staticmethod
    def _ids(candidates) -> List[str]:
        return [item.product_id for item in candidates]

    def test_demo_a_golden_trade_numbers_and_top_three_are_frozen(self):
        shortlist = self.artifacts["shortlist"]
        stage2 = self.workflow.cashflow.data
        down_five = next(
            item
            for item in stage2.scenario_results
            if item.scenario_name == "DOWN_5"
        )
        self.assertEqual(
            self._ids(shortlist.candidates),
            [
                "ksure_short_term_export_insurance",
                "kb_star_fx_forward",
                "ksure_fx_insurance_general",
            ],
        )
        self.assertEqual(self.transaction.due_date, "2026-08-20")
        self.assertEqual(
            Decimal(stage2.total_foreign_amount),
            Decimal("100000"),
        )
        self.assertEqual(
            Decimal(stage2.base_required_or_proceeds_krw),
            Decimal("140000000"),
        )
        self.assertEqual(
            Decimal(down_five.fx_krw_inflow),
            Decimal("133000000"),
        )
        self.assertEqual(
            Decimal(down_five.loss_vs_base),
            Decimal("7000000"),
        )
        self.assertEqual(
            Decimal(down_five.ending_cash),
            Decimal("8000000"),
        )
        self.assertEqual(
            Decimal(down_five.maximum_buffer_shortfall),
            Decimal("2000000"),
        )
        self.assertEqual(Decimal(down_five.cash_deficit), Decimal("0"))
        self.assertEqual(
            Decimal(down_five.post_credit_shortfall),
            Decimal("0"),
        )
        self.assertEqual(
            self.packet.protection_summary.advance_payment_receipt,
            "UNKNOWN",
        )

    def test_demo_b_pre_shipment_manufacturing_finance(self):
        profile = self._profile(
            shipment_status="PRE_SHIPMENT",
            receivable_status="NOT_YET",
            funding_purposes=["MANUFACTURING"],
            bank_financing_intent="YES",
            receivable_financing_intent="NONE",
            early_cash_conversion_intent="NOT_APPLICABLE",
            policy_finance_need="NO",
        )
        shortlist = self._shortlist(profile)
        selected = self._ids(shortlist.candidates)
        self.assertEqual(
            selected,
            [
                "ksure_export_credit_guarantee_pre_shipment",
                "kb_star_fx_forward",
                "ksure_fx_insurance_general",
            ],
        )
        self.assertFalse(
            {
                "ksure_export_credit_guarantee_post_shipment",
                "ksure_export_credit_guarantee_purchase",
                "ksure_export_credit_guarantee_comprehensive_purchase",
                "kb_non_lc_export_bill_purchase",
                "ksure_short_term_export_insurance",
            }
            & set(selected)
        )

    def test_demo_c_completed_oa_receivable_purchase(self):
        profile = self._profile(
            shipment_status="COMPLETED",
            receivable_status="EXISTS",
            trade_form="GENERAL_EXPORT",
            relationship_scope="SINGLE_ONE_OFF",
            receivable_financing_intent="KB_RECEIVABLE_PURCHASE",
            early_cash_conversion_intent="YES",
            bank_financing_intent="YES",
            repayment_responsibility_acknowledgement="ACKNOWLEDGED",
            short_term_export_insurance_linkage_review="AGREED_TO_REVIEW",
        )
        shortlist = self._shortlist(profile)
        selected = self._ids(shortlist.candidates)
        self.assertEqual(selected[0], "kb_non_lc_export_bill_purchase")
        self.assertNotIn(
            "ksure_export_credit_guarantee_pre_shipment",
            selected,
        )
        self.assertNotIn(
            "ksure_export_credit_guarantee_comprehensive_purchase",
            selected,
        )
        evaluation_status = {
            item.catalogue_id: item.status
            for item in shortlist.candidate_evaluations
        }
        self.assertEqual(
            evaluation_status["ksure_export_credit_guarantee_purchase"],
            "ELIGIBLE_OVERFLOW",
        )
        self.assertNotIn(
            "ksure_export_credit_guarantee_purchase",
            shortlist.deferred_catalogue_ids,
        )

    def test_demo_d_pre_shipment_policy_finance_order(self):
        profile = self._profile(
            shipment_status="PRE_SHIPMENT",
            receivable_status="NOT_YET",
            funding_purposes=["MANUFACTURING"],
            bank_financing_intent="YES",
            receivable_financing_intent="NONE",
            early_cash_conversion_intent="NOT_APPLICABLE",
            sme_status="CONFIRMED",
            annual_export_band="AT_LEAST_USD_100K",
            market_entry_purpose="YES",
            policy_finance_need="YES",
            production_or_working_capital_need="YES",
        )
        shortlist = self._shortlist(profile)
        self.assertEqual(
            self._ids(shortlist.candidates),
            [
                "ksure_export_credit_guarantee_pre_shipment",
                "kosmes_export_funding",
                "kb_star_fx_forward",
            ],
        )
        policy = active_official_catalogue_by_id()["kosmes_export_funding"]
        self.assertEqual(policy.current_application_status, "UNKNOWN")
        self.assertTrue(
            any("승인" in limitation for limitation in policy.limitations)
        )

    def test_demo_e_conflict_blocks_and_declined_auxiliary_is_suppressed(self):
        conflict = self._profile(
            shipment_status="PRE_SHIPMENT",
            receivable_status="NOT_YET",
            customs_clearance="YES",
            credit_information_status="INSUFFICIENT",
            credit_investigation_intent="NO",
            receivable_financing_intent="NEGO_OR_PURCHASE",
            early_cash_conversion_intent="NO",
        )
        validation = assess_official_candidate_input_profile(conflict)
        self.assertEqual(
            [item.code for item in validation.hard_blocking_issues],
            ["RECEIVABLE_UNAVAILABLE_FOR_FINANCING"],
        )
        self.assertEqual(
            {item.code for item in validation.warning_issues},
            {
                "PRE_SHIPMENT_CUSTOMS_CLEARANCE_RECONFIRM",
                "CREDIT_INFORMATION_INSUFFICIENT_INVESTIGATION_DECLINED",
            },
        )
        corrected = self._profile(
            shipment_status="PRE_SHIPMENT",
            receivable_status="NOT_YET",
            customs_clearance="YES",
            credit_information_status="INSUFFICIENT",
            credit_investigation_intent="NO",
            receivable_financing_intent="NONE",
            early_cash_conversion_intent="NOT_APPLICABLE",
        )
        auxiliary = self._auxiliary(corrected)
        self.assertEqual(auxiliary.candidates, [])
        self.assertEqual(
            auxiliary.suppressed_catalogue_ids,
            ["ksure_foreign_company_credit_investigation"],
        )


if __name__ == "__main__":
    unittest.main()
