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
    "FORECAST": "외부 Stage 1 예측 결과",
    "CALCULATION": "결정론적 계산",
}


def status_badge(status: str) -> str:
    return "`{}` · {}".format(status, STATUS_HELP.get(status, "상태"))


def render_stepper(completed_stage: int) -> None:
    labels = [
        "0 문서",
        "확인",
        "1 시나리오",
        "2 계산",
        "3 전략",
        "4 상품",
        "5 보고서",
    ]
    cells = st.columns(len(labels))
    for index, (cell, label) in enumerate(zip(cells, labels)):
        icon = "✅" if index <= completed_stage else "○"
        cell.markdown(
            "<div style='text-align:center;font-size:0.84rem'>"
            "{}<br>{}</div>".format(icon, label),
            unsafe_allow_html=True,
        )


def render_validation(validation: ValidationResult) -> None:
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
    with st.expander("Workflow 실행 추적", expanded=False):
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
