import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from prompt import get_prompt_version
from schemas import TradeDocumentExtraction
from src.config import Settings
from src.document_intake.extractor import ExtractionRun
from src.document_intake.openai_adapter import ExtractionUsage
from src.document_intake.source_evidence import extract_pdf_page_texts
from src.security.upload_guard import validate_upload
from validators import apply_deterministic_review_state


ROOT = Path(__file__).resolve().parents[2]
PRESENTATION_FIXTURE_ID = "golden_export_contract_v1"
PRESENTATION_DOCUMENT_PATH = (
    ROOT / "dataset" / "golden_demo" / "golden_export_contract.pdf"
)
PRESENTATION_EXTRACTION_PATH = (
    ROOT / "dataset" / "golden_demo" / "expected_extraction.json"
)
PRESENTATION_DEMO_INPUTS_PATH = (
    ROOT / "dataset" / "golden_demo" / "demo_inputs.json"
)


@dataclass(frozen=True)
class RegisteredDocument:
    fixture_id: str
    filename: str
    mime_type: str
    file_bytes: bytes


def presentation_document() -> RegisteredDocument:
    return RegisteredDocument(
        fixture_id=PRESENTATION_FIXTURE_ID,
        filename=PRESENTATION_DOCUMENT_PATH.name,
        mime_type="application/pdf",
        file_bytes=PRESENTATION_DOCUMENT_PATH.read_bytes(),
    )


def presentation_document_sha256() -> str:
    return hashlib.sha256(presentation_document().file_bytes).hexdigest()


def presentation_demo_inputs() -> Dict[str, Any]:
    with PRESENTATION_DEMO_INPUTS_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("등록 데모 입력은 JSON object여야 합니다.")
    return payload


def extract_registered_document(
    *,
    file_bytes: bytes,
    filename: str,
    mime_type: Optional[str],
    company_role: str,
    company_country: str,
    settings: Settings,
) -> Optional[ExtractionRun]:
    """Use a reviewed fixture only when uploaded bytes match exactly.

    The adapter is intentionally limited to presentation or explicit demo
    mode. Unknown bytes return ``None`` and must continue through the live
    extraction adapter.
    """

    if settings.app_env != "presentation" and not settings.demo_mode:
        return None
    registered = presentation_document()
    actual_sha256 = hashlib.sha256(file_bytes).hexdigest()
    registered_sha256 = presentation_document_sha256()
    if actual_sha256 != registered_sha256:
        return None

    upload = validate_upload(
        file_bytes=file_bytes,
        filename=filename,
        claimed_mime_type=mime_type,
        settings=settings,
    )
    raw_extraction = TradeDocumentExtraction.model_validate_json(
        PRESENTATION_EXTRACTION_PATH.read_text(encoding="utf-8")
    )
    extraction, validation = apply_deterministic_review_state(
        raw_extraction,
        company_role=company_role,
        company_country=company_country,
        source_page_texts=extract_pdf_page_texts(file_bytes),
    )
    return ExtractionRun(
        raw_extraction=raw_extraction,
        extraction=extraction,
        validation=validation,
        upload=upload,
        usage=ExtractionUsage(
            model="registered_api_free_fixture",
            prompt_version=get_prompt_version(),
            request_id="registered:{}".format(actual_sha256[:16]),
            latency_seconds=0.0,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            attempts=1,
        ),
    )
