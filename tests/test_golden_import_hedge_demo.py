import hashlib
import json
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

from scripts.generate_golden_import_hedge_demo import (
    BUYER_LINE,
    DEMO_INPUTS_PATH,
    EXPECTED_EXTRACTION_PATH,
    GUARANTEE_LINE,
    LC_LINE,
    NOTICE,
    PAYMENT_QUOTE,
    PDF_PATH,
    SELLER_LINE,
    build_pdf_bytes,
    demo_inputs_payload,
    expected_extraction_payload,
    generate,
)
from scripts.verify_golden_import_hedge_flow import (
    golden_import_hedge_summary,
)
from src.document_intake.normalization import normalize_country_name
from src.ui.state import input_signature
from tests.golden_import_hedge_fixture import (
    KB_MACRO_FIXTURE_ROOT,
    KB_MACRO_FORECAST,
    KB_MACRO_HEDGE,
    build_golden_import_hedge_fixture,
)


ROOT = Path(__file__).resolve().parents[1]
OLD_GOLDEN = (
    ROOT / "dataset" / "golden_demo" / "golden_export_contract.pdf"
)
GOLDEN_IMPORT_SHA256 = (
    "fbd4c4dbdf0f92d459e19acf2af4a1e2ee3cd0916f43576290d54b040662550b"
)
OLD_GOLDEN_SHA256 = (
    "5330a1a572488005f7b02cccfc7150fbaa8b38c84bb9290da1e0c6e1c3a0a91c"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GoldenImportHedgeDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = build_golden_import_hedge_fixture()
        cls.summary = golden_import_hedge_summary()

    def test_generated_artifacts_are_deterministic(self):
        self.assertEqual(PDF_PATH.read_bytes(), build_pdf_bytes())
        self.assertEqual(
            json.loads(
                EXPECTED_EXTRACTION_PATH.read_text(encoding="utf-8")
            ),
            expected_extraction_payload(),
        )
        self.assertEqual(
            json.loads(DEMO_INPUTS_PATH.read_text(encoding="utf-8")),
            demo_inputs_payload(),
        )
        with tempfile.TemporaryDirectory(
            prefix="golden-import-hedge-"
        ) as temporary:
            output = Path(temporary)
            generate(output)
            first = {
                path.name: _sha256(path)
                for path in output.iterdir()
                if path.is_file()
            }
            generate(output)
            second = {
                path.name: _sha256(path)
                for path in output.iterdir()
                if path.is_file()
            }
        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)
        self.assertEqual(_sha256(PDF_PATH), GOLDEN_IMPORT_SHA256)

    def test_pdf_has_two_searchable_text_layer_pages(self):
        reader = PdfReader(PDF_PATH, strict=True)
        self.assertEqual(len(reader.pages), 2)
        self.assertEqual(len(self.artifacts["page_texts"]), 2)
        for text in self.artifacts["page_texts"]:
            self.assertGreater(len(text.strip()), 500)
            self.assertIn(NOTICE, text)

    def test_exact_evidence_exists_on_each_declared_page(self):
        extraction = self.artifacts["extraction"]
        for evidence in extraction.evidence:
            self.assertIsNotNone(evidence.page)
            with self.subTest(
                field=evidence.field,
                page=evidence.page,
            ):
                self.assertIn(
                    evidence.source_text,
                    self.artifacts["page_texts"][
                        int(evidence.page) - 1
                    ],
                )
        self.assertIn(PAYMENT_QUOTE, self.artifacts["page_texts"][1])

    def test_raw_country_aliases_normalize_to_import_trade(self):
        raw = self.artifacts["raw_extraction"]
        extraction = self.artifacts["extraction"]
        validation = self.artifacts["initial_validation"]
        self.assertEqual(raw.seller_country, "United States (US)")
        self.assertEqual(
            raw.buyer_country,
            "Republic of Korea (KR)",
        )
        self.assertEqual(extraction.seller_country, "US")
        self.assertEqual(extraction.buyer_country, "KR")
        self.assertEqual(extraction.trade_type, "IMPORT")
        self.assertEqual(validation.auto_trade_type, "IMPORT")
        audit = {
            item.field: item
            for item in validation.normalization_audit
        }
        self.assertEqual(
            audit["seller_country"].raw_value,
            "United States (US)",
        )
        self.assertEqual(
            audit["buyer_country"].raw_value,
            "Republic of Korea (KR)",
        )
        for raw_value, code in (
            ("United States (US)", "US"),
            ("Republic of Korea (KR)", "KR"),
        ):
            normalized, entry = normalize_country_name(
                raw_value,
                "country",
            )
            self.assertEqual(normalized, code)
            self.assertIn("warning=NONE", entry.message)

    def test_single_payable_contract_matches_expected_domain_values(self):
        extraction = self.artifacts["extraction"]
        self.assertEqual(extraction.document_type, "SALES_CONTRACT")
        self.assertEqual(extraction.company_role, "BUYER")
        self.assertEqual(extraction.currency, "USD")
        self.assertEqual(Decimal(extraction.grand_total), Decimal("100000"))
        self.assertEqual(Decimal(extraction.amount_due), Decimal("100000"))
        self.assertEqual(extraction.contract_date, "2026-07-29")
        self.assertEqual(extraction.shipment_date, "2026-08-12")
        self.assertEqual(extraction.explicit_due_date, "2026-08-27")
        self.assertEqual(extraction.installments, [])

    def test_confirmation_and_downstream_share_one_payment_date(self):
        artifacts = self.artifacts
        dates = {
            artifacts["confirmation"].checks.confirmed_due_date,
            artifacts["document_input"]["trade"]["settlement_date"],
            artifacts["stage1"].target_date,
            artifacts["stage2_input"].exposures[0].settlement_date,
            artifacts["stage2"].exposure_computations[
                0
            ].settlement_date,
            artifacts["kb_macro_reference"].request.payment_date,
        }
        self.assertEqual(dates, {"2026-08-27"})
        self.assertTrue(artifacts["validation"].validation_pass)
        self.assertTrue(artifacts["validation"].stage2_allowed)
        self.assertEqual(
            artifacts["document_input"]["trade"][
                "settlement_date_source"
            ],
            "stage0.confirmation.checks.confirmed_due_date",
        )

    def test_stage2_uses_cash_and_preserves_expected_import_exposure(self):
        stage2 = self.artifacts["stage2"]
        self.assertEqual(stage2.trade_type, "IMPORT")
        self.assertEqual(stage2.total_foreign_amount, "100000.00")
        self.assertEqual(stage2.held_fx_used, "10000.00")
        self.assertEqual(stage2.hedged_amount, "0")
        self.assertEqual(stage2.open_exposure, "90000.00")
        self.assertEqual(
            stage2.base_required_or_proceeds_krw,
            "126000000.00",
        )
        up_five = next(
            item
            for item in stage2.scenario_results
            if item.scenario_name == "UP_5"
        )
        self.assertEqual(up_five.loss_vs_base, "6300000.00")
        self.assertEqual(up_five.ending_cash, "7700000.00")
        self.assertEqual(
            up_five.maximum_buffer_shortfall,
            "2300000.00",
        )
        self.assertEqual(up_five.cash_deficit, "0.00")
        self.assertEqual(up_five.post_credit_shortfall, "0.00")

    def test_internal_stage3_remains_separate_and_has_three_candidates(self):
        stage3 = self.artifacts["stage3"]
        external = self.artifacts["kb_macro_reference"]
        self.assertEqual(stage3.status, "CANDIDATES_NOT_ADVICE")
        self.assertEqual(
            [item.rank for item in stage3.candidates],
            [1, 2, 3],
        )
        self.assertEqual(stage3.candidates[0].forward_ratio, "1")
        self.assertTrue(external.fallback_to_internal_stage3)
        self.assertFalse(external.published_to_stage4)
        self.assertNotEqual(
            stage3.candidates[1].model_dump(),
            external.candidates[1].model_dump(),
        )

    def test_external_fixture_matches_current_trade_and_is_reference_only(self):
        reference = self.artifacts["kb_macro_reference"]
        self.assertEqual(reference.status, "REFERENCE_ONLY")
        self.assertEqual(reference.provider_mode, "fixture")
        self.assertEqual(reference.pricing_status, "MOCK")
        self.assertTrue(reference.validation.passed)
        self.assertEqual(
            [item.rank for item in reference.candidates],
            [1, 2, 3],
        )
        request = reference.request
        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.amount_usd, "100000")
        self.assertEqual(request.payment_date, "2026-08-27")
        self.assertEqual(request.existing_usd_cash, "10000")
        self.assertEqual(request.existing_forward_usd, "0")
        self.assertEqual(request.net_exposure_usd, "90000")

    def test_contract_has_disclosures_and_no_operational_identifiers(self):
        joined = "\n".join(self.artifacts["page_texts"])
        for quote in (
            SELLER_LINE,
            BUYER_LINE,
            LC_LINE,
            GUARANTEE_LINE,
        ):
            self.assertIn(quote, joined)
        lowered = joined.casefold()
        for forbidden in (
            "address:",
            "telephone:",
            "email:",
            "account number:",
            "registration number:",
            "tax id:",
            "signature:",
            "signed by:",
            "seal:",
            "stamp:",
        ):
            self.assertNotIn(forbidden, lowered)
        self.assertGreaterEqual(joined.count(NOTICE), 4)

    def test_fixture_claim_boundary_excludes_live_accuracy(self):
        disclosure = self.artifacts["demo_inputs"][
            "fixture_disclosure"
        ]
        classification = self.artifacts["demo_inputs"][
            "classification"
        ]
        self.assertEqual(disclosure["evaluation_mode"], "FIXTURE")
        self.assertFalse(disclosure["model_accuracy_claim_allowed"])
        self.assertFalse(disclosure["live_extraction"])
        self.assertTrue(classification["synthetic_document"])
        self.assertFalse(classification["real_customer_document"])
        self.assertTrue(classification["test_split"])
        self.assertFalse(classification["fine_tuning_candidate"])

    def test_api_free_verifier_reports_complete_isolated_flow(self):
        self.assertTrue(self.summary["api_free"])
        self.assertFalse(self.summary["external_network_used"])
        self.assertFalse(self.summary["live_document_extraction"])
        self.assertTrue(
            all(
                value == "SUCCEEDED"
                for value in self.summary["steps"].values()
            )
        )
        self.assertFalse(
            self.summary["kb_macro_ai_reference"][
                "published_to_stage4"
            ]
        )

    def test_existing_export_golden_pdf_is_unchanged(self):
        self.assertEqual(_sha256(OLD_GOLDEN), OLD_GOLDEN_SHA256)


class GoldenImportHedgeStreamlitTests(unittest.TestCase):
    def test_current_import_can_validate_external_fixture_in_ui(self):
        from streamlit.testing.v1 import AppTest

        artifacts = build_golden_import_hedge_fixture()
        environment = {
            "ENABLE_LIVE_DOCUMENT_EXTRACTION": "false",
            "ENABLE_LLM_REPORT": "false",
            "ENABLE_KB_MACRO_HEDGE_REFERENCE": "true",
            "KB_MACRO_HEDGE_MODE": "fixture",
            "KB_MACRO_HEDGE_ALLOWED_ROOT": str(
                KB_MACRO_FIXTURE_ROOT
            ),
            "KB_MACRO_FORECAST_FILE": KB_MACRO_FORECAST.name,
            "KB_MACRO_HEDGE_FILE": KB_MACRO_HEDGE.name,
            "KB_MACRO_EXPECTED_PROVIDER_COMMIT_SHA": (
                artifacts["kb_macro_reference"]
                .provenance.producer_commit_sha
            ),
            "KB_MACRO_EXPECTED_FORECAST_SHA256": _sha256(
                KB_MACRO_FORECAST
            ),
            "KB_MACRO_EXPECTED_HEDGE_SHA256": _sha256(
                KB_MACRO_HEDGE
            ),
        }
        with patch.dict(os.environ, environment, clear=False):
            app = AppTest.from_file(
                str(ROOT / "app.py"),
                default_timeout=30,
            ).run()
            app.session_state["document_source"] = "user_upload"
            app.session_state["analysis_mode"] = "live_api"
            app.session_state["company_role_widget"] = "구매자 · BUYER"
            app.session_state["company_country_widget"] = "KR"
            app.session_state["input_signature"] = input_signature(
                mode="user_upload:live_api",
                company_role="BUYER",
                company_country="KR",
                filename="uploaded_document",
                file_bytes=b"",
            )
            app.session_state["extraction"] = artifacts[
                "extraction"
            ].model_dump()
            app.session_state["extraction_original"] = artifacts[
                "raw_extraction"
            ].model_dump()
            app.session_state["extraction_validation"] = artifacts[
                "initial_validation"
            ].model_dump()
            app.session_state["confirmation"] = artifacts[
                "confirmation"
            ].model_dump()
            app.session_state["confirmation_validation"] = artifacts[
                "validation"
            ].model_dump()
            app.session_state["upload_metadata"] = {
                "filename": artifacts["upload"].filename,
                "mime_type": artifacts["upload"].mime_type,
                "size_bytes": artifacts["upload"].size_bytes,
                "sha256": artifacts["upload"].sha256,
                "page_count": artifacts["upload"].page_count,
            }
            app.session_state["stage2_document_input"] = artifacts[
                "document_input"
            ]
            app.session_state["stage2_input"] = artifacts[
                "stage2_input"
            ].model_dump()
            app.session_state["stage2_result"] = artifacts[
                "stage2"
            ].model_dump()
            app.session_state["stage3_result"] = artifacts[
                "stage3"
            ].model_dump()
            app.session_state["active_page"] = "analysis"
            app.run()
            binding = next(
                item
                for item in app.radio
                if item.key == "kb_macro_hedge_binding_widget"
            )
            binding.set_value(
                "현재 확정 거래와 금액·지급일 대조"
            ).run()
            confirmation = next(
                item
                for item in app.checkbox
                if item.key
                == "kb_macro_hedge_constraints_confirmed_widget"
            )
            confirmation.check().run()
            button = next(
                item
                for item in app.button
                if item.key == "validate_kb_macro_hedge_reference"
            )
            button.click().run()

        self.assertEqual(len(app.exception), 0)
        stored = app.session_state["kb_macro_hedge_reference"]
        self.assertEqual(stored["status"], "REFERENCE_ONLY")
        self.assertEqual(
            stored["request"]["binding_mode"],
            "CURRENT_CONFIRMED_TRADE",
        )
        self.assertEqual(stored["request"]["amount_usd"], "100000")
        self.assertEqual(stored["request"]["payment_date"], "2026-08-27")
        self.assertEqual(stored["request"]["net_exposure_usd"], "90000")
        self.assertEqual(len(stored["candidates"]), 3)
        visible = " ".join(
            [item.value for item in app.markdown]
            + [item.value for item in app.caption]
            + [item.value for item in app.success]
            + [item.value for item in app.info]
        )
        self.assertIn("외부 환헤지 조합 참고 결과", visible)
        self.assertIn("단일 USD 수입 지급 전용", visible)
        self.assertIn("참고 전용", visible)
        self.assertNotIn("최적 상품 추천", visible)


if __name__ == "__main__":
    unittest.main()
