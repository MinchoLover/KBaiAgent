import io
import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from openai import OpenAI

from sample_data import sample_extraction
from src.config import Settings
from src.document_intake.openai_adapter import (
    AdapterExtractionResult,
    ExtractionUsage,
    OpenAIAdapterError,
    OpenAIDocumentAdapter,
    build_document_input_item,
)
from src.document_intake.extractor import (
    ExtractionError,
    extract_trade_document_with_metadata,
)
from src.security.upload_guard import (
    UploadMetadata,
    UploadValidationError,
    sanitize_filename,
    validate_upload,
)


ROOT = Path(__file__).resolve().parents[1]


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(buffer, "PNG")
    return buffer.getvalue()


class UploadGuardTests(unittest.TestCase):
    def test_png_magic_and_mime(self):
        result = validate_upload(
            file_bytes=png_bytes(),
            filename="invoice.png",
            claimed_mime_type="image/png",
        )
        self.assertEqual(result.mime_type, "image/png")
        self.assertIsNone(result.page_count)

    def test_pdf_page_count(self):
        data = (ROOT / "samples" / "demo_export_invoice.pdf").read_bytes()
        result = validate_upload(
            file_bytes=data,
            filename="invoice.pdf",
            claimed_mime_type="application/pdf",
        )
        self.assertGreaterEqual(result.page_count, 1)

    def test_extension_magic_mismatch(self):
        with self.assertRaises(UploadValidationError):
            validate_upload(
                file_bytes=png_bytes(),
                filename="invoice.pdf",
                claimed_mime_type="application/pdf",
            )

    def test_claimed_mime_mismatch(self):
        with self.assertRaises(UploadValidationError):
            validate_upload(
                file_bytes=png_bytes(),
                filename="invoice.png",
                claimed_mime_type="image/jpeg",
            )

    def test_archive_rejected(self):
        with self.assertRaises(UploadValidationError):
            validate_upload(
                file_bytes=b"PK\x03\x04archive",
                filename="documents.zip",
                claimed_mime_type="application/zip",
            )

    def test_oversized_file_rejected(self):
        settings = Settings(max_upload_mb=0)
        with self.assertRaises(UploadValidationError):
            validate_upload(
                file_bytes=png_bytes(),
                filename="invoice.png",
                claimed_mime_type="image/png",
                settings=settings,
            )

    def test_page_limit_rejected(self):
        data = (ROOT / "samples" / "demo_export_invoice.pdf").read_bytes()
        settings = Settings(max_pdf_pages=0)
        with self.assertRaises(UploadValidationError):
            validate_upload(
                file_bytes=data,
                filename="invoice.pdf",
                claimed_mime_type="application/pdf",
                settings=settings,
            )

    def test_corrupt_image_rejected(self):
        with self.assertRaises(UploadValidationError):
            validate_upload(
                file_bytes=b"\x89PNG\r\n\x1a\nbroken",
                filename="broken.png",
                claimed_mime_type="image/png",
            )

    def test_excessive_image_dimensions_rejected(self):
        with patch(
            "src.security.upload_guard.MAX_IMAGE_PIXELS",
            100,
        ):
            with self.assertRaises(UploadValidationError):
                validate_upload(
                    file_bytes=png_bytes(),
                    filename="large-dimensions.png",
                    claimed_mime_type="image/png",
                )

    def test_filename_sanitized(self):
        self.assertEqual(
            sanitize_filename("../../secret invoice?.pdf"),
            "secret_invoice_.pdf",
        )


class _FakeParse:
    def __init__(self, failures: int = 0):
        self.failures = failures
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) <= self.failures:
            raise RuntimeError("temporary failure")
        return SimpleNamespace(
            output_parsed=sample_extraction(),
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
            ),
            _request_id="request-test",
        )


class _FixedExtractionAdapter:
    def extract(self, **kwargs):
        del kwargs
        return AdapterExtractionResult(
            extraction=sample_extraction(),
            usage=ExtractionUsage(
                model="test-model",
                prompt_version="test",
                request_id="test-request",
                latency_seconds=0.0,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                attempts=1,
            ),
        )


class AdapterTests(unittest.TestCase):
    def test_installed_sdk_supports_responses_parse_contract(self):
        client = OpenAI(
            api_key="test-only",
            max_retries=0,
        )
        parameters = inspect.signature(client.responses.parse).parameters
        self.assertIn("text_format", parameters)
        self.assertIn("input", parameters)
        self.assertIn("timeout", parameters)

    def test_invalid_company_country_is_rejected_before_api_call(self):
        with self.assertRaises(ExtractionError):
            extract_trade_document_with_metadata(
                file_bytes=b"not-used",
                filename="invoice.png",
                mime_type="image/png",
                company_role="BUYER",
                company_country="1!",
                settings=Settings(),
            )

    def test_image_uses_input_image(self):
        metadata = UploadMetadata(
            filename="invoice.png",
            mime_type="image/png",
            size_bytes=3,
            sha256="x",
            page_count=None,
        )
        item = build_document_input_item(
            file_bytes=b"abc",
            metadata=metadata,
        )
        self.assertEqual(item["type"], "input_image")
        self.assertTrue(item["image_url"].startswith("data:image/png;base64,"))

    def test_pdf_uses_input_file(self):
        metadata = UploadMetadata(
            filename="invoice.pdf",
            mime_type="application/pdf",
            size_bytes=3,
            sha256="x",
            page_count=1,
        )
        item = build_document_input_item(
            file_bytes=b"abc",
            metadata=metadata,
        )
        self.assertEqual(item["type"], "input_file")
        self.assertNotIn("detail", item)

    def test_no_api_key_has_safe_error(self):
        adapter = OpenAIDocumentAdapter(settings=Settings())
        metadata = UploadMetadata(
            filename="invoice.png",
            mime_type="image/png",
            size_bytes=3,
            sha256="x",
            page_count=None,
        )
        with self.assertRaises(OpenAIAdapterError):
            adapter.extract(
                file_bytes=b"abc",
                metadata=metadata,
                company_role="BUYER",
                company_country="KR",
            )

    def test_retry_then_success_uses_structured_parse(self):
        fake_parse = _FakeParse(failures=1)
        client = SimpleNamespace(
            responses=SimpleNamespace(parse=fake_parse.parse)
        )
        settings = Settings(
            openai_api_key="test-only",
            openai_model="primary",
            openai_fallback_model="fallback",
        )
        adapter = OpenAIDocumentAdapter(settings=settings, client=client)
        metadata = UploadMetadata(
            filename="invoice.png",
            mime_type="image/png",
            size_bytes=3,
            sha256="x",
            page_count=None,
        )
        result = adapter.extract(
            file_bytes=b"abc",
            metadata=metadata,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertEqual(result.usage.attempts, 2)
        self.assertEqual(
            fake_parse.calls[-1]["text_format"].__name__,
            "TradeDocumentExtraction",
        )
        self.assertFalse(fake_parse.calls[-1]["store"])

    def test_fallback_model_after_two_primary_failures(self):
        fake_parse = _FakeParse(failures=2)
        client = SimpleNamespace(
            responses=SimpleNamespace(parse=fake_parse.parse)
        )
        adapter = OpenAIDocumentAdapter(
            settings=Settings(
                openai_api_key="test-only",
                openai_model="primary",
                openai_fallback_model="fallback",
            ),
            client=client,
        )
        metadata = UploadMetadata(
            filename="invoice.png",
            mime_type="image/png",
            size_bytes=3,
            sha256="x",
            page_count=None,
        )
        result = adapter.extract(
            file_bytes=b"abc",
            metadata=metadata,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertEqual(result.usage.model, "fallback")
        self.assertEqual(result.usage.attempts, 3)

    def test_live_image_requires_independent_evidence_override(self):
        run = extract_trade_document_with_metadata(
            file_bytes=png_bytes(),
            filename="invoice.png",
            mime_type="image/png",
            company_role="BUYER",
            company_country="KR",
            settings=Settings(),
            adapter=_FixedExtractionAdapter(),
        )

        self.assertFalse(run.validation.stage2_allowed)
        self.assertTrue(
            any(
                item.code == "EVIDENCE_UNVERIFIABLE"
                for item in run.validation.issues
            )
        )
        self.assertIn(
            "OCR_REQUIRED",
            {item.code for item in run.validation.issues},
        )


if __name__ == "__main__":
    unittest.main()
