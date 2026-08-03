import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.evaluate_extraction import (
    _base_run_metadata,
    _live_run_directories,
    _load_extraction,
    evaluate_records,
    load_manifest,
    main,
    run_live_predictions,
)
from src.config import Settings


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "dataset" / "country_validation" / "manifest.jsonl"


def _settings(key: str = "test-only-secret") -> Settings:
    return Settings(
        openai_api_key=key,
        openai_model="benchmark-model",
        openai_fallback_model="benchmark-fallback",
        enable_live_document_extraction=True,
    )


def _fake_run(row):
    extraction, unused_metadata = _load_extraction(
        ROOT / row["label_path"]
    )
    del unused_metadata
    return SimpleNamespace(
        raw_extraction=extraction,
        extraction=extraction,
        validation=SimpleNamespace(
            validation_pass=False,
            stage2_allowed=False,
            issues=[
                SimpleNamespace(
                    code="OCR_REQUIRED",
                    field=None,
                    severity="HIGH",
                )
            ],
        ),
        upload=SimpleNamespace(sha256="synthetic-document-sha"),
        usage=SimpleNamespace(
            model="benchmark-model",
            prompt_version="1.6.0",
            request_id="request-safe",
            latency_seconds=1.25,
            input_tokens=100,
            output_tokens=40,
            total_tokens=140,
            attempts=1,
        ),
    )


class LiveBenchmarkGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        (ROOT / "temp").mkdir(parents=True, exist_ok=True)

    def _main_with_args(self, arguments):
        output = io.StringIO()
        with patch("sys.argv", ["evaluate_extraction.py"] + arguments):
            with redirect_stdout(output):
                return_code = main()
        return return_code, output.getvalue()

    @patch("scripts.evaluate_extraction.run_live_predictions")
    def test_live_mode_requires_explicit_confirmation(self, live_runner):
        return_code, output = self._main_with_args(
            [
                "--mode",
                "live",
                "--manifest",
                "dataset/country_validation/manifest.jsonl",
                "--max-cases",
                "1",
                "--run-id",
                "gate-no-confirm",
            ]
        )
        self.assertEqual(return_code, 2)
        self.assertIn("--confirm-live", output)
        live_runner.assert_not_called()

    @patch("scripts.evaluate_extraction.run_live_predictions")
    def test_live_mode_requires_positive_max_cases(self, live_runner):
        for extra in ([], ["--max-cases", "0"], ["--max-cases", "-1"]):
            with self.subTest(extra=extra):
                return_code, output = self._main_with_args(
                    [
                        "--mode",
                        "live",
                        "--manifest",
                        "dataset/country_validation/manifest.jsonl",
                        "--confirm-live",
                        "--run-id",
                        "gate-max-cases",
                    ]
                    + extra
                )
                self.assertEqual(return_code, 2)
                self.assertIn("--max-cases", output)
        live_runner.assert_not_called()

    @patch("scripts.evaluate_extraction.load_dotenv")
    @patch("scripts.evaluate_extraction.Settings.from_env")
    def test_missing_key_reports_readiness_without_value(
        self,
        settings_from_env,
        load_dotenv,
    ):
        settings_from_env.return_value = Settings(
            openai_api_key=None,
            enable_live_document_extraction=True,
        )
        with tempfile.TemporaryDirectory(
            dir=str(ROOT / "temp"),
            prefix="live-key-gate-",
        ) as directory:
            relative = Path(directory).relative_to(ROOT)
            return_code, output = self._main_with_args(
                [
                    "--mode",
                    "live",
                    "--manifest",
                    "dataset/country_validation/manifest.jsonl",
                    "--confirm-live",
                    "--max-cases",
                    "1",
                    "--run-id",
                    "missing-key",
                    "--predictions-dir",
                    str(relative / "predictions"),
                    "--reports-dir",
                    str(relative / "reports"),
                ]
            )
        self.assertEqual(return_code, 2)
        self.assertIn("READY_FOR_AUTHORIZED_LIVE_RUN", output)
        self.assertIn("configured: false", output)
        self.assertNotIn("test-only-secret", output)
        load_dotenv.assert_called_once()

    def test_live_output_cannot_target_fixture_or_existing_run(self):
        fixture = (
            ROOT
            / "dataset"
            / "country_validation"
            / "predictions"
            / "fixture"
        )
        with self.assertRaises(ValueError):
            _live_run_directories(fixture, ROOT / "reports", "fixture")

        with tempfile.TemporaryDirectory(
            dir=str(ROOT / "temp"),
            prefix="live-existing-",
        ) as directory:
            root = Path(directory)
            (root / "predictions" / "baseline-v1").mkdir(parents=True)
            with self.assertRaises(FileExistsError):
                _live_run_directories(
                    root / "predictions",
                    root / "reports",
                    "baseline-v1",
                )

    def test_live_artifact_roots_are_git_ignored(self):
        paths = [
            "dataset/country_validation/predictions/live/run/case.json",
            "reports/country_validation_live/run/eval_summary.json",
        ]
        for path in paths:
            with self.subTest(path=path):
                completed = subprocess.run(
                    ["git", "check-ignore", "--quiet", path],
                    cwd=str(ROOT),
                    check=False,
                )
                self.assertEqual(completed.returncode, 0)

    def test_manifest_is_explicitly_synthetic_test_only(self):
        rows = load_manifest(MANIFEST)
        self.assertEqual(len(rows), 9)
        self.assertTrue(all(row["split"] == "test" for row in rows))
        self.assertTrue(
            all(row["fine_tuning_eligible"] is False for row in rows)
        )
        self.assertTrue(
            all(row["synthetic_document"] is True for row in rows)
        )
        self.assertTrue(
            all(row["real_customer_document"] is False for row in rows)
        )
        text_case = next(
            row
            for row in rows
            if row["case_id"] == "us_export_net60_text_009"
        )
        self.assertTrue(text_case["text_layer_expected"])
        self.assertFalse(text_case["registered_api_free"])
        self.assertFalse(text_case["fixture_prediction"])


class LiveBenchmarkExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        (ROOT / "temp").mkdir(parents=True, exist_ok=True)
        cls.rows = load_manifest(MANIFEST)

    @patch(
        "scripts.evaluate_extraction.extract_trade_document_with_metadata"
    )
    def test_live_prediction_omits_raw_model_response(self, extract):
        extract.return_value = _fake_run(self.rows[0])
        with tempfile.TemporaryDirectory(
            dir=str(ROOT / "temp"),
            prefix="live-output-",
        ) as directory:
            predictions = Path(directory) / "predictions"
            outcomes = run_live_predictions(
                manifest_rows=[self.rows[0]],
                predictions_dir=predictions,
                settings=_settings(),
                run_id="safe-output",
                max_cases=1,
            )
            payload = json.loads(
                (predictions / "{}.json".format(self.rows[0]["case_id"]))
                .read_text(encoding="utf-8")
            )
        self.assertEqual(outcomes[0]["status"], "SUCCESS")
        self.assertNotIn("raw_extraction", payload)
        self.assertNotIn("raw_response", payload)
        self.assertFalse(
            payload["metadata"]["raw_model_response_recorded"]
        )
        serialized = json.dumps(payload)
        self.assertNotIn("test-only-secret", serialized)
        self.assertNotIn("authorization", serialized.lower())

    @patch(
        "scripts.evaluate_extraction.extract_trade_document_with_metadata"
    )
    def test_case_failure_and_timeout_are_isolated_and_counted(
        self,
        extract,
    ):
        extract.side_effect = [
            _fake_run(self.rows[0]),
            TimeoutError("simulated timeout without payload"),
        ]
        with tempfile.TemporaryDirectory(
            dir=str(ROOT / "temp"),
            prefix="live-partial-",
        ) as directory:
            predictions = Path(directory) / "predictions"
            outcomes = run_live_predictions(
                manifest_rows=self.rows[:2],
                predictions_dir=predictions,
                settings=_settings(),
                run_id="partial-timeout",
                max_cases=2,
            )
            summary, unused_failures = evaluate_records(
                manifest_rows=self.rows[:2],
                predictions_dir=predictions,
                evaluation_mode="LIVE",
                run_metadata={
                    "run_id": "partial-timeout",
                    "requested_model": "benchmark-model",
                },
            )
            del unused_failures
            failed_payload = json.loads(
                (
                    predictions
                    / "{}.json".format(self.rows[1]["case_id"])
                ).read_text(encoding="utf-8")
            )
        self.assertEqual(
            [item["status"] for item in outcomes],
            ["SUCCESS", "TIMEOUT"],
        )
        self.assertEqual(
            summary["operational_metrics"]["success_count"],
            1,
        )
        self.assertEqual(
            summary["operational_metrics"]["failed_count"],
            1,
        )
        self.assertEqual(
            summary["operational_metrics"]["timeout_count"],
            1,
        )
        self.assertEqual(failed_payload["metadata"]["status"], "TIMEOUT")
        self.assertNotIn("simulated timeout", json.dumps(failed_payload))

    def test_fixture_and_live_metadata_are_distinct(self):
        fixture_payload = json.loads(
            (
                ROOT
                / "dataset"
                / "country_validation"
                / "predictions"
                / "fixture"
                / "{}.json".format(self.rows[0]["case_id"])
            ).read_text(encoding="utf-8")
        )
        metadata = fixture_payload["metadata"]
        self.assertEqual(metadata["evaluation_mode"], "FIXTURE")
        self.assertFalse(metadata["model_accuracy_claim_allowed"])
        self.assertEqual(
            metadata["purpose"],
            "EVALUATOR_PIPELINE_VALIDATION",
        )

    def test_run_metadata_records_version_without_secret(self):
        with tempfile.TemporaryDirectory(
            dir=str(ROOT / "temp"),
            prefix="live-metadata-",
        ) as directory:
            root = Path(directory)
            metadata = _base_run_metadata(
                manifest_path=MANIFEST,
                manifest_rows=self.rows,
                selected_rows=self.rows[:2],
                predictions_dir=root / "predictions" / "run",
                reports_dir=root / "reports" / "run",
                settings=_settings(),
                run_id="metadata-test",
                baseline_version="baseline-v1",
            )
        self.assertEqual(metadata["requested_model"], "benchmark-model")
        self.assertEqual(len(metadata["git_commit_sha"]), 40)
        self.assertEqual(len(metadata["manifest_sha256"]), 64)
        self.assertEqual(len(metadata["evaluator_sha256"]), 64)
        self.assertEqual(len(metadata["extraction_prompt_sha256"]), 64)
        self.assertEqual(metadata["selected_case_count"], 2)
        serialized = json.dumps(metadata)
        self.assertNotIn("test-only-secret", serialized)
        self.assertNotIn("authorization", serialized.lower())
        self.assertFalse(metadata["api_key_value_recorded"])
        self.assertFalse(metadata["raw_api_payload_recorded"])

    def test_fixture_metrics_keep_missing_currency_and_event_date_null(self):
        predictions = (
            ROOT
            / "dataset"
            / "country_validation"
            / "predictions"
            / "fixture"
        )
        summary, unused_failures = evaluate_records(
            manifest_rows=self.rows,
            predictions_dir=predictions,
            evaluation_mode="FIXTURE",
        )
        del unused_failures
        self.assertEqual(summary["evaluation_mode"], "FIXTURE")
        self.assertFalse(summary["model_accuracy_claim_allowed"])
        self.assertEqual(
            summary["safety_metrics"][
                "unsupported_currency_guess_count"
            ],
            0,
        )
        self.assertEqual(
            summary["payment_term_metrics"][
                "unknown_due_date_abstention_accuracy"
            ],
            1.0,
        )
        self.assertEqual(
            summary["payment_term_metrics"][
                "event_based_condition_preservation_accuracy"
            ],
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
