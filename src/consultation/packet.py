import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from schemas import TradeDocumentExtraction
from src.consultation.prioritization import (
    build_consultation_priorities,
)
from src.document_intake.confirmation import ConfirmationRecord
from src.domain.consultation_models import (
    CompanySummary,
    ConsultationPacket,
    ConsultationPacketResult,
    ConsultationPriorityView,
    ConsultationRationaleItem,
    ConsultationTopic,
    ExposureSummary,
    InstallmentPaymentStatus,
    PacketRiskSummary,
    PaymentScheduleSummary,
    ProtectionStatusSummary,
    RiskAssessment,
    SourceDocumentReference,
)
from src.domain.country_environment_models import (
    CountryTradeEnvironmentAssessment,
)
from src.domain.product_models import OfficialCandidateShortlist
from src.domain.stage1_models import NormalizedScenarioSet
from src.domain.stage2_models import Stage2Input, Stage2Result
from src.domain.trade_risk_models import TradeSettlementRiskAssessment
from src.stage2.metrics import money_string


DISCLAIMER = (
    "본 결과는 금융상품 가입, 대출 승인 또는 헤지 실행을 결정하지 않습니다. "
    "환율 시나리오는 미래 환율의 확정 예측이 아닙니다. 실제 이용 가능 여부와 "
    "조건은 KB를 포함한 거래은행 상담과 심사를 통해 확인해야 합니다."
    " 거래·결제 검토 우선도는 금융기관의 공식 심사등급이나 부도확률이 "
    "아닙니다."
)

SAFETY_BOUNDARIES = [
    (
        "분석 대상 예정 결제 노출액은 계약상 예정 금액이며 실제 현재 "
        "미수잔액 또는 미지급잔액을 확정하지 않습니다."
    ),
    (
        "Stage 3 후보는 입력 가정 아래 계산상 비교안이며 최적 헤지나 "
        "실행 지시가 아닙니다."
    ),
    (
        "국가환경 snapshot은 OECD·World Bank·WTO 원자료 문맥이며 "
        "KB 또는 KBaiAgent의 공식 국가신용등급이 아닙니다."
    ),
    (
        "공식 후보의 eligibility와 approval은 UNKNOWN 또는 상담 필요이며 "
        "가입·대출·보험 인수를 보장하지 않습니다."
    ),
    (
        "상담 순위는 검토 순서이며 상품 승인·보험 인수·대출 심사 "
        "결과가 아닙니다."
    ),
]


def _input_hash(
    *,
    confirmation: ConfirmationRecord,
    stage1: NormalizedScenarioSet,
    stage2_input: Stage2Input,
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
) -> str:
    canonical: Dict[str, Any] = {
        "confirmation": {
            "source_sha256": confirmation.source_sha256,
            "confirmed_values": confirmation.confirmed_values,
            "checks": confirmation.checks.model_dump(),
        },
        "stage1": stage1.model_dump(),
        "stage2_input": stage2_input.model_dump(),
    }
    if trade_settlement_risk is not None:
        canonical["trade_risk_input_fingerprint"] = (
            trade_settlement_risk.input_fingerprint
        )
    if country_environment is not None:
        canonical["country_environment_input_fingerprint"] = (
            country_environment.input_fingerprint
        )
    if official_candidate_shortlist is not None:
        canonical["official_candidate_shortlist"] = {
            "selection_policy": (
                official_candidate_shortlist.selection_policy
            ),
            "trade_type": official_candidate_shortlist.trade_type,
            "candidates": [
                {
                    "product_id": candidate.product_id,
                    "category": candidate.category,
                    "source_url": candidate.source.url,
                    "source_verified_at": candidate.source.verified_at,
                    "matched_consultation_categories": (
                        candidate.matched_consultation_categories
                    ),
                }
                for candidate in official_candidate_shortlist.candidates
            ],
            "unmatched_consultation_categories": (
                official_candidate_shortlist
                .unmatched_consultation_categories
            ),
        }
    if installment_payment_statuses:
        canonical["installment_payment_statuses"] = [
            item.model_dump()
            for item in installment_payment_statuses
        ]
    serialized = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _worst_scenario(
    stage2_result: Stage2Result,
    assessment: RiskAssessment,
) -> Any:
    for item in stage2_result.scenario_results:
        if item.scenario_name == assessment.worst_scenario_id:
            return item
    raise ValueError("위험 분류의 worst scenario가 Stage 2 결과에 없습니다.")


def _confirmed_fields(
    confirmation: ConfirmationRecord,
) -> List[str]:
    checks = confirmation.checks
    fields: List[str] = []
    if getattr(checks, "company_role_confirmed", False):
        fields.append("company_role")
    if getattr(checks, "trade_type_confirmed", False):
        fields.append("trade_type")
    if checks.currency_confirmed:
        fields.append("currency")
    if checks.amount_due_confirmed:
        fields.append("trade_amount_fx")
    if checks.due_date_confirmed:
        fields.append("settlement_date")
    return fields


def _settlement_date(stage2_result: Stage2Result) -> str:
    dates = list(
        dict.fromkeys(
            item.settlement_date
            for item in stage2_result.exposure_computations
        )
    )
    return ", ".join(dates)


def _required_documents(
    topics: List[ConsultationTopic],
    priorities: Optional[List[ConsultationPriorityView]] = None,
) -> List[str]:
    return list(
        dict.fromkeys(
            (
                [
                    document
                    for priority in priorities or []
                    for document in priority.preparation_documents
                ]
                + [
                    document
                    for topic in topics
                    for document in topic.required_documents
                ]
            )
        )
    )


def _questions(
    topics: List[ConsultationTopic],
    priorities: Optional[List[ConsultationPriorityView]] = None,
) -> List[str]:
    return list(
        dict.fromkeys(
            (
                [
                    question
                    for priority in priorities or []
                    for question in priority.bank_questions
                ]
                + [
                    question
                    for topic in topics
                    for question in topic.questions
                ]
            )
        )
    )


def _protection_summary(
    *,
    stage2_result: Stage2Result,
    trade_settlement_risk: Optional[
        TradeSettlementRiskAssessment
    ],
    payment_statuses: List[InstallmentPaymentStatus],
) -> ProtectionStatusSummary:
    factor_codes = {
        item.code
        for item in (
            trade_settlement_risk.factors
            if trade_settlement_risk is not None
            else []
        )
    }
    if "DOCUMENTARY_CREDIT_DETAILS_NOT_ASSESSED" in factor_codes:
        documentary_credit = "PRESENT_DETAILS_NOT_ASSESSED"
    elif (
        "NO_APPLICABLE_EXPORT_PROTECTION" in factor_codes
        or "NO_APPLICABLE_IMPORT_PROTECTION" in factor_codes
    ):
        documentary_credit = "NONE_CONFIRMED"
    else:
        documentary_credit = "UNKNOWN"
    no_protection = bool(
        {
            "NO_APPLICABLE_EXPORT_PROTECTION",
            "NO_APPLICABLE_IMPORT_PROTECTION",
        }.intersection(factor_codes)
    )
    has_protection = bool(
        {
            "APPLICABLE_EXPORT_PROTECTION",
            "APPLICABLE_IMPORT_PROTECTION",
        }.intersection(factor_codes)
    )
    if no_protection:
        insurance = "NONE_CONFIRMED"
        guarantee = "NONE_CONFIRMED"
    elif has_protection:
        insurance = "PROTECTION_PRESENT_TYPE_NOT_EXPOSED"
        guarantee = "PROTECTION_PRESENT_TYPE_NOT_EXPOSED"
    else:
        insurance = "UNKNOWN"
        guarantee = "UNKNOWN"
    if not payment_statuses:
        receipt_status = "NOT_APPLICABLE"
    elif any(item.status == "UNKNOWN" for item in payment_statuses):
        receipt_status = "UNKNOWN"
    elif all(
        item.status == "CONFIRMED_RECEIVED"
        for item in payment_statuses
    ):
        receipt_status = "CONFIRMED_RECEIVED"
    elif all(
        item.status == "CONFIRMED_NOT_RECEIVED"
        for item in payment_statuses
    ):
        receipt_status = "CONFIRMED_NOT_RECEIVED"
    else:
        receipt_status = "MIXED_USER_CONFIRMED"
    return ProtectionStatusSummary(
        documentary_credit=documentary_credit,
        credit_insurance=insurance,
        independent_payment_guarantee=guarantee,
        existing_hedge=(
            "NONE_IN_CALCULATION_INPUT"
            if Decimal(stage2_result.hedged_amount) == 0
            else "PRESENT_IN_CALCULATION_INPUT"
        ),
        advance_payment_receipt=receipt_status,
    )


def _country_environment_lines(
    assessment: Optional[CountryTradeEnvironmentAssessment],
) -> str:
    if assessment is None:
        return "- 사용자 확인 국가에 대한 별도 공식자료 검토 결과가 없습니다."
    priority_labels = {
        "STANDARD_REVIEW": "통상 검토",
        "ELEVATED_REVIEW": "추가 검토",
        "HIGH_REVIEW": "우선 검토",
        "INSUFFICIENT_INFORMATION": "정보 부족",
    }
    references = {
        item.source_record_id: item
        for item in assessment.official_source_references
    }
    oecd = assessment.oecd_payment_transfer
    if oecd.status == "CLASSIFIED":
        oecd_value = (
            "OECD 공식 원자료 분류: {} · 자체 국가등급 아님".format(
                oecd.raw_classification
            )
        )
    elif oecd.status == "HIGH_INCOME_OECD_UNCLASSIFIED":
        oecd_value = (
            "고소득 OECD 회원국 미분류 · 0 또는 낮은 위험으로 변환하지 않음"
        )
    else:
        oecd_value = "OECD 원자료 확인 불가"
    oecd_reference = references.get(oecd.source_record_id or "")
    oecd_url = (
        oecd_reference.official_url
        if oecd_reference is not None
        else ""
    )
    lines = [
        "- 거래국: **{}**".format(assessment.country),
        "- 거래 검토 우선순위: **{}** · 국가 신용등급이 아님".format(
            priority_labels[assessment.review_priority]
        ),
        "- 지급·이전 환경 — OECD: {} · 기준일 {} · [{}]({})  \n"
        "  해석: {}  \n"
        "  한계: {}".format(
            oecd_value,
            oecd.as_of_date,
            "공식 출처",
            oecd_url,
            oecd.interpretation,
            oecd.limitations,
        ),
    ]
    for item in assessment.world_bank_macro_environment.observations:
        reference = references[item.source_record_id]
        raw = (
            item.raw_value
            if item.raw_value is not None
            else item.raw_status or "자료 없음"
        )
        lines.append(
            "- 거시환경 — World Bank `{}`: {} {} · 관측 {} · "
            "[공식 출처]({})  \n"
            "  해석: {}  \n"
            "  한계: {}".format(
                item.indicator_code,
                raw,
                item.raw_unit,
                item.observation_period,
                reference.official_url,
                item.interpretation,
                item.limitations,
            )
        )
    for item in assessment.wto_trade_market_access.observations:
        reference = references[item.source_record_id]
        raw = (
            item.raw_value
            if item.raw_value is not None
            else item.raw_status or "자료 없음"
        )
        lines.append(
            "- 무역·시장접근 — WTO `{}`: {} {} · 자료기간 {} · "
            "[공식 출처]({})  \n"
            "  해석: {}  \n"
            "  한계: {}".format(
                item.indicator_code,
                raw,
                item.raw_unit,
                item.observation_period,
                reference.official_url,
                item.interpretation,
                item.limitations,
            )
        )
    return "\n".join(lines)


def rationale_display_text(
    item: ConsultationRationaleItem,
) -> str:
    if item.unit in {"FX", "KRW"}:
        value = Decimal(item.value)
        if value == value.to_integral():
            number = "{:,.0f}".format(value)
        else:
            number = "{:,.2f}".format(value).rstrip("0").rstrip(".")
        if item.unit == "KRW":
            return "{}원".format(number)
        return "{} {}".format(item.currency or "FX", number)
    return item.value


def _markdown(packet: ConsultationPacket) -> str:
    risk_lines = (
        "\n".join(
            "- `{}` · 시나리오 `{}` · 기준값 {} / 임계값 {}".format(
                item.risk_code,
                item.scenario_id or "공통",
                item.trigger_value,
                item.threshold or "없음",
            )
            for item in packet.risk_findings
        )
        or "- 현재 입력에서 구조화된 주요 위험 코드가 발생하지 않았습니다."
    )
    if packet.trade_settlement_risk is None:
        trade_risk_lines = (
            "- 거래처·결제·보호조건의 별도 확인 결과가 없습니다."
        )
        trade_risk_assumptions = "- 없음"
    else:
        trade_risk = packet.trade_settlement_risk
        priority_labels = {
            "STANDARD_REVIEW": "일반 검토",
            "ELEVATED_REVIEW": "추가 검토 필요",
            "HIGH_REVIEW": "우선 검토 필요",
            "UNKNOWN": "정보 확인 필요",
        }
        risk_type_labels = {
            "IMPORT_PREPAYMENT_PERFORMANCE_RISK": (
                "수입 선지급·계약이행 위험"
            ),
            "EXPORT_RECEIVABLE_COLLECTION_RISK": (
                "수출대금 회수 위험"
            ),
        }
        factor_lines = [
            "- {}: {}".format(
                {
                    "RISK_SIGNAL": "위험 신호",
                    "MITIGANT": "확인된 완화요소",
                    "INFORMATION_GAP": "정보 부족",
                }[factor.effect],
                factor.reason,
            )
            for factor in trade_risk.factors
        ]
        trade_risk_lines = "\n".join(
            [
                "- 위험 유형: {}".format(
                    risk_type_labels[trade_risk.risk_type]
                ),
                "- 검토 우선도: **{}**".format(
                    priority_labels[trade_risk.review_priority]
                ),
            ]
            + factor_lines
        )
        trade_risk_assumptions = (
            "\n".join(
                "- {}".format(item)
                for item in trade_risk.assumptions
            )
            or "- 별도 수치 가정 없음"
        )
    country_environment_lines = _country_environment_lines(
        packet.country_environment
    )
    schedule_lines = (
        "\n".join(
            "- {}회차: {} · 예정일 {} · 조건 {}".format(
                item.sequence,
                (
                    "{} {}".format(
                        item.currency
                        or packet.company_summary.currency,
                        "{:,.0f}".format(Decimal(item.amount_fx)),
                    )
                    if item.amount_fx is not None
                    else "금액 미확인"
                ),
                item.scheduled_date or "미확인",
                item.condition or "미확인",
            )
            for item in packet.company_summary.payment_schedule
        )
        or "- 문서에서 구조화된 분할 결제 schedule이 없습니다."
    )
    priority_sections: List[str] = []
    for priority in packet.consultation_priorities:
        rationale_lines = "\n".join(
            "  - {}: {}  \n"
            "    source path: `{}`".format(
                item.label,
                rationale_display_text(item),
                "`, `".join(item.source_paths),
            )
            for item in priority.numeric_rationale
        ) or "  - 추가 수치 근거 없음"
        priority_missing = (
            "\n".join(
                "  - {}".format(item)
                for item in priority.missing_information
            )
            or "  - 이 카드에 별도로 등록된 미확인 항목 없음"
        )
        priority_candidates = (
            "\n".join(
                "  - {} · {} · [공식 출처]({}) · 확인일 {}  \n"
                "    연결 이유: {}  \n"
                "    eligibility=UNKNOWN · "
                "approval=CONSULTATION_REQUIRED".format(
                    item.name,
                    item.institution,
                    item.source.url,
                    item.source.verified_at,
                    item.strategy_connection_reason,
                )
                for item in priority.official_candidates
            )
            or (
                "  - 현재 검증된 공식 후보가 없습니다. 최신 상담 가능 "
                "구조는 KB 영업점 또는 기업금융·외환 상담에서 확인하세요."
            )
        )
        priority_sections.append(
            """### {rank}순위 · {title}

- 검토 순서 근거: {priority_reason}
- primary trigger: {triggered_by}
- 결정 규칙: `{rule_code}` · tie-break `{tie_break}`
- 숫자·조건 근거:
{rationale_lines}
- 아직 확인할 정보:
{missing_lines}
- 상담에서 기대하는 결정: {expected_decision}
- 다음 행동: {next_action}
- 연결된 공식 후보:
{candidate_lines}

{disclaimer}
""".format(
                rank=priority.rank,
                title=priority.title,
                priority_reason=priority.priority_reason,
                triggered_by=(
                    ", ".join(priority.triggered_by) or "HUMAN_REVIEW"
                ),
                rule_code=priority.priority_rule_code,
                tie_break=priority.category_tie_break,
                rationale_lines=rationale_lines,
                missing_lines=priority_missing,
                expected_decision=priority.expected_decision,
                next_action=priority.next_action,
                candidate_lines=priority_candidates,
                disclaimer=priority.disclaimer,
            )
        )
    priority_lines = (
        "\n".join(priority_sections)
        or "현재 입력에서 생성된 우선 상담 카드가 없습니다."
    )
    topic_lines = "\n".join(
        "- **{}**: {} 최종 판단은 사용자와 KB 담당자가 합니다.".format(
            item.title,
            item.explanation,
        )
        for item in packet.consultation_topics
    )
    if packet.official_candidate_shortlist is None:
        official_candidate_lines = (
            "- 현재 검증된 공식 후보가 없습니다. 최신 상담 가능 구조는 "
            "KB 영업점 또는 기업금융·외환 상담에서 확인하세요."
        )
    elif not packet.official_candidate_shortlist.candidates:
        official_candidate_lines = (
            "- 현재 검증된 공식 후보가 없습니다. 최신 상담 가능 구조는 "
            "KB 영업점 또는 기업금융·외환 상담에서 확인하세요. "
            "후보를 임의로 만들지 않았습니다."
        )
    else:
        official_candidate_lines = "\n".join(
            "- **{}** · {} · [{}]({}) · 자료 확인일 {}  \n"
            "  연결 근거: {}".format(
                candidate.name,
                candidate.institution,
                candidate.source.title,
                candidate.source.url,
                candidate.source.verified_at,
                candidate.strategy_connection_reason,
            )
            for candidate in packet.official_candidate_shortlist.candidates
        )
    missing_lines = (
        "\n".join("- {}".format(item) for item in packet.missing_information)
        or "- 현재 패킷에 명시적으로 등록된 미확인 항목이 없습니다."
    )
    document_lines = (
        "\n".join("- {}".format(item) for item in packet.required_documents)
        or "- 상담 과정에서 필요한 서류를 확인해야 합니다."
    )
    question_lines = (
        "\n".join("- {}".format(item) for item in packet.bank_questions)
        or "- 실제 이용 가능 조건과 추가 확인사항은 무엇인가?"
    )
    safety_lines = "\n".join(
        "- {}".format(item) for item in packet.safety_boundaries
    )
    other_topic_lines = (
        "\n".join(
            "- **{}**: {}".format(item.title, item.explanation)
            for item in packet.other_consultation_topics
        )
        or "- Top 3 외 별도 확인사항이 없습니다."
    )
    protection = packet.protection_summary
    loss_label = (
        "추가 원화 비용"
        if packet.company_summary.trade_type == "IMPORT"
        else "원화 수취 감소"
    )
    return """# KB 상담 준비 패킷

> 이 첫 요약은 `ConsultationPacket` JSON에서 결정론적으로 생성했습니다.

## 1. 거래 요약

- Case ID: `{case_id}`
- 회사 역할: {company_role}
- 거래 방향: {trade_type}
- 통화·금액: {currency} {trade_amount}
- 거래 상대국: {counterparty}
- 결제·수취일: {settlement_date}
- Incoterm: {incoterm}
- 결제조건: {payment_terms}
- 열린 환노출: {currency} {open_exposure}
- 사용자 확인 필드: {confirmed_fields}

결제 회차:

{schedule_lines}

## 2. 상담 Top 3

{priority_lines}

## 3. 보호수단 현황

- 신용장: {documentary_credit}
- 보험: {credit_insurance}
- 독립 지급보증: {payment_guarantee}
- 기존 헤지: {existing_hedge}
- 선지급 실제 입금 확인: {advance_receipt}

## 4. 준비할 자료

{document_lines}

## 5. 은행에 물어볼 질문

{question_lines}

## 6. 공식 출처 상담 후보

{official_candidate_lines}

후보는 최대 3개이며, 자격·승인·가격·한도는 제공 기관에서 다시 확인해야 합니다.

## 7. 안전 경계

{safety_lines}

## 8. Trace

- 원문 document hash: `{document_hash}`
- 사용자 확인 필드: {confirmed_fields}
- 입력 hash: `{input_hash}`
- 거래위험 fingerprint: `{trade_risk_fingerprint}`
- 상담 priority fingerprint: `{priority_fingerprint}`
- 계산 버전: `{calculation_version}`
- 환율 기준시각: `{exchange_rate_as_of}`
- 시나리오 ID: {scenario_ids}
- 생성시각: `{generated_at}`

---

# 상세 근거 부록

## 2. 핵심 계산 결과

- 가장 위험한 스트레스 시나리오: {worst_scenario}
- {loss_label}: {loss}원
- 결제·수취 후 현금: {ending_cash}원
- 최소 운영자금 부족: {buffer_shortfall}원
- 실제 현금 적자: {cash_deficit}원
- 대출한도 반영 후 지급 부족: {payment_gap}원

`최소 운영자금 부족`과 `대출한도 반영 후 지급 부족`은 서로 다른 지표입니다.

## 3. 환율·유동성 위험 원인

{risk_lines}

## 4. 거래·결제조건 위험

{trade_risk_lines}

적용 가정:

{trade_risk_assumptions}

## 4A. 국가·무역환경 검토

{country_environment_lines}

## 5. 검토할 금융 대응

{topic_lines}

위 항목은 금융상품 추천이나 승인 결과가 아니라 상담 범주입니다.

## 5A. 기타 확인사항

{other_topic_lines}

## 6. 공식 출처 상담 후보

{official_candidate_lines}

## 7. 아직 확인할 정보

{missing_lines}

## 8. 준비할 서류

{document_lines}

## 9. KB 상담 시 질문

{question_lines}

## 10. 재현성 정보

- 계산 버전: `{calculation_version}`
- 입력 hash: `{input_hash}`
- 환율 기준시각: `{exchange_rate_as_of}`
- 시나리오 ID: {scenario_ids}
- 생성시각: `{generated_at}`

## 11. 고지문

{disclaimer}
""".format(
        case_id=packet.case_id,
        company_role=packet.company_summary.company_role or "미확인",
        trade_type=packet.company_summary.trade_type,
        currency=packet.company_summary.currency,
        trade_amount=packet.company_summary.trade_amount_fx,
        counterparty=packet.company_summary.counterparty_country or "미확인",
        settlement_date=packet.company_summary.settlement_date,
        incoterm=packet.company_summary.incoterm or "미확인",
        payment_terms=packet.company_summary.payment_terms or "미확인",
        schedule_lines=schedule_lines,
        open_exposure=packet.exposure_summary.open_exposure_fx,
        confirmed_fields=(
            ", ".join(packet.user_confirmed_fields) or "없음"
        ),
        worst_scenario=packet.risk_summary.worst_scenario_id,
        loss_label=loss_label,
        loss=packet.risk_summary.additional_cost_or_receipt_loss_krw,
        ending_cash=packet.risk_summary.cash_after_settlement_krw,
        buffer_shortfall=packet.risk_summary.buffer_shortfall_krw,
        cash_deficit=packet.risk_summary.cash_deficit_krw,
        payment_gap=packet.risk_summary.payment_gap_krw,
        risk_lines=risk_lines,
        trade_risk_lines=trade_risk_lines,
        trade_risk_assumptions=trade_risk_assumptions,
        country_environment_lines=country_environment_lines,
        priority_lines=priority_lines,
        topic_lines=topic_lines,
        other_topic_lines=other_topic_lines,
        official_candidate_lines=official_candidate_lines,
        missing_lines=missing_lines,
        document_lines=document_lines,
        question_lines=question_lines,
        safety_lines=safety_lines,
        documentary_credit=protection.documentary_credit,
        credit_insurance=protection.credit_insurance,
        payment_guarantee=protection.independent_payment_guarantee,
        existing_hedge=protection.existing_hedge,
        advance_receipt=protection.advance_payment_receipt,
        document_hash=(
            packet.source_documents[0].document_id
            if packet.source_documents
            else "UNKNOWN"
        ),
        trade_risk_fingerprint=(
            packet.trade_settlement_risk.input_fingerprint
            if packet.trade_settlement_risk is not None
            else "NOT_AVAILABLE"
        ),
        priority_fingerprint=(
            packet.consultation_priority_fingerprint or "NOT_AVAILABLE"
        ),
        calculation_version=packet.calculation_version,
        input_hash=packet.input_hash,
        exchange_rate_as_of=packet.exchange_rate_as_of,
        scenario_ids=", ".join(packet.scenario_ids),
        generated_at=packet.generated_at,
        disclaimer=packet.disclaimer,
    )


def build_consultation_packet(
    *,
    case_id: str,
    extraction: TradeDocumentExtraction,
    confirmation: ConfirmationRecord,
    stage1: NormalizedScenarioSet,
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
    missing_information: Optional[List[str]] = None,
    generated_at: Optional[str] = None,
) -> ConsultationPacketResult:
    worst = _worst_scenario(stage2_result, assessment)
    loss = max(Decimal(worst.loss_vs_base), Decimal("0"))
    counterparty_country = (
        extraction.seller_country
        if stage2_result.trade_type == "IMPORT"
        else extraction.buyer_country
    )
    (
        consultation_priorities,
        other_consultation_topics,
        priority_fingerprint,
        materialized_payment_statuses,
    ) = build_consultation_priorities(
        extraction=extraction,
        stage2_input=stage2_input,
        stage2_result=stage2_result,
        assessment=assessment,
        consultation_topics=consultation_topics,
        trade_settlement_risk=trade_settlement_risk,
        country_environment=country_environment,
        official_candidate_shortlist=official_candidate_shortlist,
        installment_payment_statuses=installment_payment_statuses,
    )
    priority_missing = [
        value
        for priority in consultation_priorities
        for value in priority.missing_information
    ]
    gaps = list(
        dict.fromkeys(
            item.strip()
            for item in (
                priority_missing + (missing_information or [])
            )
            if item and item.strip()
        )
    )
    if trade_settlement_risk is not None:
        gaps = list(
            dict.fromkeys(
                gaps + trade_settlement_risk.information_gaps
            )
        )
    if (
        country_environment is not None
        and country_environment.review_priority
        == "INSUFFICIENT_INFORMATION"
    ):
        gaps = list(
            dict.fromkeys(gaps + country_environment.reasons)
        )
    calculation_versions = [
        stage2_result.calculation_version,
        assessment.calculation_version,
    ]
    if trade_settlement_risk is not None:
        calculation_versions.append(
            trade_settlement_risk.calculation_version
        )
    if country_environment is not None:
        calculation_versions.append(country_environment.rule_version)
    packet = ConsultationPacket(
        case_id=case_id,
        calculation_version="+".join(calculation_versions),
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        input_hash=_input_hash(
            confirmation=confirmation,
            stage1=stage1,
            stage2_input=stage2_input,
            trade_settlement_risk=trade_settlement_risk,
            country_environment=country_environment,
            official_candidate_shortlist=official_candidate_shortlist,
            installment_payment_statuses=(
                materialized_payment_statuses
            ),
        ),
        exchange_rate_as_of=stage1.as_of,
        scenario_ids=[
            item.scenario_name for item in stage2_result.scenario_results
        ],
        company_summary=CompanySummary(
            trade_type=stage2_result.trade_type,
            currency=stage2_result.currency,
            counterparty_country=counterparty_country,
            settlement_date=_settlement_date(stage2_result),
            trade_amount_fx=stage2_result.total_foreign_amount,
            company_role=extraction.company_role,
            incoterm=extraction.incoterm,
            payment_terms=extraction.payment_terms,
            payment_schedule=[
                PaymentScheduleSummary(
                    sequence=item.sequence or index + 1,
                    amount_fx=item.amount,
                    currency=item.currency or extraction.currency,
                    scheduled_date=item.due_date,
                    condition=item.condition,
                )
                for index, item in enumerate(extraction.installments)
            ],
        ),
        exposure_summary=ExposureSummary(
            gross_exposure_fx=stage2_result.total_foreign_amount,
            usable_fx_balance=stage2_result.held_fx_used,
            existing_hedge_fx=stage2_result.hedged_amount,
            open_exposure_fx=stage2_result.open_exposure,
        ),
        risk_summary=PacketRiskSummary(
            status=assessment.status,
            worst_scenario_id=assessment.worst_scenario_id,
            additional_cost_or_receipt_loss_krw=money_string(loss),
            cash_after_settlement_krw=worst.ending_cash,
            buffer_shortfall_krw=worst.maximum_buffer_shortfall,
            cash_deficit_krw=worst.cash_deficit,
            payment_gap_krw=worst.post_credit_shortfall,
            risk_codes=assessment.risk_codes,
        ),
        protection_summary=_protection_summary(
            stage2_result=stage2_result,
            trade_settlement_risk=trade_settlement_risk,
            payment_statuses=materialized_payment_statuses,
        ),
        risk_findings=assessment.findings,
        trade_settlement_risk=trade_settlement_risk,
        country_environment=country_environment,
        consultation_topics=consultation_topics,
        consultation_priorities=consultation_priorities,
        other_consultation_topics=other_consultation_topics,
        consultation_priority_fingerprint=priority_fingerprint,
        installment_payment_statuses=materialized_payment_statuses,
        official_candidate_shortlist=official_candidate_shortlist,
        missing_information=gaps,
        required_documents=_required_documents(
            consultation_topics,
            consultation_priorities,
        ),
        bank_questions=_questions(
            consultation_topics,
            consultation_priorities,
        ),
        safety_boundaries=SAFETY_BOUNDARIES,
        source_documents=[
            SourceDocumentReference(
                document_id=confirmation.source_sha256,
                filename=confirmation.source_filename,
                document_type=extraction.document_type,
            )
        ],
        user_confirmed_fields=_confirmed_fields(confirmation),
        disclaimer=DISCLAIMER,
    )
    return ConsultationPacketResult(
        packet=packet,
        markdown=_markdown(packet),
    )
