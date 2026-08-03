import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from schemas import (
    ConfirmationState,
    FieldEvidence,
    NormalizationAuditEntry,
    TradeDocumentExtraction,
)
from src.document_intake.source_evidence import (
    _amount_values,
    _date_values,
    extract_pdf_page_texts,
    recover_source_grounded_evidence,
)
from validators import apply_deterministic_review_state


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_ROOT = ROOT / "dataset" / "golden_demo"


class SourceEvidenceRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.expected = TradeDocumentExtraction.model_validate_json(
            (GOLDEN_ROOT / "expected_extraction.json").read_text(
                encoding="utf-8"
            )
        )
        cls.pages = extract_pdf_page_texts(
            (GOLDEN_ROOT / "golden_export_contract.pdf").read_bytes()
        )

    def without_recoverable_evidence(
        self,
        extraction: Optional[TradeDocumentExtraction] = None,
    ) -> TradeDocumentExtraction:
        source = extraction or self.expected
        return source.model_copy(
            update={
                "evidence": [
                    item
                    for item in source.evidence
                    if item.field
                    not in {"amount_due", "explicit_due_date"}
                ]
            }
        )

    @staticmethod
    def failed_audit(
        field: str,
        status: str,
    ) -> NormalizationAuditEntry:
        return NormalizationAuditEntry(
            field=field,
            raw_value=None,
            normalized_value=None,
            status=status,
            message="model evidence rejected for test",
        )

    @staticmethod
    def confirmed() -> ConfirmationState:
        return ConfirmationState(
            company_role_confirmed=True,
            trade_type_confirmed=True,
            currency_confirmed=True,
            amount_due_confirmed=True,
            due_date_confirmed=True,
            confirmed_due_date="2026-08-20",
            confirmed_by="evidence-recovery-test",
            confirmed_at="2026-07-29T09:00:00+09:00",
        )

    def live_like_extraction(self) -> TradeDocumentExtraction:
        evidence = [
            item
            for item in self.expected.evidence
            if item.field not in {"amount_due", "explicit_due_date"}
        ]
        evidence.extend(
            [
                FieldEvidence(
                    field="amount_due",
                    page=2,
                    source_text=(
                        "The remaining eighty percent (80%), equal to "
                        "USD 80,000, shall be paid by T/T remittance on or "
                        "before 20 August 2026 (Payment Due Date)."
                    ),
                    extraction_type="EXPLICIT",
                    confidence_reason="Model bound the balance clause.",
                ),
                FieldEvidence(
                    field="explicit_due_date",
                    page=2,
                    source_text="Payment Due Date: 2026-08-20",
                    extraction_type="EXPLICIT",
                    confidence_reason="Model normalized the date in its quote.",
                ),
            ]
        )
        return self.expected.model_copy(update={"evidence": evidence})

    def recover(
        self,
        *,
        page_texts: List[str],
        extraction: Optional[TradeDocumentExtraction] = None,
        audit: Optional[List[NormalizationAuditEntry]] = None,
    ):
        return recover_source_grounded_evidence(
            extraction or self.without_recoverable_evidence(),
            source_page_texts=page_texts,
            evidence_audit=audit or [],
        )

    def test_parses_canonical_amount_from_usd_grouped_number(self):
        self.assertEqual(
            _amount_values("Amount Due: USD 100,000"),
            [Decimal("100000")],
        )

    def test_amount_display_variants_recover_same_canonical_value(self):
        variants = (
            "USD 100,000",
            "USD 100,000.00",
            "100,000 United States dollars",
            (
                "one hundred thousand United States dollars "
                "(USD 100,000)"
            ),
        )
        for value in variants:
            with self.subTest(value=value):
                extraction, audit = self.recover(
                    page_texts=[
                        "The total Contract Price is {}.".format(value)
                    ]
                )
                amount_evidence = [
                    item
                    for item in extraction.evidence
                    if item.field == "amount_due"
                ]
                self.assertEqual(len(amount_evidence), 1)
                self.assertIn(value, amount_evidence[0].source_text)
                self.assertTrue(
                    any(
                        item.status == "EVIDENCE_RECOVERED_FROM_TEXT"
                        and item.normalized_value == "100000.00"
                        for item in audit
                    )
                )

    def test_balance_amount_is_not_used_for_contract_aggregate(self):
        extraction, audit = self.recover(
            page_texts=[
                (
                    "The remaining balance, equal to USD 80,000, "
                    "is the Balance Due."
                )
            ]
        )
        self.assertFalse(
            any(item.field == "amount_due" for item in extraction.evidence)
        )
        self.assertTrue(
            any(
                item.status == "EVIDENCE_RECOVERY_AMBIGUOUS"
                and "VALUE_MISMATCH" in item.message
                for item in audit
            )
        )

    def test_installment_sum_matches_contract_amount_due(self):
        total = sum(
            (
                Decimal(item.amount)
                for item in self.expected.installments
                if item.amount is not None
            ),
            Decimal("0"),
        )
        self.assertEqual(total, Decimal(self.expected.amount_due))
        self.assertEqual(total, Decimal("100000.00"))

    def test_amount_due_uses_contract_total_quote_only(self):
        extraction, unused_audit = self.recover(page_texts=self.pages)
        evidence = [
            item
            for item in extraction.evidence
            if item.field == "amount_due"
        ]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].page, 1)
        self.assertEqual(
            evidence[0].source_text,
            (
                "The total Contract Price is one hundred thousand "
                "United States dollars (USD 100,000)."
            ),
        )
        self.assertNotIn("USD 80,000", evidence[0].source_text)

    def test_currency_conflict_blocks_amount_recovery(self):
        extraction, audit = self.recover(
            page_texts=[
                "The total Contract Price is EUR 100,000."
            ]
        )
        self.assertFalse(
            any(item.field == "amount_due" for item in extraction.evidence)
        )
        self.assertTrue(
            any(
                "CURRENCY_CONFLICT" in item.message
                for item in audit
            )
        )

    def test_same_amount_in_multiple_meanings_blocks_recovery(self):
        extraction, audit = self.recover(
            page_texts=[
                "The total Contract Price is USD 100,000.",
                "The Balance Due is USD 100,000.",
            ]
        )
        self.assertFalse(
            any(item.field == "amount_due" for item in extraction.evidence)
        )
        self.assertTrue(
            any(
                "MULTIPLE_SEMANTIC_FIELDS" in item.message
                for item in audit
            )
        )

    def test_unrelated_same_amount_does_not_replace_contract_context(self):
        extraction, unused_audit = self.recover(
            page_texts=[
                "The total Contract Price is USD 100,000.",
                "The insured value is USD 100,000.",
            ]
        )
        evidence = [
            item
            for item in extraction.evidence
            if item.field == "amount_due"
        ]
        self.assertEqual(len(evidence), 1)
        self.assertIn("Contract Price", evidence[0].source_text)

    def test_parses_english_due_date_to_canonical_date(self):
        self.assertEqual(
            _date_values("Payment Due Date: 20 August 2026"),
            [date(2026, 8, 20)],
        )

    def test_due_date_display_variants_recover_same_canonical_date(self):
        variants = (
            "Payment Due Date: 20 August 2026",
            "Due no later than August 20, 2026",
            "Payment shall be made by 20 Aug 2026",
        )
        for line in variants:
            with self.subTest(line=line):
                extraction, unused_audit = self.recover(
                    page_texts=[
                        "The total Contract Price is USD 100,000.",
                        line,
                    ]
                )
                due_evidence = [
                    item
                    for item in extraction.evidence
                    if item.field == "explicit_due_date"
                ]
                self.assertEqual(len(due_evidence), 1)
                self.assertEqual(due_evidence[0].source_text, line)
                self.assertNotIn("2026-08-20", due_evidence[0].source_text)

    def test_contract_date_is_not_used_as_due_date(self):
        extraction, unused_audit = self.recover(
            page_texts=[
                "The total Contract Price is USD 100,000.",
                "Contract Date: 20 August 2026",
                "Shipment on or before 20 August 2026",
            ]
        )
        self.assertFalse(
            any(
                item.field == "explicit_due_date"
                for item in extraction.evidence
            )
        )

    def test_multiple_strong_due_dates_block_recovery(self):
        extraction, audit = self.recover(
            page_texts=[
                "The total Contract Price is USD 100,000.",
                "Payment Due Date: 20 August 2026",
                "Settlement Date: 20 August 2026",
            ]
        )
        self.assertFalse(
            any(
                item.field == "explicit_due_date"
                for item in extraction.evidence
            )
        )
        self.assertTrue(
            any(
                "MULTIPLE_STRONG_DUE_DATE_CANDIDATES" in item.message
                for item in audit
            )
        )

    def test_conflicting_due_date_blocks_instead_of_using_weaker_match(self):
        extraction, audit = self.recover(
            page_texts=[
                "The total Contract Price is USD 100,000.",
                "Payment Due Date: 21 August 2026",
                "Payment Terms: pay on or before 20 August 2026",
            ]
        )
        self.assertFalse(
            any(
                item.field == "explicit_due_date"
                for item in extraction.evidence
            )
        )
        self.assertTrue(
            any(
                "DUE_DATE_CANDIDATE_VALUE_MISMATCH" in item.message
                for item in audit
            )
        )

    def test_recovered_quote_and_discard_reason_are_audited(self):
        extraction, audit = self.recover(
            page_texts=self.pages,
            audit=[
                self.failed_audit(
                    "amount_due",
                    "EVIDENCE_VALUE_MISMATCH",
                ),
                self.failed_audit(
                    "explicit_due_date",
                    "EVIDENCE_NOT_IN_SOURCE",
                ),
            ],
        )
        statuses = {
            (item.field, item.status, item.raw_value)
            for item in audit
        }
        self.assertIn(
            (
                "amount_due",
                "EVIDENCE_RECOVERED_FROM_TEXT",
                "EVIDENCE_VALUE_MISMATCH",
            ),
            statuses,
        )
        self.assertIn(
            (
                "explicit_due_date",
                "EVIDENCE_RECOVERED_FROM_TEXT",
                "EVIDENCE_NOT_IN_SOURCE",
            ),
            statuses,
        )
        for item in extraction.evidence:
            if item.field in {"amount_due", "explicit_due_date"}:
                self.assertIn(
                    "recovery_method=UNIQUE_SEMANTIC_TEXT_LINE",
                    item.confidence_reason,
                )

    def test_textless_scan_does_not_recover_evidence(self):
        extraction, validation = apply_deterministic_review_state(
            self.live_like_extraction(),
            company_role="SELLER",
            company_country="KR",
            confirmations=self.confirmed(),
            source_page_texts=[],
        )
        self.assertFalse(validation.validation_pass)
        self.assertFalse(validation.stage2_allowed)
        self.assertFalse(
            any(
                item.status == "EVIDENCE_RECOVERED_FROM_TEXT"
                for item in validation.normalization_audit
            )
        )
        self.assertTrue(
            any(
                item.code == "EVIDENCE_UNVERIFIABLE"
                and item.field == "amount_due"
                for item in validation.issues
            )
        )
        self.assertFalse(
            any(item.field == "amount_due" for item in extraction.evidence)
        )

    def test_simple_confirmation_does_not_hide_source_mismatch(self):
        bad_pages = [
            page.replace(
                "USD 100,000",
                "USD 99,000",
            )
            for page in self.pages
        ]
        unused_extraction, validation = apply_deterministic_review_state(
            self.live_like_extraction(),
            company_role="SELLER",
            company_country="KR",
            confirmations=self.confirmed(),
            source_page_texts=bad_pages,
        )
        self.assertFalse(validation.validation_pass)
        self.assertFalse(validation.stage2_allowed)
        issue_fields = {
            (item.code, item.field)
            for item in validation.issues
        }
        self.assertIn(
            ("EVIDENCE_VALUE_MISMATCH", "amount_due"),
            issue_fields,
        )

    def test_live_like_failure_recovers_from_golden_text_layer(self):
        extraction, validation = apply_deterministic_review_state(
            self.live_like_extraction(),
            company_role="SELLER",
            company_country="KR",
            confirmations=self.confirmed(),
            source_page_texts=self.pages,
        )
        self.assertTrue(validation.validation_pass)
        self.assertTrue(validation.stage2_allowed)
        evidence = {
            item.field: item
            for item in extraction.evidence
            if item.field in {"amount_due", "explicit_due_date"}
        }
        self.assertEqual(set(evidence), {"amount_due", "explicit_due_date"})
        self.assertEqual(evidence["amount_due"].page, 1)
        self.assertEqual(evidence["explicit_due_date"].page, 2)
        self.assertIn("USD 100,000", evidence["amount_due"].source_text)
        self.assertIn(
            "20 August 2026",
            evidence["explicit_due_date"].source_text,
        )
        self.assertNotIn(
            "2026-08-20",
            evidence["explicit_due_date"].source_text,
        )

    def test_recovered_amount_relinks_currency_from_verified_source(self):
        evidence = [
            item
            for item in self.expected.evidence
            if item.field not in {"amount_due", "currency"}
        ]
        evidence.append(
            FieldEvidence(
                field="amount_due",
                page=1,
                source_text="Invented Invoice Total: USD 100,000",
                extraction_type="EXPLICIT",
                confidence_reason="Model quote is absent from the PDF.",
            )
        )

        extraction, validation = apply_deterministic_review_state(
            self.expected.model_copy(update={"evidence": evidence}),
            company_role="SELLER",
            company_country="KR",
            source_page_texts=self.pages,
        )

        currency_evidence = [
            item
            for item in extraction.evidence
            if item.field == "currency"
        ]
        self.assertEqual(len(currency_evidence), 1)
        self.assertIn("USD 100,000", currency_evidence[0].source_text)
        self.assertNotIn(
            ("MISSING_CORE_EVIDENCE", "currency"),
            {(item.code, item.field) for item in validation.issues},
        )

    def test_recovery_is_deterministic_and_preserves_other_fields(self):
        raw = self.live_like_extraction()
        first, first_validation = apply_deterministic_review_state(
            raw,
            company_role="SELLER",
            company_country="KR",
            source_page_texts=self.pages,
        )
        second, second_validation = apply_deterministic_review_state(
            raw,
            company_role="SELLER",
            company_country="KR",
            source_page_texts=self.pages,
        )
        self.assertEqual(first.model_dump(), second.model_dump())
        self.assertEqual(
            first_validation.model_dump(),
            second_validation.model_dump(),
        )
        for field in (
            "seller_country",
            "buyer_country",
            "trade_type",
            "currency",
            "grand_total",
            "contract_date",
            "installments",
        ):
            with self.subTest(field=field):
                self.assertEqual(
                    getattr(first, field),
                    getattr(self.expected, field),
                )


if __name__ == "__main__":
    unittest.main()
