from datetime import datetime
from typing import List, Optional

from pydantic import Field

from schemas import StrictModel
from src.workflow.result import StageResult, StageStatus


class TraceEvent(StrictModel):
    sequence: int = Field(ge=1)
    case_id: str
    stage: str
    status: StageStatus
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: int = Field(default=0, ge=0)
    provider: str
    mode: str
    fallback_used: bool = False
    user_confirmed: bool = False
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    critic_passed: Optional[bool] = None
    retry_count: int = Field(default=0, ge=0)
    rewrite_count: int = Field(default=0, ge=0)


def build_trace_event(
    *,
    sequence: int,
    case_id: str,
    stage: str,
    result: StageResult[object],
    mode: str,
    user_confirmed: bool,
    critic_passed: Optional[bool] = None,
    rewrite_count: int = 0,
) -> TraceEvent:
    return TraceEvent(
        sequence=sequence,
        case_id=case_id,
        stage=stage,
        status=result.status,
        started_at=result.started_at,
        finished_at=result.finished_at,
        duration_ms=result.duration_ms,
        provider=result.provider,
        mode=mode,
        fallback_used=result.fallback_used,
        user_confirmed=user_confirmed,
        warnings=result.warnings,
        errors=result.errors,
        evidence=result.evidence,
        critic_passed=critic_passed,
        retry_count=result.retry_count,
        rewrite_count=rewrite_count,
    )
