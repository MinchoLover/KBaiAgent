from types import MappingProxyType
from typing import Dict, List, Mapping, NamedTuple

from src.consultation.prioritization import CATEGORY_PRIORITY_RULES
from src.domain.consultation_models import (
    ConsultationPriorityView,
    ConsultationRationaleItem,
    ConsultationReviewAreaId,
    ConsultationReviewAreaView,
    ConsultationSupportingCheckId,
    ConsultationSupportingCheckView,
)


REVIEW_AREA_DISPLAY_NAMES: Mapping[
    ConsultationReviewAreaId,
    str,
] = MappingProxyType(
    {
        "COLLECTION_PROTECTION": "수출대금 회수 보호",
        "FX_MANAGEMENT": "환율 관리",
        "PAYMENT_TERMS": "결제조건 보강",
        "WORKING_CAPITAL_TRADE_FINANCE": "무역금융·운영자금",
        "POLICY_FINANCE": "정책자금 검토",
    }
)


CATEGORY_TO_REVIEW_AREA: Mapping[
    str,
    ConsultationReviewAreaId,
] = MappingProxyType(
    {
        "PAYMENT_CAPACITY_REVIEW": (
            "WORKING_CAPITAL_TRADE_FINANCE"
        ),
        "EXPORT_RECEIVABLE_PROTECTION": "COLLECTION_PROTECTION",
        "IMPORT_ADVANCE_PAYMENT_PROTECTION": "PAYMENT_TERMS",
        "DOCUMENTARY_CREDIT_TERMS_REVIEW": "PAYMENT_TERMS",
        "FX_RISK_MANAGEMENT": "FX_MANAGEMENT",
        "EXPORT_RECEIPT_MANAGEMENT": "FX_MANAGEMENT",
        "FX_BALANCE_UTILIZATION": "FX_MANAGEMENT",
        "EXPORT_LIQUIDITY_REVIEW": (
            "WORKING_CAPITAL_TRADE_FINANCE"
        ),
        "IMPORT_SETTLEMENT_FINANCE": (
            "WORKING_CAPITAL_TRADE_FINANCE"
        ),
        "PAYMENT_TERMS_REVIEW": "PAYMENT_TERMS",
        "COUNTRY_PAYMENT_TRANSFER_PROTECTION": "PAYMENT_TERMS",
    }
)


SUPPORTING_CHECK_DISPLAY_NAMES: Mapping[
    ConsultationSupportingCheckId,
    str,
] = MappingProxyType(
    {
        "TRADE_RISK_INFORMATION": "거래·보호조건 정보 보완",
        "TRADE_INFORMATION_COMPLETENESS": "거래 핵심정보 보완",
        "COUNTRY_INFORMATION_COMPLETENESS": "거래국 공식정보 보완",
        "COUNTRY_MACRO_MONITORING": "거래국 거시환경 모니터링",
        "MARKET_ACCESS_AND_TRADE_ENVIRONMENT": (
            "시장접근·통상환경 확인"
        ),
        "ROUTINE_TRADE_CHECK": "정기 거래 점검",
    }
)


CATEGORY_TO_SUPPORTING_CHECK: Mapping[
    str,
    ConsultationSupportingCheckId,
] = MappingProxyType(
    {
        "TRADE_RISK_INFORMATION_REVIEW": "TRADE_RISK_INFORMATION",
        "TRADE_INFORMATION_REVIEW": "TRADE_INFORMATION_COMPLETENESS",
        "COUNTRY_INFORMATION_COMPLETENESS": (
            "COUNTRY_INFORMATION_COMPLETENESS"
        ),
        "COUNTRY_MACRO_ENVIRONMENT_MONITORING": (
            "COUNTRY_MACRO_MONITORING"
        ),
        "TRADE_MARKET_ACCESS_REVIEW": (
            "MARKET_ACCESS_AND_TRADE_ENVIRONMENT"
        ),
        "ROUTINE_TRADE_REVIEW": "ROUTINE_TRADE_CHECK",
    }
)


class UnmappedConsultationCategoryError(ValueError):
    pass


class ConsultationPresentationProjection(NamedTuple):
    review_areas: List[ConsultationReviewAreaView]
    supporting_checks: List[ConsultationSupportingCheckView]


def validate_category_classification() -> None:
    supported = set(CATEGORY_PRIORITY_RULES)
    primary = set(CATEGORY_TO_REVIEW_AREA)
    supporting = set(CATEGORY_TO_SUPPORTING_CHECK)
    overlap = sorted(primary & supporting)
    classified = primary | supporting
    if overlap or classified != supported:
        missing = sorted(supported - classified)
        unexpected = sorted(classified - supported)
        raise ValueError(
            "상담 presentation classification이 priority category 계약과 "
            "일치하지 않습니다. missing={} unexpected={} overlap={}".format(
                missing,
                unexpected,
                overlap,
            )
        )


def validate_review_area_mapping() -> None:
    validate_category_classification()


def _dedupe_strings(values: List[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))


def _evidence_key(item: ConsultationRationaleItem) -> str:
    return item.model_dump_json()


def _dedupe_evidence(
    values: List[ConsultationRationaleItem],
) -> List[ConsultationRationaleItem]:
    rows: Dict[str, ConsultationRationaleItem] = {}
    for item in values:
        rows.setdefault(_evidence_key(item), item)
    return list(rows.values())


def _review_area_for_category(
    category: str,
) -> ConsultationReviewAreaId:
    try:
        return CATEGORY_TO_REVIEW_AREA[category]
    except KeyError as exc:
        raise UnmappedConsultationCategoryError(
            "명시적으로 매핑되지 않은 상담 category입니다: {}".format(
                category
            )
        ) from exc


def _supporting_check_for_category(
    category: str,
) -> ConsultationSupportingCheckId:
    try:
        return CATEGORY_TO_SUPPORTING_CHECK[category]
    except KeyError as exc:
        raise UnmappedConsultationCategoryError(
            "명시적으로 분류되지 않은 상담 category입니다: {}".format(
                category
            )
        ) from exc


def _family_for_category(category: str) -> str:
    try:
        return CATEGORY_PRIORITY_RULES[category][3]
    except KeyError as exc:
        raise UnmappedConsultationCategoryError(
            "family를 확인할 수 없는 상담 category입니다: {}".format(
                category
            )
        ) from exc


def _new_view(
    *,
    priority: ConsultationPriorityView,
    priority_fingerprint: str,
) -> ConsultationReviewAreaView:
    review_area_id = _review_area_for_category(priority.category)
    family = _family_for_category(priority.category)
    return ConsultationReviewAreaView(
        rank=priority.rank,
        review_area_id=review_area_id,
        display_name=REVIEW_AREA_DISPLAY_NAMES[review_area_id],
        source_priority_category=priority.category,
        source_priority_family=family,
        source_priority_categories=[priority.category],
        source_priority_families=[family],
        source_priority_reasons=[priority.priority_reason],
        summary=priority.priority_reason,
        trigger_codes=list(priority.triggered_by),
        evidence_items=list(priority.numeric_rationale),
        missing_information=list(priority.missing_information),
        preparation_documents=list(priority.preparation_documents),
        bank_questions=list(priority.bank_questions),
        expected_decision=priority.expected_decision,
        next_action=priority.next_action,
        source_topic_ids=list(priority.source_topic_ids),
        source_priority_fingerprint=priority_fingerprint,
        human_review_required=priority.human_review_required,
        disclaimer=priority.disclaimer,
    )


def _merge_view(
    *,
    representative: ConsultationReviewAreaView,
    later: ConsultationReviewAreaView,
) -> ConsultationReviewAreaView:
    return ConsultationReviewAreaView(
        rank=representative.rank,
        review_area_id=representative.review_area_id,
        display_name=representative.display_name,
        source_priority_category=(
            representative.source_priority_category
        ),
        source_priority_family=representative.source_priority_family,
        source_priority_categories=_dedupe_strings(
            representative.source_priority_categories
            + later.source_priority_categories
        ),
        source_priority_families=_dedupe_strings(
            representative.source_priority_families
            + later.source_priority_families
        ),
        source_priority_reasons=_dedupe_strings(
            representative.source_priority_reasons
            + later.source_priority_reasons
        ),
        summary=representative.summary,
        trigger_codes=_dedupe_strings(
            representative.trigger_codes + later.trigger_codes
        ),
        evidence_items=_dedupe_evidence(
            representative.evidence_items + later.evidence_items
        ),
        missing_information=_dedupe_strings(
            representative.missing_information
            + later.missing_information
        ),
        preparation_documents=_dedupe_strings(
            representative.preparation_documents
            + later.preparation_documents
        ),
        bank_questions=_dedupe_strings(
            representative.bank_questions + later.bank_questions
        ),
        expected_decision=representative.expected_decision,
        next_action=representative.next_action,
        source_topic_ids=_dedupe_strings(
            representative.source_topic_ids + later.source_topic_ids
        ),
        source_priority_fingerprint=(
            representative.source_priority_fingerprint
        ),
        human_review_required=(
            representative.human_review_required
            or later.human_review_required
        ),
        disclaimer=representative.disclaimer,
    )


def _new_supporting_check(
    *,
    priority: ConsultationPriorityView,
    priority_fingerprint: str,
) -> ConsultationSupportingCheckView:
    check_id = _supporting_check_for_category(priority.category)
    family = _family_for_category(priority.category)
    return ConsultationSupportingCheckView(
        source_rank=priority.rank,
        check_id=check_id,
        display_name=SUPPORTING_CHECK_DISPLAY_NAMES[check_id],
        source_priority_category=priority.category,
        source_priority_family=family,
        source_priority_categories=[priority.category],
        source_priority_families=[family],
        source_priority_ranks=[priority.rank],
        source_priority_reasons=[priority.priority_reason],
        summary=priority.priority_reason,
        trigger_codes=list(priority.triggered_by),
        evidence_items=list(priority.numeric_rationale),
        missing_information=list(priority.missing_information),
        preparation_documents=list(priority.preparation_documents),
        bank_questions=list(priority.bank_questions),
        expected_decision=priority.expected_decision,
        next_action=priority.next_action,
        source_topic_ids=list(priority.source_topic_ids),
        source_priority_fingerprint=priority_fingerprint,
        human_review_required=priority.human_review_required,
        disclaimer=priority.disclaimer,
    )


def _merge_supporting_check(
    *,
    representative: ConsultationSupportingCheckView,
    later: ConsultationSupportingCheckView,
) -> ConsultationSupportingCheckView:
    return ConsultationSupportingCheckView(
        source_rank=representative.source_rank,
        check_id=representative.check_id,
        display_name=representative.display_name,
        source_priority_category=(
            representative.source_priority_category
        ),
        source_priority_family=representative.source_priority_family,
        source_priority_categories=_dedupe_strings(
            representative.source_priority_categories
            + later.source_priority_categories
        ),
        source_priority_families=_dedupe_strings(
            representative.source_priority_families
            + later.source_priority_families
        ),
        source_priority_ranks=list(
            dict.fromkeys(
                representative.source_priority_ranks
                + later.source_priority_ranks
            )
        ),
        source_priority_reasons=_dedupe_strings(
            representative.source_priority_reasons
            + later.source_priority_reasons
        ),
        summary=representative.summary,
        trigger_codes=_dedupe_strings(
            representative.trigger_codes + later.trigger_codes
        ),
        evidence_items=_dedupe_evidence(
            representative.evidence_items + later.evidence_items
        ),
        missing_information=_dedupe_strings(
            representative.missing_information
            + later.missing_information
        ),
        preparation_documents=_dedupe_strings(
            representative.preparation_documents
            + later.preparation_documents
        ),
        bank_questions=_dedupe_strings(
            representative.bank_questions + later.bank_questions
        ),
        expected_decision=representative.expected_decision,
        next_action=representative.next_action,
        source_topic_ids=_dedupe_strings(
            representative.source_topic_ids + later.source_topic_ids
        ),
        source_priority_fingerprint=(
            representative.source_priority_fingerprint
        ),
        human_review_required=(
            representative.human_review_required
            or later.human_review_required
        ),
        disclaimer=representative.disclaimer,
    )


def project_consultation_presentation(
    *,
    priorities: List[ConsultationPriorityView],
    priority_fingerprint: str,
) -> ConsultationPresentationProjection:
    validate_category_classification()
    if len(priorities) > 3:
        raise ValueError("상담 priority는 최대 3개만 projection할 수 있습니다.")
    ranks = [item.rank for item in priorities]
    if ranks != sorted(ranks) or len(ranks) != len(set(ranks)):
        raise ValueError(
            "상담 priority 입력은 기존 rank 오름차순이며 중복이 없어야 합니다."
        )

    review_areas: List[ConsultationReviewAreaView] = []
    review_position_by_area: Dict[ConsultationReviewAreaId, int] = {}
    supporting_checks: List[ConsultationSupportingCheckView] = []
    supporting_position_by_check: Dict[
        ConsultationSupportingCheckId,
        int,
    ] = {}
    for priority in priorities:
        if priority.category in CATEGORY_TO_REVIEW_AREA:
            review_candidate = _new_view(
                priority=priority,
                priority_fingerprint=priority_fingerprint,
            )
            review_position = review_position_by_area.get(
                review_candidate.review_area_id
            )
            if review_position is None:
                review_position_by_area[
                    review_candidate.review_area_id
                ] = len(review_areas)
                review_areas.append(review_candidate)
            else:
                review_areas[review_position] = _merge_view(
                    representative=review_areas[review_position],
                    later=review_candidate,
                )
            continue
        if priority.category in CATEGORY_TO_SUPPORTING_CHECK:
            supporting_candidate = _new_supporting_check(
                priority=priority,
                priority_fingerprint=priority_fingerprint,
            )
            supporting_position = supporting_position_by_check.get(
                supporting_candidate.check_id
            )
            if supporting_position is None:
                supporting_position_by_check[
                    supporting_candidate.check_id
                ] = len(supporting_checks)
                supporting_checks.append(supporting_candidate)
            else:
                supporting_checks[
                    supporting_position
                ] = _merge_supporting_check(
                    representative=supporting_checks[
                        supporting_position
                    ],
                    later=supporting_candidate,
                )
            continue
        raise UnmappedConsultationCategoryError(
            "명시적으로 분류되지 않은 상담 category입니다: {}".format(
                priority.category
            )
        )
    return ConsultationPresentationProjection(
        review_areas=review_areas,
        supporting_checks=supporting_checks,
    )


def project_consultation_review_areas(
    *,
    priorities: List[ConsultationPriorityView],
    priority_fingerprint: str,
) -> List[ConsultationReviewAreaView]:
    return project_consultation_presentation(
        priorities=priorities,
        priority_fingerprint=priority_fingerprint,
    ).review_areas


def project_consultation_supporting_checks(
    *,
    priorities: List[ConsultationPriorityView],
    priority_fingerprint: str,
) -> List[ConsultationSupportingCheckView]:
    return project_consultation_presentation(
        priorities=priorities,
        priority_fingerprint=priority_fingerprint,
    ).supporting_checks
