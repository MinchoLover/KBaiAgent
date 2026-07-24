from typing import List, Optional

from schemas import TradeDocumentExtraction
from src.consultation.packet import build_consultation_packet
from src.consultation.response_mapping import map_consultation_topics
from src.consultation.risk_classifier import classify_stage2_risks
from src.document_intake.confirmation import ConfirmationRecord
from src.domain.consultation_models import DecisionSupportResult
from src.domain.stage1_models import NormalizedScenarioSet
from src.domain.stage2_models import Stage2Input, Stage2Result


def build_decision_support(
    *,
    case_id: str,
    extraction: TradeDocumentExtraction,
    confirmation: ConfirmationRecord,
    stage1: NormalizedScenarioSet,
    stage2_input: Stage2Input,
    stage2_result: Stage2Result,
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
    packet = build_consultation_packet(
        case_id=case_id,
        extraction=extraction,
        confirmation=confirmation,
        stage1=stage1,
        stage2_input=stage2_input,
        stage2_result=stage2_result,
        assessment=assessment,
        consultation_topics=topics,
        missing_information=missing_information,
        generated_at=generated_at,
    )
    return DecisionSupportResult(
        risk_assessment=assessment,
        consultation_topics=topics,
        consultation_packet=packet,
    )
