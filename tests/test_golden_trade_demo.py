import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

from pypdf import PdfReader

from schemas import ConfirmationState, TradeDocumentExtraction
from scripts.generate_golden_trade_demo import (
    ADVANCE_QUOTE,
    BALANCE_QUOTE,
    BUYER_LINE,
    DEMO_INPUTS_PATH,
    EXPECTED_EXTRACTION_PATH,
    GUARANTEE_LINE,
    LC_LINE,
    NOTICE,
    PDF_PATH,
    SELLER_LINE,
    build_pdf_bytes,
    demo_inputs_payload,
    expected_extraction_payload,
    generate,
)
from src.document_intake.normalization import normalize_country_name
from src.document_intake.source_evidence import extract_pdf_page_texts
from src.domain.stage1_web_models import SpotQuote
from src.security.upload_guard import validate_upload
from src.stage1.scenario_builder import build_fx_scenarios
from src.stage1.web_forecast import normalize_stage1_web_forecast
from src.config import Settings
from validators import apply_deterministic_review_state


ROOT = Path(__file__).resolve().parents[1]
STAGE1_FIXTURE = (
    ROOT
    / "src"
    / "integration_assets"
    / "stage1"
    / "latest_forecast.json"
)


class GoldenTradeDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pdf_bytes = PDF_PATH.read_bytes()
        cls.page_texts = extract_pdf_page_texts(cls.pdf_bytes)
        cls.extraction = TradeDocumentExtraction.model_validate_json(
            EXPECTED_EXTRACTION_PATH.read_text(encoding="utf-8")
        )
        cls.demo_inputs: Dict[str, Any] = json.loads(
            DEMO_INPUTS_PATH.read_text(encoding="utf-8")
        )

    def test_generated_artifacts_match_deterministic_sources(self):
        self.assertEqual(self.pdf_bytes, build_pdf_bytes())
        self.assertEqual(
            json.loads(EXPECTED_EXTRACTION_PATH.read_text(encoding="utf-8")),
            expected_extraction_payload(),
        )
        self.assertEqual(self.demo_inputs, demo_inputs_payload())

        with tempfile.TemporaryDirectory(prefix="golden-demo-") as temp_dir:
            output = Path(temp_dir)
            generate(output)
            first = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in output.iterdir()
                if path.is_file()
            }
            generate(output)
            second = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in output.iterdir()
                if path.is_file()
            }
        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)

    def test_pdf_has_two_nonempty_text_layer_pages(self):
        reader = PdfReader(PDF_PATH, strict=True)
        self.assertEqual(len(reader.pages), 2)
        self.assertEqual(len(self.page_texts), 2)
        for page_number, text in enumerate(self.page_texts, start=1):
            with self.subTest(page=page_number):
                self.assertGreater(len(text.strip()), 500)
                self.assertIn(NOTICE, text)

    def test_every_expected_evidence_quote_exists_on_declared_page(self):
        for evidence in self.extraction.evidence:
            self.assertIsNotNone(evidence.page)
            page_text = self.page_texts[int(evidence.page) - 1]
            with self.subTest(
                field=evidence.field,
                page=evidence.page,
                quote=evidence.source_text,
            ):
                self.assertIn(evidence.source_text, page_text)

    def test_expected_countries_normalize_and_derive_export(self):
        raw = self.extraction.model_copy(
            update={
                "seller_country": "Republic of Korea (KR)",
                "buyer_country": "Brazil (BR)",
                "trade_type": "UNKNOWN",
            }
        )
        normalized, validation = apply_deterministic_review_state(
            raw,
            company_role="SELLER",
            company_country="Republic of Korea (KR)",
            source_page_texts=self.page_texts,
        )
        self.assertEqual(normalized.seller_country, "KR")
        self.assertEqual(normalized.buyer_country, "BR")
        self.assertEqual(normalized.trade_type, "EXPORT")
        self.assertEqual(validation.auto_trade_type, "EXPORT")

        country_audit = {
            item.field: item
            for item in validation.normalization_audit
            if item.field in {"seller_country", "buyer_country"}
        }
        self.assertEqual(
            country_audit["seller_country"].raw_value,
            "Republic of Korea (KR)",
        )
        self.assertEqual(
            country_audit["seller_country"].normalized_value,
            "KR",
        )
        self.assertIn(
            "normalization_method=VERIFIED_COUNTRY_NAME_AND_CODE",
            country_audit["seller_country"].message,
        )
        self.assertEqual(
            country_audit["buyer_country"].raw_value,
            "Brazil (BR)",
        )
        self.assertEqual(
            country_audit["buyer_country"].normalized_value,
            "BR",
        )

    def test_direct_country_normalization_has_no_warning(self):
        expected = {
            "Republic of Korea (KR)": "KR",
            "Brazil (BR)": "BR",
        }
        for raw_value, expected_code in expected.items():
            normalized, audit = normalize_country_name(
                raw_value,
                "country",
            )
            with self.subTest(raw_value=raw_value):
                self.assertEqual(normalized, expected_code)
                self.assertEqual(audit.raw_value, raw_value)
                self.assertEqual(audit.normalized_value, expected_code)
                self.assertIn("warning=NONE", audit.message)

    def test_financial_dates_and_installments_match_contract(self):
        extraction = self.extraction
        self.assertEqual(extraction.document_type, "SALES_CONTRACT")
        self.assertEqual(extraction.currency, "USD")
        self.assertEqual(Decimal(extraction.grand_total), Decimal("100000"))
        self.assertEqual(Decimal(extraction.amount_due), Decimal("100000"))
        self.assertEqual(extraction.contract_date, "2026-07-29")
        self.assertEqual(extraction.shipment_date, "2026-08-05")
        self.assertEqual(extraction.explicit_due_date, "2026-08-20")
        self.assertIsNone(extraction.derived_due_date)
        installment_total = sum(
            (
                Decimal(item.amount)
                for item in extraction.installments
                if item.amount is not None
            ),
            Decimal("0"),
        )
        self.assertEqual(installment_total, Decimal("100000"))
        self.assertEqual(
            [item.amount for item in extraction.installments],
            ["20000.00", "80000.00"],
        )
        self.assertEqual(
            [item.due_date for item in extraction.installments],
            ["2026-07-29", "2026-08-20"],
        )

    def test_source_grounded_values_pass_after_user_confirmation(self):
        confirmations = ConfirmationState(
            company_role_confirmed=True,
            trade_type_confirmed=True,
            currency_confirmed=True,
            amount_due_confirmed=True,
            due_date_confirmed=True,
            confirmed_due_date="2026-08-20",
            confirmed_by="golden-demo-test",
            confirmed_at="2026-07-29T09:00:00+09:00",
        )
        normalized, validation = apply_deterministic_review_state(
            self.extraction,
            company_role="SELLER",
            company_country="KR",
            confirmations=confirmations,
            source_page_texts=self.page_texts,
        )
        self.assertEqual(normalized.currency, "USD")
        self.assertEqual(normalized.amount_due, "100000.00")
        self.assertEqual(normalized.explicit_due_date, "2026-08-20")
        self.assertEqual(normalized.trade_type, "EXPORT")
        self.assertTrue(validation.validation_pass)
        self.assertTrue(validation.stage2_allowed)
        self.assertFalse(
            {
                "EVIDENCE_NOT_IN_SOURCE",
                "EVIDENCE_VALUE_MISMATCH",
                "EVIDENCE_UNVERIFIABLE",
                "OCR_REQUIRED",
            }.intersection(item.code for item in validation.issues)
        )

    def test_contract_and_manual_user_inputs_are_separated(self):
        facts = self.demo_inputs[
            "document_facts_outside_extraction_schema"
        ]
        presenter = self.demo_inputs["presenter_only_inputs"]
        self.assertEqual(facts["letter_of_credit_status"], "NOT_REQUIRED")
        self.assertEqual(
            facts["independent_bank_guarantee_status"],
            "NOT_PROVIDED",
        )
        self.assertIn(LC_LINE, self.page_texts[1])
        self.assertIn(GUARANTEE_LINE, self.page_texts[1])
        self.assertEqual(presenter["credit_insurance"], "NO")
        self.assertEqual(presenter["existing_hedge"], "NONE")
        self.assertEqual(
            self.demo_inputs["user_confirmed_trade_inputs"][
                "counterparty_relationship"
            ],
            "EXISTING",
        )
        self.assertEqual(
            self.demo_inputs["fixture_disclosure"]["evaluation_mode"],
            "FIXTURE",
        )
        self.assertFalse(
            self.demo_inputs["fixture_disclosure"][
                "model_accuracy_claim_allowed"
            ]
        )

    def test_contract_contains_required_natural_language_clauses(self):
        joined = "\n".join(self.page_texts)
        for quote in (
            SELLER_LINE,
            BUYER_LINE,
            ADVANCE_QUOTE,
            BALANCE_QUOTE,
            LC_LINE,
            GUARANTEE_LINE,
        ):
            with self.subTest(quote=quote):
                self.assertIn(quote, joined)

    def test_contract_contains_no_operational_identifiers_or_signatures(self):
        joined = "\n".join(self.page_texts).casefold()
        forbidden_labels = (
            "address:",
            "telephone:",
            "phone:",
            "email:",
            "account number:",
            "registration number:",
            "tax id:",
            "signature:",
            "signed by:",
            "seal:",
            "stamp:",
        )
        for label in forbidden_labels:
            with self.subTest(label=label):
                self.assertNotIn(label, joined)
        self.assertNotIn("payment risk:", joined)
        self.assertNotIn("recommended product:", joined)

    def test_upload_guard_accepts_golden_pdf(self):
        metadata = validate_upload(
            file_bytes=self.pdf_bytes,
            filename=PDF_PATH.name,
            claimed_mime_type="application/pdf",
            settings=Settings(max_upload_mb=15, max_pdf_pages=20),
        )
        self.assertEqual(metadata.filename, PDF_PATH.name)
        self.assertEqual(metadata.mime_type, "application/pdf")

    def test_due_date_is_inside_current_stage1_horizon(self):
        forecast = normalize_stage1_web_forecast(
            json.loads(STAGE1_FIXTURE.read_text(encoding="utf-8")),
            provider="golden-demo-test",
            now=datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc),
        )
        result = build_fx_scenarios(
            spot_quote=SpotQuote(
                pair="USD/KRW",
                rate="1400.00",
                quote_convention="KRW_PER_1_USD",
                rate_type="TEST_FIXTURE",
                as_of="2026-07-29T09:00:00+09:00",
                source="GOLDEN_DEMO_FIXTURE",
                user_confirmed=False,
            ),
            settlement_date="2026-08-20",
            currency="USD",
            forecast=forecast,
        )
        self.assertEqual(result.horizon_end_date, "2026-08-25")
        self.assertFalse(result.horizon_mismatch)
        self.assertTrue(
            all(
                item.included_in_calculation
                for item in result.model_path_scenarios
            )
        )


if __name__ == "__main__":
    unittest.main()
