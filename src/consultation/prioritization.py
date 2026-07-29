import hashlib
import json
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from schemas import PaymentInstallment, TradeDocumentExtraction
from src.domain.consultation_models import (
    ConsultationPriorityView,
    ConsultationRationaleItem,
    ConsultationTopic,
    InstallmentPaymentStatus,
    RiskAssessment,
)
from src.domain.country_environment_models import (
    CountryTradeEnvironmentAssessment,
)
from src.domain.product_models import OfficialCandidateShortlist
from src.domain.stage2_models import (
    ScenarioResult,
    Stage2Input,
    Stage2Result,
)
from src.domain.trade_risk_models import TradeSettlementRiskAssessment


PRIORITY_DISCLAIMER = (
    "상담 순위는 현재 거래에서 먼저 확인할 검토 순서이며, "
    "상품 승인·보험 인수·대출 심사 결과가 아닙니다."
)

# 사전식 정렬 규칙이다. 숫자를 더하거나 새로운 종합 위험점수를 만들지 않는다.
CATEGORY_PRIORITY_RULES: Dict[str, Tuple[int, int, str, str]] = {
    "PAYMENT_CAPACITY_REVIEW": (
        5,
        10,
        "PAYMENT_GAP_FIRST",
        "PAYMENT_CAPACITY",
    ),
    "EXPORT_RECEIVABLE_PROTECTION": (
        10,
        10,
        "EXPORT_COLLECTION_PROTECTION",
        "COLLECTION",
    ),
    "IMPORT_ADVANCE_PAYMENT_PROTECTION": (
        10,
        20,
        "IMPORT_ADVANCE_PROTECTION",
        "ADVANCE_PROTECTION",
    ),
    "DOCUMENTARY_CREDIT_TERMS_REVIEW": (
        15,
        10,
        "DOCUMENTARY_CREDIT_TERMS",
        "DOCUMENTARY_CREDIT",
    ),
    "FX_RISK_MANAGEMENT": (
        20,
        10,
        "FX_LOSS_AND_OPEN_EXPOSURE",
        "FX",
    ),
    "EXPORT_RECEIPT_MANAGEMENT": (
        20,
        20,
        "EXPORT_RECEIPT_FX_CONTEXT",
        "FX",
    ),
    "FX_BALANCE_UTILIZATION": (
        20,
        30,
        "USABLE_FX_CONTEXT",
        "FX",
    ),
    "EXPORT_LIQUIDITY_REVIEW": (
        30,
        10,
        "EXPORT_BUFFER_SHORTFALL",
        "LIQUIDITY",
    ),
    "IMPORT_SETTLEMENT_FINANCE": (
        30,
        20,
        "IMPORT_BUFFER_SHORTFALL",
        "LIQUIDITY",
    ),
    "PAYMENT_TERMS_REVIEW": (
        40,
        10,
        "PAYMENT_TERMS_REVIEW",
        "PAYMENT_TERMS",
    ),
    "COUNTRY_PAYMENT_TRANSFER_PROTECTION": (
        50,
        10,
        "COUNTRY_PROTECTION_CONTEXT",
        "COUNTRY_PROTECTION",
    ),
    "TRADE_RISK_INFORMATION_REVIEW": (
        70,
        10,
        "TRADE_INFORMATION_GAP",
        "INFORMATION",
    ),
    "TRADE_INFORMATION_REVIEW": (
        70,
        20,
        "DOCUMENT_INFORMATION_GAP",
        "INFORMATION",
    ),
    "COUNTRY_INFORMATION_COMPLETENESS": (
        70,
        30,
        "COUNTRY_INFORMATION_GAP",
        "COUNTRY_INFORMATION",
    ),
    "COUNTRY_MACRO_ENVIRONMENT_MONITORING": (
        80,
        10,
        "COUNTRY_STANDARD_MONITORING",
        "COUNTRY_MONITORING",
    ),
    "TRADE_MARKET_ACCESS_REVIEW": (
        80,
        20,
        "TRADE_MARKET_ACCESS_CONTEXT",
        "MARKET_ACCESS",
    ),
    "ROUTINE_TRADE_REVIEW": (
        90,
        10,
        "ROUTINE_REVIEW",
        "ROUTINE",
    ),
}

DEFAULT_PRIORITY_RULE = (85, 90, "OTHER_REVIEW", "OTHER")


def _dedupe(values: List[str]) -> List[str]:
    return list(dict.fromkeys(item for item in values if item))


def _topic_sort_key(
    topic: ConsultationTopic,
) -> Tuple[int, int, str]:
    tier, tie_break, unused_rule, unused_family = (
        CATEGORY_PRIORITY_RULES.get(
            topic.category,
            DEFAULT_PRIORITY_RULE,
        )
    )
    del unused_rule, unused_family
    if (
        topic.category
        in {
            "DOCUMENTARY_CREDIT_TERMS_REVIEW",
            "PAYMENT_TERMS_REVIEW",
        }
        and not topic.trade_risk_review_needs
        and topic.country_environment_review_needs
    ):
        tier = 50
    return tier, tie_break, topic.category


def _advance_installment(
    item: PaymentInstallment,
) -> bool:
    condition = (item.condition or "").casefold()
    return any(
        token in condition
        for token in ("advance", "prepay", "선지급", "선급")
    )


def materialize_installment_payment_statuses(
    *,
    extraction: TradeDocumentExtraction,
    supplied: Optional[List[InstallmentPaymentStatus]] = None,
) -> List[InstallmentPaymentStatus]:
    by_sequence: Dict[int, InstallmentPaymentStatus] = {}
    valid_sequences = {
        item.sequence
        for item in extraction.installments
        if item.sequence is not None
    }
    for item in supplied or []:
        if item.installment_sequence not in valid_sequences:
            raise ValueError(
                "문서 schedule에 없는 회차의 입금 상태를 확인할 수 없습니다."
            )
        if item.installment_sequence in by_sequence:
            raise ValueError("같은 회차의 입금 상태가 중복됐습니다.")
        if item.status == "UNKNOWN" and item.source != "UNCONFIRMED":
            raise ValueError("UNKNOWN 입금 상태는 미확인 source여야 합니다.")
        if item.status != "UNKNOWN" and item.source != "USER_CONFIRMED":
            raise ValueError("확정 입금 상태는 사용자 확인 source여야 합니다.")
        by_sequence[item.installment_sequence] = item

    statuses: List[InstallmentPaymentStatus] = []
    if extraction.trade_type != "EXPORT":
        return statuses
    for item in sorted(
        extraction.installments,
        key=lambda value: value.sequence or 0,
    ):
        if item.sequence is None or not _advance_installment(item):
            continue
        statuses.append(
            by_sequence.get(
                item.sequence,
                InstallmentPaymentStatus(
                    installment_sequence=item.sequence,
                ),
            )
        )
    return statuses


def _scenario(
    *,
    stage2_result: Stage2Result,
    assessment: RiskAssessment,
) -> Tuple[int, ScenarioResult]:
    for index, item in enumerate(stage2_result.scenario_results):
        if item.scenario_name == assessment.worst_scenario_id:
            return index, item
    raise ValueError("상담 숫자 근거에 해당하는 Stage 2 시나리오가 없습니다.")


def _rationale(
    *,
    label: str,
    value: str,
    unit: str,
    source_paths: List[str],
    currency: Optional[str] = None,
) -> ConsultationRationaleItem:
    return ConsultationRationaleItem(
        label=label,
        value=value,
        unit=unit,
        currency=currency,
        source_paths=source_paths,
    )


def _scenario_label(
    *,
    scenario_name: str,
    trade_type: str,
    suffix: str,
) -> str:
    normalized = scenario_name.upper()
    if (
        trade_type == "EXPORT"
        and (
            "DOWN_5" in normalized
            or "-5PCT" in normalized
        )
    ):
        return "-5% {}".format(suffix)
    if (
        trade_type == "IMPORT"
        and (
            "UP_5" in normalized
            or "+5PCT" in normalized
        )
    ):
        return "+5% {}".format(suffix)
    return "{} {}".format(scenario_name, suffix)


def _factor_path(
    *,
    assessment: Optional[TradeSettlementRiskAssessment],
    code: str,
) -> Optional[str]:
    if assessment is None:
        return None
    for index, item in enumerate(assessment.factors):
        if item.code == code:
            return "consultation.trade_settlement_risk.factors.{}".format(
                index
            )
    return None


def _collection_rationale(
    *,
    extraction: TradeDocumentExtraction,
    stage2_result: Stage2Result,
    trade_risk: Optional[TradeSettlementRiskAssessment],
    payment_statuses: List[InstallmentPaymentStatus],
) -> List[ConsultationRationaleItem]:
    currency = stage2_result.currency
    rows = [
        _rationale(
            label="분석 대상 예정 수취액",
            value=stage2_result.total_foreign_amount,
            unit="FX",
            currency=currency,
            source_paths=["stage2.total_foreign_amount"],
        )
    ]
    for index, item in enumerate(extraction.installments):
        condition = (item.condition or "").casefold()
        if item.amount is None or not any(
            token in condition
            for token in ("balance", "잔금", "remaining")
        ):
            continue
        rows.append(
            _rationale(
                label="잔금 예정",
                value=item.amount,
                unit="FX",
                currency=item.currency or currency,
                source_paths=[
                    "stage0.extraction.installments.{}.amount".format(
                        index
                    )
                ],
            )
        )
    factor_codes = {
        item.code for item in (trade_risk.factors if trade_risk else [])
    }
    payment_methods: List[str] = []
    method_sources: List[str] = []
    if "EXPORT_OPEN_ACCOUNT" in factor_codes:
        payment_methods.append("Open Account")
        path = _factor_path(
            assessment=trade_risk,
            code="EXPORT_OPEN_ACCOUNT",
        )
        if path:
            method_sources.append(path)
    if extraction.payment_terms and "t/t" in (
        extraction.payment_terms.casefold()
    ):
        payment_methods.append("T/T")
        method_sources.append("stage0.extraction.payment_terms")
    rows.append(
        _rationale(
            label="결제방식",
            value=" / ".join(payment_methods) or "UNKNOWN",
            unit="TEXT",
            source_paths=method_sources or [
                "consultation.trade_settlement_risk"
            ],
        )
    )
    protection_value = "UNKNOWN"
    protection_source = "consultation.trade_settlement_risk"
    if "NO_APPLICABLE_EXPORT_PROTECTION" in factor_codes:
        protection_value = "없음"
        protection_source = _factor_path(
            assessment=trade_risk,
            code="NO_APPLICABLE_EXPORT_PROTECTION",
        ) or protection_source
    elif "APPLICABLE_EXPORT_PROTECTION" in factor_codes:
        protection_value = "확인됨(적용범위 재확인 필요)"
        protection_source = _factor_path(
            assessment=trade_risk,
            code="APPLICABLE_EXPORT_PROTECTION",
        ) or protection_source
    rows.append(
        _rationale(
            label="확인된 보험·보증·신용장 보호",
            value=protection_value,
            unit="STATUS",
            source_paths=[protection_source],
        )
    )
    if trade_risk is not None:
        rows.append(
            _rationale(
                label="trade review",
                value=trade_risk.review_priority,
                unit="STATUS",
                source_paths=[
                    "consultation.trade_settlement_risk.review_priority"
                ],
            )
        )
    status_by_sequence = {
        item.installment_sequence: (index, item)
        for index, item in enumerate(payment_statuses)
    }
    for extraction_index, installment in enumerate(
        extraction.installments
    ):
        if (
            installment.sequence is None
            or installment.amount is None
            or not _advance_installment(installment)
        ):
            continue
        status_index, status = status_by_sequence[installment.sequence]
        rows.extend(
            [
                _rationale(
                    label="선지급 예정",
                    value=installment.amount,
                    unit="FX",
                    currency=installment.currency or currency,
                    source_paths=[
                        "stage0.extraction.installments.{}.amount".format(
                            extraction_index
                        )
                    ],
                ),
                _rationale(
                    label="선지급 실제 입금 여부",
                    value=status.status,
                    unit="STATUS",
                    source_paths=[
                        "consultation.installment_payment_statuses.{}"
                        ".status".format(status_index)
                    ],
                ),
            ]
        )
    return rows


def _fx_rationale(
    *,
    stage2_input: Stage2Input,
    stage2_result: Stage2Result,
    scenario_index: int,
    scenario: ScenarioResult,
) -> List[ConsultationRationaleItem]:
    is_export = stage2_result.trade_type == "EXPORT"
    scenario_flow = (
        scenario.fx_krw_inflow
        if is_export
        else scenario.fx_krw_outflow
    )
    flow_label = "수취" if is_export else "결제"
    return [
        _rationale(
            label=(
                "예정 수취 노출액"
                if is_export
                else "예정 지급 노출액"
            ),
            value=stage2_result.total_foreign_amount,
            unit="FX",
            currency=stage2_result.currency,
            source_paths=["stage2.total_foreign_amount"],
        ),
        _rationale(
            label="기준 원화 {}".format(flow_label),
            value=stage2_result.base_required_or_proceeds_krw,
            unit="KRW",
            source_paths=[
                "stage2.base_required_or_proceeds_krw"
            ],
        ),
        _rationale(
            label=_scenario_label(
                scenario_name=scenario.scenario_name,
                trade_type=stage2_result.trade_type,
                suffix=flow_label,
            ),
            value=scenario_flow,
            unit="KRW",
            source_paths=[
                "stage2.scenario_results.{}.{}".format(
                    scenario_index,
                    "fx_krw_inflow" if is_export else "fx_krw_outflow",
                )
            ],
        ),
        _rationale(
            label="기준 대비 감소" if is_export else "기준 대비 증가",
            value=scenario.loss_vs_base,
            unit="KRW",
            source_paths=[
                "stage2.scenario_results.{}.loss_vs_base".format(
                    scenario_index
                )
            ],
        ),
        _rationale(
            label="사용자 허용손실",
            value=stage2_input.acceptable_fx_loss,
            unit="KRW",
            source_paths=[
                "stage2.stage3_constraints.acceptable_fx_loss"
            ],
        ),
        _rationale(
            label="기존 헤지",
            value=stage2_result.hedged_amount,
            unit="FX",
            currency=stage2_result.currency,
            source_paths=["stage2.hedged_amount"],
        ),
        _rationale(
            label="보유 {}".format(stage2_result.currency),
            value=stage2_result.held_fx_used,
            unit="FX",
            currency=stage2_result.currency,
            source_paths=["stage2.held_fx_used"],
        ),
    ]


def _liquidity_rationale(
    *,
    stage2_result: Stage2Result,
    scenario_index: int,
    scenario: ScenarioResult,
) -> List[ConsultationRationaleItem]:
    return [
        _rationale(
            label=_scenario_label(
                scenario_name=scenario.scenario_name,
                trade_type=stage2_result.trade_type,
                suffix="ending cash",
            ),
            value=scenario.ending_cash,
            unit="KRW",
            source_paths=[
                "stage2.scenario_results.{}.ending_cash".format(
                    scenario_index
                )
            ],
        ),
        _rationale(
            label="목표 buffer",
            value=str(
                stage2_result.stage3_constraints.get(
                    "minimum_cash_buffer",
                    "0",
                )
            ),
            unit="KRW",
            source_paths=[
                "stage2.stage3_constraints.minimum_cash_buffer"
            ],
        ),
        _rationale(
            label="buffer shortfall",
            value=scenario.maximum_buffer_shortfall,
            unit="KRW",
            source_paths=[
                "stage2.scenario_results.{}"
                ".maximum_buffer_shortfall".format(scenario_index)
            ],
        ),
        _rationale(
            label="cash deficit",
            value=scenario.cash_deficit,
            unit="KRW",
            source_paths=[
                "stage2.scenario_results.{}.cash_deficit".format(
                    scenario_index
                )
            ],
        ),
        _rationale(
            label="payment/post-credit deficit",
            value=scenario.post_credit_shortfall,
            unit="KRW",
            source_paths=[
                "stage2.scenario_results.{}"
                ".post_credit_shortfall".format(scenario_index)
            ],
        ),
    ]


def _generic_rationale(
    *,
    topic: ConsultationTopic,
) -> List[ConsultationRationaleItem]:
    return [
        _rationale(
            label="trigger",
            value=", ".join(
                topic.triggered_by
                + topic.trade_risk_review_needs
                + topic.country_environment_review_needs
            )
            or "HUMAN_REVIEW",
            unit="TEXT",
            source_paths=[
                "consultation.consultation_topics.{}".format(
                    topic.category
                )
            ],
        )
    ]


def _priority_reason(
    *,
    family: str,
    stage2_result: Stage2Result,
    scenario: ScenarioResult,
    trade_risk: Optional[TradeSettlementRiskAssessment],
) -> str:
    if family == "COLLECTION":
        review = (
            trade_risk.review_priority
            if trade_risk is not None
            else "UNKNOWN"
        )
        return (
            "Open Account 등 회수 보호 검토 finding과 확인된 보호수단 "
            "상태를 먼저 확인합니다. 거래 검토 우선도는 {}이며 금융기관 "
            "승인등급이 아닙니다."
        ).format(review)
    if family == "FX":
        return (
            "열린 예정 외화노출에서 불리한 시나리오 손실이 발생하며, "
            "기존 LOSS_LIMIT_EXCEEDED finding과 허용손실을 함께 확인합니다."
        )
    if family == "LIQUIDITY":
        if (
            Decimal(scenario.cash_deficit) == 0
            and Decimal(scenario.post_credit_shortfall) == 0
        ):
            return (
                "목표 현금 버퍼 부족은 있으나 현금 적자와 지급부족은 "
                "0원입니다. 지급불능이나 대출 필요성 판단이 아니라 실제 "
                "자금계획·회수시점·가용한도 확인 순서입니다."
            )
        return (
            "기존 LIQUIDITY_BUFFER_RISK finding에 따라 목표 버퍼와 "
            "현금 적자·지급부족을 서로 구분해 확인합니다."
        )
    if family == "PAYMENT_CAPACITY":
        return (
            "기존 PAYMENT_CAPACITY_RISK finding의 지급부족을 우선 "
            "확인하되, 승인 가능성이나 필요 대출금은 판단하지 않습니다."
        )
    return (
        "기존 구조화 risk finding 또는 review need가 생성한 상담 항목을 "
        "명시적 category tie-break에 따라 검토합니다."
    )


def _decision_and_action(
    *,
    family: str,
    topic: ConsultationTopic,
) -> Tuple[str, str]:
    if family == "COLLECTION":
        return (
            "현재 채권에 검토 가능한 보험·보증·신용장 또는 결제조건 "
            "보강 구조와 필요서류를 확인",
            "계약서, 인보이스, 선적서류, 입금내역, 거래처 정보를 "
            "준비하고 수출대금 회수 보호 상담을 요청",
        )
    if family == "FX":
        return (
            "관리할 외화금액·회차·수단과 실제 환율·수수료·한도를 확인",
            "수취·지급 일정, 기존 헤지, 외화보유 내역을 준비하고 "
            "선물환·분할환전·외화예금 상담을 요청",
        )
    if family == "LIQUIDITY":
        return (
            "최신 자금계획에서 목표 버퍼를 유지하기 위한 일정 조정 또는 "
            "검토 가능한 단기 유동성 수단을 확인",
            "자금계획표, 입출금 일정, 기존 신용한도 자료를 준비하고 "
            "운영자금 버퍼 상담을 요청",
        )
    if family == "PAYMENT_CAPACITY":
        return (
            "실제 가용현금·한도와 지급일 조정 가능성, 검토 가능한 "
            "자금수단의 심사요건을 확인",
            "자금일보, 계좌잔액, 기존 한도, 결제일정 자료를 준비해 "
            "결제능력 상담을 요청",
        )
    return (
        "{}에서 확인해야 할 조건·필요서류·담당 검토 범위를 확정".format(
            topic.title
        ),
        "해당 준비자료와 질문 목록을 확인한 뒤 KB 영업점 또는 "
        "기업금융·외환 상담 경로에서 사람 상담을 요청",
    )


def _missing_information(
    *,
    family: str,
    extraction: TradeDocumentExtraction,
    payment_statuses: List[InstallmentPaymentStatus],
    trade_risk: Optional[TradeSettlementRiskAssessment],
) -> List[str]:
    missing: List[str] = []
    if family == "COLLECTION":
        status_by_sequence = {
            item.installment_sequence: item
            for item in payment_statuses
        }
        for installment in extraction.installments:
            if (
                installment.sequence is None
                or installment.amount is None
                or not _advance_installment(installment)
            ):
                continue
            status = status_by_sequence[installment.sequence]
            if status.status == "UNKNOWN":
                missing.append(
                    "{} {:,.0f} 선지급의 실제 입금 여부와 입금일".format(
                        installment.currency
                        or extraction.currency
                        or "외화",
                        Decimal(installment.amount),
                    )
                )
        missing.append("거래처의 과거 지급·연체·분쟁 이력")
        if trade_risk is not None:
            missing.extend(trade_risk.information_gaps)
    elif family == "FX":
        missing.append(
            "실제 적용 가능한 은행 환율·spread·fee·한도"
        )
    elif family in {"LIQUIDITY", "PAYMENT_CAPACITY"}:
        missing.append("최신 자금계획과 실제 가용 신용한도")
    return _dedupe(missing)


def _official_candidates(
    *,
    source_topic_ids: List[str],
    shortlist: Optional[OfficialCandidateShortlist],
) -> List:
    if shortlist is None:
        return []
    categories = set(source_topic_ids)
    return [
        item
        for item in shortlist.candidates
        if categories.intersection(
            item.matched_consultation_categories
        )
    ][:3]


def _fingerprint(
    priorities: List[ConsultationPriorityView],
) -> str:
    serialized = json.dumps(
        [item.model_dump() for item in priorities],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_consultation_priorities(
    *,
    extraction: TradeDocumentExtraction,
    stage2_input: Stage2Input,
    stage2_result: Stage2Result,
    assessment: RiskAssessment,
    consultation_topics: List[ConsultationTopic],
    trade_settlement_risk: Optional[
        TradeSettlementRiskAssessment
    ] = None,
    country_environment: Optional[
        CountryTradeEnvironmentAssessment
    ] = None,
    official_candidate_shortlist: Optional[
        OfficialCandidateShortlist
    ] = None,
    installment_payment_statuses: Optional[
        List[InstallmentPaymentStatus]
    ] = None,
) -> Tuple[
    List[ConsultationPriorityView],
    List[ConsultationTopic],
    str,
    List[InstallmentPaymentStatus],
]:
    del country_environment
    payment_statuses = materialize_installment_payment_statuses(
        extraction=extraction,
        supplied=installment_payment_statuses,
    )
    scenario_index, adverse = _scenario(
        stage2_result=stage2_result,
        assessment=assessment,
    )
    grouped: Dict[str, List[ConsultationTopic]] = {}
    for topic in sorted(consultation_topics, key=_topic_sort_key):
        unused_tier, unused_tie, unused_rule, family = (
            CATEGORY_PRIORITY_RULES.get(
                topic.category,
                (
                    DEFAULT_PRIORITY_RULE[0],
                    DEFAULT_PRIORITY_RULE[1],
                    DEFAULT_PRIORITY_RULE[2],
                    "{}:{}".format(
                        DEFAULT_PRIORITY_RULE[3],
                        topic.category,
                    ),
                ),
            )
        )
        del unused_tier, unused_tie, unused_rule
        grouped.setdefault(family, []).append(topic)

    group_rows = sorted(
        grouped.items(),
        key=lambda item: _topic_sort_key(item[1][0]),
    )
    selected = group_rows[:3]
    selected_families = {item[0] for item in selected}
    priorities: List[ConsultationPriorityView] = []
    for rank, (family, source_topics) in enumerate(
        selected,
        start=1,
    ):
        primary = source_topics[0]
        tier, tie_break, rule_code, unused_family = (
            CATEGORY_PRIORITY_RULES.get(
                primary.category,
                DEFAULT_PRIORITY_RULE,
            )
        )
        del tier, unused_family
        source_topic_ids = [
            item.category for item in source_topics
        ]
        if family == "COLLECTION":
            rationale = _collection_rationale(
                extraction=extraction,
                stage2_result=stage2_result,
                trade_risk=trade_settlement_risk,
                payment_statuses=payment_statuses,
            )
        elif family == "FX":
            rationale = _fx_rationale(
                stage2_input=stage2_input,
                stage2_result=stage2_result,
                scenario_index=scenario_index,
                scenario=adverse,
            )
        elif family in {"LIQUIDITY", "PAYMENT_CAPACITY"}:
            rationale = _liquidity_rationale(
                stage2_result=stage2_result,
                scenario_index=scenario_index,
                scenario=adverse,
            )
        else:
            rationale = _generic_rationale(topic=primary)
        expected_decision, next_action = _decision_and_action(
            family=family,
            topic=primary,
        )
        triggered_by = _dedupe(
            [
                value
                for topic in source_topics
                for value in (
                    list(topic.triggered_by)
                    + list(topic.trade_risk_review_needs)
                    + list(topic.country_environment_review_needs)
                )
            ]
        )
        preparation_documents = _dedupe(
            [
                value
                for topic in source_topics
                for value in topic.required_documents
            ]
        )
        bank_questions = _dedupe(
            [
                value
                for topic in source_topics
                for value in topic.questions
            ]
        )
        priorities.append(
            ConsultationPriorityView(
                rank=rank,
                category=primary.category,
                title=primary.title,
                priority_reason=_priority_reason(
                    family=family,
                    stage2_result=stage2_result,
                    scenario=adverse,
                    trade_risk=trade_settlement_risk,
                ),
                numeric_rationale=rationale,
                triggered_by=triggered_by,
                missing_information=_missing_information(
                    family=family,
                    extraction=extraction,
                    payment_statuses=payment_statuses,
                    trade_risk=trade_settlement_risk,
                ),
                preparation_documents=preparation_documents,
                bank_questions=bank_questions,
                expected_decision=expected_decision,
                next_action=next_action,
                official_candidates=_official_candidates(
                    source_topic_ids=source_topic_ids,
                    shortlist=official_candidate_shortlist,
                ),
                source_topic_ids=source_topic_ids,
                priority_rule_code=rule_code,
                category_tie_break="{:03d}:{}".format(
                    tie_break,
                    primary.category,
                ),
                disclaimer=PRIORITY_DISCLAIMER,
            )
        )

    other_topics = [
        topic
        for family, topics in group_rows
        if family not in selected_families
        for topic in topics
    ]
    return (
        priorities,
        other_topics,
        _fingerprint(priorities),
        payment_statuses,
    )
