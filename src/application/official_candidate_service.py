from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from src.consultation.review_area import CATEGORY_TO_REVIEW_AREA
from src.domain.consultation_models import (
    ConsultationPacket,
    ConsultationTopic,
)
from src.domain.confirmed_transaction_models import (
    ConfirmedTransactionSnapshot,
)
from src.domain.product_models import (
    AuxiliaryServiceCandidate,
    AuxiliaryServiceCandidates,
    OfficialCandidateEvaluation,
    OfficialCandidateShortlist,
    OfficialCandidateInputProfile,
    ProductCandidate,
    ProductRecord,
    Stage4Result,
    assess_official_candidate_input_profile,
)
from src.domain.trade_risk_models import TradeRiskConfirmationRecord
from src.stage4.official_search import is_official_url
from src.stage4.local_kb import active_official_catalogue_by_id


MAX_OFFICIAL_CANDIDATES = 3

PROFILE_RELATED_CATALOGUE_IDS = {
    "ksure_export_credit_guarantee_pre_shipment",
    "ksure_export_credit_guarantee_post_shipment",
    "ksure_export_credit_guarantee_purchase",
    "ksure_export_credit_guarantee_comprehensive_purchase",
    "kb_non_lc_export_bill_purchase",
    "kosmes_export_funding",
}

CONSULTATION_PRODUCT_CATEGORIES: Dict[str, List[str]] = {
    "IMPORT_ADVANCE_PAYMENT_PROTECTION": [
        "IMPORT_ADVANCE_PAYMENT_INSURANCE",
    ],
    "EXPORT_RECEIVABLE_PROTECTION": [
        "EXPORT_CREDIT_INSURANCE",
    ],
    "FX_RISK_MANAGEMENT": [
        "FORWARD",
        "FX_RISK_INSURANCE",
        "FX_RISK_INSURANCE_OPTION",
    ],
    "FX_BALANCE_UTILIZATION": [
        "FX_DEPOSIT",
    ],
    "IMPORT_SETTLEMENT_FINANCE": [
        "TRADE_FINANCE_LOAN",
    ],
    "PAYMENT_CAPACITY_REVIEW": [
        "TRADE_FINANCE_LOAN",
        "EXPORT_CREDIT_GUARANTEE",
    ],
    "EXPORT_LIQUIDITY_REVIEW": [
        "EXPORT_CREDIT_GUARANTEE",
        "EXPORT_RECEIVABLE_PURCHASE",
        "TRADE_FINANCE_LOAN",
    ],
    "EXPORT_RECEIPT_MANAGEMENT": [
        "FORWARD",
        "FX_RISK_INSURANCE",
        "FX_RISK_INSURANCE_OPTION",
        "FX_DEPOSIT",
    ],
    "EXPLICIT_POLICY_FINANCE_REVIEW": [
        "POLICY_FINANCE",
    ],
}

CONSULTATION_QUERY_TERMS: Dict[str, List[str]] = {
    "IMPORT_ADVANCE_PAYMENT_PROTECTION": [
        "수입보험",
        "수입자용",
        "선급금",
        "미회수",
        "IMPORT_ADVANCE_PAYMENT_INSURANCE",
    ],
    "EXPORT_RECEIVABLE_PROTECTION": [
        "단기수출보험",
        "수출대금",
        "미회수",
        "EXPORT_CREDIT_INSURANCE",
    ],
    "DOCUMENTARY_CREDIT_TERMS_REVIEW": [
        "신용장",
        "확인신용장",
        "서류조건",
    ],
    "PAYMENT_TERMS_REVIEW": [
        "D/P",
        "D/A",
        "결제조건",
    ],
    "FX_RISK_MANAGEMENT": [
        "선물환",
        "환변동보험",
        "환율관리",
    ],
    "FX_BALANCE_UTILIZATION": [
        "외화예금",
        "보유외화",
    ],
    "IMPORT_SETTLEMENT_FINANCE": [
        "수입결제자금",
        "수출입대출",
    ],
    "PAYMENT_CAPACITY_REVIEW": [
        "수출입대출",
        "운전자금",
        "보증",
    ],
    "EXPORT_RECEIPT_MANAGEMENT": [
        "수출채권",
        "수출신용보증",
        "매입외환",
    ],
    "EXPORT_LIQUIDITY_REVIEW": [
        "수출채권",
        "운전자금",
        "수출신용보증",
    ],
}

CONSULTATION_PRIORITY = [
    "IMPORT_ADVANCE_PAYMENT_PROTECTION",
    "EXPORT_RECEIVABLE_PROTECTION",
    "DOCUMENTARY_CREDIT_TERMS_REVIEW",
    "PAYMENT_TERMS_REVIEW",
    "PAYMENT_CAPACITY_REVIEW",
    "IMPORT_SETTLEMENT_FINANCE",
    "EXPORT_RECEIPT_MANAGEMENT",
    "EXPORT_LIQUIDITY_REVIEW",
    "FX_RISK_MANAGEMENT",
    "FX_BALANCE_UTILIZATION",
]

SIGNAL_REASON_LABELS: Dict[str, str] = {
    "IS_EXPORT": "확정 거래방향이 수출입니다.",
    "IS_IMPORT": "확정 거래방향이 수입입니다.",
    "COMPANY_IS_SELLER": "확정 거래에서 회사 역할이 판매자입니다.",
    "COMPANY_IS_BUYER": "확정 거래에서 회사 역할이 구매자입니다.",
    "HAS_EXPORT_RECEIVABLE": "확정 수출대금 수취 노출이 있습니다.",
    "OPEN_ACCOUNT": "확정 결제조건에 Open Account가 포함됩니다.",
    "NO_LC": "신용장 보호가 확인되지 않았습니다.",
    "INSURANCE_NOT_CONFIRMED": "현재 거래에 적용되는 보험이 확인되지 않았습니다.",
    "GUARANTEE_NOT_CONFIRMED": "현재 거래에 적용되는 지급보증이 확인되지 않았습니다.",
    "HAS_FX_EXPOSURE": "검증된 계산에 미헤지 외화 노출이 있습니다.",
    "EXPORT_RECEIPT_EXPOSURE": "수출 외화수취 노출이 있습니다.",
    "IMPORT_PAYMENT_EXPOSURE": "수입 외화지급 노출이 있습니다.",
    "FX_LOSS_EXCEEDS_TOLERANCE": "검증된 시나리오에서 허용손실 초과 신호가 있습니다.",
    "NO_CONFIRMED_HEDGE": "계산 입력에서 기존 헤지가 확인되지 않았습니다.",
    "DUE_DATE_AVAILABLE": "확정 결제일이 있습니다.",
    "IMPORT_SETTLEMENT_FUNDING_NEED": "수입 결제자금 검토 항목이 명시적으로 생성됐습니다.",
    "COLLECTION_PROTECTION": "상담 검토 분야에 수출대금 회수 보호가 있습니다.",
    "FX_MANAGEMENT": "상담 검토 분야에 환율 관리가 있습니다.",
    "PAYMENT_TERMS": "상담 검토 분야에 결제조건 보강이 있습니다.",
    "WORKING_CAPITAL_TRADE_FINANCE": "상담 검토 분야에 무역금융·운영자금이 있습니다.",
    "POLICY_FINANCE": "상담 검토 분야에 정책자금 검토가 명시돼 있습니다.",
    "EXPLICIT_POLICY_FINANCE_REVIEW": "정책자금 검토가 명시적으로 존재합니다.",
    "EXPORT_PRE_SHIPMENT_FUNDING_NEED": "선적 전 수출이행 자금 목적이 명시됐습니다.",
    "BANK_FINANCING_INTENT": "금융기관 자금조달 상담 의사가 확인됐습니다.",
    "SHIPMENT_COMPLETED": "선적 완료 상태가 사용자 확인됐습니다.",
    "EXPORT_POST_SHIPMENT_LIQUIDITY_NEED": "선적 후 수출채권 금융 수요가 확인됐습니다.",
    "RECEIVABLE_PURCHASE_OR_NEGO_INTENT": "수출채권 매입·네고 의사가 확인됐습니다.",
    "NON_LC_CONFIRMED": "무신용장 결제방식이 사용자 확인됐습니다.",
    "REPAYMENT_RESPONSIBILITY_ACKNOWLEDGED": "수출자의 최종 상환책임 고지를 확인했습니다.",
    "EARLY_CASH_CONVERSION_INTENT": "수출채권 조기 현금화 의사가 확인됐습니다.",
    "BANK_RECEIVABLE_PURCHASE_INTENT": "은행 수출채권 매입 상담 의사가 확인됐습니다.",
    "COMPANY_SME_STATUS_CONFIRMED": "중소기업 해당 사실이 확인됐습니다.",
    "EXPORT_EXPANSION_OR_MARKET_ENTRY_PURPOSE": "수출 확대·시장진출 목적이 확인됐습니다.",
    "PRODUCTION_FACILITY_OR_WORKING_CAPITAL_NEED": "생산설비·운전자금 용도가 확인됐습니다.",
}


def build_official_candidate_query(
    *,
    consultation_topics: List[ConsultationTopic],
    additional_terms: Optional[List[str]] = None,
) -> str:
    terms: List[str] = []
    for topic in consultation_topics:
        terms.extend(
            CONSULTATION_QUERY_TERMS.get(topic.category, [])
        )
    terms.extend(additional_terms or [])
    return " ".join(
        dict.fromkeys(
            item.strip()
            for item in terms
            if item and item.strip()
        )
    )


def _candidate_score(value: ProductCandidate) -> Decimal:
    try:
        score = Decimal(value.relevance_score)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return score if score.is_finite() else Decimal("0")


def _priority(category: str) -> int:
    try:
        return CONSULTATION_PRIORITY.index(category)
    except ValueError:
        return len(CONSULTATION_PRIORITY)


def _matches(
    *,
    candidate: ProductCandidate,
    consultation_categories: List[str],
) -> List[str]:
    return [
        category
        for category in consultation_categories
        if candidate.category
        in CONSULTATION_PRODUCT_CATEGORIES.get(category, [])
    ]


def _decimal_is_positive(value: str) -> bool:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return False
    return parsed.is_finite() and parsed > 0


def _review_area_ids(
    *,
    consultation_categories: List[str],
    consultation_packet: Optional[ConsultationPacket],
) -> List[str]:
    if consultation_packet is not None:
        return list(
            dict.fromkeys(
                item.review_area_id
                for item in consultation_packet.consultation_review_areas
            )
        )
    return list(
        dict.fromkeys(
            CATEGORY_TO_REVIEW_AREA[category]
            for category in consultation_categories
            if category in CATEGORY_TO_REVIEW_AREA
        )
    )


def _confirmed_trade_risk_signals(
    confirmation: Optional[TradeRiskConfirmationRecord],
) -> Set[str]:
    if confirmation is None:
        return set()
    confirmed = confirmation.confirmed_input
    signals: Set[str] = set()
    relationship_source = confirmed.field_sources.get(
        "counterparty_relationship",
        "UNKNOWN",
    )
    if relationship_source != "UNKNOWN":
        if confirmed.counterparty_relationship == "NEW":
            signals.add("COUNTERPARTY_NEW")
    elif confirmed.counterparty_relationship == "UNKNOWN":
        signals.add("COUNTERPARTY_INFORMATION_STATUS_UNKNOWN")

    method_source = confirmed.field_sources.get(
        "balance_payment_method",
        "UNKNOWN",
    )
    method = confirmed.balance_payment_method
    if method_source != "UNKNOWN":
        if method == "DOCUMENTARY_CREDIT":
            signals.add("HAS_LC")
        elif method in {
            "OPEN_ACCOUNT",
            "DOCUMENTARY_COLLECTION_DP",
            "DOCUMENTARY_COLLECTION_DA",
        }:
            signals.update(
                {
                    "NON_LC_CONFIRMED",
                    "ELIGIBLE_NON_LC_PAYMENT_METHOD",
                }
            )
            method_signal = {
                "OPEN_ACCOUNT": "PAYMENT_METHOD_OA",
                "DOCUMENTARY_COLLECTION_DP": "PAYMENT_METHOD_DP",
                "DOCUMENTARY_COLLECTION_DA": "PAYMENT_METHOD_DA",
            }[method]
            signals.add(method_signal)
            if method == "OPEN_ACCOUNT":
                signals.add("OPEN_ACCOUNT")
    elif method == "UNKNOWN":
        signals.update({"PAYMENT_METHOD_UNKNOWN", "LC_STATUS_UNKNOWN"})
    return signals


def _profile_signals(
    profile: Optional[OfficialCandidateInputProfile],
) -> Set[str]:
    if profile is None:
        return set()
    signals: Set[str] = set()

    if profile.shipment_status == "PRE_SHIPMENT":
        signals.add("PRE_SHIPMENT_TRANSACTION")
    elif profile.shipment_status == "COMPLETED":
        signals.add("SHIPMENT_COMPLETED")
    else:
        signals.add("SHIPMENT_STATUS_UNKNOWN")

    if profile.receivable_status == "EXISTS":
        signals.add("HAS_EXPORT_RECEIVABLE")
    elif profile.receivable_status == "UNKNOWN":
        signals.add("RECEIVABLE_STATUS_UNKNOWN")

    if profile.trade_form in {"GENERAL_EXPORT", "PROCESSING_TRADE"}:
        signals.add("TRADE_FORM_ELIGIBLE")
    elif profile.trade_form == "INTERMEDIARY_TRADE":
        signals.add("INTERMEDIARY_OR_RESALE_TRADE")
    elif profile.trade_form == "RESALE_TRADE":
        signals.update({"INTERMEDIARY_OR_RESALE_TRADE", "RESALE_TRADE"})
    else:
        signals.add("TRADE_FORM_UNKNOWN")

    relationship_signals = {
        "SINGLE_ONE_OFF": {"SINGLE_TRANSACTION_ONLY", "SINGLE_BUYER_ONLY"},
        "RECURRING_SINGLE_BUYER": {
            "RECURRING_EXPORT_TRANSACTIONS",
            "SINGLE_BUYER_ONLY",
        },
        "RECURRING_MULTIPLE_BUYERS": {
            "RECURRING_EXPORT_TRANSACTIONS",
            "MULTIPLE_BUYERS",
        },
        "UNKNOWN": {
            "RECURRING_TRANSACTION_STATUS_UNKNOWN",
            "BUYER_SCOPE_UNKNOWN",
        },
    }
    signals.update(relationship_signals[profile.relationship_scope])

    if profile.credit_information_status == "INSUFFICIENT":
        signals.add("COUNTERPARTY_CREDIT_INFORMATION_INSUFFICIENT")
    elif profile.credit_information_status == "UNKNOWN":
        signals.add("COUNTERPARTY_INFORMATION_STATUS_UNKNOWN")
    if profile.credit_investigation_intent == "YES":
        signals.add("BUYER_CREDIT_INVESTIGATION_REQUIRED")
    elif profile.credit_investigation_intent == "UNKNOWN":
        signals.add("COUNTERPARTY_INFORMATION_STATUS_UNKNOWN")

    purpose_signals = {
        "MANUFACTURING": "MANUFACTURING_FUNDING_USE",
        "PROCESSING": "PROCESSING_FUNDING_USE",
        "RAW_MATERIAL_PROCUREMENT": "RAW_MATERIAL_PROCUREMENT_USE",
        "FINISHED_GOODS_PROCUREMENT": "FINISHED_GOODS_PROCUREMENT_USE",
        "EXPORT_PERFORMANCE": "EXPORT_PERFORMANCE_FUNDING_USE",
    }
    for purpose in profile.funding_purposes:
        signal = purpose_signals.get(purpose)
        if signal:
            signals.add(signal)
    if any(item in purpose_signals for item in profile.funding_purposes):
        signals.add("EXPORT_PRE_SHIPMENT_FUNDING_NEED")
    if "RECEIVABLE_EARLY_CASH_CONVERSION" in profile.funding_purposes:
        signals.add("EXPORT_POST_SHIPMENT_LIQUIDITY_NEED")
    if any(
        item in {"GENERAL_WORKING_CAPITAL", "PRODUCTION_FACILITY"}
        for item in profile.funding_purposes
    ):
        signals.add("PRODUCTION_FACILITY_OR_WORKING_CAPITAL_NEED")
    if profile.funding_purposes == ["UNKNOWN"]:
        signals.update(
            {"PRE_SHIPMENT_FUNDING_USE_UNKNOWN", "FUNDING_PURPOSE_UNKNOWN"}
        )

    if profile.receivable_financing_intent in {
        "NEGO_OR_PURCHASE",
        "KB_RECEIVABLE_PURCHASE",
    }:
        signals.update(
            {
                "RECEIVABLE_PURCHASE_OR_NEGO_INTENT",
                "EXPORT_POST_SHIPMENT_LIQUIDITY_NEED",
            }
        )
        if profile.receivable_financing_intent == "KB_RECEIVABLE_PURCHASE":
            signals.add("BANK_RECEIVABLE_PURCHASE_INTENT")
    elif profile.receivable_financing_intent == "NONE":
        signals.add("RECEIVABLE_PURCHASE_NOT_NEEDED")
    else:
        signals.update(
            {
                "RECEIVABLE_PURCHASE_INTENT_UNKNOWN",
                "BANK_RECEIVABLE_PURCHASE_INTENT_UNKNOWN",
                "POST_SHIPMENT_LIQUIDITY_NEED_UNKNOWN",
            }
        )

    if profile.early_cash_conversion_intent == "YES":
        signals.update(
            {
                "EARLY_CASH_CONVERSION_INTENT",
                "EXPORT_POST_SHIPMENT_LIQUIDITY_NEED",
            }
        )
    elif profile.early_cash_conversion_intent == "NO":
        signals.add("EARLY_CASH_CONVERSION_NOT_NEEDED")
    elif profile.early_cash_conversion_intent == "UNKNOWN":
        signals.add("EARLY_CASH_CONVERSION_INTENT_UNKNOWN")

    if profile.bank_financing_intent == "YES":
        signals.add("BANK_FINANCING_INTENT")
    elif profile.bank_financing_intent == "UNKNOWN":
        signals.add("BANK_FINANCING_INTENT_UNKNOWN")

    if profile.repayment_responsibility_acknowledgement == "ACKNOWLEDGED":
        signals.add("REPAYMENT_RESPONSIBILITY_ACKNOWLEDGED")
    elif profile.repayment_responsibility_acknowledgement == "UNKNOWN":
        signals.add("REPAYMENT_RESPONSIBILITY_UNKNOWN")

    if (
        profile.short_term_export_insurance_linkage_review
        == "AGREED_TO_REVIEW"
    ):
        signals.add("SHORT_TERM_EXPORT_INSURANCE_LINKAGE_REVIEW")
    elif profile.short_term_export_insurance_linkage_review == "UNKNOWN":
        signals.add("SHORT_TERM_EXPORT_INSURANCE_LINKAGE_UNKNOWN")

    if profile.sme_status == "CONFIRMED":
        signals.add("COMPANY_SME_STATUS_CONFIRMED")
    elif profile.sme_status == "NOT_CONFIRMED":
        signals.add("COMPANY_SME_STATUS_NOT_CONFIRMED")
    else:
        signals.add("SME_STATUS_UNKNOWN")
    if profile.annual_export_band == "UNKNOWN":
        signals.add("EXPORT_PERFORMANCE_UNKNOWN")
    if profile.market_entry_purpose == "YES":
        signals.add("EXPORT_EXPANSION_OR_MARKET_ENTRY_PURPOSE")
    elif profile.market_entry_purpose == "UNKNOWN":
        signals.add("EXPORT_EXPANSION_PURPOSE_UNKNOWN")
    if profile.policy_finance_need == "YES":
        signals.update({"POLICY_FINANCE", "EXPLICIT_POLICY_FINANCE_REVIEW"})
    elif profile.policy_finance_need == "NO":
        signals.add("POLICY_FINANCE_NOT_REQUESTED")
    if profile.production_or_working_capital_need == "YES":
        signals.add("PRODUCTION_FACILITY_OR_WORKING_CAPITAL_NEED")
    elif profile.production_or_working_capital_need == "UNKNOWN":
        signals.add("FUNDING_PURPOSE_UNKNOWN")
    return signals


def _apply_confirmed_input_precedence(
    *,
    signals: Set[str],
    trade_risk_confirmation: Optional[TradeRiskConfirmationRecord],
    profile: Optional[OfficialCandidateInputProfile],
) -> Set[str]:
    """넓은 상담 신호보다 확인된 거래·profile 사실을 마지막에 적용한다."""

    resolved = set(signals)
    if trade_risk_confirmation is not None:
        confirmed = trade_risk_confirmation.confirmed_input
        method_source = confirmed.field_sources.get(
            "balance_payment_method",
            "UNKNOWN",
        )
        method = confirmed.balance_payment_method
        if method_source != "UNKNOWN" and method == "DOCUMENTARY_CREDIT":
            resolved.difference_update(
                {
                    "NO_LC",
                    "NON_LC_CONFIRMED",
                    "ELIGIBLE_NON_LC_PAYMENT_METHOD",
                    "PAYMENT_METHOD_OA",
                    "PAYMENT_METHOD_DP",
                    "PAYMENT_METHOD_DA",
                    "LC_STATUS_UNKNOWN",
                }
            )
            resolved.add("HAS_LC")
        elif method_source != "UNKNOWN" and method in {
            "OPEN_ACCOUNT",
            "DOCUMENTARY_COLLECTION_DP",
            "DOCUMENTARY_COLLECTION_DA",
        }:
            resolved.discard("HAS_LC")
            resolved.discard("LC_STATUS_UNKNOWN")
            resolved.update(
                {"NON_LC_CONFIRMED", "ELIGIBLE_NON_LC_PAYMENT_METHOD"}
            )

    if profile is None:
        return resolved

    resolved.difference_update(
        {"PRE_SHIPMENT_TRANSACTION", "SHIPMENT_COMPLETED", "SHIPMENT_STATUS_UNKNOWN"}
    )
    if profile.shipment_status == "PRE_SHIPMENT":
        resolved.add("PRE_SHIPMENT_TRANSACTION")
    elif profile.shipment_status == "COMPLETED":
        resolved.add("SHIPMENT_COMPLETED")
    else:
        resolved.add("SHIPMENT_STATUS_UNKNOWN")

    resolved.difference_update(
        {
            "HAS_EXPORT_RECEIVABLE",
            "RECEIVABLE_NOT_YET",
            "NO_EXPORT_RECEIVABLE",
            "RECEIVABLE_STATUS_UNKNOWN",
        }
    )
    if profile.receivable_status == "EXISTS":
        resolved.add("HAS_EXPORT_RECEIVABLE")
    elif profile.receivable_status == "NOT_YET":
        resolved.add("RECEIVABLE_NOT_YET")
    elif profile.receivable_status == "NONE":
        resolved.add("NO_EXPORT_RECEIVABLE")
    else:
        resolved.add("RECEIVABLE_STATUS_UNKNOWN")

    resolved.difference_update(
        {
            "SINGLE_TRANSACTION_ONLY",
            "SINGLE_BUYER_ONLY",
            "RECURRING_EXPORT_TRANSACTIONS",
            "MULTIPLE_BUYERS",
            "RECURRING_TRANSACTION_STATUS_UNKNOWN",
            "BUYER_SCOPE_UNKNOWN",
        }
    )
    relationship_signals = {
        "SINGLE_ONE_OFF": {"SINGLE_TRANSACTION_ONLY", "SINGLE_BUYER_ONLY"},
        "RECURRING_SINGLE_BUYER": {
            "RECURRING_EXPORT_TRANSACTIONS",
            "SINGLE_BUYER_ONLY",
        },
        "RECURRING_MULTIPLE_BUYERS": {
            "RECURRING_EXPORT_TRANSACTIONS",
            "MULTIPLE_BUYERS",
        },
        "UNKNOWN": {
            "RECURRING_TRANSACTION_STATUS_UNKNOWN",
            "BUYER_SCOPE_UNKNOWN",
        },
    }
    resolved.update(relationship_signals[profile.relationship_scope])

    if profile.credit_investigation_intent == "YES":
        resolved.discard("BUYER_CREDIT_INVESTIGATION_DECLINED")
        resolved.add("BUYER_CREDIT_INVESTIGATION_REQUIRED")
    elif profile.credit_investigation_intent == "NO":
        resolved.discard("BUYER_CREDIT_INVESTIGATION_REQUIRED")
        resolved.add("BUYER_CREDIT_INVESTIGATION_DECLINED")
    else:
        resolved.discard("BUYER_CREDIT_INVESTIGATION_REQUIRED")

    resolved.difference_update(
        {
            "RECEIVABLE_PURCHASE_OR_NEGO_INTENT",
            "BANK_RECEIVABLE_PURCHASE_INTENT",
            "RECEIVABLE_PURCHASE_NOT_NEEDED",
            "RECEIVABLE_PURCHASE_INTENT_UNKNOWN",
            "BANK_RECEIVABLE_PURCHASE_INTENT_UNKNOWN",
        }
    )
    if profile.receivable_financing_intent in {
        "NEGO_OR_PURCHASE",
        "KB_RECEIVABLE_PURCHASE",
    }:
        resolved.add("RECEIVABLE_PURCHASE_OR_NEGO_INTENT")
        resolved.add("EXPORT_POST_SHIPMENT_LIQUIDITY_NEED")
        if profile.receivable_financing_intent == "KB_RECEIVABLE_PURCHASE":
            resolved.add("BANK_RECEIVABLE_PURCHASE_INTENT")
    elif profile.receivable_financing_intent == "NONE":
        resolved.add("RECEIVABLE_PURCHASE_NOT_NEEDED")
        if (
            profile.early_cash_conversion_intent != "YES"
            and "RECEIVABLE_EARLY_CASH_CONVERSION"
            not in profile.funding_purposes
        ):
            resolved.discard("EXPORT_POST_SHIPMENT_LIQUIDITY_NEED")
    else:
        resolved.update(
            {
                "RECEIVABLE_PURCHASE_INTENT_UNKNOWN",
                "BANK_RECEIVABLE_PURCHASE_INTENT_UNKNOWN",
            }
        )

    resolved.difference_update(
        {
            "EARLY_CASH_CONVERSION_INTENT",
            "EARLY_CASH_CONVERSION_NOT_NEEDED",
            "EARLY_CASH_CONVERSION_INTENT_UNKNOWN",
        }
    )
    if profile.early_cash_conversion_intent == "YES":
        resolved.update(
            {"EARLY_CASH_CONVERSION_INTENT", "EXPORT_POST_SHIPMENT_LIQUIDITY_NEED"}
        )
    elif profile.early_cash_conversion_intent == "NO":
        resolved.add("EARLY_CASH_CONVERSION_NOT_NEEDED")
    elif profile.early_cash_conversion_intent == "UNKNOWN":
        resolved.add("EARLY_CASH_CONVERSION_INTENT_UNKNOWN")

    if profile.bank_financing_intent == "YES":
        resolved.discard("BANK_FINANCING_INTENT_UNKNOWN")
        resolved.add("BANK_FINANCING_INTENT")
    elif profile.bank_financing_intent == "NO":
        resolved.discard("BANK_FINANCING_INTENT")
        resolved.discard("BANK_FINANCING_INTENT_UNKNOWN")
    else:
        resolved.discard("BANK_FINANCING_INTENT")
        resolved.add("BANK_FINANCING_INTENT_UNKNOWN")

    if profile.repayment_responsibility_acknowledgement == "ACKNOWLEDGED":
        resolved.discard("REPAYMENT_RESPONSIBILITY_UNKNOWN")
        resolved.add("REPAYMENT_RESPONSIBILITY_ACKNOWLEDGED")
    else:
        resolved.discard("REPAYMENT_RESPONSIBILITY_ACKNOWLEDGED")
        if profile.repayment_responsibility_acknowledgement == "UNKNOWN":
            resolved.add("REPAYMENT_RESPONSIBILITY_UNKNOWN")
        else:
            resolved.discard("REPAYMENT_RESPONSIBILITY_UNKNOWN")

    if (
        profile.short_term_export_insurance_linkage_review
        == "AGREED_TO_REVIEW"
    ):
        resolved.discard("SHORT_TERM_EXPORT_INSURANCE_LINKAGE_UNKNOWN")
        resolved.add("SHORT_TERM_EXPORT_INSURANCE_LINKAGE_REVIEW")
    else:
        resolved.discard("SHORT_TERM_EXPORT_INSURANCE_LINKAGE_REVIEW")
        if profile.short_term_export_insurance_linkage_review == "UNKNOWN":
            resolved.add("SHORT_TERM_EXPORT_INSURANCE_LINKAGE_UNKNOWN")
        else:
            resolved.discard("SHORT_TERM_EXPORT_INSURANCE_LINKAGE_UNKNOWN")

    if profile.sme_status == "CONFIRMED":
        resolved.discard("COMPANY_SME_STATUS_NOT_CONFIRMED")
        resolved.discard("SME_STATUS_UNKNOWN")
        resolved.add("COMPANY_SME_STATUS_CONFIRMED")
    elif profile.sme_status == "NOT_CONFIRMED":
        resolved.discard("COMPANY_SME_STATUS_CONFIRMED")
        resolved.discard("SME_STATUS_UNKNOWN")
        resolved.add("COMPANY_SME_STATUS_NOT_CONFIRMED")
    else:
        resolved.discard("COMPANY_SME_STATUS_CONFIRMED")
        resolved.add("SME_STATUS_UNKNOWN")

    if profile.market_entry_purpose == "YES":
        resolved.discard("EXPORT_EXPANSION_PURPOSE_UNKNOWN")
        resolved.add("EXPORT_EXPANSION_OR_MARKET_ENTRY_PURPOSE")
    elif profile.market_entry_purpose == "NO":
        resolved.discard("EXPORT_EXPANSION_OR_MARKET_ENTRY_PURPOSE")
        resolved.discard("EXPORT_EXPANSION_PURPOSE_UNKNOWN")
    else:
        resolved.discard("EXPORT_EXPANSION_OR_MARKET_ENTRY_PURPOSE")
        resolved.add("EXPORT_EXPANSION_PURPOSE_UNKNOWN")

    if profile.policy_finance_need == "YES":
        resolved.discard("POLICY_FINANCE_NOT_REQUESTED")
        resolved.update({"POLICY_FINANCE", "EXPLICIT_POLICY_FINANCE_REVIEW"})
    elif profile.policy_finance_need == "NO":
        resolved.difference_update({"POLICY_FINANCE", "EXPLICIT_POLICY_FINANCE_REVIEW"})
        resolved.add("POLICY_FINANCE_NOT_REQUESTED")
    else:
        resolved.difference_update({"POLICY_FINANCE", "EXPLICIT_POLICY_FINANCE_REVIEW"})

    if profile.production_or_working_capital_need == "YES":
        resolved.add("PRODUCTION_FACILITY_OR_WORKING_CAPITAL_NEED")
    elif profile.production_or_working_capital_need == "NO":
        resolved.discard("PRODUCTION_FACILITY_OR_WORKING_CAPITAL_NEED")

    return resolved


def _validate_profile_transaction_binding(
    *,
    profile: Optional[OfficialCandidateInputProfile],
    confirmed_transaction: Optional[ConfirmedTransactionSnapshot],
) -> None:
    if profile is None:
        return
    if confirmed_transaction is None:
        raise ValueError(
            "상품 입력 profile은 canonical confirmed transaction이 필요합니다."
        )
    if (
        profile.bound_transaction_fingerprint
        != confirmed_transaction.input_fingerprint
    ):
        raise ValueError(
            "상품 입력 profile이 현재 confirmed transaction과 다릅니다."
        )


def project_official_candidate_signals(
    *,
    trade_type: str,
    consultation_categories: List[str],
    consultation_packet: Optional[ConsultationPacket],
    confirmed_transaction: Optional[ConfirmedTransactionSnapshot] = None,
    trade_risk_confirmation: Optional[TradeRiskConfirmationRecord] = None,
    official_candidate_input_profile: Optional[
        OfficialCandidateInputProfile
    ] = None,
) -> FrozenSet[str]:
    if confirmed_transaction is not None and (
        trade_type != confirmed_transaction.trade_type
    ):
        raise ValueError(
            "공식 후보 거래방향이 confirmed transaction과 다릅니다."
        )
    if consultation_packet is not None and confirmed_transaction is not None:
        if (
            consultation_packet.confirmed_transaction_fingerprint
            != confirmed_transaction.input_fingerprint
        ):
            raise ValueError(
                "공식 후보 입력 Packet이 current transaction과 다릅니다."
            )
    _validate_profile_transaction_binding(
        profile=official_candidate_input_profile,
        confirmed_transaction=confirmed_transaction,
    )
    # confirmed_transaction의 날짜는 선적 완료를 뜻하지 않으므로 의도적으로
    # shipment 상태 signal을 만들지 않는다.
    _ = confirmed_transaction
    signals: Set[str] = {
        "IS_EXPORT" if trade_type == "EXPORT" else "IS_IMPORT"
    }
    review_area_ids = _review_area_ids(
        consultation_categories=consultation_categories,
        consultation_packet=consultation_packet,
    )
    signals.update(review_area_ids)
    if "POLICY_FINANCE" in review_area_ids:
        signals.add("EXPLICIT_POLICY_FINANCE_REVIEW")

    if "EXPORT_RECEIVABLE_PROTECTION" in consultation_categories:
        signals.add("HAS_EXPORT_RECEIVABLE")
    if "EXPORT_RECEIPT_MANAGEMENT" in consultation_categories:
        signals.add("HAS_EXPORT_RECEIVABLE")
    if "IMPORT_SETTLEMENT_FINANCE" in consultation_categories:
        signals.add("IMPORT_SETTLEMENT_FUNDING_NEED")
    if "IMPORT_ADVANCE_PAYMENT_PROTECTION" in consultation_categories:
        signals.add("ADVANCE_PAYMENT_CONTRACTUAL")
    if "FX_RISK_MANAGEMENT" in consultation_categories:
        signals.add("HAS_FX_EXPOSURE")

    signals.update(_confirmed_trade_risk_signals(trade_risk_confirmation))
    signals.update(_profile_signals(official_candidate_input_profile))

    if consultation_packet is None:
        return frozenset(
            _apply_confirmed_input_precedence(
                signals=signals,
                trade_risk_confirmation=trade_risk_confirmation,
                profile=official_candidate_input_profile,
            )
        )

    company = consultation_packet.company_summary
    if company.company_role == "SELLER":
        signals.add("COMPANY_IS_SELLER")
    elif company.company_role == "BUYER":
        signals.add("COMPANY_IS_BUYER")
    if company.settlement_date:
        signals.add("DUE_DATE_AVAILABLE")
    if (
        not company.settlement_date
        or not company.currency
        or not _decimal_is_positive(company.trade_amount_fx)
    ):
        signals.add("CORE_TRADE_INFORMATION_MISSING")
    payment_terms = (company.payment_terms or "").upper()
    if "OPEN ACCOUNT" in payment_terms or "O/A" in payment_terms:
        signals.add("OPEN_ACCOUNT")

    exposure = consultation_packet.exposure_summary
    if _decimal_is_positive(exposure.open_exposure_fx):
        signals.add("HAS_FX_EXPOSURE")
        signals.add(
            "EXPORT_RECEIPT_EXPOSURE"
            if trade_type == "EXPORT"
            else "IMPORT_PAYMENT_EXPOSURE"
        )
    protection = consultation_packet.protection_summary
    if protection.documentary_credit == "NONE_CONFIRMED":
        signals.add("NO_LC")
    elif protection.documentary_credit == "UNKNOWN":
        signals.add("LC_STATUS_UNKNOWN")
    if protection.credit_insurance == "NONE_CONFIRMED":
        signals.add("INSURANCE_NOT_CONFIRMED")
    elif protection.credit_insurance == "UNKNOWN":
        signals.add("INSURANCE_STATUS_UNKNOWN")
    elif protection.credit_insurance not in {"UNKNOWN", "NONE_CONFIRMED"}:
        signals.add("INSURANCE_CONFIRMED")
    if protection.independent_payment_guarantee == "NONE_CONFIRMED":
        signals.add("GUARANTEE_NOT_CONFIRMED")
    elif protection.independent_payment_guarantee == "UNKNOWN":
        signals.add("GUARANTEE_STATUS_UNKNOWN")
    elif protection.independent_payment_guarantee not in {
        "UNKNOWN",
        "NONE_CONFIRMED",
    }:
        signals.add("GUARANTEE_CONFIRMED")
    if protection.existing_hedge == "NONE_IN_CALCULATION_INPUT":
        signals.add("NO_CONFIRMED_HEDGE")
    elif protection.existing_hedge == "UNKNOWN":
        signals.add("HEDGE_STATUS_UNKNOWN")
    elif protection.existing_hedge not in {
        "UNKNOWN",
        "NONE_IN_CALCULATION_INPUT",
    }:
        signals.add("HEDGE_CONFIRMED")
    if "LOSS_LIMIT_EXCEEDED" in consultation_packet.risk_summary.risk_codes:
        signals.add("FX_LOSS_EXCEEDS_TOLERANCE")
    if _decimal_is_positive(
        consultation_packet.risk_summary.buffer_shortfall_krw
    ):
        signals.add("ENDING_CASH_BELOW_BUFFER")
    return frozenset(
        _apply_confirmed_input_precedence(
            signals=signals,
            trade_risk_confirmation=trade_risk_confirmation,
            profile=official_candidate_input_profile,
        )
    )


def _selection_signals(
    *,
    trade_type: str,
    consultation_categories: List[str],
    consultation_packet: Optional[ConsultationPacket],
) -> Set[str]:
    """이전 내부 호출과 테스트를 위한 호환 wrapper."""

    return set(
        project_official_candidate_signals(
            trade_type=trade_type,
            consultation_categories=consultation_categories,
            consultation_packet=consultation_packet,
        )
    )


def _canonical_candidate(
    *,
    candidate: ProductCandidate,
    catalogue_by_id: Dict[str, ProductRecord],
) -> Optional[ProductCandidate]:
    catalogue_id = candidate.catalogue_id
    if not catalogue_id or catalogue_id != candidate.product_id:
        return None
    record = catalogue_by_id.get(catalogue_id)
    if record is None:
        return None
    if (
        candidate.name != record.name
        or candidate.official_name != record.official_name
        or candidate.display_name != record.display_name
        or candidate.institution != record.institution
        or candidate.category != record.category
        or candidate.candidate_family != record.candidate_family
        or candidate.source.url != record.source.url
    ):
        return None
    payload = record.model_dump()
    payload.update(
        {
            "relevance_score": candidate.relevance_score,
            "strategy_connection_reason": (
                candidate.strategy_connection_reason
            ),
        }
    )
    return ProductCandidate.model_validate(payload)


def _profile_related_catalogue_ids(
    profile: Optional[OfficialCandidateInputProfile],
) -> List[str]:
    """명시 입력과 관련된 공식 항목만 token 검색 밖에서도 평가한다."""

    if profile is None:
        return []
    product_ids: List[str] = []
    pre_shipment_purposes = {
        "MANUFACTURING",
        "PROCESSING",
        "RAW_MATERIAL_PROCUREMENT",
        "FINISHED_GOODS_PROCUREMENT",
        "EXPORT_PERFORMANCE",
    }
    if (
        profile.shipment_status == "PRE_SHIPMENT"
        or bool(pre_shipment_purposes.intersection(profile.funding_purposes))
        or profile.bank_financing_intent == "YES"
    ):
        product_ids.append("ksure_export_credit_guarantee_pre_shipment")
    if profile.receivable_financing_intent in {
        "NEGO_OR_PURCHASE",
        "KB_RECEIVABLE_PURCHASE",
    }:
        product_ids.extend(
            [
                "ksure_export_credit_guarantee_post_shipment",
                "ksure_export_credit_guarantee_purchase",
            ]
        )
    if profile.relationship_scope == "RECURRING_MULTIPLE_BUYERS":
        product_ids.append(
            "ksure_export_credit_guarantee_comprehensive_purchase"
        )
    if profile.receivable_financing_intent == "KB_RECEIVABLE_PURCHASE":
        product_ids.append("kb_non_lc_export_bill_purchase")
    if (
        profile.policy_finance_need == "YES"
        or profile.market_entry_purpose == "YES"
    ):
        product_ids.append("kosmes_export_funding")
    return list(dict.fromkeys(product_ids))


def _catalogue_candidate(record: ProductRecord) -> ProductCandidate:
    payload = record.model_dump()
    payload.update(
        {
            "relevance_score": "0",
            "strategy_connection_reason": (
                "사용자가 확인한 거래조건과 관련된 공식 catalogue 항목을 "
                "결정론 필터에서 평가합니다."
            ),
        }
    )
    return ProductCandidate.model_validate(payload)


def _candidate_pool(
    *,
    stage4_result: Stage4Result,
    catalogue_by_id: Dict[str, ProductRecord],
    profile: Optional[OfficialCandidateInputProfile],
) -> List[Tuple[ProductCandidate, bool]]:
    rows: List[Tuple[ProductCandidate, bool]] = []
    seen = set()
    for candidate in stage4_result.candidates:
        if candidate.product_id in seen:
            continue
        rows.append((candidate, False))
        seen.add(candidate.product_id)
    for product_id in _profile_related_catalogue_ids(profile):
        if product_id in seen or product_id not in PROFILE_RELATED_CATALOGUE_IDS:
            continue
        record = catalogue_by_id.get(product_id)
        if record is None:
            continue
        rows.append((_catalogue_candidate(record), True))
        seen.add(product_id)
    return rows


def _is_explicit_profile_match(
    *,
    product_id: str,
    profile: Optional[OfficialCandidateInputProfile],
    signals: FrozenSet[str],
) -> bool:
    if profile is None:
        return False
    pre_shipment_purposes = {
        "MANUFACTURING",
        "PROCESSING",
        "RAW_MATERIAL_PROCUREMENT",
        "FINISHED_GOODS_PROCUREMENT",
        "EXPORT_PERFORMANCE",
    }
    if product_id == "ksure_export_credit_guarantee_pre_shipment":
        return (
            profile.shipment_status == "PRE_SHIPMENT"
            and bool(
                pre_shipment_purposes.intersection(profile.funding_purposes)
            )
            and profile.bank_financing_intent == "YES"
        )
    if product_id == "ksure_export_credit_guarantee_post_shipment":
        return (
            profile.shipment_status == "COMPLETED"
            and profile.receivable_status == "EXISTS"
            and profile.trade_form in {"GENERAL_EXPORT", "PROCESSING_TRADE"}
            and profile.receivable_financing_intent
            in {"NEGO_OR_PURCHASE", "KB_RECEIVABLE_PURCHASE"}
            and profile.short_term_export_insurance_linkage_review
            == "AGREED_TO_REVIEW"
        )
    if product_id == "ksure_export_credit_guarantee_purchase":
        return (
            profile.shipment_status == "COMPLETED"
            and profile.receivable_status == "EXISTS"
            and profile.receivable_financing_intent
            in {"NEGO_OR_PURCHASE", "KB_RECEIVABLE_PURCHASE"}
            and profile.repayment_responsibility_acknowledgement
            == "ACKNOWLEDGED"
            and "NON_LC_CONFIRMED" in signals
        )
    if (
        product_id
        == "ksure_export_credit_guarantee_comprehensive_purchase"
    ):
        return (
            profile.shipment_status == "COMPLETED"
            and profile.receivable_status == "EXISTS"
            and profile.relationship_scope == "RECURRING_MULTIPLE_BUYERS"
            and profile.receivable_financing_intent
            in {"NEGO_OR_PURCHASE", "KB_RECEIVABLE_PURCHASE"}
            and profile.repayment_responsibility_acknowledgement
            == "ACKNOWLEDGED"
            and "NON_LC_CONFIRMED" in signals
        )
    if product_id == "kb_non_lc_export_bill_purchase":
        return (
            profile.shipment_status == "COMPLETED"
            and profile.receivable_status == "EXISTS"
            and profile.receivable_financing_intent
            == "KB_RECEIVABLE_PURCHASE"
            and profile.early_cash_conversion_intent == "YES"
            and "NON_LC_CONFIRMED" in signals
            and "ELIGIBLE_NON_LC_PAYMENT_METHOD" in signals
        )
    if product_id == "kosmes_export_funding":
        return (
            profile.sme_status == "CONFIRMED"
            and profile.market_entry_purpose == "YES"
            and profile.policy_finance_need == "YES"
            and profile.production_or_working_capital_need == "YES"
        )
    return False


def _explicit_profile_match_priority(
    *,
    product_id: str,
    profile: Optional[OfficialCandidateInputProfile],
    signals: FrozenSet[str],
) -> int:
    if not _is_explicit_profile_match(
        product_id=product_id,
        profile=profile,
        signals=signals,
    ):
        return 1
    if (
        profile is not None
        and profile.receivable_financing_intent
        == "KB_RECEIVABLE_PURCHASE"
        and product_id != "kb_non_lc_export_bill_purchase"
    ):
        return 1
    return 0


def project_auxiliary_service_candidates(
    *,
    trade_type: str,
    signals: FrozenSet[str],
    official_candidate_input_profile: Optional[
        OfficialCandidateInputProfile
    ] = None,
    confirmed_transaction: Optional[ConfirmedTransactionSnapshot] = None,
    catalogue_path: Optional[Path] = None,
) -> AuxiliaryServiceCandidates:
    """Catalogue 신호를 충족한 보조서비스만 금융 shortlist 밖에 둔다."""

    if trade_type not in {"IMPORT", "EXPORT"}:
        raise ValueError("보조서비스 연결에는 IMPORT 또는 EXPORT가 필요합니다.")
    if official_candidate_input_profile is None:
        return AuxiliaryServiceCandidates(
            trade_type=trade_type,
            candidates=[],
        )
    _validate_profile_transaction_binding(
        profile=official_candidate_input_profile,
        confirmed_transaction=confirmed_transaction,
    )
    profile_validation = assess_official_candidate_input_profile(
        official_candidate_input_profile,
        has_confirmed_lc="HAS_LC" in signals,
    )
    if profile_validation.hard_blocking_issues:
        raise ValueError(
            "상품 입력 충돌을 먼저 수정해야 합니다: {}".format(
                " ".join(
                    issue.user_message
                    for issue in profile_validation.hard_blocking_issues
                )
            )
        )
    candidates: List[AuxiliaryServiceCandidate] = []
    suppressed_catalogue_ids: List[str] = []
    warnings: List[str] = []
    for record in active_official_catalogue_by_id(catalogue_path).values():
        if (
            record.product_id
            == "ksure_foreign_company_credit_investigation"
            and "BUYER_CREDIT_INVESTIGATION_DECLINED" in signals
        ):
            suppressed_catalogue_ids.append(record.product_id)
            warnings.append(
                "거래처 신용정보가 부족할 수 있지만 사용자가 신용조사를 "
                "원하지 않는다고 확인해 보조서비스를 표시하지 않았습니다."
            )
            continue
        if (
            record.product_type != "AUXILIARY_SERVICE"
            or record.financial_shortlist_eligible
            or trade_type not in record.trade_types
            or any(item in signals for item in record.excluded_signals)
            or any(item not in signals for item in record.required_signals)
        ):
            continue
        matched_any = [
            item for item in record.required_any_signals if item in signals
        ]
        if record.required_any_signals and not matched_any:
            continue
        deferred = [
            item for item in record.deferral_signals if item in signals
        ]
        if deferred and not matched_any:
            continue
        reason_signals = list(
            dict.fromkeys(list(record.required_signals) + matched_any)
        )
        reasons = [
            SIGNAL_REASON_LABELS.get(item, item)
            for item in reason_signals
        ]
        candidates.append(
            AuxiliaryServiceCandidate.model_validate(
                {
                    **record.model_dump(),
                    "matched_signals": reason_signals,
                    "selection_reasons": reasons,
                }
            )
        )
    candidates.sort(key=lambda item: item.product_id)
    return AuxiliaryServiceCandidates(
        trade_type=trade_type,
        candidates=candidates[:MAX_OFFICIAL_CANDIDATES],
        source_profile_fingerprint=(
            official_candidate_input_profile.input_fingerprint
            if official_candidate_input_profile is not None
            else None
        ),
        source_transaction_fingerprint=(
            confirmed_transaction.input_fingerprint
            if confirmed_transaction is not None
            else None
        ),
        suppressed_catalogue_ids=suppressed_catalogue_ids,
        warnings=warnings,
    )


def _product_priority(
    consultation_category: str,
    product_category: str,
) -> int:
    product_categories = CONSULTATION_PRODUCT_CATEGORIES.get(
        consultation_category,
        [],
    )
    try:
        return product_categories.index(product_category)
    except ValueError:
        return len(product_categories)


def shortlist_official_candidates(
    *,
    stage4_result: Stage4Result,
    trade_type: str,
    consultation_topics: List[ConsultationTopic],
    limit: int = MAX_OFFICIAL_CANDIDATES,
    consultation_packet: Optional[ConsultationPacket] = None,
    confirmed_transaction: Optional[ConfirmedTransactionSnapshot] = None,
    trade_risk_confirmation: Optional[TradeRiskConfirmationRecord] = None,
    official_candidate_input_profile: Optional[
        OfficialCandidateInputProfile
    ] = None,
    catalogue_path: Optional[Path] = None,
) -> OfficialCandidateShortlist:
    if trade_type not in {"IMPORT", "EXPORT"}:
        raise ValueError("공식 후보 연결에는 IMPORT 또는 EXPORT가 필요합니다.")
    if limit < 1 or limit > MAX_OFFICIAL_CANDIDATES:
        raise ValueError("공식 상담 후보는 1~3개까지만 선택할 수 있습니다.")

    consultation_categories = list(
        dict.fromkeys(
            topic.category
            for topic in consultation_topics
            if topic.category in CONSULTATION_PRODUCT_CATEGORIES
        )
    )
    consultation_titles = {
        topic.category: topic.title
        for topic in consultation_topics
    }
    signals = project_official_candidate_signals(
        trade_type=trade_type,
        consultation_categories=consultation_categories,
        consultation_packet=consultation_packet,
        confirmed_transaction=confirmed_transaction,
        trade_risk_confirmation=trade_risk_confirmation,
        official_candidate_input_profile=official_candidate_input_profile,
    )
    if official_candidate_input_profile is not None:
        profile_validation = assess_official_candidate_input_profile(
            official_candidate_input_profile,
            has_confirmed_lc="HAS_LC" in signals,
        )
        if profile_validation.hard_blocking_issues:
            raise ValueError(
                "상품 입력 충돌을 먼저 수정해야 합니다: {}".format(
                    " ".join(
                        issue.user_message
                        for issue in profile_validation.hard_blocking_issues
                    )
                )
            )
    if "EXPLICIT_POLICY_FINANCE_REVIEW" in signals:
        consultation_categories = list(
            dict.fromkeys(
                consultation_categories
                + ["EXPLICIT_POLICY_FINANCE_REVIEW"]
            )
        )
        consultation_titles["EXPLICIT_POLICY_FINANCE_REVIEW"] = (
            "사용자 확인 정책자금 검토"
        )
    review_area_ids = _review_area_ids(
        consultation_categories=consultation_categories,
        consultation_packet=consultation_packet,
    )
    if "POLICY_FINANCE" in signals:
        review_area_ids.append("POLICY_FINANCE")
        review_area_ids = list(dict.fromkeys(review_area_ids))
    catalogue_by_id = active_official_catalogue_by_id(catalogue_path)
    matched_rows: List[
        Tuple[int, int, int, Decimal, str, ProductCandidate]
    ] = []
    removed_unofficial = 0
    deferred_catalogue_ids: List[str] = []
    excluded_catalogue_ids: List[str] = []
    evaluations_by_id: Dict[str, OfficialCandidateEvaluation] = {}

    def record_evaluation(
        product_id: str,
        status: str,
        reasons: List[str],
    ) -> None:
        if official_candidate_input_profile is None:
            return
        evaluations_by_id[product_id] = OfficialCandidateEvaluation(
            catalogue_id=product_id,
            status=status,
            reasons=list(dict.fromkeys(reasons)),
        )

    candidate_pool = _candidate_pool(
        stage4_result=stage4_result,
        catalogue_by_id=catalogue_by_id,
        profile=official_candidate_input_profile,
    )
    for candidate, profile_injected in candidate_pool:
        if stage4_result.mode != "OFFLINE_KB" and not profile_injected:
            removed_unofficial += 1
            continue
        canonical = _canonical_candidate(
            candidate=candidate,
            catalogue_by_id=catalogue_by_id,
        )
        if (
            canonical is None
            or not is_official_url(candidate.source.url)
            or candidate.verification_status
            != "OFFICIAL_SOURCE_VERIFIED"
            or trade_type not in candidate.trade_types
        ):
            removed_unofficial += 1
            continue
        candidate = canonical
        if (
            not candidate.financial_shortlist_eligible
            or candidate.product_type == "AUXILIARY_SERVICE"
        ):
            record_evaluation(
                candidate.product_id,
                "EXCLUDED_NOT_APPLICABLE",
                ["금융 Top 3 대상이 아닌 catalogue 항목입니다."],
            )
            continue
        if (
            candidate.company_roles
            and consultation_packet is not None
            and consultation_packet.company_summary.company_role
            not in candidate.company_roles
        ):
            excluded_catalogue_ids.append(candidate.product_id)
            record_evaluation(
                candidate.product_id,
                "EXCLUDED_NOT_APPLICABLE",
                ["확정 회사 역할이 상품 대상과 다릅니다."],
            )
            continue
        matched_categories = _matches(
            candidate=candidate,
            consultation_categories=consultation_categories,
        )
        if not matched_categories:
            excluded_catalogue_ids.append(candidate.product_id)
            record_evaluation(
                candidate.product_id,
                "EXCLUDED_NOT_APPLICABLE",
                ["현재 상담 범주와 직접 연결되지 않습니다."],
            )
            continue
        matched_review_areas = [
            item
            for item in review_area_ids
            if item in candidate.supported_review_areas
        ]
        if (
            candidate.supported_review_areas
            and not matched_review_areas
        ):
            excluded_catalogue_ids.append(candidate.product_id)
            record_evaluation(
                candidate.product_id,
                "EXCLUDED_NOT_APPLICABLE",
                ["현재 금융상담 검토 분야와 직접 연결되지 않습니다."],
            )
            continue

        hard_exclusions = [
            item for item in candidate.excluded_signals if item in signals
        ]
        if hard_exclusions:
            excluded_catalogue_ids.append(candidate.product_id)
            record_evaluation(
                candidate.product_id,
                "EXCLUDED_CONFLICT",
                hard_exclusions,
            )
            continue

        missing_required = [
            item for item in candidate.required_signals if item not in signals
        ]
        missing_required_any: List[str] = []
        if candidate.required_any_signals and not any(
            item in signals for item in candidate.required_any_signals
        ):
            missing_required_any = list(candidate.required_any_signals)
        deferred_reasons = [
            item for item in candidate.deferral_signals if item in signals
        ]
        if deferred_reasons and (
            missing_required or missing_required_any or deferred_reasons
        ):
            deferred_catalogue_ids.append(candidate.product_id)
            record_evaluation(
                candidate.product_id,
                "DEFERRED_MISSING_INFORMATION",
                deferred_reasons + missing_required + missing_required_any,
            )
            continue
        if missing_required or missing_required_any:
            excluded_catalogue_ids.append(candidate.product_id)
            record_evaluation(
                candidate.product_id,
                "EXCLUDED_NOT_APPLICABLE",
                missing_required + missing_required_any,
            )
            continue
        reason_signals = list(candidate.required_signals) + [
            item
            for item in (
                "IS_EXPORT" if trade_type == "EXPORT" else "IS_IMPORT",
                (
                    "EXPORT_RECEIPT_EXPOSURE"
                    if trade_type == "EXPORT"
                    else "IMPORT_PAYMENT_EXPOSURE"
                ),
            )
            if item in signals
        ]
        selection_reasons = list(
            dict.fromkeys(
                SIGNAL_REASON_LABELS[item]
                for item in reason_signals
                if item in SIGNAL_REASON_LABELS
            )
        )
        reason = (
            "공식 자료의 제도 분류가 확인된 상담 항목 {}와 연결됩니다. "
            "이용 자격·승인·가격·한도는 기관 확인이 필요합니다."
        ).format(
            ", ".join(
                "‘{}’".format(
                    consultation_titles.get(
                        category,
                        "추가 금융 검토",
                    )
                )
                for category in matched_categories
            ),
        )
        explicit_profile_match = _is_explicit_profile_match(
            product_id=candidate.product_id,
            profile=official_candidate_input_profile,
            signals=signals,
        )
        matched = candidate.model_copy(
            update={
                "matched_consultation_categories": matched_categories,
                "matched_review_areas": matched_review_areas,
                "selection_reasons": selection_reasons,
                "strategy_connection_reason": reason,
                "explicit_profile_match": explicit_profile_match,
            }
        )
        record_evaluation(candidate.product_id, "ELIGIBLE", [])
        matched_rows.append(
            (
                _explicit_profile_match_priority(
                    product_id=candidate.product_id,
                    profile=official_candidate_input_profile,
                    signals=signals,
                ),
                min(_priority(item) for item in matched_categories),
                min(
                    _product_priority(item, candidate.category)
                    for item in matched_categories
                ),
                -_candidate_score(candidate),
                candidate.product_id,
                matched,
            )
        )

    matched_rows.sort(key=lambda item: item[:5])
    candidates: List[ProductCandidate] = []
    used_families: Set[str] = set()
    for row in matched_rows:
        candidate = row[5]
        family = candidate.candidate_family
        if family and family in used_families:
            continue
        candidates.append(candidate)
        if family:
            used_families.add(family)
        if len(candidates) == limit:
            break

    selected_ids = {candidate.product_id for candidate in candidates}
    selected_families = {
        candidate.candidate_family
        for candidate in candidates
        if candidate.candidate_family
    }
    eligible_overflow_candidates: List[ProductCandidate] = []
    overflow_reasons: Dict[str, str] = {}
    if official_candidate_input_profile is not None:
        for row in matched_rows:
            candidate = row[5]
            if candidate.product_id in selected_ids:
                continue
            if candidate.candidate_family in selected_families:
                overflow_reason = (
                    "동일한 금융 목적의 대표 후보가 우선 상담 3개에 "
                    "포함됐습니다."
                )
            else:
                overflow_reason = (
                    "현재 조건에는 맞지만 더 높은 상담 우선순위 후보가 있어 "
                    "다음 검토 대상으로 분류했습니다."
                )
            if len(eligible_overflow_candidates) < MAX_OFFICIAL_CANDIDATES:
                eligible_overflow_candidates.append(candidate)
                overflow_reasons[candidate.product_id] = overflow_reason
            evaluations_by_id[candidate.product_id] = (
                OfficialCandidateEvaluation(
                    catalogue_id=candidate.product_id,
                    status="ELIGIBLE_OVERFLOW",
                    reasons=[overflow_reason],
                )
            )
    matched_category_set = {
        category
        for candidate in candidates
        for category in candidate.matched_consultation_categories
    }
    unmatched = [
        category
        for category in consultation_categories
        if category not in matched_category_set
    ]
    warnings = list(stage4_result.warnings)
    if removed_unofficial:
        warnings.append(
            "공식 출처·거래방향 검증을 통과하지 못한 후보 {}건을 "
            "제외했습니다.".format(removed_unofficial)
        )
    if len(matched_rows) > len(candidates):
        warnings.append(
            "동일 candidate family 중복을 제거하고 상담 화면에는 공식 후보를 "
            "최대 {}개만 표시합니다.".format(limit)
        )
    if deferred_catalogue_ids:
        warnings.append(
            "필수 정보 확인 전 보류한 catalogue 후보가 있습니다: {}".format(
                ", ".join(dict.fromkeys(deferred_catalogue_ids))
            )
        )
    if unmatched:
        warnings.append(
            "직접 연결할 공식 후보가 없는 상담 범주는 상품을 만들지 "
            "않았습니다: {}".format(", ".join(unmatched))
        )
    warnings.append(
        "공식 후보는 추천·승인 결과가 아니며 최신 이용조건은 제공 기관에서 "
        "다시 확인해야 합니다."
    )
    return OfficialCandidateShortlist(
        trade_type=trade_type,
        source_mode=stage4_result.mode,
        query=stage4_result.query,
        candidates=candidates,
        unmatched_consultation_categories=unmatched,
        deferred_catalogue_ids=list(
            dict.fromkeys(deferred_catalogue_ids)
        ),
        excluded_catalogue_ids=(
            list(dict.fromkeys(excluded_catalogue_ids))
            if official_candidate_input_profile is not None
            else []
        ),
        eligible_overflow_candidates=eligible_overflow_candidates,
        overflow_reasons=overflow_reasons,
        candidate_evaluations=list(evaluations_by_id.values()),
        source_profile_fingerprint=(
            official_candidate_input_profile.input_fingerprint
            if official_candidate_input_profile is not None
            else None
        ),
        source_transaction_fingerprint=(
            confirmed_transaction.input_fingerprint
            if official_candidate_input_profile is not None
            and confirmed_transaction is not None
            else None
        ),
        warnings=list(dict.fromkeys(warnings)),
    )
