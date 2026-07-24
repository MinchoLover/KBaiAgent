from decimal import Decimal
from typing import Dict, List

from src.domain.consultation_models import (
    ConsultationTopic,
    RiskAssessment,
    RiskCode,
)
from src.domain.stage2_models import Stage2Result


def _topic(
    *,
    category: str,
    title: str,
    triggered_by: List[RiskCode],
    explanation: str,
    required_information: List[str],
    required_documents: List[str],
    questions: List[str],
) -> ConsultationTopic:
    return ConsultationTopic(
        category=category,
        title=title,
        triggered_by=triggered_by,
        explanation=explanation,
        required_information=required_information,
        required_documents=required_documents,
        questions=questions,
    )


def map_consultation_topics(
    *,
    trade_type: str,
    assessment: RiskAssessment,
    stage2_result: Stage2Result,
) -> List[ConsultationTopic]:
    if trade_type not in {"IMPORT", "EXPORT"}:
        raise ValueError("상담 대응 매핑에는 IMPORT 또는 EXPORT가 필요합니다.")
    risks = set(assessment.risk_codes)
    topics: Dict[str, ConsultationTopic] = {}

    fx_risk = (
        "FX_COST_RISK"
        if trade_type == "IMPORT"
        else "FX_RECEIPT_RISK"
    )
    if fx_risk in risks or "LOSS_LIMIT_EXCEEDED" in risks:
        topics["FX_RISK_MANAGEMENT"] = _topic(
            category="FX_RISK_MANAGEMENT",
            title="환율 관리 상담",
            triggered_by=[
                item
                for item in [fx_risk, "LOSS_LIMIT_EXCEEDED"]
                if item in risks
            ],
            explanation=(
                "기준 시나리오와 불리한 스트레스 시나리오의 원화 금액 차이를 "
                "확인해 분할 환전·선물환 등 가능한 관리 수단을 상담할 항목입니다."
            ),
            required_information=[
                "결제 또는 수취 예정일 변경 가능 여부",
                "실제 거래은행 적용 환율·스프레드·수수료",
                "이미 체결한 환헤지 계약의 잔액과 만기",
            ],
            required_documents=[
                "수출입 계약서 또는 인보이스",
                "기존 환헤지 계약서(있는 경우)",
            ],
            questions=[
                "현재 결제일과 통화에 적용 가능한 환율 관리 수단은 무엇인가?",
                "선물환 또는 분할 환전의 실제 비용과 한도는 얼마인가?",
                "이미 체결한 환헤지 계약이 있는가?",
            ],
        )

    held_fx = Decimal(stage2_result.held_fx_used)
    if trade_type == "IMPORT" and (
        held_fx > 0 or "FX_COST_RISK" in risks
    ):
        topics["FX_BALANCE_UTILIZATION"] = _topic(
            category="FX_BALANCE_UTILIZATION",
            title="보유 외화 활용 검토",
            triggered_by=[
                "FX_COST_RISK"
            ] if "FX_COST_RISK" in risks else [],
            explanation=(
                "결제에 사용할 수 있는 보유 외화를 먼저 확인해 불필요한 신규 "
                "환전을 줄일 수 있는지 검토하는 상담 항목입니다."
            ),
            required_information=[
                "통화별 실제 사용 가능 외화 잔액",
                "다른 결제에 이미 배정된 외화 여부",
                "결제일까지 추가 외화 유입 예정",
            ],
            required_documents=[
                "외화예금 잔액 및 최근 거래내역",
                "향후 외화 입출금 일정",
            ],
            questions=[
                "보유 외화 중 이번 결제에 실제 사용할 수 있는 금액은 얼마인가?",
                "결제일까지 추가 외화 유입이 예정되어 있는가?",
            ],
        )

    if (
        trade_type == "IMPORT"
        and "LIQUIDITY_BUFFER_RISK" in risks
    ):
        topics["IMPORT_SETTLEMENT_FINANCE"] = _topic(
            category="IMPORT_SETTLEMENT_FINANCE",
            title="수입 결제자금 상담",
            triggered_by=["LIQUIDITY_BUFFER_RISK"],
            explanation=(
                "결제 후 현금이 최소 운영자금 기준보다 낮아질 수 있어, 실제 "
                "결제자금 한도와 자금 집행 시점을 확인할 상담 항목입니다."
            ),
            required_information=[
                "현재 사용 가능한 원화 현금",
                "실제 사용 가능한 대출한도와 만기",
                "결제일까지 확정된 원화 입출금",
                "결제조건 분할 또는 조정 가능성",
            ],
            required_documents=[
                "수입 계약서 또는 인보이스",
                "최근 자금계획표",
                "기존 대출 약정 및 한도 확인 자료",
            ],
            questions=[
                "실제 사용 가능한 대출한도는 얼마인가?",
                "결제조건을 분할하거나 조정할 수 있는가?",
                "결제일까지 운영자금 방어선을 유지할 조달 방법이 있는가?",
            ],
        )

    if "PAYMENT_CAPACITY_RISK" in risks:
        topics["PAYMENT_CAPACITY_REVIEW"] = _topic(
            category="PAYMENT_CAPACITY_REVIEW",
            title="결제능력 및 자금한도 긴급 확인",
            triggered_by=["PAYMENT_CAPACITY_RISK"],
            explanation=(
                "현재 현금과 입력된 대출한도를 반영해도 지급 부족이 남는 "
                "시나리오가 있어 실제 가용자금과 결제조건을 우선 확인해야 합니다."
            ),
            required_information=[
                "당일 인출 가능한 현금과 미사용 신용한도",
                "추가 담보 또는 보증 제공 가능 여부",
                "거래 상대방과 결제일 조정 가능 여부",
            ],
            required_documents=[
                "자금일보 및 계좌 잔액 자료",
                "대출 약정서와 미사용 한도 확인서",
                "결제 일정이 표시된 계약서",
            ],
            questions=[
                "현재 즉시 사용할 수 있는 현금과 신용한도는 정확히 얼마인가?",
                "지급일 조정 또는 분할 지급 협의가 가능한가?",
                "추가 자금 지원 가능 여부는 어떤 심사와 서류가 필요한가?",
            ],
        )

    if trade_type == "EXPORT" and "FX_RECEIPT_RISK" in risks:
        topics["EXPORT_RECEIPT_MANAGEMENT"] = _topic(
            category="EXPORT_RECEIPT_MANAGEMENT",
            title="수출대금 회수·환율 관리 상담",
            triggered_by=["FX_RECEIPT_RISK"],
            explanation=(
                "환율 하락 스트레스에서 원화 수취액이 감소하므로 회수 일정과 "
                "수출대금 관리 수단을 함께 확인할 상담 항목입니다."
            ),
            required_information=[
                "수출대금 회수 예정일과 지연 가능성",
                "수출채권 금액과 통화",
                "동일 통화 비용 또는 상계 가능 금액",
            ],
            required_documents=[
                "수출 계약서 또는 인보이스",
                "선적 및 수출대금 회수 일정",
                "기존 환헤지 계약서(있는 경우)",
            ],
            questions=[
                "수출대금 회수일이 지연될 가능성이 있는가?",
                "환율 하락에 대비해 검토할 수 있는 관리 수단은 무엇인가?",
                "수출채권을 활용한 금융 상담에 필요한 서류는 무엇인가?",
            ],
        )

    if "DOCUMENT_INFORMATION_GAP" in risks:
        topics["TRADE_INFORMATION_REVIEW"] = _topic(
            category="TRADE_INFORMATION_REVIEW",
            title="거래조건 및 추가 문서 확인",
            triggered_by=["DOCUMENT_INFORMATION_GAP"],
            explanation=(
                "계산 또는 상담에 필요한 거래·자금 정보가 확인되지 않아 "
                "추가 문서와 사용자 확인이 필요한 항목입니다."
            ),
            required_information=[
                "통화·금액·결제일·거래 방향 최종 확인",
                "누락된 회사 자금 및 기존 헤지 정보",
            ],
            required_documents=[
                "최종 수출입 계약서 또는 인보이스",
                "결제조건 변경 합의서(있는 경우)",
            ],
            questions=[
                "현재 입력 중 문서로 확정되지 않은 항목은 무엇인가?",
                "추가 계약서 또는 결제조건 변경 문서가 있는가?",
            ],
        )

    if not topics:
        topics["ROUTINE_TRADE_REVIEW"] = _topic(
            category="ROUTINE_TRADE_REVIEW",
            title="거래 일정 및 환율 관리 정기 점검",
            triggered_by=[],
            explanation=(
                "현재 입력에서는 주요 위험 기준을 넘지 않았지만 실제 적용 환율, "
                "수수료와 결제 일정은 거래 전에 다시 확인해야 합니다."
            ),
            required_information=[
                "최종 결제 또는 수취 일정",
                "거래은행 실제 적용 환율과 수수료",
            ],
            required_documents=[
                "최종 수출입 계약서 또는 인보이스",
            ],
            questions=[
                "거래 전 최종 확인해야 할 환율·수수료·서류는 무엇인가?",
            ],
        )

    return list(topics.values())
