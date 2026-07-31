from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from src.domain.consultation_models import ConsultationTopic
from src.domain.product_models import (
    OfficialCandidateShortlist,
    ProductCandidate,
    Stage4Result,
)
from src.stage4.official_search import is_official_url


MAX_OFFICIAL_CANDIDATES = 3

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
        "POLICY_FINANCE",
    ],
    "PAYMENT_CAPACITY_REVIEW": [
        "TRADE_FINANCE_LOAN",
        "POLICY_FINANCE",
        "EXPORT_CREDIT_GUARANTEE",
    ],
    "EXPORT_RECEIPT_MANAGEMENT": [
        "FORWARD",
        "FX_RISK_INSURANCE",
        "FX_RISK_INSURANCE_OPTION",
        "FX_DEPOSIT",
    ],
    "ROUTINE_TRADE_REVIEW": [
        "FORWARD",
        "FX_RISK_INSURANCE",
        "FX_DEPOSIT",
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
    "ROUTINE_TRADE_REVIEW": [
        "수출입",
        "환율관리",
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
    "FX_RISK_MANAGEMENT",
    "FX_BALANCE_UTILIZATION",
    "ROUTINE_TRADE_REVIEW",
]


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


def shortlist_official_candidates(
    *,
    stage4_result: Stage4Result,
    trade_type: str,
    consultation_topics: List[ConsultationTopic],
    limit: int = MAX_OFFICIAL_CANDIDATES,
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
    matched_rows: List[
        Tuple[int, Decimal, str, ProductCandidate]
    ] = []
    removed_unofficial = 0
    for candidate in stage4_result.candidates:
        if (
            not is_official_url(candidate.source.url)
            or candidate.verification_status
            != "OFFICIAL_SOURCE_VERIFIED"
            or trade_type not in candidate.trade_types
        ):
            removed_unofficial += 1
            continue
        matched_categories = _matches(
            candidate=candidate,
            consultation_categories=consultation_categories,
        )
        if not matched_categories:
            continue
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
        matched = candidate.model_copy(
            update={
                "matched_consultation_categories": matched_categories,
                "strategy_connection_reason": reason,
            }
        )
        matched_rows.append(
            (
                min(_priority(item) for item in matched_categories),
                -_candidate_score(candidate),
                candidate.product_id,
                matched,
            )
        )

    matched_rows.sort(key=lambda item: item[:3])
    candidates = [item[3] for item in matched_rows[:limit]]
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
    if len(matched_rows) > limit:
        warnings.append(
            "상담 화면에는 우선순위가 높은 공식 후보 {}개만 표시합니다.".format(
                limit
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
        warnings=list(dict.fromkeys(warnings)),
    )
