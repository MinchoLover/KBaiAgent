from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from schemas import TradeDocumentExtraction
from src.domain.confirmed_transaction_models import (
    ConfirmedTransactionSnapshot,
)
from src.domain.consultation_models import (
    ConsultationPacketResult,
    ConsultationPriorityView,
    ConsultationRationaleItem,
)
from src.domain.country_environment_models import (
    CountryTradeEnvironmentAssessment,
)


COUNTRY_NAMES = {
    "BR": "브라질",
    "KR": "한국",
    "US": "미국",
}

WORLD_BANK_LABELS = {
    "NY.GDP.MKTP.KD.ZG": ("GDP 성장률", "%"),
    "FP.CPI.TOTL.ZG": ("소비자물가 상승률", "%"),
    "BN.CAB.XOKA.GD.ZS": ("경상수지", "% of GDP"),
}

COUNTRY_REVIEW_NEED_LABELS = {
    "PAYMENT_TRANSFER_PROTECTION_REVIEW": "결제·송금 보호수단 확인",
    "CREDIT_INSURANCE_REVIEW": "신용보험 검토",
    "GUARANTEE_REVIEW": "보증 검토",
    "DOCUMENTARY_CREDIT_TERMS_REVIEW": "신용장 조건 확인",
    "PAYMENT_TERMS_REVIEW": "결제기간 확인",
    "MACRO_ENVIRONMENT_MONITORING": "거시환경 변화 확인",
    "TRADE_MARKET_ACCESS_REVIEW": "통관·관세·시장접근 확인",
    "INFORMATION_COMPLETENESS_REVIEW": "공식 자료 보완",
}

NO_FEASIBLE_REASON_LABELS = {
    "MAXIMUM_FORWARD_RATIO_EXCEEDED": (
        "설정한 신규 환율 고정 최대 비율을 만족하는 조합이 없습니다."
    ),
    "TOTAL_HEDGE_RATIO_EXCEEDED": (
        "기존 헤지를 합친 총 헤지 비율이 거래금액 범위를 넘습니다."
    ),
    "MINIMUM_TRADE_RATIO_NOT_MET": (
        "설정한 최소 거래 비율 조건을 만족하는 조합이 없습니다."
    ),
    "ACCEPTABLE_LOSS_EXCEEDED": (
        "허용 가능한 환율 추가부담 안에 드는 조합이 없습니다."
    ),
    "Q90_LOSS_LIMIT_EXCEEDED": (
        "모델 경로위험 분위수에서 허용 손실 조건을 만족하지 못합니다."
    ),
    "FIXED_10_SCENARIO_MISSING": (
        "비교에 필요한 환율 ±10% 스트레스 구간이 준비되지 않았습니다."
    ),
    "MINIMUM_CASH_BUFFER_NOT_MET": (
        "반드시 남길 운영자금 조건을 만족하는 조합이 없습니다."
    ),
    "POST_CREDIT_PAYMENT_GAP": (
        "신용한도를 반영해도 지급 또는 자금 부족이 남습니다."
    ),
}


def _decimal_or_none(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed


def _country_name(value: Optional[str]) -> str:
    if not value:
        return "국가 확인 필요"
    return COUNTRY_NAMES.get(value, value)


def _payment_method_from_terms(value: Optional[str]) -> str:
    if not value:
        return "결제방식 확인 필요"
    upper = value.upper()
    methods: List[str] = []
    if "OPEN ACCOUNT" in upper:
        methods.append("외상거래(Open Account)")
    if "T/T" in upper or "TELEGRAPHIC TRANSFER" in upper:
        methods.append("전신송금(T/T)")
    if "L/C" in upper or "LETTER OF CREDIT" in upper:
        methods.append("신용장(L/C)")
    if "D/P" in upper:
        methods.append("지급인도조건(D/P)")
    if "D/A" in upper:
        methods.append("인수인도조건(D/A)")
    if methods:
        return " / ".join(dict.fromkeys(methods))
    return value


def _advance_missing_information_display(value: str) -> str:
    parts = value.replace("선지급의", "선지급").split()
    if (
        len(parts) >= 4
        and len(parts[0]) == 3
        and parts[0].isalpha()
        and parts[2] == "선지급"
    ):
        display = "선지급 {} {} {}".format(
            parts[0],
            parts[1],
            " ".join(parts[3:]),
        )
    else:
        display = value
    normalized = display.replace("선지급의", "선지급")
    if (
        normalized.startswith("선지급 ")
        and "실제 입금" in normalized
        and "여부" in normalized
        and "확인 필요" not in normalized
    ):
        identity = normalized.split("실제 입금", 1)[0].strip()
        return "{} 실제 입금 여부 확인 필요".format(identity)
    return normalized


def rationale_item(
    value: ConsultationPacketResult,
    labels: List[str],
) -> Optional[ConsultationRationaleItem]:
    for priority in value.packet.consultation_priorities:
        for item in priority.numeric_rationale:
            if item.label in labels:
                return item
    return None


def transaction_summary(
    extraction: TradeDocumentExtraction,
    confirmed_transaction: Optional[ConfirmedTransactionSnapshot] = None,
    consultation: Optional[ConsultationPacketResult] = None,
) -> Dict[str, object]:
    trade_type = (
        confirmed_transaction.trade_type
        if confirmed_transaction is not None
        else extraction.trade_type
    )
    company_role = (
        confirmed_transaction.company_role
        if confirmed_transaction is not None
        else extraction.company_role
    )
    currency = (
        confirmed_transaction.currency
        if confirmed_transaction is not None
        else extraction.currency
    )
    amount_due = (
        confirmed_transaction.amount_due
        if confirmed_transaction is not None
        else extraction.amount_due
    )
    due_date = (
        confirmed_transaction.due_date
        if confirmed_transaction is not None
        else (
            consultation.packet.company_summary.settlement_date
            if consultation is not None
            else extraction.explicit_due_date
            or extraction.derived_due_date
        )
    )
    seller_country = (
        confirmed_transaction.seller_country
        if confirmed_transaction is not None
        else extraction.seller_country
    )
    buyer_country = (
        confirmed_transaction.buyer_country
        if confirmed_transaction is not None
        else extraction.buyer_country
    )
    payment_terms = (
        confirmed_transaction.payment_terms
        if confirmed_transaction is not None
        else extraction.payment_terms
    )
    payment_method_item = (
        rationale_item(consultation, ["결제방식"])
        if consultation is not None
        else None
    )
    payment_method = (
        payment_method_item.value
        if payment_method_item is not None
        else _payment_method_from_terms(payment_terms)
    )

    installment_rows: List[Dict[str, object]] = []
    if confirmed_transaction is not None:
        installment_rows = [
            {
                "sequence": item.sequence,
                "amount": item.amount,
                "currency": item.currency,
                "due_date": item.due_date,
                "condition": item.condition,
            }
            for item in confirmed_transaction.installments
        ]
    else:
        installment_rows = [
            {
                "sequence": item.sequence,
                "amount": item.amount,
                "currency": item.currency or currency,
                "due_date": item.due_date,
                "condition": item.condition,
            }
            for item in extraction.installments
        ]

    major_installment: Optional[Dict[str, object]] = None
    if installment_rows:
        balance_rows = [
            row
            for row in installment_rows
            if "balance" in str(row.get("condition") or "").lower()
            or "잔금" in str(row.get("condition") or "")
        ]
        candidates = balance_rows or installment_rows
        major_installment = max(
            candidates,
            key=lambda row: (
                _decimal_or_none(
                    str(row.get("amount"))
                    if row.get("amount") is not None
                    else None
                )
                or Decimal("0"),
                int(row.get("sequence") or 0),
            ),
        )

    missing_information = ""
    if consultation is not None:
        payment_gaps = [
            item
            for item in consultation.packet.missing_information
            if "입금" in item or "지급" in item
        ]
        if payment_gaps:
            missing_information = payment_gaps[0]
        elif consultation.packet.missing_information:
            missing_information = consultation.packet.missing_information[0]
    if not missing_information:
        advance_rows = [
            row
            for row in installment_rows
            if "advance" in str(row.get("condition") or "").lower()
            or "선지급" in str(row.get("condition") or "")
        ]
        if advance_rows:
            advance = advance_rows[0]
            advance_amount = _decimal_or_none(
                str(advance.get("amount"))
                if advance.get("amount") is not None
                else None
            )
            advance_amount_text = (
                format(advance_amount, ",.2f").rstrip("0").rstrip(".")
                if advance_amount is not None
                else "금액 미확인"
            )
            missing_information = (
                "{} {} 선지급 실제 입금 여부 확인 필요".format(
                    advance.get("currency") or currency or "",
                    advance_amount_text,
                ).strip()
            )
    if not missing_information:
        missing_information = "현재 확인된 핵심 누락정보 없음"
    missing_information = _advance_missing_information_display(
        missing_information
    )

    return {
        "trade_type": trade_type,
        "trade_type_label": {
            "EXPORT": "수출",
            "IMPORT": "수입",
        }.get(trade_type, "거래 방향 확인 필요"),
        "company_role": company_role,
        "company_role_label": {
            "SELLER": "판매자",
            "BUYER": "구매자",
        }.get(company_role, "역할 확인 필요"),
        "route_label": "{} 판매자 → {} 구매자".format(
            _country_name(seller_country),
            _country_name(buyer_country),
        ),
        "currency": currency,
        "amount_due": amount_due,
        "due_date": due_date,
        "payment_method": payment_method,
        "major_installment": major_installment,
        "missing_information": missing_information,
        "installments": installment_rows,
        "source_path": (
            "workflow.confirmed_transaction.due_date"
            if confirmed_transaction is not None
            else "stage0.extraction.explicit_due_date"
        ),
    }


def priority_key_rationale(
    priority: ConsultationPriorityView,
) -> List[ConsultationRationaleItem]:
    preferred_by_rank = {
        1: [
            "분석 대상 예정 수취액",
            "분석 대상 예정 지급액",
            "잔금 예정",
            "결제방식",
        ],
        2: [
            "예정 수취 노출액",
            "예정 지급 노출액",
            "기준 대비 감소",
            "기준 대비 증가",
            "사용자 허용손실",
        ],
        3: [
            "-5% ending cash",
            "+5% ending cash",
            "목표 buffer",
            "buffer shortfall",
        ],
    }
    labels = preferred_by_rank.get(priority.rank, [])
    selected: List[ConsultationRationaleItem] = []
    for label in labels:
        item = next(
            (
                candidate
                for candidate in priority.numeric_rationale
                if candidate.label == label
            ),
            None,
        )
        if item is not None and item not in selected:
            selected.append(item)
        if len(selected) == 3:
            return selected
    for item in priority.numeric_rationale:
        if item not in selected:
            selected.append(item)
        if len(selected) == 3:
            break
    return selected


def priority_risk_sentence(priority: ConsultationPriorityView) -> str:
    first_sentence = priority.priority_reason.split(". ", 1)[0].strip()
    if first_sentence and not first_sentence.endswith("."):
        first_sentence += "."
    return first_sentence or priority.priority_reason


def country_summary(
    assessment: CountryTradeEnvironmentAssessment,
) -> Dict[str, object]:
    review_labels = {
        "HIGH_REVIEW": "우선 검토 필요",
        "ELEVATED_REVIEW": "추가 검토 필요",
        "STANDARD_REVIEW": "통상 검토",
        "INSUFFICIENT_INFORMATION": "정보 부족",
    }
    verified_dates = [
        item.verified_at
        for item in assessment.official_source_references
        if item.verified_at
    ]
    return {
        "country": _country_name(assessment.country),
        "review_label": review_labels[assessment.review_priority],
        "review_needs": [
            COUNTRY_REVIEW_NEED_LABELS[item]
            for item in assessment.review_needs[:2]
        ],
        "verified_at": max(verified_dates) if verified_dates else "확인 필요",
    }


def world_bank_display(
    indicator_code: str,
    raw_value: Optional[str],
    raw_status: str,
) -> str:
    label, unit = WORLD_BANK_LABELS.get(
        indicator_code,
        (indicator_code, ""),
    )
    parsed = _decimal_or_none(raw_value)
    if parsed is None:
        return "{} · {}".format(label, raw_status)
    rounded = parsed.quantize(Decimal("0.1"))
    return "{} {}{}".format(label, format(rounded, "f"), unit)


def no_feasible_reason_copy(reasons: List[str]) -> List[str]:
    return [
        NO_FEASIBLE_REASON_LABELS[reason]
        for reason in reasons
        if reason in NO_FEASIBLE_REASON_LABELS
    ]
