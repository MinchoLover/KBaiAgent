import hashlib
import json
import mimetypes
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image
from pypdf import PdfReader

from schemas import TradeDocumentExtraction
from scripts.export_finetuning_candidates import export_candidates
from scripts.generate_country_validation_dataset import (
    NOTICE_EN,
    NOTICE_KO,
    NOTICE_PT,
    _cases,
    generate,
)
from src.config import Settings
from src.security.upload_guard import validate_upload


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset" / "country_validation"
MANIFEST = DATASET / "manifest.jsonl"
FIXTURE_PREDICTIONS = DATASET / "predictions" / "fixture"
FORBIDDEN_REAL_NAMES = {
    "samsung",
    "hyundai",
    "kb kookmin",
    "kookmin bank",
    "bank of america",
    "itau",
    "bradesco",
}
SYNTHETIC_NAME_MARKERS = {
    "synthetic",
    "test",
    "fictional",
    "sandbox",
}


def _manifest_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with MANIFEST.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _labels() -> Dict[str, TradeDocumentExtraction]:
    labels: Dict[str, TradeDocumentExtraction] = {}
    for row in _manifest_rows():
        path = ROOT / row["label_path"]
        labels[row["case_id"]] = TradeDocumentExtraction.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    return labels


def _document_image(path: Path) -> Image.Image:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return reader.pages[0].images[0].image.convert("RGB")
    with Image.open(path) as image:
        return image.convert("RGB")


class CountryValidationDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        generate(render_documents=False)

    def test_manifest_has_required_balanced_eight_cases(self):
        rows = _manifest_rows()
        self.assertEqual(len(rows), 8)
        self.assertEqual(
            sum(row["counterparty_country"] == "US" for row in rows),
            4,
        )
        self.assertEqual(
            sum(row["counterparty_country"] == "BR" for row in rows),
            4,
        )
        self.assertEqual(sum(row["trade_type"] == "IMPORT" for row in rows), 4)
        self.assertEqual(sum(row["trade_type"] == "EXPORT" for row in rows), 4)
        self.assertEqual(
            sum(
                row["expected_validation_status"] == "CONDITIONAL_REVIEW"
                for row in rows
            ),
            5,
        )
        self.assertEqual(
            sum(
                row["expected_validation_status"] == "BLOCKED"
                for row in rows
            ),
            3,
        )
        self.assertTrue(all(row["split"] == "test" for row in rows))
        self.assertTrue(all(not row["human_approved"] for row in rows))
        self.assertTrue(all(not row["user_confirmed"] for row in rows))
        self.assertTrue(all(not row["fine_tuning_eligible"] for row in rows))

    def test_documents_labels_and_fixture_predictions_exist_and_validate(self):
        for row in _manifest_rows():
            with self.subTest(case_id=row["case_id"]):
                document_path = ROOT / row["document_path"]
                label_path = ROOT / row["label_path"]
                prediction_path = (
                    FIXTURE_PREDICTIONS
                    / "{}.json".format(row["case_id"])
                )
                self.assertTrue(document_path.is_file())
                self.assertTrue(label_path.is_file())
                self.assertTrue(prediction_path.is_file())
                label = TradeDocumentExtraction.model_validate_json(
                    label_path.read_text(encoding="utf-8")
                )
                prediction_payload = json.loads(
                    prediction_path.read_text(encoding="utf-8")
                )
                prediction = TradeDocumentExtraction.model_validate(
                    prediction_payload["extraction"]
                )
                self.assertEqual(label, prediction)
                self.assertEqual(
                    prediction_payload["metadata"]["mode"],
                    "fixture",
                )
                self.assertTrue(
                    prediction_payload["metadata"]["fixture_only"]
                )

    def test_document_format_mix_and_upload_guard(self):
        rows = _manifest_rows()
        pdf_paths = [
            ROOT / row["document_path"]
            for row in rows
            if Path(row["document_path"]).suffix.lower() == ".pdf"
        ]
        image_paths = [
            ROOT / row["document_path"]
            for row in rows
            if Path(row["document_path"]).suffix.lower() in {".jpg", ".png"}
        ]
        self.assertGreaterEqual(len(pdf_paths), 4)
        self.assertGreaterEqual(len(image_paths), 3)

        settings = Settings(max_upload_mb=15, max_pdf_pages=20)
        for row in rows:
            path = ROOT / row["document_path"]
            mime_type = mimetypes.guess_type(path.name)[0]
            metadata = validate_upload(
                file_bytes=path.read_bytes(),
                filename=path.name,
                claimed_mime_type=mime_type,
                settings=settings,
            )
            self.assertEqual(metadata.filename, path.name)
            self.assertLess(metadata.size_bytes, 15 * 1024 * 1024)

        for path in pdf_paths:
            reader = PdfReader(str(path))
            self.assertEqual(len(reader.pages), 1)
            self.assertEqual((reader.pages[0].extract_text() or "").strip(), "")
            self.assertGreaterEqual(len(reader.pages[0].images), 1)

    def test_all_parties_are_obviously_fictional(self):
        for case_id, label in _labels().items():
            for value in (label.seller_name, label.buyer_name):
                self.assertIsNotNone(value)
                normalized = str(value).lower()
                with self.subTest(case_id=case_id, value=value):
                    self.assertTrue(
                        any(
                            marker in normalized
                            for marker in SYNTHETIC_NAME_MARKERS
                        )
                    )
                    self.assertFalse(
                        any(name in normalized for name in FORBIDDEN_REAL_NAMES)
                    )

        logical_text = "\n".join(
            line
            for spec in _cases()
            for line in spec["lines"]
        ).lower()
        self.assertFalse(
            any(name in logical_text for name in FORBIDDEN_REAL_NAMES)
        )
        for disallowed in (
            "account number",
            "tax id",
            "business registration",
            "signature:",
            "phone:",
            "address:",
        ):
            self.assertNotIn(disallowed, logical_text)

    def test_notices_are_in_ground_truth_and_visually_rendered(self):
        labels = _labels()
        for spec in _cases():
            case_id = spec["case_id"]
            notice_sources = {
                item.source_text
                for item in labels[case_id].evidence
                if item.field == "document_notice"
            }
            self.assertIn(NOTICE_EN, notice_sources)
            self.assertIn(NOTICE_KO, notice_sources)
            if spec["country"] == "BR":
                self.assertIn(NOTICE_PT, notice_sources)

            path = (
                DATASET
                / "documents"
                / "{}{}".format(case_id, spec["extension"])
            )
            image = _document_image(path)
            top = image.crop((0, 0, image.width, image.height // 4))
            red_pixels = sum(
                1
                for red, green, blue in top.getdata()
                if red > 80 and red > green + 18 and red > blue + 12
            )
            self.assertGreater(red_pixels, 100)

    def test_every_evidence_quote_matches_rendered_logical_source(self):
        labels = _labels()
        for spec in _cases():
            rendered_sources = set(spec["lines"])
            rendered_sources.update({NOTICE_EN, NOTICE_KO})
            if spec["country"] == "BR":
                rendered_sources.add(NOTICE_PT)
            for item in labels[spec["case_id"]].evidence:
                with self.subTest(
                    case_id=spec["case_id"],
                    field=item.field,
                    source=item.source_text,
                ):
                    self.assertIn(item.source_text, rendered_sources)

    def test_core_non_null_fields_have_field_evidence(self):
        minimum_fields = {
            "seller_name",
            "seller_country",
            "buyer_name",
            "buyer_country",
            "amount_due",
            "document_notice",
        }
        labels = _labels()
        for case_id, label in labels.items():
            evidence_fields = {item.field for item in label.evidence}
            required = set(minimum_fields)
            for field in (
                "currency",
                "grand_total",
                "issue_date",
                "contract_date",
                "explicit_due_date",
                "derived_due_date",
                "payment_terms",
            ):
                if getattr(label, field) is not None:
                    required.add(field)
            if label.installments:
                required.add("installments")
            with self.subTest(case_id=case_id):
                self.assertTrue(required.issubset(evidence_fields))

    def test_split_payment_amounts_and_unresolved_event_dates(self):
        labels = _labels()
        for case_id in (
            "us_import_split_scan_001",
            "br_import_advance_photo_002",
            "br_export_mixed_split_scan_006",
        ):
            label = labels[case_id]
            total = sum(
                Decimal(str(item.amount))
                for item in label.installments
                if item.amount is not None
            )
            self.assertEqual(total, Decimal(str(label.amount_due)))

        net_60 = labels["us_export_net60_scan_003"]
        self.assertIsNone(net_60.explicit_due_date)
        self.assertEqual(net_60.derived_due_date, "2026-10-02")

        event_based = labels["br_export_bl_event_photo_004"]
        self.assertIsNone(event_based.explicit_due_date)
        self.assertIsNone(event_based.derived_due_date)

        mixed = labels["br_export_mixed_split_scan_006"]
        self.assertEqual(mixed.installments[0].due_date, "2026-08-18")
        self.assertIsNone(mixed.installments[1].due_date)
        self.assertIsNone(mixed.explicit_due_date)
        self.assertIsNone(mixed.derived_due_date)

    def test_missing_currency_balance_due_and_occluded_due_labels(self):
        labels = _labels()
        missing_currency = labels["us_import_missing_currency_photo_007"]
        self.assertIsNone(missing_currency.currency)
        self.assertIn("currency", missing_currency.missing_required_fields)

        balance_due = labels["us_import_balance_scan_005"]
        self.assertEqual(balance_due.grand_total, "105000.00")
        self.assertEqual(balance_due.amount_due, "80000.00")
        self.assertNotEqual(balance_due.grand_total, balance_due.amount_due)

        occluded = labels["br_export_occluded_due_photo_008"]
        self.assertIsNone(occluded.explicit_due_date)
        self.assertIsNone(occluded.derived_due_date)
        self.assertIn("due_date", occluded.missing_required_fields)

    def test_test_split_is_excluded_from_fine_tuning(self):
        temp_root = ROOT / "temp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=str(temp_root),
            prefix="country-ft-",
        ) as temp_dir:
            included, excluded = export_candidates(
                manifest_path=MANIFEST,
                candidate_path=Path(temp_dir) / "candidates.jsonl",
                excluded_path=Path(temp_dir) / "excluded.jsonl",
            )
        self.assertEqual(included, 0)
        self.assertEqual(excluded, 8)

    def test_fixture_offline_evaluator_cli(self):
        temp_root = ROOT / "temp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=str(temp_root),
            prefix="country-eval-",
        ) as temp_dir:
            command = [
                sys.executable,
                "scripts/evaluate_extraction.py",
                "--mode",
                "offline",
                "--manifest",
                "dataset/country_validation/manifest.jsonl",
                "--predictions-dir",
                "dataset/country_validation/predictions/fixture",
                "--reports-dir",
                str(Path(temp_dir).relative_to(ROOT)),
            ]
            completed = subprocess.run(
                command,
                cwd=str(ROOT),
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg="{}\n{}".format(completed.stdout, completed.stderr),
            )
            summary = json.loads(
                (Path(temp_dir) / "eval_summary.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(summary["cases_evaluated"], 8)
        self.assertEqual(summary["currency_accuracy"], 1.0)
        self.assertEqual(summary["amount_exact_accuracy"], 1.0)
        self.assertEqual(summary["hallucination_rate"], 0.0)
        self.assertEqual(summary["document_pass_rate"], 0.5)
        failed_cases = {
            case_id
            for case_id, result in summary["case_results"].items()
            if not result["passed"]
        }
        self.assertEqual(
            failed_cases,
            {
                "br_export_bl_event_photo_004",
                "br_export_mixed_split_scan_006",
                "us_import_missing_currency_photo_007",
                "br_export_occluded_due_photo_008",
            },
        )

    def test_generation_is_byte_deterministic_and_contains_no_secrets(self):
        tracked_paths = sorted(
            path
            for path in DATASET.rglob("*")
            if path.is_file() and path.name != "README.md"
        )

        def digests() -> Dict[str, str]:
            return {
                path.relative_to(DATASET).as_posix(): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in tracked_paths
            }

        before = digests()
        generate(render_documents=True)
        self.assertEqual(before, digests())

        forbidden_tokens = (
            b"sk-proj-",
            b"OPENAI_API_KEY",
            b"OPEN_AI_API_KEY",
            b"KOREAEXIM_KEY",
            b"BEGIN PRIVATE KEY",
        )
        for path in tracked_paths:
            if path.suffix.lower() not in {".json", ".jsonl", ".md"}:
                continue
            payload = path.read_bytes()
            with self.subTest(path=path.name):
                self.assertFalse(
                    any(token in payload for token in forbidden_tokens)
                )


if __name__ == "__main__":
    unittest.main()
