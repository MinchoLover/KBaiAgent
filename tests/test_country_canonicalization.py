import json
import unittest
from pathlib import Path
from typing import Dict, List

from schemas import TradeDocumentExtraction
from src.document_intake.normalization import (
    normalize_country_name,
    normalize_extraction_values,
)
from validators import apply_deterministic_review_state


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    ROOT / "tests" / "fixtures" / "kbfx_sales_contract_extraction.json"
)

COUNTRY_VARIANTS: Dict[str, List[str]] = {
    "US": [
        "United States",
        "United States of America",
        "United States (US)",
        "U.S.",
        "U.S.A.",
        "USA",
    ],
    "BR": [
        "Brazil",
        "Brazil (BR)",
        "Federative Republic of Brazil",
    ],
    "KR": [
        "Republic of Korea",
        "Republic of Korea (KR)",
        "South Korea",
        "Korea, Republic of",
        "Korea (KR)",
    ],
}


def raw_contract() -> TradeDocumentExtraction:
    return TradeDocumentExtraction.model_validate(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    )


class CountryCanonicalizationUnitTests(unittest.TestCase):
    def test_required_variants_normalize_to_verified_iso_codes(self):
        for expected, variants in COUNTRY_VARIANTS.items():
            for raw_value in variants:
                with self.subTest(expected=expected, raw_value=raw_value):
                    normalized, audit = normalize_country_name(
                        raw_value,
                        "seller_country",
                    )
                    self.assertEqual(normalized, expected)
                    self.assertEqual(audit.raw_value, raw_value)
                    self.assertEqual(audit.normalized_value, expected)
                    self.assertIn(
                        "normalization_method=",
                        audit.message,
                    )
                    self.assertIn("warning=NONE", audit.message)

    def test_name_and_parenthetical_code_conflict_becomes_unknown(self):
        conflicts = [
            "United States (BR)",
            "Brazil (US)",
            "Republic of Korea (US)",
            "United States (ZZ)",
        ]
        for raw_value in conflicts:
            with self.subTest(raw_value=raw_value):
                normalized, audit = normalize_country_name(
                    raw_value,
                    "buyer_country",
                )
                self.assertEqual(normalized, "UNKNOWN")
                self.assertEqual(audit.raw_value, raw_value)
                self.assertEqual(audit.normalized_value, "UNKNOWN")
                self.assertEqual(audit.status, "UNKNOWN_ALIAS")
                self.assertIn(
                    "normalization_method=COUNTRY_NAME_CODE_CONFLICT",
                    audit.message,
                )
                self.assertNotIn("warning=NONE", audit.message)

    def test_unverified_country_expression_is_not_guessed(self):
        unsupported = [
            "United Statess",
            "Federative Republic of Brasil",
        ]
        for raw_value in unsupported:
            with self.subTest(raw_value=raw_value):
                normalized, audit = normalize_country_name(
                    raw_value,
                    "seller_country",
                )
                self.assertEqual(normalized, raw_value)
                self.assertEqual(audit.raw_value, raw_value)
                self.assertEqual(audit.normalized_value, raw_value)
                self.assertEqual(audit.status, "UNKNOWN_ALIAS")
                self.assertNotIn("warning=NONE", audit.message)

        normalized, audit = normalize_country_name(
            "Atlantis (US)",
            "seller_country",
        )
        self.assertEqual(normalized, "UNKNOWN")
        self.assertEqual(audit.raw_value, "Atlantis (US)")
        self.assertEqual(audit.normalized_value, "UNKNOWN")
        self.assertEqual(audit.status, "UNKNOWN_ALIAS")
        self.assertIn(
            "normalization_method=UNVERIFIED_COUNTRY_NAME_WITH_CODE",
            audit.message,
        )

    def test_raw_value_and_verified_method_survive_whitespace_cleanup(self):
        raw_value = "  Brazil (BR)  "
        normalized, audit = normalize_country_name(
            raw_value,
            "seller_country",
        )
        self.assertEqual(normalized, "BR")
        self.assertEqual(audit.raw_value, raw_value)
        self.assertEqual(audit.normalized_value, "BR")
        self.assertIn(
            "normalization_method=VERIFIED_COUNTRY_NAME_AND_CODE",
            audit.message,
        )


class CountryCanonicalizationMetamorphicTests(unittest.TestCase):
    def test_equivalent_expressions_produce_the_same_iso_code(self):
        for expected, variants in COUNTRY_VARIANTS.items():
            normalized_values = {
                normalize_country_name(value, "country")[0]
                for value in variants
            }
            self.assertEqual(normalized_values, {expected})

    def test_normalized_countries_derive_import_and_export(self):
        import_raw = raw_contract().model_copy(
            update={
                "company_role": "BUYER",
                "seller_country": "United States (US)",
                "buyer_country": "Republic of Korea (KR)",
            }
        )
        normalized_import, import_validation = (
            apply_deterministic_review_state(
                import_raw,
                company_role="BUYER",
                company_country="Korea (KR)",
            )
        )
        self.assertEqual(normalized_import.seller_country, "US")
        self.assertEqual(normalized_import.buyer_country, "KR")
        self.assertEqual(normalized_import.trade_type, "IMPORT")
        self.assertEqual(import_validation.auto_trade_type, "IMPORT")

        export_raw = raw_contract().model_copy(
            update={
                "company_role": "SELLER",
                "seller_country": "Korea (KR)",
                "buyer_country": "Brazil (BR)",
            }
        )
        normalized_export, export_validation = (
            apply_deterministic_review_state(
                export_raw,
                company_role="SELLER",
                company_country="Republic of Korea (KR)",
            )
        )
        self.assertEqual(normalized_export.seller_country, "KR")
        self.assertEqual(normalized_export.buyer_country, "BR")
        self.assertEqual(normalized_export.trade_type, "EXPORT")
        self.assertEqual(export_validation.auto_trade_type, "EXPORT")

    def test_country_code_conflict_keeps_trade_type_unknown(self):
        raw = raw_contract().model_copy(
            update={
                "company_role": "BUYER",
                "seller_country": "United States (BR)",
                "buyer_country": "Republic of Korea (KR)",
            }
        )
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertEqual(extraction.seller_country, "UNKNOWN")
        self.assertEqual(extraction.trade_type, "UNKNOWN")
        self.assertEqual(validation.auto_trade_type, "UNKNOWN")
        self.assertIn(
            "UNKNOWN_COUNTRY_ALIAS",
            {item.code for item in validation.issues},
        )

    def test_country_normalization_does_not_change_financial_or_date_fields(
        self,
    ):
        canonical_raw = raw_contract().model_copy(
            update={
                "seller_country": "US",
                "buyer_country": "KR",
            }
        )
        variant_raw = raw_contract().model_copy(
            update={
                "seller_country": "United States (US)",
                "buyer_country": "Republic of Korea (KR)",
            }
        )
        canonical, unused_canonical_audit = normalize_extraction_values(
            canonical_raw
        )
        variant, unused_variant_audit = normalize_extraction_values(
            variant_raw
        )
        del unused_canonical_audit
        del unused_variant_audit

        immutable_fields = [
            "currency",
            "grand_total",
            "amount_due",
            "issue_date",
            "contract_date",
            "shipment_date",
            "explicit_due_date",
            "derived_due_date",
            "installments",
        ]
        for field in immutable_fields:
            with self.subTest(field=field):
                self.assertEqual(
                    getattr(canonical, field),
                    getattr(variant, field),
                )


if __name__ == "__main__":
    unittest.main()
