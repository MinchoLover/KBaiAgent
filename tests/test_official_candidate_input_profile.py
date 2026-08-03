import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError

from src.application.official_candidate_service import (
    project_auxiliary_service_candidates,
    project_official_candidate_signals,
    shortlist_official_candidates,
)
from src.application.consultation_service import build_decision_support
from src.config import Settings
from src.consultation.trade_settlement_risk import (
    create_trade_risk_confirmation,
)
from src.demo import run_decision_support_demo
from src.domain.consultation_models import ConsultationPacket
from src.domain.product_models import (
    OfficialCandidateInputProfile,
    ProductCandidate,
    Stage4Result,
    assess_official_candidate_input_profile,
)
from src.stage4.local_kb import (
    active_official_catalogue_by_id,
    load_official_kb,
)
from src.stage5.deterministic_fallback import generate_deterministic_report
from src.ui.state import (
    PIPELINE_KEYS,
    clear_confirmation_and_later,
    clear_downstream,
    input_signature,
    sync_input_signature,
    update_official_candidate_input_profile,
    validate_official_candidate_artifact_state,
)
from src.ui.layout import set_active_page
from src.workflow.orchestrator import WorkflowOrchestrator
from src.workflow.result import StageStatus
from src.workflow.state import WorkflowState


class OfficialCandidateInputProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = run_decision_support_demo("SELLER")
        cls.packet = cls.demo["consultation_packet"].packet
        cls.trade_risk = cls.demo["trade_risk_confirmation"]
        cls.confirmed_transaction = cls.demo[
            "workflow_state"
        ].confirmed_transaction
        cls.liquidity_topic = next(
            item
            for item in cls.demo["consultation_topics"]
            if item.category == "EXPORT_LIQUIDITY_REVIEW"
        )
        cls.catalogue = active_official_catalogue_by_id()

    def _profile(
        self,
        *,
        bound_transaction=None,
        confirmed_at="2026-08-02T09:00:00+09:00",
        confirmed_by="TEST_USER",
        source_overrides=None,
        **values
    ):
        sources = {
            field_name: (
                "COMPANY_PROFILE_CONFIRMED"
                if field_name in {"sme_status", "annual_export_band"}
                else "USER_CONFIRMED"
            )
            for field_name in values
        }
        sources.update(source_overrides or {})
        transaction = bound_transaction or self.confirmed_transaction
        return OfficialCandidateInputProfile(
            **values,
            field_sources=sources,
            confirmed_at=confirmed_at,
            confirmed_by=confirmed_by,
            bound_transaction_fingerprint=(
                transaction.input_fingerprint
            ),
        )

    def _stage4(self, product_id):
        record = self.catalogue[product_id]
        candidate = ProductCandidate.model_validate(
            {
                **record.model_dump(),
                "relevance_score": "1",
            }
        )
        return Stage4Result(
            mode="OFFLINE_KB",
            query=product_id,
            candidates=[candidate],
        )

    def _shortlist(self, product_id, profile, trade_risk=None):
        return shortlist_official_candidates(
            stage4_result=self._stage4(product_id),
            trade_type="EXPORT",
            consultation_topics=[self.liquidity_topic],
            consultation_packet=self.packet,
            confirmed_transaction=self.confirmed_transaction,
            trade_risk_confirmation=trade_risk,
            official_candidate_input_profile=profile,
        )

    def _full_shortlist(self, profile):
        return shortlist_official_candidates(
            stage4_result=self.demo["stage4"],
            trade_type="EXPORT",
            consultation_topics=self.demo["consultation_topics"],
            consultation_packet=self.packet,
            confirmed_transaction=self.confirmed_transaction,
            trade_risk_confirmation=self.trade_risk,
            official_candidate_input_profile=profile,
        )

    def _build_decision(self, profile, shortlist, auxiliary=None):
        return build_decision_support(
            case_id=self.demo["workflow_state"].case_id,
            extraction=self.demo["extraction"],
            confirmation=self.demo["confirmation"],
            stage1=self.demo["stage1"],
            stage2_input=self.demo["stage2_input"],
            stage2_result=self.demo["stage2"],
            trade_settlement_risk=self.demo["trade_risk_assessment"],
            country_environment=self.demo["country_environment_assessment"],
            trade_statistics=self.demo["trade_statistics_result"],
            official_candidate_shortlist=shortlist,
            official_candidate_input_profile=profile,
            auxiliary_service_candidates=auxiliary,
            generated_at="2026-08-02T09:00:00+09:00",
            confirmed_transaction=self.confirmed_transaction,
        )

    def assert_selected(self, product_id, profile, trade_risk=None):
        shortlist = self._shortlist(product_id, profile, trade_risk)
        self.assertEqual(
            [item.product_id for item in shortlist.candidates],
            [product_id],
        )

    def test_profile_unknown_no_and_not_applicable_are_distinct(self):
        profile = self._profile(
            early_cash_conversion_intent="NOT_APPLICABLE",
            bank_financing_intent="NO",
        )
        self.assertEqual(profile.shipment_status, "UNKNOWN")
        self.assertEqual(
            profile.early_cash_conversion_intent,
            "NOT_APPLICABLE",
        )
        self.assertEqual(profile.bank_financing_intent, "NO")
        with self.assertRaises(ValidationError):
            OfficialCandidateInputProfile(
                funding_purposes=["NONE", "MANUFACTURING"],
                field_sources={"funding_purposes": "USER_CONFIRMED"},
                confirmed_at="2026-08-02T09:00:00+09:00",
                confirmed_by="TEST_USER",
            )

    def test_profile_requires_provenance_and_has_stable_fingerprint(self):
        with self.assertRaises(ValidationError):
            OfficialCandidateInputProfile(shipment_status="COMPLETED")
        first = self._profile(
            funding_purposes=["RAW_MATERIAL_PROCUREMENT", "MANUFACTURING"]
        )
        second = self._profile(
            funding_purposes=["MANUFACTURING", "RAW_MATERIAL_PROCUREMENT"]
        )
        later = first.model_copy(
            update={"confirmed_at": "2026-08-03T09:00:00+09:00"}
        )
        self.assertEqual(first.input_fingerprint, second.input_fingerprint)
        self.assertEqual(first.input_fingerprint, later.input_fingerprint)
        changed_source = self._profile(
            funding_purposes=["MANUFACTURING", "RAW_MATERIAL_PROCUREMENT"],
            source_overrides={
                "funding_purposes": "DOCUMENT_CONFIRMED"
            },
        )
        self.assertNotEqual(
            first.input_fingerprint,
            changed_source.input_fingerprint,
        )

    def test_confirmed_payment_method_projection_is_fail_closed(self):
        base = self.trade_risk.confirmed_input
        expectations = {
            "DOCUMENTARY_CREDIT": {"HAS_LC"},
            "DOCUMENTARY_COLLECTION_DP": {
                "NON_LC_CONFIRMED",
                "PAYMENT_METHOD_DP",
            },
            "DOCUMENTARY_COLLECTION_DA": {
                "NON_LC_CONFIRMED",
                "PAYMENT_METHOD_DA",
            },
            "OPEN_ACCOUNT": {"NON_LC_CONFIRMED", "PAYMENT_METHOD_OA"},
            "OTHER": set(),
            "UNKNOWN": set(),
        }
        for method, expected in expectations.items():
            with self.subTest(method=method):
                changed = base.model_copy(
                    update={"balance_payment_method": method}
                )
                confirmation = create_trade_risk_confirmation(
                    confirmed_input=changed,
                    confirmed_by="TEST_USER",
                    confirmed_at="2026-08-02T09:00:00+09:00",
                )
                signals = project_official_candidate_signals(
                    trade_type="EXPORT",
                    consultation_categories=[],
                    consultation_packet=None,
                    confirmed_transaction=self.confirmed_transaction,
                    trade_risk_confirmation=confirmation,
                )
                self.assertTrue(expected.issubset(signals))
                if method in {"OTHER", "UNKNOWN"}:
                    self.assertNotIn("NON_LC_CONFIRMED", signals)
                    self.assertNotIn("PAYMENT_METHOD_OA", signals)

    def test_shipment_date_never_implies_completed(self):
        self.assertIsNotNone(self.confirmed_transaction.shipment_date)
        signals = project_official_candidate_signals(
            trade_type="EXPORT",
            consultation_categories=[],
            consultation_packet=None,
            confirmed_transaction=self.confirmed_transaction,
        )
        self.assertNotIn("SHIPMENT_COMPLETED", signals)

    def test_all_unknown_profile_keeps_all_new_targets_fail_closed(self):
        profile = OfficialCandidateInputProfile(
            bound_transaction_fingerprint=(
                self.confirmed_transaction.input_fingerprint
            )
        )
        financial_ids = (
            "ksure_export_credit_guarantee_pre_shipment",
            "ksure_export_credit_guarantee_post_shipment",
            "ksure_export_credit_guarantee_purchase",
            "ksure_export_credit_guarantee_comprehensive_purchase",
            "kb_non_lc_export_bill_purchase",
            "kosmes_export_funding",
        )
        for product_id in financial_ids:
            with self.subTest(product_id=product_id):
                self.assertEqual(
                    self._shortlist(product_id, profile).candidates,
                    [],
                )
        signals = project_official_candidate_signals(
            trade_type="EXPORT",
            consultation_categories=[],
            consultation_packet=None,
            confirmed_transaction=self.confirmed_transaction,
            official_candidate_input_profile=profile,
        )
        auxiliary = project_auxiliary_service_candidates(
            trade_type="EXPORT",
            signals=signals,
            official_candidate_input_profile=profile,
            confirmed_transaction=self.confirmed_transaction,
        )
        self.assertEqual(auxiliary.candidates, [])

    def test_new_counterparty_requires_confirmed_provenance(self):
        signals = project_official_candidate_signals(
            trade_type="EXPORT",
            consultation_categories=[],
            consultation_packet=None,
            trade_risk_confirmation=self.trade_risk,
        )
        self.assertIn("COUNTERPARTY_NEW", signals)
        changed_input = self.trade_risk.confirmed_input.model_copy(
            update={
                "field_sources": {
                    **self.trade_risk.confirmed_input.field_sources,
                    "counterparty_relationship": "UNKNOWN",
                }
            }
        )
        unconfirmed = create_trade_risk_confirmation(
            confirmed_input=changed_input,
            confirmed_by="TEST_USER",
            confirmed_at="2026-08-02T09:00:00+09:00",
        )
        unconfirmed_signals = project_official_candidate_signals(
            trade_type="EXPORT",
            consultation_categories=[],
            consultation_packet=None,
            trade_risk_confirmation=unconfirmed,
        )
        self.assertNotIn("COUNTERPARTY_NEW", unconfirmed_signals)

    def test_export_guarantee_positive_and_unknown_boundaries(self):
        pre = self._profile(
            shipment_status="PRE_SHIPMENT",
            funding_purposes=["RAW_MATERIAL_PROCUREMENT"],
            bank_financing_intent="YES",
        )
        self.assert_selected(
            "ksure_export_credit_guarantee_pre_shipment",
            pre,
        )
        pre_unknown = self._profile(
            shipment_status="PRE_SHIPMENT",
            bank_financing_intent="YES",
        )
        self.assertEqual(
            self._shortlist(
                "ksure_export_credit_guarantee_pre_shipment",
                pre_unknown,
            ).candidates,
            [],
        )

        post = self._profile(
            shipment_status="COMPLETED",
            receivable_status="EXISTS",
            trade_form="GENERAL_EXPORT",
            receivable_financing_intent="NEGO_OR_PURCHASE",
            short_term_export_insurance_linkage_review="AGREED_TO_REVIEW",
        )
        self.assert_selected(
            "ksure_export_credit_guarantee_post_shipment",
            post,
        )
        no_linkage = self._profile(
            shipment_status="COMPLETED",
            receivable_status="EXISTS",
            trade_form="GENERAL_EXPORT",
            receivable_financing_intent="NEGO_OR_PURCHASE",
            short_term_export_insurance_linkage_review="UNKNOWN",
        )
        self.assertEqual(
            self._shortlist(
                "ksure_export_credit_guarantee_post_shipment",
                no_linkage,
            ).candidates,
            [],
        )

    def test_purchase_guarantees_positive_and_negative_boundaries(self):
        purchase = self._profile(
            shipment_status="COMPLETED",
            receivable_status="EXISTS",
            trade_form="GENERAL_EXPORT",
            receivable_financing_intent="NEGO_OR_PURCHASE",
            repayment_responsibility_acknowledgement="ACKNOWLEDGED",
        )
        self.assert_selected(
            "ksure_export_credit_guarantee_purchase",
            purchase,
            self.trade_risk,
        )
        no_acknowledgement = self._profile(
            shipment_status="COMPLETED",
            receivable_status="EXISTS",
            trade_form="GENERAL_EXPORT",
            receivable_financing_intent="NEGO_OR_PURCHASE",
            repayment_responsibility_acknowledgement="UNKNOWN",
        )
        self.assertEqual(
            self._shortlist(
                "ksure_export_credit_guarantee_purchase",
                no_acknowledgement,
                self.trade_risk,
            ).candidates,
            [],
        )

        comprehensive = self._profile(
            shipment_status="COMPLETED",
            receivable_status="EXISTS",
            relationship_scope="RECURRING_MULTIPLE_BUYERS",
            receivable_financing_intent="NEGO_OR_PURCHASE",
            repayment_responsibility_acknowledgement="ACKNOWLEDGED",
        )
        self.assert_selected(
            "ksure_export_credit_guarantee_comprehensive_purchase",
            comprehensive,
            self.trade_risk,
        )
        one_off = self._profile(
            shipment_status="COMPLETED",
            receivable_status="EXISTS",
            relationship_scope="SINGLE_ONE_OFF",
            receivable_financing_intent="NEGO_OR_PURCHASE",
            repayment_responsibility_acknowledgement="ACKNOWLEDGED",
        )
        one_off_shortlist = self._shortlist(
            "ksure_export_credit_guarantee_comprehensive_purchase",
            one_off,
            self.trade_risk,
        )
        self.assertNotIn(
            "ksure_export_credit_guarantee_comprehensive_purchase",
            {item.product_id for item in one_off_shortlist.candidates},
        )
        self.assertIn(
            "ksure_export_credit_guarantee_purchase",
            {item.product_id for item in one_off_shortlist.candidates},
        )

    def test_profile_conflicts_and_reconfirmation_warnings_are_structured(self):
        hard_blocked = self._profile(
            shipment_status="PRE_SHIPMENT",
            receivable_status="NOT_YET",
            receivable_financing_intent="NEGO_OR_PURCHASE",
            early_cash_conversion_intent="NOT_APPLICABLE",
        )
        hard_result = assess_official_candidate_input_profile(hard_blocked)
        self.assertFalse(hard_result.recommendation_allowed)
        self.assertEqual(
            {
                item.code for item in hard_result.hard_blocking_issues
            },
            {
                "RECEIVABLE_UNAVAILABLE_FOR_FINANCING",
                "RECEIVABLE_FINANCING_NOT_APPLICABLE",
            },
        )

        warnings = self._profile(
            shipment_status="PRE_SHIPMENT",
            receivable_status="NOT_YET",
            customs_clearance="YES",
            credit_information_status="INSUFFICIENT",
            credit_investigation_intent="NO",
            receivable_financing_intent="NONE",
            early_cash_conversion_intent="NOT_APPLICABLE",
        )
        warning_result = assess_official_candidate_input_profile(warnings)
        self.assertTrue(warning_result.recommendation_allowed)
        self.assertEqual(len(warning_result.warning_issues), 2)
        self.assertTrue(
            all(item.user_message for item in warning_result.warning_issues)
        )

        completed_not_yet = self._profile(
            shipment_status="COMPLETED",
            receivable_status="NOT_YET",
        )
        completed_result = assess_official_candidate_input_profile(
            completed_not_yet
        )
        self.assertIn(
            "COMPLETED_RECEIVABLE_NOT_YET_RECONFIRM",
            {item.code for item in completed_result.warning_issues},
        )

        lc_intent = self._profile(
            receivable_financing_intent="NEGO_OR_PURCHASE"
        )
        lc_result = assess_official_candidate_input_profile(
            lc_intent,
            has_confirmed_lc=True,
        )
        self.assertIn(
            "LC_WITH_NON_LC_RECEIVABLE_FINANCING_RECONFIRM",
            {item.code for item in lc_result.warning_issues},
        )

    def test_all_required_hard_conflict_combinations_are_blocked(self):
        cases = {
            "pre_shipment_receivable": {
                "shipment_status": "PRE_SHIPMENT",
                "receivable_status": "EXISTS",
            },
            "missing_receivable_purchase": {
                "receivable_status": "NONE",
                "receivable_financing_intent": "NEGO_OR_PURCHASE",
            },
            "kb_without_early_cash": {
                "receivable_status": "EXISTS",
                "receivable_financing_intent": "KB_RECEIVABLE_PURCHASE",
                "early_cash_conversion_intent": "NO",
            },
            "not_applicable_early_cash": {
                "receivable_status": "EXISTS",
                "receivable_financing_intent": "NEGO_OR_PURCHASE",
                "early_cash_conversion_intent": "NOT_APPLICABLE",
            },
            "not_applicable_repayment": {
                "receivable_status": "EXISTS",
                "receivable_financing_intent": "NEGO_OR_PURCHASE",
                "repayment_responsibility_acknowledgement": (
                    "NOT_APPLICABLE"
                ),
            },
            "policy_no_with_positive_purpose": {
                "policy_finance_need": "NO",
                "market_entry_purpose": "YES",
            },
        }
        for name, values in cases.items():
            with self.subTest(name=name):
                result = assess_official_candidate_input_profile(
                    self._profile(**values)
                )
                self.assertFalse(result.recommendation_allowed)
                self.assertTrue(result.hard_blocking_issues)

    def test_explicit_receivable_and_intent_values_override_broad_signals(self):
        not_yet = self._profile(
            shipment_status="PRE_SHIPMENT",
            receivable_status="NOT_YET",
            receivable_financing_intent="NONE",
            early_cash_conversion_intent="NOT_APPLICABLE",
        )
        signals = project_official_candidate_signals(
            trade_type="EXPORT",
            consultation_categories=["EXPORT_RECEIVABLE_PROTECTION"],
            consultation_packet=self.packet,
            confirmed_transaction=self.confirmed_transaction,
            trade_risk_confirmation=self.trade_risk,
            official_candidate_input_profile=not_yet,
        )
        self.assertNotIn("HAS_EXPORT_RECEIVABLE", signals)
        self.assertNotIn("RECEIVABLE_PURCHASE_OR_NEGO_INTENT", signals)
        self.assertIn("RECEIVABLE_NOT_YET", signals)
        self.assertIn("RECEIVABLE_PURCHASE_NOT_NEEDED", signals)

        no_policy = self._profile(policy_finance_need="NO")
        no_policy_signals = project_official_candidate_signals(
            trade_type="EXPORT",
            consultation_categories=[],
            consultation_packet=None,
            confirmed_transaction=self.confirmed_transaction,
            official_candidate_input_profile=no_policy,
        )
        self.assertNotIn("POLICY_FINANCE", no_policy_signals)
        self.assertNotIn(
            "EXPLICIT_POLICY_FINANCE_REVIEW",
            no_policy_signals,
        )

    def test_hard_exclusion_precedes_missing_information_deferral(self):
        completed = self._profile(shipment_status="COMPLETED")
        shortlist = self._shortlist(
            "ksure_export_credit_guarantee_pre_shipment",
            completed,
        )
        self.assertNotIn(
            "ksure_export_credit_guarantee_pre_shipment",
            shortlist.deferred_catalogue_ids,
        )
        evaluation = next(
            item
            for item in shortlist.candidate_evaluations
            if item.catalogue_id
            == "ksure_export_credit_guarantee_pre_shipment"
        )
        self.assertEqual(evaluation.status, "EXCLUDED_CONFLICT")
        self.assertIn("SHIPMENT_COMPLETED", evaluation.reasons)

    def test_explicit_profiles_reach_and_lead_integrated_top_three(self):
        pre_and_policy = self._profile(
            shipment_status="PRE_SHIPMENT",
            receivable_status="NOT_YET",
            trade_form="PROCESSING_TRADE",
            customs_clearance="YES",
            relationship_scope="RECURRING_SINGLE_BUYER",
            credit_information_status="INSUFFICIENT",
            credit_investigation_intent="NO",
            funding_purposes=["MANUFACTURING"],
            receivable_financing_intent="NONE",
            early_cash_conversion_intent="NOT_APPLICABLE",
            bank_financing_intent="YES",
            short_term_export_insurance_linkage_review="NOT_APPLICABLE",
            sme_status="CONFIRMED",
            annual_export_band="AT_LEAST_USD_100K",
            market_entry_purpose="YES",
            policy_finance_need="YES",
            production_or_working_capital_need="YES",
        )
        shortlist = self._full_shortlist(pre_and_policy)
        self.assertEqual(
            [item.product_id for item in shortlist.candidates],
            [
                "ksure_export_credit_guarantee_pre_shipment",
                "kosmes_export_funding",
                "kb_star_fx_forward",
            ],
        )
        self.assertTrue(shortlist.candidates[0].explicit_profile_match)
        self.assertTrue(shortlist.candidates[1].explicit_profile_match)
        self.assertNotIn(
            "ksure_short_term_export_insurance",
            {item.product_id for item in shortlist.candidates},
        )
        self.assertTrue(shortlist.eligible_overflow_candidates)
        self.assertTrue(
            all(
                item.status == "ELIGIBLE_OVERFLOW"
                for item in shortlist.candidate_evaluations
                if item.catalogue_id
                in {
                    candidate.product_id
                    for candidate in shortlist.eligible_overflow_candidates
                }
            )
        )

        signals = project_official_candidate_signals(
            trade_type="EXPORT",
            consultation_categories=[
                item.category for item in self.demo["consultation_topics"]
            ],
            consultation_packet=self.packet,
            confirmed_transaction=self.confirmed_transaction,
            trade_risk_confirmation=self.trade_risk,
            official_candidate_input_profile=pre_and_policy,
        )
        auxiliary = project_auxiliary_service_candidates(
            trade_type="EXPORT",
            signals=signals,
            official_candidate_input_profile=pre_and_policy,
            confirmed_transaction=self.confirmed_transaction,
        )
        self.assertEqual(auxiliary.candidates, [])
        self.assertEqual(
            auxiliary.suppressed_catalogue_ids,
            ["ksure_foreign_company_credit_investigation"],
        )

    def test_post_shipment_kb_and_comprehensive_profiles_reach_default_pool(self):
        purchase = self._profile(
            shipment_status="COMPLETED",
            receivable_status="EXISTS",
            trade_form="GENERAL_EXPORT",
            receivable_financing_intent="NEGO_OR_PURCHASE",
            early_cash_conversion_intent="YES",
            repayment_responsibility_acknowledgement="ACKNOWLEDGED",
        )
        self.assertEqual(
            self._full_shortlist(purchase).candidates[0].product_id,
            "ksure_export_credit_guarantee_purchase",
        )

        comprehensive = self._profile(
            shipment_status="COMPLETED",
            receivable_status="EXISTS",
            relationship_scope="RECURRING_MULTIPLE_BUYERS",
            receivable_financing_intent="NEGO_OR_PURCHASE",
            early_cash_conversion_intent="YES",
            repayment_responsibility_acknowledgement="ACKNOWLEDGED",
        )
        self.assertEqual(
            self._full_shortlist(comprehensive).candidates[0].product_id,
            "ksure_export_credit_guarantee_comprehensive_purchase",
        )

        kb_purchase = self._profile(
            shipment_status="COMPLETED",
            receivable_status="EXISTS",
            receivable_financing_intent="KB_RECEIVABLE_PURCHASE",
            early_cash_conversion_intent="YES",
            bank_financing_intent="YES",
            repayment_responsibility_acknowledgement="ACKNOWLEDGED",
        )
        self.assertNotIn(
            "kb_non_lc_export_bill_purchase",
            {
                item.product_id for item in self.demo["stage4"].candidates
            },
        )
        self.assertEqual(
            self._full_shortlist(kb_purchase).candidates[0].product_id,
            "kb_non_lc_export_bill_purchase",
        )

    def test_hard_blocked_profile_is_not_saved_or_ranked(self):
        profile = self._profile(
            shipment_status="PRE_SHIPMENT",
            receivable_status="NOT_YET",
            receivable_financing_intent="NEGO_OR_PURCHASE",
        )
        state = {"workflow_state": self.demo["workflow_state"]}
        with self.assertRaisesRegex(ValueError, "충돌"):
            update_official_candidate_input_profile(state, profile)
        with self.assertRaisesRegex(ValueError, "충돌"):
            self._full_shortlist(profile)
        self.assertIsNone(
            WorkflowState.model_validate(
                state["workflow_state"]
            ).official_candidate_input_profile
        )

    def test_kb_receivable_purchase_needs_explicit_intent(self):
        profile = self._profile(
            shipment_status="COMPLETED",
            receivable_status="EXISTS",
            receivable_financing_intent="KB_RECEIVABLE_PURCHASE",
            early_cash_conversion_intent="YES",
        )
        self.assert_selected(
            "kb_non_lc_export_bill_purchase",
            profile,
            self.trade_risk,
        )
        buffer_only = OfficialCandidateInputProfile(
            bound_transaction_fingerprint=(
                self.confirmed_transaction.input_fingerprint
            )
        )
        self.assertEqual(
            self._shortlist(
                "kb_non_lc_export_bill_purchase",
                buffer_only,
                self.trade_risk,
            ).candidates,
            [],
        )

    def test_auxiliary_service_is_separate_and_optional(self):
        profile = self._profile(credit_investigation_intent="YES")
        signals = project_official_candidate_signals(
            trade_type="EXPORT",
            consultation_categories=[],
            consultation_packet=None,
            confirmed_transaction=self.confirmed_transaction,
            official_candidate_input_profile=profile,
        )
        auxiliary = project_auxiliary_service_candidates(
            trade_type="EXPORT",
            signals=signals,
            official_candidate_input_profile=profile,
            confirmed_transaction=self.confirmed_transaction,
        )
        self.assertEqual(
            [item.product_id for item in auxiliary.candidates],
            ["ksure_foreign_company_credit_investigation"],
        )
        self.assertFalse(auxiliary.candidates[0].financial_shortlist_eligible)
        financial = self._shortlist(
            "ksure_foreign_company_credit_investigation",
            profile,
        )
        self.assertEqual(financial.candidates, [])
        without_profile = project_auxiliary_service_candidates(
            trade_type="EXPORT",
            signals=frozenset({"IS_EXPORT", "COUNTERPARTY_NEW"}),
        )
        self.assertEqual(without_profile.candidates, [])

    def test_policy_funding_positive_and_unknown_boundaries(self):
        policy = self._profile(
            sme_status="CONFIRMED",
            annual_export_band="BELOW_USD_100K",
            funding_purposes=["GENERAL_WORKING_CAPITAL"],
            market_entry_purpose="YES",
            policy_finance_need="YES",
            production_or_working_capital_need="YES",
        )
        self.assert_selected("kosmes_export_funding", policy)
        missing_sme = self._profile(
            annual_export_band="BELOW_USD_100K",
            funding_purposes=["GENERAL_WORKING_CAPITAL"],
            market_entry_purpose="YES",
            policy_finance_need="YES",
            production_or_working_capital_need="YES",
        )
        self.assertEqual(
            self._shortlist("kosmes_export_funding", missing_sme).candidates,
            [],
        )

    def test_legacy_packet_and_golden_shortlist_are_unchanged(self):
        legacy = self.packet.model_dump(mode="json")
        legacy.pop("confirmed_transaction_fingerprint", None)
        legacy.pop("official_candidate_input_profile", None)
        legacy.pop("auxiliary_service_candidates", None)
        restored = ConsultationPacket.model_validate(legacy)
        self.assertIsNone(restored.official_candidate_input_profile)
        self.assertIsNone(restored.auxiliary_service_candidates)
        self.assertEqual(
            [
                item.product_id
                for item in self.demo[
                    "official_candidate_shortlist"
                ].candidates
            ],
            [
                "ksure_short_term_export_insurance",
                "kb_star_fx_forward",
                "ksure_fx_insurance_general",
            ],
        )
        self.assertIsNone(
            self.demo[
                "official_candidate_shortlist"
            ].source_profile_fingerprint
        )
        self.assertEqual(
            self.demo[
                "official_candidate_shortlist"
            ].eligible_overflow_candidates,
            [],
        )
        self.assertTrue(
            all(
                not item.explicit_profile_match
                for item in self.demo[
                    "official_candidate_shortlist"
                ].candidates
            )
        )
        self.assertEqual(len(load_official_kb()), 16)

    def test_workflow_and_packet_reject_transaction_profile_mismatch(self):
        profile = self._profile(policy_finance_need="NO")
        transaction_b = self.confirmed_transaction.model_copy(
            update={"input_fingerprint": "b" * 64}
        )
        workflow_payload = self.demo["workflow_state"].model_dump(
            mode="json"
        )
        workflow_payload["confirmed_transaction"] = transaction_b.model_dump(
            mode="json"
        )
        workflow_payload["official_candidate_input_profile"] = (
            profile.model_dump(mode="json")
        )
        with self.assertRaisesRegex(ValueError, "confirmed transaction"):
            WorkflowState.model_validate(workflow_payload)

        shortlist = shortlist_official_candidates(
            stage4_result=self.demo["stage4"],
            trade_type="EXPORT",
            consultation_topics=self.demo["consultation_topics"],
            consultation_packet=self.packet,
            confirmed_transaction=self.confirmed_transaction,
            trade_risk_confirmation=self.trade_risk,
            official_candidate_input_profile=profile,
        )
        decision = self._build_decision(profile, shortlist)
        packet_payload = decision.consultation_packet.packet.model_dump(
            mode="json"
        )
        packet_payload["confirmed_transaction_fingerprint"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "confirmed transaction"):
            ConsultationPacket.model_validate(packet_payload)

    def test_packet_and_stage5_share_optional_auxiliary_projection(self):
        profile = self._profile(credit_investigation_intent="YES")
        signals = project_official_candidate_signals(
            trade_type="EXPORT",
            consultation_categories=[
                item.category for item in self.demo["consultation_topics"]
            ],
            consultation_packet=self.packet,
            confirmed_transaction=self.confirmed_transaction,
            trade_risk_confirmation=self.trade_risk,
            official_candidate_input_profile=profile,
        )
        auxiliary = project_auxiliary_service_candidates(
            trade_type="EXPORT",
            signals=signals,
            official_candidate_input_profile=profile,
            confirmed_transaction=self.confirmed_transaction,
        )
        shortlist = shortlist_official_candidates(
            stage4_result=self.demo["stage4"],
            trade_type="EXPORT",
            consultation_topics=self.demo["consultation_topics"],
            consultation_packet=self.packet,
            confirmed_transaction=self.confirmed_transaction,
            trade_risk_confirmation=self.trade_risk,
            official_candidate_input_profile=profile,
        )
        decision = build_decision_support(
            case_id=self.demo["workflow_state"].case_id,
            extraction=self.demo["extraction"],
            confirmation=self.demo["confirmation"],
            stage1=self.demo["stage1"],
            stage2_input=self.demo["stage2_input"],
            stage2_result=self.demo["stage2"],
            trade_settlement_risk=self.demo["trade_risk_assessment"],
            country_environment=self.demo["country_environment_assessment"],
            trade_statistics=self.demo["trade_statistics_result"],
            official_candidate_shortlist=shortlist,
            official_candidate_input_profile=profile,
            auxiliary_service_candidates=auxiliary,
            generated_at="2026-08-02T09:00:00+09:00",
            confirmed_transaction=self.confirmed_transaction,
        )
        packet = decision.consultation_packet.packet
        self.assertEqual(packet.official_candidate_input_profile, profile)
        self.assertEqual(packet.auxiliary_service_candidates, auxiliary)
        self.assertEqual(
            packet.confirmed_transaction_fingerprint,
            self.confirmed_transaction.input_fingerprint,
        )
        self.assertEqual(
            packet.official_candidate_shortlist.source_profile_fingerprint,
            profile.input_fingerprint,
        )
        self.assertEqual(
            packet.official_candidate_shortlist
            .source_transaction_fingerprint,
            self.confirmed_transaction.input_fingerprint,
        )
        self.assertEqual(
            auxiliary.source_transaction_fingerprint,
            self.confirmed_transaction.input_fingerprint,
        )
        self.assertIn("## 6A. 추가 확인 서비스", decision.consultation_packet.markdown)
        self.assertNotEqual(packet.input_hash, self.packet.input_hash)

        report = generate_deterministic_report(
            extraction=self.demo["extraction"],
            confirmation=self.demo["confirmation"],
            stage1=self.demo["stage1"],
            stage2=self.demo["stage2"],
            stage3=self.demo["stage3"],
            stage4=self.demo["stage4"],
            market_integration=self.demo["market_integration"],
            consultation_packet=packet,
            confirmed_transaction=self.confirmed_transaction,
        )
        self.assertIn("## 11A. 추가 확인 서비스", report.markdown)
        self.assertIn(
            "ksure_foreign_company_credit_investigation",
            packet.model_dump_json(),
        )

    def test_profile_update_preserves_stages_and_invalidates_report_outputs(self):
        profile = self._profile(policy_finance_need="NO")
        original_workflow = self.demo["workflow_state"]
        state = {
            "workflow_state": original_workflow,
            "official_candidate_shortlist": {"stale": True},
            "auxiliary_service_candidates": {"stale": True},
            "consultation_packet": {"stale": True},
            "report_result": {"stale": True},
        }

        changed = update_official_candidate_input_profile(state, profile)

        self.assertTrue(changed)
        updated = state["workflow_state"]
        self.assertEqual(updated.market_risk, original_workflow.market_risk)
        self.assertEqual(updated.cashflow, original_workflow.cashflow)
        self.assertEqual(updated.hedge, original_workflow.hedge)
        self.assertEqual(
            updated.official_candidate_input_profile,
            profile,
        )
        self.assertIsNone(updated.final_report)
        for key in (
            "official_candidate_shortlist",
            "auxiliary_service_candidates",
            "consultation_packet",
            "report_result",
        ):
            self.assertNotIn(key, state)
        self.assertFalse(
            update_official_candidate_input_profile(state, profile)
        )

    def test_profile_a_to_b_clears_stale_artifacts_and_rebuilds_cleanly(self):
        profile_a = self._profile(
            shipment_status="COMPLETED",
            receivable_status="EXISTS",
            relationship_scope="RECURRING_MULTIPLE_BUYERS",
            receivable_financing_intent="KB_RECEIVABLE_PURCHASE",
            early_cash_conversion_intent="YES",
            repayment_responsibility_acknowledgement="ACKNOWLEDGED",
            credit_investigation_intent="YES",
        )
        shortlist_a = self._shortlist(
            "kb_non_lc_export_bill_purchase",
            profile_a,
            self.trade_risk,
        )
        signals_a = project_official_candidate_signals(
            trade_type="EXPORT",
            consultation_categories=[self.liquidity_topic.category],
            consultation_packet=self.packet,
            confirmed_transaction=self.confirmed_transaction,
            trade_risk_confirmation=self.trade_risk,
            official_candidate_input_profile=profile_a,
        )
        auxiliary_a = project_auxiliary_service_candidates(
            trade_type="EXPORT",
            signals=signals_a,
            official_candidate_input_profile=profile_a,
            confirmed_transaction=self.confirmed_transaction,
        )
        decision_a = self._build_decision(
            profile_a,
            shortlist_a,
            auxiliary_a,
        )
        report_a = generate_deterministic_report(
            extraction=self.demo["extraction"],
            confirmation=self.demo["confirmation"],
            stage1=self.demo["stage1"],
            stage2=self.demo["stage2"],
            stage3=self.demo["stage3"],
            stage4=self.demo["stage4"],
            market_integration=self.demo["market_integration"],
            consultation_packet=decision_a.consultation_packet.packet,
            confirmed_transaction=self.confirmed_transaction,
        )
        workflow_a = self.demo["workflow_state"].model_copy(
            update={
                "official_candidate_input_profile": profile_a,
                "final_report": report_a,
            }
        )
        state = {
            "workflow_state": workflow_a,
            "official_candidate_shortlist": shortlist_a,
            "auxiliary_service_candidates": auxiliary_a,
            "consultation_packet": decision_a.consultation_packet,
            "report_result": report_a,
            "report_download_payload": report_a.markdown,
        }
        validate_official_candidate_artifact_state(state)

        profile_b = self._profile(
            shipment_status="PRE_SHIPMENT",
            receivable_status="NOT_YET",
            relationship_scope="SINGLE_ONE_OFF",
            funding_purposes=["RAW_MATERIAL_PROCUREMENT"],
            receivable_financing_intent="NONE",
            early_cash_conversion_intent="NOT_APPLICABLE",
            bank_financing_intent="YES",
        )
        self.assertTrue(
            update_official_candidate_input_profile(state, profile_b)
        )
        for key in (
            "official_candidate_shortlist",
            "auxiliary_service_candidates",
            "consultation_packet",
            "report_result",
            "report_download_payload",
        ):
            self.assertNotIn(key, state)
        updated = state["workflow_state"]
        self.assertEqual(updated.market_risk, workflow_a.market_risk)
        self.assertEqual(updated.cashflow, workflow_a.cashflow)
        self.assertEqual(updated.hedge, workflow_a.hedge)
        self.assertIsNone(updated.final_report)
        self.assertEqual(
            updated.official_candidate_input_profile.input_fingerprint,
            profile_b.input_fingerprint,
        )

        shortlist_b = self._shortlist(
            "ksure_export_credit_guarantee_pre_shipment",
            profile_b,
        )
        self.assertEqual(
            [item.product_id for item in shortlist_b.candidates],
            ["ksure_export_credit_guarantee_pre_shipment"],
        )
        self.assertNotIn(
            "kb_non_lc_export_bill_purchase",
            {item.product_id for item in shortlist_b.candidates},
        )
        decision_b = self._build_decision(profile_b, shortlist_b)
        self.assertEqual(
            [
                (item.rank, item.category)
                for item in (
                    decision_a.consultation_packet.packet
                    .consultation_priorities
                )
            ],
            [
                (item.rank, item.category)
                for item in (
                    decision_b.consultation_packet.packet
                    .consultation_priorities
                )
            ],
        )
        self.assertEqual(
            [
                (item.rank, item.review_area_id)
                for item in decision_a.consultation_packet.packet
                .consultation_review_areas
            ],
            [
                (item.rank, item.review_area_id)
                for item in decision_b.consultation_packet.packet
                .consultation_review_areas
            ],
        )

    def test_same_fingerprint_different_audit_metadata_does_not_invalidate(self):
        first = self._profile(policy_finance_need="NO")
        same = self._profile(
            policy_finance_need="NO",
            confirmed_at="2026-08-03T10:00:00+09:00",
            confirmed_by="ANOTHER_REVIEWER",
        )
        self.assertEqual(first.input_fingerprint, same.input_fingerprint)
        workflow = self.demo["workflow_state"].model_copy(
            update={
                "official_candidate_input_profile": first,
                "report": None,
                "final_report": None,
            }
        )
        marker = {"kept": True}
        state = {
            "workflow_state": workflow,
            "official_candidate_shortlist": marker,
        }
        with self.assertRaisesRegex(ValueError, "Packet 없는 금융후보"):
            update_official_candidate_input_profile(state, same)
        state = {"workflow_state": workflow}
        self.assertFalse(
            update_official_candidate_input_profile(state, same)
        )
        self.assertEqual(
            state["workflow_state"].official_candidate_input_profile,
            first,
        )

    def test_transaction_switch_rejects_profile_and_reset_clears_everything(self):
        profile_a = self._profile(policy_finance_need="NO")
        transaction_b = self.confirmed_transaction.model_copy(
            update={
                "input_fingerprint": "b" * 64,
                "amount_due": "99000.00",
            }
        )
        with self.assertRaisesRegex(ValueError, "confirmed transaction"):
            project_official_candidate_signals(
                trade_type="EXPORT",
                consultation_categories=[],
                consultation_packet=None,
                confirmed_transaction=transaction_b,
                official_candidate_input_profile=profile_a,
            )
        state = {
            "workflow_state": self.demo["workflow_state"].model_copy(
                update={"official_candidate_input_profile": profile_a}
            ),
            "official_candidate_shortlist": {"stale": True},
            "auxiliary_service_candidates": {"stale": True},
            "consultation_packet": {"stale": True},
            "report_result": {"stale": True},
            "report_download_payload": "stale",
        }
        state["input_signature"] = input_signature(
            mode="DEMO",
            company_role="SELLER",
            company_country="KR",
            filename="trade-a.pdf",
            file_bytes=b"trade-a",
        )
        new_signature = input_signature(
            mode="LIVE",
            company_role="SELLER",
            company_country="KR",
            filename="trade-b.pdf",
            file_bytes=b"trade-b",
        )
        self.assertTrue(sync_input_signature(state, new_signature))
        for key in PIPELINE_KEYS:
            self.assertNotIn(key, state)
        self.assertNotIn("official_candidate_input_profile", state)

    def test_confirmation_reset_and_session_profile_copy_are_fail_closed(self):
        profile = self._profile(policy_finance_need="NO")
        state = {
            "workflow_state": self.demo["workflow_state"].model_copy(
                update={"official_candidate_input_profile": profile}
            ),
            "official_candidate_input_profile": profile,
        }
        with self.assertRaisesRegex(ValueError, "별도 복제"):
            validate_official_candidate_artifact_state(state)
        clear_confirmation_and_later(state)
        self.assertNotIn("workflow_state", state)
        self.assertNotIn("official_candidate_input_profile", state)

    def test_page_navigation_preserves_profile_and_full_reset_clears_it(self):
        profile = self._profile(policy_finance_need="NO")
        workflow = self.demo["workflow_state"].model_copy(
            update={"official_candidate_input_profile": profile}
        )
        state = {
            "active_page": "analysis",
            "workflow_state": workflow,
            "official_candidate_shortlist": {"stale": True},
            "auxiliary_service_candidates": {"stale": True},
            "consultation_packet": {"stale": True},
            "report_result": {"stale": True},
            "report_download_payload": "stale",
        }

        with patch(
            "src.ui.layout.st",
            SimpleNamespace(session_state=state),
        ):
            set_active_page("consultation")

        self.assertEqual(state["active_page"], "consultation")
        self.assertEqual(
            state["workflow_state"].official_candidate_input_profile,
            profile,
        )
        self.assertIn("official_candidate_shortlist", state)
        self.assertIn("consultation_packet", state)

        clear_downstream(state, 0)
        for key in PIPELINE_KEYS:
            self.assertNotIn(key, state)
        self.assertEqual(state["active_page"], "consultation")

    def test_packet_rejects_stale_shortlist_auxiliary_and_report(self):
        profile_a = self._profile(credit_investigation_intent="YES")
        profile_b = self._profile(
            credit_information_status="SUFFICIENT",
            credit_investigation_intent="NO",
        )
        shortlist_a = self._shortlist(
            "kb_non_lc_export_bill_purchase",
            self._profile(
                shipment_status="COMPLETED",
                receivable_status="EXISTS",
                receivable_financing_intent="KB_RECEIVABLE_PURCHASE",
                early_cash_conversion_intent="YES",
            ),
            self.trade_risk,
        )
        with self.assertRaisesRegex(ValueError, "shortlist"):
            self._build_decision(profile_b, shortlist_a)

        signals_a = project_official_candidate_signals(
            trade_type="EXPORT",
            consultation_categories=[],
            consultation_packet=None,
            confirmed_transaction=self.confirmed_transaction,
            official_candidate_input_profile=profile_a,
        )
        auxiliary_a = project_auxiliary_service_candidates(
            trade_type="EXPORT",
            signals=signals_a,
            official_candidate_input_profile=profile_a,
            confirmed_transaction=self.confirmed_transaction,
        )
        shortlist_b = shortlist_official_candidates(
            stage4_result=self.demo["stage4"],
            trade_type="EXPORT",
            consultation_topics=self.demo["consultation_topics"],
            consultation_packet=self.packet,
            confirmed_transaction=self.confirmed_transaction,
            trade_risk_confirmation=self.trade_risk,
            official_candidate_input_profile=profile_b,
        )
        with self.assertRaisesRegex(ValueError, "보조서비스 projection"):
            self._build_decision(profile_b, shortlist_b, auxiliary_a)

        decision_b = self._build_decision(profile_b, shortlist_b)
        report = generate_deterministic_report(
            extraction=self.demo["extraction"],
            confirmation=self.demo["confirmation"],
            stage1=self.demo["stage1"],
            stage2=self.demo["stage2"],
            stage3=self.demo["stage3"],
            stage4=self.demo["stage4"],
            market_integration=self.demo["market_integration"],
            consultation_packet=decision_b.consultation_packet.packet,
            confirmed_transaction=self.confirmed_transaction,
        )
        stale_bundle = dict(report.report_json)
        stale_consultation = dict(stale_bundle["consultation"])
        stale_consultation["input_hash"] = "a" * 64
        stale_bundle["consultation"] = stale_consultation
        stale_report = report.model_copy(
            update={"report_json": stale_bundle}
        )
        workflow = self.demo["workflow_state"].model_copy(
            update={
                "official_candidate_input_profile": profile_b,
                "report": None,
                "final_report": None,
            }
        )
        state = {
            "workflow_state": workflow,
            "official_candidate_shortlist": shortlist_b,
            "consultation_packet": decision_b.consultation_packet,
            "report_result": stale_report,
        }
        with self.assertRaisesRegex(ValueError, "Stage5 report"):
            validate_official_candidate_artifact_state(state)

    def test_stage5_rejects_packet_bound_to_a_different_profile(self):
        profile_a = self._profile(policy_finance_need="NO")
        profile_b = self._profile(
            shipment_status="PRE_SHIPMENT",
            funding_purposes=["RAW_MATERIAL_PROCUREMENT"],
            bank_financing_intent="YES",
        )
        shortlist_b = self._shortlist(
            "ksure_export_credit_guarantee_pre_shipment",
            profile_b,
        )
        packet_b = self._build_decision(
            profile_b,
            shortlist_b,
        ).consultation_packet.packet
        state = self.demo["workflow_state"].model_copy(
            update={"official_candidate_input_profile": profile_a}
        )
        report_generator = Mock()
        orchestrator = WorkflowOrchestrator(
            settings=Settings(enable_llm_report=False),
            report_generator=report_generator,
        )

        result = orchestrator.run_report(
            state,
            consultation_packet=packet_b,
        )

        self.assertEqual(result.report.status, StageStatus.FAILED)
        self.assertEqual(
            result.report.provider,
            "consultation_packet_binding_gate",
        )
        self.assertIn("profile", result.report.errors[0])
        self.assertIsNone(result.final_report)
        report_generator.assert_not_called()


if __name__ == "__main__":
    unittest.main()
