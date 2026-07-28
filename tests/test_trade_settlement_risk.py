import unittest

from pydantic import ValidationError

from sample_data import sample_extraction
from src.application.trade_risk_service import build_trade_risk_prefill
from src.consultation.trade_settlement_risk import (
    assess_trade_settlement_risk,
    create_trade_risk_confirmation,
    trade_risk_fingerprint,
)
from src.domain.trade_risk_models import (
    ProtectionMechanism,
    TradeSettlementRiskInput,
)


def source_map():
    return {
        "counterparty_relationship": "USER_CONFIRMED",
        "advance_payment_ratio": "USER_CONFIRMED",
        "balance_payment_method": "USER_CONFIRMED",
        "payment_term_days": "USER_CONFIRMED",
        "protection_information_status": "USER_CONFIRMED",
    }


def trade_risk_input(
    *,
    trade_type="IMPORT",
    relationship="NEW",
    ratio="0.3",
    method="DOCUMENTARY_CREDIT",
    term_days=90,
    term_basis="EXPLICIT_NET_TERM",
    protection_status="NONE_CONFIRMED",
    protections=None,
):
    return TradeSettlementRiskInput(
        confirmed_trade_sha256="a" * 64,
        trade_type=trade_type,
        counterparty_relationship=relationship,
        advance_payment_ratio=ratio,
        balance_payment_method=method,
        payment_term_days=term_days,
        payment_term_basis=term_basis,
        protection_information_status=protection_status,
        protection_mechanisms=protections or [],
        field_sources=source_map(),
    )


def assess(value):
    confirmation = create_trade_risk_confirmation(
        confirmed_input=value,
        confirmed_by="test-user",
        confirmed_at="2026-07-29T00:00:00+09:00",
    )
    return assess_trade_settlement_risk(confirmation)


def protection(
    protection_type,
    applicability="CONFIRMED_APPLICABLE",
):
    return ProtectionMechanism(
        protection_type=protection_type,
        applicability_status=applicability,
        source="USER_CONFIRMED",
    )


class TradeRiskContractTests(unittest.TestCase):
    def test_ratio_is_canonical_decimal_string(self):
        value = trade_risk_input(ratio="0.30")
        self.assertEqual(value.advance_payment_ratio, "0.3")

    def test_ratio_distinguishes_unknown_and_confirmed_zero(self):
        unknown = trade_risk_input(
            ratio=None,
            method="UNKNOWN",
            term_days=None,
            term_basis="UNKNOWN",
            protection_status="UNKNOWN",
        )
        zero = trade_risk_input(ratio="0")
        self.assertIsNone(unknown.advance_payment_ratio)
        self.assertEqual(zero.advance_payment_ratio, "0")

    def test_ratio_rejects_percent_unit_float_and_non_finite_values(self):
        for invalid in ("30", "-0.1", "1.01", "1e-1", "NaN", "Infinity", 0.3):
            with self.subTest(invalid=invalid):
                with self.assertRaises((ValidationError, ValueError)):
                    trade_risk_input(ratio=invalid)

    def test_full_advance_requires_no_balance_method(self):
        with self.assertRaises(ValidationError):
            trade_risk_input(ratio="1", method="OPEN_ACCOUNT")
        value = trade_risk_input(
            ratio="1",
            method="NOT_APPLICABLE",
            term_days=None,
            term_basis="NOT_APPLICABLE",
        )
        self.assertEqual(value.balance_payment_method, "NOT_APPLICABLE")

    def test_partial_advance_preserves_balance_method(self):
        value = trade_risk_input(
            ratio="0.3",
            method="DOCUMENTARY_CREDIT",
        )
        self.assertEqual(value.advance_payment_ratio, "0.3")
        self.assertEqual(
            value.balance_payment_method,
            "DOCUMENTARY_CREDIT",
        )

    def test_remaining_balance_rejects_not_applicable_term_basis(self):
        with self.assertRaises(ValidationError):
            trade_risk_input(
                ratio="0.3",
                term_days=None,
                term_basis="NOT_APPLICABLE",
            )

    def test_unknown_and_none_protection_cannot_have_details(self):
        for status in ("UNKNOWN", "NONE_CONFIRMED"):
            with self.subTest(status=status):
                with self.assertRaises(ValidationError):
                    trade_risk_input(
                        protection_status=status,
                        protections=[
                            protection("ADVANCE_PAYMENT_GUARANTEE")
                        ],
                    )

    def test_duplicate_protection_types_are_rejected(self):
        with self.assertRaises(ValidationError):
            trade_risk_input(
                protection_status="DETAILS_PROVIDED",
                protections=[
                    protection("ADVANCE_PAYMENT_GUARANTEE"),
                    protection(
                        "ADVANCE_PAYMENT_GUARANTEE",
                        "PRESENT_SCOPE_UNVERIFIED",
                    ),
                ],
            )

    def test_fingerprint_is_stable_for_canonical_input(self):
        first = trade_risk_input(ratio="0.30")
        second = trade_risk_input(ratio="0.3")
        self.assertEqual(
            trade_risk_fingerprint(first),
            trade_risk_fingerprint(second),
        )

    def test_tampered_confirmation_is_rejected(self):
        value = trade_risk_input()
        confirmation = create_trade_risk_confirmation(
            confirmed_input=value,
            confirmed_at="2026-07-29T00:00:00+09:00",
        ).model_copy(update={"trade_risk_sha256": "b" * 64})
        with self.assertRaises(ValueError):
            assess_trade_settlement_risk(confirmation)


class TradeRiskPrefillTests(unittest.TestCase):
    def test_verified_net_term_is_prefilled_without_llm_inference(self):
        prefill = build_trade_risk_prefill(sample_extraction("SELLER"))
        self.assertEqual(prefill.payment_term_days, 90)
        self.assertEqual(prefill.payment_term_basis, "EXPLICIT_NET_TERM")
        self.assertEqual(
            prefill.field_sources["payment_term_days"],
            "DETERMINISTIC_DERIVED",
        )

    def test_event_based_term_is_not_converted_to_days(self):
        original = sample_extraction("SELLER")
        extraction = original.model_copy(
            update={
                "payment_terms": "Net 30 days after shipment",
                "evidence": [
                    item.model_copy(
                        update={
                            "source_text": (
                                "Payment Terms: Net 30 days after shipment"
                            )
                        }
                    )
                    if item.field == "payment_terms"
                    else item
                    for item in original.evidence
                ],
            }
        )
        prefill = build_trade_risk_prefill(extraction)
        self.assertIsNone(prefill.payment_term_days)
        self.assertEqual(
            prefill.payment_term_basis,
            "EVENT_BASED_UNRESOLVED",
        )

    def test_stale_payment_term_evidence_is_not_used_for_prefill(self):
        extraction = sample_extraction("SELLER").model_copy(
            update={"payment_terms": "Net 30 days after shipment"}
        )

        prefill = build_trade_risk_prefill(extraction)

        self.assertIsNone(prefill.payment_term_days)
        self.assertEqual(prefill.payment_term_basis, "UNKNOWN")

    def test_term_without_verified_evidence_stays_unknown(self):
        extraction = sample_extraction("SELLER").model_copy(
            update={
                "evidence": [
                    item
                    for item in sample_extraction("SELLER").evidence
                    if item.field != "payment_terms"
                ]
            }
        )
        prefill = build_trade_risk_prefill(extraction)
        self.assertIsNone(prefill.payment_term_days)
        self.assertEqual(prefill.payment_term_basis, "UNKNOWN")


class ImportTradeRiskTests(unittest.TestCase):
    def test_new_counterparty_advance_and_no_protection_is_high(self):
        result = assess(trade_risk_input())
        self.assertEqual(
            result.risk_type,
            "IMPORT_PREPAYMENT_PERFORMANCE_RISK",
        )
        self.assertEqual(result.review_priority, "HIGH_REVIEW")
        self.assertIn(
            "IMPORT_ADVANCE_PAYMENT",
            [item.code for item in result.factors],
        )
        self.assertIn(
            "ADVANCE_PAYMENT_PROTECTION_REVIEW",
            result.review_needs,
        )

    def test_applicable_advance_guarantee_only_lowers_one_level(self):
        result = assess(
            trade_risk_input(
                protection_status="DETAILS_PROVIDED",
                protections=[
                    protection("ADVANCE_PAYMENT_GUARANTEE")
                ],
            )
        )
        self.assertEqual(result.review_priority, "ELEVATED_REVIEW")
        self.assertIn(
            "NEW_COUNTERPARTY",
            [item.code for item in result.factors],
        )
        self.assertIn(
            "APPLICABLE_IMPORT_PROTECTION",
            [item.code for item in result.factors],
        )

    def test_unverified_guarantee_does_not_reduce_priority(self):
        result = assess(
            trade_risk_input(
                protection_status="DETAILS_PROVIDED",
                protections=[
                    protection(
                        "ADVANCE_PAYMENT_GUARANTEE",
                        "PRESENT_SCOPE_UNVERIFIED",
                    )
                ],
            )
        )
        self.assertEqual(result.review_priority, "HIGH_REVIEW")
        self.assertTrue(
            any("존재만 확인" in warning for warning in result.warnings)
        )

    def test_export_insurance_does_not_mitigate_import_risk(self):
        result = assess(
            trade_risk_input(
                protection_status="DETAILS_PROVIDED",
                protections=[
                    protection("EXPORT_CREDIT_INSURANCE")
                ],
            )
        )
        self.assertEqual(result.review_priority, "HIGH_REVIEW")
        self.assertNotIn(
            "APPLICABLE_IMPORT_PROTECTION",
            [item.code for item in result.factors],
        )

    def test_unknown_protection_is_not_treated_as_absent(self):
        result = assess(
            trade_risk_input(protection_status="UNKNOWN")
        )
        self.assertEqual(result.review_priority, "UNKNOWN")
        self.assertIn(
            "IMPORT_PROTECTION_UNKNOWN",
            [item.code for item in result.factors],
        )


class ExportTradeRiskTests(unittest.TestCase):
    def test_new_open_account_ninety_days_is_high(self):
        result = assess(
            trade_risk_input(
                trade_type="EXPORT",
                ratio="0",
                method="OPEN_ACCOUNT",
            )
        )
        self.assertEqual(
            result.risk_type,
            "EXPORT_RECEIVABLE_COLLECTION_RISK",
        )
        self.assertEqual(result.review_priority, "HIGH_REVIEW")

    def test_applicable_export_insurance_only_lowers_one_level(self):
        result = assess(
            trade_risk_input(
                trade_type="EXPORT",
                ratio="0",
                method="OPEN_ACCOUNT",
                protection_status="DETAILS_PROVIDED",
                protections=[
                    protection("EXPORT_CREDIT_INSURANCE")
                ],
            )
        )
        self.assertEqual(result.review_priority, "ELEVATED_REVIEW")
        self.assertIn(
            "NEW_COUNTERPARTY",
            [item.code for item in result.factors],
        )

    def test_dp_and_da_have_different_priority(self):
        common = {
            "trade_type": "EXPORT",
            "relationship": "EXISTING",
            "ratio": "0",
            "term_days": 30,
        }
        dp = assess(
            trade_risk_input(
                **common,
                method="DOCUMENTARY_COLLECTION_DP",
            )
        )
        da = assess(
            trade_risk_input(
                **common,
                method="DOCUMENTARY_COLLECTION_DA",
            )
        )
        self.assertEqual(dp.review_priority, "STANDARD_REVIEW")
        self.assertEqual(da.review_priority, "ELEVATED_REVIEW")

    def test_unspecified_collection_blocks_priority(self):
        result = assess(
            trade_risk_input(
                trade_type="EXPORT",
                relationship="EXISTING",
                ratio="0",
                method="DOCUMENTARY_COLLECTION_UNSPECIFIED",
                term_days=30,
            )
        )

        self.assertEqual(result.review_priority, "UNKNOWN")
        self.assertTrue(result.information_gaps)

    def test_import_guarantee_does_not_mitigate_export_risk(self):
        result = assess(
            trade_risk_input(
                trade_type="EXPORT",
                ratio="0",
                method="OPEN_ACCOUNT",
                protection_status="DETAILS_PROVIDED",
                protections=[
                    protection("ADVANCE_PAYMENT_GUARANTEE")
                ],
            )
        )
        self.assertEqual(result.review_priority, "HIGH_REVIEW")

    def test_documentary_credit_keeps_terms_review_factor(self):
        result = assess(
            trade_risk_input(
                trade_type="EXPORT",
                relationship="EXISTING",
                ratio="0",
                method="DOCUMENTARY_CREDIT",
                term_days=30,
            )
        )
        self.assertIn(
            "DOCUMENTARY_CREDIT_DETAILS_NOT_ASSESSED",
            [item.code for item in result.factors],
        )
        self.assertIn(
            "DOCUMENTARY_CREDIT_TERMS_REVIEW",
            result.review_needs,
        )

    def test_event_based_term_is_unknown_not_invented(self):
        result = assess(
            trade_risk_input(
                trade_type="EXPORT",
                ratio="0",
                method="OPEN_ACCOUNT",
                term_days=None,
                term_basis="EVENT_BASED_UNRESOLVED",
            )
        )
        self.assertEqual(result.review_priority, "UNKNOWN")
        self.assertIn(
            "PAYMENT_TERM_UNRESOLVED",
            [item.code for item in result.factors],
        )

    def test_long_term_review_boundary_is_transparent(self):
        day_89 = assess(
            trade_risk_input(
                trade_type="EXPORT",
                relationship="EXISTING",
                ratio="0",
                method="OTHER",
                term_days=89,
            )
        )
        day_90 = assess(
            trade_risk_input(
                trade_type="EXPORT",
                relationship="EXISTING",
                ratio="0",
                method="OTHER",
                term_days=90,
            )
        )
        self.assertEqual(day_89.review_priority, "STANDARD_REVIEW")
        self.assertEqual(day_90.review_priority, "ELEVATED_REVIEW")
        self.assertTrue(day_90.assumptions)


if __name__ == "__main__":
    unittest.main()
