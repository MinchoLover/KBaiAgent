import json
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import streamlit as st

from schemas import TradeDocumentExtraction, ValidationResult
from src.workflow.state import WorkflowState


STATUS_HELP = {
    "EXPLICIT": "문서에 직접 쓰인 값",
    "DERIVED": "문서 조건을 일반 코드로 계산한 값",
    "INFERRED": "문맥 추론값이며 사람 검토가 필요",
    "STRESS": "예측이 아닌 가정",
    "FORECAST": "외부 환율 전망 결과",
    "CALCULATION": "결정론적 계산",
}

USER_FIELD_LABELS = {
    "seller_name": "판매자",
    "seller_country": "판매자 국가",
    "buyer_name": "구매자",
    "buyer_country": "구매자 국가",
    "currency": "거래 통화",
    "grand_total": "문서 총액",
    "amount_due": "분석 대상 예정 결제액",
    "issue_date": "발행일",
    "contract_date": "계약일",
    "shipment_date": "선적일",
    "explicit_due_date": "결제일",
    "payment_terms": "결제조건",
    "installments": "분할결제 일정",
}

SCHEDULED_EXPOSURE_WARNING = (
    "현재 분석은 계약서에 명시된 예정 결제액을 기준으로 합니다. "
    "실제 입금·지급 이력을 반영한 현재 미수·미지급 잔액은 "
    "별도 확인이 필요합니다."
)

CONSULTATION_RATIONALE_LABELS = {
    "-5% ending cash": "환율 5% 하락 시 예상 현금",
    "buffer shortfall": "최소 운영자금 대비 부족액",
    "cash deficit": "실제 현금 적자",
    "payment/post-credit deficit": "대출한도 반영 후 부족액",
    "trade review": "거래 검토 우선도",
    "목표 buffer": "최소 유지 운영자금",
}

CONSULTATION_STATUS_LABELS = {
    "ELEVATED_REVIEW": "추가 검토 우선도",
    "HIGH_REVIEW": "높은 검토 우선도",
    "STANDARD_REVIEW": "정기 확인",
    "UNKNOWN": "확인 필요",
}

USER_ISSUE_MESSAGES = {
    "MISSING_CORE_EVIDENCE": "원문 근거를 확인해 주세요.",
    "INFERRED_CRITICAL_FIELD": "AI가 추론한 값이므로 원문 대조가 필요합니다.",
    "EVIDENCE_NOT_IN_SOURCE": "제시된 근거 문구를 원문에서 찾지 못했습니다.",
    "EVIDENCE_VALUE_MISMATCH": "원문 근거와 현재 입력값이 서로 다릅니다.",
    "EVIDENCE_UNVERIFIABLE": "독립된 원문 텍스트로 자동 대조할 수 없습니다.",
    "MISSING_REQUIRED_FIELD": "계산에 필요한 값이 비어 있습니다.",
    "AMBIGUOUS_DUE_DATE": "결제일 또는 결제조건을 하나로 확정해 주세요.",
    "DUE_DATE_CONFLICT": "문서에 표시된 결제일과 계산된 결제일이 다릅니다.",
    "AMOUNT_CONFLICT": "문서의 금액 정보가 서로 다릅니다.",
}


def status_badge(status: str) -> str:
    return "`{}` · {}".format(status, STATUS_HELP.get(status, "상태"))


def amount_due_user_label(trade_type: Optional[str]) -> str:
    if trade_type == "EXPORT":
        return "분석 대상 예정 수취액"
    if trade_type == "IMPORT":
        return "분석 대상 예정 지급액"
    return "분석 대상 예정 결제액"


def consultation_priority_reason_copy(value: str) -> str:
    replacements = [
        (
            "Open Account 등 회수 보호 검토 finding과",
            "외상거래(Open Account) 등 결제·회수 보호 필요와",
        ),
        (
            "기존 LOSS_LIMIT_EXCEEDED finding과",
            "기존 허용손실 초과 신호와",
        ),
        (
            "기존 LIQUIDITY_BUFFER_RISK finding에 따라",
            "최소 운영자금 대비 부족 신호에 따라",
        ),
        (
            "기존 PAYMENT_CAPACITY_RISK finding의",
            "지급능력 확인 신호의",
        ),
        (
            "기존 구조화 risk finding 또는 review need가 생성한 "
            "상담 항목을 명시적 category tie-break에 따라",
            "기존 구조화 위험 신호 또는 검토 필요가 생성한 "
            "상담 항목을 정해진 상담 순서에 따라",
        ),
        ("HIGH_REVIEW", "높은 검토 우선도"),
        ("ELEVATED_REVIEW", "추가 검토 우선도"),
        ("STANDARD_REVIEW", "정기 확인"),
    ]
    result = value
    for source, target in replacements:
        result = result.replace(source, target)
    return result


def consultation_rationale_label(value: str) -> str:
    return CONSULTATION_RATIONALE_LABELS.get(value, value)


def consultation_status_label(value: str) -> str:
    return CONSULTATION_STATUS_LABELS.get(value, value)


def format_decimal_display(
    value: Any,
    decimal_places: int = 0,
) -> str:
    try:
        parsed = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return str(value)
    if not parsed.is_finite():
        return str(value)
    return format(parsed, ",.{}f".format(decimal_places))


def format_krw(value: Any) -> str:
    return "{}원".format(format_decimal_display(value))


def format_foreign(value: Any, currency: str) -> str:
    return "{} {}".format(
        format_decimal_display(value, decimal_places=2),
        currency,
    )


def format_ratio(value: Any) -> str:
    try:
        percentage = Decimal(str(value)) * Decimal("100")
    except (InvalidOperation, ValueError):
        return str(value)
    if not percentage.is_finite():
        return str(value)
    places = 0 if percentage == percentage.to_integral_value() else 1
    return "{}%".format(
        format(percentage, ",.{}f".format(places))
    )


def render_stepper(completed_stage: int) -> None:
    labels = [
        "거래 확인",
        "금융 리스크 분석",
        "상담 준비",
        "결과 및 전달",
    ]
    completion_thresholds = [1, 3, 4, 6]
    cells = st.columns(len(labels))
    for index, (cell, label) in enumerate(zip(cells, labels)):
        is_done = completed_stage >= completion_thresholds[index]
        previous_threshold = (
            -1 if index == 0 else completion_thresholds[index - 1]
        )
        is_current = not is_done and completed_stage >= previous_threshold
        state_class = "done" if is_done else "current" if is_current else "todo"
        icon = "✓" if is_done else str(index + 1)
        cell.markdown(
            "<div class='journey-step {}'>"
            "<span class='journey-dot'>{}</span>"
            "<span>{}</span></div>".format(
                state_class,
                icon,
                label,
            ),
            unsafe_allow_html=True,
        )


def validation_issue_copy(field: Optional[str], code: str) -> str:
    label = USER_FIELD_LABELS.get(field or "", field or "거래정보")
    guidance = USER_ISSUE_MESSAGES.get(
        code,
        "값과 원문 근거를 다시 확인해 주세요.",
    )
    return "{}: {}".format(label, guidance)


def render_validation_summary(validation: ValidationResult) -> None:
    actionable = [
        item
        for item in validation.issues
        if item.severity in {"CRITICAL", "HIGH", "MEDIUM"}
    ]
    if not actionable:
        st.success("자동 검증을 통과했습니다. 핵심 거래정보를 원문과 대조해 주세요.")
        return
    st.markdown("**확인이 필요한 항목 {}건**".format(len(actionable)))
    for item in actionable:
        st.markdown("- {}".format(validation_issue_copy(item.field, item.code)))


def render_validation(validation: ValidationResult) -> None:
    for item in validation.normalization_audit:
        if item.status in {
            "NORMALIZED",
            "AUTO",
            "USER_OVERRIDE",
            "USER_CONTEXT_APPLIED",
            "EVIDENCE_LINKED",
            "VERIFIED",
            "USER_CONFIRMED_OVERRIDE",
        }:
            st.info(item.message)
    if not validation.issues:
        st.success("결정론적 검증 PASS")
        return
    severity_icon = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "MEDIUM": "🟡",
        "LOW": "🔵",
    }
    for issue in validation.issues:
        st.write(
            "{} **{}** · `{}` · {}".format(
                severity_icon[issue.severity],
                issue.severity,
                issue.code,
                issue.message,
            )
        )


def evidence_rows(
    extraction: TradeDocumentExtraction,
) -> List[Dict[str, Any]]:
    return [
        {
            "필드": item.field,
            "페이지": item.page,
            "상태": item.extraction_type,
            "원문 근거": item.source_text,
            "판정 이유": item.confidence_reason,
        }
        for item in extraction.evidence
    ]


def decimal_text(
    value: Any,
    field_name: str,
    allow_zero: bool = True,
    allow_negative: bool = False,
) -> str:
    text = str(value).strip().replace(",", "")
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            "{}은 숫자 문자열이어야 합니다.".format(field_name)
        ) from exc
    if (
        not parsed.is_finite()
        or (not allow_zero and parsed == 0)
        or (not allow_negative and parsed < 0)
    ):
        raise ValueError(
            "{}은 {}이어야 합니다.".format(
                field_name,
                (
                    "유한한 signed 값"
                    if allow_negative
                    else "0보다 큰 값"
                    if not allow_zero
                    else "0 이상의 값"
                ),
            )
        )
    return format(parsed, "f")


def optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    text = str(value or "").strip()
    if text in {"nan", "NaN", "NaT", "<NA>"}:
        return None
    return text or None


def optional_positive_integer(
    value: Any,
    field_name: str,
) -> Optional[int]:
    text = optional_text(value)
    if text is None:
        return None
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            "{}은 양의 정수여야 합니다.".format(field_name)
        ) from exc
    if (
        not parsed.is_finite()
        or parsed < 1
        or parsed != parsed.to_integral_value()
    ):
        raise ValueError(
            "{}은 양의 정수여야 합니다.".format(field_name)
        )
    return int(parsed)


def json_download(
    *,
    label: str,
    value: Any,
    filename: str,
    key: str,
) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    payload = json.dumps(value, ensure_ascii=False, indent=2)
    st.download_button(
        label,
        data=payload,
        file_name=filename,
        mime="application/json",
        key=key,
    )


def render_workflow_trace(state: WorkflowState) -> None:
    with st.expander("분석 근거 및 기술 정보 보기", expanded=False):
        st.caption(
            "case_id={} · mode={} · final={} · user_confirmed={}".format(
                state.case_id,
                state.mode,
                state.final_status.value,
                state.user_confirmed,
            )
        )
        rows = [
            {
                "순서": item.sequence,
                "Stage": item.stage,
                "상태": item.status.value,
                "provider": item.provider,
                "duration_ms": item.duration_ms,
                "fallback": item.fallback_used,
                "근거 참조": ", ".join(item.evidence),
                "경고": " | ".join(item.warnings),
                "critic": (
                    ""
                    if item.critic_passed is None
                    else "PASS"
                    if item.critic_passed
                    else "FAIL"
                ),
                "retry_count": item.retry_count,
                "rewrite_count": item.rewrite_count,
            }
            for item in state.trace
        ]
        st.dataframe(rows, width="stretch", hide_index=True)
        if state.errors:
            st.error(" | ".join(state.errors))
