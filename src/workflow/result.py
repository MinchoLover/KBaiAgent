from datetime import datetime
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import Field

from schemas import StrictModel


class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    FALLBACK = "FALLBACK"


StageData = TypeVar("StageData")


class StageResult(StrictModel, Generic[StageData]):
    status: StageStatus = StageStatus.PENDING
    data: Optional[StageData] = None
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: int = Field(default=0, ge=0)
    provider: str = "not_started"
    fallback_used: bool = False
    retry_count: int = Field(default=0, ge=0)
