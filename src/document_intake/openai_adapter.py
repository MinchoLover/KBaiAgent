import base64
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from schemas import TradeDocumentExtraction
from src.config import Settings
from src.document_intake.prompt_builder import build_prompt_bundle
from src.security.upload_guard import UploadMetadata


class OpenAIAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractionUsage:
    model: str
    prompt_version: str
    request_id: str
    latency_seconds: float
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int]
    attempts: int


@dataclass(frozen=True)
class AdapterExtractionResult:
    extraction: TradeDocumentExtraction
    usage: ExtractionUsage


def _data_uri(file_bytes: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(file_bytes).decode("ascii")
    return "data:{};base64,{}".format(mime_type, encoded)


def build_document_input_item(
    *,
    file_bytes: bytes,
    metadata: UploadMetadata,
) -> Dict[str, Any]:
    data_uri = _data_uri(file_bytes, metadata.mime_type)
    if metadata.mime_type == "application/pdf":
        return {
            "type": "input_file",
            "filename": metadata.filename,
            "file_data": data_uri,
        }
    return {
        "type": "input_image",
        "image_url": data_uri,
        "detail": "high",
    }


def _usage_value(usage: Any, field: str) -> Optional[int]:
    value = getattr(usage, field, None)
    return int(value) if value is not None else None


def _friendly_api_error(exc: Exception, settings: Settings) -> str:
    error_text = str(exc).lower()
    if "model" in error_text and (
        "not found" in error_text
        or "does not exist" in error_text
        or "access" in error_text
    ):
        return (
            "설정한 모델을 사용할 수 없습니다. OPENAI_MODEL 또는 "
            "OPENAI_FALLBACK_MODEL을 계정에서 사용 가능한 vision/Structured "
            "Outputs 모델 ID로 설정하세요."
        )
    if "api key" in error_text or "authentication" in error_text:
        return (
            "OpenAI 인증에 실패했습니다. 서버의 OPENAI_API_KEY 설정을 "
            "확인하세요."
        )
    if "timeout" in error_text:
        return "문서 분석 요청 시간이 초과되었습니다. 잠시 후 다시 시도하세요."
    return (
        "OpenAI 문서 분석에 실패했습니다. 원문이나 비밀값은 로그에 "
        "남기지 않았습니다."
    )


class OpenAIDocumentAdapter:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[Any] = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        if client is not None:
            self.client = client
        elif self.settings.openai_api_key:
            self.client = OpenAI(
                api_key=self.settings.openai_api_key,
                timeout=self.settings.openai_timeout_seconds,
                max_retries=0,
            )
        else:
            self.client = None

    def _models_to_try(self) -> List[str]:
        primary = self.settings.openai_model
        fallback = self.settings.openai_fallback_model
        models = [primary, primary]
        if fallback and fallback != primary:
            models.append(fallback)
        return models

    def extract(
        self,
        *,
        file_bytes: bytes,
        metadata: UploadMetadata,
        company_role: str,
        company_country: str,
    ) -> AdapterExtractionResult:
        if not self.settings.openai_api_key or self.client is None:
            raise OpenAIAdapterError(
                "OPENAI_API_KEY가 없어 실제 추출을 실행할 수 없습니다. "
                "데모 모드를 사용하세요."
            )
        if not self.settings.enable_live_document_extraction:
            raise OpenAIAdapterError(
                "ENABLE_LIVE_DOCUMENT_EXTRACTION=false로 설정되어 있습니다."
            )

        prompt_bundle = build_prompt_bundle(
            company_role,
            company_country,
        )
        input_item = build_document_input_item(
            file_bytes=file_bytes,
            metadata=metadata,
        )
        request_id = uuid.uuid4().hex
        started = time.monotonic()
        last_error: Optional[Exception] = None

        for attempt, model in enumerate(self._models_to_try(), start=1):
            try:
                response = self.client.responses.parse(
                    model=model,
                    input=[
                        {
                            "role": "system",
                            "content": prompt_bundle["system"],
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": prompt_bundle["user"],
                                },
                                input_item,
                            ],
                        },
                    ],
                    text_format=TradeDocumentExtraction,
                    store=False,
                    max_output_tokens=8000,
                    timeout=self.settings.openai_timeout_seconds,
                )
                parsed = response.output_parsed
                if parsed is None:
                    raise OpenAIAdapterError(
                        "모델이 검증 가능한 구조화 결과를 반환하지 않았습니다."
                    )

                usage = getattr(response, "usage", None)
                response_request_id = getattr(response, "_request_id", None)
                return AdapterExtractionResult(
                    extraction=parsed,
                    usage=ExtractionUsage(
                        model=model,
                        prompt_version=prompt_bundle["version"],
                        request_id=response_request_id or request_id,
                        latency_seconds=time.monotonic() - started,
                        input_tokens=_usage_value(usage, "input_tokens"),
                        output_tokens=_usage_value(usage, "output_tokens"),
                        total_tokens=_usage_value(usage, "total_tokens"),
                        attempts=attempt,
                    ),
                )
            except Exception as exc:
                last_error = exc

        if isinstance(last_error, OpenAIAdapterError):
            raise last_error
        raise OpenAIAdapterError(
            _friendly_api_error(
                last_error or RuntimeError("unknown error"),
                self.settings,
            )
        ) from last_error
