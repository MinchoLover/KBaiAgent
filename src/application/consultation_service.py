from typing import List, Optional

from schemas import TradeDocumentExtraction
from src.consultation.packet import build_consultation_packet
from src.consultation.response_mapping import (
    map_country_environment_consultation_topics,
    map_consultation_topics,
    map_trade_risk_consultation_topics,
)
from src.consultation.risk_classifier import classify_stage2_risks
from src.document_intake.confirmation import ConfirmationRecord
from src.domain.consultation_models import (
    ConsultationTopic,
    DecisionSupportResult,
    InstallmentPaymentStatus,
)
from src.domain.country_environment_models import (
    CountryTradeEnvironmentAssessment,
)
from src.domain.country_economic_interpretation_models import (
    CountryEconomicInterpretationResult,
)
from src.domain.confirmed_transaction_models import (
    ConfirmedTransactionSnapshot,
)
from src.domain.product_models import (
    AuxiliaryServiceCandidates,
    OfficialCandidateInputProfile,
    OfficialCandidateShortlist,
)
from src.domain.stage1_models import NormalizedScenarioSet
from src.domain.stage2_models import Stage2Input, Stage2Result
from src.domain.trade_risk_models import TradeSettlementRiskAssessment
from src.domain.trade_statistics_models import TradeStatisticsResult
from src.domain.trade_statistics_interpretation_models import (
    TradeStatisticsInterpretationResult,
)


def _dedupe(values: List[str]) -> List[str]:
    return list(dict.fromkeys(values))


def _merge_topics(
    topics: List[ConsultationTopic],
) -> List[ConsultationTopic]:
    merged = {}
    order: List[str] = []
    for topic in topics:
        if topic.category not in merged:
            merged[topic.category] = topic
            order.append(topic.category)
            continue
        current = merged[topic.category]
        explanations = _dedupe(
            [current.explanation, topic.explanation]
        )
        merged[topic.category] = current.model_copy(
            update={
                "triggered_by": _dedupe(
                    current.triggered_by + topic.triggered_by
                ),
                "trade_risk_factor_codes": _dedupe(
                    current.trade_risk_factor_codes
                    + topic.trade_risk_factor_codes
                ),
                "trade_risk_review_needs": _dedupe(
                    current.trade_risk_review_needs
                    + topic.trade_risk_review_needs
                ),
                "country_environment_rule_codes": _dedupe(
                    current.country_environment_rule_codes
                    + topic.country_environment_rule_codes
                ),
                "country_environment_review_needs": _dedupe(
                    current.country_environment_review_needs
                    + topic.country_environment_review_needs
                ),
                "explanation": " ".join(explanations),
                "required_information": _dedupe(
                    current.required_information
                    + topic.required_information
                ),
                "required_documents": _dedupe(
                    current.required_documents
                    + topic.required_documents
                ),
                "questions": _dedupe(
                    current.questions + topic.questions
                ),
            }
        )
    return [merged[category] for category in order]


def build_decision_support(
    *,
    case_id: str,
    extraction: TradeDocumentExtraction,
    confirmation: ConfirmationRecord,
    stage1: NormalizedScenarioSet,
    stage2_input: Stage2Input,
    stage2_result: Stage2Result,
    trade_settlement_risk: Optional[
        TradeSettlementRiskAssessment
    ] = None,
    country_environment: Optional[
        CountryTradeEnvironmentAssessment
    ] = None,
    country_economic_interpretation: Optional[
        CountryEconomicInterpretationResult
    ] = None,
    trade_statistics: Optional[TradeStatisticsResult] = None,
    trade_statistics_interpretation: Optional[
        TradeStatisticsInterpretationResult
    ] = None,
    official_candidate_shortlist: Optional[
        OfficialCandidateShortlist
    ] = None,
    official_candidate_input_profile: Optional[
        OfficialCandidateInputProfile
    ] = None,
    auxiliary_service_candidates: Optional[
        AuxiliaryServiceCandidates
    ] = None,
    installment_payment_statuses: Optional[
        List[InstallmentPaymentStatus]
    ] = None,
    missing_information: Optional[List[str]] = None,
    generated_at: Optional[str] = None,
    confirmed_transaction: Optional[
        ConfirmedTransactionSnapshot
    ] = None,
) -> DecisionSupportResult:
    assessment = classify_stage2_risks(
        stage2_result=stage2_result,
        stage2_input=stage2_input,
        missing_information=missing_information,
    )
    topics = map_consultation_topics(
        trade_type=stage2_result.trade_type,
        assessment=assessment,
        stage2_result=stage2_result,
    )
    if trade_settlement_risk is not None:
        topics.extend(
            map_trade_risk_consultation_topics(
                trade_settlement_risk
            )
        )
    if country_environment is not None:
        topics.extend(
            map_country_environment_consultation_topics(
                country_environment
            )
        )
    topics = _merge_topics(topics)
    packet = build_consultation_packet(
        case_id=case_id,
        extraction=extraction,
        confirmation=confirmation,
        stage1=stage1,
        stage2_input=stage2_input,
        stage2_result=stage2_result,
        assessment=assessment,
        consultation_topics=topics,
        trade_settlement_risk=trade_settlement_risk,
        country_environment=country_environment,
        country_economic_interpretation=country_economic_interpretation,
        trade_statistics=trade_statistics,
        trade_statistics_interpretation=(
            trade_statistics_interpretation
        ),
        official_candidate_shortlist=official_candidate_shortlist,
        official_candidate_input_profile=official_candidate_input_profile,
        auxiliary_service_candidates=auxiliary_service_candidates,
        installment_payment_statuses=installment_payment_statuses,
        missing_information=missing_information,
        generated_at=generated_at,
        confirmed_transaction=confirmed_transaction,
    )
    return DecisionSupportResult(
        risk_assessment=assessment,
        trade_settlement_risk=trade_settlement_risk,
        country_environment=country_environment,
        country_economic_interpretation=country_economic_interpretation,
        trade_statistics=trade_statistics,
        trade_statistics_interpretation=(
            trade_statistics_interpretation
        ),
        consultation_topics=topics,
        official_candidate_shortlist=official_candidate_shortlist,
        auxiliary_service_candidates=auxiliary_service_candidates,
        consultation_packet=packet,
    )
