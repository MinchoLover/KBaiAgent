import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Set

from src.domain.trade_risk_models import (
    ProtectionMechanism,
    TradeRiskConfirmationRecord,
    TradeRiskFactor,
    TradeRiskReviewNeed,
    TradeSettlementRiskAssessment,
    TradeSettlementRiskInput,
)


TRADE_RISK_CALCULATION_VERSION = "trade-settlement-risk-1.0"
TRADE_RISK_RULE_VERSION = "trade-settlement-rules-1.0"
LONG_TERM_REVIEW_DAYS = 90
TRADE_RISK_DISCLAIMER = (
    "본 결과는 확인된 거래조건을 이용한 공모전 MVP의 결정론적 "
    "사전검토 우선도이며 금융기관의 공식 심사등급, 부도확률 또는 "
    "보험 인수판단이 아닙니다."
)

IMPORT_APPLICABLE_PROTECTIONS = {
    "ADVANCE_PAYMENT_GUARANTEE",
    "PERFORMANCE_GUARANTEE",
}
EXPORT_APPLICABLE_PROTECTIONS = {
    "PAYMENT_GUARANTEE",
    "EXPORT_CREDIT_INSURANCE",
    "STANDBY_LETTER_OF_CREDIT",
}
EXPORT_RISKY_PAYMENT_METHODS = {
    "OPEN_ACCOUNT",
    "DOCUMENTARY_COLLECTION_DA",
}


def trade_risk_fingerprint(value: TradeSettlementRiskInput) -> str:
    serialized = json.dumps(
        value.model_dump(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def create_trade_risk_confirmation(
    *,
    confirmed_input: TradeSettlementRiskInput,
    confirmed_by: Optional[str] = None,
    confirmed_at: Optional[str] = None,
) -> TradeRiskConfirmationRecord:
    return TradeRiskConfirmationRecord(
        confirmed_input=confirmed_input,
        confirmed_at=(
            confirmed_at or datetime.now(timezone.utc).isoformat()
        ),
        confirmed_by=confirmed_by,
        trade_risk_sha256=trade_risk_fingerprint(confirmed_input),
    )


def _factor(
    code: str,
    effect: str,
    reason: str,
    *evidence_refs: str,
) -> TradeRiskFactor:
    return TradeRiskFactor(
        code=code,
        effect=effect,
        reason=reason,
        evidence_refs=list(evidence_refs),
        rule_version=TRADE_RISK_RULE_VERSION,
    )


def _applicable_types(
    mechanisms: List[ProtectionMechanism],
    allowed_types: Set[str],
) -> Set[str]:
    return {
        item.protection_type
        for item in mechanisms
        if (
            item.applicability_status == "CONFIRMED_APPLICABLE"
            and item.protection_type in allowed_types
        )
    }


def _unverified_types(
    mechanisms: List[ProtectionMechanism],
) -> List[str]:
    return [
        item.protection_type
        for item in mechanisms
        if item.applicability_status == "PRESENT_SCOPE_UNVERIFIED"
    ]


def _other_direction_types(
    mechanisms: List[ProtectionMechanism],
    allowed_types: Set[str],
) -> List[str]:
    return [
        item.protection_type
        for item in mechanisms
        if item.protection_type not in allowed_types
    ]


def _dedupe(values: List[str]) -> List[str]:
    return list(dict.fromkeys(values))


def _ratio_percent(value: Decimal) -> str:
    percent = value * Decimal("100")
    return format(percent.normalize(), "f")


def _import_assessment(
    value: TradeSettlementRiskInput,
) -> TradeSettlementRiskAssessment:
    factors: List[TradeRiskFactor] = []
    gaps: List[str] = []
    warnings: List[str] = [TRADE_RISK_DISCLAIMER]
    needs: List[TradeRiskReviewNeed] = []
    ratio = (
        Decimal(value.advance_payment_ratio)
        if value.advance_payment_ratio is not None
        else None
    )

    if value.counterparty_relationship == "UNKNOWN":
        gaps.append("거래처가 신규인지 기존인지 확인이 필요합니다.")
        factors.append(
            _factor(
                "COUNTERPARTY_RELATIONSHIP_UNKNOWN",
                "INFORMATION_GAP",
                gaps[-1],
                "trade_risk_input.counterparty_relationship",
            )
        )
    elif value.counterparty_relationship == "NEW":
        factors.append(
            _factor(
                "NEW_COUNTERPARTY",
                "RISK_SIGNAL",
                "신규 거래처와의 수입 거래입니다.",
                "trade_risk_input.counterparty_relationship",
            )
        )

    if ratio is None:
        gaps.append("선지급 비율을 확인해야 합니다.")
        factors.append(
            _factor(
                "ADVANCE_PAYMENT_RATIO_UNKNOWN",
                "INFORMATION_GAP",
                gaps[-1],
                "trade_risk_input.advance_payment_ratio",
            )
        )
    elif ratio > 0:
        factors.append(
            _factor(
                "IMPORT_ADVANCE_PAYMENT",
                "RISK_SIGNAL",
                "수입대금의 {}%가 선지급 조건입니다.".format(
                    _ratio_percent(ratio)
                ),
                "trade_risk_input.advance_payment_ratio",
            )
        )
        needs.append("ADVANCE_PAYMENT_PROTECTION_REVIEW")

    applicable = _applicable_types(
        value.protection_mechanisms,
        IMPORT_APPLICABLE_PROTECTIONS,
    )
    if ratio is not None and ratio > 0:
        if value.protection_information_status == "UNKNOWN":
            gaps.append("선지급 보호수단의 존재와 적용범위를 확인해야 합니다.")
            factors.append(
                _factor(
                    "IMPORT_PROTECTION_UNKNOWN",
                    "INFORMATION_GAP",
                    gaps[-1],
                    "trade_risk_input.protection_information_status",
                )
            )
        elif applicable:
            factors.append(
                _factor(
                    "APPLICABLE_IMPORT_PROTECTION",
                    "MITIGANT",
                    "이 거래에 적용되는 선급금·이행 보호수단이 확인됐습니다.",
                    "trade_risk_input.protection_mechanisms",
                )
            )
        else:
            reason = (
                "선지급 보호수단이 없다고 확인했습니다."
                if value.protection_information_status == "NONE_CONFIRMED"
                else "입력된 보호수단의 선지급 적용범위가 확인되지 않았습니다."
            )
            factors.append(
                _factor(
                    "NO_APPLICABLE_IMPORT_PROTECTION",
                    "RISK_SIGNAL",
                    reason,
                    "trade_risk_input.protection_information_status",
                )
            )

    unverified = _unverified_types(value.protection_mechanisms)
    if unverified:
        warnings.append(
            "존재만 확인된 보호수단은 위험 완화에 반영하지 않았습니다: {}".format(
                ", ".join(unverified)
            )
        )
    other_direction = _other_direction_types(
        value.protection_mechanisms,
        IMPORT_APPLICABLE_PROTECTIONS,
    )
    if other_direction:
        warnings.append(
            "수입 선지급 위험과 직접 대응하지 않는 보호수단은 감경하지 "
            "않았습니다: {}".format(", ".join(other_direction))
        )

    no_applicable = not applicable
    if gaps:
        priority = "UNKNOWN"
        needs.append("HUMAN_REVIEW")
    elif (
        value.counterparty_relationship == "NEW"
        and ratio is not None
        and ratio > 0
        and no_applicable
    ):
        priority = "HIGH_REVIEW"
    elif (
        value.counterparty_relationship == "NEW"
        or (
            ratio is not None
            and ratio > 0
            and no_applicable
        )
    ):
        priority = "ELEVATED_REVIEW"
    else:
        priority = "STANDARD_REVIEW"

    return TradeSettlementRiskAssessment(
        calculation_version=TRADE_RISK_CALCULATION_VERSION,
        input_fingerprint=trade_risk_fingerprint(value),
        risk_type="IMPORT_PREPAYMENT_PERFORMANCE_RISK",
        review_priority=priority,
        factors=factors,
        review_needs=_dedupe(needs),
        information_gaps=_dedupe(gaps),
        warnings=_dedupe(warnings),
        assumptions=[],
    )


def _export_assessment(
    value: TradeSettlementRiskInput,
) -> TradeSettlementRiskAssessment:
    factors: List[TradeRiskFactor] = []
    gaps: List[str] = []
    warnings: List[str] = [TRADE_RISK_DISCLAIMER]
    needs: List[TradeRiskReviewNeed] = []
    ratio = (
        Decimal(value.advance_payment_ratio)
        if value.advance_payment_ratio is not None
        else None
    )

    if value.counterparty_relationship == "UNKNOWN":
        gaps.append("거래처가 신규인지 기존인지 확인이 필요합니다.")
        factors.append(
            _factor(
                "COUNTERPARTY_RELATIONSHIP_UNKNOWN",
                "INFORMATION_GAP",
                gaps[-1],
                "trade_risk_input.counterparty_relationship",
            )
        )
    elif value.counterparty_relationship == "NEW":
        factors.append(
            _factor(
                "NEW_COUNTERPARTY",
                "RISK_SIGNAL",
                "신규 거래처와의 수출 거래입니다.",
                "trade_risk_input.counterparty_relationship",
            )
        )

    if ratio is None:
        gaps.append("계약상 선지급 비율을 확인해야 합니다.")
        factors.append(
            _factor(
                "ADVANCE_PAYMENT_RATIO_UNKNOWN",
                "INFORMATION_GAP",
                gaps[-1],
                "trade_risk_input.advance_payment_ratio",
            )
        )

    method = value.balance_payment_method
    risky_method = method in EXPORT_RISKY_PAYMENT_METHODS
    collection_unspecified = method == "DOCUMENTARY_COLLECTION_UNSPECIFIED"
    if method == "UNKNOWN":
        gaps.append("잔여 수출대금의 결제방식을 확인해야 합니다.")
        factors.append(
            _factor(
                "BALANCE_PAYMENT_METHOD_UNKNOWN",
                "INFORMATION_GAP",
                gaps[-1],
                "trade_risk_input.balance_payment_method",
            )
        )
    elif method == "OPEN_ACCOUNT":
        factors.append(
            _factor(
                "EXPORT_OPEN_ACCOUNT",
                "RISK_SIGNAL",
                "잔여 수출대금이 Open Account 방식입니다.",
                "trade_risk_input.balance_payment_method",
            )
        )
    elif method == "DOCUMENTARY_COLLECTION_DA":
        factors.append(
            _factor(
                "EXPORT_DOCUMENTARY_COLLECTION_DA",
                "RISK_SIGNAL",
                "D/A 추심은 은행의 지급보증 없이 만기 지급약속에 의존합니다.",
                "trade_risk_input.balance_payment_method",
            )
        )
    elif collection_unspecified:
        gaps.append("추심 방식이 D/P인지 D/A인지 확인해야 합니다.")
        factors.append(
            _factor(
                "DOCUMENTARY_COLLECTION_TYPE_UNKNOWN",
                "INFORMATION_GAP",
                gaps[-1],
                "trade_risk_input.balance_payment_method",
            )
        )
        needs.append("TRADE_TERMS_REVIEW")
    elif method == "DOCUMENTARY_CREDIT":
        factors.append(
            _factor(
                "DOCUMENTARY_CREDIT_DETAILS_NOT_ASSESSED",
                "INFORMATION_GAP",
                "신용장 방식이지만 확인 여부·발행은행·서류조건은 심사하지 않았습니다.",
                "trade_risk_input.balance_payment_method",
            )
        )
        needs.append("DOCUMENTARY_CREDIT_TERMS_REVIEW")

    remaining_balance = ratio is None or ratio < 1
    if remaining_balance:
        if value.payment_term_basis in {
            "UNKNOWN",
            "EVENT_BASED_UNRESOLVED",
        }:
            gaps.append("잔여대금 회수기간을 확정할 기준정보가 부족합니다.")
            factors.append(
                _factor(
                    "PAYMENT_TERM_UNRESOLVED",
                    "INFORMATION_GAP",
                    gaps[-1],
                    "trade_risk_input.payment_term_basis",
                )
            )
            needs.append("TRADE_TERMS_REVIEW")
        elif value.payment_term_days is not None:
            if value.payment_term_days >= LONG_TERM_REVIEW_DAYS:
                factors.append(
                    _factor(
                        "LONG_EXPORT_PAYMENT_TERM",
                        "RISK_SIGNAL",
                        "잔여 수출대금 회수기간이 {}일입니다.".format(
                            value.payment_term_days
                        ),
                        "trade_risk_input.payment_term_days",
                    )
                )

    long_term = bool(
        value.payment_term_days is not None
        and value.payment_term_days >= LONG_TERM_REVIEW_DAYS
    )
    needs_protection = risky_method or long_term
    applicable = _applicable_types(
        value.protection_mechanisms,
        EXPORT_APPLICABLE_PROTECTIONS,
    )
    if needs_protection:
        needs.append("RECEIVABLE_PROTECTION_REVIEW")
        if value.protection_information_status == "UNKNOWN":
            gaps.append("수출대금 회수 보호수단의 적용여부를 확인해야 합니다.")
            factors.append(
                _factor(
                    "EXPORT_PROTECTION_UNKNOWN",
                    "INFORMATION_GAP",
                    gaps[-1],
                    "trade_risk_input.protection_information_status",
                )
            )
        elif applicable:
            factors.append(
                _factor(
                    "APPLICABLE_EXPORT_PROTECTION",
                    "MITIGANT",
                    "이 거래에 적용되는 수출대금 회수 보호수단이 확인됐습니다.",
                    "trade_risk_input.protection_mechanisms",
                )
            )
        else:
            reason = (
                "수출대금 회수 보호수단이 없다고 확인했습니다."
                if value.protection_information_status == "NONE_CONFIRMED"
                else "입력된 보호수단의 회수위험 적용범위가 확인되지 않았습니다."
            )
            factors.append(
                _factor(
                    "NO_APPLICABLE_EXPORT_PROTECTION",
                    "RISK_SIGNAL",
                    reason,
                    "trade_risk_input.protection_information_status",
                )
            )

    unverified = _unverified_types(value.protection_mechanisms)
    if unverified:
        warnings.append(
            "존재만 확인된 보호수단은 위험 완화에 반영하지 않았습니다: {}".format(
                ", ".join(unverified)
            )
        )
    other_direction = _other_direction_types(
        value.protection_mechanisms,
        EXPORT_APPLICABLE_PROTECTIONS,
    )
    if other_direction:
        warnings.append(
            "수출 회수위험과 직접 대응하지 않는 보호수단은 감경하지 "
            "않았습니다: {}".format(", ".join(other_direction))
        )

    high_combination = bool(
        value.counterparty_relationship == "NEW"
        and risky_method
        and long_term
    )
    if gaps:
        priority = "UNKNOWN"
        needs.append("HUMAN_REVIEW")
    elif high_combination and not applicable:
        priority = "HIGH_REVIEW"
    elif (
        high_combination
        or value.counterparty_relationship == "NEW"
        or risky_method
        or long_term
        or collection_unspecified
    ):
        priority = "ELEVATED_REVIEW"
    else:
        priority = "STANDARD_REVIEW"

    if ratio == 1:
        warnings.append(
            "전액 선지급 조건은 실제 입금 확인 전까지 수취 완료로 보지 않습니다."
        )
        needs.append("TRADE_TERMS_REVIEW")

    return TradeSettlementRiskAssessment(
        calculation_version=TRADE_RISK_CALCULATION_VERSION,
        input_fingerprint=trade_risk_fingerprint(value),
        risk_type="EXPORT_RECEIVABLE_COLLECTION_RISK",
        review_priority=priority,
        factors=factors,
        review_needs=_dedupe(needs),
        information_gaps=_dedupe(gaps),
        warnings=_dedupe(warnings),
        assumptions=[
            "{}일은 공식 신용등급 경계가 아니라 MVP의 장기조건 "
            "추가 검토 기준입니다.".format(LONG_TERM_REVIEW_DAYS)
        ],
    )


def assess_trade_settlement_risk(
    confirmation: TradeRiskConfirmationRecord,
) -> TradeSettlementRiskAssessment:
    expected = trade_risk_fingerprint(confirmation.confirmed_input)
    if expected != confirmation.trade_risk_sha256:
        raise ValueError("거래위험 확인 snapshot의 fingerprint가 일치하지 않습니다.")
    if confirmation.confirmed_input.trade_type == "IMPORT":
        return _import_assessment(confirmation.confirmed_input)
    return _export_assessment(confirmation.confirmed_input)
