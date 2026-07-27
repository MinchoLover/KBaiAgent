import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pypdf import PdfReader

from prompt import (
    REQUIRED_EVIDENCE_FIELDS,
    audit_few_shot_evidence,
    build_system_prompt,
    build_user_prompt,
    load_few_shot_examples,
)
from sample_data import sample_extraction
from schemas import TradeDocumentExtraction
from scripts.evaluate_extraction import (
    _evidence_covered,
    evaluate,
    evaluate_records,
)
from scripts.export_finetuning_candidates import export_candidates
from scripts.run_regression import compare_metrics
from src.demo import run_offline_demo
from src.security.redaction import redact_text, safe_event_log
from src.ui.components import (
    format_decimal_display,
    format_foreign,
    format_krw,
    format_ratio,
    optional_positive_integer,
)
from src.ui.state import input_signature, sync_input_signature


ROOT = Path(__file__).resolve().parents[1]


class SecurityTests(unittest.TestCase):
    def test_secret_redaction(self):
        secret = "sk-" + "example_secret_123456789"
        output = redact_text(
            "OPENAI_API_KEY={} authorization: bearer {}".format(
                secret,
                secret,
            )
        )
        self.assertNotIn(secret, output)
        self.assertIn("[REDACTED]", output)

    def test_safe_log_has_no_document_content(self):
        value = safe_event_log(
            request_id="req-1",
            fingerprint="abc",
            status="PASS",
            latency_seconds=1.23456,
        )
        self.assertEqual(
            set(value),
            {"request_id", "fingerprint", "status", "latency_seconds"},
        )

    def test_prompt_marks_document_as_untrusted_data(self):
        prompt = build_system_prompt().lower()
        self.assertIn("데이터", prompt)
        self.assertIn("prompt injection", prompt)

    def test_prompt_requires_exact_party_evidence_fields(self):
        prompt = "{}\n{}".format(
            build_system_prompt(),
            build_user_prompt("BUYER", "KR"),
        )
        for field in (
            "seller_name",
            "seller_country",
            "buyer_name",
            "buyer_country",
        ):
            self.assertIn(field, prompt)
        self.assertIn("동일한 field 이름", prompt)

    def test_few_shots_have_verifiable_required_evidence(self):
        examples = load_few_shot_examples()
        self.assertEqual(audit_few_shot_evidence(examples), [])
        for example in examples:
            output = example["expected_output"]
            evidence = output["evidence"]
            for field in REQUIRED_EVIDENCE_FIELDS:
                value = output.get(field)
                if value is None or (
                    field == "installments" and not value
                ):
                    continue
                self.assertTrue(
                    any(
                        item["field"] == field
                        and item["extraction_type"] != "INFERRED"
                        and item["source_text"] in example["document_excerpt"]
                        for item in evidence
                    ),
                    msg="{}: {}".format(example["case_id"], field),
                )

    def test_evaluator_excludes_inferred_and_inexact_party_evidence(self):
        extraction = sample_extraction()
        inferred_currency = extraction.model_copy(
            update={
                "evidence": [
                    item.model_copy(
                        update={"extraction_type": "INFERRED"}
                    )
                    if item.field == "currency"
                    else item
                    for item in extraction.evidence
                ]
            }
        )
        self.assertFalse(_evidence_covered(inferred_currency, "currency"))
        missing_party_countries = extraction.model_copy(
            update={
                "evidence": [
                    item
                    for item in extraction.evidence
                    if item.field not in {"seller_country", "buyer_country"}
                ]
            }
        )
        self.assertFalse(_evidence_covered(missing_party_countries, "trade_type"))

    def test_session_state_invalidates_on_input_change(self):
        state = {
            "extraction": {"x": 1},
            "stage2_result": {"x": 2},
            "workflow_state": {"case_id": "case_old"},
            "confirm_currency_widget": True,
            "stage2_current_cash_widget": "999",
            "company_role_widget": "구매자 · BUYER",
        }
        first = input_signature(
            mode="DEMO",
            company_role="BUYER",
            company_country="KR",
            file_bytes=b"one",
        )
        second = input_signature(
            mode="DEMO",
            company_role="SELLER",
            company_country="KR",
            file_bytes=b"one",
        )
        self.assertFalse(sync_input_signature(state, first))
        self.assertTrue(sync_input_signature(state, second))
        self.assertNotIn("extraction", state)
        self.assertNotIn("stage2_result", state)
        self.assertNotIn("workflow_state", state)
        self.assertNotIn("confirm_currency_widget", state)
        self.assertNotIn("stage2_current_cash_widget", state)
        self.assertEqual(
            state["company_role_widget"],
            "구매자 · BUYER",
        )

    def test_fractional_installment_sequence_is_rejected(self):
        with self.assertRaises(ValueError):
            optional_positive_integer("1.5", "sequence")
        self.assertEqual(
            optional_positive_integer("2", "sequence"),
            2,
        )

    def test_financial_display_formatters_are_readable(self):
        self.assertEqual(
            format_decimal_display("1234567.5", decimal_places=2),
            "1,234,567.50",
        )
        self.assertEqual(format_krw("-2500.4"), "-2,500원")
        self.assertEqual(
            format_foreign("100000", "USD"),
            "100,000.00 USD",
        )
        self.assertEqual(format_ratio("0.725"), "72.5%")

    def test_filename_is_part_of_document_state_signature(self):
        first = input_signature(
            mode="LIVE",
            company_role="BUYER",
            company_country="KR",
            file_bytes=b"same",
            filename="first.pdf",
        )
        second = input_signature(
            mode="LIVE",
            company_role="BUYER",
            company_country="KR",
            file_bytes=b"same",
            filename="second.pdf",
        )
        self.assertNotEqual(first, second)


class DatasetAndEvaluationTests(unittest.TestCase):
    def test_manifest_has_sixteen_synthetic_cases(self):
        rows = [
            json.loads(line)
            for line in (
                ROOT / "dataset" / "manifest.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        synthetic = [
            row
            for row in rows
            if row["document_path"].startswith("dataset/synthetic/")
        ]
        self.assertGreaterEqual(len(synthetic), 16)

    def test_every_synthetic_label_is_fictional_schema(self):
        rows = [
            json.loads(line)
            for line in (
                ROOT / "dataset" / "manifest.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for row in rows:
            label = TradeDocumentExtraction.model_validate_json(
                (ROOT / row["label_path"]).read_text(encoding="utf-8")
            )
            combined = "{} {}".format(
                label.seller_name or "",
                label.buyer_name or "",
            )
            self.assertNotIn("Samsung", combined)
            self.assertNotIn("Hyundai", combined)

    def test_pdf_test_documents_have_legal_effect_banner(self):
        pdfs = list((ROOT / "dataset" / "synthetic").rglob("*.pdf"))
        self.assertTrue(pdfs)
        for path in pdfs:
            page = PdfReader(path).pages[0]
            self.assertTrue(page.images)
            image = page.images[0].image.convert("RGB")
            red_pixels = 0
            for red, green, blue in image.crop((50, 45, 900, 120)).getdata():
                if red > 110 and red > green * 1.6 and red > blue * 1.3:
                    red_pixels += 1
            self.assertGreater(red_pixels, 100)
            label_path = (
                ROOT
                / "dataset"
                / "labels"
                / "{}.json".format(path.stem)
            )
            label = json.loads(label_path.read_text(encoding="utf-8"))
            notice_evidence = [
                item["source_text"]
                for item in label["evidence"]
                if item["field"] == "document_notice"
            ]
            self.assertIn(
                "TEST DOCUMENT - NO LEGAL EFFECT",
                notice_evidence,
            )

    def test_image_test_documents_have_legal_effect_banner(self):
        images = [
            path
            for path in (ROOT / "dataset" / "synthetic").rglob("*")
            if path.suffix.lower() in {".png", ".jpg", ".jpeg"}
        ]
        self.assertTrue(images)
        for path in images:
            with Image.open(path) as source:
                image = source.convert("RGB")
            red_pixels = 0
            for red, green, blue in image.crop((50, 45, 900, 120)).getdata():
                if red > 110 and red > green * 1.6 and red > blue * 1.3:
                    red_pixels += 1
            self.assertGreater(red_pixels, 100, msg=str(path))

    def test_offline_evaluation_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = evaluate(
                manifest_path=ROOT / "dataset" / "manifest.jsonl",
                predictions_dir=(
                    ROOT / "dataset" / "predictions" / "fixture"
                ),
                reports_dir=Path(directory),
            )
            self.assertEqual(summary["cases_evaluated"], 17)
            self.assertEqual(summary["currency_accuracy"], 1.0)
            self.assertEqual(summary["hallucination_rate"], 0.0)
            self.assertEqual(summary["evidence_coverage"], 1.0)
            self.assertTrue((Path(directory) / "eval_report.md").is_file())

    def test_missing_prediction_penalizes_all_metrics(self):
        row = {
            "case_id": "missing_case",
            "label_path": "dataset/labels/invoice_single_currency_001.json",
            "company_country": "KR",
        }
        with tempfile.TemporaryDirectory() as directory:
            summary, failures = evaluate_records(
                manifest_rows=[row],
                predictions_dir=Path(directory),
            )
        self.assertEqual(summary["currency_accuracy"], 0.0)
        self.assertEqual(
            summary["exact_match_accuracy_per_field"]["currency"],
            0.0,
        )
        self.assertEqual(summary["required_field_completion_rate"], 0.0)
        self.assertEqual(summary["document_pass_rate"], 0.0)
        self.assertTrue(
            any(
                item["cause"] == "missing_prediction_file"
                for item in failures
            )
        )

    def test_invalid_prediction_is_isolated_as_failure(self):
        row = {
            "case_id": "invalid_case",
            "label_path": "dataset/labels/invoice_single_currency_001.json",
            "company_country": "KR",
        }
        with tempfile.TemporaryDirectory() as directory:
            prediction = Path(directory) / "invalid_case.json"
            prediction.write_text("{invalid", encoding="utf-8")
            summary, failures = evaluate_records(
                manifest_rows=[row],
                predictions_dir=Path(directory),
            )
        self.assertEqual(summary["cases_evaluated"], 1)
        self.assertEqual(summary["document_pass_rate"], 0.0)
        self.assertTrue(
            any(
                item["cause"] == "invalid_prediction_file"
                for item in failures
            )
        )

    def test_regression_detects_core_drop(self):
        baseline = {
            "core_field_accuracy": {
                "currency": 1,
                "amount_due": 1,
                "required_date": 1,
                "due_date": 1,
                "trade_type": 1,
            },
            "hallucination_rate": 0,
            "document_pass_rate": 1,
            "case_results": {},
        }
        current = dict(baseline)
        current["core_field_accuracy"] = dict(
            baseline["core_field_accuracy"]
        )
        current["core_field_accuracy"]["currency"] = 0.98
        failures = compare_metrics(baseline, current)
        self.assertTrue(any("currency" in item for item in failures))

    def test_finetuning_export_excludes_unapproved_test_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.jsonl"
            excluded = Path(directory) / "excluded.jsonl"
            included_count, excluded_count = export_candidates(
                manifest_path=ROOT / "dataset" / "manifest.jsonl",
                candidate_path=candidate,
                excluded_path=excluded,
            )
            self.assertEqual(included_count, 0)
            self.assertEqual(excluded_count, 17)
            self.assertEqual(candidate.read_text(encoding="utf-8"), "")


class EndToEndTests(unittest.TestCase):
    def test_python_runtime_is_39_or_newer_without_310_syntax_dependency(self):
        self.assertGreaterEqual(sys.version_info[:2], (3, 9))

    def test_offline_end_to_end_demo(self):
        result = run_offline_demo()
        self.assertTrue(result["validation"].stage2_allowed)
        self.assertEqual(len(result["stage2"].scenario_results), 7)
        self.assertEqual(len(result["stage3"].candidates), 3)
        self.assertTrue(result["stage4"].candidates)
        self.assertTrue(result["report"].critique.passed)
        self.assertEqual(
            result["workflow_state"].cashflow.data,
            result["stage2"],
        )
        self.assertEqual(
            [item.stage for item in result["trace"]],
            [
                "intake",
                "market_risk",
                "cashflow",
                "hedge",
                "product_search",
                "report",
            ],
        )

    def test_offline_demo_never_uses_configured_api_key(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-only"},
        ), patch(
            "src.stage5.report_agent.OpenAI",
            side_effect=AssertionError("network client must not be created"),
        ):
            result = run_offline_demo()
        self.assertEqual(
            result["report"].status,
            "DETERMINISTIC_FALLBACK",
        )

    def test_streamlit_one_click_demo_renders_without_exception(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(
            str(ROOT / "app.py"),
            default_timeout=20,
        ).run()
        role_widget = next(
            radio
            for radio in app.radio
            if radio.label == "이 거래에서 우리 회사의 역할"
        )
        role_widget.set_value("판매자 · SELLER").run()
        self.assertEqual(len(app.exception), 0)
        export_demo = next(
            button
            for button in app.button
            if button.label == "수출기업 대표 데모"
        )
        export_demo.click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(
            [tab.label for tab in app.tabs],
            [
                "1  거래 확인",
                "2  환율 가정",
                "3  리스크 진단",
                "4  대응 시뮬레이션",
                "5  공식 상담 정보",
                "6  상담 리포트",
            ],
        )
        self.assertEqual(
            next(
                radio.value
                for radio in app.radio
                if radio.label == "이 거래에서 우리 회사의 역할"
            ),
            "판매자 · SELLER",
        )
        self.assertTrue(
            any(
                "FX_RECEIPT_RISK" in item.value
                for item in app.markdown
            )
        )
        import_demo = next(
            button
            for button in app.button
            if button.label == "수입기업 대표 데모"
        )
        import_demo.click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(
            next(
                radio.value
                for radio in app.radio
                if radio.label == "이 거래에서 우리 회사의 역할"
            ),
            "구매자 · BUYER",
        )
        self.assertTrue(
            any(
                "환율·현금흐름 리스크 검토 보고서" in item.value
                for item in app.markdown
            )
        )
        self.assertTrue(
            any(
                item.label == "고급 · 실행 기록 및 감사 추적"
                for item in app.expander
            )
        )


if __name__ == "__main__":
    unittest.main()
