import hashlib
from typing import Iterable

from src.domain.consultation_models import ConsultationPacketResult
from src.domain.product_models import (
    AuxiliaryServiceCandidates,
    OFFICIAL_CANDIDATE_INPUT_FIELDS,
    OfficialCandidateInputProfile,
    OfficialCandidateShortlist,
    assess_official_candidate_input_profile,
)
from src.domain.report_models import ReportResult
from src.workflow.result import StageStatus
from src.workflow.state import WorkflowState


PIPELINE_KEYS = (
    "extraction",
    "extraction_original",
    "extraction_validation",
    "upload_metadata",
    "document_analysis_provenance",
    "confirmation",
    "confirmation_validation",
    "confirmed_transaction",
    "stage0_output",
    "stage2_document_input",
    "stage1_load",
    "market_integration",
    "stage2_input",
    "stage2_result",
    "cashflow_error",
    "trade_risk_confirmation",
    "trade_risk_assessment",
    "country_environment_input",
    "country_environment_assessment",
    "country_environment_trace",
    "country_economic_interpretation_result",
    "trade_statistics_request",
    "trade_statistics_result",
    "trade_statistics_interpretation_result",
    "trade_statistics_trace",
    "trade_statistics_error",
    "risk_assessment",
    "consultation_topics",
    "installment_payment_statuses",
    "consultation_packet",
    "stage3_result",
    "kb_macro_hedge_reference",
    "integration_readiness",
    "stage4_result",
    "official_candidate_input_profile",
    "official_candidate_shortlist",
    "auxiliary_service_candidates",
    "report_result",
    "report_download_payload",
    "official_candidate_auto_refresh",
    "official_profile_saved_notice",
    "official_profile_warning_confirmation_fingerprint",
    "workflow_state",
    "review_audit_trail",
    "party_role_auto_match_notice",
)

REVIEW_WIDGET_KEYS = (
    "review_company_role_widget",
    "review_company_country_widget",
    "review_document_type_widget",
    "review_document_number_widget",
    "review_currency_widget",
    "review_amount_due_widget",
    "review_grand_total_widget",
    "review_issue_date_widget",
    "review_contract_date_widget",
    "review_shipment_date_widget",
    "review_explicit_due_date_widget",
    "review_payment_terms_widget",
    "review_incoterm_widget",
    "review_trade_type_widget",
    "review_trade_type_choice_widget",
    "review_seller_name_widget",
    "review_seller_country_widget",
    "review_buyer_name_widget",
    "review_buyer_country_widget",
    "installment_editor",
)

CONFIRMATION_WIDGET_KEYS = (
    "confirmed_due_widget",
    "confirm_company_role_widget",
    "confirm_trade_type_widget",
    "confirm_currency_widget",
    "confirm_amount_widget",
    "confirm_due_widget",
    "confirm_evidence_override_widget",
)

STAGE1_WIDGET_KEYS = (
    "stage1_mode_widget",
    "stage1_base_rate_widget",
    "stage1_source_type_widget",
    "stage1_json_upload",
    "stage1_endpoint_widget",
    "stage1_provider_widget",
    "spot_provider_widget",
    "spot_confirmed_widget",
)

STAGE2_WIDGET_KEYS = (
    "stage2_current_cash_widget",
    "stage2_minimum_buffer_widget",
    "stage2_credit_limit_widget",
    "stage2_usable_fx_widget",
    "stage2_acceptable_loss_widget",
    "stage2_as_of_widget",
    "stage2_same_flow_amount_widget",
    "stage2_same_flow_date_widget",
    "stage2_same_flow_direction_widget",
    "stage2_hedge_amount_widget",
    "stage2_locked_rate_widget",
    "stage2_hedge_fee_widget",
    "stage2_bank_spread_widget",
    "stage2_bank_fee_widget",
    "krw_cashflow_editor",
    "stage2_revenue_reduction_widget",
    "stage2_revenue_delay_widget",
    "stage2_cost_increase_widget",
)

TRADE_RISK_WIDGET_KEYS = (
    "trade_risk_relationship_widget",
    "trade_risk_advance_status_widget",
    "trade_risk_advance_percent_widget",
    "trade_risk_balance_method_widget",
    "trade_risk_term_basis_widget",
    "trade_risk_term_days_widget",
    "trade_risk_protection_status_widget",
    "trade_risk_protection_types_widget",
    "trade_risk_protection_applicability_widget",
    "trade_risk_confirm_widget",
)

TRADE_STATISTICS_WIDGET_KEYS = (
    "trade_statistics_hs_code_widget",
    "trade_statistics_hs_confirmed_widget",
)

STAGE3_WIDGET_KEYS = (
    "stage3_grid_widget",
    "stage3_stability_widget",
    "stage3_forward_fee_widget",
    "stage3_staged_fee_widget",
    "stage3_max_forward_widget",
    "stage3_staged_risk_widget",
    "stage3_forward_rate_widget",
)

KB_MACRO_HEDGE_WIDGET_KEYS = (
    "kb_macro_hedge_binding_widget",
    "kb_macro_hedge_constraints_confirmed_widget",
    "kb_macro_payment_certainty_widget",
    "kb_macro_maximum_cost_widget",
    "kb_macro_maximum_probability_widget",
    "kb_macro_risk_tolerance_widget",
    "kb_macro_maximum_ratio_widget",
    "kb_macro_option_budget_widget",
    "kb_macro_allowed_instruments_widget",
    "kb_macro_cli_constraints_confirmed_widget",
)

OFFICIAL_CANDIDATE_PROFILE_WIDGET_KEYS = tuple(
    "official_profile_{}_widget".format(field_name)
    for field_name in OFFICIAL_CANDIDATE_INPUT_FIELDS
)


STAGE4_WIDGET_KEYS = (
    "stage4_query_widget",
    "stage4_search_mode_widget",
) + OFFICIAL_CANDIDATE_PROFILE_WIDGET_KEYS

CONSULTATION_WIDGET_KEYS = (
    "consultation_payment_status_editor",
)

DOWNSTREAM_WIDGET_KEYS = (
    CONFIRMATION_WIDGET_KEYS
    + TRADE_RISK_WIDGET_KEYS
    + TRADE_STATISTICS_WIDGET_KEYS
    + STAGE1_WIDGET_KEYS
    + STAGE2_WIDGET_KEYS
    + STAGE3_WIDGET_KEYS
    + KB_MACRO_HEDGE_WIDGET_KEYS
    + STAGE4_WIDGET_KEYS
    + CONSULTATION_WIDGET_KEYS
)

TRANSACTION_WIDGET_KEYS = REVIEW_WIDGET_KEYS + DOWNSTREAM_WIDGET_KEYS


def input_signature(
    *,
    mode: str,
    company_role: str,
    company_country: str,
    file_bytes: bytes,
    filename: str = "",
) -> str:
    digest = hashlib.sha256()
    parts = (
        mode.encode("utf-8"),
        company_role.encode("utf-8"),
        company_country.encode("utf-8"),
        filename.encode("utf-8"),
        file_bytes,
    )
    for part in parts:
        digest.update(len(part).to_bytes(8, byteorder="big"))
        digest.update(part)
    return digest.hexdigest()


def clear_keys(state: object, keys: Iterable[str]) -> None:
    for key in keys:
        if key in state:
            del state[key]


def sync_input_signature(state: object, signature: str) -> bool:
    previous = state.get("input_signature")
    changed = previous is not None and previous != signature
    if changed:
        clear_keys(state, PIPELINE_KEYS + TRANSACTION_WIDGET_KEYS)
    state["input_signature"] = signature
    return changed


def clear_downstream(
    state: object,
    from_stage: int,
    *,
    clear_widgets: bool = True,
) -> None:
    stage_keys = {
        0: PIPELINE_KEYS,
        1: (
            "stage1_load",
            "market_integration",
            "stage2_input",
            "stage2_result",
            "cashflow_error",
            "risk_assessment",
            "consultation_topics",
            "installment_payment_statuses",
            "consultation_packet",
            "stage3_result",
            "kb_macro_hedge_reference",
            "integration_readiness",
            "stage4_result",
            "official_candidate_shortlist",
            "report_result",
            "report_download_payload",
            "official_candidate_auto_refresh",
            "official_profile_saved_notice",
            "official_profile_warning_confirmation_fingerprint",
            "official_profile_validation_notice",
        ),
        2: (
            "stage2_input",
            "stage2_result",
            "cashflow_error",
            "risk_assessment",
            "consultation_topics",
            "consultation_packet",
            "stage3_result",
            "kb_macro_hedge_reference",
            "integration_readiness",
            "stage4_result",
            "official_candidate_shortlist",
            "report_result",
            "report_download_payload",
        ),
        3: (
            "risk_assessment",
            "consultation_topics",
            "consultation_packet",
            "stage3_result",
            "kb_macro_hedge_reference",
            "stage4_result",
            "official_candidate_shortlist",
            "report_result",
            "report_download_payload",
        ),
        4: (
            "stage4_result",
            "official_candidate_shortlist",
            "report_result",
            "report_download_payload",
        ),
        5: ("report_result", "report_download_payload"),
    }
    stage_widget_keys = {
        0: TRANSACTION_WIDGET_KEYS,
        1: (
            STAGE1_WIDGET_KEYS
            + STAGE2_WIDGET_KEYS
            + STAGE3_WIDGET_KEYS
            + KB_MACRO_HEDGE_WIDGET_KEYS
            + STAGE4_WIDGET_KEYS
            + CONSULTATION_WIDGET_KEYS
        ),
        2: (
            STAGE2_WIDGET_KEYS
            + STAGE3_WIDGET_KEYS
            + KB_MACRO_HEDGE_WIDGET_KEYS
            + STAGE4_WIDGET_KEYS
        ),
        3: (
            STAGE3_WIDGET_KEYS
            + KB_MACRO_HEDGE_WIDGET_KEYS
            + STAGE4_WIDGET_KEYS
        ),
        4: STAGE4_WIDGET_KEYS,
        5: (),
    }
    clear_keys(
        state,
        stage_keys.get(from_stage, ())
        + (
            stage_widget_keys.get(from_stage, ())
            if clear_widgets
            else ()
        ),
    )


def clear_confirmation_and_later(state: object) -> None:
    clear_keys(
        state,
        (
            "confirmation",
            "confirmation_validation",
            "confirmed_transaction",
            "stage0_output",
            "stage2_document_input",
            "stage1_load",
            "market_integration",
            "stage2_input",
            "stage2_result",
            "cashflow_error",
            "trade_risk_confirmation",
            "trade_risk_assessment",
            "country_environment_input",
            "country_environment_assessment",
            "country_environment_trace",
            "country_economic_interpretation_result",
            "trade_statistics_request",
            "trade_statistics_result",
            "trade_statistics_interpretation_result",
            "trade_statistics_trace",
            "trade_statistics_error",
            "risk_assessment",
            "consultation_topics",
            "installment_payment_statuses",
            "consultation_packet",
            "stage3_result",
            "kb_macro_hedge_reference",
            "stage4_result",
            "official_candidate_input_profile",
            "auxiliary_service_candidates",
            "official_candidate_shortlist",
            "report_result",
            "report_download_payload",
            "workflow_state",
        )
        + DOWNSTREAM_WIDGET_KEYS,
    )


def clear_trade_risk_and_related(state: object) -> None:
    clear_keys(
        state,
        (
            "trade_risk_confirmation",
            "trade_risk_assessment",
            "country_environment_input",
            "country_environment_assessment",
            "country_environment_trace",
            "country_economic_interpretation_result",
            "consultation_topics",
            "auxiliary_service_candidates",
            "official_candidate_shortlist",
            "consultation_packet",
            "report_result",
            "report_download_payload",
            "official_candidate_auto_refresh",
            "official_profile_saved_notice",
            "official_profile_warning_confirmation_fingerprint",
        ),
    )


def clear_country_environment_and_related(state: object) -> None:
    clear_keys(
        state,
        (
            "country_environment_input",
            "country_environment_assessment",
            "country_environment_trace",
            "country_economic_interpretation_result",
            "consultation_topics",
            "consultation_packet",
            "report_result",
            "report_download_payload",
        ),
    )


def clear_official_candidate_outputs(state: object) -> None:
    """상품 전용 확인값 변경 시 계산 결과를 보존하고 후보 이후만 지운다."""

    clear_keys(
        state,
        (
            "official_candidate_shortlist",
            "auxiliary_service_candidates",
            "consultation_packet",
            "report_result",
            "report_download_payload",
            "official_candidate_auto_refresh",
            "official_profile_saved_notice",
            "official_profile_warning_confirmation_fingerprint",
        ),
    )
    workflow_value = state.get("workflow_state")
    workflow_state = (
        workflow_value
        if isinstance(workflow_value, WorkflowState)
        else WorkflowState.model_validate(workflow_value)
        if workflow_value is not None
        else None
    )
    if workflow_state is not None:
        updated = workflow_state.model_copy(
            update={
                "report": None,
                "report_draft": None,
                "critic_result": None,
                "final_report": None,
                "rewrite_count": 0,
                "final_status": StageStatus.PENDING,
            }
        )
        state["workflow_state"] = (
            updated
            if isinstance(workflow_value, WorkflowState)
            else updated.model_dump()
        )


def update_official_candidate_input_profile(
    state: object,
    profile: OfficialCandidateInputProfile,
) -> bool:
    """WorkflowState 한 곳에 profile을 저장하고 상품 후보 이후만 무효화한다."""

    workflow_value = state.get("workflow_state")
    if workflow_value is None:
        raise ValueError("상품 입력 profile을 저장할 WorkflowState가 없습니다.")
    workflow_state = WorkflowState.model_validate(workflow_value)
    confirmed_transaction = workflow_state.confirmed_transaction
    if confirmed_transaction is None:
        raise ValueError("상품 입력 profile은 confirmed transaction 이후 저장합니다.")
    if (
        profile.bound_transaction_fingerprint
        != confirmed_transaction.input_fingerprint
    ):
        raise ValueError(
            "상품 입력 profile이 현재 confirmed transaction과 다릅니다."
        )
    profile_validation = assess_official_candidate_input_profile(profile)
    if profile_validation.hard_blocking_issues:
        raise ValueError(
            "상품 입력 충돌을 먼저 수정해야 합니다: {}".format(
                " ".join(
                    issue.user_message
                    for issue in profile_validation.hard_blocking_issues
                )
            )
        )
    current = workflow_state.official_candidate_input_profile
    if (
        current is not None
        and current.input_fingerprint == profile.input_fingerprint
    ):
        validate_official_candidate_artifact_state(state)
        return False
    clear_official_candidate_outputs(state)
    cleared_workflow = WorkflowState.model_validate(state["workflow_state"])
    updated = cleared_workflow.model_copy(
        update={"official_candidate_input_profile": profile}
    )
    state["workflow_state"] = (
        updated
        if isinstance(workflow_value, WorkflowState)
        else updated.model_dump()
    )
    return True


def validate_official_candidate_artifact_state(state: object) -> None:
    """현재 거래·profile·후보·Packet·report의 binding을 fail-closed한다."""

    if "official_candidate_input_profile" in state:
        raise ValueError(
            "상품 입력 profile은 session_state에 별도 복제할 수 없습니다."
        )
    workflow_value = state.get("workflow_state")
    if workflow_value is None:
        raise ValueError("상품 후보 artifact를 검증할 WorkflowState가 없습니다.")
    workflow_state = WorkflowState.model_validate(workflow_value)
    transaction = workflow_state.confirmed_transaction
    profile = workflow_state.official_candidate_input_profile
    if profile is not None and (
        transaction is None
        or profile.bound_transaction_fingerprint
        != transaction.input_fingerprint
    ):
        raise ValueError(
            "WorkflowState profile이 현재 confirmed transaction과 다릅니다."
        )

    packet_value = state.get("consultation_packet")
    packet = (
        ConsultationPacketResult.model_validate(packet_value).packet
        if packet_value is not None
        else None
    )
    if packet is not None:
        expected_transaction = (
            transaction.input_fingerprint
            if transaction is not None
            else None
        )
        if packet.confirmed_transaction_fingerprint != expected_transaction:
            raise ValueError(
                "ConsultationPacket이 현재 confirmed transaction과 다릅니다."
            )
        packet_profile = packet.official_candidate_input_profile
        if (packet_profile is None) != (profile is None) or (
            packet_profile is not None
            and profile is not None
            and packet_profile.input_fingerprint
            != profile.input_fingerprint
        ):
            raise ValueError("ConsultationPacket이 현재 profile과 다릅니다.")

    shortlist_value = state.get("official_candidate_shortlist")
    if shortlist_value is not None:
        if packet is None:
            raise ValueError("Packet 없는 금융후보 artifact는 사용할 수 없습니다.")
        shortlist = OfficialCandidateShortlist.model_validate(shortlist_value)
        if shortlist != packet.official_candidate_shortlist:
            raise ValueError("금융후보 artifact가 최신 Packet과 다릅니다.")

    auxiliary_value = state.get("auxiliary_service_candidates")
    if auxiliary_value is not None:
        if packet is None:
            raise ValueError("Packet 없는 보조서비스 artifact는 사용할 수 없습니다.")
        auxiliary = AuxiliaryServiceCandidates.model_validate(auxiliary_value)
        if auxiliary != packet.auxiliary_service_candidates:
            raise ValueError("보조서비스 artifact가 최신 Packet과 다릅니다.")

    reports = [state.get("report_result"), workflow_state.final_report]
    for report_value in reports:
        if report_value is None:
            continue
        if packet is None:
            raise ValueError("Packet 없는 Stage5 report는 사용할 수 없습니다.")
        report = ReportResult.model_validate(report_value)
        report_packet_hash = (
            report.report_json.get("consultation", {}).get("input_hash")
        )
        if report_packet_hash != packet.input_hash:
            raise ValueError("Stage5 report가 최신 ConsultationPacket과 다릅니다.")


def clear_review_widgets(state: object) -> None:
    clear_keys(state, REVIEW_WIDGET_KEYS)


def clear_transaction_widgets(state: object) -> None:
    clear_keys(state, TRANSACTION_WIDGET_KEYS)
