import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from schemas import ConfirmationState, FieldEvidence, TradeDocumentExtraction
from src.document_intake.confirmation import (
    create_confirmation_record,
    validate_confirmation,
)
from src.document_intake.normalization import (
    augment_currency_evidence,
    country_alias_matches_text,
    normalize_country_name,
    normalize_date_text,
)
from src.document_intake.party_matching import (
    match_company_role_from_verified_parties,
)
from src.document_intake.source_evidence import (
    augment_party_evidence,
    extract_pdf_page_texts,
)
from validators import (
    ISO_4217_CODES,
    apply_deterministic_review_state,
    build_stage2_input,
    calculate_net_due_date,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    ROOT / "tests" / "fixtures" / "kbfx_sales_contract_extraction.json"
)


def raw_contract() -> TradeDocumentExtraction:
    return TradeDocumentExtraction.model_validate(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    )


def issue_codes(validation):
    return {item.code for item in validation.issues}


class CountryNormalizationTests(unittest.TestCase):
    def test_required_aliases_normalize_to_iso_alpha_2(self):
        aliases = {
            "United States": "US",
            "United States of America": "US",
            "USA": "US",
            "U.S.A.": "US",
            "US": "US",
            "Republic of Korea": "KR",
            "South Korea": "KR",
            "Korea, Republic of": "KR",
            "Republic of Korea (South Korea)": "KR",
            "대한민국": "KR",
            "한국": "KR",
            "KR": "KR",
        }
        for source, expected in aliases.items():
            with self.subTest(source=source):
                normalized, audit = normalize_country_name(
                    source,
                    "country",
                )
                self.assertEqual(normalized, expected)
                self.assertEqual(audit.raw_value, source)

    def test_alias_matching_ignores_case_spaces_and_punctuation(self):
        normalized, audit = normalize_country_name(
            "  u.s.a.  ",
            "seller_country",
        )
        self.assertEqual(normalized, "US")
        self.assertEqual(audit.raw_value, "  u.s.a.  ")

    def test_unknown_country_is_preserved_and_warned(self):
        normalized, audit = normalize_country_name(
            "Atlantis",
            "seller_country",
        )
        self.assertEqual(normalized, "Atlantis")
        self.assertEqual(audit.status, "UNKNOWN_ALIAS")

    def test_dataset_country_aliases_normalize_to_iso_alpha_2(self):
        aliases = {
            "Australia": "AU",
            "Canada": "CA",
            "France": "FR",
            "The Netherlands": "NL",
            "Norway": "NO",
            "Taiwan": "TW",
        }
        for source, expected in aliases.items():
            with self.subTest(source=source):
                normalized, unused_audit = normalize_country_name(
                    source,
                    "country",
                )
                self.assertEqual(normalized, expected)

    def test_country_evidence_matches_uppercase_code_without_common_word_false_positive(
        self,
    ):
        self.assertTrue(
            country_alias_matches_text(
                "Buyer: Evergreen Mock Distribution Inc. (CA)",
                "CA",
            )
        )
        self.assertFalse(
            country_alias_matches_text(
                "Contract No: SC-SYN-005",
                "NO",
            )
        )


class TradeTypeDerivationTests(unittest.TestCase):
    def test_buyer_korea_and_seller_us_is_import(self):
        extraction, validation = apply_deterministic_review_state(
            raw_contract(),
            company_role="BUYER",
            company_country="KR",
        )
        self.assertEqual(extraction.seller_country, "US")
        self.assertEqual(extraction.buyer_country, "KR")
        self.assertEqual(extraction.trade_type, "IMPORT")
        self.assertEqual(validation.auto_trade_type, "IMPORT")
        self.assertEqual(validation.trade_type_source, "AUTO")

    def test_seller_korea_and_buyer_us_is_export(self):
        raw = raw_contract().model_copy(
            update={
                "company_role": "SELLER",
                "seller_country": "Republic of Korea",
                "buyer_country": "United States",
            }
        )
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="SELLER",
            company_country="대한민국",
        )
        self.assertEqual(extraction.trade_type, "EXPORT")
        self.assertEqual(validation.auto_trade_type, "EXPORT")

    def test_domestic_trade_remains_unknown(self):
        raw = raw_contract().model_copy(
            update={"seller_country": "Republic of Korea"}
        )
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertEqual(extraction.trade_type, "UNKNOWN")
        self.assertIn("MISSING_REQUIRED_FIELD", issue_codes(validation))

    def test_role_country_conflict_remains_unknown_with_warning(self):
        raw = raw_contract().model_copy(
            update={
                "seller_country": "Republic of Korea",
                "buyer_country": "United States",
            }
        )
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertEqual(extraction.trade_type, "UNKNOWN")
        self.assertIn(
            "COMPANY_COUNTRY_ROLE_MISMATCH",
            issue_codes(validation),
        )

    def test_explicit_user_trade_type_wins_and_conflict_is_recorded(self):
        extraction, validation = apply_deterministic_review_state(
            raw_contract(),
            company_role="BUYER",
            company_country="KR",
            user_trade_type="EXPORT",
        )
        self.assertEqual(extraction.trade_type, "EXPORT")
        self.assertEqual(validation.auto_trade_type, "IMPORT")
        self.assertEqual(validation.trade_type_source, "USER_OVERRIDE")
        self.assertIn(
            "TRADE_TYPE_OVERRIDE_CONFLICT",
            issue_codes(validation),
        )


class CompanyRoleMatchingTests(unittest.TestCase):
    def test_unique_verified_party_country_matches_buyer(self):
        extraction, unused_validation = apply_deterministic_review_state(
            raw_contract(),
            company_role="BUYER",
            company_country="KR",
        )

        match = match_company_role_from_verified_parties(
            extraction,
            "KR",
        )

        self.assertIsNotNone(match)
        self.assertEqual(match.role, "BUYER")
        self.assertEqual(match.matched_party, "buyer")

    def test_unique_verified_party_country_matches_seller(self):
        extraction, unused_validation = apply_deterministic_review_state(
            raw_contract(),
            company_role="SELLER",
            company_country="US",
        )

        match = match_company_role_from_verified_parties(
            extraction,
            "US",
        )

        self.assertIsNotNone(match)
        self.assertEqual(match.role, "SELLER")
        self.assertEqual(match.matched_party, "seller")

    def test_missing_verified_party_country_does_not_guess(self):
        raw = raw_contract()
        evidence = [
            item
            for item in raw.evidence
            if item.field != "seller_country"
        ]

        match = match_company_role_from_verified_parties(
            raw.model_copy(update={"evidence": evidence}),
            "KR",
        )

        self.assertIsNone(match)


class EvidenceNormalizationTests(unittest.TestCase):
    def test_currency_evidence_is_linked_from_real_amount_source(self):
        extraction, audit = augment_currency_evidence(
            raw_contract(),
            ISO_4217_CODES,
        )
        evidence = [
            item
            for item in extraction.evidence
            if item.field == "currency"
        ]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(
            evidence[0].source_text,
            "Total Contract Price: USD 100,000.00",
        )
        self.assertEqual(evidence[0].extraction_type, "EXPLICIT")
        self.assertEqual(audit[0].status, "EVIDENCE_LINKED")

    def test_currency_evidence_is_not_invented_without_source_code(self):
        raw = raw_contract()
        evidence = [
            item.model_copy(
                update={"source_text": "Total Contract Price: 100,000.00"}
            )
            if item.field == "amount_due"
            else item
            for item in raw.evidence
        ]
        extraction, audit = augment_currency_evidence(
            raw.model_copy(update={"evidence": evidence}),
            ISO_4217_CODES,
        )
        self.assertFalse(
            any(item.field == "currency" for item in extraction.evidence)
        )
        self.assertEqual(audit, [])
        normalized, validation = apply_deterministic_review_state(
            extraction,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertFalse(
            any(item.field == "currency" for item in normalized.evidence)
        )
        self.assertIn("MISSING_CORE_EVIDENCE", issue_codes(validation))

    def test_existing_currency_evidence_removes_gap(self):
        raw = raw_contract().model_copy(
            update={
                "evidence": list(raw_contract().evidence)
                + [
                    FieldEvidence(
                        field="currency",
                        page=1,
                        source_text="Currency: USD",
                        extraction_type="EXPLICIT",
                        confidence_reason="통화 코드가 직접 표시됨",
                    )
                ]
            }
        )
        unused_extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        del unused_extraction
        currency_gaps = [
            item
            for item in validation.issues
            if (
                item.code == "MISSING_CORE_EVIDENCE"
                and item.field == "currency"
            )
        ]
        self.assertEqual(currency_gaps, [])

    def test_inferred_currency_can_only_pass_with_user_override_record(self):
        raw = raw_contract()
        evidence = [
            item.model_copy(update={"extraction_type": "INFERRED"})
            if item.field == "amount_due"
            else item
            for item in raw.evidence
        ]
        evidence.append(
            FieldEvidence(
                field="currency",
                page=1,
                source_text="Currency appears to be USD",
                extraction_type="INFERRED",
                confidence_reason="문맥 추론",
            )
        )
        raw = raw.model_copy(update={"evidence": evidence})
        extraction, initial = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertTrue(
            any(
                item.code == "INFERRED_CRITICAL_FIELD"
                and item.field == "currency"
                for item in initial.issues
            )
        )
        checks = ConfirmationState(
            company_role_confirmed=True,
            trade_type_confirmed=True,
            currency_confirmed=True,
            amount_due_confirmed=True,
            due_date_confirmed=True,
            confirmed_due_date="2026-10-25",
            user_confirmed_override=True,
            user_confirmed_override_fields=["currency"],
        )
        unused_extraction, confirmed = apply_deterministic_review_state(
            extraction,
            company_role="BUYER",
            company_country="KR",
            confirmations=checks,
        )
        del unused_extraction
        self.assertFalse(
            any(
                item.code == "INFERRED_CRITICAL_FIELD"
                and item.field == "currency"
                for item in confirmed.issues
            )
        )


class SourceGroundedEvidenceTests(unittest.TestCase):
    @staticmethod
    def confirmed_checks(
        overrides=None,
    ):
        override_fields = overrides or []
        return ConfirmationState(
            company_role_confirmed=True,
            trade_type_confirmed=True,
            currency_confirmed=True,
            amount_due_confirmed=True,
            due_date_confirmed=True,
            confirmed_due_date="2026-10-25",
            user_confirmed_override=bool(override_fields),
            user_confirmed_override_fields=override_fields,
        )

    @staticmethod
    def matching_page_text():
        return """Seller: BlueWave Components Inc.
Seller Country: United States
Buyer: Hanseong Precision Co., Ltd.
Buyer Country: Republic of Korea
Total Contract Price: USD 100,000.00
Contract Date: July 27, 2026
Payment Due Date: October 25, 2026
Net 90 calendar days from the Contract Date
"""

    def test_amount_and_due_evidence_must_match_current_values(self):
        raw = raw_contract().model_copy(
            update={
                "evidence": [
                    item.model_copy(
                        update={
                            "source_text": "Total Contract Price: USD 9.00"
                        }
                    )
                    if item.field == "amount_due"
                    else item.model_copy(
                        update={
                            "source_text": (
                                "Payment Due Date: January 1, 2030"
                            )
                        }
                    )
                    if item.field == "explicit_due_date"
                    else item
                    for item in raw_contract().evidence
                ]
            }
        )
        page_text = self.matching_page_text().replace(
            "Total Contract Price: USD 100,000.00",
            "Total Contract Price: USD 9.00",
        ).replace(
            "Payment Due Date: October 25, 2026",
            "Payment Due Date: January 1, 2030",
        )

        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
            confirmations=self.confirmed_checks(),
            source_page_texts=[page_text],
        )

        self.assertFalse(validation.validation_pass)
        self.assertFalse(validation.stage2_allowed)
        self.assertTrue(
            any(
                item.code == "EVIDENCE_VALUE_MISMATCH"
                and item.field == "amount_due"
                for item in validation.issues
            )
        )
        self.assertTrue(
            any(
                item.code == "EVIDENCE_VALUE_MISMATCH"
                and item.field == "explicit_due_date"
                for item in validation.issues
            )
        )
        self.assertFalse(
            any(item.field == "amount_due" for item in extraction.evidence)
        )
        self.assertFalse(
            any(
                item.field == "explicit_due_date"
                for item in extraction.evidence
            )
        )

    def test_party_quote_absent_from_uploaded_text_blocks_stage2(self):
        page_text = self.matching_page_text().replace(
            "Seller: BlueWave Components Inc.",
            "Seller: Different Seller LLC",
        )
        extraction, validation = apply_deterministic_review_state(
            raw_contract(),
            company_role="BUYER",
            company_country="KR",
            confirmations=self.confirmed_checks(),
            source_page_texts=[page_text],
        )

        self.assertFalse(validation.stage2_allowed)
        self.assertTrue(
            any(
                item.code == "EVIDENCE_NOT_IN_SOURCE"
                and item.field == "seller_name"
                for item in validation.issues
            )
        )
        self.assertFalse(
            any(
                item.field == "seller_name"
                for item in extraction.evidence
            )
        )

    def test_opposite_party_label_cannot_support_seller_name(self):
        raw = raw_contract().model_copy(
            update={
                "evidence": [
                    item.model_copy(
                        update={
                            "source_text": "Buyer: BlueWave Components Inc."
                        }
                    )
                    if item.field == "seller_name"
                    else item
                    for item in raw_contract().evidence
                ]
            }
        )
        page_text = self.matching_page_text().replace(
            "Seller: BlueWave Components Inc.",
            "Buyer: BlueWave Components Inc.",
        )
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
            confirmations=self.confirmed_checks(),
            source_page_texts=[page_text],
        )

        self.assertFalse(validation.stage2_allowed)
        self.assertTrue(
            any(
                item.code == "EVIDENCE_VALUE_MISMATCH"
                and item.field == "seller_name"
                for item in validation.issues
            )
        )
        self.assertFalse(
            any(
                item.field == "seller_name"
                for item in extraction.evidence
            )
        )

    def test_unlabeled_quantity_cannot_support_amount_due(self):
        raw = raw_contract().model_copy(
            update={
                "evidence": [
                    item.model_copy(
                        update={
                            "source_text": "Quantity: USD 100,000.00"
                        }
                    )
                    if item.field == "amount_due"
                    else item
                    for item in raw_contract().evidence
                ]
            }
        )
        page_text = self.matching_page_text().replace(
            "Total Contract Price: USD 100,000.00",
            "Quantity: USD 100,000.00",
        )
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
            confirmations=self.confirmed_checks(),
            source_page_texts=[page_text],
        )

        self.assertFalse(validation.stage2_allowed)
        self.assertTrue(
            any(
                item.code == "EVIDENCE_VALUE_MISMATCH"
                and item.field == "amount_due"
                for item in validation.issues
            )
        )
        self.assertFalse(
            any(item.field == "amount_due" for item in extraction.evidence)
        )

    def test_verified_evidence_recovers_actual_page_number(self):
        extraction, validation = apply_deterministic_review_state(
            raw_contract(),
            company_role="BUYER",
            company_country="KR",
            confirmations=self.confirmed_checks(),
            source_page_texts=["Contract No. KBFX-2026-001", self.matching_page_text()],
        )

        self.assertTrue(validation.stage2_allowed)
        self.assertEqual(
            {
                item.page
                for item in extraction.evidence
                if item.field
                in {
                    "seller_name",
                    "seller_country",
                    "buyer_name",
                    "buyer_country",
                    "currency",
                    "amount_due",
                    "contract_date",
                    "explicit_due_date",
                    "payment_terms",
                }
            },
            {2},
        )

    def test_textless_live_document_requires_field_level_override(self):
        extraction, validation = apply_deterministic_review_state(
            raw_contract(),
            company_role="BUYER",
            company_country="KR",
            confirmations=self.confirmed_checks(),
            source_page_texts=[],
        )

        self.assertFalse(validation.stage2_allowed)
        self.assertIn("OCR_REQUIRED", issue_codes(validation))
        self.assertTrue(
            any(
                item.code == "EVIDENCE_UNVERIFIABLE"
                and item.field == "amount_due"
                for item in validation.issues
            )
        )
        self.assertFalse(extraction.evidence)

    def test_explicit_human_override_can_release_value_mismatch(self):
        raw = raw_contract().model_copy(
            update={
                "evidence": [
                    item.model_copy(
                        update={
                            "source_text": "Total Contract Price: USD 9.00"
                        }
                    )
                    if item.field == "amount_due"
                    else item
                    for item in raw_contract().evidence
                ]
            }
        )
        page_text = self.matching_page_text().replace(
            "Total Contract Price: USD 100,000.00",
            "Total Contract Price: USD 9.00",
        )
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
            confirmations=self.confirmed_checks(overrides=["amount_due"]),
            source_page_texts=[page_text],
        )

        self.assertTrue(validation.stage2_allowed)
        self.assertFalse(
            any(item.field == "amount_due" for item in extraction.evidence)
        )
        self.assertTrue(
            any(
                item.status == "USER_CONFIRMED_OVERRIDE"
                and item.field == "amount_due"
                for item in validation.normalization_audit
            )
        )

    def test_confirmation_rechecks_source_text_when_available(self):
        raw = raw_contract().model_copy(
            update={
                "evidence": [
                    item.model_copy(
                        update={
                            "source_text": "Total Contract Price: USD 9.00"
                        }
                    )
                    if item.field == "amount_due"
                    else item
                    for item in raw_contract().evidence
                ]
            }
        )
        page_text = self.matching_page_text().replace(
            "Total Contract Price: USD 100,000.00",
            "Total Contract Price: USD 9.00",
        )
        record = create_confirmation_record(
            original=raw,
            confirmed=raw,
            confirmed_due_date="2026-10-25",
            company_role_confirmed=True,
            trade_type_confirmed=True,
            currency_confirmed=True,
            amount_due_confirmed=True,
            due_date_confirmed=True,
            source_filename="contract.pdf",
            source_sha256="d" * 64,
            company_country="KR",
            confirmed_by="regression-test",
            confirmed_at="2026-07-28T10:00:00+09:00",
        )

        validation = validate_confirmation(
            extraction=raw,
            record=record,
            company_country="KR",
            source_page_texts=[page_text],
        )

        self.assertFalse(validation.stage2_allowed)
        self.assertTrue(
            any(
                item.code == "EVIDENCE_VALUE_MISMATCH"
                and item.field == "amount_due"
                for item in validation.issues
            )
        )


class PartyEvidenceAugmentationTests(unittest.TestCase):
    PARTY_FIELDS = {
        "seller_name",
        "seller_country",
        "buyer_name",
        "buyer_country",
    }

    def without_party_evidence(self) -> TradeDocumentExtraction:
        raw = raw_contract()
        return raw.model_copy(
            update={
                "evidence": [
                    item
                    for item in raw.evidence
                    if item.field not in self.PARTY_FIELDS
                ]
            }
        )

    def test_text_pdf_party_blocks_backfill_exact_evidence(self):
        raw = self.without_party_evidence()
        page_text = """SELLER BUYER
Legal Name: BlueWave Components Inc.
Country: United States
Address: 1200 Harbor Avenue, Seattle, WA 98101, USA
Legal Name: Hanseong Precision Co., Ltd.
Country: Republic of Korea
Address: 77 Techno Valley-ro, Pohang-si
"""
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
            source_page_texts=[page_text],
        )
        party_evidence = {
            item.field: item
            for item in extraction.evidence
            if item.field in self.PARTY_FIELDS
            and item.extraction_type == "EXPLICIT"
        }
        self.assertEqual(set(party_evidence), self.PARTY_FIELDS)
        self.assertEqual(
            party_evidence["seller_name"].source_text,
            "Legal Name: BlueWave Components Inc.",
        )
        self.assertEqual(
            party_evidence["seller_country"].source_text,
            "Country: United States",
        )
        self.assertEqual(
            party_evidence["buyer_name"].source_text,
            "Legal Name: Hanseong Precision Co., Ltd.",
        )
        self.assertEqual(
            party_evidence["buyer_country"].source_text,
            "Country: Republic of Korea",
        )
        self.assertFalse(
            any(
                item.code == "MISSING_CORE_EVIDENCE"
                and item.field in self.PARTY_FIELDS
                for item in validation.issues
            )
        )

    def test_canada_code_in_party_quote_backfills_exact_country_evidence(self):
        raw = self.without_party_evidence().model_copy(
            update={
                "seller_name": "Busan Synthetic Machines Ltd.",
                "seller_country": "KR",
                "buyer_name": "Evergreen Mock Distribution Inc.",
                "buyer_country": "CA",
                "company_role": "SELLER",
                "evidence": [
                    item
                    for item in self.without_party_evidence().evidence
                ]
                + [
                    FieldEvidence(
                        field="seller_name",
                        page=1,
                        source_text=(
                            "Seller: Busan Synthetic Machines Ltd. (KR)"
                        ),
                        extraction_type="EXPLICIT",
                        confidence_reason="판매자와 국가 코드가 명시됨",
                    ),
                    FieldEvidence(
                        field="buyer_name",
                        page=1,
                        source_text=(
                            "Buyer: Evergreen Mock Distribution Inc. (CA)"
                        ),
                        extraction_type="EXPLICIT",
                        confidence_reason="구매자와 국가 코드가 명시됨",
                    ),
                ],
            }
        )
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="SELLER",
            company_country="KR",
        )
        buyer_country_evidence = [
            item
            for item in extraction.evidence
            if item.field == "buyer_country"
        ]
        self.assertEqual(len(buyer_country_evidence), 1)
        self.assertEqual(
            buyer_country_evidence[0].source_text,
            "Buyer: Evergreen Mock Distribution Inc. (CA)",
        )
        self.assertFalse(
            any(
                item.code == "MISSING_CORE_EVIDENCE"
                and item.field == "buyer_country"
                for item in validation.issues
            )
        )

    def test_text_pdf_backfill_rejects_model_quote_not_in_page_text(self):
        raw = self.without_party_evidence()
        page_text = """Legal Name: BlueWave Components Inc.
Country: United States
Legal Name: Hanseong Precision Co., Ltd.
Country: Republic of Korea
"""
        stale_model_quote = FieldEvidence(
            field="seller_name",
            page=1,
            source_text="Seller: BlueWave Components Inc.",
            extraction_type="EXPLICIT",
            confidence_reason="모델 인용문",
        )
        extraction, unused_validation = apply_deterministic_review_state(
            raw.model_copy(
                update={"evidence": list(raw.evidence) + [stale_model_quote]}
            ),
            company_role="BUYER",
            company_country="KR",
            source_page_texts=[page_text],
        )
        seller_evidence = [
            item
            for item in extraction.evidence
            if item.field == "seller_name"
            and item.extraction_type == "EXPLICIT"
        ]
        self.assertIn(
            "Legal Name: BlueWave Components Inc.",
            [item.source_text for item in seller_evidence],
        )

    def test_blank_pdf_text_layer_reports_ocr_required_without_weakening_gaps(self):
        extraction, validation = apply_deterministic_review_state(
            self.without_party_evidence(),
            company_role="BUYER",
            company_country="KR",
            source_page_texts=[""],
        )
        del extraction
        issues = {item.code: item for item in validation.issues}
        self.assertIn("OCR_REQUIRED", issues)
        self.assertEqual(issues["OCR_REQUIRED"].severity, "MEDIUM")
        self.assertTrue(
            any(
                item.code == "MISSING_CORE_EVIDENCE"
                and item.severity == "HIGH"
                for item in validation.issues
            )
        )

    def test_missing_image_text_context_does_not_report_pdf_ocr_required(self):
        extraction, validation = apply_deterministic_review_state(
            self.without_party_evidence(),
            company_role="BUYER",
            company_country="KR",
            source_page_texts=None,
        )
        del extraction
        self.assertFalse(
            any(
                item.code == "OCR_REQUIRED"
                for item in validation.issues
            )
        )

    def test_missing_source_text_is_never_invented(self):
        raw = self.without_party_evidence()
        extraction, audit = augment_party_evidence(
            raw,
            source_page_texts=["Contract No. KBFX-2026-001"],
        )
        self.assertFalse(
            any(
                item.field in self.PARTY_FIELDS
                for item in extraction.evidence
            )
        )
        self.assertEqual(audit, [])

    def test_unrelated_iso_code_quote_is_not_promoted_to_party_country(self):
        raw = self.without_party_evidence()
        extraction, unused_audit = augment_party_evidence(
            raw.model_copy(
                update={
                    "evidence": list(raw.evidence)
                    + [
                        FieldEvidence(
                            field="document_number",
                            page=1,
                            source_text="Reference: US-2026-001",
                            extraction_type="EXPLICIT",
                            confidence_reason="문서번호 원문",
                        )
                    ]
                }
            )
        )
        self.assertFalse(
            any(
                item.field == "seller_country"
                for item in extraction.evidence
            )
        )

    def test_country_evidence_stays_with_its_named_party_block(self):
        raw = self.without_party_evidence()
        page_text = """Legal Name: BlueWave Components Inc.
Country: United States
Legal Name: Hanseong Precision Co., Ltd.
Country: Republic of Korea
Port of Destination: Seattle, United States
"""
        extraction, unused_audit = augment_party_evidence(
            raw.model_copy(
                update={
                    "seller_country": "US",
                    "buyer_country": "KR",
                }
            ),
            source_page_texts=[page_text],
        )
        by_field = {
            item.field: item.source_text
            for item in extraction.evidence
            if item.field in self.PARTY_FIELDS
        }
        self.assertEqual(by_field["seller_country"], "Country: United States")
        self.assertEqual(
            by_field["buyer_country"],
            "Country: Republic of Korea",
        )

    def test_combined_model_evidence_can_be_safely_promoted(self):
        raw = self.without_party_evidence()
        combined = [
            FieldEvidence(
                field="seller",
                page=1,
                source_text=(
                    "Seller Legal Name: BlueWave Components Inc.; "
                    "Country: United States"
                ),
                extraction_type="EXPLICIT",
                confidence_reason="판매자 블록 원문",
            ),
            FieldEvidence(
                field="buyer",
                page=1,
                source_text=(
                    "Buyer Legal Name: Hanseong Precision Co., Ltd.; "
                    "Country: Republic of Korea"
                ),
                extraction_type="EXPLICIT",
                confidence_reason="구매자 블록 원문",
            ),
        ]
        extraction, audit = augment_party_evidence(
            raw.model_copy(
                update={"evidence": list(raw.evidence) + combined}
            )
        )
        generated_fields = {
            item.field
            for item in extraction.evidence
            if item.field in self.PARTY_FIELDS
        }
        self.assertEqual(generated_fields, self.PARTY_FIELDS)
        self.assertEqual(
            {item.field for item in audit},
            self.PARTY_FIELDS,
        )

    def test_inferred_party_evidence_does_not_satisfy_core_gate(self):
        raw = self.without_party_evidence()
        inferred = FieldEvidence(
            field="seller_name",
            page=1,
            source_text="BlueWave Components Inc.",
            extraction_type="INFERRED",
            confidence_reason="문맥 추론",
        )
        unused_extraction, validation = apply_deterministic_review_state(
            raw.model_copy(
                update={"evidence": list(raw.evidence) + [inferred]}
            ),
            company_role="BUYER",
            company_country="KR",
        )
        self.assertTrue(
            any(
                item.code == "MISSING_CORE_EVIDENCE"
                and item.field == "seller_name"
                for item in validation.issues
            )
        )

    def test_stale_party_evidence_after_name_change_is_a_gap(self):
        raw = raw_contract().model_copy(
            update={"seller_name": "Replacement Components Inc."}
        )
        unused_extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertTrue(
            any(
                item.code == "MISSING_CORE_EVIDENCE"
                and item.field == "seller_name"
                for item in validation.issues
            )
        )

    def test_pdf_text_reader_handles_image_only_pdf_without_inventing_text(self):
        source = ROOT / "samples" / "demo_net90_contract.pdf"
        pages = extract_pdf_page_texts(source.read_bytes())
        self.assertEqual(len(pages), 1)
        self.assertIsInstance(pages[0], str)


class DateNormalizationTests(unittest.TestCase):
    def test_date_placeholders_become_none(self):
        for value in (
            "",
            " ",
            "YYYY-MM-DD",
            "yyyy-mm-dd",
            "None",
            "null",
            "N/A",
            "-",
        ):
            with self.subTest(value=value):
                self.assertIsNone(normalize_date_text(value))

    def test_net_90_calendar_days_from_contract_date_matches(self):
        self.assertEqual(
            calculate_net_due_date(
                "2026-07-27",
                "Net 90 calendar days from the Contract Date",
            ),
            "2026-10-25",
        )
        extraction, validation = apply_deterministic_review_state(
            raw_contract(),
            company_role="BUYER",
            company_country="KR",
        )
        self.assertIsNone(extraction.issue_date)
        self.assertNotIn("DUE_DATE_CONFLICT", issue_codes(validation))
        self.assertTrue(
            any(
                item.field == "explicit_due_date"
                and item.status == "VERIFIED"
                for item in validation.normalization_audit
            )
        )

    def test_due_date_conflict_is_reported(self):
        raw = raw_contract().model_copy(
            update={"explicit_due_date": "2026-10-24"}
        )
        unused_extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        del unused_extraction
        self.assertIn("DUE_DATE_CONFLICT", issue_codes(validation))

    def test_business_days_are_not_calendar_days(self):
        self.assertEqual(
            calculate_net_due_date(
                "2026-07-24",
                "Net 2 business days from the Contract Date",
            ),
            "2026-07-28",
        )


class SalesContractEndToEndTests(unittest.TestCase):
    def test_fixture_normalizes_without_original_five_errors(self):
        extraction, validation = apply_deterministic_review_state(
            raw_contract(),
            company_role="BUYER",
            company_country="KR",
        )
        self.assertEqual(
            {
                "seller_country": extraction.seller_country,
                "buyer_country": extraction.buyer_country,
                "trade_type": extraction.trade_type,
                "issue_date": extraction.issue_date,
            },
            {
                "seller_country": "US",
                "buyer_country": "KR",
                "trade_type": "IMPORT",
                "issue_date": None,
            },
        )
        self.assertTrue(
            any(item.field == "currency" for item in extraction.evidence)
        )
        self.assertTrue(
            {
                "COMPANY_COUNTRY_ROLE_MISMATCH",
                "INVALID_PARTY_COUNTRY",
            }.isdisjoint(issue_codes(validation))
        )
        self.assertFalse(
            any(
                item.code == "MISSING_REQUIRED_FIELD"
                and item.field == "trade_type"
                for item in validation.issues
            )
        )
        self.assertFalse(
            any(
                item.code == "MISSING_CORE_EVIDENCE"
                and item.field == "currency"
                for item in validation.issues
            )
        )

    def test_stage2_is_blocked_before_confirmation_and_built_after(self):
        raw = raw_contract()
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        with self.assertRaises(ValueError):
            build_stage2_input(
                extraction=extraction,
                validation=validation,
                confirmations=ConfirmationState(),
                source_filename="KBFX_sample_international_sales_contract.pdf",
            )

        record = create_confirmation_record(
            original=raw,
            confirmed=extraction,
            confirmed_due_date="2026-10-25",
            company_role_confirmed=True,
            trade_type_confirmed=True,
            currency_confirmed=True,
            amount_due_confirmed=True,
            due_date_confirmed=True,
            source_filename="KBFX_sample_international_sales_contract.pdf",
            source_sha256="b" * 64,
            company_country="Republic of Korea",
            trade_type_source=validation.trade_type_source,
            confirmed_by="regression-test",
            confirmed_at="2026-07-27T12:00:00+09:00",
            review_audit_trail=[
                {
                    "changed_at": "2026-07-27T11:59:00+09:00",
                    "before": {
                        "company_role": "BUYER",
                        "company_country": "KR",
                        "trade_type": "UNKNOWN",
                        "seller_country": "United States",
                        "buyer_country": "Republic of Korea",
                        "currency": "USD",
                        "amount_due": "100000.00",
                        "contract_date": "2026-07-27",
                        "explicit_due_date": "2026-10-25",
                    },
                    "after": {
                        "company_role": "BUYER",
                        "company_country": "KR",
                        "trade_type": "IMPORT",
                        "seller_country": "US",
                        "buyer_country": "KR",
                        "currency": "USD",
                        "amount_due": "100000.00",
                        "contract_date": "2026-07-27",
                        "explicit_due_date": "2026-10-25",
                    },
                }
            ],
        )
        confirmed_validation = validate_confirmation(
            extraction=extraction,
            record=record,
            company_country="KR",
        )
        self.assertTrue(confirmed_validation.stage2_allowed)
        payload = build_stage2_input(
            extraction=extraction,
            validation=confirmed_validation,
            confirmations=record.checks,
            source_filename=record.source_filename,
            source_sha256=record.source_sha256,
            confirmed_at=record.confirmed_at,
        )
        self.assertEqual(payload["trade"]["trade_type"], "IMPORT")
        self.assertEqual(payload["trade"]["currency"], "USD")
        self.assertEqual(payload["trade"]["foreign_amount"], "100000.00")
        self.assertEqual(
            payload["trade"]["settlement_date"],
            "2026-10-25",
        )
        self.assertEqual(
            set(payload["source"]["confirmed_fields"]),
            {
                "company_role",
                "trade_type",
                "currency",
                "amount_due",
                "due_date",
            },
        )
        self.assertEqual(
            record.original_values["seller_country"],
            "United States",
        )
        self.assertEqual(len(record.review_audit_trail), 1)
        self.assertEqual(
            record.review_audit_trail[0].before.trade_type,
            "UNKNOWN",
        )

    def test_user_evidence_override_is_explicit_and_not_fake_ai_evidence(self):
        raw = raw_contract()
        evidence = [
            item.model_copy(
                update={"source_text": "Total Contract Price: 100,000.00"}
            )
            if item.field == "amount_due"
            else item
            for item in raw.evidence
        ]
        raw = raw.model_copy(update={"evidence": evidence})
        extraction, initial_validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertIn(
            "MISSING_CORE_EVIDENCE",
            issue_codes(initial_validation),
        )
        record = create_confirmation_record(
            original=raw,
            confirmed=extraction,
            confirmed_due_date="2026-10-25",
            company_role_confirmed=True,
            trade_type_confirmed=True,
            currency_confirmed=True,
            amount_due_confirmed=True,
            due_date_confirmed=True,
            source_filename="contract.pdf",
            source_sha256="c" * 64,
            company_country="KR",
            evidence_override_fields=["currency"],
            confirmed_by="regression-test",
            confirmed_at="2026-07-27T12:00:00+09:00",
        )
        validation = validate_confirmation(
            extraction=extraction,
            record=record,
            company_country="KR",
        )
        self.assertTrue(validation.stage2_allowed)
        self.assertFalse(
            any(item.field == "currency" for item in extraction.evidence)
        )
        self.assertTrue(record.checks.user_confirmed_override)
        self.assertEqual(
            record.checks.user_confirmed_override_fields,
            ["currency"],
        )


class StreamlitReviewFlowTests(unittest.TestCase):
    def test_user_country_edits_are_revalidated_from_latest_widgets(self):
        from streamlit.testing.v1 import AppTest

        environment = patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "",
                "ENABLE_LIVE_DOCUMENT_EXTRACTION": "false",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        app = AppTest.from_file(
            str(ROOT / "app.py"),
            default_timeout=20,
        ).run()
        next(
            button
            for button in app.button
            if button.key == "service_sample_export"
        ).click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("extraction", app.session_state)

        seller_country = next(
            widget
            for widget in app.text_input
            if widget.key == "review_seller_country_widget"
        )
        buyer_country = next(
            widget
            for widget in app.text_input
            if widget.key == "review_buyer_country_widget"
        )
        issue_date = next(
            widget
            for widget in app.text_input
            if widget.key == "review_issue_date_widget"
        )
        company_role = next(
            widget
            for widget in app.selectbox
            if widget.key == "review_company_role_widget"
        )
        company_role.set_value("BUYER")
        seller_country.set_value("United States")
        buyer_country.set_value("Republic of Korea")
        issue_date.set_value("YYYY-MM-DD")
        review = next(
            button
            for button in app.button
            if button.label == "수정 내용 저장 및 다시 검증"
        )
        review.click().run()
        self.assertEqual(len(app.exception), 0)

        extraction = TradeDocumentExtraction.model_validate(
            app.session_state["extraction"]
        )
        validation = app.session_state["extraction_validation"]
        self.assertEqual(extraction.seller_country, "US")
        self.assertEqual(extraction.buyer_country, "KR")
        self.assertEqual(extraction.trade_type, "IMPORT")
        self.assertIsNone(extraction.issue_date)
        self.assertFalse(
            any(
                item["code"]
                in {
                    "INVALID_PARTY_COUNTRY",
                    "COMPANY_COUNTRY_ROLE_MISMATCH",
                }
                for item in validation["issues"]
            )
        )
        self.assertEqual(
            len(app.session_state["review_audit_trail"]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
