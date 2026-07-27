import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from scripts.live_smoke_test import main


class LiveSmokeTestTests(unittest.TestCase):
    @patch("scripts.live_smoke_test.Settings.from_env")
    @patch("scripts.live_smoke_test.extract_trade_document_with_metadata")
    @patch("scripts.live_smoke_test.Path.is_file", return_value=True)
    @patch("scripts.live_smoke_test.Path.read_bytes", return_value=b"sample")
    def test_validation_block_returns_failure(
        self,
        unused_read,
        unused_is_file,
        extract,
        settings,
    ):
        settings.return_value = SimpleNamespace(live_extraction_ready=True)
        extract.return_value = SimpleNamespace(
            extraction=SimpleNamespace(document_type="SALES_CONTRACT"),
            validation=SimpleNamespace(
                validation_pass=False,
                issues=[
                    SimpleNamespace(
                        code="MISSING_CORE_EVIDENCE",
                        field="seller_name",
                    )
                ],
            ),
            usage=SimpleNamespace(latency_seconds=1.0),
        )
        with patch(
            "sys.argv",
            [
                "live_smoke_test.py",
                "synthetic.pdf",
            ],
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(), 1)
        self.assertIn("BLOCKED", output.getvalue())
        self.assertIn(
            "MISSING_CORE_EVIDENCE:seller_name",
            output.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
