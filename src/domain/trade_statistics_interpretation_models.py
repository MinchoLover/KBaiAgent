from typing import Literal, Optional

from pydantic import Field

from schemas import StrictModel
from src.domain.trade_statistics_models import (
    TradeStatisticsProviderStatus,
    TradeStatisticsSourceReference,
)


TradeExportChangeDirection = Literal[
    "INCREASED",
    "DECREASED",
    "UNCHANGED",
    "UNAVAILABLE",
]
TradeBalanceDirection = Literal[
    "SURPLUS",
    "DEFICIT",
    "BALANCED",
    "UNAVAILABLE",
]
TradeStatisticsInterpretationStatus = Literal[
    "AI_VALIDATED",
    "DETERMINISTIC_FALLBACK",
]
TradeStatisticsInterpretationFallbackReason = Literal[
    "AI_DISABLED",
    "NO_API_KEY",
    "API_FAILURE",
    "PARSE_FAILURE",
    "VALIDATION_FAILED",
    "DATA_UNAVAILABLE",
]


class TradeStatisticsInterpretationInput(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    prompt_version: str
    reporting_country_code: str = Field(pattern=r"^[A-Z]{2}$")
    partner_country_code: str = Field(pattern=r"^[A-Z]{2}$")
    partner_country_name: str
    trade_direction: Literal["IMPORT", "EXPORT"]
    observation_period: str
    comparison_period: Optional[str] = None
    latest_12m_export_value: Optional[str] = None
    latest_12m_import_value: Optional[str] = None
    latest_12m_trade_balance: Optional[str] = None
    previous_12m_export_value: Optional[str] = None
    export_change_rate: Optional[str] = None
    export_change_direction: TradeExportChangeDirection
    trade_balance_direction: TradeBalanceDirection
    data_source_type: TradeStatisticsProviderStatus
    source_reference: Optional[TradeStatisticsSourceReference] = None
    snapshot_version: Optional[str] = None
    source_as_of: Optional[str] = None
    trade_statistics_result_fingerprint: str = Field(
        pattern=r"^[a-f0-9]{64}$"
    )
    normalized_snapshot_fingerprint: str = Field(
        pattern=r"^[a-f0-9]{64}$"
    )
    confirmed_transaction_fingerprint: str = Field(
        pattern=r"^[a-f0-9]{64}$"
    )
    model_configuration_fingerprint: str = Field(
        pattern=r"^[a-f0-9]{64}$"
    )
    input_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class TradeStatisticsInterpretationDraft(StrictModel):
    summary: str = Field(min_length=1, max_length=240)
    limitation: str = Field(min_length=1, max_length=280)


class TradeStatisticsInterpretationResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    prompt_version: str
    status: TradeStatisticsInterpretationStatus
    fallback_reason: Optional[
        TradeStatisticsInterpretationFallbackReason
    ] = None
    reporting_country_code: str = Field(pattern=r"^[A-Z]{2}$")
    partner_country_code: str = Field(pattern=r"^[A-Z]{2}$")
    trade_direction: Literal["IMPORT", "EXPORT"]
    export_change_direction: TradeExportChangeDirection
    source_result_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalized_snapshot_fingerprint: str = Field(
        pattern=r"^[a-f0-9]{64}$"
    )
    confirmed_transaction_fingerprint: str = Field(
        pattern=r"^[a-f0-9]{64}$"
    )
    model_configuration_fingerprint: str = Field(
        pattern=r"^[a-f0-9]{64}$"
    )
    input_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    generation_model: Optional[str] = None
    summary: str
    limitation: str
