from typing import List, Literal, Optional

from pydantic import Field

from schemas import (
    FieldEvidence,
    StrictModel,
    TradeDocumentExtraction,
    ValidationResult,
)
from src.document_intake.confirmation import ConfirmationRecord
from src.domain.country_environment_models import (
    CountryTradeEnvironmentAssessment,
)
from src.domain.product_models import Stage4Result
from src.domain.report_models import ReportCritique, ReportResult
from src.domain.stage1_models import Stage1LoadResult
from src.domain.stage1_web_models import MarketIntegrationResult
from src.domain.stage2_models import (
    CashflowErrorDetail,
    Stage2Input,
    Stage2Result,
)
from src.domain.stage3_models import Stage3Result, StrategyCandidate
from src.workflow.result import StageResult, StageStatus
from src.workflow.trace import TraceEvent


class DocumentReference(StrictModel):
    filename: str
    sha256: str


class WorkflowState(StrictModel):
    case_id: str
    mode: Literal["OFFLINE", "ONLINE"]
    input_document: Optional[DocumentReference] = None
    extracted_trade: Optional[TradeDocumentExtraction] = None
    extraction_confidence: Optional[
        Literal[
            "REVIEW_REQUIRED",
            "DETERMINISTIC_PASS",
            "HUMAN_CONFIRMED",
        ]
    ] = None
    extraction_evidence: List[FieldEvidence] = Field(default_factory=list)
    confirmation: Optional[ConfirmationRecord] = None
    confirmation_validation: Optional[ValidationResult] = None
    user_confirmed: bool = False

    intake: Optional[StageResult[TradeDocumentExtraction]] = None
    market_risk: Optional[StageResult[Stage1LoadResult]] = None
    market_integration: Optional[MarketIntegrationResult] = None
    stage2_input: Optional[Stage2Input] = None
    cashflow: Optional[StageResult[Stage2Result]] = None
    cashflow_error: Optional[CashflowErrorDetail] = None
    hedge: Optional[StageResult[Stage3Result]] = None
    selected_strategy: Optional[StrategyCandidate] = None
    product_search: Optional[StageResult[Stage4Result]] = None
    country_environment: Optional[
        StageResult[CountryTradeEnvironmentAssessment]
    ] = None
    report: Optional[StageResult[ReportResult]] = None
    report_draft: Optional[str] = None
    critic_result: Optional[ReportCritique] = None
    final_report: Optional[ReportResult] = None

    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    trace: List[TraceEvent] = Field(default_factory=list)
    rewrite_count: int = Field(default=0, ge=0)
    final_status: StageStatus = StageStatus.PENDING
