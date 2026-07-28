from typing import List, Optional

from schemas import TradeDocumentExtraction
from src.consultation.packet import build_consultation_packet
from src.consultation.response_mapping import (
    map_consultation_topics,
    map_trade_risk_consultation_topics,
)
from src.consultation.risk_classifier import classify_stage2_risks
from src.document_intake.confirmation import ConfirmationRecord
from src.domain.consultation_models import DecisionSupportResult
from src.domain.product_models import OfficialCandidateShortlist
from src.domain.stage1_models import NormalizedScenarioSet
from src.domain.stage2_models import Stage2Input, Stage2Result
from src.domain.trade_risk_models import TradeSettlementRiskAssessment


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
    official_candidate_shortlist: Optional[
        OfficialCandidateShortlist
    ] = None,
    missing_information: Optional[List[str]] = None,
    generated_at: Optional[str] = None,
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
        official_candidate_shortlist=official_candidate_shortlist,
        missing_information=missing_information,
        generated_at=generated_at,
    )
    return DecisionSupportResult(
        risk_assessment=assessment,
        trade_settlement_risk=trade_settlement_risk,
        consultation_topics=topics,
        official_candidate_shortlist=official_candidate_shortlist,
        consultation_packet=packet,
    )
