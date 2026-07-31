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
    CashflowValidationError,
    Stage2FormInput,
    build_validated_stage2_input_from_form,
    classify_cashflow_error,
    recommended_stage2_as_of_date,
    stage2_form_error_context,
    stage2_form_fingerprint,
    validate_stage2_as_of_date,
)
from src.application.registered_document_service import (
    PRESENTATION_FIXTURE_ID,
    extract_registered_document,
    presentation_document,
)
from src.application.consultation_service import build_decision_support
from src.application.integration_readiness_service import (
    build_integration_readiness_report,
)
from src.application.kb_macro_hedge_service import (
    evaluate_kb_macro_hedge_reference,
    run_kb_macro_hedge_for_confirmed_trade,
)
from src.application.country_environment_service import (
    build_country_environment_input,
)
from src.application.official_candidate_service import (
    build_official_candidate_query,
    shortlist_official_candidates,
)
from src.application.trade_risk_service import build_trade_risk_prefill
from src.config import Settings
from src.consultation.packet import rationale_display_text
from src.consultation.trade_settlement_risk import (
    assess_trade_settlement_risk,
    create_trade_risk_confirmation,
)
from src.country_environment.assessment import (
    assess_country_trade_environment,
    country_environment_trace,
)
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
    ConsultationPriorityView,
    ConsultationTopic,
    DecisionSupportResult,
    InstallmentPaymentStatus,
    RiskAssessment,
)
from src.domain.country_environment_models import (
    CountryTradeEnvironmentAssessment,
)
from src.domain.confirmed_transaction_models import (
    ConfirmedTransactionSnapshot,
)
from src.domain.integration_readiness_models import (
    IntegrationReadinessReport,
)
from src.domain.kb_macro_hedge_models import (
    KbMacroHedgeExecutionConstraints,
    KbMacroHedgeReferenceResult,
)
from src.domain.product_models import (
    OfficialCandidateShortlist,
    Stage4Result,
)
from src.domain.report_models import ReportResult
from src.domain.stage1_models import Stage1LoadResult
from src.domain.stage1_web_models import MarketIntegrationResult
from src.domain.stage2_models import (
    CashflowErrorDetail,
    Stage2Input,
    Stage2Result,
)
from src.domain.stage3_models import Stage3Assumptions, Stage3Result
from src.domain.trade_risk_models import (
    ProtectionMechanism,
    TradeRiskConfirmationRecord,
    TradeSettlementRiskAssessment,
    TradeSettlementRiskInput,
)
from src.security.upload_guard import validate_upload
from src.stage2.binding import (
    confirmed_analysis_due_date_from_document_input,
    confirmed_trade_from_document_input,
    document_input_from_confirmed_transaction,
)
from src.ui.components import (
    SCHEDULED_EXPOSURE_WARNING,
    amount_due_user_label,
    consultation_priority_reason_copy,
    consultation_rationale_label,
    consultation_status_label,
    decimal_text,
    evidence_rows,
    format_decimal_display,
    format_foreign,
    format_krw,
    format_ratio,
    json_download,
    optional_positive_integer,
    optional_text,
    render_validation,
    render_validation_summary,
    render_workflow_trace,
    status_badge,
)
from src.ui.presentation import (
    country_summary,
    no_feasible_reason_copy,
    priority_key_rationale,
    priority_risk_sentence,
    transaction_summary,
    world_bank_display,
)
from src.ui.state import (
    clear_confirmation_and_later,
    clear_downstream,
    clear_review_widgets,
    clear_trade_risk_and_related,
    input_signature,
    sync_input_signature,
)
from src.workflow.orchestrator import WorkflowOrchestrator
from src.workflow.state import WorkflowState
from validators import (
    apply_deterministic_review_state,
    build_stage0_output,
)


ROOT = Path(__file__).resolve().parent
SAMPLE_PATH = ROOT / "samples" / "sample_invoice.png"
DEMO_EXPORT_PATH = ROOT / "samples" / "demo_export_invoice.pdf"
DEMO_EXPORT_LABEL_PATH = (
    ROOT / "dataset" / "labels" / "kr_seller_export_012.json"
)
COUNTRY_DISPLAY_NAMES = {
    "BR": "브라질",
    "KR": "한국",
    "US": "미국",
}


def _model_from_state(key: str, model_class: Any) -> Optional[Any]:
    value = st.session_state.get(key)
    if value is None:
        return None
    return model_class.model_validate(value)


def _save_model(key: str, value: Any) -> None:
    st.session_state[key] = value.model_dump()


def _render_kb_macro_hedge_reference(
    result: KbMacroHedgeReferenceResult,
) -> None:
    status_copy = {
        "READY": "검증 완료",
        "REFERENCE_ONLY": "참고 전용",
        "VALIDATION_FAILED": "검증 실패",
        "UNSUPPORTED_EXPOSURE": "지원 범위 밖",
        "UPSTREAM_UNAVAILABLE": "외부 파일 사용 불가",
    }
    status = status_copy.get(result.status, result.status)
    if result.status in {"READY", "REFERENCE_ONLY"}:
        st.success(
            "{} · 기존 Stage 3와 분리된 외부 참고 결과입니다.".format(
                status
            )
        )
    else:
        st.warning(
            "{} · 외부 후보는 표시하지 않으며 기존 Stage 3 결과는 "
            "그대로 유지합니다.".format(status)
        )
    info_cols = st.columns(3)
    info_cols[0].metric("검증 상태", status)
    info_cols[1].metric(
        "가격 상태",
        (
            "목업 가격"
            if result.pricing_status == "MOCK"
            else (
                "목업 아님 · 출처 확인 필요"
                if result.pricing_status == "ACTUAL"
                else "확인 불가"
            )
        ),
    )
    info_cols[2].metric(
        "현재 거래 결속",
        (
            "확인"
            if (
                result.request is not None
                and result.request.binding_mode
                == "CURRENT_CONFIRMED_TRADE"
            )
            else "외부 fixture 자체 검증"
        ),
    )
    st.caption(
        "단일 USD 수입 지급 전용 · 실제 상품 추천, 가입 승인 또는 "
        "실행 지시가 아닙니다. 외부 후보는 Stage 4와 상담 리포트에 "
        "자동 전달되지 않습니다."
    )
    if result.request is not None:
        st.caption(
            "현재 외부 모델 입력 · 예정 지급액 {} · 보유 USD {} · "
            "기존 선물환 {} · 순노출 {} · 지급일 {}".format(
                format_foreign(result.request.amount_usd, "USD"),
                format_foreign(
                    result.request.existing_usd_cash,
                    "USD",
                ),
                format_foreign(
                    result.request.existing_forward_usd,
                    "USD",
                ),
                format_foreign(
                    result.request.net_exposure_usd,
                    "USD",
                ),
                result.request.payment_date,
            )
        )
    if result.provenance is not None:
        provenance = result.provenance
        st.caption(
            "실행 {} · producer commit {} · schema {} / {} · "
            "forecast SHA {} · hedge SHA {}".format(
                (
                    "고정 로컬 CLI"
                    if provenance.execution_method
                    == "PINNED_LOCAL_CLI"
                    else "사전 생성 파일"
                ),
                provenance.producer_commit_sha,
                provenance.forecast_schema_version,
                provenance.hedge_schema_version,
                provenance.forecast_sha256,
                provenance.hedge_sha256,
            )
        )
    if result.candidates:
        cards = st.columns(3)
        strategy_copy = {
            "forward_only": "선물환만",
            "forward_and_call_option": "선물환 + 달러 콜옵션",
            "call_option_only": "달러 콜옵션만",
            "unhedged": "무헤지",
        }
        for card, candidate in zip(cards, result.candidates):
            with card:
                st.markdown(
                    "#### 외부 참고안 {}".format(candidate.rank)
                )
                st.write(
                    strategy_copy.get(
                        candidate.strategy_type,
                        candidate.strategy_type,
                    )
                )
                st.write(
                    "선물환 {} · 콜옵션 {} · 무헤지 {}".format(
                        format_ratio(candidate.forward_ratio),
                        format_ratio(candidate.call_option_ratio),
                        format_ratio(candidate.unhedged_ratio),
                    )
                )
                st.write(
                    "선물환 {} · 콜옵션 {} · 미고정 {}".format(
                        format_foreign(
                            candidate.forward_notional_usd,
                            "USD",
                        ),
                        format_foreign(
                            candidate.call_option_notional_usd,
                            "USD",
                        ),
                        format_foreign(
                            candidate.unhedged_notional_usd,
                            "USD",
                        ),
                    )
                )
                st.write(
                    "옵션 quote {} · 프리미엄 {}".format(
                        candidate.option_id or "미사용",
                        format_krw(candidate.option_premium_krw),
                    )
                )
                st.caption(
                    "목적함수 {} · CVaR95 {}".format(
                        format_krw(candidate.objective_score_krw),
                        format_krw(candidate.cvar_95_cost_krw),
                    )
                )
    failed = [
        item for item in result.validation.checks if not item.passed
    ]
    if failed:
        with st.expander("외부 결과 검증 실패 항목", expanded=True):
            for item in failed:
                st.write(
                    "· {}{}: {}".format(
                        item.check,
                        (
                            " ({})".format(item.field)
                            if item.field
                            else ""
                        ),
                        item.detail,
                    )
                )
    if result.warnings:
        warning_copy = {
            "UPSTREAM_JSON_SCHEMAS_NOT_PROVIDED": (
                "upstream이 공식 request/response JSON Schema를 "
                "제공하지 않아 내부 필수계약으로 재검증했습니다."
            ),
            "UPSTREAM_CONTRACT_MANIFEST_NOT_PROVIDED": (
                "upstream manifest가 없어 파일 SHA를 실행 설정에서 "
                "고정했습니다."
            ),
            "PRODUCER_COMMIT_NOT_EMBEDDED_IN_RESPONSE": (
                "producer commit은 response 내장값이 아니라 실행 설정의 "
                "고정값입니다."
            ),
            "REQUEST_AND_FORECAST_HASHES_NOT_EMBEDDED_IN_RESPONSE": (
                "request/forecast SHA가 response에 내장되지 않아 "
                "KBaiAgent가 직접 계산했습니다."
            ),
            "UPSTREAM_RAW_NUMBERS_ORIGINATED_AS_FLOAT": (
                "upstream 숫자는 float 기반이며 KBaiAgent에서 "
                "Decimal(str(value))로 재검증했습니다."
            ),
            "CURRENT_TRADE_BINDING_NOT_CHECKED": (
                "현재 앱 거래와 대조하지 않은 외부 fixture 자체 "
                "검증입니다."
            ),
            "MOCK_QUOTES": "선물환·옵션 가격은 목업입니다.",
            "ACTUAL_QUOTE_PROVENANCE_NOT_VERIFIED": (
                "upstream이 목업 아님으로 표시했지만 은행 실제 견적 "
                "provenance는 별도 확인이 필요합니다."
            ),
            "PROTOTYPE_ONLY": "연구·대회용 prototype 결과입니다.",
            "PAYMENT_DATE_OUTSIDE_THREE_TRADING_DAYS": (
                "지급일이 forecast 기간과 3거래일 넘게 차이 납니다."
            ),
            "NOT_CONNECTED_TO_STAGE4_OR_STAGE5": (
                "공식 상품 후보와 최종 상담 리포트에는 연결하지 않습니다."
            ),
            "PINNED_LOCAL_CLI_EXECUTION": (
                "고정된 kb_macro_ai commit과 입력 SHA를 확인한 뒤 "
                "공식 로컬 CLI로 현재 거래를 계산했습니다."
            ),
            "TEMPORARY_RAW_OUTPUT_DELETED": (
                "임시 요청과 raw 결과는 검증 후 삭제하고 정규화된 "
                "참고 결과만 세션에 보관합니다."
            ),
            "INTERNAL_STAGE3_FALLBACK_REMAINS_ACTIVE": (
                "외부 실행 실패와 관계없이 기존 Stage 3 계산은 유지됩니다."
            ),
        }
        with st.expander("검증 경고와 적용 한계", expanded=False):
            for warning in result.warnings:
                st.write(
                    "· {}".format(warning_copy.get(warning, warning))
                )
    with st.expander("고급 · 정규화된 외부 참고 데이터", expanded=False):
        _advanced_downloads_title()
        json_download(
            label="외부 헤지 참고 검증 JSON",
            value=result,
            filename="kb_macro_hedge_reference.json",
            key="download_kb_macro_hedge_reference",
        )


def _render_integration_readiness(
    report: IntegrationReadinessReport,
) -> None:
    status_copy = {
        "READY": "준비 완료",
        "DEGRADED": "주의 필요",
        "BLOCKED": "설정 확인 필요",
        "DISABLED": "외부 헤지 꺼짐",
        "NOT_CHECKED": "미점검",
    }
    status = status_copy.get(report.status, report.status)
    if report.status == "READY":
        st.success("통합 연결 상태 · {}".format(status))
    elif report.status == "BLOCKED":
        st.error("통합 연결 상태 · {}".format(status))
    else:
        st.warning("통합 연결 상태 · {}".format(status))

    stage1 = report.stage1
    st.markdown("**환율 예측 · Stage 1**")
    st.caption(
        "상태 {} · provider {} · health {} · source {}".format(
            status_copy.get(stage1.status, stage1.status),
            stage1.configured_provider,
            stage1.health_status or "UNKNOWN",
            stage1.active_source or "NOT_CHECKED",
        )
    )
    st.caption(
        "예측일 {} · 시장데이터 {} · freshness {} · provider fallback "
        "{} · upstream partial fallback {}".format(
            stage1.prediction_date or "UNKNOWN",
            stage1.market_data_latest_date or "UNKNOWN",
            (
                "PASS"
                if stage1.forecast_fresh is True
                else "STALE"
                if stage1.forecast_fresh is False
                else "NOT_CHECKED"
            ),
            (
                "사용"
                if stage1.fallback_used is True
                else "미사용"
                if stage1.fallback_used is False
                else "미점검"
            ),
            (
                "사용"
                if stage1.partial_fallback_used is True
                else "미사용"
                if stage1.partial_fallback_used is False
                else "미점검"
            ),
        )
    )

    spot = report.spot
    st.markdown("**기준환율 출처**")
    st.caption(
        "상태 {} · 설정 {} · 실제 source {}".format(
            status_copy.get(spot.status, spot.status),
            spot.configured_provider,
            spot.active_source or spot.configured_source,
        )
    )
    st.caption(
        "자격증명 {} · 수동환율 {} · 이 점검의 외부 환율 호출 없음".format(
            "설정됨" if spot.credential_configured else "미설정",
            "설정됨" if spot.manual_rate_configured else "거래 입력 필요",
        )
    )

    macro = report.kb_macro_hedge
    st.markdown("**kb_macro_ai 외부 헤지 참고**")
    st.caption(
        "상태 {} · flag {} · mode {} · 현재 거래 {}".format(
            status_copy.get(macro.status, macro.status),
            "ON" if macro.feature_enabled else "OFF",
            macro.configured_mode,
            (
                "지원"
                if macro.exposure.supported is True
                else "지원 밖"
                if macro.exposure.supported is False
                else "거래 확정 후 점검"
            ),
        )
    )
    st.caption(macro.exposure.detail)
    st.caption(
        "producer commit · expected {} · actual {}".format(
            macro.expected_producer_commit_sha or "NOT_CONFIGURED",
            macro.actual_producer_commit_sha or "NOT_OBSERVED",
        )
    )
    for asset in macro.assets:
        st.caption(
            "{} SHA-256 · expected {} · actual {} · {}".format(
                asset.asset,
                asset.expected_sha256 or "NOT_CONFIGURED",
                asset.actual_sha256 or "NOT_OBSERVED",
                (
                    "MATCH"
                    if asset.sha256_matches is True
                    else "MISMATCH"
                    if asset.sha256_matches is False
                    else "NOT_CHECKED"
                ),
            )
        )
    st.caption(
        "API key 값은 표시하지 않습니다. 외부 헤지는 단일 USD 수입 지급 "
        "참고 전용이며 기존 Stage 3·공식 후보·상담 리포트를 변경하지 않습니다."
    )


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
    if value.trade_settlement_risk is not None:
        _save_model(
            "trade_risk_assessment",
            value.trade_settlement_risk,
        )
    if value.country_environment is not None:
        _save_model(
            "country_environment_assessment",
            value.country_environment,
        )
    st.session_state["consultation_topics"] = [
        item.model_dump() for item in value.consultation_topics
    ]
    if value.official_candidate_shortlist is not None:
        _save_model(
            "official_candidate_shortlist",
            value.official_candidate_shortlist,
        )
    else:
        st.session_state.pop(
            "official_candidate_shortlist",
            None,
        )
    st.session_state["installment_payment_statuses"] = [
        item.model_dump()
        for item in (
            value.consultation_packet.packet
            .installment_payment_statuses
        )
    ]
    _save_model("consultation_packet", value.consultation_packet)


def _consultation_topics_from_state() -> List[ConsultationTopic]:
    return [
        ConsultationTopic.model_validate(item)
        for item in st.session_state.get("consultation_topics", [])
    ]


def _installment_payment_statuses_from_state(
) -> List[InstallmentPaymentStatus]:
    return [
        InstallmentPaymentStatus.model_validate(item)
        for item in st.session_state.get(
            "installment_payment_statuses",
            [],
        )
    ]


def _render_priority_card(
    priority: ConsultationPriorityView,
    display_rationale: Optional[List[Tuple[str, str]]] = None,
) -> None:
    if display_rationale is None:
        display_rationale = [
            (
                consultation_rationale_label(item.label),
                (
                    consultation_status_label(item.value)
                    if item.unit == "STATUS"
                    else rationale_display_text(item)
                ),
            )
            for item in priority_key_rationale(priority)
        ]
    rationale_html = "".join(
        "<p><small>{}</small><strong>{}</strong></p>".format(
            escape(label),
            escape(display_value),
        )
        for label, display_value in display_rationale
    )
    st.markdown(
        "<div class='consultation-card'>"
        "<span class='rank'>{}</span><h4>{}</h4>"
        "<p>{}</p>{}"
        "<div class='decision'><small>상담에서 결정할 사항</small>"
        "<p>{}</p></div>"
        "<div class='decision'><small>다음 행동</small>"
        "<p>{}</p></div></div>".format(
            priority.rank,
            escape(priority.title),
            escape(
                consultation_priority_reason_copy(
                    priority_risk_sentence(priority)
                )
            ),
            rationale_html,
            escape(priority.expected_decision),
            escape(priority.next_action),
        ),
        unsafe_allow_html=True,
    )
    with st.expander("준비자료·질문·공식 후보", expanded=False):
        if priority.missing_information:
            st.warning(
                "아직 확인할 정보 · {}".format(
                    " · ".join(priority.missing_information)
                )
            )
        st.markdown("**준비자료**")
        for item in priority.preparation_documents:
            st.write("· {}".format(item))
        st.markdown("**은행에 물어볼 질문**")
        for item in priority.bank_questions:
            st.write("· {}".format(item))
        st.markdown("**공식 후보**")
        if priority.official_candidates:
            for candidate in priority.official_candidates:
                st.markdown(
                    "- [{} · {}]({}) · 확인일 {}  \n"
                    "  연결 이유: {}  \n"
                    "  eligibility=UNKNOWN · "
                    "approval=CONSULTATION_REQUIRED".format(
                        candidate.institution,
                        candidate.name,
                        candidate.source.url,
                        candidate.source.verified_at,
                        candidate.strategy_connection_reason,
                    )
                )
        else:
            st.info(
                "현재 검증된 공식 후보가 없습니다. 최신 상담 가능 "
                "구조는 KB 영업점 또는 기업금융·외환 상담에서 "
                "확인하세요."
            )


def _render_consultation_priorities(
    value: ConsultationPacketResult,
    *,
    key_prefix: str,
    stage2_result: Optional[Stage2Result] = None,
    show_download: bool = False,
) -> None:
    priorities = value.packet.consultation_priorities
    if not priorities:
        return
    st.markdown("### 먼저 확인할 상담")
    st.caption(
        "지금 은행과 확인할 순서입니다. 각 카드의 핵심 숫자와 결정사항을 "
        "먼저 보고, 준비자료와 질문은 필요할 때 펼쳐보세요."
    )
    st.caption(priorities[0].disclaimer)
    adverse_five = _five_percent_adverse_result(stage2_result)
    rationale_overrides: Dict[int, List[Tuple[str, str]]] = {}
    if adverse_five is not None:
        scenario_name = _scenario_label(
            adverse_five.scenario_name
        ).replace("환율 ", "")
        rationale_overrides[2] = [
            (
                amount_due_user_label(
                    value.packet.company_summary.trade_type
                ),
                _format_foreign_ui(
                    value.packet.company_summary.trade_amount_fx,
                    value.packet.company_summary.currency,
                ),
            ),
            (
                "{} 기준 대비 영향".format(scenario_name),
                format_krw(adverse_five.loss_vs_base),
            ),
            (
                "사용자 허용손실",
                _priority_rationale_text(
                    value,
                    ("사용자 허용손실",),
                ),
            ),
        ]
        rationale_overrides[3] = [
            (
                "스트레스 후 예상 현금",
                format_krw(adverse_five.ending_cash),
            ),
            (
                "목표 현금 버퍼",
                _priority_rationale_text(
                    value,
                    ("목표 buffer", "목표 현금 버퍼"),
                ),
            ),
            (
                "목표 현금 버퍼 부족",
                format_krw(
                    adverse_five.maximum_buffer_shortfall
                ),
            ),
        ]
    with st.container(key="consultation_top3"):
        columns = st.columns(len(priorities))
        for column, priority in zip(columns, priorities):
            with column:
                _render_priority_card(
                    priority,
                    display_rationale=rationale_overrides.get(
                        priority.rank
                    ),
                )
    if value.packet.other_consultation_topics:
        with st.expander("기타 확인사항", expanded=False):
            for topic in value.packet.other_consultation_topics:
                st.markdown("- **{}**: {}".format(
                    topic.title,
                    topic.explanation,
                ))
    if show_download:
        st.download_button(
            "상담 준비서 다운로드",
            data=value.markdown,
            file_name="kb_consultation_handoff.md",
            mime="text/markdown",
            key="{}_handoff_download".format(key_prefix),
            type="primary",
            width="stretch",
        )
        st.caption(
            "다운로드는 상담 준비자료 생성이며 실제 예약·RM 전송·신청 "
            "완료를 의미하지 않습니다."
        )


def _country_display(country: Optional[str]) -> str:
    if not country:
        return "확인 필요"
    return "{} ({})".format(
        COUNTRY_DISPLAY_NAMES.get(country, country),
        country,
    )


def _format_foreign_ui(value: Any, currency: str) -> str:
    formatted = format_decimal_display(value, decimal_places=2)
    if formatted.endswith(".00"):
        formatted = formatted[:-3]
    return "{} {}".format(currency or "통화 확인 필요", formatted)


def _priority_rationale_text(
    value: ConsultationPacketResult,
    labels: Tuple[str, ...],
) -> str:
    for priority in value.packet.consultation_priorities:
        for item in priority.numeric_rationale:
            if item.label in labels:
                return rationale_display_text(item)
    return "확인 필요"


def _render_transaction_overview(
    extraction: TradeDocumentExtraction,
    confirmed_transaction: Optional[ConfirmedTransactionSnapshot],
    consultation: Optional[ConsultationPacketResult],
) -> None:
    summary = transaction_summary(
        extraction,
        confirmed_transaction=confirmed_transaction,
        consultation=consultation,
    )
    currency = str(summary["currency"] or "")
    major_installment = summary["major_installment"]
    major_condition = (
        str(major_installment.get("condition") or "")
        if isinstance(major_installment, dict)
        else ""
    )
    major_label = (
        "잔금"
        if "balance" in major_condition.lower() or "잔금" in major_condition
        else "주요 회차"
    )
    major_value = (
        _format_foreign_ui(
            major_installment.get("amount") or "0",
            str(major_installment.get("currency") or currency),
        )
        if isinstance(major_installment, dict)
        else "확인 필요"
    )
    st.markdown("### 이 거래는 무엇인가요?")
    st.markdown(
        "<div class='summary-grid'>"
        "<div class='summary-item'><small>수출/수입</small><strong>{}</strong></div>"
        "<div class='summary-item'><small>우리 회사 역할</small><strong>{}</strong></div>"
        "<div class='summary-item wide'><small>거래 당사국</small><strong>{}</strong></div>"
        "<div class='summary-item'><small>통화</small><strong>{}</strong></div>"
        "<div class='summary-item'><small>{}</small><strong>{}</strong></div>"
        "<div class='summary-item'><small>최종 예정 결제일</small><strong>{}</strong></div>"
        "<div class='summary-item'><small>결제방식</small><strong>{}</strong></div>"
        "<div class='summary-item'><small>{}</small><strong>{}</strong></div>"
        "<div class='summary-item attention wide'><small>가장 중요한 확인사항</small>"
        "<strong>{}</strong></div></div>".format(
            escape(str(summary["trade_type_label"])),
            escape(str(summary["company_role_label"])),
            escape(str(summary["route_label"])),
            escape(currency or "확인 필요"),
            escape(amount_due_user_label(str(summary["trade_type"]))),
            escape(
                _format_foreign_ui(
                    summary["amount_due"] or "0",
                    currency,
                )
            ),
            escape(str(summary["due_date"] or "확인 필요")),
            escape(str(summary["payment_method"])),
            escape(major_label),
            escape(major_value),
            escape(str(summary["missing_information"])),
        ),
        unsafe_allow_html=True,
    )
    st.caption(SCHEDULED_EXPOSURE_WARNING)

    detail_snapshot = confirmed_transaction
    with st.expander("상세 거래정보", expanded=False):
        detail_columns = st.columns(3)
        detail_columns[0].write(
            "**문서번호**  \n{}".format(
                (
                    detail_snapshot.document_number
                    if detail_snapshot is not None
                    else extraction.document_number
                )
                or "확인 필요"
            )
        )
        detail_columns[1].write(
            "**문서유형**  \n{}".format(
                (
                    detail_snapshot.document_type
                    if detail_snapshot is not None
                    else extraction.document_type
                )
            )
        )
        detail_columns[2].write(
            "**계약 총액**  \n{}".format(
                _format_foreign_ui(
                    (
                        detail_snapshot.grand_total
                        if detail_snapshot is not None
                        else extraction.grand_total
                    )
                    or "0",
                    currency,
                )
            )
        )
        date_columns = st.columns(2)
        date_columns[0].write(
            "**계약일**  \n{}".format(
                (
                    detail_snapshot.contract_date
                    if detail_snapshot is not None
                    else extraction.contract_date
                )
                or "확인 필요"
            )
        )
        date_columns[1].write(
            "**선적일**  \n{}".format(
                (
                    detail_snapshot.shipment_date
                    if detail_snapshot is not None
                    else extraction.shipment_date
                )
                or "확인 필요"
            )
        )
        st.write(
            "**Incoterm**  \n{}".format(
                (
                    detail_snapshot.incoterm
                    if detail_snapshot is not None
                    else extraction.incoterm
                )
                or "확인 필요"
            )
        )
        st.write(
            "**결제조건 원문**  \n{}".format(
                (
                    detail_snapshot.payment_terms
                    if detail_snapshot is not None
                    else extraction.payment_terms
                )
                or "확인 필요"
            )
        )
        if summary["installments"]:
            st.markdown("**분할결제 전체 일정**")
            st.dataframe(
                [
                    {
                        "회차": row.get("sequence"),
                        "예정 금액": _format_foreign_ui(
                            row.get("amount") or "0",
                            str(row.get("currency") or currency),
                        ),
                        "예정일": row.get("due_date") or "조건 확인",
                        "조건": row.get("condition") or "확인 필요",
                    }
                    for row in summary["installments"]
                ],
                width="stretch",
                hide_index=True,
            )
        rows = evidence_rows(extraction)
        st.markdown("**원문 근거**")
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.warning("원문 근거가 없어 거래 확정 전 직접 대조가 필요합니다.")
        st.caption(
            "결제일 source path · {}".format(summary["source_path"])
        )
        if detail_snapshot is not None:
            st.caption(
                "확정 입력 fingerprint · {}".format(
                    detail_snapshot.input_fingerprint
                )
            )


def _render_financial_overview(
    value: ConsultationPacketResult,
    stage2_result: Optional[Stage2Result] = None,
) -> None:
    packet = value.packet
    trade_type = packet.company_summary.trade_type
    adverse_five = _five_percent_adverse_result(stage2_result)
    if adverse_five is not None:
        scenario_label = _scenario_label(adverse_five.scenario_name)
        loss_value = adverse_five.loss_vs_base
        cash_after = adverse_five.ending_cash
        buffer_shortfall = adverse_five.maximum_buffer_shortfall
        cash_deficit = adverse_five.cash_deficit
        payment_gap = adverse_five.post_credit_shortfall
        loss_limit_exceeded = adverse_five.acceptable_loss_exceeded
    else:
        scenario_label = next(
            (
                item.label.split()[0]
                for priority in packet.consultation_priorities
                for item in priority.numeric_rationale
                if "%" in item.label
                and ("수취" in item.label or "지급" in item.label)
            ),
            "불리한 환율",
        )
        loss_value = (
            packet.risk_summary.additional_cost_or_receipt_loss_krw
        )
        cash_after = packet.risk_summary.cash_after_settlement_krw
        buffer_shortfall = packet.risk_summary.buffer_shortfall_krw
        cash_deficit = packet.risk_summary.cash_deficit_krw
        payment_gap = packet.risk_summary.payment_gap_krw
        loss_limit_exceeded = (
            "LOSS_LIMIT_EXCEEDED"
            in packet.risk_summary.risk_codes
        )
    if (
        scenario_label != "불리한 환율"
        and not scenario_label.startswith("환율 ")
    ):
        scenario_label = "환율 {}".format(scenario_label)
    loss_subject = (
        "원화 지급액"
        if trade_type == "IMPORT"
        else "원화 수취액"
    )
    loss_verb = "증가" if trade_type == "IMPORT" else "감소"
    allowed_loss = _priority_rationale_text(
        value,
        ("사용자 허용손실",),
    )
    loss_limit_copy = (
        "허용손실 {} 초과".format(allowed_loss)
        if loss_limit_exceeded
        else "허용손실 {} 이내".format(allowed_loss)
    )
    target_buffer = _priority_rationale_text(
        value,
        ("목표 buffer", "목표 현금 버퍼"),
    )
    balance_amount = _priority_rationale_text(
        value,
        ("잔금 예정",),
    )
    payment_method = _priority_rationale_text(
        value,
        ("결제방식",),
    )
    protection_needs_review = bool(
        packet.trade_settlement_risk is not None
        and any(
            item
            in {
                "RECEIVABLE_PROTECTION_REVIEW",
                "ADVANCE_PAYMENT_PROTECTION_REVIEW",
                "DOCUMENTARY_CREDIT_TERMS_REVIEW",
            }
            for item in packet.trade_settlement_risk.review_needs
        )
    )
    protection_copy = (
        "현재 거래에 적용되는 보호수단 확인 필요"
        if protection_needs_review
        else "확인된 보호수단과 적용범위를 상담에서 재확인"
    )
    st.markdown("### 이번 거래의 핵심 결과")
    st.caption(
        "{} {} · 상대국 {} · 결제 예정일 {}".format(
            "수입" if trade_type == "IMPORT" else "수출",
            packet.company_summary.currency,
            _country_display(
                packet.company_summary.counterparty_country
            ),
            packet.company_summary.settlement_date,
        )
    )
    st.markdown(
        "<div class='result-grid'>"
        "<div class='impact-card warning'><small>카드 1 · 환율 영향</small>"
        "<strong>{} 시 {} {} {}</strong>"
        "<p>{}</p></div>"
        "<div class='impact-card warning'><small>카드 2 · 현금 방어선</small>"
        "<strong>스트레스 후 예상 현금 {}</strong>"
        "<p>목표 버퍼 {} · 버퍼 부족 {}</p>"
        "<p>현금 적자 {} · 지급 또는 post-credit 부족 {}</p></div>"
        "<div class='impact-card safe'><small>카드 3 · {}</small>"
        "<strong>{}</strong><p>{}</p><p>{}</p></div>"
        "</div>".format(
            escape(scenario_label),
            escape(loss_subject),
            escape(format_krw(loss_value)),
            escape(loss_verb),
            escape(loss_limit_copy),
            escape(format_krw(cash_after)),
            escape(target_buffer),
            escape(format_krw(buffer_shortfall)),
            escape(format_krw(cash_deficit)),
            escape(format_krw(payment_gap)),
            "회수 위험" if trade_type == "EXPORT" else "결제 위험",
            escape(balance_amount),
            escape(payment_method),
            escape(protection_copy),
        ),
        unsafe_allow_html=True,
    )
    with st.expander("결과 해석 기준", expanded=False):
        st.caption(SCHEDULED_EXPOSURE_WARNING)
        st.caption(
            "목표 현금 버퍼 부족은 지급불능 또는 필요 대출금이 아닙니다. "
            "현금 적자와 지급/post-credit 부족을 함께 확인해야 합니다."
        )


def _render_financial_evidence(
    *,
    stage1_load: Stage1LoadResult,
    stage2_result: Stage2Result,
    market_integration: Optional[MarketIntegrationResult],
    risk_assessment: Optional[RiskAssessment],
) -> None:
    scenarios = stage1_load.scenario_set
    with st.expander(
        "환율 분석 근거 및 데이터 품질",
        expanded=False,
    ):
        st.markdown("#### 환율 가정과 출처")
        st.caption(
            "{} · 통화 {} · 결제 예정일 {} · 적용 규칙 {}".format(
                stage1_load.source,
                scenarios.currency,
                scenarios.target_date,
                scenarios.application_rule,
            )
        )
        base_point = next(
            (item for item in scenarios.scenarios if item.is_base),
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
                    "출처 성격": item.source_kind,
                }
            )
        st.dataframe(scenario_rows, width="stretch", hide_index=True)
        if market_integration is not None:
            quote = market_integration.spot_quote
            st.caption(
                "기준환율 {}원 · rate type {} · source {}".format(
                    format_decimal_display(quote.rate, 2),
                    quote.rate_type,
                    quote.source,
                )
            )
            forecast_load = market_integration.forecast_load
            if forecast_load is not None:
                forecast = forecast_load.forecast
                st.write(forecast.market_context.summary)
                st.caption(
                    "모델 score는 발생확률이 아니며 q90은 예측분포의 "
                    "경로위험 분위수입니다. 검색 오류 지역 · {}".format(
                        ", ".join(forecast.market_context.query_errors)
                        or "없음"
                    )
                )
                if forecast.market_context.news:
                    st.dataframe(
                        [
                            {
                                "지역": item.region,
                                "범주": item.category,
                                "요약": item.summary,
                                "분석 신뢰": format_ratio(
                                    item.analysis_confidence
                                ),
                            }
                            for item in forecast.market_context.news
                        ],
                        width="stretch",
                        hide_index=True,
                    )
        if stage1_load.warnings:
            st.markdown("**데이터 품질 경고**")
            for warning in stage1_load.warnings:
                st.warning(warning)

        st.divider()
        st.markdown("#### 환율 구간별 현금흐름")
        stage2_rows = [
            {
                "환율 구간": _scenario_label(item.scenario_name),
                "적용 환율": "{}원".format(
                    format_decimal_display(item.applied_rate, 2)
                ),
                "기준 대비 영향": format_krw(item.loss_vs_base),
                "결제 후 잔고": format_krw(item.ending_cash),
                "운영자금 부족": format_krw(
                    item.maximum_buffer_shortfall
                ),
                "현금 적자": format_krw(item.cash_deficit),
                "지급/post-credit 부족": format_krw(
                    item.post_credit_shortfall
                ),
            }
            for item in stage2_result.scenario_results
        ]
        st.dataframe(stage2_rows, width="stretch", hide_index=True)
        ledger_rows = []
        for scenario in stage2_result.scenario_results:
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
        for warning in stage2_result.warnings:
            st.warning(warning)

        if risk_assessment is not None:
            st.divider()
            st.markdown("#### 위험 판정 근거")
            finding_labels = {
                "FX_COST_RISK": "환율 상승 시 수입 결제비용 증가",
                "FX_RECEIPT_RISK": "환율 하락 시 수출대금 원화 수취 감소",
                "LOSS_LIMIT_EXCEEDED": "입력한 손실한도 초과",
                "LIQUIDITY_BUFFER_RISK": "최소 운영자금 방어선 미달",
                "NEGATIVE_CASH_RISK": "현금 잔고 음수",
                "PAYMENT_CAPACITY_RISK": "현금·대출한도 반영 후 지급 부족",
                "TIMING_MISMATCH_RISK": "현금 유입·지급 시점 불일치",
                "DOCUMENT_INFORMATION_GAP": "거래·자금 정보 확인 필요",
            }
            st.dataframe(
                [
                    {
                        "위험 원인": finding_labels.get(
                            item.risk_code,
                            item.risk_code,
                        ),
                        "시나리오": item.scenario_id or "공통",
                        "발생값": (
                            format_krw(item.trigger_value)
                            if item.unit == "KRW"
                            else item.trigger_value
                        ),
                        "기준값": (
                            format_krw(item.threshold)
                            if item.unit == "KRW"
                            and item.threshold is not None
                            else item.threshold or "-"
                        ),
                        "중요도": item.severity,
                    }
                    for item in risk_assessment.findings
                ],
                width="stretch",
                hide_index=True,
            )

        st.divider()
        st.markdown("#### 계산 입력과 원본 데이터")
        download_columns = st.columns(3)
        with download_columns[0]:
            json_download(
                label="환율 시나리오 JSON",
                value=scenarios,
                filename="stage1_normalized.json",
                key="download_stage1_results",
            )
        stage2_input = _model_from_state("stage2_input", Stage2Input)
        if stage2_input is not None:
            with download_columns[1]:
                json_download(
                    label="현금 계산 입력 JSON",
                    value=stage2_input,
                    filename="stage2_input.json",
                    key="download_stage2_input_results",
                )
        with download_columns[2]:
            json_download(
                label="현금 계산 결과 JSON",
                value=stage2_result,
                filename="stage2_result.json",
                key="download_stage2_results",
            )


def _render_official_sources_body(
    value: ConsultationPacketResult,
) -> None:
    shortlist = value.packet.official_candidate_shortlist
    if shortlist is None or not shortlist.candidates:
        st.info(
            "현재 검증된 공식 후보가 없습니다. 최신 상담 가능 구조는 "
            "KB 영업점 또는 기업금융·외환 상담에서 확인하세요."
        )
        return
    for candidate in shortlist.candidates:
        st.markdown(
            "- [{} · {}]({}) · 자료 확인일 {}  \n"
            "  eligibility=UNKNOWN · "
            "approval=CONSULTATION_REQUIRED".format(
                candidate.institution,
                candidate.name,
                candidate.source.url,
                candidate.source.verified_at,
            )
        )
    st.caption(
        "전체 상담 준비서의 공식 후보는 고유 후보 기준 최대 3개이며, "
        "가입 자격과 승인 여부는 사람 상담에서 확인합니다."
    )


def _workflow_from_state() -> Optional[WorkflowState]:
    value = st.session_state.get("workflow_state")
    if value is None:
        return None
    return WorkflowState.model_validate(value)


def _save_workflow(value: WorkflowState) -> None:
    _save_model("workflow_state", value)
    if value.confirmed_transaction is not None:
        _save_model(
            "confirmed_transaction",
            value.confirmed_transaction,
        )
    else:
        st.session_state.pop("confirmed_transaction", None)


def _render_cashflow_error(detail: CashflowErrorDetail) -> None:
    st.error(detail.user_message)
    with st.expander("오류 기술 정보", expanded=False):
        st.write("error code: `{}`".format(detail.code))
        st.write("stage: `{}`".format(detail.stage))
        st.write(
            "input fingerprint: `{}`".format(
                detail.input_fingerprint or "UNKNOWN"
            )
        )
        st.write("used due_date: `{}`".format(detail.due_date or "UNKNOWN"))
        st.write(
            "cashflow base date: `{}`".format(
                detail.cashflow_base_date or "UNKNOWN"
            )
        )
        st.write(
            "field path: `{}`".format(detail.field_path or "UNKNOWN")
        )
        st.write(
            "offending value: `{}`".format(
                detail.offending_value or "UNKNOWN"
            )
        )
        st.write(
            "technical message: `{}`".format(
                detail.technical_message or "UNKNOWN"
            )
        )


def _persist_cashflow_failure(detail: CashflowErrorDetail) -> None:
    _save_model("cashflow_error", detail)
    workflow = _workflow_from_state()
    if workflow is None:
        return
    existing = workflow.cashflow_error
    if (
        existing is not None
        and existing.code == detail.code
        and existing.input_fingerprint == detail.input_fingerprint
    ):
        _save_workflow(workflow)
        return
    workflow = orchestrator.record_cashflow_failure(workflow, detail)
    _save_workflow(workflow)


def _rebuild_consultation_with_payment_statuses(
    statuses: List[InstallmentPaymentStatus],
) -> None:
    workflow = _workflow_from_state()
    extraction = _model_from_state(
        "extraction",
        TradeDocumentExtraction,
    )
    confirmation = _model_from_state(
        "confirmation",
        ConfirmationRecord,
    )
    stage1_load = _model_from_state(
        "stage1_load",
        Stage1LoadResult,
    )
    stage2_input = _model_from_state("stage2_input", Stage2Input)
    stage2_result = _model_from_state("stage2_result", Stage2Result)
    if (
        workflow is None
        or extraction is None
        or confirmation is None
        or stage1_load is None
        or stage2_input is None
        or stage2_result is None
    ):
        raise ValueError(
            "입금 확인을 반영할 확정 거래와 금융분석 결과가 없습니다."
        )
    decision_support = build_decision_support(
        case_id=workflow.case_id,
        extraction=extraction,
        confirmation=confirmation,
        stage1=stage1_load.scenario_set,
        stage2_input=stage2_input,
        stage2_result=stage2_result,
        trade_settlement_risk=_model_from_state(
            "trade_risk_assessment",
            TradeSettlementRiskAssessment,
        ),
        country_environment=_model_from_state(
            "country_environment_assessment",
            CountryTradeEnvironmentAssessment,
        ),
        official_candidate_shortlist=_model_from_state(
            "official_candidate_shortlist",
            OfficialCandidateShortlist,
        ),
        installment_payment_statuses=statuses,
        missing_information=list(
            extraction.missing_required_fields
        ),
        confirmed_transaction=workflow.confirmed_transaction,
    )
    _save_decision_support(decision_support)
    clear_downstream(st.session_state, 5)


def _demo_fixture(
    company_role: str,
) -> Tuple[Path, str, TradeDocumentExtraction]:
    if company_role == "SELLER":
        extraction = TradeDocumentExtraction.model_validate_json(
            DEMO_EXPORT_LABEL_PATH.read_text(encoding="utf-8")
        )
        return DEMO_EXPORT_PATH, "application/pdf", extraction
    return SAMPLE_PATH, "image/png", sample_extraction("BUYER")


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
    document_input: Optional[Dict[str, Any]] = None,
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
        "cashflows": [],
        "revenue_reduction": "0",
        "revenue_delay": 0,
        "cost_increase": "0",
    }
    if value is None:
        if document_input is not None:
            recommended_as_of = recommended_stage2_as_of_date(
                document_input
            )
            defaults["as_of"] = recommended_as_of
            defaults["same_flow_date"] = recommended_as_of
            trade = document_input.get("trade", {})
            trade_type = (
                trade.get("trade_type")
                if isinstance(trade, dict)
                else None
            )
            if trade_type == "EXPORT":
                defaults["usable_fx"] = "0"
                defaults["same_flow_direction"] = "OUTFLOW"
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
            "usable_fx": (
                value.non_applicable_inputs.get("usable_fx_balance")
                or _decimal_total(
                    [
                        exposure.usable_fx_balance
                        for exposure in value.exposures
                    ]
                )
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


def _trade_risk_form_defaults(
    *,
    extraction: TradeDocumentExtraction,
    confirmation: Optional[TradeRiskConfirmationRecord],
) -> Dict[str, Any]:
    if confirmation is None:
        prefill = build_trade_risk_prefill(extraction)
        ratio = prefill.advance_payment_ratio
        return {
            "relationship": "UNKNOWN",
            "advance_status": (
                "UNKNOWN"
                if ratio is None
                else "NONE_CONFIRMED"
                if Decimal(ratio) == 0
                else "RATIO_CONFIRMED"
            ),
            "advance_percent": (
                float(Decimal(ratio) * Decimal("100"))
                if ratio is not None
                else 0.0
            ),
            "balance_method": prefill.balance_payment_method,
            "term_basis": prefill.payment_term_basis,
            "term_days": prefill.payment_term_days or 0,
            "protection_status": "UNKNOWN",
            "protection_types": [],
            "protection_applicability": "PRESENT_SCOPE_UNVERIFIED",
        }

    confirmed = confirmation.confirmed_input
    ratio = confirmed.advance_payment_ratio
    applicability_values = {
        item.applicability_status
        for item in confirmed.protection_mechanisms
    }
    return {
        "relationship": confirmed.counterparty_relationship,
        "advance_status": (
            "UNKNOWN"
            if ratio is None
            else "NONE_CONFIRMED"
            if Decimal(ratio) == 0
            else "RATIO_CONFIRMED"
        ),
        "advance_percent": (
            float(Decimal(ratio) * Decimal("100"))
            if ratio is not None
            else 0.0
        ),
        "balance_method": confirmed.balance_payment_method,
        "term_basis": confirmed.payment_term_basis,
        "term_days": confirmed.payment_term_days or 0,
        "protection_status": confirmed.protection_information_status,
        "protection_types": [
            item.protection_type
            for item in confirmed.protection_mechanisms
        ],
        "protection_applicability": (
            "CONFIRMED_APPLICABLE"
            if applicability_values == {"CONFIRMED_APPLICABLE"}
            else "PRESENT_SCOPE_UNVERIFIED"
        ),
    }


def _trade_risk_ratio(
    *,
    status: str,
    percent: float,
) -> Optional[str]:
    if status == "UNKNOWN":
        return None
    if status == "NONE_CONFIRMED":
        return "0"
    ratio = Decimal(str(percent)) / Decimal("100")
    if ratio == 0:
        return "0"
    if ratio == 1:
        return "1"
    return format(ratio.normalize(), "f")


def _trade_risk_priority_copy(
    value: TradeSettlementRiskAssessment,
) -> Tuple[str, str, str]:
    mapping = {
        "HIGH_REVIEW": (
            "danger",
            "우선 검토 필요",
            "보호수단과 계약조건을 거래 진행 전에 먼저 확인하세요.",
        ),
        "ELEVATED_REVIEW": (
            "warning",
            "추가 검토 필요",
            "확인된 위험 신호가 있어 계약조건 보완 검토가 필요합니다.",
        ),
        "STANDARD_REVIEW": (
            "safe",
            "일반 검토",
            "확인된 정보에서는 우선 검토를 높일 조합이 발견되지 않았습니다.",
        ),
        "UNKNOWN": (
            "warning",
            "정보 확인 필요",
            "미확인 정보가 있어 검토 우선도를 아직 정할 수 없습니다.",
        ),
    }
    return mapping[value.review_priority]


def _render_country_environment_section(
    assessment: CountryTradeEnvironmentAssessment,
) -> None:
    summary = country_summary(assessment)
    tone = (
        "danger"
        if assessment.review_priority == "HIGH_REVIEW"
        else "warning"
        if assessment.review_priority
        in {"ELEVATED_REVIEW", "INSUFFICIENT_INFORMATION"}
        else "safe"
    )
    headline = (
        " · ".join(summary["review_needs"])
        if summary["review_needs"]
        else "현재 확인된 공식 자료에서 추가 우선 경고가 없습니다."
    )
    st.markdown("### 국가·무역환경 검토")
    st.markdown(
        "<div class='risk-banner {}'><div class='signal'>{}</div>"
        "<div><strong>{}</strong><p>{}</p></div>"
        "<div class='detail'>{}</div></div>".format(
            tone,
            escape(str(summary["review_label"])),
            escape(headline),
            escape(str(summary["country"])),
            escape(
                "공식 자료 확인일 {}".format(summary["verified_at"])
            ),
        ),
        unsafe_allow_html=True,
    )
    st.caption(
        "국가 신용등급·부도확률·은행 승인등급이 아닙니다. 공식 자료는 "
        "상담 전 확인사항만 보완하며 환헤지 비율과 현금흐름을 바꾸지 않습니다."
    )

    references = {
        item.source_record_id: item
        for item in assessment.official_source_references
    }
    oecd = assessment.oecd_payment_transfer
    with st.expander("거래국 환경 자세히 보기", expanded=False):
        st.markdown("#### OECD 결제·송금 환경")
        if oecd.status == "CLASSIFIED":
            st.write(
                "OECD 공식 원자료 분류: {} · 자체 국가등급 아님".format(
                    oecd.raw_classification
                )
            )
        elif oecd.status == "HIGH_INCOME_OECD_UNCLASSIFIED":
            st.write(
                "고소득 OECD 회원국 미분류 · 0 또는 낮은 위험으로 "
                "변환하지 않음"
            )
        else:
            st.warning("검증된 OECD 원자료를 확인할 수 없습니다.")
        st.caption(
            "기준일 {} · {}".format(
                oecd.as_of_date,
                oecd.interpretation,
            )
        )
        st.caption("한계: {}".format(oecd.limitations))
        reference = references.get(oecd.source_record_id or "")
        if reference is not None:
            st.markdown(
                "[{}]({}) · 관측기간 {} · 검증일 {}".format(
                    escape(reference.source_title),
                    escape(reference.official_url),
                    escape(reference.observation_period),
                    escape(reference.verified_at),
                )
            )
        st.divider()
        st.markdown("#### World Bank 거시환경")
        if not assessment.world_bank_macro_environment.observations:
            st.warning("검증된 World Bank 관측값이 없습니다.")
        for observation in (
            assessment.world_bank_macro_environment.observations
        ):
            reference = references.get(observation.source_record_id)
            st.markdown(
                "**{}**".format(
                    escape(
                        world_bank_display(
                            observation.indicator_code,
                            observation.raw_value,
                            observation.raw_status,
                        )
                    )
                )
            )
            st.caption(
                "관측기간 {} · 기준일 {} · {} · 한계: {}".format(
                    observation.observation_period,
                    observation.as_of_date,
                    observation.interpretation,
                    observation.limitations,
                )
            )
            if reference is not None:
                st.markdown(
                    "[공식 원자료]({})".format(
                        escape(reference.official_url)
                    )
                )
        for warning in assessment.world_bank_macro_environment.warnings:
            st.warning(warning)
        st.divider()
        st.markdown("#### WTO 무역·시장접근")
        if not assessment.wto_trade_market_access.observations:
            st.warning("검증된 WTO 관측값이 없습니다.")
        for observation in assessment.wto_trade_market_access.observations:
            reference = references.get(observation.source_record_id)
            raw_value = (
                observation.raw_value
                if observation.raw_value is not None
                else str(observation.raw_status)
            )
            if observation.raw_value is not None:
                raw_value = format_decimal_display(
                    observation.raw_value,
                    decimal_places=1,
                )
            st.markdown(
                "**{}** · {} {}".format(
                    escape(observation.indicator_code),
                    escape(raw_value),
                    escape(observation.raw_unit),
                )
            )
            st.caption(
                "관측기간 {} · 기준일 {} · {} · 한계: {}".format(
                    observation.observation_period,
                    observation.as_of_date,
                    observation.interpretation,
                    observation.limitations,
                )
            )
            if reference is not None:
                st.markdown(
                    "[공식 원자료]({})".format(
                        escape(reference.official_url)
                    )
                )
    trace = country_environment_trace(assessment)
    with st.expander("국가환경 분석 근거 및 기술정보", expanded=False):
        st.caption(
            "snapshot={} · version={} · hash={} · rule={}".format(
                assessment.snapshot_id,
                assessment.snapshot_version,
                assessment.snapshot_hash,
                assessment.rule_version,
            )
        )
        st.caption(
            "input_fingerprint={}".format(
                assessment.input_fingerprint
            )
        )
        st.json(trace.model_dump())
        json_download(
            label="국가환경 추적 JSON",
            value=trace,
            filename="country_environment_trace.json",
            key="country_environment_trace_download",
        )


def _render_trade_risk_section(
    *,
    document_input: Dict[str, Any],
    extraction: TradeDocumentExtraction,
) -> None:
    trade_binding = confirmed_trade_from_document_input(document_input)
    stored_confirmation = _model_from_state(
        "trade_risk_confirmation",
        TradeRiskConfirmationRecord,
    )
    if (
        stored_confirmation is not None
        and stored_confirmation.confirmed_input.confirmed_trade_sha256
        != trade_binding.trade_sha256
    ):
        clear_trade_risk_and_related(st.session_state)
        stored_confirmation = None
    defaults = _trade_risk_form_defaults(
        extraction=extraction,
        confirmation=stored_confirmation,
    )

    with st.expander(
        "거래·결제조건 확인",
        expanded=stored_confirmation is None,
    ):
        st.caption(
            "문서에서 확인 가능한 결제조건을 먼저 채웠습니다. 신규 거래처 여부와 "
            "보호수단은 추측하지 않으므로 직접 확인해 주세요."
        )
        with st.form("trade_risk_confirmation_form"):
            overview_cols = st.columns(2)
            relationship = overview_cols[0].selectbox(
                "거래처 관계",
                ["UNKNOWN", "NEW", "EXISTING"],
                index=_safe_index(
                    ["UNKNOWN", "NEW", "EXISTING"],
                    defaults["relationship"],
                ),
                format_func=lambda value: {
                    "UNKNOWN": "미확인",
                    "NEW": "신규 거래처",
                    "EXISTING": "기존 거래처",
                }[value],
                key="trade_risk_relationship_widget",
            )
            advance_status = overview_cols[1].selectbox(
                "선지급 조건",
                ["UNKNOWN", "NONE_CONFIRMED", "RATIO_CONFIRMED"],
                index=_safe_index(
                    ["UNKNOWN", "NONE_CONFIRMED", "RATIO_CONFIRMED"],
                    defaults["advance_status"],
                ),
                format_func=lambda value: {
                    "UNKNOWN": "미확인",
                    "NONE_CONFIRMED": "선지급 없음",
                    "RATIO_CONFIRMED": "선지급 비율 확인",
                }[value],
                key="trade_risk_advance_status_widget",
            )
            advance_percent = 0.0
            if advance_status == "RATIO_CONFIRMED":
                advance_percent = st.number_input(
                    "선지급 비율 · %",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(defaults["advance_percent"]),
                    step=1.0,
                    help="화면에서는 %로 입력하고 내부 계약에는 0~1 비율로 저장합니다.",
                    key="trade_risk_advance_percent_widget",
                )

            method_options = [
                "UNKNOWN",
                "OPEN_ACCOUNT",
                "DOCUMENTARY_CREDIT",
                "DOCUMENTARY_COLLECTION_DP",
                "DOCUMENTARY_COLLECTION_DA",
                "DOCUMENTARY_COLLECTION_UNSPECIFIED",
                "OTHER",
            ]
            term_cols = st.columns(2)
            balance_method = term_cols[0].selectbox(
                "잔여대금 결제방식",
                method_options,
                index=_safe_index(
                    method_options,
                    (
                        "UNKNOWN"
                        if defaults["balance_method"] == "NOT_APPLICABLE"
                        else defaults["balance_method"]
                    ),
                ),
                format_func=lambda value: {
                    "UNKNOWN": "미확인",
                    "OPEN_ACCOUNT": "Open Account · 사후송금",
                    "DOCUMENTARY_CREDIT": "신용장 · L/C",
                    "DOCUMENTARY_COLLECTION_DP": "추심 D/P",
                    "DOCUMENTARY_COLLECTION_DA": "추심 D/A",
                    "DOCUMENTARY_COLLECTION_UNSPECIFIED": "추심 · 방식 미확인",
                    "OTHER": "기타",
                }[value],
                key="trade_risk_balance_method_widget",
            )
            term_basis_options = [
                "UNKNOWN",
                "EXPLICIT_NET_TERM",
                "CONFIRMED_DATE_INTERVAL",
                "EVENT_BASED_UNRESOLVED",
                "NOT_APPLICABLE",
            ]
            term_basis = term_cols[1].selectbox(
                "잔여대금 기간 기준",
                term_basis_options,
                index=_safe_index(
                    term_basis_options,
                    defaults["term_basis"],
                ),
                format_func=lambda value: {
                    "UNKNOWN": "미확인",
                    "EXPLICIT_NET_TERM": "문서에 Net N일 명시",
                    "CONFIRMED_DATE_INTERVAL": "날짜 간격 직접 확인",
                    "EVENT_BASED_UNRESOLVED": "선적·B/L·검수 등 사건 기준",
                    "NOT_APPLICABLE": "해당 없음",
                }[value],
                key="trade_risk_term_basis_widget",
            )
            term_days = 0
            if term_basis in {
                "EXPLICIT_NET_TERM",
                "CONFIRMED_DATE_INTERVAL",
            }:
                term_days = st.number_input(
                    "잔여대금 회수기간 · 일",
                    min_value=0,
                    max_value=3650,
                    value=int(defaults["term_days"]),
                    key="trade_risk_term_days_widget",
                )

            protection_status = st.selectbox(
                "보호수단 확인 상태",
                ["UNKNOWN", "NONE_CONFIRMED", "DETAILS_PROVIDED"],
                index=_safe_index(
                    ["UNKNOWN", "NONE_CONFIRMED", "DETAILS_PROVIDED"],
                    defaults["protection_status"],
                ),
                format_func=lambda value: {
                    "UNKNOWN": "미확인",
                    "NONE_CONFIRMED": "없음 확인",
                    "DETAILS_PROVIDED": "보호수단 있음",
                }[value],
                key="trade_risk_protection_status_widget",
            )
            protection_types: List[str] = []
            protection_applicability = "PRESENT_SCOPE_UNVERIFIED"
            if protection_status == "DETAILS_PROVIDED":
                if trade_binding.trade_type == "IMPORT":
                    protection_options = [
                        "ADVANCE_PAYMENT_GUARANTEE",
                        "PERFORMANCE_GUARANTEE",
                        "OTHER",
                    ]
                else:
                    protection_options = [
                        "PAYMENT_GUARANTEE",
                        "EXPORT_CREDIT_INSURANCE",
                        "STANDBY_LETTER_OF_CREDIT",
                        "OTHER",
                    ]
                protection_types = st.multiselect(
                    "보호수단 종류",
                    protection_options,
                    default=[
                        value
                        for value in defaults["protection_types"]
                        if value in protection_options
                    ],
                    format_func=lambda value: {
                        "ADVANCE_PAYMENT_GUARANTEE": "선급금환급보증",
                        "PERFORMANCE_GUARANTEE": "계약이행보증",
                        "PAYMENT_GUARANTEE": "지급보증",
                        "EXPORT_CREDIT_INSURANCE": "수출신용보험",
                        "STANDBY_LETTER_OF_CREDIT": "보증신용장 · SBLC",
                        "OTHER": "기타",
                    }[value],
                    key="trade_risk_protection_types_widget",
                )
                protection_applicability = st.radio(
                    "이 거래에 실제 적용되는 범위까지 확인했나요?",
                    [
                        "PRESENT_SCOPE_UNVERIFIED",
                        "CONFIRMED_APPLICABLE",
                    ],
                    index=_safe_index(
                        [
                            "PRESENT_SCOPE_UNVERIFIED",
                            "CONFIRMED_APPLICABLE",
                        ],
                        defaults["protection_applicability"],
                    ),
                    format_func=lambda value: {
                        "PRESENT_SCOPE_UNVERIFIED": "존재만 확인",
                        "CONFIRMED_APPLICABLE": "현재 거래 적용범위 확인",
                    }[value],
                    horizontal=True,
                    key="trade_risk_protection_applicability_widget",
                )
            counterparty_country = (
                extraction.seller_country
                if trade_binding.trade_type == "IMPORT"
                else extraction.buyer_country
            ) or "미확인"
            st.info(
                "이 검토에 사용할 거래 상대국: {}".format(
                    counterparty_country
                )
            )
            confirmed_by_user = st.checkbox(
                "위 입력값과 거래 상대국 {}를 확인했습니다.".format(
                    counterparty_country
                ),
                key="trade_risk_confirm_widget",
            )
            submitted = st.form_submit_button(
                "결제·회수 위험 확인",
                type="primary",
            )

        if submitted:
            try:
                if not confirmed_by_user:
                    raise ValueError("입력값 확인 체크가 필요합니다.")
                ratio = _trade_risk_ratio(
                    status=advance_status,
                    percent=advance_percent,
                )
                if ratio == "1":
                    balance_method = "NOT_APPLICABLE"
                    term_basis = "NOT_APPLICABLE"
                    term_days_value: Optional[int] = None
                else:
                    term_days_value = (
                        int(term_days)
                        if term_basis
                        in {
                            "EXPLICIT_NET_TERM",
                            "CONFIRMED_DATE_INTERVAL",
                        }
                        else None
                    )
                mechanisms = [
                    ProtectionMechanism(
                        protection_type=value,
                        applicability_status=protection_applicability,
                        source="USER_CONFIRMED",
                    )
                    for value in protection_types
                ]
                risk_input = TradeSettlementRiskInput(
                    confirmed_trade_sha256=trade_binding.trade_sha256,
                    trade_type=trade_binding.trade_type,
                    counterparty_relationship=relationship,
                    advance_payment_ratio=ratio,
                    balance_payment_method=balance_method,
                    payment_term_days=term_days_value,
                    payment_term_basis=term_basis,
                    protection_information_status=protection_status,
                    protection_mechanisms=mechanisms,
                    field_sources={
                        "counterparty_relationship": "USER_CONFIRMED",
                        "advance_payment_ratio": "USER_CONFIRMED",
                        "balance_payment_method": "USER_CONFIRMED",
                        "payment_term_days": "USER_CONFIRMED",
                        "protection_information_status": "USER_CONFIRMED",
                    },
                )
                record = create_trade_risk_confirmation(
                    confirmed_input=risk_input,
                    confirmed_by="streamlit-user",
                )
                assessment = assess_trade_settlement_risk(record)
                country_input = build_country_environment_input(
                    extraction=extraction,
                    trade_risk_confirmation=record,
                )
                country_assessment = assess_country_trade_environment(
                    country_input
                )
                clear_trade_risk_and_related(st.session_state)
                _save_model("trade_risk_confirmation", record)
                _save_model("trade_risk_assessment", assessment)
                _save_model("country_environment_input", country_input)
                _save_model(
                    "country_environment_assessment",
                    country_assessment,
                )
                _save_model(
                    "country_environment_trace",
                    country_environment_trace(country_assessment),
                )

                workflow = _workflow_from_state()
                if workflow is not None:
                    workflow = orchestrator.run_country_environment(
                        workflow,
                        country_input,
                    )
                    _save_workflow(workflow)
                stage1_load = _model_from_state(
                    "stage1_load",
                    Stage1LoadResult,
                )
                stage2_input = _model_from_state(
                    "stage2_input",
                    Stage2Input,
                )
                stage2_result = _model_from_state(
                    "stage2_result",
                    Stage2Result,
                )
                document_confirmation = _model_from_state(
                    "confirmation",
                    ConfirmationRecord,
                )
                if (
                    workflow is not None
                    and stage1_load is not None
                    and stage2_input is not None
                    and stage2_result is not None
                    and document_confirmation is not None
                ):
                    decision_support = build_decision_support(
                        case_id=workflow.case_id,
                        extraction=extraction,
                        confirmation=document_confirmation,
                        stage1=stage1_load.scenario_set,
                        stage2_input=stage2_input,
                        stage2_result=stage2_result,
                        trade_settlement_risk=assessment,
                        country_environment=country_assessment,
                        installment_payment_statuses=(
                            _installment_payment_statuses_from_state()
                        ),
                        missing_information=list(
                            extraction.missing_required_fields
                        ),
                        confirmed_transaction=(
                            workflow.confirmed_transaction
                        ),
                    )
                    stage4_result = _model_from_state(
                        "stage4_result",
                        Stage4Result,
                    )
                    if stage4_result is not None:
                        shortlist = shortlist_official_candidates(
                            stage4_result=stage4_result,
                            trade_type=stage2_result.trade_type,
                            consultation_topics=(
                                decision_support.consultation_topics
                            ),
                        )
                        decision_support = build_decision_support(
                            case_id=workflow.case_id,
                            extraction=extraction,
                            confirmation=document_confirmation,
                            stage1=stage1_load.scenario_set,
                            stage2_input=stage2_input,
                            stage2_result=stage2_result,
                            trade_settlement_risk=assessment,
                            country_environment=country_assessment,
                            official_candidate_shortlist=shortlist,
                            installment_payment_statuses=(
                                _installment_payment_statuses_from_state()
                            ),
                            missing_information=list(
                                extraction.missing_required_fields
                            ),
                            confirmed_transaction=(
                                workflow.confirmed_transaction
                            ),
                        )
                    _save_decision_support(decision_support)
                st.success("확인된 거래조건으로 결제·회수 위험을 갱신했습니다.")
            except (ValueError, TypeError) as exc:
                st.error("거래조건을 확인하세요: {}".format(exc))

    assessment = _model_from_state(
        "trade_risk_assessment",
        TradeSettlementRiskAssessment,
    )
    if assessment is None:
        st.info(
            "거래처 관계와 결제·보호조건을 확인하면 환율 위험과 별도로 "
            "결제·회수 검토 우선도를 보여드립니다."
        )
        return
    tone, label, headline = _trade_risk_priority_copy(assessment)
    risk_name = (
        "수입 선지급·계약이행"
        if assessment.risk_type
        == "IMPORT_PREPAYMENT_PERFORMANCE_RISK"
        else "수출대금 회수"
    )
    st.markdown(
        "<div class='risk-banner {}'><div class='signal'>{}</div>"
        "<div><strong>{}</strong><p>{}</p></div>"
        "<div class='detail'>{}</div></div>".format(
            tone,
            escape(label),
            escape(headline),
            escape(risk_name),
            "규칙 기반 사전검토",
        ),
        unsafe_allow_html=True,
    )
    visible_factors = [
        item
        for item in assessment.factors
        if item.effect in {"RISK_SIGNAL", "INFORMATION_GAP"}
    ][:3]
    if visible_factors:
        st.markdown("**핵심 근거**")
        for factor in visible_factors:
            st.markdown("- {}".format(factor.reason))
    if assessment.review_needs:
        need_labels = {
            "ADVANCE_PAYMENT_PROTECTION_REVIEW": "선지급 보호수단 검토",
            "RECEIVABLE_PROTECTION_REVIEW": "수출대금 회수 보호 검토",
            "DOCUMENTARY_CREDIT_TERMS_REVIEW": "신용장 세부조건 검토",
            "TRADE_TERMS_REVIEW": "결제조건 재확인",
            "HUMAN_REVIEW": "담당자 확인",
        }
        st.caption(
            "다음 검토: {}".format(
                " · ".join(
                    need_labels[value]
                    for value in assessment.review_needs
                )
            )
        )
    st.caption(
        "공식 신용등급이나 승인 결과가 아니며, 환헤지 비율과 "
        "유동성 계산을 직접 변경하지 않습니다."
    )
    country_assessment = _model_from_state(
        "country_environment_assessment",
        CountryTradeEnvironmentAssessment,
    )
    if country_assessment is not None:
        _render_country_environment_section(country_assessment)


def _scenario_label(value: str) -> str:
    if value == "BASE":
        return "기준 환율"
    if value.startswith("STRESS_") and value.endswith("PCT"):
        percentage = value[len("STRESS_") : -len("PCT")]
        try:
            percentage = format(Decimal(percentage).normalize(), "f")
        except InvalidOperation:
            pass
        return "환율 {}%".format(percentage)
    return value.replace("_", " ")


def _five_percent_adverse_result(
    result: Optional[Stage2Result],
) -> Optional[Any]:
    if result is None:
        return None
    expected_name = (
        "STRESS_+5.00PCT"
        if result.trade_type == "IMPORT"
        else "STRESS_-5.00PCT"
    )
    return next(
        (
            item
            for item in result.scenario_results
            if item.scenario_name == expected_name
        ),
        None,
    )


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
    _reset_state()
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
    demo_snapshot = result["workflow_state"].confirmed_transaction
    if demo_snapshot is None:
        raise ValueError("데모 확정 거래 snapshot을 만들 수 없습니다.")
    st.session_state["stage2_document_input"] = (
        document_input_from_confirmed_transaction(demo_snapshot)
    )
    _save_model("stage1_load", result["stage1_load"])
    _save_model("stage2_input", result["stage2_input"])
    _save_model("stage2_result", result["stage2"])
    _save_model(
        "trade_risk_confirmation",
        result["trade_risk_confirmation"],
    )
    _save_model(
        "trade_risk_assessment",
        result["trade_risk_assessment"],
    )
    _save_model(
        "country_environment_input",
        result["country_environment_input"],
    )
    _save_model(
        "country_environment_assessment",
        result["country_environment_assessment"],
    )
    _save_model(
        "country_environment_trace",
        country_environment_trace(
            result["country_environment_assessment"]
        ),
    )
    _save_model("risk_assessment", result["risk_assessment"])
    st.session_state["consultation_topics"] = [
        item.model_dump() for item in result["consultation_topics"]
    ]
    _save_model("consultation_packet", result["consultation_packet"])
    _save_model("stage3_result", result["stage3"])
    _save_model("stage4_result", result["stage4"])
    _save_model(
        "official_candidate_shortlist",
        result["official_candidate_shortlist"],
    )
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
        "수입기업" if company_role == "BUYER" else "미국 수출"
    )


def _reset_state() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def _start_document_registration() -> None:
    _reset_state()
    st.session_state["run_mode_widget"] = "실제 문서 분석"


def _start_golden_registration() -> None:
    _start_document_registration()
    st.session_state["registered_document_id"] = PRESENTATION_FIXTURE_ID
    st.session_state["company_role_widget"] = "판매자 · SELLER"
    st.session_state["company_country_widget"] = "KR"


load_dotenv()
settings = Settings.from_env()
presentation_mode = settings.app_env == "presentation"
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
    page_title="KBaiAgent · 수출입 거래 금융 리스크 분석",
    page_icon="₩",
    layout="wide",
    initial_sidebar_state="auto",
)
st.markdown(
    """
<style>
:root {
  --ink: #172033;
  --muted: #667085;
  --panel: #ffffff;
  --panel-strong: #f8fafc;
  --line: #e3e8ef;
  --mint: #2563eb;
  --blue: #0f766e;
  --amber: #b45309;
  --danger: #c2414f;
  --success-bg: #ecfdf5;
  --warning-bg: #fffbeb;
  --danger-bg: #fff1f2;
}

html {scroll-behavior: smooth;}
[data-testid="stAppViewContainer"] {
  background: #f6f8fb;
}
[data-testid="stHeader"] {background: rgba(246, 248, 251, 0.9);}
[data-testid="stSidebar"] {
  background: #ffffff;
  border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
  color: var(--muted);
}
.block-container {
  padding-top: 1.5rem;
  padding-bottom: 4rem;
  max-width: 1180px;
}
h1, h2, h3 {letter-spacing: -0.035em;}
p {line-height: 1.65;}

div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button {
  border-radius: 10px;
  min-height: 2.7rem;
  font-weight: 700;
  border: 1px solid var(--line);
  background: #ffffff;
  transition: transform 120ms ease, border-color 120ms ease;
}
div[data-testid="stButton"] > button:hover,
div[data-testid="stDownloadButton"] > button:hover {
  transform: translateY(-1px);
  border-color: #93b4f5;
}
div[data-testid="stButton"] > button[kind="primary"],
div[data-testid="stDownloadButton"] > button[kind="primary"],
div[data-testid="stFormSubmitButton"] > button[kind="primary"],
div[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"] {
  background: #2563eb;
  color: #ffffff;
  border: 0;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.18);
}
div[data-testid="stButton"] > button[kind="primary"] *,
div[data-testid="stDownloadButton"] > button[kind="primary"] *,
div[data-testid="stFormSubmitButton"] > button[kind="primary"] *,
div[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"] * {
  color: #ffffff !important;
}

div[data-testid="stMetric"] {
  background: #ffffff;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 1rem 1.05rem;
  box-shadow: 0 8px 24px rgba(23, 32, 51, 0.05);
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
  background: #ffffff;
}

.stTabs [data-baseweb="tab-list"] {
  gap: 0.25rem;
  padding: 0.35rem;
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid var(--line);
  box-shadow: 0 6px 18px rgba(23, 32, 51, 0.04);
}
.stTabs [data-baseweb="tab"] {
  height: 3rem;
  padding: 0 1rem;
  border-radius: 10px;
  color: #667085;
  font-weight: 700;
}
.stTabs [aria-selected="true"] {
  color: #1d4ed8;
  background: #eff6ff;
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
  color: #ffffff;
  background: #2563eb;
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
  padding: 1.55rem 1.65rem;
  margin-bottom: 0.8rem;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 10px 30px rgba(23, 32, 51, 0.05);
}
.eyebrow {
  color: var(--mint);
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.hero-copy h1 {
  max-width: 850px;
  margin: 0.35rem 0 0.45rem;
  color: var(--ink);
  font-size: clamp(1.65rem, 3vw, 2.35rem);
  line-height: 1.12;
}
.hero-copy p {
  max-width: 760px;
  margin: 0;
  color: var(--muted);
  font-size: 0.94rem;
}

.journey-step {
  display: flex;
  min-height: 3.35rem;
  align-items: center;
  justify-content: center;
  gap: 0.42rem;
  color: #98a2b3;
  font-size: 0.78rem;
  font-weight: 700;
  text-align: center;
}
.journey-step.done {color: #344054;}
.journey-step.current {color: #1d4ed8;}
.journey-dot {
  display: inline-flex;
  width: 1.42rem;
  height: 1.42rem;
  flex: 0 0 1.42rem;
  align-items: center;
  justify-content: center;
  border: 1px solid #cfd6df;
  border-radius: 999px;
  font-size: 0.68rem;
}
.journey-step.done .journey-dot {
  color: #ffffff;
  border-color: #0f766e;
  background: #0f766e;
}
.journey-step.current .journey-dot {
  color: #ffffff;
  border-color: #2563eb;
  background: #2563eb;
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
  background: #ffffff;
}
.state-banner .state-icon {
  display: inline-flex;
  width: 2.1rem;
  height: 2.1rem;
  flex: 0 0 2.1rem;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: #eff6ff;
  color: #2563eb;
  font-weight: 900;
}
.state-banner strong {display: block; color: var(--ink);}
.state-banner p {margin: 0.15rem 0 0; color: var(--muted); font-size: 0.86rem;}
.state-banner.warning .state-icon {
  color: var(--amber);
  background: var(--warning-bg);
}
.state-banner.danger .state-icon {
  color: var(--danger);
  background: var(--danger-bg);
}

.risk-banner {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 1rem;
  align-items: center;
  padding: 1.2rem 1.35rem;
  margin: 0.75rem 0 1rem;
  border: 1px solid #a7f3d0;
  border-radius: 16px;
  background: var(--success-bg);
}
.risk-banner.warning {
  border-color: #fcd34d;
  background: var(--warning-bg);
}
.risk-banner.danger {
  border-color: #fda4af;
  background: var(--danger-bg);
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
.risk-banner .detail {color: #475467; font-size: 0.78rem; text-align: right;}

.status-card {
  min-height: 255px;
  border: 1px solid var(--line);
  border-radius: 17px;
  padding: 1.2rem;
  background: #ffffff;
  color: var(--ink);
  margin-bottom: 0.65rem;
  box-shadow: 0 10px 30px rgba(23, 32, 51, 0.06);
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
  color: #1d4ed8;
  background: #eff6ff;
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
  background: #f8fafc;
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
  color: #475467;
  font-size: 0.74rem;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.7rem;
  margin: 0.8rem 0;
}
.summary-item {
  min-width: 0;
  padding: 0.9rem 1rem;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: #ffffff;
}
.summary-item.wide {grid-column: span 2;}
.summary-item small,
.impact-card small,
.consultation-card small {
  display: block;
  margin-bottom: 0.3rem;
  color: var(--muted);
  font-size: 0.72rem;
  font-weight: 700;
}
.summary-item strong {
  display: block;
  overflow-wrap: anywhere;
  color: var(--ink);
  font-size: 1rem;
  line-height: 1.4;
}
.summary-item.attention {
  border-color: #fcd34d;
  background: var(--warning-bg);
}
.result-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.8rem;
  margin: 0.8rem 0 1.25rem;
}
.impact-card {
  min-width: 0;
  padding: 1.05rem;
  border: 1px solid var(--line);
  border-radius: 15px;
  background: #ffffff;
  box-shadow: 0 8px 22px rgba(23, 32, 51, 0.04);
}
.impact-card.warning {
  border-top: 4px solid #f59e0b;
}
.impact-card.safe {
  border-top: 4px solid #0f766e;
}
.impact-card strong {
  display: block;
  margin: 0.15rem 0 0.55rem;
  color: var(--ink);
  font-size: 1.08rem;
  line-height: 1.35;
}
.impact-card p {
  margin: 0.2rem 0;
  color: #475467;
  font-size: 0.84rem;
  line-height: 1.5;
}
.consultation-card {
  min-height: 100%;
  padding: 1rem;
  border: 1px solid var(--line);
  border-radius: 15px;
  background: #ffffff;
}
.consultation-card .rank {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 2rem;
  height: 2rem;
  margin-bottom: 0.65rem;
  border-radius: 999px;
  color: #ffffff;
  background: #2563eb;
  font-size: 0.8rem;
  font-weight: 900;
}
.consultation-card h4 {
  min-height: 3.1rem;
  margin: 0;
  color: var(--ink);
  font-size: 1rem;
  line-height: 1.45;
}
.consultation-card p {
  margin: 0.45rem 0 0;
  color: #475467;
  font-size: 0.82rem;
  line-height: 1.5;
}
.consultation-card .decision {
  margin-top: 0.7rem;
  padding-top: 0.65rem;
  border-top: 1px solid var(--line);
}
.st-key-consultation_top3 [data-testid="stVerticalBlockBorderWrapper"] {
  border: 0;
  background: transparent;
}

.sidebar-summary {
  margin: 0.2rem 0 0.9rem;
  padding: 0.9rem;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #f8fafc;
}
.sidebar-summary small {
  display: block;
  color: var(--muted);
  margin-bottom: 0.25rem;
}
.sidebar-summary strong {
  display: block;
  color: var(--ink);
  line-height: 1.4;
}
.st-key-service_entry_actions {
  margin: 0.35rem 0 0.8rem;
}
.st-key-service_entry_actions [data-testid="stVerticalBlockBorderWrapper"] {
  border-color: #dbe7fb;
  background: #f8fbff;
}
.st-key-service_entry_actions h4 {
  margin-top: 0;
}
.stage-bridge {
  margin: 1.5rem 0 0.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--line);
}
.stage-bridge span {
  color: #1d4ed8;
  font-size: 0.75rem;
  font-weight: 800;
}

[data-testid="stDataFrame"] {
  background: #ffffff;
}
[data-testid="stAlert"] {
  border-radius: 12px;
}

@media (max-width: 900px) {
  .summary-grid {grid-template-columns: repeat(2, minmax(0, 1fr));}
  .result-grid {grid-template-columns: 1fr;}
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
  .hero-shell {
    gap: 0.75rem;
    padding: 1rem;
    border-radius: 14px;
  }
  .hero-copy h1 {font-size: 1.75rem;}
  .hero-copy p {font-size: 0.88rem;}
  .section-intro h2 {font-size: 1.55rem; word-break: keep-all;}
  .summary-grid {grid-template-columns: 1fr;}
  .summary-item.wide {grid-column: span 1;}
  .st-key-service_entry_actions [data-testid="stHorizontalBlock"] {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.5rem;
  }
  .st-key-result_actions [data-testid="stHorizontalBlock"] {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.5rem;
  }
  .st-key-service_entry_actions
    [data-testid="stHorizontalBlock"]
    > div[data-testid="stColumn"] {
    width: 100% !important;
    min-width: 0 !important;
    flex: none !important;
  }
  .st-key-result_actions
    [data-testid="stHorizontalBlock"]
    > div[data-testid="stColumn"] {
    width: 100% !important;
    min-width: 0 !important;
    flex: none !important;
  }
  .stTabs [data-baseweb="tab-list"] {
    gap: 0.1rem;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .stTabs [data-baseweb="tab"] {
    padding: 0 0.2rem;
    font-size: 0.72rem;
    white-space: nowrap;
  }
  div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) {
    grid-template-columns: 1fr;
  }
  .st-key-consultation_top3 [data-testid="stHorizontalBlock"] {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.75rem;
  }
  .st-key-consultation_top3
    [data-testid="stHorizontalBlock"]
    > div[data-testid="stColumn"] {
    width: 100% !important;
    min-width: 0 !important;
    flex: none !important;
  }
  [data-testid="stDataFrame"] {
    max-width: calc(100vw - 2rem);
    overflow-x: auto;
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
        else "실제 문서 분석"
    ),
)
if st.session_state.get("run_mode_widget") == "실제 API 모드":
    st.session_state["run_mode_widget"] = "실제 문서 분석"
st.session_state.setdefault(
    "company_role_widget",
    "구매자 · BUYER",
)
st.session_state.setdefault("company_country_widget", "KR")
st.session_state.setdefault(
    "stage1_mode_widget",
    (
        "WEB_FORECAST"
        if settings.stage1_mode
        in {"web", "web_forecast", "stage1_web"}
        else "EXTERNAL_STAGE1"
        if settings.stage1_mode in {"external", "external_stage1"}
        else "MANUAL_STRESS"
    ),
)
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
        "<div class='sidebar-brand'><span class='mark'>KB</span>"
        "<strong>KBaiAgent</strong>"
        "<p>수출입 거래 금융 리스크 분석</p></div>",
        unsafe_allow_html=True,
    )
    sidebar_extraction = _model_from_state(
        "extraction",
        TradeDocumentExtraction,
    )
    sidebar_confirmation = _model_from_state(
        "confirmation",
        ConfirmationRecord,
    )
    if sidebar_extraction is None:
        sidebar_summary = "새 거래 분석을 시작해 주세요."
        sidebar_detail = "아직 확인된 거래가 없습니다."
    else:
        sidebar_summary = "{} · {}".format(
            (
                "수입"
                if sidebar_extraction.trade_type == "IMPORT"
                else "수출"
                if sidebar_extraction.trade_type == "EXPORT"
                else "거래 확인 중"
            ),
            sidebar_extraction.currency or "통화 확인 필요",
        )
        sidebar_detail = "{} · {}".format(
            format_foreign(
                sidebar_extraction.amount_due or "0",
                sidebar_extraction.currency or "",
            ),
            (
                "거래정보 확정"
                if sidebar_confirmation is not None
                else "원문 확인 필요"
            ),
        )
    st.markdown(
        "<div class='sidebar-summary'><small>현재 거래</small>"
        "<strong>{}</strong><small>{}</small></div>".format(
            escape(sidebar_summary),
            escape(sidebar_detail),
        ),
        unsafe_allow_html=True,
    )
    st.button(
        "새 분석 시작",
        width="stretch",
        on_click=_reset_state,
    )
    stage1_provider: Optional[str] = None
    spot_provider: Optional[str] = None
    payload: Optional[bytes] = None
    endpoint: Optional[str] = None
    with st.expander("분석 환경 및 고급 설정", expanded=False):
        live_label = "실제 문서 분석"
        if presentation_mode:
            mode_label = live_label
            st.caption("분석할 문서 · 브라질 Golden 수출 계약")
        else:
            mode_label = st.radio(
                "분석할 문서",
                ["데모 모드", live_label],
                key="run_mode_widget",
                help="API 키는 서버 환경변수에서만 읽습니다.",
            )
        run_mode = "LIVE" if mode_label == live_label else "DEMO"
        if (
            run_mode == "LIVE"
            and not settings.live_extraction_ready
            and not presentation_mode
        ):
            st.warning(
                "실제 문서 분석 연결이 준비되지 않았습니다. "
                "서버 설정을 확인하거나 데모 모드를 선택하세요."
            )
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
        st.caption(
            "문서 모델 환경변수 · {}".format(settings.openai_model)
        )
        if presentation_mode:
            st.caption(
                "등록된 합성문서는 content SHA-256이 일치할 때만 "
                "API-free 검토 adapter를 사용합니다."
            )
        st.divider()
        st.markdown("**환율 데이터 연결**")
        sidebar_scenario_mode = st.session_state["stage1_mode_widget"]
        if sidebar_scenario_mode == "WEB_FORECAST":
            provider_options = ["http", "file", "mock"]
            default_provider = (
                "mock"
                if run_mode == "DEMO"
                else settings.stage1_provider
            )
            stage1_provider = st.radio(
                "환율 경로 provider",
                provider_options,
                index=_safe_index(provider_options, default_provider),
                format_func=lambda value: {
                    "http": "로컬 HTTP",
                    "file": "latest_forecast.json",
                    "mock": "제공 fixture",
                }[value],
                key="stage1_provider_widget",
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
                "기준환율 provider",
                spot_options,
                index=_safe_index(spot_options, default_spot),
                format_func=lambda value: {
                    "koreaexim": "한국수출입은행 API",
                    "manual": "사용자 확인 수동 입력",
                    "fixture": "데모 1,400원",
                }[value],
                key="spot_provider_widget",
            )
            st.caption(
                "fallback · HTTP 실패 시 허용된 file/mock 경로와 "
                "FALLBACK_USED 상태를 결과 근거에 남깁니다."
            )
        elif sidebar_scenario_mode == "EXTERNAL_STAGE1":
            source_type = st.radio(
                "외부 시나리오 연결",
                ["JSON 업로드", "REST endpoint"],
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
            st.caption("외부 JSON/REST는 Stage 1 adapter 계약으로 검증합니다.")
        else:
            st.caption(
                "현재는 직접 스트레스 테스트를 사용합니다. 외부 provider와 "
                "fixture fallback은 계산에 적용되지 않습니다."
            )
        if not presentation_mode:
            st.markdown("**테스트 fixture**")
            st.button(
                "수입기업 대표 데모",
                width="stretch",
                on_click=_demo_all,
                args=("BUYER",),
                key="sidebar_import_sample",
            )
            st.button(
                "미국 수출 샘플",
                width="stretch",
                on_click=_demo_all,
                args=("SELLER",),
                key="sidebar_export_sample",
            )
        st.divider()
        st.markdown("**연동 상태 점검**")
        st.caption(
            "Stage 1 health·forecast freshness·fallback·spot 출처와 "
            "kb_macro_ai 고정 commit·SHA·거래 지원 여부를 점검합니다."
        )
        st.caption(
            "현재 설정 · Stage 1 {} · Spot {} · kb_macro_ai {}/{}".format(
                settings.stage1_provider,
                settings.spot_rate_provider,
                (
                    "ON"
                    if settings.enable_kb_macro_hedge_reference
                    else "OFF"
                ),
                settings.kb_macro_hedge_mode,
            )
        )
        if st.button(
            "연동 상태 점검",
            key="check_integration_readiness",
            width="stretch",
        ):
            try:
                readiness = build_integration_readiness_report(
                    settings=settings,
                    stage2_input=_model_from_state(
                        "stage2_input",
                        Stage2Input,
                    ),
                    market_integration=_model_from_state(
                        "market_integration",
                        MarketIntegrationResult,
                    ),
                    active_stage1_check=True,
                    run_local_cli_e2e=False,
                )
                _save_model("integration_readiness", readiness)
            except Exception as exc:
                st.error(
                    "연동 상태를 안전하게 확인하지 못했습니다: {}".format(
                        type(exc).__name__
                    )
                )
        stored_readiness = _model_from_state(
            "integration_readiness",
            IntegrationReadinessReport,
        )
        if stored_readiness is not None:
            _render_integration_readiness(stored_readiness)
        else:
            st.caption(
                "상태 점검 전입니다. 이 버튼은 API key 값을 출력하지 않고 "
                "kb_macro_ai 모델을 실행하지 않습니다."
            )
    loaded_demo = st.session_state.pop("demo_just_loaded", None)
    if loaded_demo:
        st.success("{} 샘플의 전체 분석 결과를 준비했습니다.".format(
            loaded_demo
        ))
    st.divider()
    with st.expander("개인정보·계산 원칙", expanded=False):
        st.caption(
            "문서 원문은 로그·데이터셋에 자동 저장하지 않습니다. "
            "AI 추출값은 사용자 확인 전 계산에 들어가지 않습니다."
        )

st.markdown(
    "<section class='hero-shell'>"
    "<div class='hero-copy'>"
    "<div class='eyebrow'>수출입 기업 재무 담당자용</div>"
    "<h1>수출입 거래 금융 리스크 분석</h1>"
    "<p>계약서를 검증하고 환율·현금흐름·결제·회수 위험을 분석해 "
    "은행 상담 준비사항까지 정리합니다.</p></div></section>",
    unsafe_allow_html=True,
)
with st.container(
    border=True,
    key="service_entry_actions",
):
    entry_columns = st.columns(2)
    if presentation_mode:
        entry_columns[0].button(
            "샘플 수출 거래로 체험하기",
            type="primary",
            width="stretch",
            on_click=_start_golden_registration,
            key="service_sample_export",
        )
    else:
        entry_columns[0].button(
            "샘플 수출 거래로 체험하기",
            type="primary",
            width="stretch",
            on_click=_demo_all,
            args=("SELLER",),
            key="service_sample_export",
        )
    entry_columns[1].button(
        "내 거래문서 업로드",
        width="stretch",
        on_click=_start_document_registration,
        key="service_register_document",
    )
    st.caption(
        "샘플은 실제 고객정보가 없는 API-free 합성문서이며, 분석 결과는 "
        "금융상품 가입·승인 또는 보험 인수 결과가 아닙니다."
    )

stage0_tab, risk_tab, response_tab, stage5_tab = (
    st.tabs(
        [
            "1  거래 확인",
            "2  금융 분석",
            "3  상담 준비",
            "4  결과 다운로드",
        ]
    )
)
stage1_tab = risk_tab
stage2_tab = risk_tab
stage3_tab = response_tab
stage4_tab = response_tab

with stage0_tab:
    _section_intro(
        "원문 검증",
        "어떤 거래인지 먼저 확인하세요",
        "AI는 입력을 도울 뿐입니다. 통화·분석 대상 예정 결제액·결제일을 원문과 "
        "대조하기 전에는 어떤 금융 계산도 시작하지 않습니다.",
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

    registered_document = None
    if (
        presentation_mode
        and st.session_state.get("registered_document_id")
        == PRESENTATION_FIXTURE_ID
    ):
        registered_document = presentation_document()

    if run_mode == "DEMO":
        demo_path, preview_mime, demo_extraction = _demo_fixture(
            company_role
        )
        preview_bytes = demo_path.read_bytes()
        preview_name = demo_path.name
        if uploaded is not None:
            st.info(
                "데모 모드에서는 업로드 파일을 전송·분석하지 않고 고정된 가상 "
                "역할별 fixture를 사용합니다. 실제 문서는 실제 문서 분석을 "
                "선택하세요."
            )
    else:
        preview_bytes = (
            uploaded.getvalue()
            if uploaded is not None
            else (
                registered_document.file_bytes
                if registered_document is not None
                else b""
            )
        )
        preview_name = (
            uploaded.name
            if uploaded is not None
            else (
                registered_document.filename
                if registered_document is not None
                else "uploaded_document"
            )
        )
        preview_mime = (
            uploaded.type
            if uploaded is not None
            else (
                registered_document.mime_type
                if registered_document is not None
                else "application/octet-stream"
            )
        )
        if registered_document is not None and uploaded is None:
            st.caption(
                "등록된 API-free 합성 계약서가 선택되었습니다. 업로드한 "
                "문서가 있으면 업로드 문서를 우선 분석합니다."
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
        st.session_state["transaction_change_notice"] = True
        st.rerun()
    elif st.session_state.pop("transaction_change_notice", False):
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
                if not preview_bytes:
                    raise ValueError(
                        "실제 문서 분석에서는 문서를 업로드하거나 등록된 "
                        "합성문서를 선택하세요."
                    )
                extraction_run = extract_registered_document(
                    file_bytes=preview_bytes,
                    filename=preview_name,
                    mime_type=preview_mime,
                    company_role=company_role,
                    company_country=company_country,
                    settings=settings,
                )
                if extraction_run is None:
                    if not settings.live_extraction_ready:
                        raise ValueError(
                            "이 문서는 등록된 API-free fixture와 일치하지 "
                            "않습니다. OPENAI_API_KEY와 "
                            "ENABLE_LIVE_DOCUMENT_EXTRACTION=true를 "
                            "설정하거나 등록된 합성문서를 선택하세요."
                        )
                    with st.spinner(
                        "문서를 안전 검사하고 모델로 추출 중입니다..."
                    ):
                        extraction_run = (
                            extract_trade_document_with_metadata(
                                file_bytes=preview_bytes,
                                filename=preview_name,
                                mime_type=preview_mime,
                                company_role=company_role,
                                company_country=company_country,
                                settings=settings,
                            )
                        )
                else:
                    st.info(
                        "content SHA-256이 등록된 합성 계약과 일치해 "
                        "API-free 검토 adapter를 사용했습니다."
                    )
                extraction = extraction_run.extraction
                validation = extraction_run.validation
                original_extraction = extraction_run.raw_extraction
                provider_name = extraction_run.usage.model
                metadata_dict = {
                    "filename": extraction_run.upload.filename,
                    "mime_type": extraction_run.upload.mime_type,
                    "size_bytes": extraction_run.upload.size_bytes,
                    "sha256": extraction_run.upload.sha256,
                    "page_count": extraction_run.upload.page_count,
                    "latency_seconds": extraction_run.usage.latency_seconds,
                    "input_tokens": extraction_run.usage.input_tokens,
                    "output_tokens": extraction_run.usage.output_tokens,
                    "provider": (
                        provider_name
                        if provider_name
                        == "registered_api_free_fixture"
                        else "openai:{}".format(provider_name)
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
        _render_transaction_overview(
            extraction,
            _model_from_state(
                "confirmed_transaction",
                ConfirmedTransactionSnapshot,
            ),
            _model_from_state(
                "consultation_packet",
                ConsultationPacketResult,
            ),
        )
        st.caption(
            "수정이 필요한 경우 아래에서 값을 저장하고 다시 검증할 수 "
            "있습니다. 저장된 변경은 이후 분석 결과를 무효화합니다."
        )
        document_types = [
            "COMMERCIAL_INVOICE",
            "SALES_CONTRACT",
            "PURCHASE_ORDER",
            "UNKNOWN",
        ]
        review_panel = st.expander(
            "거래정보 수정 및 재검증",
            expanded=False,
        )
        with review_panel.form("review_extraction"):
            st.markdown("#### 핵심 거래정보")
            st.caption(
                "아래 정보는 이후 모든 환율·현금 계산의 기준입니다. "
                "문서 원문과 다른 값만 수정하세요."
            )
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
            party_row = st.columns(2)
            seller_name = party_row[0].text_input(
                "판매자",
                value=extraction.seller_name or "",
                key="review_seller_name_widget",
            )
            buyer_name = party_row[1].text_input(
                "구매자",
                value=extraction.buyer_name or "",
                key="review_buyer_name_widget",
            )
            country_row = st.columns(2)
            seller_country = country_row[0].text_input(
                "판매자 국가",
                value=extraction.seller_country or "",
                key="review_seller_country_widget",
            ).strip()
            buyer_country = country_row[1].text_input(
                "구매자 국가",
                value=extraction.buyer_country or "",
                key="review_buyer_country_widget",
            ).strip()
            review_trade_type = (
                selected_trade_type
                if selected_trade_type in {"IMPORT", "EXPORT"}
                else extraction.trade_type
            )
            amount_due_label = amount_due_user_label(review_trade_type)
            payment_row = st.columns(3)
            currency = payment_row[0].text_input(
                "통화",
                value=extraction.currency or "",
                key="review_currency_widget",
            ).strip().upper()
            amount_due = payment_row[1].text_input(
                amount_due_label,
                value=extraction.amount_due or "",
                key="review_amount_due_widget",
            )
            explicit_due_date = payment_row[2].text_input(
                "명시 결제일",
                value=extraction.explicit_due_date or "",
                placeholder="YYYY-MM-DD",
                key="review_explicit_due_date_widget",
            )
            payment_terms = st.text_input(
                "결제조건 · 예: Net 90 Days",
                value=extraction.payment_terms or "",
                key="review_payment_terms_widget",
            )
            st.caption(SCHEDULED_EXPOSURE_WARNING)

            with st.container(border=True):
                st.markdown("##### 추가 문서정보")
                document_row = st.columns(3)
                document_type = document_row[0].selectbox(
                    "문서 유형",
                    document_types,
                    index=_safe_index(
                        document_types,
                        extraction.document_type,
                    ),
                    format_func=lambda value: {
                        "COMMERCIAL_INVOICE": "상업송장",
                        "SALES_CONTRACT": "매매계약서",
                        "PURCHASE_ORDER": "구매주문서",
                        "UNKNOWN": "기타/확인 필요",
                    }.get(value, value),
                    key="review_document_type_widget",
                )
                document_number = document_row[1].text_input(
                    "문서 번호",
                    value=extraction.document_number or "",
                    key="review_document_number_widget",
                )
                grand_total = document_row[2].text_input(
                    "문서 총액",
                    value=extraction.grand_total or "",
                    key="review_grand_total_widget",
                )
                date_row = st.columns(3)
                issue_date = date_row[0].text_input(
                    "발행일",
                    value=extraction.issue_date or "",
                    placeholder="YYYY-MM-DD",
                    key="review_issue_date_widget",
                )
                contract_date = date_row[1].text_input(
                    "계약일",
                    value=extraction.contract_date or "",
                    placeholder="YYYY-MM-DD",
                    key="review_contract_date_widget",
                )
                shipment_date = date_row[2].text_input(
                    "선적일",
                    value=extraction.shipment_date or "",
                    placeholder="YYYY-MM-DD",
                    key="review_shipment_date_widget",
                )
                additional_row = st.columns(2)
                incoterm = additional_row[0].text_input(
                    "Incoterm",
                    value=extraction.incoterm or "",
                    key="review_incoterm_widget",
                )
                additional_row[1].text_input(
                    "현재 적용된 거래 방향",
                    value=extraction.trade_type,
                    disabled=True,
                    help=(
                        "위 자동/사용자 지정 선택을 저장하면 최신 입력으로 "
                        "다시 판정합니다."
                    ),
                )

            with st.container(border=True):
                st.markdown("##### 분할결제 일정")
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
                "회사 역할·거래 방향·통화·{}·결제일을 사용자가 "
                "확인했습니다. 이제 환율 가정 단계로 이동할 수 있습니다."
            ).format(amount_due_label)
        elif validation.validation_pass:
            banner_class = "warning"
            banner_icon = "3"
            banner_title = "자동 검증 완료 · 핵심값 확인이 남았습니다"
            banner_copy = (
                "아래 원문 근거와 회사 역할·거래 방향·통화·{}·결제일을 "
                "대조한 뒤 거래를 확정하세요.".format(amount_due_label)
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
        if not is_confirmed:
            render_validation_summary(validation)

        with st.expander(
            "거래 검증 기술정보",
            expanded=False,
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
        st.markdown(
            "#### {}".format(
                "핵심 거래값 확인 기록"
                if is_confirmed
                else "핵심 거래값 최종 확인"
            )
        )
        st.caption(
            "체크는 단순 동의가 아니라 문서 원문과 직접 대조했다는 기록입니다."
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
        with st.form("critical_confirmation"):
            confirmed_due = st.text_input(
                "최종 결제일",
                value=(
                    confirmation.checks.confirmed_due_date
                    if is_confirmed and confirmation is not None
                    else resolved_due
                ),
                placeholder="YYYY-MM-DD",
                help=(
                    "Net N 조건은 일반 코드가 계산하며, "
                    "여기서는 사용자가 최종 결제일을 확인합니다."
                ),
                key="confirmed_due_widget",
                disabled=is_confirmed,
            )
            company_role_ok = st.checkbox(
                "{} 역할을 확인했습니다".format(extraction.company_role),
                value=is_confirmed,
                key="confirm_company_role_widget",
                disabled=is_confirmed,
            )
            trade_type_ok = st.checkbox(
                "{} 거래 방향을 확인했습니다".format(
                    validation.derived_trade_type
                ),
                value=is_confirmed,
                key="confirm_trade_type_widget",
                disabled=is_confirmed,
            )
            currency_ok = st.checkbox(
                "통화를 원문과 대조했습니다",
                value=is_confirmed,
                key="confirm_currency_widget",
                disabled=is_confirmed,
            )
            amount_ok = st.checkbox(
                "{}을 원문과 대조했습니다".format(amount_due_label),
                value=is_confirmed,
                key="confirm_amount_widget",
                disabled=is_confirmed,
            )
            due_ok = st.checkbox(
                "결제일과 조건을 대조했습니다",
                value=is_confirmed,
                key="confirm_due_widget",
                disabled=is_confirmed,
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
                    default=(
                        confirmation.checks.user_confirmed_override_fields
                        if is_confirmed and confirmation is not None
                        else []
                    ),
                    key="confirm_evidence_override_widget",
                    disabled=is_confirmed,
                )
            confirmation_submit = st.form_submit_button(
                "원문과 확인하고 금융분석 시작",
                type="primary",
                disabled=is_confirmed,
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
                    snapshot = _model_from_state(
                        "confirmed_transaction",
                        ConfirmedTransactionSnapshot,
                    )
                    if snapshot is None:
                        raise ValueError(
                            "확정 거래 snapshot을 만들 수 없습니다. "
                            "핵심 거래값을 다시 확인하세요."
                        )
                    document_input = (
                        document_input_from_confirmed_transaction(snapshot)
                    )
                    st.session_state[
                        "stage2_document_input"
                    ] = document_input
                    st.success(
                        "거래가 확정되었습니다. 금융 리스크 분석으로 이동하세요."
                    )
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
                    amount_due_label,
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
        "거래 영향",
        "돈으로 얼마나 영향을 받는지 확인하세요",
        "기준환율과 불리한 환율 구간을 준비합니다. 이 구간은 미래 가격을 "
        "맞히기 위한 예측이 아니라 회사의 지급 능력을 확인하는 조건입니다.",
    )
    risk_overview = _model_from_state(
        "consultation_packet",
        ConsultationPacketResult,
    )
    if risk_overview is not None:
        evidence_stage2 = _model_from_state(
            "stage2_result",
            Stage2Result,
        )
        _render_financial_overview(
            risk_overview,
            stage2_result=evidence_stage2,
        )
        _render_consultation_priorities(
            risk_overview,
            key_prefix="financial_results",
            stage2_result=evidence_stage2,
        )
        evidence_stage1 = _model_from_state(
            "stage1_load",
            Stage1LoadResult,
        )
        if evidence_stage1 is not None and evidence_stage2 is not None:
            _render_financial_evidence(
                stage1_load=evidence_stage1,
                stage2_result=evidence_stage2,
                market_integration=_model_from_state(
                    "market_integration",
                    MarketIntegrationResult,
                ),
                risk_assessment=_model_from_state(
                    "risk_assessment",
                    RiskAssessment,
                ),
            )
        st.divider()
    document_input = st.session_state.get("stage2_document_input")
    if document_input is None:
        st.markdown(
            "<div class='state-banner warning'><span class='state-icon'>1</span>"
            "<div><strong>먼저 거래값을 확정하세요</strong>"
            "<p>첫 번째 탭에서 통화·분석 대상 예정 결제액·결제일을 확인하면 "
            "환율 가정을 만들 수 있습니다.</p></div></div>",
            unsafe_allow_html=True,
        )
    else:
        trade = document_input["trade"]
        target_date = ""
        try:
            target_date = confirmed_analysis_due_date_from_document_input(
                document_input
            )
        except (TypeError, ValueError) as exc:
            st.error(
                "확정 결제일을 금융분석에 연결할 수 없습니다: {}".format(
                    str(exc)
                )
            )
        scenario_settings = st.expander(
            "금융분석 입력과 환율 가정",
            expanded=False,
        )
        scenario_mode = scenario_settings.radio(
            "환율 가정을 만드는 방법",
            ["WEB_FORECAST", "MANUAL_STRESS", "EXTERNAL_STAGE1"],
            horizontal=True,
            format_func=lambda value: {
                "WEB_FORECAST": "AI 경로 분석 + 고정 스트레스",
                "MANUAL_STRESS": "직접 스트레스 테스트",
                "EXTERNAL_STAGE1": "기존 시나리오 JSON",
            }[value],
            key="stage1_mode_widget",
        )
        manual_spot_confirmed = False
        base_rate = scenario_settings.text_input(
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
            manual_spot_confirmed = scenario_settings.checkbox(
                "위 기준환율의 값과 기준시점을 확인했습니다",
                value=False,
                key="spot_confirmed_widget",
                help=(
                    "Stage 1 JSON에는 절대환율이 없으므로 사용자가 확인한 "
                    "환율만 계산에 사용할 수 있습니다."
                ),
            )
        elif scenario_mode == "WEB_FORECAST" and spot_provider == "fixture":
            scenario_settings.warning(
                "1,400원은 가상 데모 fixture이며 현재 시장환율이 아닙니다."
            )
        scenario_settings.caption(
            "provider·fixture·file·fallback 설정은 sidebar의 "
            "‘분석 환경 및 고급 설정’에서 관리합니다."
        )
        st.caption(
            "현재 기준환율 · 1 {} = {}원".format(
                trade["currency"],
                format_decimal_display(base_rate, 2),
            )
        )
        if st.button(
            "환율 위험 범위 준비하기",
            type="primary",
            key="load_stage1",
            disabled=not bool(target_date),
        ):
            try:
                clear_downstream(
                    st.session_state,
                    1,
                    clear_widgets=False,
                )
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
                _save_workflow(workflow)
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
        if stage1_load is not None and risk_overview is None:
            scenarios = stage1_load.scenario_set
            source_copy = (
                "AI 경로위험 + 고정 스트레스"
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
            stage1_details = st.expander(
                "환율 구간과 시장 분석 근거 보기",
                expanded=False,
            )
            if market_integration is not None:
                quote = market_integration.spot_quote
                integration_cols = stage1_details.columns(4)
                integration_cols[0].metric(
                    "경로 분석 연결",
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
                    stage1_details.markdown("#### 모델 기반 21일 경로위험")
                    direction_cols = stage1_details.columns(4)
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
                    stage1_details.caption(
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
                    stage1_details.dataframe(
                        model_rows,
                        width="stretch",
                        hide_index=True,
                    )
                    stage1_details.info(
                        "q90은 ‘90% 확률로 발생’이 아니라 모델 "
                        "예측분포의 상위 경로위험 분위수입니다."
                    )

                    stage1_details.markdown("#### 뉴스 기반 시장 문맥")
                    stage1_details.write(forecast.market_context.summary)
                    stage1_details.caption(
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
                        stage1_details.dataframe(
                            news_rows,
                            width="stretch",
                            hide_index=True,
                        )
                if market_integration.scenario_build.horizon_mismatch:
                    stage1_details.warning(
                        "HORIZON_MISMATCH · 결제일이 Stage 1의 21거래일 "
                        "검증범위 밖입니다. 모델 환율은 계산에서 제외하고 "
                        "±3/5/10% 고정 스트레스만 적용했습니다."
                    )
                stage1_details.markdown("#### 고정 스트레스 테스트")
                stage1_details.caption(
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
            stage1_details.dataframe(
                scenario_rows,
                width="stretch",
                hide_index=True,
            )
            if stage1_load.warnings:
                stage1_details.markdown("#### 데이터 품질·적용 경고")
                for warning in stage1_load.warnings:
                    stage1_details.warning(warning)
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
    stage1_load = _model_from_state("stage1_load", Stage1LoadResult)
    document_input = st.session_state.get("stage2_document_input")
    if stage1_load is None or document_input is None:
        pass
    else:
        st.markdown(
            "<div class='stage-bridge'><span>이어서 · 회사 자금 입력</span></div>",
            unsafe_allow_html=True,
        )
        st.markdown("### 회사 자금 입력")
        st.caption(
            "현재 현금과 운영자금 방어선을 입력하면 환율이 불리해질 때의 "
            "추가 부담과 실제 지급 부족 여부를 계산합니다."
        )
        extraction_for_trade_risk = _model_from_state(
            "extraction",
            TradeDocumentExtraction,
        )
        if extraction_for_trade_risk is not None:
            _render_trade_risk_section(
                document_input=document_input,
                extraction=extraction_for_trade_risk,
            )
        trade = document_input["trade"]
        confirmed_analysis_due_date = ""
        try:
            confirmed_analysis_due_date = (
                confirmed_analysis_due_date_from_document_input(
                    document_input
                )
            )
        except (TypeError, ValueError) as exc:
            st.error(
                "확정 결제일을 현금 계산에 연결할 수 없습니다: {}".format(
                    str(exc)
                )
            )
        stored_stage2_input = _model_from_state(
            "stage2_input",
            Stage2Input,
        )
        form_defaults = _stage2_form_defaults(
            stored_stage2_input,
            document_input=document_input,
        )
        st.caption(
            "확정 거래 · {} · {} · 결제일 {}".format(
                format_foreign(
                    trade["foreign_amount"],
                    trade["currency"],
                ),
                "수입 결제" if trade["trade_type"] == "IMPORT" else "수출 수취",
                confirmed_analysis_due_date or "확인 필요",
            )
        )
        with st.form("stage2_company_input"):
            st.markdown("#### 회사의 자금 방어선")
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
            additional_funds = st.expander(
                "선택 · 보유외화와 기존 방어수단",
                expanded=False,
            )
            timing_cols = additional_funds.columns(2)
            as_of = timing_cols[0].date_input(
                "현금 계산 기준일",
                value=form_defaults["as_of"],
                key="stage2_as_of_widget",
            )
            timing_cols[0].caption(
                "가장 이른 예정 결제일보다 늦을 수 없습니다."
            )
            is_import_trade = trade["trade_type"] == "IMPORT"
            usable_fx = timing_cols[1].text_input(
                (
                    "결제에 사용할 수 있는 보유외화 · {}".format(
                        trade["currency"]
                    )
                    if is_import_trade
                    else "현재 보유외화 · {} · 수취액 계산 미적용".format(
                        trade["currency"]
                    )
                ),
                value=form_defaults["usable_fx"],
                help=(
                    "수입 결제에 직접 사용할 잔액만 입력합니다."
                    if is_import_trade
                    else (
                        "수출 예정 수취액은 보유외화로 줄지 않습니다. "
                        "입력값은 참고용으로 보존하고 계산에는 적용하지 "
                        "않습니다."
                    )
                ),
                key="stage2_usable_fx_widget",
            )
            if not is_import_trade:
                timing_cols[1].caption(
                    "미적용 · 기존 보유외화는 이번 수출대금 수취액과 "
                    "현금흐름을 상계하지 않습니다."
                )

            additional_funds.markdown("#### 같은 통화의 예정 자금")
            additional_funds.caption(
                (
                    "결제 전에 같은 외화가 들어오면 수입 결제 부담을 "
                    "일부 상계할 수 있습니다."
                    if is_import_trade
                    else (
                        "수취 전에 같은 외화로 확정된 지급이 있으면 "
                        "수출 수취 노출의 자연상계 후보가 됩니다."
                    )
                )
            )
            natural_cols = additional_funds.columns(3)
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

            additional_funds.markdown("#### 기존 환율 고정·은행 비용")
            hedge_cols = additional_funds.columns(3)
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
            fee_cols = additional_funds.columns(2)
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

            scheduled_cash = st.expander(
                "선택 · 결제일까지 예정된 원화 입출금",
                expanded=False,
            )
            scheduled_cash.caption(
                "행을 추가하거나 삭제해 회사의 현금 일정을 반영하세요."
            )
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
            edited_cashflows = scheduled_cash.data_editor(
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
                "환율·자금 위험 계산하기",
                type="primary",
                disabled=not bool(confirmed_analysis_due_date),
            )

        if stage2_submit:
            clear_downstream(
                st.session_state,
                2,
                clear_widgets=False,
            )
            form_input: Optional[Stage2FormInput] = None
            stage2_input: Optional[Stage2Input] = None
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
                stage2_input = build_validated_stage2_input_from_form(
                    document_input=document_input,
                    form=form_input,
                )
                validate_stage2_as_of_date(stage2_input)
                workflow = _workflow_from_state()
                if workflow is None:
                    raise ValueError(
                        "분석 세션을 찾을 수 없습니다. 거래 확인부터 다시 시작하세요."
                    )
                workflow = orchestrator.run_cashflow(
                    workflow,
                    stage2_input,
                )
                _save_workflow(workflow)
                if workflow.cashflow is None or workflow.cashflow.data is None:
                    detail = workflow.cashflow_error or classify_cashflow_error(
                        ValueError(
                            ", ".join(
                                workflow.cashflow.errors
                                if workflow.cashflow is not None
                                else []
                            )
                        ),
                        stage2_input=stage2_input,
                    )
                    _save_model("cashflow_error", detail)
                    raise CashflowValidationError(detail)
                result = workflow.cashflow.data
                _save_model("stage2_input", stage2_input)
                _save_model("stage2_result", result)
                st.session_state.pop("cashflow_error", None)
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
                    trade_settlement_risk=_model_from_state(
                        "trade_risk_assessment",
                        TradeSettlementRiskAssessment,
                    ),
                    country_environment=_model_from_state(
                        "country_environment_assessment",
                        CountryTradeEnvironmentAssessment,
                    ),
                    installment_payment_statuses=(
                        _installment_payment_statuses_from_state()
                    ),
                    missing_information=list(
                        extraction_for_decision.missing_required_fields
                    ),
                    confirmed_transaction=workflow.confirmed_transaction,
                )
                _save_decision_support(decision_support)
                st.success("환율별 현금 영향 계산을 완료했습니다.")
                st.rerun()
            except CashflowValidationError as exc:
                _persist_cashflow_failure(exc.detail)
                _render_cashflow_error(exc.detail)
            except (ValueError, TypeError) as exc:
                input_fingerprint = None
                offending_value = None
                field_path = None
                if form_input is not None:
                    input_fingerprint = (
                        stage2_form_fingerprint(
                            document_input=document_input,
                            form=form_input,
                        )
                        if stage2_input is None
                        else None
                    )
                    field_path, offending_value = (
                        stage2_form_error_context(exc, form_input)
                    )
                detail = classify_cashflow_error(
                    exc,
                    stage2_input=stage2_input,
                    input_fingerprint=input_fingerprint,
                    supplied_offending_value=offending_value,
                    supplied_field_path=field_path,
                )
                _persist_cashflow_failure(detail)
                _render_cashflow_error(detail)

        stored_cashflow_error = _model_from_state(
            "cashflow_error",
            CashflowErrorDetail,
        )
        if stored_cashflow_error is not None and not stage2_submit:
            _render_cashflow_error(stored_cashflow_error)

        stage2_result = _model_from_state("stage2_result", Stage2Result)
        if stage2_result is not None and risk_overview is None:
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
            metrics = st.columns(4)
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
                "신용한도 사용 후 부족",
                format_krw(highest_payment_gap),
                help=(
                    "최소 운영자금 부족과 다릅니다. 현금과 입력한 대출한도를 "
                    "모두 반영해도 남는 실제 자금 부족입니다."
                ),
            )
            if highest_buffer_gap > 0:
                st.caption(
                    "운영자금 방어선 대비 최대 부족 · {}".format(
                        format_krw(highest_buffer_gap)
                    )
                )

            calculation_details = st.expander(
                "환율 구간별 계산과 현금 흐름 보기",
                expanded=False,
            )
            calculation_details.markdown("#### 환율 구간별 현금 결과")
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
            calculation_details.dataframe(
                scenario_rows,
                width="stretch",
                hide_index=True,
            )

            calculation_details.markdown("#### 결제일까지 현금 잔고 흐름")
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
                calculation_details.line_chart(ledger_frame)
                calculation_details.caption(
                    "선이 운영자금 방어선 아래로 내려가는 시점이 있는지 확인하세요."
                )
            if stage2_result.warnings:
                for warning in stage2_result.warnings:
                    calculation_details.warning(warning)

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
                    st.markdown(
                        "**주요 위험** · {}".format(
                            " · ".join(
                                dict.fromkeys(
                                    risk_labels.get(
                                        finding.risk_code,
                                        "추가 확인 필요",
                                    )
                                    for finding in risk_assessment.findings
                                )
                            )
                        )
                    )
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
                with st.expander(
                    "분석 근거 및 기술 정보 보기",
                    expanded=False,
                ):
                    st.caption(
                        "Top 3와 기타 확인사항을 만든 원래 규칙 기반 상담 "
                        "범주입니다. 상품 추천·승인·최적 헤지 확정이 아니며 "
                        "실제 조건은 KB 담당자 검토가 필요합니다."
                    )
                    for topic in consultation_topics:
                        st.markdown("**{}**".format(topic.title))
                        topic_basis = (
                            ", ".join(topic.triggered_by)
                            if topic.triggered_by
                            else "거래·결제조건 확인"
                            if topic.trade_risk_review_needs
                            else "정기 점검"
                        )
                        st.caption(
                            "{} · 근거 {} · 사람 검토 필수".format(
                                topic.category,
                                topic_basis,
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
                        st.divider()

            if consultation_packet is not None:
                st.markdown(
                    "<div class='state-banner'><span class='state-icon'>→</span>"
                    "<div><strong>상담 준비사항이 정리되었습니다</strong>"
                    "<p>상담 준비에서 순서와 준비자료를 확인하고, "
                    "결과 다운로드에서 상담 준비서를 저장할 수 있습니다.</p></div></div>",
                    unsafe_allow_html=True,
                )

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
        "상담 실행 준비",
        "필요한 대응안과 공식 자료를 확인하세요",
        "먼저 확인할 상담 Top 3는 금융 핵심 결과 바로 아래에 정리했습니다. "
        "여기서는 상담 전에 비교할 대응안과 공식 출처를 선택적으로 확인합니다.",
    )
    consultation_preparation = _model_from_state(
        "consultation_packet",
        ConsultationPacketResult,
    )
    if consultation_preparation is None:
        st.markdown(
            "<div class='state-banner warning'><span class='state-icon'>2</span>"
            "<div><strong>먼저 금융 리스크 분석을 완료하세요</strong>"
            "<p>확정 거래와 환율·현금 결과가 준비되면 우선 확인할 상담과 "
            "준비자료가 생성됩니다.</p></div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.success(
            "상담 Top 3와 준비자료가 생성되었습니다. 금융 분석 결과에서 "
            "순위별 핵심 숫자와 다음 행동을 확인할 수 있습니다."
        )
    st.markdown(
        "<div class='stage-bridge'><span>선택 · 환율 대응안 비교</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown("### 환율 대응안 비교")
    st.caption(
        "환율 고정·분할환전·미고정 비율에 따른 추가 부담과 현금 영향을 "
        "비교합니다. 실제 상품 추천이나 계약 결정을 확정하지 않습니다."
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
            "대응안 비교하기",
            type="primary",
            key="optimize_stage3",
        ):
            st.session_state.pop("stage3_result", None)
            clear_downstream(
                st.session_state,
                4,
                clear_widgets=False,
            )
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
            _save_workflow(workflow)
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
            clear_downstream(st.session_state, 4)
            st.rerun()
        stage3_result = _model_from_state("stage3_result", Stage3Result)
        if stage3_result is not None:
            if not stage3_result.candidates:
                st.info(
                    "현재 입력된 조건에서는 제시할 수 있는 헤지 비교안이 "
                    "없습니다."
                )
                reason_copies = no_feasible_reason_copy(
                    stage3_result.infeasible_reasons
                )
                if reason_copies:
                    st.markdown("**현재 결과에 포함된 사유**")
                    for reason in reason_copies:
                        st.write("· {}".format(reason))
                st.markdown(
                    "**다음 행동**  \n"
                    "· 입력조건 다시 확인  \n"
                    "· 환율 관리 상담에서 허용조건 확인  \n"
                    "· 실제 은행 견적과 한도 확인"
                )
                with st.expander(
                    "헤지 비교 기술정보",
                    expanded=False,
                ):
                    st.caption(
                        "status={} · reason_codes={}".format(
                            stage3_result.status,
                            ", ".join(
                                stage3_result.infeasible_reasons
                            )
                            or "none",
                        )
                    )
            if stage3_result.candidates:
                st.markdown(
                    "<div class='state-banner'><span class='state-icon'>i</span>"
                    "<div><strong>세 가지 관점의 계산상 비교안입니다</strong>"
                    "<p>실제 계약 전 거래은행에 약정환율·수수료·중도해지 조건을 "
                    "확인하세요.</p></div></div>",
                    unsafe_allow_html=True,
                )
            cards = (
                st.columns(3)
                if stage3_result.candidates
                else []
            )
            for card, candidate in zip(
                cards,
                stage3_result.candidates,
            ):
                with card:
                    candidate_chip = {
                        "STABILITY_FIRST": "안정성 중심",
                        "BALANCED": "균형 중심",
                        "COST_FIRST": "비용 중심",
                    }.get(candidate.profile, "비교 후보")
                    constraint_copy = (
                        "입력한 제약 충족"
                        if candidate.constraints_satisfied
                        else "입력한 제약 미충족"
                    )
                    st.markdown(
                        "<div class='status-card'>"
                        "<div class='rank'><strong>{}</strong>"
                        "<span class='chip'>계산상 비교안</span></div>"
                        "<div class='mix'>"
                        "<div><small>환율 고정</small><b>{}</b></div>"
                        "<div><small>분할환전</small><b>{}</b></div>"
                        "<div><small>미고정</small><b>{}</b></div>"
                        "</div>"
                        "<div class='outcome'>"
                        "<div><small>불리한 경우 추가부담</small><b>{}</b></div>"
                        "<div><small>비용 가정</small><b>{}</b></div>"
                        "<div><small>최저 현금잔고</small><b>{}</b></div>"
                        "<div><small>신용한도 사용 후 부족</small><b>{}</b></div>"
                        "</div><div class='constraint'>{}</div></div>".format(
                            candidate_chip,
                            format_ratio(candidate.forward_ratio),
                            format_ratio(
                                candidate.staged_conversion_ratio
                            ),
                            format_ratio(candidate.unhedged_ratio),
                            format_krw(candidate.worst_case_loss),
                            format_krw(candidate.assumed_hedge_cost),
                            format_krw(candidate.minimum_cash_balance),
                            format_krw(candidate.post_credit_deficit),
                            constraint_copy,
                        ),
                        unsafe_allow_html=True,
                    )
                    st.caption(candidate.rationale)
                    with st.expander("계산 기준과 세부 결과", expanded=False):
                        st.write(
                            "통상보다 크게 불리한 경우 · {}".format(
                                (
                                    format_krw(candidate.q90_adverse_loss)
                                    if candidate.q90_adverse_loss is not None
                                    else "기간 외 · 미적용"
                                )
                            )
                        )
                        st.write(
                            "환율 ±10% 불리방향 · {}".format(
                                (
                                    format_krw(
                                        candidate.fixed_10_adverse_loss
                                    )
                                    if candidate.fixed_10_adverse_loss
                                    is not None
                                    else "미확인"
                                )
                            )
                        )
                        st.write(
                            "보유외화 반영 비율 · {}".format(
                                format_ratio(candidate.held_fx_ratio)
                            )
                        )
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
    if getattr(settings, "enable_kb_macro_hedge_reference", False):
        st.divider()
        _section_intro(
            "외부 환헤지 조합 참고 결과",
            "kb_macro_ai 결과를 현재 거래와 분리 검증합니다",
            "local_cli 모드에서는 확정된 단일 USD 수입 지급 거래를 "
            "고정된 kb_macro_ai 모델에 전달합니다. 기존 Stage 3를 "
            "대체하거나 공식 상품·상담 리포트 순위에 합치지 않습니다.",
        )
        kb_macro_mode = getattr(settings, "kb_macro_hedge_mode", "off")
        current_stage2_input = _model_from_state(
            "stage2_input",
            Stage2Input,
        )
        if kb_macro_mode == "local_cli":
            st.info(
                "현재 확정 거래를 kb_macro_ai 모델로 새로 계산합니다. "
                "IMPORT · USD · 단일 지급 한 건만 지원하며, 가격은 "
                "상류 저장소의 목업 견적입니다."
            )
            with st.expander(
                "외부 모델 제약조건 입력",
                expanded=True,
            ):
                st.caption(
                    "다음 값은 기존 Stage 3에서 변환하지 않습니다. "
                    "kb_macro_ai 시연값을 시작점으로 표시하므로 테스트 "
                    "조건에 맞게 직접 확인·수정하세요."
                )
                cli_cols_1 = st.columns(3)
                cli_payment_certainty = cli_cols_1[0].text_input(
                    "지급 확정도 · 0~1",
                    value="1.0",
                    key="kb_macro_payment_certainty_widget",
                )
                cli_maximum_cost = cli_cols_1[1].text_input(
                    "허용 가능한 최대 원화 지급액",
                    value="135000000",
                    key="kb_macro_maximum_cost_widget",
                )
                cli_maximum_probability = cli_cols_1[2].text_input(
                    "최대 예산초과확률 · 0~1",
                    value="0.15",
                    key="kb_macro_maximum_probability_widget",
                )
                cli_cols_2 = st.columns(3)
                cli_risk_tolerance = cli_cols_2[0].selectbox(
                    "위험성향",
                    ["low", "medium", "high"],
                    index=1,
                    key="kb_macro_risk_tolerance_widget",
                )
                cli_maximum_ratio = cli_cols_2[1].text_input(
                    "최대 총 헤지비율 · 0~1",
                    value="1.0",
                    key="kb_macro_maximum_ratio_widget",
                )
                cli_option_budget = cli_cols_2[2].text_input(
                    "옵션 프리미엄 예산 · KRW",
                    value="1500000",
                    key="kb_macro_option_budget_widget",
                )
                cli_allowed_instruments = st.multiselect(
                    "허용 상품",
                    ["forward", "vanilla_usd_call"],
                    default=["forward", "vanilla_usd_call"],
                    key="kb_macro_allowed_instruments_widget",
                )
                cli_constraints_confirmed = st.checkbox(
                    "위 제약조건과 목업 선물환·옵션 견적을 참고 계산에 사용합니다",
                    value=False,
                    key="kb_macro_cli_constraints_confirmed_widget",
                )
            if st.button(
                "현재 수입 거래로 kb_macro_ai 계산하기",
                key="run_kb_macro_hedge_model",
                disabled=(
                    not cli_constraints_confirmed
                    or current_stage2_input is None
                    or stage2_result is None
                ),
            ):
                try:
                    cli_constraints = (
                        KbMacroHedgeExecutionConstraints(
                            payment_certainty=cli_payment_certainty,
                            maximum_acceptable_cost_krw=(
                                cli_maximum_cost
                            ),
                            maximum_budget_exceedance_probability=(
                                cli_maximum_probability
                            ),
                            risk_tolerance=cli_risk_tolerance,
                            maximum_total_hedge_ratio=(
                                cli_maximum_ratio
                            ),
                            option_premium_budget_krw=(
                                cli_option_budget
                            ),
                            allowed_instruments=(
                                cli_allowed_instruments
                            ),
                        )
                    )
                    reference = run_kb_macro_hedge_for_confirmed_trade(
                        settings=settings,
                        stage2_input=current_stage2_input,
                        stage2_result=stage2_result,
                        constraints=cli_constraints,
                        constraints_confirmed=(
                            cli_constraints_confirmed
                        ),
                    )
                    if reference is not None:
                        _save_model(
                            "kb_macro_hedge_reference",
                            reference,
                        )
                    st.rerun()
                except ValueError as exc:
                    st.error(
                        "외부 모델 입력을 확인하세요: {}".format(exc)
                    )
        else:
            binding_label = st.radio(
                "검증 범위",
                [
                    "외부 fixture 파일 자체 검증",
                    "현재 확정 거래와 금액·지급일 대조",
                ],
                key="kb_macro_hedge_binding_widget",
                help=(
                    "파일 자체 검증은 생성된 결과의 수학·계약만 검사합니다. "
                    "현재 거래 대조는 amount/date/cash/forward까지 "
                    "일치해야 합니다."
                ),
            )
            fixture_constraints_confirmed = st.checkbox(
                "외부 파일의 목업 제약조건을 참고 검증에 사용합니다",
                value=False,
                key="kb_macro_hedge_constraints_confirmed_widget",
            )
            if st.button(
                "외부 헤지 파일 검증하기",
                key="validate_kb_macro_hedge_reference",
                disabled=not fixture_constraints_confirmed,
            ):
                binding_mode = (
                    "CURRENT_CONFIRMED_TRADE"
                    if binding_label
                    == "현재 확정 거래와 금액·지급일 대조"
                    else "UPSTREAM_FIXTURE_SELF_TEST"
                )
                reference = evaluate_kb_macro_hedge_reference(
                    settings=settings,
                    stage2_input=current_stage2_input,
                    stage2_result=stage2_result,
                    binding_mode=binding_mode,
                    fixture_constraints_confirmed=(
                        fixture_constraints_confirmed
                    ),
                )
                if reference is not None:
                    _save_model(
                        "kb_macro_hedge_reference",
                        reference,
                    )
                st.rerun()
        kb_macro_reference = _model_from_state(
            "kb_macro_hedge_reference",
            KbMacroHedgeReferenceResult,
        )
        if kb_macro_reference is not None:
            _render_kb_macro_hedge_reference(kb_macro_reference)

with stage4_tab:
    stage2_result = _model_from_state("stage2_result", Stage2Result)
    stage3_result = _model_from_state("stage3_result", Stage3Result)
    if stage2_result is None or stage3_result is None:
        pass
    else:
        st.markdown(
            "<div class='stage-bridge'><span>선택 · 공식 상담정보</span></div>",
            unsafe_allow_html=True,
        )
        _section_intro(
            "선택 · 공식 출처",
            "필요하면 공식 금융상품·지원제도를 함께 확인합니다",
            "앞에서 계산한 대응 전략과 관련 있는 후보를 찾습니다. "
            "가입 자격·승인·한도·금리는 확정하지 않고 상담에서 "
            "확인할 항목으로 남깁니다.",
        )
        consultation_topics = _consultation_topics_from_state()
        strategy_terms = (
            stage3_result.candidates[0].required_product_types
            if stage3_result.candidates
            else []
        )
        default_query = build_official_candidate_query(
            consultation_topics=consultation_topics,
            additional_terms=strategy_terms
            + [
                "선물환",
                "환변동보험",
                "외화예금",
                "수출입대출",
                "정책자금",
                "보증상품",
            ],
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
                st.session_state.pop("stage4_result", None)
                st.session_state.pop("official_candidate_shortlist", None)
                st.session_state.pop("report_result", None)
                _rebuild_consultation_with_payment_statuses(
                    _installment_payment_statuses_from_state()
                )
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
                _save_workflow(workflow)
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
                shortlist = shortlist_official_candidates(
                    stage4_result=result,
                    trade_type=stage2_result.trade_type,
                    consultation_topics=consultation_topics,
                )
                extraction = _model_from_state(
                    "extraction",
                    TradeDocumentExtraction,
                )
                document_confirmation = _model_from_state(
                    "confirmation",
                    ConfirmationRecord,
                )
                stage1_load = _model_from_state(
                    "stage1_load",
                    Stage1LoadResult,
                )
                stage2_input = _model_from_state(
                    "stage2_input",
                    Stage2Input,
                )
                if (
                    extraction is None
                    or document_confirmation is None
                    or stage1_load is None
                    or stage2_input is None
                ):
                    raise RuntimeError(
                        "공식 후보를 상담자료에 연결할 확정 입력이 없습니다."
                    )
                decision_support = build_decision_support(
                    case_id=workflow.case_id,
                    extraction=extraction,
                    confirmation=document_confirmation,
                    stage1=stage1_load.scenario_set,
                    stage2_input=stage2_input,
                    stage2_result=stage2_result,
                    trade_settlement_risk=_model_from_state(
                        "trade_risk_assessment",
                        TradeSettlementRiskAssessment,
                    ),
                    country_environment=_model_from_state(
                        "country_environment_assessment",
                        CountryTradeEnvironmentAssessment,
                    ),
                    official_candidate_shortlist=shortlist,
                    installment_payment_statuses=(
                        _installment_payment_statuses_from_state()
                    ),
                    missing_information=list(
                        extraction.missing_required_fields
                    ),
                    confirmed_transaction=workflow.confirmed_transaction,
                )
                _save_model("stage4_result", result)
                _save_decision_support(decision_support)
                clear_downstream(st.session_state, 5)
                st.rerun()
            except (RuntimeError, TypeError, ValueError) as exc:
                st.error(str(exc))
        stage4_result = _model_from_state("stage4_result", Stage4Result)
        official_candidate_shortlist = _model_from_state(
            "official_candidate_shortlist",
            OfficialCandidateShortlist,
        )
        if stage4_result is not None:
            if official_candidate_shortlist is None:
                st.info(
                    "이전 형식의 검색 결과입니다. 현재 상담 항목에 맞춰 "
                    "공식 후보를 다시 찾으세요."
                )
            elif not official_candidate_shortlist.candidates:
                st.markdown(
                    "<div class='state-banner warning'><span class='state-icon'>!</span>"
                    "<div><strong>공식 출처에서 연결할 후보를 찾지 못했습니다</strong>"
                    "<p>현재 상담 필요 항목과 직접 맞는 상품을 임의로 만들지 "
                    "않았습니다. 검색 범위를 조정하거나 "
                    "거래은행에 직접 문의하세요.</p></div></div>",
                    unsafe_allow_html=True,
                )
            official_details = st.expander(
                "공식 후보 자세히 보기",
                expanded=False,
            )
            product_columns = official_details.columns(2)
            shortlist_candidates = (
                official_candidate_shortlist.candidates
                if official_candidate_shortlist is not None
                else []
            )
            for index, candidate in enumerate(shortlist_candidates):
                with product_columns[index % 2]:
                    with st.container(border=True):
                        st.caption(
                            "{} · 공식 출처 확인".format(
                                candidate.institution,
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
            if official_candidate_shortlist is not None:
                st.markdown(
                    "<div class='state-banner'><span class='state-icon'>→</span>"
                    "<div><strong>다음 단계는 사람과의 상담입니다</strong>"
                    "<p>표시 후보는 최대 3개이며 추천이나 승인 결과가 아닙니다. "
                    "공식 페이지와 거래은행에서 조건을 다시 확인하세요.</p></div></div>",
                    unsafe_allow_html=True,
                )
                with st.expander(
                    "고급 · 공식 후보 데이터",
                    expanded=False,
                ):
                    _advanced_downloads_title()
                    json_download(
                        label="공식 상담 후보 JSON",
                        value=official_candidate_shortlist,
                        filename="official_candidate_shortlist.json",
                        key="download_stage4",
                    )
                    for warning in official_candidate_shortlist.warnings:
                        st.caption("· {}".format(warning))

with stage5_tab:
    _section_intro(
        "결과 저장",
        "상담 준비가 완료되었습니다",
        "거래 요약, 위험 결과, 상담 우선순위, 부족정보, 준비자료와 "
        "질문을 하나의 상담 준비자료로 정리했습니다.",
    )
    consultation_packet = _model_from_state(
        "consultation_packet",
        ConsultationPacketResult,
    )
    if consultation_packet is None:
        st.markdown(
            "<div class='state-banner warning'><span class='state-icon'>3</span>"
            "<div><strong>먼저 금융 리스크 분석을 완료하세요</strong>"
            "<p>확정 거래와 환율·현금정보를 계산하면 상담 우선순위와 "
            "준비자료가 생성됩니다.</p></div></div>",
            unsafe_allow_html=True,
        )
    else:
        packet = consultation_packet.packet
        with st.container(key="result_actions"):
            action_columns = st.columns(2)
            action_columns[0].download_button(
                "상담 준비서 다운로드",
                data=consultation_packet.markdown,
                file_name="kb_consultation_handoff.md",
                mime="text/markdown",
                key="stage5_handoff_download",
                type="primary",
                width="stretch",
            )
            with action_columns[1].popover(
                "공식 출처 확인",
                use_container_width=True,
            ):
                _render_official_sources_body(consultation_packet)
        st.caption(
            "다운로드는 상담 준비자료 저장이며 실제 상담 예약·RM 전송·신청 "
            "또는 승인 완료를 의미하지 않습니다."
        )
        if packet.installment_payment_statuses:
            payment_status_panel = st.expander(
                "선지급 실제 입금 상태 확인",
                expanded=False,
            )
            payment_status_panel.caption(
                "이 확인은 상담용 부족정보만 갱신합니다. 계약상 예정 "
                "수취 노출액과 기존 금융분석 계산값은 변경하지 않습니다."
            )
            schedule_by_sequence = {
                item.sequence: item
                for item in packet.company_summary.payment_schedule
            }
            status_rows = []
            for item in packet.installment_payment_statuses:
                schedule = schedule_by_sequence.get(
                    item.installment_sequence
                )
                status_rows.append(
                    {
                        "회차": item.installment_sequence,
                        "예정금액": (
                            "{} {}".format(
                                schedule.currency,
                                schedule.amount_fx,
                            )
                            if (
                                schedule is not None
                                and schedule.amount_fx is not None
                            )
                            else "미확인"
                        ),
                        "예정일": (
                            schedule.scheduled_date
                            if schedule is not None
                            else None
                        ),
                        "실제 입금 상태": item.status,
                        "실제 입금일": (
                            item.actual_payment_date or ""
                        ),
                    }
                )
            edited_payment_statuses = payment_status_panel.data_editor(
                status_rows,
                key="consultation_payment_status_editor",
                hide_index=True,
                width="stretch",
                disabled=["회차", "예정금액", "예정일"],
                column_config={
                    "실제 입금 상태": st.column_config.SelectboxColumn(
                        options=[
                            "UNKNOWN",
                            "CONFIRMED_RECEIVED",
                            "CONFIRMED_NOT_RECEIVED",
                        ],
                        required=True,
                    ),
                    "실제 입금일": st.column_config.TextColumn(
                        help=(
                            "CONFIRMED_RECEIVED이면 YYYY-MM-DD로 "
                            "입력하세요."
                        )
                    ),
                },
            )
            if payment_status_panel.button(
                "선지급 입금 상태 반영",
                key="confirm_installment_payment_status",
            ):
                try:
                    updated_statuses: List[
                        InstallmentPaymentStatus
                    ] = []
                    for row in edited_payment_statuses.to_dict(
                        "records"
                    ):
                        status = str(row["실제 입금 상태"])
                        actual_date = _date_or_none(
                            row.get("실제 입금일")
                        )
                        if (
                            status == "CONFIRMED_RECEIVED"
                            and actual_date is None
                        ):
                            raise ValueError(
                                "입금 확인 회차에는 실제 입금일이 "
                                "필요합니다."
                            )
                        updated_statuses.append(
                            InstallmentPaymentStatus(
                                installment_sequence=int(row["회차"]),
                                status=status,
                                actual_payment_date=(
                                    actual_date
                                    if status
                                    == "CONFIRMED_RECEIVED"
                                    else None
                                ),
                                confirmed_by=(
                                    "streamlit-user"
                                    if status != "UNKNOWN"
                                    else None
                                ),
                                confirmed_at=(
                                    datetime.now(
                                        timezone.utc
                                    ).isoformat()
                                    if status != "UNKNOWN"
                                    else None
                                ),
                                source=(
                                    "USER_CONFIRMED"
                                    if status != "UNKNOWN"
                                    else "UNCONFIRMED"
                                ),
                            )
                        )
                    _rebuild_consultation_with_payment_statuses(
                        updated_statuses
                    )
                    st.success(
                        "상담용 실제 입금 확인 상태를 반영했습니다."
                    )
                    st.rerun()
                except (TypeError, ValueError) as exc:
                    st.error(str(exc))
        with st.expander(
            "JSON 데이터 및 분석 근거",
            expanded=False,
        ):
            st.caption(
                "Case ID {} · 계산 버전 {}".format(
                    packet.case_id[:12],
                    packet.calculation_version,
                )
            )
            json_download(
                label="JSON 데이터 다운로드",
                value=packet,
                filename="kb_consultation_packet.json",
                key="download_consultation_packet_json_stage5",
            )
        with st.expander(
            "상담 준비서 미리보기",
            expanded=False,
        ):
            st.markdown(consultation_packet.markdown)

    extraction = _model_from_state("extraction", TradeDocumentExtraction)
    confirmation = _model_from_state("confirmation", ConfirmationRecord)
    stage1_load = _model_from_state("stage1_load", Stage1LoadResult)
    stage2_result = _model_from_state("stage2_result", Stage2Result)
    stage3_result = _model_from_state("stage3_result", Stage3Result)
    stage4_result = _model_from_state("stage4_result", Stage4Result)
    official_candidate_shortlist = _model_from_state(
        "official_candidate_shortlist",
        OfficialCandidateShortlist,
    )
    all_ready = all(
        item is not None
        for item in (
            consultation_packet,
            extraction,
            confirmation,
            stage1_load,
            stage2_result,
            stage3_result,
            stage4_result,
            official_candidate_shortlist,
        )
    )
    report_result = _model_from_state(
        "report_result",
        ReportResult,
    )
    missing_report_steps: List[str] = []
    if any(
        item is None
        for item in (
            consultation_packet,
            extraction,
            confirmation,
            stage1_load,
            stage2_result,
        )
    ):
        missing_report_steps.append(
            "1~2단계에서 거래 확인과 금융 리스크 분석을 완료하세요."
        )
    if stage3_result is None:
        missing_report_steps.append(
            "3단계 ‘상담 준비’에서 ‘대응안 비교하기’를 누르세요."
        )
    if (
        stage3_result is not None
        and (
            stage4_result is None
            or official_candidate_shortlist is None
        )
    ):
        missing_report_steps.append(
            "3단계 하단에서 ‘우리 거래에 맞는 공식 상담 후보 찾기’를 "
            "누르세요."
        )
    report_panel = st.expander(
        "고급 · 통합 보고서와 기술정보",
        expanded=False,
    )
    report_panel.markdown("#### 대응안과 공식자료까지 포함하기")
    if not all_ready and report_result is None:
        report_panel.info(
            "기본 상담 준비서는 위에서 이미 완성됩니다. 대응 시뮬레이션과 "
            "공식 후보 연결을 실행하면 거래·결제 위험까지 포함한 통합 "
            "리포트도 만들 수 있습니다."
        )
        if missing_report_steps:
            report_panel.markdown(
                "**통합 상담 리포트 생성 전 남은 단계**"
            )
            for index, step in enumerate(missing_report_steps, start=1):
                report_panel.write("{}. {}".format(index, step))
        report_panel.button(
            "통합 상담 리포트 만들기",
            key="generate_report",
            disabled=True,
            help="위에 표시된 남은 단계를 먼저 완료하세요.",
        )
    elif all_ready:
        if report_panel.button(
            (
                "통합 상담 리포트 다시 만들기"
                if report_result is not None
                else "통합 상담 리포트 만들기"
            ),
            key="generate_report",
        ):
            st.session_state.pop("report_result", None)
            workflow = _workflow_from_state()
            if workflow is None:
                st.error("분석 세션이 없습니다. 거래 확인부터 다시 시작하세요.")
                st.stop()
            workflow = orchestrator.run_report(
                workflow,
                consultation_packet=consultation_packet.packet,
            )
            _save_workflow(workflow)
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
            st.rerun()

    if report_result is not None:
        report_panel.markdown(
            "<div class='state-banner'><span class='state-icon'>✓</span>"
            "<div><strong>통합 상담 리포트가 완성되었습니다</strong>"
            "<p>수치와 출처를 다시 확인한 뒤 거래은행 또는 보험기관과 "
            "공유하세요.</p></div></div>",
            unsafe_allow_html=True,
        )
        report_panel.download_button(
            "통합 상담 리포트 다운로드",
            data=report_result.markdown,
            file_name="trade_finance_decision_report.md",
            mime="text/markdown",
            key="download_report_md",
            width="stretch",
        )
        report_panel.download_button(
            "근거 데이터 JSON",
            data=json.dumps(
                report_result.report_json,
                ensure_ascii=False,
                indent=2,
            ),
            file_name="trade_finance_decision_report.json",
            mime="application/json",
            key="download_report_json",
            width="stretch",
        )
        report_panel.markdown("#### 통합 상담 리포트 미리보기")
        report_panel.markdown(report_result.markdown)
        report_panel.caption(
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
