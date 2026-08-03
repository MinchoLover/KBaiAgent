from datetime import datetime
from typing import List, Literal

from pydantic import Field, model_validator

from schemas import StrictModel


DocumentSource = Literal["golden_sample", "user_upload"]
AnalysisMode = Literal["live_api", "verified_fixture"]
AnalysisSource = Literal["openai", "verified_fixture"]

GOLDEN_SAMPLE = "golden_sample"
USER_UPLOAD = "user_upload"
LIVE_API = "live_api"
VERIFIED_FIXTURE = "verified_fixture"
OPENAI_ANALYSIS_SOURCE = "openai"
FALLBACK_WARNING_CODE = "FALLBACK_USED"


class DocumentAnalysisProvenance(StrictModel):
    document_source: DocumentSource
    analysis_mode: AnalysisMode
    analysis_source: AnalysisSource
    model: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)
    fallback_used: bool = False
    warnings: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fallback_disclosure(self) -> "DocumentAnalysisProvenance":
        try:
            generated = datetime.fromisoformat(self.generated_at)
        except ValueError as exc:
            raise ValueError(
                "문서 분석 생성시각은 ISO datetime이어야 합니다."
            ) from exc
        if generated.tzinfo is None:
            raise ValueError("문서 분석 생성시각에는 timezone이 필요합니다.")
        if self.analysis_source == OPENAI_ANALYSIS_SOURCE and (
            self.analysis_mode != LIVE_API or self.fallback_used
        ):
            raise ValueError("OpenAI 결과는 live API 성공으로만 기록해야 합니다.")
        fixture_after_live_failure = (
            self.analysis_mode == LIVE_API
            and self.analysis_source == VERIFIED_FIXTURE
        )
        if fixture_after_live_failure != self.fallback_used:
            raise ValueError(
                "문서 분석 fallback provenance가 완전하지 않습니다."
            )
        if self.fallback_used != (FALLBACK_WARNING_CODE in self.warnings):
            raise ValueError("문서 분석 fallback 경고 기록이 일치하지 않습니다.")
        if self.analysis_mode == VERIFIED_FIXTURE and (
            self.analysis_source != VERIFIED_FIXTURE
            or self.fallback_used
        ):
            raise ValueError(
                "명시적 fixture 분석은 fallback과 구분해야 합니다."
            )
        return self
