from typing import List, Literal, Optional

from pydantic import Field, model_validator

from schemas import (
    FieldEvidence,
    StrictModel,
    TradeDocumentExtraction,
    ValidationResult,
)
from src.document_intake.confirmation import ConfirmationRecord
from src.domain.confirmed_transaction_models import (
    ConfirmedTransactionSnapshot,
)
from src.domain.country_environment_models import (
    CountryTradeEnvironmentAssessment,
)
from src.domain.product_models import (
    OfficialCandidateInputProfile,
    Stage4Result,
)
from src.domain.report_models import ReportCritique, ReportResult
from src.domain.stage1_models import Stage1LoadResult
from src.domain.stage1_web_models import MarketIntegrationResult
from src.domain.stage2_models import (
    CashflowErrorDetail,
    Stage2Input,
    Stage2Result,
)
from src.domain.stage3_models import Stage3Result, StrategyCandidate
from src.domain.trade_statistics_models import TradeStatisticsResult
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
    confirmed_transaction: Optional[ConfirmedTransactionSnapshot] = None
    official_candidate_input_profile: Optional[
        OfficialCandidateInputProfile
    ] = None
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
    trade_statistics: Optional[
        StageResult[TradeStatisticsResult]
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

    @model_validator(mode="after")
    def validate_official_candidate_profile_binding(self) -> "WorkflowState":
        profile = self.official_candidate_input_profile
        if profile is not None and (
            self.confirmed_transaction is None
            or profile.bound_transaction_fingerprint
            != self.confirmed_transaction.input_fingerprint
        ):
            raise ValueError(
                "상품 입력 profile이 WorkflowState confirmed transaction과 다릅니다."
            )
        return self
