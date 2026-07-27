from dataclasses import dataclass
from typing import Optional

from schemas import TradeDocumentExtraction, ValidationResult
from src.config import Settings
from src.document_intake.openai_adapter import (
    AdapterExtractionResult,
    ExtractionUsage,
    OpenAIAdapterError,
    OpenAIDocumentAdapter,
)
from src.document_intake.normalization import normalize_country_name
from src.security.upload_guard import (
    UploadMetadata,
    UploadValidationError,
    validate_upload,
)
from validators import apply_deterministic_review_state


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractionRun:
    raw_extraction: TradeDocumentExtraction
    extraction: TradeDocumentExtraction
    validation: ValidationResult
    upload: UploadMetadata
    usage: ExtractionUsage


def extract_trade_document_with_metadata(
    *,
    file_bytes: bytes,
    filename: str,
    mime_type: Optional[str],
    company_role: str,
    company_country: str = "KR",
    settings: Optional[Settings] = None,
    adapter: Optional[OpenAIDocumentAdapter] = None,
) -> ExtractionRun:
    if company_role not in {"BUYER", "SELLER"}:
        raise ExtractionError("회사 역할은 BUYER 또는 SELLER여야 합니다.")
    normalized_company_country, _ = normalize_country_name(
        company_country,
        "company_country",
    )
    if (
        normalized_company_country is None
        or len(normalized_company_country) != 2
        or not normalized_company_country.isalpha()
    ):
        raise ExtractionError("회사 국가는 ISO alpha-2 형태여야 합니다.")

    effective_settings = settings or Settings.from_env()
    try:
        upload = validate_upload(
            file_bytes=file_bytes,
            filename=filename,
            claimed_mime_type=mime_type,
            settings=effective_settings,
        )
        effective_adapter = adapter or OpenAIDocumentAdapter(
            settings=effective_settings
        )
        adapter_result: AdapterExtractionResult = effective_adapter.extract(
            file_bytes=file_bytes,
            metadata=upload,
            company_role=company_role,
            company_country=normalized_company_country,
        )
        extraction, validation = apply_deterministic_review_state(
            adapter_result.extraction,
            company_role=company_role,
            company_country=company_country,
        )
        return ExtractionRun(
            raw_extraction=adapter_result.extraction,
            extraction=extraction,
            validation=validation,
            upload=upload,
            usage=adapter_result.usage,
        )
    except (UploadValidationError, OpenAIAdapterError) as exc:
        raise ExtractionError(str(exc)) from exc


def extract_trade_document(
    *,
    file_bytes: bytes,
    filename: str,
    mime_type: Optional[str],
    company_role: str,
    company_country: str = "KR",
    model: Optional[str] = None,
) -> TradeDocumentExtraction:
    settings = Settings.from_env()
    if model:
        settings = Settings(
            openai_api_key=settings.openai_api_key,
            openai_model=model,
            openai_fallback_model=settings.openai_fallback_model,
            openai_report_model=settings.openai_report_model,
            openai_rag_model=settings.openai_rag_model,
            demo_mode=settings.demo_mode,
            enable_live_document_extraction=(
                settings.enable_live_document_extraction
            ),
            enable_official_web_search=settings.enable_official_web_search,
            stage1_mode=settings.stage1_mode,
            stage1_base_url=settings.stage1_base_url,
            stage1_allow_private_endpoints=(
                settings.stage1_allow_private_endpoints
            ),
            stage1_allowed_hosts=settings.stage1_allowed_hosts,
            max_upload_mb=settings.max_upload_mb,
            max_pdf_pages=settings.max_pdf_pages,
            openai_timeout_seconds=settings.openai_timeout_seconds,
            stage1_timeout_seconds=settings.stage1_timeout_seconds,
            official_search_cache_ttl_hours=(
                settings.official_search_cache_ttl_hours
            ),
            official_domains=settings.official_domains,
        )
    return extract_trade_document_with_metadata(
        file_bytes=file_bytes,
        filename=filename,
        mime_type=mime_type,
        company_role=company_role,
        company_country=company_country,
        settings=settings,
    ).extraction
