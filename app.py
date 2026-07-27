import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from prompt import get_prompt_version
from sample_data import sample_extraction
from schemas import (
    PaymentInstallment,
    TradeDocumentExtraction,
    ValidationResult,
)
from src.application.stage2_input_service import (
    Stage2FormInput,
    build_stage2_input_from_form,
)
from src.application.consultation_service import build_decision_support
from src.config import Settings
from src.demo import run_decision_support_demo
from src.document_intake.confirmation import (
    ConfirmationRecord,
    create_confirmation_record,
    discard_stale_evidence_after_review,
    validate_confirmation,
)
from src.document_intake.extractor import (
    ExtractionError,
    extract_trade_document_with_metadata,
)
from src.document_intake.normalization import (
    normalize_country_name,
    normalize_date_text,
)
from src.document_intake.source_evidence import extract_pdf_page_texts
from src.domain.consultation_models import (
    ConsultationPacketResult,
    ConsultationTopic,
    DecisionSupportResult,
    RiskAssessment,
)
from src.domain.product_models import Stage4Result
from src.domain.report_models import ReportResult
from src.domain.stage1_models import Stage1LoadResult
from src.domain.stage1_web_models import MarketIntegrationResult
from src.domain.stage2_models import Stage2Input, Stage2Result
from src.domain.stage3_models import Stage3Assumptions, Stage3Result
from src.security.upload_guard import validate_upload
from src.ui.components import (
    decimal_text,
    evidence_rows,
    format_decimal_display,
    format_foreign,
    format_krw,
    format_ratio,
    json_download,
    optional_positive_integer,
    optional_text,
    render_stepper,
    render_validation,
    render_workflow_trace,
    status_badge,
)
from src.ui.state import (
    clear_confirmation_and_later,
    clear_downstream,
    clear_review_widgets,
    clear_transaction_widgets,
    input_signature,
    sync_input_signature,
)
from src.workflow.orchestrator import WorkflowOrchestrator
from src.workflow.state import WorkflowState
from validators import (
    apply_deterministic_review_state,
    build_stage0_output,
    build_stage2_input,
)


ROOT = Path(__file__).resolve().parent
SAMPLE_PATH = ROOT / "samples" / "sample_invoice.png"
DEMO_EXPORT_PATH = ROOT / "samples" / "demo_export_invoice.pdf"
DEMO_EXPORT_LABEL_PATH = (
    ROOT / "dataset" / "labels" / "kr_seller_export_012.json"
)


def _model_from_state(key: str, model_class: Any) -> Optional[Any]:
    value = st.session_state.get(key)
    if value is None:
        return None
    return model_class.model_validate(value)


def _save_model(key: str, value: Any) -> None:
    st.session_state[key] = value.model_dump()


def _live_source_page_texts(
    *,
    run_mode: str,
    file_bytes: bytes,
    mime_type: str,
) -> Optional[List[str]]:
    """Return in-memory source text only for the current live upload."""

    if run_mode != "LIVE":
        return None
    if mime_type == "application/pdf":
        return extract_pdf_page_texts(file_bytes)
    # Live images have no independent local text layer. An explicit empty
    # sequence preserves the fail-closed evidence policy.
    return []


def _save_decision_support(value: DecisionSupportResult) -> None:
    _save_model("risk_assessment", value.risk_assessment)
    st.session_state["consultation_topics"] = [
        item.model_dump() for item in value.consultation_topics
    ]
    _save_model("consultation_packet", value.consultation_packet)


def _consultation_topics_from_state() -> List[ConsultationTopic]:
    return [
        ConsultationTopic.model_validate(item)
        for item in st.session_state.get("consultation_topics", [])
    ]


def _workflow_from_state() -> Optional[WorkflowState]:
    value = st.session_state.get("workflow_state")
    if value is None:
        return None
    return WorkflowState.model_validate(value)


def _save_workflow(value: WorkflowState) -> None:
    _save_model("workflow_state", value)


def _demo_fixture(
    company_role: str,
) -> Tuple[Path, str, TradeDocumentExtraction]:
    if company_role == "SELLER":
        extraction = TradeDocumentExtraction.model_validate_json(
            DEMO_EXPORT_LABEL_PATH.read_text(encoding="utf-8")
        )
        return DEMO_EXPORT_PATH, "application/pdf", extraction
    return SAMPLE_PATH, "image/png", sample_extraction("BUYER")


def _completed_stage() -> int:
    keys = [
        "extraction",
        "confirmation",
        "stage1_load",
        "stage2_result",
        "stage3_result",
        "stage4_result",
        "report_result",
    ]
    completed = -1
    for index, key in enumerate(keys):
        if key in st.session_state:
            if key == "confirmation":
                confirmation_validation = st.session_state.get(
                    "confirmation_validation"
                )
                if confirmation_validation is None or not (
                    ValidationResult.model_validate(
                        confirmation_validation
                    ).stage2_allowed
                ):
                    break
            completed = index
        else:
            break
    return completed


def _blank_to_none(value: Any) -> Optional[str]:
    return optional_text(value)


def _date_or_none(value: Any) -> Optional[str]:
    return normalize_date_text(optional_text(value))


def _normalized_company_country(value: str) -> str:
    normalized, _ = normalize_country_name(value, "company_country")
    if (
        normalized is None
        or len(normalized) != 2
        or not normalized.isalpha()
    ):
        raise ValueError(
            "회사 국가를 확인 가능한 ISO alpha-2 코드로 정규화할 수 없습니다."
        )
    return normalized


def _review_audit_values(
    extraction: TradeDocumentExtraction,
    company_country: str,
) -> Dict[str, Any]:
    return {
        "company_role": extraction.company_role,
        "company_country": company_country,
        "trade_type": extraction.trade_type,
        "seller_country": extraction.seller_country,
        "buyer_country": extraction.buyer_country,
        "currency": extraction.currency,
        "amount_due": extraction.amount_due,
        "contract_date": extraction.contract_date,
        "explicit_due_date": extraction.explicit_due_date,
    }


def _safe_index(options: List[str], value: str) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0


def _decimal_or_zero(value: Any) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")
    return parsed if parsed.is_finite() else Decimal("0")


def _decimal_total(values: List[str]) -> str:
    return format(
        sum(
            (Decimal(str(value)) for value in values),
            Decimal("0"),
        ),
        "f",
    )


def _stage2_form_defaults(
    value: Optional[Stage2Input],
) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "current_cash": "200000000",
        "minimum_buffer": "50000000",
        "credit_limit": "30000000",
        "acceptable_loss": "10000000",
        "as_of": date.today(),
        "usable_fx": "10000",
        "same_flow_amount": "0",
        "same_flow_date": date.today(),
        "same_flow_direction": "INFLOW",
        "hedge_amount": "0",
        "hedge_rate": "1400",
        "hedge_fee": "0",
        "bank_spread": "15",
        "bank_fee": "50000",
        "cashflows": [
            {
                "date": str(date.today()),
                "amount": "30000000",
                "direction": "INFLOW",
                "category": "REVENUE",
                "description": "예정 매출 입금",
            }
        ],
        "revenue_reduction": "0",
        "revenue_delay": 0,
        "cost_increase": "0",
    }
    if value is None:
        return defaults

    flows = [
        flow
        for exposure in value.exposures
        for flow in exposure.same_currency_flows
    ]
    hedges = [
        exposure.existing_hedge
        for exposure in value.exposures
        if exposure.existing_hedge is not None
    ]
    defaults.update(
        {
            "current_cash": value.current_krw_cash,
            "minimum_buffer": value.minimum_cash_buffer,
            "credit_limit": value.credit_limit,
            "acceptable_loss": value.acceptable_fx_loss,
            "as_of": date.fromisoformat(value.as_of_date),
            "usable_fx": _decimal_total(
                [
                    exposure.usable_fx_balance
                    for exposure in value.exposures
                ]
            ),
            "same_flow_amount": _decimal_total(
                [flow.amount for flow in flows]
            ),
            "same_flow_date": (
                date.fromisoformat(flows[0].date)
                if flows
                else date.fromisoformat(value.as_of_date)
            ),
            "same_flow_direction": (
                flows[0].direction
                if flows
                else (
                    "INFLOW"
                    if value.exposures[0].trade_type == "IMPORT"
                    else "OUTFLOW"
                )
            ),
            "hedge_amount": _decimal_total(
                [hedge.amount for hedge in hedges]
            ),
            "hedge_rate": (
                hedges[0].locked_rate if hedges else "1400"
            ),
            "hedge_fee": _decimal_total(
                [hedge.fee for hedge in hedges]
            ),
            "bank_spread": value.bank_spread_bps,
            "bank_fee": value.bank_fee,
            "cashflows": [
                item.model_dump() for item in value.krw_cashflows
            ],
            "revenue_reduction": (
                value.composite_stress.revenue_reduction_percent
            ),
            "revenue_delay": value.composite_stress.revenue_delay_days,
            "cost_increase": (
                value.composite_stress.cost_increase_percent
            ),
        }
    )
    return defaults


def _scenario_label(value: str) -> str:
    if value == "BASE":
        return "기준 환율"
    if value.startswith("STRESS_") and value.endswith("PCT"):
        percentage = value[len("STRESS_") : -len("PCT")]
        return "환율 {}%".format(percentage)
    return value.replace("_", " ")


def _risk_summary(
    result: Stage2Result,
) -> Tuple[str, str, str, str]:
    scenarios = result.scenario_results
    highest_credit_gap = max(
        (_decimal_or_zero(item.post_credit_shortfall) for item in scenarios),
        default=Decimal("0"),
    )
    highest_buffer_gap = max(
        (_decimal_or_zero(item.maximum_buffer_shortfall) for item in scenarios),
        default=Decimal("0"),
    )
    highest_loss = max(
        (_decimal_or_zero(item.loss_vs_base) for item in scenarios),
        default=Decimal("0"),
    )
    first_gap_dates = sorted(
        item.first_buffer_shortfall_date
        for item in scenarios
        if item.first_buffer_shortfall_date
    )
    first_gap = first_gap_dates[0] if first_gap_dates else "발생하지 않음"
    if highest_credit_gap > 0:
        return (
            "danger",
            "유동성 보강 필요",
            "대출한도 반영 후에도 최대 {} 부족할 수 있습니다.".format(
                format_krw(highest_credit_gap)
            ),
            "첫 운영자금 방어선 이탈: {}".format(first_gap),
        )
    if highest_buffer_gap > 0:
        return (
            "warning",
            "운영자금 주의",
            "최악 가정에서 운영자금 방어선이 최대 {} 부족합니다.".format(
                format_krw(highest_buffer_gap)
            ),
            "첫 운영자금 방어선 이탈: {}".format(first_gap),
        )
    if any(item.acceptable_loss_exceeded for item in scenarios):
        return (
            "warning",
            "손실한도 점검",
            "현금은 버티지만 설정한 환율손실 한도를 넘는 구간이 있습니다.",
            "가장 큰 기준 대비 손실: {}".format(format_krw(highest_loss)),
        )
    return (
        "safe",
        "방어선 유지",
        "현재 입력에서는 모든 환율 가정에서 운영자금 방어선을 지킵니다.",
        "대출한도 반영 후 추가 부족액 0원",
    )


def _section_intro(
    eyebrow: str,
    title: str,
    description: str,
) -> None:
    st.markdown(
        "<div class='section-intro'>"
        "<span>{}</span><h2>{}</h2><p>{}</p></div>".format(
            escape(eyebrow),
            escape(title),
            escape(description),
        ),
        unsafe_allow_html=True,
    )


def _advanced_downloads_title() -> None:
    st.markdown(
        "<div class='advanced-label'>고급 데이터 · 검증 및 연동용</div>",
        unsafe_allow_html=True,
    )


def _demo_all(company_role: str = "BUYER") -> None:
    clear_transaction_widgets(st.session_state)
    st.session_state["run_mode_widget"] = "데모 모드"
    st.session_state["company_role_widget"] = (
        "구매자 · BUYER"
        if company_role == "BUYER"
        else "판매자 · SELLER"
    )
    st.session_state["company_country_widget"] = "KR"
    st.session_state["stage1_mode_widget"] = "EXTERNAL_STAGE1"
    result = run_decision_support_demo(company_role)
    extraction = result["extraction"]
    source_path, source_mime, original_extraction = _demo_fixture(company_role)
    _save_model("extraction", extraction)
    _save_model("extraction_original", original_extraction)
    _save_model("extraction_validation", result["validation"])
    _save_model("confirmation", result["confirmation"])
    _save_model("confirmation_validation", result["validation"])
    st.session_state["stage0_output"] = build_stage0_output(
        extraction=extraction,
        validation=result["validation"],
        confirmations=result["confirmation"].checks,
        source_filename=source_path.name,
        prompt_version=get_prompt_version(),
        confirmation_record=result["confirmation"],
    )
    st.session_state["stage2_document_input"] = build_stage2_input(
        extraction=extraction,
        validation=result["validation"],
        confirmations=result["confirmation"].checks,
        source_filename=source_path.name,
        source_sha256=result["confirmation"].source_sha256,
        confirmed_at=result["confirmation"].confirmed_at,
    )
    _save_model("stage1_load", result["stage1_load"])
    _save_model("stage2_input", result["stage2_input"])
    _save_model("stage2_result", result["stage2"])
    _save_model("risk_assessment", result["risk_assessment"])
    st.session_state["consultation_topics"] = [
        item.model_dump() for item in result["consultation_topics"]
    ]
    _save_model("consultation_packet", result["consultation_packet"])
    _save_model("stage3_result", result["stage3"])
    _save_model("stage4_result", result["stage4"])
    _save_model("report_result", result["report"])
    _save_workflow(result["workflow_state"])
    metadata = validate_upload(
        file_bytes=source_path.read_bytes(),
        filename=source_path.name,
        claimed_mime_type=source_mime,
    )
    st.session_state["upload_metadata"] = {
        "filename": metadata.filename,
        "mime_type": metadata.mime_type,
        "size_bytes": metadata.size_bytes,
        "sha256": metadata.sha256,
        "page_count": metadata.page_count,
    }
    st.session_state["skip_signature_sync_once"] = True
    st.session_state["demo_just_loaded"] = (
        "수입기업" if company_role == "BUYER" else "수출기업"
    )


def _reset_state() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


load_dotenv()
settings = Settings.from_env()
orchestrator = WorkflowOrchestrator(settings=settings)


def _store_intake_workflow(
    *,
    mode: str,
    extraction: TradeDocumentExtraction,
    validation: ValidationResult,
    confirmation: Optional[ConfirmationRecord] = None,
    provider: Optional[str] = None,
    duration_ms: Optional[int] = None,
    retry_count: int = 0,
) -> None:
    workflow_mode = "ONLINE" if mode == "LIVE" else "OFFLINE"
    current = _workflow_from_state()
    if current is not None and current.mode == workflow_mode:
        state = orchestrator.register_intake(
            current,
            extraction=extraction,
            validation=validation,
            confirmation=confirmation,
            intake_provider=provider,
            intake_duration_ms=duration_ms,
            intake_retry_count=retry_count,
        )
    else:
        state = orchestrator.initialize(
            mode=workflow_mode,
            extraction=extraction,
            validation=validation,
            confirmation=confirmation,
            intake_provider=provider,
            intake_duration_ms=duration_ms,
            intake_retry_count=retry_count,
        )
    _save_workflow(state)

st.set_page_config(
    page_title="FX Flow · 환율 현금흐름 점검",
    page_icon="₩",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
<style>
:root {
  --ink: #f4f7fb;
  --muted: #92a4ba;
  --panel: rgba(14, 27, 44, 0.82);
  --panel-strong: #101f32;
  --line: rgba(148, 172, 204, 0.16);
  --mint: #5de4c7;
  --blue: #66afff;
  --amber: #ffcc66;
  --danger: #ff7285;
}

html {scroll-behavior: smooth;}
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(circle at 82% -8%, rgba(62, 112, 164, 0.18), transparent 34rem),
    radial-gradient(circle at 18% 4%, rgba(93, 228, 199, 0.08), transparent 28rem),
    #07111f;
}
[data-testid="stHeader"] {background: transparent;}
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0b1727 0%, #091321 100%);
  border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
  color: #b7c4d4;
}
.block-container {
  padding-top: 2.1rem;
  padding-bottom: 4rem;
  max-width: 1480px;
}
h1, h2, h3 {letter-spacing: -0.035em;}
p {line-height: 1.65;}

div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button {
  border-radius: 10px;
  min-height: 2.7rem;
  font-weight: 700;
  border: 1px solid rgba(148, 172, 204, 0.2);
  transition: transform 120ms ease, border-color 120ms ease;
}
div[data-testid="stButton"] > button:hover,
div[data-testid="stDownloadButton"] > button:hover {
  transform: translateY(-1px);
  border-color: rgba(93, 228, 199, 0.7);
}
div[data-testid="stButton"] > button[kind="primary"],
div[data-testid="stFormSubmitButton"] > button[kind="primary"],
div[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"] {
  background: linear-gradient(135deg, #5de4c7, #55bde8);
  color: #04131a;
  border: 0;
  box-shadow: 0 10px 28px rgba(52, 196, 179, 0.18);
}
div[data-testid="stButton"] > button[kind="primary"] *,
div[data-testid="stFormSubmitButton"] > button[kind="primary"] *,
div[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"] * {
  color: #04131a !important;
}

div[data-testid="stMetric"] {
  background: linear-gradient(180deg, rgba(18, 35, 55, 0.92), rgba(12, 25, 41, 0.92));
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 1rem 1.05rem;
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.12);
}
[data-testid="stMetricLabel"] {color: var(--muted);}
[data-testid="stMetricValue"] {
  font-size: 1.48rem;
  letter-spacing: -0.04em;
}
[data-testid="stDataFrame"] {
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
}
[data-testid="stExpander"] {
  border-color: var(--line);
  border-radius: 12px;
  background: rgba(10, 22, 37, 0.54);
}

.stTabs [data-baseweb="tab-list"] {
  gap: 0.25rem;
  padding: 0.35rem;
  border-radius: 14px;
  background: rgba(10, 22, 37, 0.78);
  border: 1px solid var(--line);
}
.stTabs [data-baseweb="tab"] {
  height: 3rem;
  padding: 0 1rem;
  border-radius: 10px;
  color: #8fa1b8;
  font-weight: 700;
}
.stTabs [aria-selected="true"] {
  color: #06141c;
  background: var(--mint);
}
.stTabs [data-baseweb="tab-highlight"] {display: none;}

.sidebar-brand {
  padding: 0.2rem 0 1rem;
}
.sidebar-brand .mark {
  display: inline-flex;
  width: 2.15rem;
  height: 2.15rem;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  margin-right: 0.55rem;
  color: #07111f;
  background: linear-gradient(135deg, var(--mint), var(--blue));
  font-size: 0.83rem;
  font-weight: 900;
}
.sidebar-brand strong {
  color: var(--ink);
  font-size: 1rem;
  letter-spacing: 0.04em;
}
.sidebar-brand p {
  margin: 0.45rem 0 0;
  color: var(--muted) !important;
  font-size: 0.82rem;
}

.hero-shell {
  position: relative;
  overflow: hidden;
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(260px, 0.62fr);
  gap: 2rem;
  align-items: end;
  padding: clamp(1.5rem, 4vw, 3rem);
  margin-bottom: 1.2rem;
  border: 1px solid rgba(110, 148, 190, 0.18);
  border-radius: 24px;
  background:
    linear-gradient(125deg, rgba(18, 38, 60, 0.98), rgba(9, 23, 39, 0.94)),
    #0d1b2d;
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.2);
}
.hero-shell:after {
  content: "";
  position: absolute;
  width: 24rem;
  height: 24rem;
  right: -7rem;
  top: -13rem;
  border-radius: 999px;
  background: radial-gradient(circle, rgba(93, 228, 199, 0.2), transparent 68%);
}
.hero-copy, .hero-signal {position: relative; z-index: 1;}
.eyebrow {
  color: var(--mint);
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.hero-copy h1 {
  max-width: 850px;
  margin: 0.55rem 0 0.7rem;
  color: var(--ink);
  font-size: clamp(2rem, 4vw, 3.55rem);
  line-height: 1.04;
}
.hero-copy p {
  max-width: 760px;
  margin: 0;
  color: #a9b9ca;
  font-size: 1rem;
}
.hero-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 1.3rem;
}
.hero-pill {
  padding: 0.4rem 0.65rem;
  border: 1px solid rgba(148, 172, 204, 0.18);
  border-radius: 999px;
  color: #c3cfdd;
  background: rgba(7, 17, 31, 0.5);
  font-size: 0.76rem;
  font-weight: 700;
}
.hero-signal {
  min-height: 175px;
  padding: 1.25rem;
  border: 1px solid rgba(148, 172, 204, 0.17);
  border-radius: 18px;
  background: rgba(6, 18, 31, 0.58);
  backdrop-filter: blur(14px);
}
.hero-signal small {
  display: block;
  margin-bottom: 0.65rem;
  color: var(--muted);
  font-weight: 800;
  letter-spacing: 0.08em;
}
.hero-signal strong {
  display: block;
  margin-bottom: 0.55rem;
  color: var(--ink);
  font-size: 1.35rem;
  line-height: 1.25;
}
.hero-signal p {
  margin: 0;
  color: #91a5bb;
  font-size: 0.82rem;
}
.hero-signal.safe {border-color: rgba(93, 228, 199, 0.35);}
.hero-signal.warning {border-color: rgba(255, 204, 102, 0.38);}
.hero-signal.danger {border-color: rgba(255, 114, 133, 0.42);}

.journey-step {
  display: flex;
  min-height: 3.35rem;
  align-items: center;
  justify-content: center;
  gap: 0.42rem;
  color: #71849b;
  font-size: 0.74rem;
  font-weight: 700;
  text-align: center;
}
.journey-step.done {color: #c7d5e4;}
.journey-dot {
  display: inline-flex;
  width: 1.42rem;
  height: 1.42rem;
  flex: 0 0 1.42rem;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(148, 172, 204, 0.23);
  border-radius: 999px;
  font-size: 0.68rem;
}
.journey-step.done .journey-dot {
  color: #07111f;
  border-color: var(--mint);
  background: var(--mint);
}

.section-intro {
  max-width: 860px;
  padding: 1.35rem 0 1rem;
}
.section-intro > span,
.advanced-label {
  color: var(--mint);
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.section-intro h2 {
  margin: 0.3rem 0 0.35rem;
  color: var(--ink);
  font-size: 1.8rem;
}
.section-intro p {
  margin: 0;
  color: var(--muted);
}
.advanced-label {margin: 0.25rem 0 0.55rem;}

.state-banner {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  padding: 1rem 1.1rem;
  margin: 0.4rem 0 1rem;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: rgba(13, 29, 47, 0.76);
}
.state-banner .state-icon {
  display: inline-flex;
  width: 2.1rem;
  height: 2.1rem;
  flex: 0 0 2.1rem;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: rgba(93, 228, 199, 0.12);
  color: var(--mint);
  font-weight: 900;
}
.state-banner strong {display: block; color: var(--ink);}
.state-banner p {margin: 0.15rem 0 0; color: var(--muted); font-size: 0.86rem;}
.state-banner.warning .state-icon {
  color: var(--amber);
  background: rgba(255, 204, 102, 0.11);
}
.state-banner.danger .state-icon {
  color: var(--danger);
  background: rgba(255, 114, 133, 0.1);
}

.risk-banner {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 1rem;
  align-items: center;
  padding: 1.2rem 1.35rem;
  margin: 0.75rem 0 1rem;
  border: 1px solid rgba(93, 228, 199, 0.28);
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(25, 65, 69, 0.65), rgba(12, 27, 44, 0.8));
}
.risk-banner.warning {
  border-color: rgba(255, 204, 102, 0.34);
  background: linear-gradient(135deg, rgba(79, 61, 25, 0.55), rgba(12, 27, 44, 0.8));
}
.risk-banner.danger {
  border-color: rgba(255, 114, 133, 0.38);
  background: linear-gradient(135deg, rgba(79, 31, 45, 0.58), rgba(12, 27, 44, 0.8));
}
.risk-banner .signal {
  min-width: 7rem;
  color: var(--mint);
  font-size: 0.76rem;
  font-weight: 900;
  letter-spacing: 0.08em;
}
.risk-banner.warning .signal {color: var(--amber);}
.risk-banner.danger .signal {color: var(--danger);}
.risk-banner strong {display: block; color: var(--ink); font-size: 1.12rem;}
.risk-banner p {margin: 0.15rem 0 0; color: var(--muted); font-size: 0.84rem;}
.risk-banner .detail {color: #bdc9d7; font-size: 0.78rem; text-align: right;}

.status-card {
  min-height: 255px;
  border: 1px solid var(--line);
  border-radius: 17px;
  padding: 1.2rem;
  background: linear-gradient(160deg, rgba(19, 39, 60, 0.96), rgba(10, 24, 40, 0.96));
  color: var(--ink);
  margin-bottom: 0.65rem;
  box-shadow: 0 20px 55px rgba(0, 0, 0, 0.15);
}
.status-card .rank {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}
.status-card .rank strong {font-size: 1.1rem;}
.status-card .chip {
  padding: 0.3rem 0.5rem;
  border-radius: 999px;
  color: var(--mint);
  background: rgba(93, 228, 199, 0.1);
  font-size: 0.68rem;
  font-weight: 800;
}
.status-card .mix {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.45rem;
  margin-bottom: 1rem;
}
.status-card .mix div {
  padding: 0.65rem 0.4rem;
  border-radius: 10px;
  background: rgba(4, 16, 29, 0.48);
  text-align: center;
}
.status-card .mix small {display: block; color: var(--muted); font-size: 0.67rem;}
.status-card .mix b {display: block; margin-top: 0.12rem; font-size: 0.95rem;}
.status-card .outcome {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.65rem;
}
.status-card .outcome small {display: block; color: var(--muted); font-size: 0.68rem;}
.status-card .outcome b {font-size: 0.9rem;}
.status-card .constraint {
  margin-top: 0.85rem;
  color: #aebdcb;
  font-size: 0.74rem;
}

@media (max-width: 900px) {
  .hero-shell {grid-template-columns: 1fr;}
  .hero-signal {min-height: auto;}
  .journey-step {font-size: 0;}
  .journey-dot {font-size: 0.68rem;}
  .risk-banner {grid-template-columns: 1fr;}
  .risk-banner .detail {text-align: left;}
  div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.75rem;
  }
  div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"])
    > div[data-testid="stColumn"] {
    width: 100% !important;
    min-width: 0 !important;
    flex: none !important;
  }
}
@media (max-width: 640px) {
  .block-container {padding-left: 1rem; padding-right: 1rem;}
  .hero-shell {padding: 1.35rem; border-radius: 18px;}
  .hero-copy h1 {font-size: 2rem;}
  div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) {
    grid-template-columns: 1fr;
  }
}
</style>
""",
    unsafe_allow_html=True,
)

st.session_state.setdefault(
    "run_mode_widget",
    (
        "데모 모드"
        if settings.demo_mode or not settings.live_extraction_ready
        else "실제 API 모드"
    ),
)
st.session_state.setdefault(
    "company_role_widget",
    "구매자 · BUYER",
)
st.session_state.setdefault("company_country_widget", "KR")
pending_company_role = st.session_state.pop(
    "pending_company_role_widget",
    None,
)
pending_company_country = st.session_state.pop(
    "pending_company_country_widget",
    None,
)
if pending_company_role is not None:
    st.session_state["company_role_widget"] = pending_company_role
if pending_company_country is not None:
    st.session_state["company_country_widget"] = pending_company_country

with st.sidebar:
    st.markdown(
        "<div class='sidebar-brand'><span class='mark'>FX</span>"
        "<strong>FLOW CONTROL</strong>"
        "<p>수출입 기업용 현금흐름 리스크 점검</p></div>",
        unsafe_allow_html=True,
    )
    st.markdown("#### 업무 환경")
    live_label = "실제 API 모드"
    mode_label = st.radio(
        "분석할 문서",
        ["데모 모드", live_label],
        key="run_mode_widget",
        help="API 키는 서버 환경변수에서만 읽습니다.",
    )
    run_mode = "LIVE" if mode_label == live_label else "DEMO"
    if run_mode == "LIVE" and not settings.live_extraction_ready:
        st.warning(
            "OPENAI_API_KEY 또는 live 설정이 없어 분석 시 데모 모드로 "
            "자동 전환하지 않습니다. 키를 설정하거나 데모 모드를 선택하세요."
        )
    with st.expander("연결 상태", expanded=False):
        st.caption(
            "문서 AI · {}".format(
                "사용 가능" if settings.live_extraction_ready else "데모 전용"
            )
        )
        st.caption(
            "API 인증 · {}".format(
                "설정됨" if settings.openai_api_key else "설정되지 않음"
            )
        )
        st.caption("모델은 서버 환경변수로 관리됩니다.")
    st.button(
        "수입기업 대표 데모",
        type="primary",
        width="stretch",
        on_click=_demo_all,
        args=("BUYER",),
    )
    st.button(
        "수출기업 대표 데모",
        width="stretch",
        on_click=_demo_all,
        args=("SELLER",),
    )
    loaded_demo = st.session_state.pop("demo_just_loaded", None)
    if loaded_demo:
        st.success("{} 샘플의 전체 분석 결과를 준비했습니다.".format(
            loaded_demo
        ))
    st.button(
        "세션 결과 초기화",
        width="stretch",
        on_click=_reset_state,
    )
    st.divider()
    with st.expander("개인정보 및 계산 원칙", expanded=False):
        st.caption(
            "문서 원문은 로그·데이터셋에 자동 저장하지 않습니다. "
            "AI 추출값은 사용자 확인 전 계산에 들어가지 않습니다."
        )

hero_stage2 = _model_from_state("stage2_result", Stage2Result)
completed_stage = _completed_stage()
progress_labels = [
    "거래문서 준비",
    "거래값 검토 중",
    "거래값 확정",
    "환율 가정 준비",
    "리스크 진단·상담 패킷 완료",
    "대응 시뮬레이션 준비",
    "공식 상담 정보 준비",
    "리포트 준비",
]
progress_label = progress_labels[min(completed_stage + 1, 7)]
if hero_stage2 is None:
    hero_tone = "safe"
    hero_signal_label = "START HERE"
    hero_signal_title = "문서 한 장으로 시작하세요"
    hero_signal_detail = (
        "왼쪽에서 수입기업 또는 수출기업 대표 데모를 바로 확인할 수 있습니다."
    )
else:
    (
        hero_tone,
        hero_signal_label,
        hero_signal_title,
        hero_signal_detail,
    ) = _risk_summary(hero_stage2)

st.markdown(
    "<section class='hero-shell'>"
    "<div class='hero-copy'>"
    "<div class='eyebrow'>TRADE FINANCE DECISION SUPPORT · 기업 재무 담당자용</div>"
    "<h1>수출입 거래<br>리스크 진단</h1>"
    "<p>거래정보와 기업 현금정보를 바탕으로 환율 변화가 실제 결제액과 "
    "운영자금에 미치는 영향을 분석하고, 필요한 KB 상담을 준비합니다.</p>"
    "<div class='hero-pills'>"
    "<span class='hero-pill'>{}</span>"
    "<span class='hero-pill'>스트레스 시나리오 · 예측 아님</span>"
    "<span class='hero-pill'>금융 숫자는 결정론 계산</span>"
    "<span class='hero-pill'>현재 · {}</span>"
    "</div></div>"
    "<aside class='hero-signal {}'>"
    "<small>{}</small><strong>{}</strong><p>{}</p>"
    "</aside></section>".format(
        "가상 데이터 데모" if run_mode == "DEMO" else "실제 문서 분석",
        escape(progress_label),
        hero_tone,
        escape(hero_signal_label),
        escape(hero_signal_title),
        escape(hero_signal_detail),
    ),
    unsafe_allow_html=True,
)
render_stepper(completed_stage)

stage0_tab, stage1_tab, stage2_tab, stage3_tab, stage4_tab, stage5_tab = (
    st.tabs(
        [
            "1  거래 확인",
            "2  환율 가정",
            "3  리스크 진단",
            "4  대응 시뮬레이션",
            "5  공식 상담 정보",
            "6  상담 리포트",
        ]
    )
)

with stage0_tab:
    _section_intro(
        "STEP 1 · 거래 확인",
        "문서에서 결제정보를 읽고, 사람이 마지막으로 확정합니다",
        "AI는 입력을 도울 뿐입니다. 통화·결제금액·결제일을 원문과 대조하기 전에는 "
        "어떤 금융 계산도 시작하지 않습니다.",
    )
    control_col, preview_col = st.columns([1, 1])
    with control_col:
        role_label = st.radio(
            "이 거래에서 우리 회사의 역할",
            ["구매자 · BUYER", "판매자 · SELLER"],
            horizontal=True,
            key="company_role_widget",
        )
        company_role = (
            "BUYER" if role_label.startswith("구매자") else "SELLER"
        )
        company_country = st.text_input(
            "우리 회사 국가 · 예: KR, Republic of Korea",
            key="company_country_widget",
        ).strip()
        uploaded = st.file_uploader(
            "거래문서 업로드",
            type=["pdf", "png", "jpg", "jpeg"],
            help="Commercial Invoice, Sales Contract, Purchase Order · 최대 15MB",
        )
        st.caption("PDF · PNG · JPG/JPEG 지원")

    if run_mode == "DEMO":
        demo_path, preview_mime, demo_extraction = _demo_fixture(
            company_role
        )
        preview_bytes = demo_path.read_bytes()
        preview_name = demo_path.name
        if uploaded is not None:
            st.info(
                "데모 모드에서는 업로드 파일을 전송·분석하지 않고 고정된 가상 "
                "역할별 fixture를 사용합니다. 실제 문서는 실제 API 모드를 "
                "선택하세요."
            )
    else:
        preview_bytes = uploaded.getvalue() if uploaded is not None else b""
        preview_name = (
            uploaded.name if uploaded is not None else "uploaded_document"
        )
        preview_mime = (
            uploaded.type if uploaded is not None else "application/octet-stream"
        )

    preview_error: Optional[str] = None
    if run_mode == "LIVE" and preview_bytes:
        try:
            validate_upload(
                file_bytes=preview_bytes,
                filename=preview_name,
                claimed_mime_type=preview_mime,
                settings=settings,
            )
        except ValueError as exc:
            preview_error = str(exc)

    with preview_col:
        st.markdown("**문서 미리보기**")
        if preview_error:
            st.error(preview_error)
        elif preview_bytes and preview_mime.startswith("image/"):
            st.image(preview_bytes, width="stretch")
        elif preview_bytes and preview_mime == "application/pdf":
            if hasattr(st, "pdf"):
                st.pdf(preview_bytes, height=420)
            else:
                st.info("PDF 업로드 완료 · 분석 시 magic bytes를 재검증합니다.")
        else:
            st.info("업로드 후 이 영역에서 문서를 확인할 수 있습니다.")

    signature = input_signature(
        mode=run_mode,
        company_role=company_role,
        company_country=company_country,
        file_bytes=preview_bytes,
        filename=preview_name,
    )
    if st.session_state.pop("skip_signature_sync_once", False):
        st.session_state["input_signature"] = signature
    elif sync_input_signature(st.session_state, signature):
        st.info("문서·역할·모드 변경을 감지해 이전 계산 결과를 비웠습니다.")

    if st.button(
        "문서 분석하고 거래정보 채우기",
        type="primary",
        width="stretch",
        key="analyze_document",
    ):
        try:
            _normalized_company_country(company_country)
            if run_mode == "LIVE":
                if uploaded is None:
                    raise ValueError("실제 API 모드에서는 문서를 업로드하세요.")
                if not settings.live_extraction_ready:
                    raise ValueError(
                        "OPENAI_API_KEY와 "
                        "ENABLE_LIVE_DOCUMENT_EXTRACTION=true가 필요합니다."
                    )
                with st.spinner("문서를 안전 검사하고 모델로 추출 중입니다..."):
                    extraction_run = extract_trade_document_with_metadata(
                        file_bytes=preview_bytes,
                        filename=preview_name,
                        mime_type=preview_mime,
                        company_role=company_role,
                        company_country=company_country,
                        settings=settings,
                    )
                extraction = extraction_run.extraction
                validation = extraction_run.validation
                original_extraction = extraction_run.raw_extraction
                metadata_dict = {
                    "filename": extraction_run.upload.filename,
                    "mime_type": extraction_run.upload.mime_type,
                    "size_bytes": extraction_run.upload.size_bytes,
                    "sha256": extraction_run.upload.sha256,
                    "page_count": extraction_run.upload.page_count,
                    "latency_seconds": extraction_run.usage.latency_seconds,
                    "input_tokens": extraction_run.usage.input_tokens,
                    "output_tokens": extraction_run.usage.output_tokens,
                    "provider": "openai:{}".format(
                        extraction_run.usage.model
                    ),
                    "attempts": extraction_run.usage.attempts,
                }
            else:
                metadata = validate_upload(
                    file_bytes=preview_bytes,
                    filename=preview_name,
                    claimed_mime_type=preview_mime,
                    settings=settings,
                )
                extraction, validation = apply_deterministic_review_state(
                    demo_extraction,
                    company_role=company_role,
                    company_country=company_country,
                )
                original_extraction = demo_extraction
                metadata_dict = {
                    "filename": metadata.filename,
                    "mime_type": metadata.mime_type,
                    "size_bytes": metadata.size_bytes,
                    "sha256": metadata.sha256,
                    "page_count": metadata.page_count,
                    "latency_seconds": 0.0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "provider": "offline_fixture",
                    "attempts": 1,
                }
            _save_model("extraction", extraction)
            _save_model("extraction_original", original_extraction)
            _save_model("extraction_validation", validation)
            st.session_state["upload_metadata"] = metadata_dict
            clear_review_widgets(st.session_state)
            clear_confirmation_and_later(st.session_state)
            _store_intake_workflow(
                mode=run_mode,
                extraction=extraction,
                validation=validation,
                provider=str(metadata_dict["provider"]),
                duration_ms=int(
                    float(metadata_dict["latency_seconds"]) * 1000
                ),
                retry_count=max(
                    0,
                    int(metadata_dict["attempts"]) - 1,
                ),
            )
            st.success("추출이 완료되었습니다. 아래 값과 원문 근거를 확인하세요.")
            st.rerun()
        except (ExtractionError, ValueError) as exc:
            st.error(str(exc))

    extraction = _model_from_state(
        "extraction",
        TradeDocumentExtraction,
    )
    if extraction is not None:
        st.divider()
        _section_intro(
            "STEP 1.2 · 값 검토",
            "AI가 읽은 거래정보가 원문과 같은지 확인하세요",
            "값을 수정한 뒤 다시 검증하고, 회사 역할과 핵심 거래값을 직접 "
            "대조하면 거래가 확정됩니다.",
        )
        document_types = [
            "COMMERCIAL_INVOICE",
            "SALES_CONTRACT",
            "PURCHASE_ORDER",
            "UNKNOWN",
        ]
        with st.form("review_extraction"):
            context_row = st.columns(3)
            reviewed_company_role = context_row[0].selectbox(
                "우리 회사 역할",
                ["BUYER", "SELLER"],
                index=_safe_index(
                    ["BUYER", "SELLER"],
                    extraction.company_role,
                ),
                key="review_company_role_widget",
            )
            reviewed_company_country = context_row[1].text_input(
                "우리 회사 국가",
                value=company_country,
                help="자연어 국가명은 검증 전에 ISO alpha-2로 정규화합니다.",
                key="review_company_country_widget",
            )
            selected_trade_type = context_row[2].selectbox(
                "수입/수출 판정",
                ["AUTO", "IMPORT", "EXPORT"],
                index=0,
                format_func=lambda value: {
                    "AUTO": "자동 판정",
                    "IMPORT": "수입 · 사용자 지정",
                    "EXPORT": "수출 · 사용자 지정",
                }[value],
                key="review_trade_type_choice_widget",
                help=(
                    "자동 판정은 역할과 정규화된 당사자 국가를 사용합니다. "
                    "사용자 지정값이 자동판정과 다르면 경고를 남깁니다."
                ),
            )
            row1 = st.columns(4)
            document_type = row1[0].selectbox(
                "문서 유형",
                document_types,
                index=_safe_index(document_types, extraction.document_type),
                format_func=lambda value: {
                    "COMMERCIAL_INVOICE": "상업송장",
                    "SALES_CONTRACT": "매매계약서",
                    "PURCHASE_ORDER": "구매주문서",
                    "UNKNOWN": "기타/확인 필요",
                }.get(value, value),
                key="review_document_type_widget",
            )
            document_number = row1[1].text_input(
                "문서 번호",
                value=extraction.document_number or "",
                key="review_document_number_widget",
            )
            currency = row1[2].text_input(
                "통화",
                value=extraction.currency or "",
                key="review_currency_widget",
            ).strip().upper()
            amount_due = row1[3].text_input(
                "실제 결제금액",
                value=extraction.amount_due or "",
                key="review_amount_due_widget",
            )
            row2 = st.columns(4)
            grand_total = row2[0].text_input(
                "문서 총액",
                value=extraction.grand_total or "",
                key="review_grand_total_widget",
            )
            issue_date = row2[1].text_input(
                "발행일",
                value=extraction.issue_date or "",
                placeholder="YYYY-MM-DD",
                key="review_issue_date_widget",
            )
            contract_date = row2[2].text_input(
                "계약일",
                value=extraction.contract_date or "",
                placeholder="YYYY-MM-DD",
                key="review_contract_date_widget",
            )
            shipment_date = row2[3].text_input(
                "선적일",
                value=extraction.shipment_date or "",
                placeholder="YYYY-MM-DD",
                key="review_shipment_date_widget",
            )
            row3 = st.columns(4)
            explicit_due_date = row3[0].text_input(
                "명시 결제일",
                value=extraction.explicit_due_date or "",
                placeholder="YYYY-MM-DD",
                key="review_explicit_due_date_widget",
            )
            payment_terms = row3[1].text_input(
                "결제조건 · 예: Net 90 Days",
                value=extraction.payment_terms or "",
                key="review_payment_terms_widget",
            )
            incoterm = row3[2].text_input(
                "Incoterm",
                value=extraction.incoterm or "",
                key="review_incoterm_widget",
            )
            row3[3].text_input(
                "현재 적용된 수입/수출",
                value=extraction.trade_type,
                disabled=True,
                help=(
                    "위 자동/사용자 지정 선택을 저장하면 최신 입력으로 "
                    "다시 판정합니다."
                ),
            )
            row4 = st.columns(4)
            seller_name = row4[0].text_input(
                "판매자",
                value=extraction.seller_name or "",
                key="review_seller_name_widget",
            )
            seller_country = row4[1].text_input(
                "판매자 국가",
                value=extraction.seller_country or "",
                key="review_seller_country_widget",
            ).strip()
            buyer_name = row4[2].text_input(
                "구매자",
                value=extraction.buyer_name or "",
                key="review_buyer_name_widget",
            )
            buyer_country = row4[3].text_input(
                "구매자 국가",
                value=extraction.buyer_country or "",
                key="review_buyer_country_widget",
            ).strip()

            installment_rows = [
                item.model_dump() for item in extraction.installments
            ]
            edited_installments = st.data_editor(
                pd.DataFrame(
                    installment_rows,
                    columns=[
                        "sequence",
                        "amount",
                        "currency",
                        "due_date",
                        "condition",
                    ],
                ),
                num_rows="dynamic",
                width="stretch",
                hide_index=True,
                column_config={
                    "sequence": "회차",
                    "amount": "금액",
                    "currency": "통화",
                    "due_date": "결제일",
                    "condition": "조건",
                },
                key="installment_editor",
            )
            reviewed = st.form_submit_button(
                "수정 내용 저장 및 다시 검증",
                type="primary",
            )

        if reviewed:
            try:
                installment_models = []
                for row in edited_installments.to_dict("records"):
                    if not any(
                        optional_text(value) for value in row.values()
                    ):
                        continue
                    sequence_value = row.get("sequence")
                    installment_models.append(
                        PaymentInstallment(
                            sequence=optional_positive_integer(
                                sequence_value,
                                "분할결제 sequence",
                            ),
                            amount=_blank_to_none(row.get("amount")),
                            currency=(
                                optional_text(row.get("currency")).upper()
                                if optional_text(row.get("currency"))
                                else None
                            ),
                            due_date=_date_or_none(row.get("due_date")),
                            condition=_blank_to_none(row.get("condition")),
                        )
                    )
                edited = TradeDocumentExtraction.model_validate(
                    extraction.model_dump()
                ).model_copy(
                    update={
                        "document_type": document_type,
                        "document_number": _blank_to_none(document_number),
                        "seller_name": _blank_to_none(seller_name),
                        "seller_country": _blank_to_none(seller_country),
                        "buyer_name": _blank_to_none(buyer_name),
                        "buyer_country": _blank_to_none(buyer_country),
                        "currency": _blank_to_none(currency),
                        "grand_total": _blank_to_none(grand_total),
                        "amount_due": _blank_to_none(amount_due),
                        "issue_date": _date_or_none(issue_date),
                        "contract_date": _date_or_none(contract_date),
                        "shipment_date": _date_or_none(shipment_date),
                        "explicit_due_date": _date_or_none(
                            explicit_due_date
                        ),
                        "payment_terms": _blank_to_none(payment_terms),
                        "incoterm": _blank_to_none(incoterm),
                        "installments": installment_models,
                    }
                )
                edited = TradeDocumentExtraction.model_validate(
                    edited.model_dump()
                )
                review_context_updates = {
                    "company_role": reviewed_company_role,
                }
                if selected_trade_type in {"IMPORT", "EXPORT"}:
                    review_context_updates["trade_type"] = (
                        selected_trade_type
                    )
                edited = edited.model_copy(update=review_context_updates)
                edited = discard_stale_evidence_after_review(
                    extraction,
                    edited,
                )
                edited, validation = apply_deterministic_review_state(
                    edited,
                    company_role=reviewed_company_role,
                    company_country=reviewed_company_country,
                    user_trade_type=(
                        selected_trade_type
                        if selected_trade_type in {"IMPORT", "EXPORT"}
                        else None
                    ),
                    source_page_texts=_live_source_page_texts(
                        run_mode=run_mode,
                        file_bytes=preview_bytes,
                        mime_type=preview_mime,
                    ),
                )
                normalized_review_country = _normalized_company_country(
                    reviewed_company_country
                )
                audit_trail = list(
                    st.session_state.get("review_audit_trail", [])
                )
                audit_trail.append(
                    {
                        "changed_at": datetime.now(timezone.utc).isoformat(),
                        "before": _review_audit_values(
                            extraction,
                            company_country,
                        ),
                        "after": _review_audit_values(
                            edited,
                            normalized_review_country,
                        ),
                    }
                )
                st.session_state["review_audit_trail"] = audit_trail
                _save_model("extraction", edited)
                _save_model("extraction_validation", validation)
                clear_confirmation_and_later(st.session_state)
                st.session_state["pending_company_role_widget"] = (
                    "구매자 · BUYER"
                    if reviewed_company_role == "BUYER"
                    else "판매자 · SELLER"
                )
                st.session_state[
                    "pending_company_country_widget"
                ] = normalized_review_country
                st.session_state["skip_signature_sync_once"] = True
                _store_intake_workflow(
                    mode=run_mode,
                    extraction=edited,
                    validation=validation,
                    provider="deterministic_review",
                )
                st.success("수정 내용을 저장하고 규칙 검증을 완료했습니다.")
                st.rerun()
            except (ValueError, TypeError) as exc:
                st.error("수정값을 확인하세요: {}".format(exc))

        validation = _model_from_state(
            "extraction_validation",
            ValidationResult,
        )
        if validation is None:
            extraction, validation = apply_deterministic_review_state(
                extraction,
                company_role=company_role,
                company_country=company_country,
                source_page_texts=_live_source_page_texts(
                    run_mode=run_mode,
                    file_bytes=preview_bytes,
                    mime_type=preview_mime,
                ),
            )
        confirmation = _model_from_state(
            "confirmation",
            ConfirmationRecord,
        )
        confirmed_validation = _model_from_state(
            "confirmation_validation",
            ValidationResult,
        )
        is_confirmed = bool(
            confirmation is not None
            and confirmed_validation is not None
            and confirmed_validation.stage2_allowed
        )
        if is_confirmed:
            banner_class = ""
            banner_icon = "✓"
            banner_title = "거래값 확정 완료"
            banner_copy = (
                "회사 역할·거래 방향·통화·결제금액·결제일을 사용자가 "
                "확인했습니다. "
                "이제 환율 가정 단계로 이동할 수 있습니다."
            )
        elif validation.validation_pass:
            banner_class = "warning"
            banner_icon = "3"
            banner_title = "자동 검증 완료 · 핵심값 확인이 남았습니다"
            banner_copy = (
                "아래 원문 근거와 회사 역할·거래 방향·통화·결제금액·결제일을 "
                "대조한 뒤 거래를 확정하세요."
            )
        else:
            banner_class = "danger"
            banner_icon = "!"
            banner_title = "수정이 필요한 값이 있습니다"
            banner_copy = (
                "검증 결과에서 충돌한 날짜·금액·근거를 확인하고 "
                "수정 내용을 다시 저장하세요."
            )
        st.markdown(
            "<div class='state-banner {}'><span class='state-icon'>{}</span>"
            "<div><strong>{}</strong><p>{}</p></div></div>".format(
                banner_class,
                banner_icon,
                banner_title,
                banner_copy,
            ),
            unsafe_allow_html=True,
        )

        rows = evidence_rows(extraction)
        with st.expander(
            "원문 근거와 대조하기",
            expanded=validation.validation_pass and not is_confirmed,
        ):
            if rows:
                st.dataframe(rows, width="stretch", hide_index=True)
                badges = sorted({row["상태"] for row in rows})
                st.caption(" · ".join(status_badge(item) for item in badges))
            else:
                st.error("원문 근거가 없어 거래를 확정할 수 없습니다.")

        with st.expander(
            "고급 · 규칙 검증 상세",
            expanded=not validation.validation_pass,
        ):
            render_validation(validation)

        resolved_due = validation.resolved_due_date or ""
        confirmation_submit = False
        confirmed_due = resolved_due
        trade_type_ok = False
        company_role_ok = False
        currency_ok = False
        amount_ok = False
        due_ok = False
        evidence_override_fields: List[str] = []
        if not is_confirmed:
            st.markdown("#### 핵심 거래값 최종 확인")
            st.caption(
                "체크는 단순 동의가 아니라 문서 원문과 직접 대조했다는 기록입니다."
            )
            with st.form("critical_confirmation"):
                confirmed_due = st.text_input(
                    "최종 결제일",
                    value=resolved_due,
                    placeholder="YYYY-MM-DD",
                    help=(
                        "Net N 조건은 일반 코드가 계산하며, "
                        "여기서는 사용자가 최종 결제일을 확인합니다."
                    ),
                    key="confirmed_due_widget",
                )
                check_cols = st.columns(5)
                company_role_ok = check_cols[0].checkbox(
                    "{} 역할을 확인했습니다".format(extraction.company_role),
                    key="confirm_company_role_widget",
                )
                trade_type_ok = check_cols[1].checkbox(
                    "{} 거래 방향을 확인했습니다".format(
                        validation.derived_trade_type
                    ),
                    key="confirm_trade_type_widget",
                )
                currency_ok = check_cols[2].checkbox(
                    "통화를 원문과 대조했습니다",
                    key="confirm_currency_widget",
                )
                amount_ok = check_cols[3].checkbox(
                    "결제금액을 원문과 대조했습니다",
                    key="confirm_amount_widget",
                )
                due_ok = check_cols[4].checkbox(
                    "결제일과 조건을 대조했습니다",
                    key="confirm_due_widget",
                )
                missing_evidence_fields = sorted(
                    {
                        item.field
                        for item in validation.issues
                        if (
                            item.code
                            in {
                                "MISSING_CORE_EVIDENCE",
                                "INFERRED_CRITICAL_FIELD",
                            }
                            and item.field is not None
                        )
                    }
                )
                if missing_evidence_fields:
                    st.warning(
                        "아래 필드는 원문 evidence가 없거나, 원문에 인용문이 "
                        "없거나, 현재 값과 일치하지 않거나, 독립 텍스트 원문으로 "
                        "대조할 수 없습니다. 문서 미리보기와 직접 대조한 필드만 "
                        "선택해야 다음 단계로 전달됩니다."
                    )
                    evidence_override_fields = st.multiselect(
                        "원문에서 직접 확인한 evidence 예외 필드",
                        options=missing_evidence_fields,
                        key="confirm_evidence_override_widget",
                    )
                confirmation_submit = st.form_submit_button(
                    "이 거래를 확정하고 다음 단계 준비",
                    type="primary",
                )
        if confirmation_submit:
            metadata = st.session_state["upload_metadata"]
            original = _model_from_state(
                "extraction_original",
                TradeDocumentExtraction,
            ) or extraction
            try:
                record = create_confirmation_record(
                    original=original,
                    confirmed=extraction,
                    confirmed_due_date=_date_or_none(confirmed_due),
                    currency_confirmed=currency_ok,
                    amount_due_confirmed=amount_ok,
                    due_date_confirmed=due_ok,
                    source_filename=metadata["filename"],
                    source_sha256=metadata["sha256"],
                    company_country=company_country,
                    company_role_confirmed=company_role_ok,
                    trade_type_confirmed=trade_type_ok,
                    trade_type_source=validation.trade_type_source,
                    evidence_override_fields=evidence_override_fields,
                    review_audit_trail=list(
                        st.session_state.get("review_audit_trail", [])
                    ),
                    confirmed_by="streamlit-user",
                )
                confirmed_validation = validate_confirmation(
                    extraction=extraction,
                    record=record,
                    company_country=company_country,
                    source_page_texts=_live_source_page_texts(
                        run_mode=run_mode,
                        file_bytes=preview_bytes,
                        mime_type=preview_mime,
                    ),
                )
                _save_model("confirmation", record)
                _save_model(
                    "confirmation_validation",
                    confirmed_validation,
                )
                stage0_output = build_stage0_output(
                    extraction=extraction,
                    validation=confirmed_validation,
                    confirmations=record.checks,
                    source_filename=metadata["filename"],
                    prompt_version=get_prompt_version(),
                    confirmation_record=record,
                )
                st.session_state["stage0_output"] = stage0_output
                st.session_state.pop("stage2_document_input", None)
                clear_downstream(st.session_state, 1)
                _store_intake_workflow(
                    mode=run_mode,
                    extraction=extraction,
                    validation=confirmed_validation,
                    confirmation=record,
                    provider="human_confirmation_gate",
                )
                if not confirmed_validation.stage2_allowed:
                    st.error(
                        "거래를 확정하지 못했습니다. 다섯 항목을 모두 대조하고 "
                        "중요 검증 문제를 해결하세요."
                    )
                else:
                    document_input = build_stage2_input(
                        extraction=extraction,
                        validation=confirmed_validation,
                        confirmations=record.checks,
                        source_filename=metadata["filename"],
                        source_sha256=record.source_sha256,
                        confirmed_at=record.confirmed_at,
                    )
                    st.session_state[
                        "stage2_document_input"
                    ] = document_input
                    st.success("거래가 확정되었습니다. 환율 가정을 선택하세요.")
                    st.rerun()
            except ValueError as exc:
                st.error(str(exc))

        confirmation = _model_from_state(
            "confirmation",
            ConfirmationRecord,
        )
        confirmed_validation = _model_from_state(
            "confirmation_validation",
            ValidationResult,
        )
        if confirmation is not None and confirmed_validation is not None:
            if confirmed_validation.stage2_allowed:
                confirmed_cols = st.columns(4)
                confirmed_cols[0].metric(
                    "확정 거래 방향",
                    confirmed_validation.derived_trade_type,
                )
                confirmed_cols[1].metric(
                    "확정 통화",
                    extraction.currency or "-",
                )
                confirmed_cols[2].metric(
                    "확정 결제금액",
                    format_foreign(
                        extraction.amount_due or "0",
                        extraction.currency or "",
                    ),
                )
                confirmed_cols[3].metric(
                    "확정 결제일",
                    confirmation.checks.confirmed_due_date or "-",
                )
            else:
                st.error("핵심값 확인 또는 검증 문제를 해결하세요.")
            with st.expander("고급 · 확정 거래 데이터", expanded=False):
                _advanced_downloads_title()
                download_cols = st.columns(2)
                with download_cols[0]:
                    json_download(
                        label="확정 거래 전체 JSON",
                        value=st.session_state.get(
                            "stage0_output",
                            extraction.model_dump(),
                        ),
                        filename="stage0_confirmed.json",
                        key="download_stage0",
                    )
                if "stage2_document_input" in st.session_state:
                    with download_cols[1]:
                        json_download(
                            label="현금 계산용 거래 JSON",
                            value=st.session_state["stage2_document_input"],
                            filename="stage2_document_input.json",
                            key="download_document_input",
                        )

with stage1_tab:
    _section_intro(
        "STEP 2 · 환율 가정",
        "환율이 유리하거나 불리하게 움직이는 구간을 준비합니다",
        "직접 만드는 스트레스 테스트는 미래 예측이 아닙니다. "
        "우리 회사 현금이 어느 수준까지 버티는지 확인하는 민감도 가정입니다.",
    )
    document_input = st.session_state.get("stage2_document_input")
    if document_input is None:
        st.markdown(
            "<div class='state-banner warning'><span class='state-icon'>1</span>"
            "<div><strong>먼저 거래값을 확정하세요</strong>"
            "<p>첫 번째 탭에서 통화·결제금액·결제일을 확인하면 "
            "환율 가정을 만들 수 있습니다.</p></div></div>",
            unsafe_allow_html=True,
        )
    else:
        trade = document_input["trade"]
        target_date = (
            trade["settlement_date"]
            or trade["cashflow_events"][0]["settlement_date"]
        )
        st.session_state.setdefault(
            "stage1_mode_widget",
            (
                "WEB_FORECAST"
                if settings.stage1_mode
                in {"web", "web_forecast", "stage1_web"}
                else
                "EXTERNAL_STAGE1"
                if settings.stage1_mode in {"external", "external_stage1"}
                else "MANUAL_STRESS"
            ),
        )
        scenario_mode = st.radio(
            "환율 가정을 만드는 방법",
            ["WEB_FORECAST", "MANUAL_STRESS", "EXTERNAL_STAGE1"],
            horizontal=True,
            format_func=lambda value: {
                "WEB_FORECAST": "Stage 1 AI + 고정 스트레스",
                "MANUAL_STRESS": "직접 스트레스 테스트",
                "EXTERNAL_STAGE1": "기존 시나리오 JSON",
            }[value],
            key="stage1_mode_widget",
        )
        stage1_provider: Optional[str] = None
        spot_provider: Optional[str] = None
        manual_spot_confirmed = False
        if scenario_mode == "WEB_FORECAST":
            st.markdown("#### Stage 1 시장 분석 연결")
            provider_options = ["http", "file", "mock"]
            default_provider = (
                "mock"
                if run_mode == "DEMO"
                else settings.stage1_provider
            )
            stage1_provider = st.radio(
                "Stage 1 공급자",
                provider_options,
                index=_safe_index(provider_options, default_provider),
                horizontal=True,
                format_func=lambda value: {
                    "http": "로컬 HTTP",
                    "file": "latest_forecast.json",
                    "mock": "제공 fixture",
                }[value],
                key="stage1_provider_widget",
            )
            st.caption(
                "HTTP 실패 시 file/mock 사용 여부와 `FALLBACK_USED`를 "
                "결과에 표시합니다. 방향 score는 실제 발생확률로 쓰지 않습니다."
            )
            spot_options = ["fixture", "manual"]
            if settings.koreaexim_key:
                spot_options.insert(0, "koreaexim")
            default_spot = (
                "fixture"
                if run_mode == "DEMO"
                else settings.spot_rate_provider
            )
            if default_spot not in spot_options:
                default_spot = "manual"
            spot_provider = st.radio(
                "절대 기준환율 출처",
                spot_options,
                index=_safe_index(spot_options, default_spot),
                horizontal=True,
                format_func=lambda value: {
                    "koreaexim": "한국수출입은행 API",
                    "manual": "사용자 확인 수동 입력",
                    "fixture": "데모 1,400원",
                }[value],
                key="spot_provider_widget",
            )
        base_rate = st.text_input(
            "검토 기준 환율 · 1 {}당 원화".format(trade["currency"]),
            value=(
                settings.manual_usdkrw_rate or "1400"
            ),
            disabled=(
                scenario_mode == "WEB_FORECAST"
                and spot_provider in {"fixture", "koreaexim"}
            ),
            key="stage1_base_rate_widget",
        )
        if scenario_mode == "WEB_FORECAST" and spot_provider == "manual":
            manual_spot_confirmed = st.checkbox(
                "위 기준환율의 값과 기준시점을 확인했습니다",
                value=False,
                key="spot_confirmed_widget",
                help=(
                    "Stage 1 JSON에는 절대환율이 없으므로 사용자가 확인한 "
                    "환율만 계산에 사용할 수 있습니다."
                ),
            )
        elif scenario_mode == "WEB_FORECAST" and spot_provider == "fixture":
            st.warning(
                "1,400원은 가상 데모 fixture이며 현재 시장환율이 아닙니다."
            )
        payload: Optional[bytes] = None
        endpoint: Optional[str] = None
        if scenario_mode == "EXTERNAL_STAGE1":
            source_type = st.radio(
                "연결 방법",
                ["JSON 업로드", "REST endpoint"],
                horizontal=True,
                key="stage1_source_type_widget",
            )
            if source_type == "JSON 업로드":
                stage1_file = st.file_uploader(
                    "외부 환율 전망 JSON",
                    type=["json"],
                    key="stage1_json_upload",
                )
                if stage1_file is not None:
                    payload = stage1_file.getvalue()
            else:
                endpoint = st.text_input(
                    "외부 전망 API 주소",
                    value=settings.stage1_base_url,
                    key="stage1_endpoint_widget",
                )
                if settings.stage1_allow_private_endpoints:
                    st.warning(
                        "로컬 개발용 사설 endpoint 허용이 켜져 있습니다. "
                        "공개 배포에서는 false로 유지하세요."
                    )
                else:
                    st.caption(
                        "HTTPS와 public IP만 허용합니다. "
                        "STAGE1_ALLOWED_HOSTS를 설정하면 exact host도 검사합니다."
                    )
        if st.button(
            "환율별 영향 구간 만들기",
            type="primary",
            key="load_stage1",
        ):
            try:
                workflow = _workflow_from_state()
                if workflow is None:
                    raise ValueError(
                        "분석 세션을 찾을 수 없습니다. 거래 확인부터 다시 시작하세요."
                    )
                workflow = orchestrator.run_market_risk(
                    workflow,
                    expected_currency=trade["currency"],
                    expected_target_date=target_date,
                    manual_base_rate=decimal_text(
                        base_rate,
                        "기준 환율",
                        allow_zero=False,
                    ),
                    mode=scenario_mode,
                    payload=payload,
                    endpoint=endpoint,
                    stage1_provider=stage1_provider,
                    spot_provider=spot_provider,
                    manual_spot_confirmed=manual_spot_confirmed,
                )
                if (
                    workflow.market_risk is None
                    or workflow.market_risk.data is None
                ):
                    raise ValueError(
                        "환율 시나리오 실행에 실패했습니다: {}".format(
                            ", ".join(
                                workflow.market_risk.errors
                                if workflow.market_risk is not None
                                else []
                            )
                        )
                    )
                loaded = workflow.market_risk.data
                _save_model("stage1_load", loaded)
                if workflow.market_integration is not None:
                    _save_model(
                        "market_integration",
                        workflow.market_integration,
                    )
                _save_workflow(workflow)
                clear_downstream(st.session_state, 2)
                st.success("환율 가정이 준비되었습니다. 현금 영향을 계산하세요.")
                st.rerun()
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                st.error(str(exc))

        stage1_load = _model_from_state(
            "stage1_load",
            Stage1LoadResult,
        )
        market_integration = _model_from_state(
            "market_integration",
            MarketIntegrationResult,
        )
        if stage1_load is not None:
            scenarios = stage1_load.scenario_set
            source_copy = (
                "Stage 1 AI 경로위험 + 고정 스트레스"
                if market_integration is not None
                else "외부 전망"
                if scenarios.kind == "FORECAST"
                else "스트레스 테스트 · 예측 아님"
            )
            st.markdown(
                "<div class='state-banner'><span class='state-icon'>✓</span>"
                "<div><strong>환율 가정 준비 완료</strong>"
                "<p>{} · 결제 예정일 {} 기준</p></div></div>".format(
                    source_copy,
                    escape(scenarios.target_date),
                ),
                unsafe_allow_html=True,
            )
            if market_integration is not None:
                quote = market_integration.spot_quote
                integration_cols = st.columns(4)
                integration_cols[0].metric(
                    "Stage 1 연결",
                    (
                        market_integration.forecast_load.source
                        if market_integration.forecast_load is not None
                        else "고정 스트레스만"
                    ),
                )
                integration_cols[1].metric(
                    "확인된 기준환율",
                    "{}원".format(
                        format_decimal_display(quote.rate, 2)
                    ),
                )
                integration_cols[2].metric(
                    "환율 출처",
                    quote.rate_type,
                )
                integration_cols[3].metric(
                    "모델 적용 범위",
                    (
                        "초기 21일 문맥만"
                        if market_integration.scenario_build.horizon_mismatch
                        else "결제기간 내 21일"
                    ),
                )
                forecast_load = market_integration.forecast_load
                if forecast_load is not None:
                    forecast = forecast_load.forecast
                    st.markdown("#### 모델 기반 21일 경로위험")
                    direction_cols = st.columns(4)
                    direction_cols[0].metric(
                        "방향 문맥",
                        (
                            "USD/KRW 하락 우세"
                            if forecast.direction.label == "USD_KRW_DOWN"
                            else "USD/KRW 상승 우세"
                        ),
                    )
                    direction_cols[1].metric(
                        "상승 score",
                        format_ratio(forecast.direction.up_score),
                    )
                    direction_cols[2].metric(
                        "하락 score",
                        format_ratio(forecast.direction.down_score),
                    )
                    direction_cols[3].metric(
                        "확률 보정",
                        (
                            "보정됨"
                            if forecast.direction.calibrated_probability
                            else "보정되지 않음"
                        ),
                    )
                    st.caption(
                        "상승·하락 값은 v25 모델 score이며 보정된 실제 "
                        "발생확률이 아닙니다. 기대손실 가중치에 사용하지 않습니다."
                    )
                    adverse_direction = (
                        "UP"
                        if trade["trade_type"] == "IMPORT"
                        else "DOWN"
                    )
                    model_rows = []
                    for item in (
                        market_integration.scenario_build.model_path_scenarios
                    ):
                        model_rows.append(
                            {
                                "기업 위험 방향": (
                                    "불리한 방향"
                                    if item.direction == adverse_direction
                                    else "반대 방향 참고"
                                ),
                                "경로위험 분위수": item.id,
                                "상대 변동": format_ratio(
                                    str(abs(Decimal(item.move)))
                                ),
                                "절대 환율": "{}원".format(
                                    format_decimal_display(item.rate, 2)
                                ),
                                "결제 계산": (
                                    "포함"
                                    if item.included_in_calculation
                                    else "제외 · 초기 21일 문맥만"
                                ),
                            }
                        )
                    st.dataframe(
                        model_rows,
                        width="stretch",
                        hide_index=True,
                    )
                    st.info(
                        "q90은 ‘90% 확률로 발생’이 아니라 모델 "
                        "예측분포의 상위 경로위험 분위수입니다."
                    )

                    st.markdown("#### 뉴스 기반 시장 문맥")
                    st.write(forecast.market_context.summary)
                    st.caption(
                        "뉴스는 환율 숫자를 변경하지 않았습니다 · 중복 기사 "
                        "{}건 제거 · 검색 오류 지역 {}".format(
                            forecast.market_context.duplicate_news_removed,
                            ", ".join(
                                forecast.market_context.query_errors
                            )
                            or "없음",
                        )
                    )
                    if forecast.market_context.news:
                        news_rows = [
                            {
                                "지역": item.region,
                                "범주": item.category,
                                "요약": item.summary,
                                "분석 신뢰": format_ratio(
                                    item.analysis_confidence
                                ),
                            }
                            for item in forecast.market_context.news
                        ]
                        st.dataframe(
                            news_rows,
                            width="stretch",
                            hide_index=True,
                        )
                if market_integration.scenario_build.horizon_mismatch:
                    st.warning(
                        "HORIZON_MISMATCH · 결제일이 Stage 1의 21거래일 "
                        "검증범위 밖입니다. 모델 환율은 계산에서 제외하고 "
                        "±3/5/10% 고정 스트레스만 적용했습니다."
                    )
                st.markdown("#### 고정 스트레스 테스트")
                st.caption(
                    "아래 구간은 미래 예측이 아니라 전체 결제기간의 "
                    "지급·수취 능력을 확인하는 결정론적 가정입니다."
                )
            base_point = next(
                (
                    item
                    for item in scenarios.scenarios
                    if item.is_base
                ),
                scenarios.scenarios[0],
            )
            base_value = _decimal_or_zero(base_point.rate)
            scenario_rows = []
            for item in scenarios.scenarios:
                item_rate = _decimal_or_zero(item.rate)
                movement = Decimal("0")
                if base_value != 0:
                    movement = (
                        (item_rate / base_value) - Decimal("1")
                    ) * Decimal("100")
                scenario_rows.append(
                    {
                        "구간": _scenario_label(item.name),
                        "적용 환율": "{}원".format(
                            format_decimal_display(item.rate, 2)
                        ),
                        "기준 대비": "{:+.1f}%".format(movement),
                        "성격": (
                            "기준"
                            if item.is_base
                            else "모델 경로위험 분위수"
                            if item.source_kind
                            == "STAGE1_MODEL_QUANTILE"
                            else "외부 전망"
                            if scenarios.kind == "FORECAST"
                            else "고정 스트레스 가정"
                        ),
                    }
                )
            st.dataframe(
                scenario_rows,
                width="stretch",
                hide_index=True,
            )
            if stage1_load.warnings:
                with st.expander(
                    "Stage 1 품질·적용 경고",
                    expanded=bool(
                        market_integration is not None
                        and (
                            market_integration.scenario_build.horizon_mismatch
                            or (
                                market_integration.forecast_load is not None
                                and market_integration.forecast_load.fallback_used
                            )
                        )
                    ),
                ):
                    for warning in stage1_load.warnings:
                        st.warning(warning)
            with st.expander("고급 · 환율 데이터 및 적용 규칙", expanded=False):
                st.caption(
                    "{} · 적용 규칙: {} · 확률값 유효={}".format(
                        stage1_load.source,
                        scenarios.application_rule,
                        (
                            "예"
                            if scenarios.probability_valid
                            else "아니오"
                        ),
                    )
                )
                _advanced_downloads_title()
                json_download(
                    label="정규화 환율 시나리오 JSON",
                    value=scenarios,
                    filename="stage1_normalized.json",
                    key="download_stage1",
                )

with stage2_tab:
    _section_intro(
        "STEP 3 · 리스크 진단",
        "환율 변화가 실제 결제액과 운영자금에 미치는 영향을 계산합니다",
        "현재 현금, 반드시 지켜야 할 운영자금, 예정 입출금을 입력하면 "
        "결제일까지의 잔고, 위험 원인과 KB 상담 준비사항을 함께 생성합니다.",
    )
    stage1_load = _model_from_state("stage1_load", Stage1LoadResult)
    document_input = st.session_state.get("stage2_document_input")
    if stage1_load is None or document_input is None:
        st.markdown(
            "<div class='state-banner warning'><span class='state-icon'>2</span>"
            "<div><strong>거래 확정과 환율 가정이 먼저 필요합니다</strong>"
            "<p>앞 단계가 준비되면 회사 자금정보를 입력해 현금 영향을 "
            "계산할 수 있습니다.</p></div></div>",
            unsafe_allow_html=True,
        )
    else:
        trade = document_input["trade"]
        stored_stage2_input = _model_from_state(
            "stage2_input",
            Stage2Input,
        )
        form_defaults = _stage2_form_defaults(stored_stage2_input)
        st.caption(
            "확정 거래 · {} · {} · 결제일 {}".format(
                format_foreign(
                    trade["foreign_amount"],
                    trade["currency"],
                ),
                "수입 결제" if trade["trade_type"] == "IMPORT" else "수출 수취",
                trade["settlement_date"]
                or trade["cashflow_events"][0]["settlement_date"],
            )
        )
        with st.form("stage2_company_input"):
            st.markdown("#### ① 현금 방어선")
            st.caption(
                "현재 쓸 수 있는 원화와 어떤 상황에서도 남겨야 하는 운영자금을 입력하세요."
            )
            cash_cols = st.columns(4)
            current_cash = cash_cols[0].text_input(
                "현재 원화 현금",
                value=form_defaults["current_cash"],
                help="오늘 기준으로 실제 사용할 수 있는 원화 현금",
                key="stage2_current_cash_widget",
            )
            minimum_buffer = cash_cols[1].text_input(
                "반드시 남길 운영자금",
                value=form_defaults["minimum_buffer"],
                help="급여·임차료 등 운영을 위해 지켜야 하는 최소 현금",
                key="stage2_minimum_buffer_widget",
            )
            credit_limit = cash_cols[2].text_input(
                "사용 가능한 대출한도",
                value=form_defaults["credit_limit"],
                key="stage2_credit_limit_widget",
            )
            acceptable_loss = cash_cols[3].text_input(
                "허용 가능한 환율 추가부담",
                value=form_defaults["acceptable_loss"],
                key="stage2_acceptable_loss_widget",
            )
            timing_cols = st.columns(2)
            as_of = timing_cols[0].date_input(
                "현금 계산 기준일",
                value=form_defaults["as_of"],
                key="stage2_as_of_widget",
            )
            usable_fx = timing_cols[1].text_input(
                "결제에 사용할 수 있는 보유외화 · {}".format(
                    trade["currency"]
                ),
                value=form_defaults["usable_fx"],
                key="stage2_usable_fx_widget",
            )

            st.markdown("#### ② 같은 통화로 들어오거나 나갈 돈")
            st.caption(
                "결제 전에 같은 외화가 들어오면 수입 결제 부담을 일부 상계할 수 있습니다."
            )
            natural_cols = st.columns(3)
            same_flow_amount = natural_cols[0].text_input(
                "예정 외화금액",
                value=form_defaults["same_flow_amount"],
                key="stage2_same_flow_amount_widget",
            )
            same_flow_date = natural_cols[1].date_input(
                "예정일",
                value=form_defaults["same_flow_date"],
                key="stage2_same_flow_date_widget",
            )
            same_flow_direction = natural_cols[2].selectbox(
                "외화 흐름",
                ["INFLOW", "OUTFLOW"],
                index=(
                    0
                    if form_defaults["same_flow_direction"] == "INFLOW"
                    else 1
                ),
                format_func=lambda value: {
                    "INFLOW": "들어올 외화",
                    "OUTFLOW": "나갈 외화",
                }[value],
                help=(
                    "수입 거래는 들어올 외화, 수출 거래는 나갈 외화가 "
                    "자연상계 후보입니다."
                ),
                key="stage2_same_flow_direction_widget",
            )

            with st.expander(
                "이미 계약한 선물환·은행 비용 입력",
                expanded=False,
            ):
                hedge_cols = st.columns(3)
                hedge_amount = hedge_cols[0].text_input(
                    "기존 헤지 외화금액",
                    value=form_defaults["hedge_amount"],
                    key="stage2_hedge_amount_widget",
                )
                locked_rate = hedge_cols[1].text_input(
                    "기존 헤지 약정환율",
                    value=form_defaults["hedge_rate"],
                    key="stage2_locked_rate_widget",
                )
                hedge_fee = hedge_cols[2].text_input(
                    "기존 헤지 수수료",
                    value=form_defaults["hedge_fee"],
                    key="stage2_hedge_fee_widget",
                )
                fee_cols = st.columns(2)
                bank_spread = fee_cols[0].text_input(
                    "은행 환전 스프레드 · bps",
                    value=form_defaults["bank_spread"],
                    key="stage2_bank_spread_widget",
                )
                bank_fee = fee_cols[1].text_input(
                    "거래별 은행 수수료",
                    value=form_defaults["bank_fee"],
                    key="stage2_bank_fee_widget",
                )

            st.markdown("#### ③ 결제일까지 예정된 원화 입출금")
            st.caption("행을 추가하거나 삭제해 회사의 현금 일정을 반영하세요.")
            default_cashflows = pd.DataFrame(
                form_defaults["cashflows"],
                columns=[
                    "date",
                    "amount",
                    "direction",
                    "category",
                    "description",
                ],
            )
            edited_cashflows = st.data_editor(
                default_cashflows,
                num_rows="dynamic",
                width="stretch",
                hide_index=True,
                column_config={
                    "direction": st.column_config.SelectboxColumn(
                        "입출금",
                        options=["INFLOW", "OUTFLOW"],
                    ),
                    "category": st.column_config.SelectboxColumn(
                        "분류",
                        options=["REVENUE", "COST", "OTHER"],
                    ),
                    "date": "날짜",
                    "amount": "금액",
                    "description": "설명",
                },
                key="krw_cashflow_editor",
            )

            with st.expander("추가 경영 스트레스도 함께 보기", expanded=False):
                st.caption(
                    "환율 외에 매출 감소·입금 지연·비용 증가가 동시에 발생하는 경우입니다."
                )
                stress_cols = st.columns(3)
                revenue_reduction = stress_cols[0].text_input(
                    "매출 감소 비율 · 0.10=10%",
                    value=form_defaults["revenue_reduction"],
                    key="stage2_revenue_reduction_widget",
                )
                revenue_delay = stress_cols[1].number_input(
                    "매출 입금 지연 일수",
                    min_value=0,
                    max_value=365,
                    value=form_defaults["revenue_delay"],
                    key="stage2_revenue_delay_widget",
                )
                cost_increase = stress_cols[2].text_input(
                    "비용 증가 비율 · 0.10=10%",
                    value=form_defaults["cost_increase"],
                    key="stage2_cost_increase_widget",
                )
            stage2_submit = st.form_submit_button(
                "우리 회사 현금 영향 계산하기",
                type="primary",
            )

        if stage2_submit:
            try:
                form_input = Stage2FormInput(
                    as_of_date=as_of.isoformat(),
                    current_krw_cash=current_cash,
                    minimum_cash_buffer=minimum_buffer,
                    credit_limit=credit_limit,
                    usable_fx_balance=usable_fx,
                    acceptable_fx_loss=acceptable_loss,
                    same_currency_flow_amount=same_flow_amount,
                    same_currency_flow_date=same_flow_date.isoformat(),
                    same_currency_flow_direction=same_flow_direction,
                    existing_hedge_amount=hedge_amount,
                    existing_hedge_rate=locked_rate,
                    existing_hedge_fee=hedge_fee,
                    bank_spread_bps=bank_spread,
                    bank_fee=bank_fee,
                    krw_cashflow_rows=edited_cashflows.to_dict("records"),
                    revenue_reduction_percent=revenue_reduction,
                    revenue_delay_days=int(revenue_delay),
                    cost_increase_percent=cost_increase,
                )
                stage2_input = build_stage2_input_from_form(
                    document_input=document_input,
                    form=form_input,
                )
                workflow = _workflow_from_state()
                if workflow is None:
                    raise ValueError(
                        "분석 세션을 찾을 수 없습니다. 거래 확인부터 다시 시작하세요."
                    )
                workflow = orchestrator.run_cashflow(
                    workflow,
                    stage2_input,
                )
                if workflow.cashflow is None or workflow.cashflow.data is None:
                    raise ValueError(
                        "결정론 계산에 실패했습니다: {}".format(
                            ", ".join(
                                workflow.cashflow.errors
                                if workflow.cashflow is not None
                                else []
                            )
                        )
                    )
                result = workflow.cashflow.data
                _save_model("stage2_input", stage2_input)
                _save_model("stage2_result", result)
                _save_workflow(workflow)
                clear_downstream(st.session_state, 3)
                extraction_for_decision = _model_from_state(
                    "extraction",
                    TradeDocumentExtraction,
                )
                confirmation_for_decision = _model_from_state(
                    "confirmation",
                    ConfirmationRecord,
                )
                if (
                    extraction_for_decision is None
                    or confirmation_for_decision is None
                    or workflow.market_risk is None
                    or workflow.market_risk.data is None
                ):
                    raise ValueError(
                        "위험 분류에 필요한 확정 거래 또는 환율 가정이 없습니다."
                    )
                decision_support = build_decision_support(
                    case_id=workflow.case_id,
                    extraction=extraction_for_decision,
                    confirmation=confirmation_for_decision,
                    stage1=workflow.market_risk.data.scenario_set,
                    stage2_input=stage2_input,
                    stage2_result=result,
                    missing_information=list(
                        extraction_for_decision.missing_required_fields
                    ),
                )
                _save_decision_support(decision_support)
                st.success("환율별 현금 영향 계산을 완료했습니다.")
                st.rerun()
            except (ValueError, TypeError) as exc:
                st.error("계산 입력을 확인하세요: {}".format(exc))

        stage2_result = _model_from_state("stage2_result", Stage2Result)
        if stage2_result is not None:
            (
                risk_tone,
                risk_label,
                risk_headline,
                risk_detail,
            ) = _risk_summary(stage2_result)
            st.markdown(
                "<div class='risk-banner {}'><div class='signal'>{}</div>"
                "<div><strong>{}</strong><p>입력한 현금·대출한도와 모든 "
                "환율 구간을 함께 반영한 결과입니다.</p></div>"
                "<div class='detail'>{}</div></div>".format(
                    risk_tone,
                    escape(risk_label),
                    escape(risk_headline),
                    escape(risk_detail),
                ),
                unsafe_allow_html=True,
            )
            scenario_results = stage2_result.scenario_results
            highest_loss = max(
                (
                    _decimal_or_zero(item.loss_vs_base)
                    for item in scenario_results
                ),
                default=Decimal("0"),
            )
            minimum_cash = min(
                (
                    _decimal_or_zero(item.minimum_cash)
                    for item in scenario_results
                ),
                default=Decimal("0"),
            )
            highest_buffer_gap = max(
                (
                    _decimal_or_zero(item.maximum_buffer_shortfall)
                    for item in scenario_results
                ),
                default=Decimal("0"),
            )
            highest_payment_gap = max(
                (
                    _decimal_or_zero(item.post_credit_shortfall)
                    for item in scenario_results
                ),
                default=Decimal("0"),
            )
            metrics = st.columns(5)
            metrics[0].metric(
                (
                    "기준 환율 결제액"
                    if stage2_result.trade_type == "IMPORT"
                    else "기준 환율 수취액"
                ),
                format_krw(stage2_result.base_required_or_proceeds_krw),
            )
            metrics[1].metric(
                (
                    "최대 환율 추가비용"
                    if stage2_result.trade_type == "IMPORT"
                    else "최대 원화 수취 감소"
                ),
                format_krw(max(highest_loss, Decimal("0"))),
            )
            metrics[2].metric(
                "가장 낮은 예상 잔고",
                format_krw(minimum_cash),
            )
            metrics[3].metric(
                "최대 운영자금 부족",
                format_krw(highest_buffer_gap),
            )
            metrics[4].metric(
                "대출한도 반영 후 부족",
                format_krw(highest_payment_gap),
                help=(
                    "최소 운영자금 부족과 다릅니다. 현금과 입력한 대출한도를 "
                    "모두 반영해도 남는 실제 자금 부족입니다."
                ),
            )

            st.markdown("#### 환율 구간별 현금 결과")
            scenario_rows = [
                {
                    "환율 구간": _scenario_label(item.scenario_name),
                    "적용 환율": "{}원".format(
                        format_decimal_display(
                            item.applied_rate,
                            decimal_places=2,
                        )
                    ),
                    (
                        "필요 원화"
                        if stage2_result.trade_type == "IMPORT"
                        else "수취 원화"
                    ): format_krw(
                        item.fx_krw_outflow
                        if stage2_result.trade_type == "IMPORT"
                        else item.fx_krw_inflow
                    ),
                    "기준 대비 추가부담": format_krw(item.loss_vs_base),
                    "결제 후 잔고": format_krw(item.ending_cash),
                    "운영자금 부족": format_krw(
                        item.maximum_buffer_shortfall
                    ),
                    "대출 후 부족": format_krw(
                        item.post_credit_shortfall
                    ),
                    "판정": (
                        "보강 필요"
                        if _decimal_or_zero(
                            item.post_credit_shortfall
                        ) > 0
                        else "운영자금 주의"
                        if _decimal_or_zero(
                            item.maximum_buffer_shortfall
                        ) > 0
                        else "방어선 유지"
                    ),
                }
                for item in scenario_results
            ]
            st.dataframe(
                scenario_rows,
                width="stretch",
                hide_index=True,
            )

            st.markdown("#### 결제일까지 현금 잔고 흐름")
            ledger_rows = []
            for scenario in scenario_results:
                for item in scenario.ledger:
                    ledger_rows.append(
                        {
                            "date": item.date,
                            "scenario": _scenario_label(item.scenario),
                            "balance": float(Decimal(item.balance)),
                        }
                    )
            if ledger_rows:
                ledger_frame = pd.DataFrame(ledger_rows).pivot(
                    index="date",
                    columns="scenario",
                    values="balance",
                )
                st.line_chart(ledger_frame)
                st.caption(
                    "선이 운영자금 방어선 아래로 내려가는 시점이 있는지 확인하세요."
                )
            if stage2_result.warnings:
                for warning in stage2_result.warnings:
                    st.warning(warning)

            risk_assessment = _model_from_state(
                "risk_assessment",
                RiskAssessment,
            )
            consultation_topics = _consultation_topics_from_state()
            consultation_packet = _model_from_state(
                "consultation_packet",
                ConsultationPacketResult,
            )
            if risk_assessment is not None:
                st.divider()
                st.markdown("### 위험 원인")
                status_labels = {
                    "SAFE": "현재 입력 기준 방어선 유지",
                    "LOSS_LIMIT_EXCEEDED": "허용 손실한도 초과",
                    "BUFFER_SHORTFALL": "최소 운영자금 부족",
                    "NEGATIVE_CASH": "현금 잔고 음수",
                    "PAYMENT_GAP": "가용자금 반영 후 지급 부족",
                }
                risk_labels = {
                    "FX_COST_RISK": "환율 상승 시 수입 결제비용 증가",
                    "FX_RECEIPT_RISK": "환율 하락 시 수출대금 원화 수취 감소",
                    "LOSS_LIMIT_EXCEEDED": "입력한 손실한도 초과",
                    "LIQUIDITY_BUFFER_RISK": "최소 운영자금 방어선 미달",
                    "NEGATIVE_CASH_RISK": "현금 잔고 음수",
                    "PAYMENT_CAPACITY_RISK": "현금·대출한도 반영 후 지급 부족",
                    "TIMING_MISMATCH_RISK": "현금 유입·지급 시점 불일치",
                    "DOCUMENT_INFORMATION_GAP": "거래·자금 정보 확인 필요",
                }
                status_tone = (
                    "danger"
                    if risk_assessment.status
                    in {"NEGATIVE_CASH", "PAYMENT_GAP"}
                    else "warning"
                    if risk_assessment.status != "SAFE"
                    else ""
                )
                st.markdown(
                    "<div class='state-banner {}'><span class='state-icon'>"
                    "{}</span><div><strong>{}</strong><p>가장 불리한 "
                    "스트레스 시나리오는 {}입니다. 판정은 LLM이 아니라 "
                    "계산 결과와 임계값 규칙으로 생성했습니다.</p></div></div>".format(
                        status_tone,
                        "!" if risk_assessment.status != "SAFE" else "✓",
                        escape(
                            status_labels.get(
                                risk_assessment.status,
                                risk_assessment.status,
                            )
                        ),
                        escape(risk_assessment.worst_scenario_id),
                    ),
                    unsafe_allow_html=True,
                )
                if risk_assessment.findings:
                    finding_rows = []
                    for finding in risk_assessment.findings:
                        trigger_value = finding.trigger_value
                        threshold = finding.threshold or "-"
                        if finding.unit == "KRW":
                            trigger_value = format_krw(
                                finding.trigger_value
                            )
                            threshold = (
                                format_krw(finding.threshold)
                                if finding.threshold is not None
                                else "-"
                            )
                        finding_rows.append(
                            {
                                "위험 원인": risk_labels.get(
                                    finding.risk_code,
                                    finding.risk_code,
                                ),
                                "코드": finding.risk_code,
                                "시나리오": (
                                    finding.scenario_id or "공통"
                                ),
                                "발생값": trigger_value,
                                "기준값": threshold,
                                "중요도": finding.severity,
                            }
                        )
                    st.dataframe(
                        finding_rows,
                        width="stretch",
                        hide_index=True,
                    )
                else:
                    st.success(
                        "현재 입력에서는 구조화된 주요 위험 기준을 넘지 않았습니다."
                    )

            if consultation_topics:
                st.markdown("### 검토할 금융 대응")
                st.caption(
                    "아래 항목은 규칙 기반 상담 범주입니다. 상품 추천·승인·"
                    "최적 헤지 확정이 아니며 실제 조건은 KB 담당자 검토가 필요합니다."
                )
                for topic in consultation_topics:
                    with st.expander(topic.title, expanded=True):
                        st.caption(
                            "{} · 근거 {} · 사람 검토 필수".format(
                                topic.category,
                                ", ".join(topic.triggered_by) or "정기 점검",
                            )
                        )
                        st.write(topic.explanation)
                        topic_cols = st.columns(2)
                        with topic_cols[0]:
                            st.markdown("**추가 확인 정보**")
                            for information in topic.required_information:
                                st.write("· {}".format(information))
                        with topic_cols[1]:
                            st.markdown("**상담 시 질문**")
                            for question in topic.questions:
                                st.write("· {}".format(question))
                        st.info(
                            "이용 가능 여부와 조건은 사용자와 KB 담당자의 "
                            "상담·심사를 통해 최종 확인합니다."
                        )

            if consultation_packet is not None:
                st.markdown("### KB 상담 준비")
                packet = consultation_packet.packet
                packet_cols = st.columns(3)
                packet_cols[0].metric(
                    "Case ID",
                    packet.case_id[:12],
                )
                packet_cols[1].metric(
                    "계산 버전",
                    packet.calculation_version,
                )
                packet_cols[2].metric(
                    "확인 완료 핵심필드",
                    "{}/5".format(len(packet.user_confirmed_fields)),
                )
                download_cols = st.columns(2)
                with download_cols[0]:
                    json_download(
                        label="KB 상담 패킷 · JSON",
                        value=packet,
                        filename="kb_consultation_packet.json",
                        key="download_consultation_packet_json",
                    )
                with download_cols[1]:
                    st.download_button(
                        "KB 상담 패킷 · Markdown",
                        data=consultation_packet.markdown,
                        file_name="kb_consultation_packet.md",
                        mime="text/markdown",
                        key="download_consultation_packet_markdown",
                    )
                with st.expander("상담 패킷 미리보기", expanded=False):
                    st.markdown(consultation_packet.markdown)
                st.warning(packet.disclaimer)

            with st.expander("노출과 방어수단 계산 상세", expanded=False):
                exposure_cols = st.columns(4)
                exposure_cols[0].metric(
                    "총 거래금액",
                    format_foreign(
                        stage2_result.total_foreign_amount,
                        stage2_result.currency,
                    ),
                )
                exposure_cols[1].metric(
                    "아직 노출된 금액",
                    format_foreign(
                        stage2_result.open_exposure,
                        stage2_result.currency,
                    ),
                )
                exposure_cols[2].metric(
                    "보유외화·동일통화 상계",
                    format_foreign(
                        stage2_result.natural_offset,
                        stage2_result.currency,
                    ),
                )
                exposure_cols[3].metric(
                    "기존 헤지",
                    format_foreign(
                        stage2_result.hedged_amount,
                        stage2_result.currency,
                    ),
                )
                st.caption(
                    "{} · 비교 기준: {}".format(
                        status_badge(scenario_results[0].scenario_kind),
                        stage2_result.comparison_basis,
                    )
                )
            with st.expander("고급 · 계산 입력과 결과 데이터", expanded=False):
                _advanced_downloads_title()
                download_cols = st.columns(2)
                with download_cols[0]:
                    json_download(
                        label="현금 계산 입력 JSON",
                        value=st.session_state["stage2_input"],
                        filename="stage2_input.json",
                        key="download_stage2_input",
                    )
                with download_cols[1]:
                    json_download(
                        label="현금 계산 결과 JSON",
                        value=stage2_result,
                        filename="stage2_result.json",
                        key="download_stage2",
                    )

with stage3_tab:
    _section_intro(
        "STEP 4 · 대응 시뮬레이션",
        "선택 단계로 여러 헤지 조합의 계산상 결과를 비교합니다",
        "선물환·분할환전·미헤지 비율을 바꿔가며 손실과 유동성 제약을 "
        "비교합니다. 최적 비율이나 실행 결정을 확정하지 않습니다.",
    )
    stage2_result = _model_from_state("stage2_result", Stage2Result)
    if stage2_result is None:
        st.markdown(
            "<div class='state-banner warning'><span class='state-icon'>3</span>"
            "<div><strong>먼저 현금 영향을 계산하세요</strong>"
            "<p>우리 회사의 실제 노출액과 자금 방어선을 알아야 대응 조합을 "
            "비교할 수 있습니다.</p></div></div>",
            unsafe_allow_html=True,
        )
    else:
        with st.expander("후보 탐색 기준", expanded=False):
            option_cols = st.columns(2)
            grid = option_cols[0].selectbox(
                "전략 조합 간격",
                [5, 10],
                format_func=lambda value: "{}%p 단위".format(value),
                key="stage3_grid_widget",
            )
            stability = option_cols[1].slider(
                "안정성 우선순위",
                min_value=0.0,
                max_value=1.0,
                value=0.7,
                step=0.1,
                help="1에 가까울수록 비용보다 손실·유동성 방어를 우선합니다.",
                key="stage3_stability_widget",
            )
            cost_cols = st.columns(2)
            forward_fee_bps = cost_cols[0].number_input(
                "선물환 비용 가정 (bps)",
                min_value=0.0,
                value=15.0,
                step=1.0,
                key="stage3_forward_fee_widget",
            )
            staged_fee_bps = cost_cols[1].number_input(
                "분할환전 비용 가정 (bps)",
                min_value=0.0,
                value=5.0,
                step=1.0,
                key="stage3_staged_fee_widget",
            )
            constraint_cols = st.columns(2)
            maximum_forward_ratio = constraint_cols[0].slider(
                "신규 선물환 최대 비율",
                min_value=0.0,
                max_value=1.0,
                value=1.0,
                step=0.05,
                key="stage3_max_forward_widget",
            )
            staged_risk_factor = constraint_cols[1].slider(
                "분할환전 잔여위험 가정",
                min_value=0.0,
                max_value=1.0,
                value=0.5,
                step=0.05,
                key="stage3_staged_risk_widget",
            )
            forward_effective_rate = st.text_input(
                "선물환 약정환율 가정 · 비우면 기준환율 사용",
                value="",
                key="stage3_forward_rate_widget",
            )
        if st.button(
            "대응 전략 3가지 비교하기",
            type="primary",
            key="optimize_stage3",
        ):
            workflow = _workflow_from_state()
            if workflow is None:
                st.error("분석 세션이 없습니다. 거래 확인부터 다시 시작하세요.")
                st.stop()
            workflow = orchestrator.run_hedge(
                workflow,
                grid_step_percent=int(grid),
                stability_preference=format(Decimal(str(stability)), "f"),
                assumptions=Stage3Assumptions(
                    forward_effective_rate=(
                        forward_effective_rate.strip() or None
                    ),
                    forward_fee_bps=format(
                        Decimal(str(forward_fee_bps)),
                        "f",
                    ),
                    staged_conversion_fee_bps=format(
                        Decimal(str(staged_fee_bps)),
                        "f",
                    ),
                    staged_risk_factor=format(
                        Decimal(str(staged_risk_factor)),
                        "f",
                    ),
                    risk_aversion_weight=format(
                        Decimal(str(stability)),
                        "f",
                    ),
                    maximum_forward_ratio=format(
                        Decimal(str(maximum_forward_ratio)),
                        "f",
                    ),
                ),
            )
            if workflow.hedge is None or workflow.hedge.data is None:
                st.error(
                    "헤지 후보 계산에 실패했습니다: {}".format(
                        ", ".join(
                            workflow.hedge.errors
                            if workflow.hedge is not None
                            else []
                        )
                    )
                )
                st.stop()
            result = workflow.hedge.data
            _save_model("stage3_result", result)
            _save_workflow(workflow)
            clear_downstream(st.session_state, 4)
            st.rerun()
        stage3_result = _model_from_state("stage3_result", Stage3Result)
        if stage3_result is not None:
            if not stage3_result.candidates:
                st.error(
                    "현재 입력과 제약을 모두 충족하는 헤지 후보가 없습니다. "
                    "추가 자금, 결제조건 조정 또는 KB 상담이 필요합니다."
                )
                if stage3_result.infeasible_reasons:
                    st.caption(
                        "미충족 제약: {}".format(
                            ", ".join(stage3_result.infeasible_reasons)
                        )
                    )
            st.markdown(
                "<div class='state-banner'><span class='state-icon'>i</span>"
                "<div><strong>검토 순서는 계산상 우선순위이며 금융 자문이 아닙니다</strong>"
                "<p>실제 계약 전 거래은행에 약정환율·수수료·중도해지 조건을 "
                "확인하세요.</p></div></div>",
                unsafe_allow_html=True,
            )
            cards = st.columns(3)
            for card, candidate in zip(
                cards,
                stage3_result.candidates,
            ):
                with card:
                    candidate_chip = {
                        "STABILITY_FIRST": "안정성 우선",
                        "BALANCED": "균형",
                        "COST_FIRST": "비용 우선",
                    }.get(candidate.profile, "비교 후보")
                    constraint_copy = (
                        "입력한 제약 충족"
                        if candidate.constraints_satisfied
                        else "입력한 제약 미충족"
                    )
                    st.markdown(
                        "<div class='status-card'>"
                        "<div class='rank'><strong>검토 순위 {}</strong>"
                        "<span class='chip'>{}</span></div>"
                        "<div class='mix'>"
                        "<div><small>선물환</small><b>{}</b></div>"
                        "<div><small>분할환전</small><b>{}</b></div>"
                        "<div><small>미헤지</small><b>{}</b></div>"
                        "</div>"
                        "<div class='outcome'>"
                        "<div><small>최악 추가부담</small><b>{}</b></div>"
                        "<div><small>비용 가정</small><b>{}</b></div>"
                        "<div><small>유동성 영향</small><b>{}</b></div>"
                        "<div><small>보유외화 반영</small><b>{}</b></div>"
                        "<div><small>q90 손실</small><b>{}</b></div>"
                        "<div><small>±10% 불리방향 손실</small><b>{}</b></div>"
                        "<div><small>최저 현금잔고</small><b>{}</b></div>"
                        "</div><div class='constraint'>{}</div></div>".format(
                            candidate.rank,
                            candidate_chip,
                            format_ratio(candidate.forward_ratio),
                            format_ratio(
                                candidate.staged_conversion_ratio
                            ),
                            format_ratio(candidate.unhedged_ratio),
                            format_krw(candidate.worst_case_loss),
                            format_krw(candidate.assumed_hedge_cost),
                            format_krw(candidate.liquidity_impact),
                            format_ratio(candidate.held_fx_ratio),
                            (
                                format_krw(candidate.q90_adverse_loss)
                                if candidate.q90_adverse_loss is not None
                                else "기간 외 · 미적용"
                            ),
                            (
                                format_krw(candidate.fixed_10_adverse_loss)
                                if candidate.fixed_10_adverse_loss
                                is not None
                                else "미확인"
                            ),
                            format_krw(candidate.minimum_cash_balance),
                            constraint_copy,
                        ),
                        unsafe_allow_html=True,
                    )
                    st.caption(candidate.rationale)
                    if candidate.limitations:
                        with st.expander("가정과 한계", expanded=False):
                            for limitation in candidate.limitations:
                                st.write("· {}".format(limitation))
            with st.expander("고급 · 전략 후보 데이터", expanded=False):
                _advanced_downloads_title()
                json_download(
                    label="대응 전략 후보 JSON",
                    value=stage3_result,
                    filename="stage3_candidates.json",
                    key="download_stage3",
                )

with stage4_tab:
    _section_intro(
        "STEP 5 · 공식 상담 정보",
        "선택 단계로 공식 출처가 확인된 금융상품·지원제도만 연결합니다",
        "앞에서 계산한 대응 전략과 관련 있는 후보를 찾습니다. "
        "가입 자격·승인·한도·금리는 확정하지 않고 상담에서 확인할 항목으로 남깁니다.",
    )
    stage2_result = _model_from_state("stage2_result", Stage2Result)
    stage3_result = _model_from_state("stage3_result", Stage3Result)
    if stage2_result is None or stage3_result is None:
        st.markdown(
            "<div class='state-banner warning'><span class='state-icon'>4</span>"
            "<div><strong>대응 전략을 먼저 비교하세요</strong>"
            "<p>계산된 전략과 거래 방향을 바탕으로 관련 금융상품과 "
            "지원제도를 연결합니다.</p></div></div>",
            unsafe_allow_html=True,
        )
    else:
        default_query = (
            " ".join(
                stage3_result.candidates[0].required_product_types
                + [
                    "선물환",
                    "환변동보험",
                    "외화예금",
                    "수출입대출",
                    "정책자금",
                    "보증상품",
                ]
            )
            if stage3_result.candidates
            else "수출입 결제자금 환율관리 운영자금 상담"
        )
        with st.expander("검색 범위와 출처 설정", expanded=False):
            query = st.text_input(
                "찾을 상품·제도 유형",
                value=default_query,
                key="stage4_query_widget",
            )
            search_modes = ["OFFLINE_KB"]
            if settings.enable_official_web_search:
                search_modes.append("OFFICIAL_WEB_SEARCH")
            search_mode = st.radio(
                "공식자료 확인 방식",
                search_modes,
                horizontal=True,
                format_func=lambda value: {
                    "OFFLINE_KB": "검증된 공식자료 스냅샷",
                    "OFFICIAL_WEB_SEARCH": "공식 사이트 최신 검색",
                }[value],
                key="stage4_search_mode_widget",
            )
        if st.button(
            "우리 거래에 맞는 공식 상담 후보 찾기",
            type="primary",
            key="search_stage4",
        ):
            try:
                workflow = _workflow_from_state()
                if workflow is None:
                    raise RuntimeError(
                        "분석 세션이 없습니다. 거래 확인부터 다시 시작하세요."
                    )
                workflow = orchestrator.run_product_search(
                    workflow,
                    query=query,
                    mode=search_mode,
                )
                if (
                    workflow.product_search is None
                    or workflow.product_search.data is None
                ):
                    raise RuntimeError(
                        "상품 검색에 실패했습니다: {}".format(
                            ", ".join(
                                workflow.product_search.errors
                                if workflow.product_search is not None
                                else []
                            )
                        )
                    )
                result = workflow.product_search.data
                _save_model("stage4_result", result)
                _save_workflow(workflow)
                clear_downstream(st.session_state, 5)
                st.rerun()
            except RuntimeError as exc:
                st.error(str(exc))
        stage4_result = _model_from_state("stage4_result", Stage4Result)
        if stage4_result is not None:
            if not stage4_result.candidates:
                st.markdown(
                    "<div class='state-banner warning'><span class='state-icon'>!</span>"
                    "<div><strong>공식 출처에서 연결할 후보를 찾지 못했습니다</strong>"
                    "<p>상품을 임의로 만들지 않았습니다. 검색 범위를 조정하거나 "
                    "거래은행에 직접 문의하세요.</p></div></div>",
                    unsafe_allow_html=True,
                )
            product_columns = st.columns(2)
            for index, candidate in enumerate(stage4_result.candidates):
                with product_columns[index % 2]:
                    with st.container(border=True):
                        st.caption(
                            "{} · {} · 공식 출처 확인".format(
                                candidate.institution,
                                candidate.category,
                            )
                        )
                        st.markdown("### {}".format(candidate.name))
                        st.write(candidate.summary)
                        st.markdown("**왜 이 거래와 연결되나요?**")
                        st.write(candidate.strategy_connection_reason)
                        status_cols = st.columns(2)
                        status_cols[0].metric("분류", "상담 후보")
                        status_cols[1].metric("자격 여부", "기관 확인 필요")
                        with st.expander("상담 전 확인할 조건과 서류"):
                            st.markdown(
                                "**주요 조건**  \n{}".format(
                                    " · ".join(candidate.key_conditions)
                                    or "기관 확인 필요"
                                )
                            )
                            st.markdown(
                                "**준비 서류**  \n{}".format(
                                    " · ".join(candidate.required_documents)
                                    or "기관 확인 필요"
                                )
                            )
                            st.markdown(
                                "**대상 고객**  \n{}".format(
                                    " · ".join(candidate.target_customers)
                                    or "기관 확인 필요"
                                )
                            )
                        st.markdown(
                            "[공식 페이지에서 확인 · {}]({})  \n"
                            "자료 확인일 {}".format(
                                candidate.source.title,
                                candidate.source.url,
                                candidate.source.verified_at,
                            )
                        )
            st.markdown(
                "<div class='state-banner'><span class='state-icon'>→</span>"
                "<div><strong>다음 단계는 사람과의 상담입니다</strong>"
                "<p>이 화면은 상품 추천이나 승인 결과가 아닙니다. "
                "공식 페이지와 거래은행에서 조건을 다시 확인하세요.</p></div></div>",
                unsafe_allow_html=True,
            )
            with st.expander("고급 · 공식 후보 데이터", expanded=False):
                _advanced_downloads_title()
                json_download(
                    label="공식 상담 후보 JSON",
                    value=stage4_result,
                    filename="stage4_products.json",
                    key="download_stage4",
                )

with stage5_tab:
    _section_intro(
        "STEP 6 · 상담 리포트",
        "계산 결과와 상담 질문을 재현 가능한 패킷으로 정리합니다",
        "위험 진단까지 완료하면 JSON·Markdown 상담 패킷을 바로 받을 수 있습니다. "
        "헤지 시뮬레이션과 공식 정보 검색은 선택 단계입니다.",
    )
    consultation_packet = _model_from_state(
        "consultation_packet",
        ConsultationPacketResult,
    )
    if consultation_packet is None:
        st.markdown(
            "<div class='state-banner warning'><span class='state-icon'>3</span>"
            "<div><strong>먼저 리스크 진단을 완료하세요</strong>"
            "<p>확정 거래와 환율·현금정보를 계산하면 위험 원인, 대응 후보와 "
            "상담 준비 패킷이 함께 생성됩니다.</p></div></div>",
            unsafe_allow_html=True,
        )
    else:
        packet = consultation_packet.packet
        st.markdown(
            "<div class='state-banner'><span class='state-icon'>✓</span>"
            "<div><strong>KB 상담 준비 패킷이 완성되었습니다</strong>"
            "<p>패킷 숫자는 Stage 2 결정론 계산 결과에서 직접 가져왔으며 "
            "LLM이 다시 계산하거나 변형하지 않았습니다.</p></div></div>",
            unsafe_allow_html=True,
        )
        packet_metrics = st.columns(4)
        packet_metrics[0].metric(
            "거래 방향",
            packet.company_summary.trade_type,
        )
        packet_metrics[1].metric(
            "열린 환노출",
            format_foreign(
                packet.exposure_summary.open_exposure_fx,
                packet.company_summary.currency,
            ),
        )
        packet_metrics[2].metric(
            "운영자금 부족",
            format_krw(packet.risk_summary.buffer_shortfall_krw),
        )
        packet_metrics[3].metric(
            "대출한도 반영 후 부족",
            format_krw(packet.risk_summary.payment_gap_krw),
        )
        packet_downloads = st.columns(2)
        with packet_downloads[0]:
            json_download(
                label="상담 패킷 다운로드 · JSON",
                value=packet,
                filename="kb_consultation_packet.json",
                key="download_consultation_packet_json_stage5",
            )
        with packet_downloads[1]:
            st.download_button(
                "상담 패킷 다운로드 · Markdown",
                data=consultation_packet.markdown,
                file_name="kb_consultation_packet.md",
                mime="text/markdown",
                key="download_consultation_packet_markdown_stage5",
            )
        st.markdown("### 상담 패킷 미리보기")
        st.markdown(consultation_packet.markdown)

    extraction = _model_from_state("extraction", TradeDocumentExtraction)
    confirmation = _model_from_state("confirmation", ConfirmationRecord)
    stage1_load = _model_from_state("stage1_load", Stage1LoadResult)
    stage2_result = _model_from_state("stage2_result", Stage2Result)
    stage3_result = _model_from_state("stage3_result", Stage3Result)
    stage4_result = _model_from_state("stage4_result", Stage4Result)
    all_ready = all(
        item is not None
        for item in (
            extraction,
            confirmation,
            stage1_load,
            stage2_result,
            stage3_result,
            stage4_result,
        )
    )
    st.divider()
    st.markdown("### 선택 · 헤지·공식자료를 포함한 확장 리포트")
    if not all_ready:
        st.info(
            "기본 상담 패킷은 위에서 이미 완성됩니다. 대응 시뮬레이션과 공식 "
            "상담 정보를 실행하면 출처를 포함한 확장 리포트도 만들 수 있습니다."
        )
    else:
        if st.button(
            "확장 상담 리포트 만들기",
            type="primary",
            key="generate_report",
        ):
            workflow = _workflow_from_state()
            if workflow is None:
                st.error("분석 세션이 없습니다. 거래 확인부터 다시 시작하세요.")
                st.stop()
            workflow = orchestrator.run_report(workflow)
            if workflow.final_report is None:
                st.error(
                    "보고서 생성에 실패했습니다: {}".format(
                        ", ".join(
                            workflow.report.errors
                            if workflow.report is not None
                            else []
                        )
                    )
                )
                st.stop()
            report = workflow.final_report
            _save_model("report_result", report)
            _save_workflow(workflow)
            st.rerun()
        report_result = _model_from_state(
            "report_result",
            ReportResult,
        )
        if report_result is not None:
            st.markdown(
                "<div class='state-banner'><span class='state-icon'>✓</span>"
                "<div><strong>확장 상담 리포트가 완성되었습니다</strong>"
                "<p>수치와 출처를 다시 확인한 뒤 거래은행 또는 보험기관과 "
                "공유하세요.</p></div></div>",
                unsafe_allow_html=True,
            )
            report_cols = st.columns(2)
            with report_cols[0]:
                st.download_button(
                    "상담 리포트 다운로드 · Markdown",
                    data=report_result.markdown,
                    file_name="fx_cashflow_risk_report.md",
                    mime="text/markdown",
                    key="download_report_md",
                )
            with report_cols[1]:
                json_download(
                    label="근거 데이터 다운로드 · JSON",
                    value=report_result.report_json,
                    filename="fx_cashflow_risk_report.json",
                    key="download_report_json",
                )
            st.divider()
            st.markdown("### 리포트 미리보기")
            st.markdown(report_result.markdown)
            with st.expander("고급 · 보고서 검수 기록", expanded=False):
                st.caption(
                    "상태: {} · critic={} · score={} · rewrite={} · "
                    "fallback_reason={}".format(
                        report_result.status,
                        (
                            "PASS"
                            if report_result.critique.passed
                            else "FALLBACK_POLICY"
                        ),
                        report_result.critique.score,
                        report_result.revision_count,
                        report_result.fallback_reason or "none",
                    )
                )

workflow_trace_state = _workflow_from_state()
if workflow_trace_state is not None:
    render_workflow_trace(workflow_trace_state)

st.divider()
st.markdown(
    "<div style='display:flex;justify-content:space-between;gap:1rem;"
    "flex-wrap:wrap;color:#7f92a8;font-size:.76rem;padding:.5rem 0'>"
    "<span>수출입 금융 의사결정 지원 · 기업 재무 담당자용</span>"
    "<span>AI는 문서 추출·설명만 지원 · 금융 계산은 일반 코드 · "
    "대응은 상담 후보</span></div>",
    unsafe_allow_html=True,
)
