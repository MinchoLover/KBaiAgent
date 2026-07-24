import json
from datetime import date
from decimal import Decimal
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
from src.config import Settings
from src.demo import run_offline_demo
from src.document_intake.confirmation import (
    ConfirmationRecord,
    create_confirmation_record,
    validate_confirmation,
)
from src.document_intake.extractor import (
    ExtractionError,
    extract_trade_document_with_metadata,
)
from src.domain.product_models import Stage4Result
from src.domain.report_models import ReportResult
from src.domain.stage1_models import Stage1LoadResult
from src.domain.stage2_models import Stage2Result
from src.domain.stage3_models import Stage3Result
from src.security.upload_guard import validate_upload
from src.ui.components import (
    decimal_text,
    evidence_rows,
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


def _safe_index(options: List[str], value: str) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0


def _demo_all() -> None:
    clear_transaction_widgets(st.session_state)
    st.session_state["run_mode_widget"] = "데모 모드"
    st.session_state["company_role_widget"] = "구매자 · BUYER"
    st.session_state["company_country_widget"] = "KR"
    st.session_state["stage1_mode_widget"] = "MANUAL_STRESS"
    result = run_offline_demo()
    extraction = result["extraction"]
    _save_model("extraction", extraction)
    _save_model("extraction_original", extraction)
    _save_model("extraction_validation", result["validation"])
    _save_model("confirmation", result["confirmation"])
    _save_model("confirmation_validation", result["validation"])
    st.session_state["stage0_output"] = build_stage0_output(
        extraction=extraction,
        validation=result["validation"],
        confirmations=result["confirmation"].checks,
        source_filename="sample_invoice.png",
        prompt_version=get_prompt_version(),
        confirmation_record=result["confirmation"],
    )
    st.session_state["stage2_document_input"] = build_stage2_input(
        extraction=extraction,
        validation=result["validation"],
        confirmations=result["confirmation"].checks,
        source_filename="sample_invoice.png",
        source_sha256=result["confirmation"].source_sha256,
        confirmed_at=result["confirmation"].confirmed_at,
    )
    _save_model(
        "stage1_load",
        Stage1LoadResult(
            source="MANUAL",
            scenario_set=result["stage1"],
        ),
    )
    _save_model("stage2_input", result["stage2_input"])
    _save_model("stage2_result", result["stage2"])
    _save_model("stage3_result", result["stage3"])
    _save_model("stage4_result", result["stage4"])
    _save_model("report_result", result["report"])
    _save_workflow(result["workflow_state"])
    metadata = validate_upload(
        file_bytes=SAMPLE_PATH.read_bytes(),
        filename=SAMPLE_PATH.name,
        claimed_mime_type="image/png",
    )
    st.session_state["upload_metadata"] = {
        "filename": metadata.filename,
        "mime_type": metadata.mime_type,
        "size_bytes": metadata.size_bytes,
        "sha256": metadata.sha256,
        "page_count": metadata.page_count,
    }
    st.session_state["skip_signature_sync_once"] = True
    st.session_state["demo_just_loaded"] = True


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
    page_title="FX Cashflow Risk Copilot",
    page_icon="₩",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
<style>
.block-container {padding-top: 1.7rem; max-width: 1450px;}
[data-testid="stMetricValue"] {font-size: 1.55rem;}
.status-card {
  border: 1px solid #e4e7ec; border-radius: 12px; padding: 0.75rem 1rem;
  background: #f8fafc; margin-bottom: 0.5rem;
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

with st.sidebar:
    st.header("실행 모드")
    live_label = "실제 API 모드"
    mode_label = st.radio(
        "문서 추출",
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
    st.caption(
        "API key: {}".format(
            "configured" if settings.openai_api_key else "not configured"
        )
    )
    st.caption("모델: 환경변수 OPENAI_MODEL")
    st.button(
        "전체 오프라인 데모 실행",
        width="stretch",
        on_click=_demo_all,
    )
    if st.session_state.pop("demo_just_loaded", False):
        st.success("Stage 0~5 데모 결과를 생성했습니다.")
    st.button(
        "세션 결과 초기화",
        width="stretch",
        on_click=_reset_state,
    )
    st.divider()
    st.info(
        "개인정보 안내: 문서 원문은 로그나 데이터셋에 자동 저장되지 "
        "않습니다. 실제 문서 전송 전 회사 정책을 확인하세요."
    )

st.title("수출입 환율·현금흐름 리스크 Copilot")
st.caption(
    "문서 근거 추출 → 사람 확인 → 스트레스/예측 시나리오 → "
    "Decimal 계산 → 전략·공식상품 후보 → 추적 가능한 보고서"
)
render_stepper(_completed_stage())

stage0_tab, stage1_tab, stage2_tab, stage3_tab, stage4_tab, stage5_tab = (
    st.tabs(
        [
            "0 · 문서 인테이크",
            "1 · 환율 시나리오",
            "2 · 현금흐름 계산",
            "3 · 헤지 후보",
            "4 · 공식 상품",
            "5 · 보고서",
        ]
    )
)

with stage0_tab:
    st.subheader("문서 업로드와 근거 기반 추출")
    control_col, preview_col = st.columns([1, 1])
    with control_col:
        role_label = st.radio(
            "우리 회사의 문서상 역할",
            ["구매자 · BUYER", "판매자 · SELLER"],
            horizontal=True,
            key="company_role_widget",
        )
        company_role = (
            "BUYER" if role_label.startswith("구매자") else "SELLER"
        )
        company_country = st.text_input(
            "우리 회사 국가 코드",
            max_chars=2,
            key="company_country_widget",
        ).strip().upper()
        uploaded = st.file_uploader(
            "Commercial Invoice / Sales Contract / Purchase Order",
            type=["pdf", "png", "jpg", "jpeg"],
            help="기본 제한: 15MB, PDF 20페이지",
        )
        st.caption("지원: PDF, PNG, JPG/JPEG · archive 업로드 금지")

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
        "문서 분석",
        type="primary",
        width="stretch",
        key="analyze_document",
    ):
        try:
            if len(company_country) != 2 or not company_country.isalpha():
                raise ValueError("회사 국가는 ISO alpha-2 두 글자여야 합니다.")
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
            _save_model("extraction_original", extraction)
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
        st.subheader("사용자 검토·수정")
        st.warning(
            "모델 추출값은 계산 입력이 아닙니다. 수정 후 통화·금액·결제일을 "
            "각각 확인해야 Stage 2가 열립니다."
        )
        document_types = [
            "COMMERCIAL_INVOICE",
            "SALES_CONTRACT",
            "PURCHASE_ORDER",
            "UNKNOWN",
        ]
        st.session_state[
            "review_trade_type_widget"
        ] = extraction.trade_type
        with st.form("review_extraction"):
            row1 = st.columns(4)
            document_type = row1[0].selectbox(
                "문서 유형",
                document_types,
                index=_safe_index(document_types, extraction.document_type),
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
                "Balance / Amount Due",
                value=extraction.amount_due or "",
                key="review_amount_due_widget",
            )
            row2 = st.columns(4)
            grand_total = row2[0].text_input(
                "Grand Total",
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
                "결제조건",
                value=extraction.payment_terms or "",
                key="review_payment_terms_widget",
            )
            incoterm = row3[2].text_input(
                "Incoterm",
                value=extraction.incoterm or "",
                key="review_incoterm_widget",
            )
            row3[3].text_input(
                "거래 방향 · 자동 결정",
                disabled=True,
                key="review_trade_type_widget",
                help=(
                    "회사 역할과 구매자·판매자 국가 근거가 모두 맞을 때만 "
                    "IMPORT/EXPORT로 결정합니다."
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
            ).strip().upper()
            buyer_name = row4[2].text_input(
                "구매자",
                value=extraction.buyer_name or "",
                key="review_buyer_name_widget",
            )
            buyer_country = row4[3].text_input(
                "구매자 국가",
                value=extraction.buyer_country or "",
                key="review_buyer_country_widget",
            ).strip().upper()

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
                key="installment_editor",
            )
            reviewed = st.form_submit_button(
                "수정값 검증",
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
                            due_date=_blank_to_none(row.get("due_date")),
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
                        "issue_date": _blank_to_none(issue_date),
                        "contract_date": _blank_to_none(contract_date),
                        "shipment_date": _blank_to_none(shipment_date),
                        "explicit_due_date": _blank_to_none(
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
                edited, validation = apply_deterministic_review_state(
                    edited,
                    company_role=company_role,
                    company_country=company_country,
                )
                _save_model("extraction", edited)
                _save_model("extraction_validation", validation)
                clear_confirmation_and_later(st.session_state)
                _store_intake_workflow(
                    mode=run_mode,
                    extraction=edited,
                    validation=validation,
                    provider="deterministic_review",
                )
                st.success("수정값을 결정론적으로 재검증했습니다.")
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
            )
        status_col, gate_col = st.columns(2)
        status_col.metric(
            "결정론 검증",
            "PASS" if validation.validation_pass else "REVIEW",
        )
        gate_col.metric(
            "Stage 2 gate",
            "OPEN" if validation.stage2_allowed else "LOCKED",
        )
        with st.expander("규칙 검증 결과", expanded=not validation.validation_pass):
            render_validation(validation)

        st.markdown("**원문 근거**")
        rows = evidence_rows(extraction)
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
            badges = sorted({row["상태"] for row in rows})
            st.caption(" · ".join(status_badge(item) for item in badges))
        else:
            st.error("evidence가 없어 자동 전달할 수 없습니다.")

        resolved_due = validation.resolved_due_date or ""
        with st.form("critical_confirmation"):
            confirmed_due = st.text_input(
                "최종 결제일",
                value=resolved_due,
                placeholder="YYYY-MM-DD",
                help="Net N은 Python이 계산하고, 이 값은 사용자가 최종 확인합니다.",
                key="confirmed_due_widget",
            )
            check_cols = st.columns(3)
            currency_ok = check_cols[0].checkbox(
                "통화를 원문과 대조했습니다",
                key="confirm_currency_widget",
            )
            amount_ok = check_cols[1].checkbox(
                "금액을 원문과 대조했습니다",
                key="confirm_amount_widget",
            )
            due_ok = check_cols[2].checkbox(
                "결제일/조건을 대조했습니다",
                key="confirm_due_widget",
            )
            confirmation_submit = st.form_submit_button(
                "확인 완료 · Stage 0 JSON 확정",
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
                    confirmed_due_date=_blank_to_none(confirmed_due),
                    currency_confirmed=currency_ok,
                    amount_due_confirmed=amount_ok,
                    due_date_confirmed=due_ok,
                    source_filename=metadata["filename"],
                    source_sha256=metadata["sha256"],
                    confirmed_by="streamlit-user",
                )
                confirmed_validation = validate_confirmation(
                    extraction=extraction,
                    record=record,
                    company_country=company_country,
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
                        "확인 gate가 열리지 않았습니다. 세 체크와 "
                        "CRITICAL/HIGH 검증 문제를 모두 해결하세요."
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
                    st.success("확인 기록과 Stage 1/2 전달 JSON을 생성했습니다.")
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
                st.success(
                    "Gate OPEN · 통화, 금액, 결제일이 사용자 확인되었습니다."
                )
            else:
                st.error("Gate LOCKED · 확인 또는 검증 문제를 해결하세요.")
            download_cols = st.columns(2)
            with download_cols[0]:
                json_download(
                    label="Stage 0 전체 JSON",
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
                        label="Stage 2 문서 입력 JSON",
                        value=st.session_state["stage2_document_input"],
                        filename="stage2_document_input.json",
                        key="download_document_input",
                    )

with stage1_tab:
    st.subheader("환율 시나리오")
    st.info(
        "MANUAL_STRESS는 예측이 아니라 민감도 가정입니다. "
        "EXTERNAL_STAGE1만 팀원 모델의 FORECAST 결과를 전달합니다."
    )
    document_input = st.session_state.get("stage2_document_input")
    if document_input is None:
        st.warning("먼저 Stage 0 사용자 확인 gate를 통과하세요.")
    else:
        trade = document_input["trade"]
        target_date = (
            trade["settlement_date"]
            or trade["cashflow_events"][0]["settlement_date"]
        )
        st.session_state.setdefault(
            "stage1_mode_widget",
            (
                "EXTERNAL_STAGE1"
                if settings.stage1_mode in {"external", "external_stage1"}
                else "MANUAL_STRESS"
            ),
        )
        scenario_mode = st.radio(
            "시나리오 원천",
            ["MANUAL_STRESS", "EXTERNAL_STAGE1"],
            horizontal=True,
            key="stage1_mode_widget",
        )
        base_rate = st.text_input(
            "기준 환율 · KRW per 1 {}".format(trade["currency"]),
            value="1400",
            key="stage1_base_rate_widget",
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
                    "팀원 Stage 1 JSON",
                    type=["json"],
                    key="stage1_json_upload",
                )
                if stage1_file is not None:
                    payload = stage1_file.getvalue()
            else:
                endpoint = st.text_input(
                    "Stage 1 endpoint",
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
            "시나리오 불러오기",
            type="primary",
            key="load_stage1",
        ):
            try:
                workflow = _workflow_from_state()
                if workflow is None:
                    raise ValueError("Workflow 상태가 없습니다. Stage 0을 다시 확인하세요.")
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
                _save_workflow(workflow)
                clear_downstream(st.session_state, 2)
                st.success("시나리오를 정규화·검증했습니다.")
                st.rerun()
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                st.error(str(exc))

        stage1_load = _model_from_state(
            "stage1_load",
            Stage1LoadResult,
        )
        if stage1_load is not None:
            scenarios = stage1_load.scenario_set
            st.markdown(status_badge(scenarios.kind))
            st.dataframe(
                [item.model_dump() for item in scenarios.scenarios],
                width="stretch",
                hide_index=True,
            )
            st.caption(
                "{} · 적용 규칙: {} · probability_valid={}".format(
                    stage1_load.source,
                    scenarios.application_rule,
                    scenarios.probability_valid,
                )
            )
            json_download(
                label="정규화 Stage 1 JSON",
                value=scenarios,
                filename="stage1_normalized.json",
                key="download_stage1",
            )

with stage2_tab:
    st.subheader("기업 현금흐름·환위험 계산")
    stage1_load = _model_from_state("stage1_load", Stage1LoadResult)
    document_input = st.session_state.get("stage2_document_input")
    if stage1_load is None or document_input is None:
        st.warning("Stage 0 확인과 Stage 1 시나리오가 필요합니다.")
    else:
        trade = document_input["trade"]
        with st.form("stage2_company_input"):
            cash_cols = st.columns(5)
            current_cash = cash_cols[0].text_input(
                "현재 원화 현금",
                value="200000000",
                key="stage2_current_cash_widget",
            )
            minimum_buffer = cash_cols[1].text_input(
                "최소 운영자금",
                value="50000000",
                key="stage2_minimum_buffer_widget",
            )
            credit_limit = cash_cols[2].text_input(
                "대출한도",
                value="30000000",
                key="stage2_credit_limit_widget",
            )
            usable_fx = cash_cols[3].text_input(
                "사용 가능한 보유외화",
                value="10000",
                key="stage2_usable_fx_widget",
            )
            acceptable_loss = cash_cols[4].text_input(
                "감당 가능한 환율손실",
                value="10000000",
                key="stage2_acceptable_loss_widget",
            )
            as_of = st.date_input(
                "현금흐름 기준일",
                value=date.today(),
                key="stage2_as_of_widget",
            )

            natural_cols = st.columns(3)
            same_flow_amount = natural_cols[0].text_input(
                "결제 전 동일통화 흐름",
                value="0",
                key="stage2_same_flow_amount_widget",
            )
            same_flow_date = natural_cols[1].date_input(
                "동일통화 흐름일",
                value=as_of,
                key="stage2_same_flow_date_widget",
            )
            same_flow_direction = natural_cols[2].selectbox(
                "동일통화 흐름 방향",
                ["INFLOW", "OUTFLOW"],
                help="수입은 유입, 수출은 예정 외화지출이 자연헤지 후보입니다.",
                key="stage2_same_flow_direction_widget",
            )

            hedge_cols = st.columns(3)
            hedge_amount = hedge_cols[0].text_input(
                "기존 헤지 외화금액",
                value="0",
                key="stage2_hedge_amount_widget",
            )
            locked_rate = hedge_cols[1].text_input(
                "기존 헤지 약정환율",
                value="1400",
                key="stage2_locked_rate_widget",
            )
            hedge_fee = hedge_cols[2].text_input(
                "기존 헤지 수수료",
                value="0",
                key="stage2_hedge_fee_widget",
            )
            fee_cols = st.columns(2)
            bank_spread = fee_cols[0].text_input(
                "은행 spread · bps",
                value="15",
                key="stage2_bank_spread_widget",
            )
            bank_fee = fee_cols[1].text_input(
                "거래별 은행 수수료",
                value="50000",
                key="stage2_bank_fee_widget",
            )

            st.markdown("**날짜별 원화 입출금 · 행 추가/삭제 가능**")
            default_cashflows = pd.DataFrame(
                [
                    {
                        "date": str(date.today()),
                        "amount": "30000000",
                        "direction": "INFLOW",
                        "category": "REVENUE",
                        "description": "예정 매출 입금",
                    }
                ]
            )
            edited_cashflows = st.data_editor(
                default_cashflows,
                num_rows="dynamic",
                width="stretch",
                hide_index=True,
                column_config={
                    "direction": st.column_config.SelectboxColumn(
                        "direction",
                        options=["INFLOW", "OUTFLOW"],
                    ),
                    "category": st.column_config.SelectboxColumn(
                        "category",
                        options=["REVENUE", "COST", "OTHER"],
                    ),
                },
                key="krw_cashflow_editor",
            )

            stress_cols = st.columns(3)
            revenue_reduction = stress_cols[0].text_input(
                "매출 감소 비율 · 0.10=10%",
                value="0",
                key="stage2_revenue_reduction_widget",
            )
            revenue_delay = stress_cols[1].number_input(
                "매출 입금 지연 일수",
                min_value=0,
                max_value=365,
                value=0,
                key="stage2_revenue_delay_widget",
            )
            cost_increase = stress_cols[2].text_input(
                "비용 증가 비율 · 0.10=10%",
                value="0",
                key="stage2_cost_increase_widget",
            )
            stage2_submit = st.form_submit_button(
                "결정론적 계산 실행",
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
                        "Workflow 상태가 없습니다. Stage 0을 다시 확인하세요."
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
                st.success("동일 입력에 동일 결과를 내는 Decimal 계산을 완료했습니다.")
                st.rerun()
            except (ValueError, TypeError) as exc:
                st.error("계산 입력을 확인하세요: {}".format(exc))

        stage2_result = _model_from_state("stage2_result", Stage2Result)
        if stage2_result is not None:
            metrics = st.columns(4)
            metrics[0].metric(
                "총 외화금액",
                "{} {}".format(
                    stage2_result.total_foreign_amount,
                    stage2_result.currency,
                ),
            )
            metrics[1].metric(
                "Open exposure",
                stage2_result.open_exposure,
            )
            metrics[2].metric(
                "Natural offset",
                stage2_result.natural_offset,
            )
            metrics[3].metric(
                "기존 hedge",
                stage2_result.hedged_amount,
            )
            scenario_rows = [
                {
                    "scenario": item.scenario_name,
                    "상태": item.scenario_kind,
                    "환율": item.scenario_rate,
                    "적용환율": item.applied_rate,
                    "필요/수취 원화": (
                        item.fx_krw_outflow
                        if stage2_result.trade_type == "IMPORT"
                        else item.fx_krw_inflow
                    ),
                    "기준 대비 불리한 손실": item.loss_vs_base,
                    "종료잔고": item.ending_cash,
                    "최대 buffer 부족": item.maximum_buffer_shortfall,
                    "현금 적자": item.cash_deficit,
                    "신용 후 부족": item.post_credit_shortfall,
                }
                for item in stage2_result.scenario_results
            ]
            st.dataframe(
                scenario_rows,
                width="stretch",
                hide_index=True,
            )
            st.caption(
                "{} · 비교 기준: {}".format(
                    status_badge(
                        stage2_result.scenario_results[0].scenario_kind
                    ),
                    stage2_result.comparison_basis,
                )
            )
            ledger_rows = []
            for scenario in stage2_result.scenario_results:
                for item in scenario.ledger:
                    ledger_rows.append(
                        {
                            "date": item.date,
                            "scenario": item.scenario,
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
                    "차트의 float 변환은 표시 전용이며 원 계산과 JSON은 "
                    "Decimal 문자열입니다."
                )
            if stage2_result.warnings:
                for warning in stage2_result.warnings:
                    st.warning(warning)
            download_cols = st.columns(2)
            with download_cols[0]:
                json_download(
                    label="Stage 2 입력 JSON",
                    value=st.session_state["stage2_input"],
                    filename="stage2_input.json",
                    key="download_stage2_input",
                )
            with download_cols[1]:
                json_download(
                    label="Stage 2 결과 JSON",
                    value=stage2_result,
                    filename="stage2_result.json",
                    key="download_stage2",
                )

with stage3_tab:
    st.subheader("검토 가능한 헤지 전략 후보")
    stage2_result = _model_from_state("stage2_result", Stage2Result)
    if stage2_result is None:
        st.warning("먼저 Stage 2 계산을 완료하세요.")
    else:
        option_cols = st.columns(2)
        grid = option_cols[0].selectbox(
            "Grid 단위",
            [10, 5],
            key="stage3_grid_widget",
        )
        stability = option_cols[1].slider(
            "안정성 선호",
            min_value=0.0,
            max_value=1.0,
            value=0.7,
            step=0.1,
            key="stage3_stability_widget",
        )
        if st.button(
            "상위 3개 후보 계산",
            type="primary",
            key="optimize_stage3",
        ):
            workflow = _workflow_from_state()
            if workflow is None:
                st.error("Workflow 상태가 없습니다. Stage 0부터 다시 실행하세요.")
                st.stop()
            workflow = orchestrator.run_hedge(
                workflow,
                grid_step_percent=int(grid),
                stability_preference=format(Decimal(str(stability)), "f"),
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
            st.info(
                "최적 자문이 아니라 입력 가정 아래 계산된 후보입니다. "
                "실제 계약 전 은행·보험기관 상담이 필요합니다."
            )
            cards = st.columns(3)
            for card, candidate in zip(
                cards,
                stage3_result.candidates,
            ):
                with card:
                    st.markdown(
                        "<div class='status-card'><b>#{} 후보</b><br>"
                        "선물환 {} · 분할환전 {} · 미헤지 {}<br>"
                        "보유외화 반영 {}<br>최악손실 {}원<br>"
                        "유동성 영향 {}원 · 비용가정 {}원<br>"
                        "손실한도 초과 {} · 제약 {}</div>".format(
                            candidate.rank,
                            candidate.forward_ratio,
                            candidate.staged_conversion_ratio,
                            candidate.unhedged_ratio,
                            candidate.held_fx_ratio,
                            candidate.worst_case_loss,
                            candidate.liquidity_impact,
                            candidate.assumed_hedge_cost,
                            (
                                "예"
                                if candidate.acceptable_loss_exceeded
                                else "아니오"
                            ),
                            (
                                "충족"
                                if candidate.constraints_satisfied
                                else "미충족"
                            ),
                        ),
                        unsafe_allow_html=True,
                    )
                    st.caption(candidate.rationale)
            json_download(
                label="Stage 3 후보 JSON",
                value=stage3_result,
                filename="stage3_candidates.json",
                key="download_stage3",
            )

with stage4_tab:
    st.subheader("공식 자료 기반 상품·제도 후보")
    stage2_result = _model_from_state("stage2_result", Stage2Result)
    stage3_result = _model_from_state("stage3_result", Stage3Result)
    if stage2_result is None or stage3_result is None:
        st.warning("Stage 2와 Stage 3 결과가 필요합니다.")
    else:
        default_query = " ".join(
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
        query = st.text_input(
            "검색 유형",
            value=default_query,
            key="stage4_query_widget",
        )
        search_modes = ["OFFLINE_KB"]
        if settings.enable_official_web_search:
            search_modes.append("OFFICIAL_WEB_SEARCH")
        search_mode = st.radio(
            "검색 모드",
            search_modes,
            horizontal=True,
            key="stage4_search_mode_widget",
        )
        if st.button(
            "공식 후보 검색",
            type="primary",
            key="search_stage4",
        ):
            try:
                workflow = _workflow_from_state()
                if workflow is None:
                    raise RuntimeError(
                        "Workflow 상태가 없습니다. Stage 0부터 다시 실행하세요."
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
                st.warning("공식 allowlist에서 확인 가능한 후보가 없습니다.")
            for candidate in stage4_result.candidates:
                with st.expander(
                    "{} · {}".format(
                        candidate.institution,
                        candidate.name,
                    )
                ):
                    st.write(candidate.summary)
                    st.write(
                        "전략 연결: {}".format(
                            candidate.strategy_connection_reason
                        )
                    )
                    st.write(
                        "대상: {} / 주요 조건: {}".format(
                            ", ".join(candidate.target_customers),
                            ", ".join(candidate.key_conditions),
                        )
                    )
                    st.write(
                        "필요 서류: {}".format(
                            ", ".join(candidate.required_documents)
                        )
                    )
                    st.write(
                        "상태: **후보 · 상담 필요** / 자격: **{}**".format(
                            candidate.eligibility
                        )
                    )
                    st.markdown(
                        "[공식 출처 · {}]({}) · 확인일 {}".format(
                            candidate.source.title,
                            candidate.source.url,
                            candidate.source.verified_at,
                        )
                    )
            st.info(
                "승인·한도·금리·자격은 확정하지 않습니다. 담당 기관 또는 "
                "거래은행에 인간 상담으로 연결하세요."
            )
            json_download(
                label="Stage 4 후보 JSON",
                value=stage4_result,
                filename="stage4_products.json",
                key="download_stage4",
            )

with stage5_tab:
    st.subheader("설명 가능한 보고서")
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
    if not all_ready:
        st.warning("Stage 0~4 결과가 모두 필요합니다.")
    else:
        if st.button(
            "보고서 생성·critic 검수",
            type="primary",
            key="generate_report",
        ):
            workflow = _workflow_from_state()
            if workflow is None:
                st.error("Workflow 상태가 없습니다. Stage 0부터 다시 실행하세요.")
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
            st.markdown(report_result.markdown)
            report_cols = st.columns(2)
            with report_cols[0]:
                st.download_button(
                    "Markdown 보고서",
                    data=report_result.markdown,
                    file_name="fx_cashflow_risk_report.md",
                    mime="text/markdown",
                    key="download_report_md",
                )
            with report_cols[1]:
                json_download(
                    label="근거 포함 JSON 보고서",
                    value=report_result.report_json,
                    filename="fx_cashflow_risk_report.json",
                    key="download_report_json",
                )

workflow_trace_state = _workflow_from_state()
if workflow_trace_state is not None:
    render_workflow_trace(workflow_trace_state)

st.divider()
st.caption(
    "AI는 문서 추출·설명에만 사용합니다. 날짜 파생, 규칙 검증, 금융 계산, "
    "제약 판정은 일반 코드가 수행하며 상품 결과는 후보이지 금융 자문이 아닙니다."
)
