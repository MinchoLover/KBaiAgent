from typing import Dict, List, Literal, Optional

from pydantic import Field

from schemas import StrictModel
from src.domain.country_environment_models import (
    CountryEnvironmentReviewNeed,
    CountryTradeEnvironmentAssessment,
)
from src.domain.product_models import (
    OfficialCandidateShortlist,
    ProductCandidate,
)
from src.domain.trade_risk_models import (
    TradeRiskReviewNeed,
    TradeSettlementRiskAssessment,
)


RiskCode = Literal[
    "FX_COST_RISK",
    "FX_RECEIPT_RISK",
    "LOSS_LIMIT_EXCEEDED",
    "LIQUIDITY_BUFFER_RISK",
    "NEGATIVE_CASH_RISK",
    "PAYMENT_CAPACITY_RISK",
    "TIMING_MISMATCH_RISK",
    "DOCUMENT_INFORMATION_GAP",
]
RiskStatus = Literal[
    "SAFE",
    "LOSS_LIMIT_EXCEEDED",
    "BUFFER_SHORTFALL",
    "NEGATIVE_CASH",
    "PAYMENT_GAP",
]


class RiskFinding(StrictModel):
    risk_code: RiskCode
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    scenario_id: Optional[str] = None
    trigger_value: str
    threshold: Optional[str] = None
    unit: Literal["KRW", "FX", "DATE", "COUNT"]
    explanation_data: Dict[str, str] = Field(default_factory=dict)


class RiskAssessment(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    calculation_version: str = "risk-classifier-1.0"
    status: RiskStatus
    worst_scenario_id: str
    risk_codes: List[RiskCode] = Field(default_factory=list)
    findings: List[RiskFinding] = Field(default_factory=list)


class ConsultationTopic(StrictModel):
    category: str
    title: str
    triggered_by: List[RiskCode] = Field(default_factory=list)
    trade_risk_factor_codes: List[str] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    trade_risk_review_needs: List[TradeRiskReviewNeed] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    country_environment_rule_codes: List[str] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    country_environment_review_needs: List[
        CountryEnvironmentReviewNeed
    ] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    explanation: str
    required_information: List[str] = Field(default_factory=list)
    required_documents: List[str] = Field(default_factory=list)
    questions: List[str] = Field(default_factory=list)
    eligibility_status: Literal[
        "REQUIRES_BANK_REVIEW"
    ] = "REQUIRES_BANK_REVIEW"
    source_status: Literal[
        "GENERIC_CONSULTATION_CATEGORY",
        "OFFICIAL_SOURCE_VERIFIED",
    ] = "GENERIC_CONSULTATION_CATEGORY"
    source: Optional[str] = None
    source_url: Optional[str] = None
    as_of: Optional[str] = None
    retrieved_at: Optional[str] = None
    verification_status: Literal[
        "GENERIC_CATEGORY",
        "OFFICIAL_SOURCE_VERIFIED",
    ] = "GENERIC_CATEGORY"
    human_review_required: bool = True
    final_decision_maker: Literal[
        "USER_AND_KB_REPRESENTATIVE"
    ] = "USER_AND_KB_REPRESENTATIVE"


class InstallmentPaymentStatus(StrictModel):
    installment_sequence: int = Field(ge=1)
    status: Literal[
        "UNKNOWN",
        "CONFIRMED_RECEIVED",
        "CONFIRMED_NOT_RECEIVED",
    ] = "UNKNOWN"
    actual_payment_date: Optional[str] = None
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[str] = None
    source: Literal[
        "UNCONFIRMED",
        "USER_CONFIRMED",
    ] = "UNCONFIRMED"


class ConsultationRationaleItem(StrictModel):
    label: str
    value: str
    unit: Literal[
        "FX",
        "KRW",
        "DATE",
        "STATUS",
        "TEXT",
        "COUNT",
    ]
    currency: Optional[str] = None
    source_paths: List[str] = Field(min_length=1)


class ConsultationPriorityView(StrictModel):
    rank: int = Field(ge=1, le=3)
    category: str
    title: str
    priority_reason: str
    numeric_rationale: List[ConsultationRationaleItem] = Field(
        default_factory=list
    )
    triggered_by: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    preparation_documents: List[str] = Field(default_factory=list)
    bank_questions: List[str] = Field(default_factory=list)
    expected_decision: str
    next_action: str
    official_candidates: List[ProductCandidate] = Field(
        default_factory=list,
        max_length=3,
    )
    source_topic_ids: List[str] = Field(default_factory=list)
    priority_rule_code: str
    category_tie_break: str
    human_review_required: bool = True
    disclaimer: str


class PaymentScheduleSummary(StrictModel):
    sequence: int = Field(ge=1)
    amount_fx: Optional[str] = None
    currency: Optional[str] = None
    scheduled_date: Optional[str] = None
    condition: Optional[str] = None


class CompanySummary(StrictModel):
    trade_type: Literal["IMPORT", "EXPORT"]
    currency: str
    counterparty_country: Optional[str] = None
    settlement_date: str
    trade_amount_fx: str
    company_role: Optional[Literal["BUYER", "SELLER"]] = None
    incoterm: Optional[str] = None
    payment_terms: Optional[str] = None
    payment_schedule: List[PaymentScheduleSummary] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )


class ExposureSummary(StrictModel):
    gross_exposure_fx: str
    usable_fx_balance: str
    existing_hedge_fx: str
    open_exposure_fx: str


class PacketRiskSummary(StrictModel):
    status: RiskStatus
    worst_scenario_id: str
    additional_cost_or_receipt_loss_krw: str
    cash_after_settlement_krw: str
    buffer_shortfall_krw: str
    cash_deficit_krw: str
    payment_gap_krw: str
    risk_codes: List[RiskCode] = Field(default_factory=list)


class ProtectionStatusSummary(StrictModel):
    documentary_credit: str = "UNKNOWN"
    credit_insurance: str = "UNKNOWN"
    independent_payment_guarantee: str = "UNKNOWN"
    existing_hedge: str = "UNKNOWN"
    advance_payment_receipt: str = "NOT_APPLICABLE"


class SourceDocumentReference(StrictModel):
    document_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    filename: str
    document_type: str


class ConsultationPacket(StrictModel):
    case_id: str
    schema_version: Literal["1.0"] = "1.0"
    calculation_version: str
    generated_at: str
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    exchange_rate_as_of: str
    scenario_ids: List[str] = Field(default_factory=list)
    company_summary: CompanySummary
    exposure_summary: ExposureSummary
    risk_summary: PacketRiskSummary
    protection_summary: ProtectionStatusSummary = Field(
        default_factory=ProtectionStatusSummary
    )
    risk_findings: List[RiskFinding] = Field(default_factory=list)
    trade_settlement_risk: Optional[
        TradeSettlementRiskAssessment
    ] = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    country_environment: Optional[
        CountryTradeEnvironmentAssessment
    ] = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    consultation_topics: List[ConsultationTopic] = Field(
        default_factory=list
    )
    consultation_priorities: List[ConsultationPriorityView] = Field(
        default_factory=list,
        max_length=3,
        exclude_if=lambda value: not value,
    )
    other_consultation_topics: List[ConsultationTopic] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    consultation_priority_fingerprint: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
        exclude_if=lambda value: value is None,
    )
    installment_payment_statuses: List[
        InstallmentPaymentStatus
    ] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    official_candidate_shortlist: Optional[
        OfficialCandidateShortlist
    ] = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    missing_information: List[str] = Field(default_factory=list)
    required_documents: List[str] = Field(default_factory=list)
    bank_questions: List[str] = Field(default_factory=list)
    safety_boundaries: List[str] = Field(default_factory=list)
    source_documents: List[SourceDocumentReference] = Field(
        default_factory=list
    )
    user_confirmed_fields: List[str] = Field(default_factory=list)
    disclaimer: str


class ConsultationPacketResult(StrictModel):
    packet: ConsultationPacket
    markdown: str
    generation_provider: Literal[
        "DETERMINISTIC_TEMPLATE"
    ] = "DETERMINISTIC_TEMPLATE"


class DecisionSupportResult(StrictModel):
    risk_assessment: RiskAssessment
    trade_settlement_risk: Optional[
        TradeSettlementRiskAssessment
    ] = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    country_environment: Optional[
        CountryTradeEnvironmentAssessment
    ] = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    consultation_topics: List[ConsultationTopic] = Field(
        default_factory=list
    )
    official_candidate_shortlist: Optional[
        OfficialCandidateShortlist
    ] = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    consultation_packet: ConsultationPacketResult
