from typing import List, Literal, Optional

from pydantic import Field

from schemas import StrictModel


CountryEconomicIndicatorId = Literal[
    "GDP_GROWTH",
    "INFLATION",
    "CURRENT_ACCOUNT",
    "OECD_CLASSIFICATION",
]
InterpretationGenerationStatus = Literal[
    "AI_VALIDATED",
    "DETERMINISTIC_FALLBACK",
]
InterpretationFallbackReason = Literal[
    "AI_DISABLED",
    "NO_API_KEY",
    "API_FAILURE",
    "PARSE_FAILURE",
    "VALIDATION_FAILED",
]


class CountryEconomicSourceReference(StrictModel):
    source_record_id: str
    source_name: str
    source_axis: str
    official_url: str
    source_title: str
    as_of_date: str
    observation_period: str
    verified_at: str


class CountryEconomicIndicatorInput(StrictModel):
    indicator_id: CountryEconomicIndicatorId
    deterministic_value: Optional[str] = None
    deterministic_status: Optional[str] = None
    unit: str
    period: str
    as_of: str
    source: CountryEconomicSourceReference


class CountryEconomicTransactionContext(StrictModel):
    trade_direction: Literal["IMPORT", "EXPORT"]
    payment_method: str
    documentary_credit_status: str
    insurance_status: str
    guarantee_status: str


class CountryEconomicInterpretationInput(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    prompt_version: str
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    country_name: str
    country_environment_snapshot_fingerprint: str = Field(
        pattern=r"^[a-f0-9]{64}$"
    )
    country_environment_snapshot_hash: str = Field(
        pattern=r"^[a-f0-9]{64}$"
    )
    confirmed_transaction_fingerprint: str = Field(
        pattern=r"^[a-f0-9]{64}$"
    )
    model_configuration_fingerprint: str = Field(
        pattern=r"^[a-f0-9]{64}$"
    )
    transaction_context: CountryEconomicTransactionContext
    indicators: List[CountryEconomicIndicatorInput] = Field(
        min_length=1,
        max_length=4,
    )
    input_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class CountryEconomicInterpretationSection(StrictModel):
    indicator_id: str = Field(min_length=1, max_length=64)
    observation: str = Field(min_length=1, max_length=240)
    transaction_check: str = Field(min_length=1, max_length=240)


class CountryEconomicInterpretationDraft(StrictModel):
    overall_summary: str = Field(min_length=1, max_length=360)
    sections: List[CountryEconomicInterpretationSection] = Field(
        min_length=1,
        max_length=4,
    )
    limitations: List[str] = Field(
        min_length=1,
        max_length=3,
    )


class CountryEconomicInterpretationResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    prompt_version: str
    status: InterpretationGenerationStatus
    fallback_reason: Optional[InterpretationFallbackReason] = None
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    trade_direction: Literal["IMPORT", "EXPORT"]
    source_assessment_fingerprint: str = Field(
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
    overall_summary: str
    sections: List[CountryEconomicInterpretationSection]
    limitations: List[str]
