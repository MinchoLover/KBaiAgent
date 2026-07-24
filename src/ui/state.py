import hashlib
from typing import Iterable


PIPELINE_KEYS = (
    "extraction",
    "extraction_original",
    "extraction_validation",
    "upload_metadata",
    "confirmation",
    "confirmation_validation",
    "stage0_output",
    "stage2_document_input",
    "stage1_load",
    "stage2_input",
    "stage2_result",
    "risk_assessment",
    "consultation_topics",
    "consultation_packet",
    "stage3_result",
    "stage4_result",
    "report_result",
    "workflow_state",
)

REVIEW_WIDGET_KEYS = (
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
    "review_seller_name_widget",
    "review_seller_country_widget",
    "review_buyer_name_widget",
    "review_buyer_country_widget",
    "installment_editor",
)

CONFIRMATION_WIDGET_KEYS = (
    "confirmed_due_widget",
    "confirm_trade_type_widget",
    "confirm_currency_widget",
    "confirm_amount_widget",
    "confirm_due_widget",
)

STAGE1_WIDGET_KEYS = (
    "stage1_mode_widget",
    "stage1_base_rate_widget",
    "stage1_source_type_widget",
    "stage1_json_upload",
    "stage1_endpoint_widget",
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

STAGE3_WIDGET_KEYS = (
    "stage3_grid_widget",
    "stage3_stability_widget",
)

STAGE4_WIDGET_KEYS = (
    "stage4_query_widget",
    "stage4_search_mode_widget",
)

DOWNSTREAM_WIDGET_KEYS = (
    CONFIRMATION_WIDGET_KEYS
    + STAGE1_WIDGET_KEYS
    + STAGE2_WIDGET_KEYS
    + STAGE3_WIDGET_KEYS
    + STAGE4_WIDGET_KEYS
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


def clear_downstream(state: object, from_stage: int) -> None:
    stage_keys = {
        0: PIPELINE_KEYS,
        1: (
            "stage1_load",
            "stage2_input",
            "stage2_result",
            "risk_assessment",
            "consultation_topics",
            "consultation_packet",
            "stage3_result",
            "stage4_result",
            "report_result",
        ),
        2: (
            "stage2_input",
            "stage2_result",
            "risk_assessment",
            "consultation_topics",
            "consultation_packet",
            "stage3_result",
            "stage4_result",
            "report_result",
        ),
        3: (
            "risk_assessment",
            "consultation_topics",
            "consultation_packet",
            "stage3_result",
            "stage4_result",
            "report_result",
        ),
        4: ("stage4_result", "report_result"),
        5: ("report_result",),
    }
    stage_widget_keys = {
        0: TRANSACTION_WIDGET_KEYS,
        1: (
            STAGE1_WIDGET_KEYS
            + STAGE2_WIDGET_KEYS
            + STAGE3_WIDGET_KEYS
            + STAGE4_WIDGET_KEYS
        ),
        2: STAGE2_WIDGET_KEYS + STAGE3_WIDGET_KEYS + STAGE4_WIDGET_KEYS,
        3: STAGE3_WIDGET_KEYS + STAGE4_WIDGET_KEYS,
        4: STAGE4_WIDGET_KEYS,
        5: (),
    }
    clear_keys(
        state,
        stage_keys.get(from_stage, ())
        + stage_widget_keys.get(from_stage, ()),
    )


def clear_confirmation_and_later(state: object) -> None:
    clear_keys(
        state,
        (
            "confirmation",
            "confirmation_validation",
            "stage0_output",
            "stage2_document_input",
            "stage1_load",
            "stage2_input",
            "stage2_result",
            "risk_assessment",
            "consultation_topics",
            "consultation_packet",
            "stage3_result",
            "stage4_result",
            "report_result",
        )
        + DOWNSTREAM_WIDGET_KEYS,
    )


def clear_review_widgets(state: object) -> None:
    clear_keys(state, REVIEW_WIDGET_KEYS)


def clear_transaction_widgets(state: object) -> None:
    clear_keys(state, TRANSACTION_WIDGET_KEYS)
