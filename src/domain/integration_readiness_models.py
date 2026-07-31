from typing import List, Literal, Optional

from pydantic import Field

from schemas import StrictModel


IntegrationReadinessStatus = Literal[
    "READY",
    "DEGRADED",
    "BLOCKED",
    "DISABLED",
    "NOT_CHECKED",
]


class IntegrationReadinessCheck(StrictModel):
    check: str
    status: IntegrationReadinessStatus
    summary: str
    action: Optional[str] = None


class Stage1IntegrationReadiness(StrictModel):
    status: IntegrationReadinessStatus
    configured_provider: str
    endpoint_kind: str
    active_source: Optional[str] = None
    health_status: Optional[str] = None
    reachable: Optional[bool] = None
    forecast_available: Optional[bool] = None
    fallback_used: Optional[bool] = None
    schema_version: Optional[str] = None
    raw_schema_version: Optional[str] = None
    prediction_date: Optional[str] = None
    generated_at: Optional[str] = None
    market_data_latest_date: Optional[str] = None
    forecast_fresh: Optional[bool] = None
    partial_fallback_used: Optional[bool] = None
    research_only: Optional[bool] = None
    error_code: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    checks: List[IntegrationReadinessCheck] = Field(
        default_factory=list
    )


class SpotIntegrationReadiness(StrictModel):
    status: IntegrationReadinessStatus
    configured_provider: str
    configured_source: str
    active_source: Optional[str] = None
    credential_configured: bool = False
    manual_rate_configured: bool = False
    requires_transaction_confirmation: bool = False
    external_call_performed: bool = False
    warnings: List[str] = Field(default_factory=list)


class KbMacroAssetReadiness(StrictModel):
    asset: str
    configured: bool
    available: bool
    expected_sha256: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    actual_sha256: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    sha256_matches: Optional[bool] = None


class KbMacroExposureReadiness(StrictModel):
    status: IntegrationReadinessStatus
    supported: Optional[bool] = None
    scope: str = "SINGLE_USD_IMPORT_PAYABLE_ONLY"
    failed_checks: List[str] = Field(default_factory=list)
    detail: str


class KbMacroLocalCliE2EReadiness(StrictModel):
    status: IntegrationReadinessStatus
    executed: bool
    fixture_id: str = "SYNTHETIC_SINGLE_USD_IMPORT_100000_V1"
    api_free: bool = True
    provider_mode: Optional[str] = None
    result_status: Optional[str] = None
    pricing_status: Optional[str] = None
    validation_passed: Optional[bool] = None
    candidate_count: Optional[int] = Field(default=None, ge=0)
    candidate_ranks: List[int] = Field(default_factory=list)
    producer_commit_sha: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{40}$",
    )
    forecast_sha256: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    temporary_raw_output_deleted: Optional[bool] = None
    failed_checks: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class KbMacroIntegrationReadiness(StrictModel):
    status: IntegrationReadinessStatus
    feature_enabled: bool
    configured_mode: str
    provider_root_configured: bool
    provider_root_available: bool
    expected_producer_commit_sha: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{40}$",
    )
    actual_producer_commit_sha: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{40}$",
    )
    producer_commit_matches: Optional[bool] = None
    tracked_worktree_clean: Optional[bool] = None
    cli_available: Optional[bool] = None
    assets: List[KbMacroAssetReadiness] = Field(default_factory=list)
    exposure: KbMacroExposureReadiness
    local_cli_e2e: Optional[KbMacroLocalCliE2EReadiness] = None
    warnings: List[str] = Field(default_factory=list)
    checks: List[IntegrationReadinessCheck] = Field(
        default_factory=list
    )


class IntegrationReadinessReport(StrictModel):
    schema_version: Literal[
        "kbaiagent_integration_readiness_v1"
    ] = "kbaiagent_integration_readiness_v1"
    status: IntegrationReadinessStatus
    checked_at: str
    secret_values_exposed: Literal[False] = False
    stage1: Stage1IntegrationReadiness
    spot: SpotIntegrationReadiness
    kb_macro_hedge: KbMacroIntegrationReadiness
    checks: List[IntegrationReadinessCheck] = Field(
        default_factory=list
    )
