from decimal import Decimal
from typing import Dict, List, Optional

from src.domain.consultation_models import (
    ConsultationTopic,
    RiskAssessment,
    RiskCode,
)
from src.domain.country_environment_models import (
    CountryEnvironmentReviewNeed,
    CountryTradeEnvironmentAssessment,
)
from src.domain.stage2_models import Stage2Result
from src.domain.trade_risk_models import (
    TradeRiskReviewNeed,
    TradeSettlementRiskAssessment,
)


def _topic(
    *,
    category: str,
    title: str,
    triggered_by: List[RiskCode],
    explanation: str,
    required_information: List[str],
    required_documents: List[str],
    questions: List[str],
    trade_risk_factor_codes: Optional[List[str]] = None,
    trade_risk_review_needs: Optional[
        List[TradeRiskReviewNeed]
    ] = None,
    country_environment_rule_codes: Optional[List[str]] = None,
    country_environment_review_needs: Optional[
        List[CountryEnvironmentReviewNeed]
    ] = None,
) -> ConsultationTopic:
    return ConsultationTopic(
        category=category,
        title=title,
        triggered_by=triggered_by,
        trade_risk_factor_codes=trade_risk_factor_codes or [],
        trade_risk_review_needs=trade_risk_review_needs or [],
        country_environment_rule_codes=(
            country_environment_rule_codes or []
        ),
        country_environment_review_needs=(
            country_environment_review_needs or []
        ),
        explanation=explanation,
        required_information=required_information,
        required_documents=required_documents,
        questions=questions,
    )


def _trade_factor_codes(
    *,
    assessment: TradeSettlementRiskAssessment,
    allowed: List[str],
) -> List[str]:
    return [
        factor.code
        for factor in assessment.factors
        if factor.code in allowed
    ]


def map_trade_risk_consultation_topics(
    assessment: TradeSettlementRiskAssessment,
) -> List[ConsultationTopic]:
    needs = set(assessment.review_needs)
    topics: Dict[str, ConsultationTopic] = {}

    if "ADVANCE_PAYMENT_PROTECTION_REVIEW" in needs:
        need: TradeRiskReviewNeed = (
            "ADVANCE_PAYMENT_PROTECTION_REVIEW"
        )
        topics["IMPORT_ADVANCE_PAYMENT_PROTECTION"] = _topic(
            category="IMPORT_ADVANCE_PAYMENT_PROTECTION",
            title="수입 선지급 보호수단 상담",
            triggered_by=[],
            trade_risk_factor_codes=_trade_factor_codes(
                assessment=assessment,
                allowed=[
                    "IMPORT_ADVANCE_PAYMENT",
                    "IMPORT_PROTECTION_UNKNOWN",
                    "NO_APPLICABLE_IMPORT_PROTECTION",
                    "APPLICABLE_IMPORT_PROTECTION",
                ],
            ),
            trade_risk_review_needs=[need],
            explanation=(
                "선지급 금액을 환율 위험과 구분해, 공급자 미이행 시 적용될 "
                "수 있는 환급·이행 보호조건을 확인하는 상담 항목입니다."
            ),
            required_information=[
                "선지급 금액·비율·지급 예정일",
                "납품·검수·계약이행 기준과 예정일",
                "선지급금 반환 조항과 청구 조건",
                "보증이 있으면 보증금액·유효기간·현재 거래 적용범위",
            ],
            required_documents=[
                "최종 수입계약서와 결제 일정",
                "견적송장 또는 인보이스",
                "선급금환급보증·계약이행보증 문안(있는 경우)",
            ],
            questions=[
                "선지급금 미반환 위험에 맞는 보호수단을 검토할 수 있는가?",
                "보증금액·유효기간·청구조건이 실제 선지급 일정을 충분히 포괄하는가?",
                "보호수단 발급 전 지급하면 보호되지 않는 구간이 있는가?",
            ],
        )

    if "RECEIVABLE_PROTECTION_REVIEW" in needs:
        need = "RECEIVABLE_PROTECTION_REVIEW"
        topics["EXPORT_RECEIVABLE_PROTECTION"] = _topic(
            category="EXPORT_RECEIVABLE_PROTECTION",
            title="수출대금 회수 보호 상담",
            triggered_by=[],
            trade_risk_factor_codes=_trade_factor_codes(
                assessment=assessment,
                allowed=[
                    "EXPORT_OPEN_ACCOUNT",
                    "EXPORT_DOCUMENTARY_COLLECTION_DA",
                    "LONG_EXPORT_PAYMENT_TERM",
                    "EXPORT_PROTECTION_UNKNOWN",
                    "NO_APPLICABLE_EXPORT_PROTECTION",
                    "APPLICABLE_EXPORT_PROTECTION",
                ],
            ),
            trade_risk_review_needs=[need],
            explanation=(
                "수출대금 미회수·지연 위험을 환율 하락 위험과 구분해, "
                "보험·지급보증·보증신용장 등 회수 보호조건을 확인하는 "
                "상담 항목입니다."
            ),
            required_information=[
                "수입자와의 거래기간·과거 결제이력",
                "잔여 수출채권 금액·통화·회수 예정일",
                "Open Account 또는 추심 조건과 연체 시 조치",
                "보험·보증이 있으면 보상범위·면책·현재 거래 적용여부",
            ],
            required_documents=[
                "최종 수출계약서·인보이스·발주서",
                "선적서류와 수출채권 회수 일정",
                "수출신용보험·지급보증·보증신용장 문서(있는 경우)",
            ],
            questions=[
                "현재 거래의 미회수 위험에 검토 가능한 보호수단은 무엇인가?",
                "보상·보증 한도와 면책조건이 이 채권에 어떻게 적용되는가?",
                "Open Account 또는 D/A 조건을 보완할 수 있는 계약조건이 있는가?",
            ],
        )

    if "DOCUMENTARY_CREDIT_TERMS_REVIEW" in needs:
        need = "DOCUMENTARY_CREDIT_TERMS_REVIEW"
        topics["DOCUMENTARY_CREDIT_TERMS_REVIEW"] = _topic(
            category="DOCUMENTARY_CREDIT_TERMS_REVIEW",
            title="신용장 세부조건 상담",
            triggered_by=[],
            trade_risk_factor_codes=_trade_factor_codes(
                assessment=assessment,
                allowed=["DOCUMENTARY_CREDIT_DETAILS_NOT_ASSESSED"],
            ),
            trade_risk_review_needs=[need],
            explanation=(
                "신용장 존재만으로 회수위험이 제거된다고 보지 않고, "
                "확인 여부·발행은행·서류조건과 불일치 가능성을 검토합니다."
            ),
            required_information=[
                "취소불능 여부와 확인신용장 여부",
                "발행은행·확인은행과 지급 또는 인수 조건",
                "요구서류·제시기한·불일치 처리조건",
            ],
            required_documents=[
                "신용장 원문과 모든 amendment",
                "수출계약서와 요구 선적서류 목록",
            ],
            questions=[
                "발행은행과 신용장 조건에서 추가 확인할 위험은 무엇인가?",
                "서류불일치를 줄이기 위해 선적 전 수정할 조건이 있는가?",
                "확인신용장 검토가 필요한지 어떤 기준으로 판단하는가?",
            ],
        )

    if "TRADE_TERMS_REVIEW" in needs:
        need = "TRADE_TERMS_REVIEW"
        topics["PAYMENT_TERMS_REVIEW"] = _topic(
            category="PAYMENT_TERMS_REVIEW",
            title="결제조건 명확화 상담",
            triggered_by=[],
            trade_risk_factor_codes=_trade_factor_codes(
                assessment=assessment,
                allowed=[
                    "DOCUMENTARY_COLLECTION_TYPE_UNKNOWN",
                    "PAYMENT_TERM_UNRESOLVED",
                ],
            ),
            trade_risk_review_needs=[need],
            explanation=(
                "D/P·D/A 구분 또는 선적·B/L·검수 후 기간처럼 계산 기준이 "
                "불명확한 조건을 확정하는 상담 항목입니다."
            ),
            required_information=[
                "잔여대금 결제방식과 지급·인수 조건",
                "결제기간을 시작하는 사건과 증빙",
                "지연·분쟁·서류불일치 시 처리 조항",
            ],
            required_documents=[
                "최종 계약서와 결제조건 변경 합의서",
                "추심지시서 또는 신용장 문서(해당 시)",
            ],
            questions=[
                "현재 문구가 D/P와 D/A 중 어느 조건을 의미하는가?",
                "결제기간의 기준일과 이를 입증할 서류는 무엇인가?",
                "계약서에 추가로 명확히 해야 할 지급 조건은 무엇인가?",
            ],
        )

    if "HUMAN_REVIEW" in needs or assessment.information_gaps:
        topics["TRADE_RISK_INFORMATION_REVIEW"] = _topic(
            category="TRADE_RISK_INFORMATION_REVIEW",
            title="거래·보호조건 추가 확인",
            triggered_by=[],
            trade_risk_factor_codes=[
                factor.code
                for factor in assessment.factors
                if factor.effect == "INFORMATION_GAP"
            ],
            trade_risk_review_needs=["HUMAN_REVIEW"],
            explanation=(
                "미확인 정보를 ‘없음’으로 가정하지 않고 담당자가 문서와 "
                "거래 사실을 확인해야 하는 항목입니다."
            ),
            required_information=assessment.information_gaps,
            required_documents=[
                "최종 계약서·인보이스·결제 일정",
                "보험·보증·신용장 문서(있는 경우)",
            ],
            questions=[
                "현재 미확인 항목을 증명할 문서 또는 담당자는 누구인가?",
                "보호수단이 없다면 부재를 확인한 근거는 무엇인가?",
            ],
        )

    return list(topics.values())


def _country_rule_codes(
    *,
    assessment: CountryTradeEnvironmentAssessment,
    needs: List[CountryEnvironmentReviewNeed],
) -> List[str]:
    return [
        item.rule_code
        for item in assessment.rule_contributions
        if item.review_need in needs
    ]


def map_country_environment_consultation_topics(
    assessment: CountryTradeEnvironmentAssessment,
) -> List[ConsultationTopic]:
    needs = set(assessment.review_needs)
    topics: Dict[str, ConsultationTopic] = {}
    if "INFORMATION_COMPLETENESS_REVIEW" in needs:
        info_need: CountryEnvironmentReviewNeed = (
            "INFORMATION_COMPLETENESS_REVIEW"
        )
        topics["COUNTRY_INFORMATION_COMPLETENESS"] = _topic(
            category="COUNTRY_INFORMATION_COMPLETENESS",
            title="국가 공식자료 완전성 확인",
            triggered_by=[],
            country_environment_rule_codes=_country_rule_codes(
                assessment=assessment,
                needs=[info_need],
            ),
            country_environment_review_needs=[info_need],
            explanation=(
                "공식 snapshot 또는 핵심 provenance가 불완전해 낮은 위험으로 "
                "간주하지 않고 자료를 다시 확인하는 상담 항목입니다."
            ),
            required_information=[
                "거래 상대국 사용자 확인",
                "snapshot version·hash와 세 공식 source provenance",
            ],
            required_documents=[
                "최종 계약서 또는 인보이스의 거래 상대국 표시",
            ],
            questions=[
                "현재 거래국의 공식자료를 어떤 기준일 자료로 다시 확인해야 하는가?",
            ],
        )
        return list(topics.values())

    protection_needs = [
        item
        for item in (
            "PAYMENT_TRANSFER_PROTECTION_REVIEW",
            "CREDIT_INSURANCE_REVIEW",
            "GUARANTEE_REVIEW",
        )
        if item in needs
    ]
    if protection_needs:
        category = (
            "EXPORT_RECEIVABLE_PROTECTION"
            if assessment.trade_type == "EXPORT"
            else "COUNTRY_PAYMENT_TRANSFER_PROTECTION"
        )
        topics[category] = _topic(
            category=category,
            title="국가 지급·이전 보호수단 상담",
            triggered_by=[],
            country_environment_rule_codes=_country_rule_codes(
                assessment=assessment,
                needs=protection_needs,
            ),
            country_environment_review_needs=protection_needs,
            explanation=(
                "OECD 원자료를 자체 국가등급으로 바꾸지 않고 보험·보증·"
                "지급보호 조건을 우선 확인하는 상담 항목입니다."
            ),
            required_information=[
                "보험·보증의 거래국·채권 적용범위",
                "보상·보증 한도, 유효기간, 면책과 청구조건",
            ],
            required_documents=[
                "수출입계약서와 결제 일정",
                "보험증권·지급보증·보증신용장 문서(있는 경우)",
            ],
            questions=[
                "지급·이전 위험에 대비해 이 거래에 적용 가능한 보호수단은 무엇인가?",
                "보험·보증의 보상범위와 면책이 현재 채권에 어떻게 적용되는가?",
            ],
        )

    if "DOCUMENTARY_CREDIT_TERMS_REVIEW" in needs:
        need = "DOCUMENTARY_CREDIT_TERMS_REVIEW"
        topics["DOCUMENTARY_CREDIT_TERMS_REVIEW"] = _topic(
            category="DOCUMENTARY_CREDIT_TERMS_REVIEW",
            title="신용장 세부조건 상담",
            triggered_by=[],
            country_environment_rule_codes=_country_rule_codes(
                assessment=assessment,
                needs=[need],
            ),
            country_environment_review_needs=[need],
            explanation=(
                "거래국 공식 신호와 별개로 발행은행·확인 여부·서류조건을 "
                "확인하는 상담 항목입니다."
            ),
            required_information=[
                "발행은행·확인은행과 지급 또는 인수 조건",
                "요구서류·제시기한·불일치 처리조건",
            ],
            required_documents=["신용장 원문과 amendment(검토 시)"],
            questions=[
                "Open Account 조건을 보완할 신용장 조건을 검토할 필요가 있는가?",
            ],
        )

    if "PAYMENT_TERMS_REVIEW" in needs:
        need = "PAYMENT_TERMS_REVIEW"
        topics["PAYMENT_TERMS_REVIEW"] = _topic(
            category="PAYMENT_TERMS_REVIEW",
            title="결제조건 명확화 상담",
            triggered_by=[],
            country_environment_rule_codes=_country_rule_codes(
                assessment=assessment,
                needs=[need],
            ),
            country_environment_review_needs=[need],
            explanation=(
                "장기 Open Account의 회수기간·연체·분쟁 조건과 보호수단을 "
                "거래 전에 다시 확인하는 상담 항목입니다."
            ),
            required_information=[
                "회수기간 기준일과 연체 시 조치",
                "결제조건 단축·분할·보호조건 추가 가능성",
            ],
            required_documents=["최종 계약서와 결제조건 변경 합의서"],
            questions=[
                "90일 Open Account 조건을 단축·분할하거나 보호조건을 추가할 수 있는가?",
            ],
        )

    if "MACRO_ENVIRONMENT_MONITORING" in needs:
        need = "MACRO_ENVIRONMENT_MONITORING"
        topics["COUNTRY_MACRO_ENVIRONMENT_MONITORING"] = _topic(
            category="COUNTRY_MACRO_ENVIRONMENT_MONITORING",
            title="거시환경 관측자료 확인",
            triggered_by=[],
            country_environment_rule_codes=_country_rule_codes(
                assessment=assessment,
                needs=[need],
            ),
            country_environment_review_needs=[need],
            explanation=(
                "World Bank 원값과 서로 다른 관측연도를 점수화하지 않고 "
                "회수기간 중 점검할 상담 문맥으로 사용합니다."
            ),
            required_information=[
                "지표별 관측연도와 갱신일",
                "결제기간 중 거래처와 회수일정 변화",
            ],
            required_documents=["최신 회수 일정과 거래처 결제이력"],
            questions=[
                "관측연도가 다른 거시지표를 현재 거래조건 검토에 어떻게 제한적으로 참고할 것인가?",
            ],
        )

    if "TRADE_MARKET_ACCESS_REVIEW" in needs:
        need = "TRADE_MARKET_ACCESS_REVIEW"
        topics["TRADE_MARKET_ACCESS_REVIEW"] = _topic(
            category="TRADE_MARKET_ACCESS_REVIEW",
            title="통관·관세·시장접근 조건 확인",
            triggered_by=[],
            country_environment_rule_codes=_country_rule_codes(
                assessment=assessment,
                needs=[need],
            ),
            country_environment_review_needs=[need],
            explanation=(
                "WTO 회원·MFN·무역정책검토 원값은 시장접근 문맥이며 "
                "실제 품목의 통관·관세 조건을 별도로 확인해야 합니다."
            ),
            required_information=[
                "HS code와 원산지",
                "품목별 관세·특혜·추가조치와 통관 요구사항",
            ],
            required_documents=[
                "품목분류·원산지·선적 서류",
            ],
            questions=[
                "현재 품목과 원산지에 적용되는 실제 관세·통관 조건은 무엇인가?",
                "최근 조치나 시장접근 제한을 무역전문가와 추가 확인해야 하는가?",
            ],
        )
    return list(topics.values())


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

    if (
        trade_type == "EXPORT"
        and "LIQUIDITY_BUFFER_RISK" in risks
    ):
        topics["EXPORT_LIQUIDITY_REVIEW"] = _topic(
            category="EXPORT_LIQUIDITY_REVIEW",
            title="운영자금 버퍼·수출대금 회수시점 상담",
            triggered_by=["LIQUIDITY_BUFFER_RISK"],
            explanation=(
                "불리한 환율 조건에서 결제·수취 후 현금이 목표 운영자금 "
                "버퍼보다 낮아질 수 있어, 실제 자금계획·회수시점·가용한도와 "
                "검토 가능한 단기 유동성 수단을 사람 상담에서 확인하는 "
                "항목입니다. 버퍼 부족만으로 지급불능이나 대출 필요성을 "
                "판단하지 않습니다."
            ),
            required_information=[
                "최신 원화 자금계획과 확정 입출금 일정",
                "수출대금 실제 회수일과 지연 가능성",
                "실제 사용 가능한 신용한도와 만기",
                "결제·수취 일정 조정 가능성",
            ],
            required_documents=[
                "수출 계약서 또는 인보이스",
                "최신 자금계획표와 입출금 일정",
                "기존 신용한도 확인 자료(있는 경우)",
            ],
            questions=[
                "최신 자금계획에서 목표 운영자금 버퍼를 유지하려면 어떤 "
                "일정과 조건을 확인해야 하는가?",
                "수출대금 회수시점이 바뀔 때 검토 가능한 단기 유동성 "
                "수단과 필요 서류는 무엇인가?",
                "실제 사용 가능한 신용한도·비용·심사요건은 무엇인가?",
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
