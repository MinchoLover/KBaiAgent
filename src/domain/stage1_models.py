from typing import List, Literal, Optional

from pydantic import Field

from schemas import StrictModel


class ScenarioPoint(StrictModel):
    name: str = Field(min_length=1)
    rate: str
    is_base: bool = False
    probability: Optional[str] = None
    source_kind: Literal[
        "LEGACY",
        "MANUAL_STRESS",
        "SPOT_BASE",
        "STAGE1_MODEL_QUANTILE",
        "DETERMINISTIC_STRESS",
    ] = "LEGACY"
    horizon_trading_days: Optional[int] = Field(default=None, gt=0)
    warnings: List[str] = Field(default_factory=list)


class Stage1ScenarioSet(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    currency: str
    quote_convention: Literal["KRW_PER_1_FC"] = "KRW_PER_1_FC"
    rate_unit_foreign_currency: str = "1"
    as_of: str
    target_date: str
    kind: Literal["FORECAST", "STRESS"]
    scenarios: List[ScenarioPoint] = Field(min_length=1)


class NormalizedScenarioSet(Stage1ScenarioSet):
    probability_valid: bool = False
    application_rule: str
    warnings: List[str] = Field(default_factory=list)


class Stage1LoadResult(StrictModel):
    source: Literal[
        "MANUAL",
        "EXTERNAL",
        "MANUAL_FALLBACK",
        "STAGE1_MODEL",
        "STAGE1_MODEL_FALLBACK",
    ]
    scenario_set: NormalizedScenarioSet
    warnings: List[str] = Field(default_factory=list)
