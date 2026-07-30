from typing import List, Literal, Optional

from pydantic import Field

from schemas import StrictModel


KbMacroHedgeStatus = Literal[
    "READY",
    "REFERENCE_ONLY",
    "VALIDATION_FAILED",
    "UNSUPPORTED_EXPOSURE",
    "UPSTREAM_UNAVAILABLE",
]


class KbMacroHedgeRequest(StrictModel):
    schema_version: Literal[
        "kbaiagent_kb_macro_hedge_request_v0"
    ] = "kbaiagent_kb_macro_hedge_request_v0"
    request_id: str
    binding_mode: Literal[
        "CURRENT_CONFIRMED_TRADE",
        "UPSTREAM_FIXTURE_SELF_TEST",
    ]
    source_trade_sha256: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    exposure_type: Literal["usd_payable"] = "usd_payable"
    currency: Literal["USD"] = "USD"
    amount_usd: str
    payment_date: str
    existing_usd_cash: str
    existing_forward_usd: str
    net_exposure_usd: str
    payment_certainty: str
    maximum_acceptable_cost_krw: str
    maximum_budget_exceedance_probability: str
    risk_tolerance: Literal["low", "medium", "high"]
    maximum_total_hedge_ratio: str
    option_premium_budget_krw: str
    allowed_instruments: List[
        Literal["forward", "vanilla_usd_call"]
    ]
    constraints_source: Literal[
        "UPSTREAM_FILE_CONFIRMED_BY_USER",
        "USER_CONFIRMED_UI",
    ] = "UPSTREAM_FILE_CONFIRMED_BY_USER"


class KbMacroHedgeExecutionConstraints(StrictModel):
    payment_certainty: str
    maximum_acceptable_cost_krw: str
    maximum_budget_exceedance_probability: str
    risk_tolerance: Literal["low", "medium", "high"]
    maximum_total_hedge_ratio: str
    option_premium_budget_krw: str
    allowed_instruments: List[
        Literal["forward", "vanilla_usd_call"]
    ]


class KbMacroHedgeCandidate(StrictModel):
    rank: int = Field(ge=1, le=3)
    strategy_type: Literal[
        "forward_only",
        "forward_and_call_option",
        "call_option_only",
        "unhedged",
    ]
    forward_ratio: str
    call_option_ratio: str
    unhedged_ratio: str
    forward_notional_usd: str
    call_option_notional_usd: str
    unhedged_notional_usd: str
    option_id: Optional[str] = None
    option_premium_krw: str
    expected_cost_krw: str
    cvar_95_cost_krw: str
    objective_score_krw: str


class KbMacroHedgeValidationCheck(StrictModel):
    check: str
    passed: bool
    field: Optional[str] = None
    detail: str


class KbMacroHedgeValidation(StrictModel):
    passed: bool
    checks: List[KbMacroHedgeValidationCheck] = Field(
        default_factory=list
    )
    failed_checks: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class KbMacroHedgeProvenance(StrictModel):
    producer_commit_sha: str = Field(
        pattern=r"^[a-f0-9]{40}$"
    )
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    forecast_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    hedge_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    forecast_schema_version: str
    hedge_schema_version: str
    prediction_date: str
    horizon_trading_days: int = Field(ge=1)
    forecast_filename: str
    hedge_filename: str
    model_config_sha256: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    market_history_sha256: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    quote_template_sha256: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    execution_method: Literal[
        "PREGENERATED_FILE",
        "PINNED_LOCAL_CLI",
    ] = "PREGENERATED_FILE"
    producer_commit_source: Literal[
        "OPERATOR_PINNED_CONFIGURATION"
    ] = "OPERATOR_PINNED_CONFIGURATION"
    upstream_contract_manifest_present: bool = False
    upstream_json_schemas_present: bool = False


class KbMacroHedgeReferenceResult(StrictModel):
    schema_version: Literal[
        "kbaiagent_kb_macro_hedge_reference_v0"
    ] = "kbaiagent_kb_macro_hedge_reference_v0"
    status: KbMacroHedgeStatus
    provider_mode: Literal["off", "fixture", "file", "local_cli"]
    pricing_status: Literal["MOCK", "ACTUAL", "UNKNOWN"]
    scope: Literal[
        "SINGLE_USD_IMPORT_PAYABLE_REFERENCE_ONLY"
    ] = "SINGLE_USD_IMPORT_PAYABLE_REFERENCE_ONLY"
    request: Optional[KbMacroHedgeRequest] = None
    provenance: Optional[KbMacroHedgeProvenance] = None
    validation: KbMacroHedgeValidation
    candidates: List[KbMacroHedgeCandidate] = Field(
        default_factory=list,
        max_length=3,
    )
    fallback_to_internal_stage3: bool = True
    published_to_stage4: bool = False
    warnings: List[str] = Field(default_factory=list)
