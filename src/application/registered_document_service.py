import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from prompt import get_prompt_version
from schemas import TradeDocumentExtraction
from src.config import Settings
from src.document_intake.extractor import (
    ExtractionError,
    ExtractionRun,
    LiveDocumentAnalysisError,
    extract_trade_document_with_metadata,
)
from src.document_intake.openai_adapter import (
    ExtractionUsage,
    OpenAIDocumentAdapter,
)
from src.document_intake.source_evidence import extract_pdf_page_texts
from src.domain.document_analysis_models import (
    AnalysisMode,
    DocumentAnalysisProvenance,
    DocumentSource,
    FALLBACK_WARNING_CODE,
    GOLDEN_SAMPLE,
    LIVE_API,
    USER_UPLOAD,
    VERIFIED_FIXTURE,
)
from src.document_intake.party_matching import (
    match_company_role_from_verified_parties,
)
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
    fallback_used: bool = False,
) -> Optional[ExtractionRun]:
    """Load the reviewed Golden fixture only for exact registered bytes."""

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
    source_page_texts = extract_pdf_page_texts(file_bytes)
    extraction, validation = apply_deterministic_review_state(
        raw_extraction,
        company_role=company_role,
        company_country=company_country,
        source_page_texts=source_page_texts,
    )
    role_match = match_company_role_from_verified_parties(
        extraction,
        company_country,
    )
    auto_matched_role = None
    if role_match is not None and role_match.role != company_role:
        extraction, validation = apply_deterministic_review_state(
            raw_extraction,
            company_role=role_match.role,
            company_country=company_country,
            source_page_texts=source_page_texts,
        )
        auto_matched_role = role_match.role
    return ExtractionRun(
        raw_extraction=raw_extraction,
        extraction=extraction,
        validation=validation,
        upload=upload,
        usage=ExtractionUsage(
            model="verified_golden_fixture",
            prompt_version=get_prompt_version(),
            request_id="verified_fixture:{}".format(actual_sha256[:16]),
            latency_seconds=0.0,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            attempts=1,
        ),
        auto_matched_company_role=auto_matched_role,
        provenance=DocumentAnalysisProvenance(
            document_source=GOLDEN_SAMPLE,
            analysis_mode=(LIVE_API if fallback_used else VERIFIED_FIXTURE),
            analysis_source=VERIFIED_FIXTURE,
            model="verified_golden_fixture",
            generated_at=datetime.now(timezone.utc).isoformat(),
            fallback_used=fallback_used,
            warnings=(
                [FALLBACK_WARNING_CODE]
                if fallback_used
                else []
            ),
        ),
    )


def analyze_document(
    *,
    file_bytes: bytes,
    filename: str,
    mime_type: Optional[str],
    company_role: str,
    company_country: str,
    document_source: DocumentSource,
    analysis_mode: AnalysisMode,
    settings: Settings,
    adapter: Optional[OpenAIDocumentAdapter] = None,
) -> ExtractionRun:
    """Analyze live first and fall back only for the registered Golden PDF."""

    if document_source not in {GOLDEN_SAMPLE, USER_UPLOAD}:
        raise ExtractionError("지원하지 않는 입력 문서 source입니다.")
    if analysis_mode not in {LIVE_API, VERIFIED_FIXTURE}:
        raise ExtractionError("지원하지 않는 문서 분석 방식입니다.")

    is_registered_golden = (
        hashlib.sha256(file_bytes).hexdigest()
        == presentation_document_sha256()
    )
    if document_source == GOLDEN_SAMPLE and not is_registered_golden:
        raise ExtractionError(
            "Golden 수출 샘플의 문서 identity가 일치하지 않습니다."
        )
    if analysis_mode == VERIFIED_FIXTURE:
        if document_source != GOLDEN_SAMPLE:
            raise ExtractionError(
                "검증된 fixture는 Golden 수출 샘플에만 사용할 수 있습니다."
            )
        fixture_run = extract_registered_document(
            file_bytes=file_bytes,
            filename=filename,
            mime_type=mime_type,
            company_role=company_role,
            company_country=company_country,
            settings=settings,
        )
        if fixture_run is None:
            raise ExtractionError(
                "검증된 Golden fixture와 문서가 일치하지 않습니다."
            )
        return fixture_run

    try:
        return extract_trade_document_with_metadata(
            file_bytes=file_bytes,
            filename=filename,
            mime_type=mime_type,
            company_role=company_role,
            company_country=company_country,
            document_source=document_source,
            settings=settings,
            adapter=adapter,
        )
    except LiveDocumentAnalysisError:
        if document_source != GOLDEN_SAMPLE:
            raise
        fallback_run = extract_registered_document(
            file_bytes=file_bytes,
            filename=filename,
            mime_type=mime_type,
            company_role=company_role,
            company_country=company_country,
            settings=settings,
            fallback_used=True,
        )
        if fallback_run is None:
            raise
        return fallback_run
