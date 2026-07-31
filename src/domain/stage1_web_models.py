from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from schemas import StrictModel
from src.domain.stage1_models import NormalizedScenarioSet, Stage1LoadResult


class ForecastSource(StrictModel):
    provider: str
    raw_schema_version: str
    prediction_date: str
    generated_at: str


class ForecastHorizon(StrictModel):
    trading_days: int = Field(gt=0)
    scope: Literal["ABOUT_ONE_MONTH"] = "ABOUT_ONE_MONTH"
    end_date: str


class DirectionScore(StrictModel):
    label: Literal["USD_KRW_UP", "USD_KRW_DOWN"]
    up_score: str
    down_score: str
    calibrated_probability: bool
    usage: Literal["MARKET_CONTEXT_ONLY"] = "MARKET_CONTEXT_ONLY"
    interpretation: str


class PathQuantiles(StrictModel):
    q10: str
    q50: str
    q75: str
    q90: str


class PathRisk(StrictModel):
    up: PathQuantiles
    down: PathQuantiles


class MarketFactor(StrictModel):
    model: str
    feature: str
    display_name: str
    effect: str
    details: Dict[str, Any] = Field(default_factory=dict)


class NewsEvent(StrictModel):
    event_id: str
    region: str
    category: str
    event_stage: str
    action_direction: str
    analysis_confidence: str
    summary: str
    headline: str
    url: str


class MarketContext(StrictModel):
    summary: str
    decision_basis: str
    top_factors: List[MarketFactor] = Field(default_factory=list)
    news: List[NewsEvent] = Field(default_factory=list)
    news_used_as_predictor: bool
    changed_model_forecast: bool
    role: str
    warning: str
    duplicate_news_removed: int = Field(default=0, ge=0)
    query_errors: Dict[str, str] = Field(default_factory=dict)


class ForecastQuality(StrictModel):
    market_data_latest_date: str
    model_trained_as_of: str
    partial_fallback_used: bool
    failed_series: Dict[str, str] = Field(default_factory=dict)
    research_only: bool
    stale_market_data: bool
    news_degraded: bool
    warnings: List[str] = Field(default_factory=list)


class NormalizedStage1Forecast(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    pair: Literal["USD/KRW"] = "USD/KRW"
    source: ForecastSource
    horizon: ForecastHorizon
    direction: DirectionScore
    path_risk: PathRisk
    market_context: MarketContext
    quality: ForecastQuality


class ProviderHealth(StrictModel):
    provider: str
    status: Literal["OK", "DEGRADED", "UNAVAILABLE"]
    reachable: bool
    forecast_available: Optional[bool] = None
    checked_at: str
    error_code: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class Stage1ForecastLoadResult(StrictModel):
    source: Literal[
        "HTTP",
        "FILE",
        "MOCK",
        "FILE_FALLBACK",
        "MOCK_FALLBACK",
    ]
    forecast: NormalizedStage1Forecast
    provider_health: ProviderHealth
    fallback_used: bool = False
    file_modified_at: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class SpotQuote(StrictModel):
    pair: str
    rate: str
    quote_convention: str
    rate_type: Literal[
        "MARKET_OR_REFERENCE",
        "USER_CONFIRMED_MANUAL",
        "TEST_FIXTURE",
    ]
    as_of: str
    source: str
    user_confirmed: bool


class ScenarioMetadata(StrictModel):
    id: str
    rate: str
    move: str
    direction: Literal["UP", "DOWN", "BASE"]
    source_kind: Literal[
        "SPOT_BASE",
        "STAGE1_MODEL_QUANTILE",
        "DETERMINISTIC_STRESS",
    ]
    horizon_trading_days: Optional[int] = None
    probability: Optional[str] = None
    is_base: bool = False
    included_in_calculation: bool = True
    warnings: List[str] = Field(default_factory=list)


class ScenarioBuildResult(StrictModel):
    spot_quote: SpotQuote
    calculation_set: NormalizedScenarioSet
    model_path_scenarios: List[ScenarioMetadata] = Field(
        default_factory=list
    )
    fixed_stress_scenarios: List[ScenarioMetadata] = Field(
        default_factory=list
    )
    horizon_end_date: Optional[str] = None
    horizon_mismatch: bool = False
    warnings: List[str] = Field(default_factory=list)


class MarketIntegrationResult(StrictModel):
    forecast_load: Optional[Stage1ForecastLoadResult] = None
    spot_quote: SpotQuote
    scenario_build: ScenarioBuildResult
    stage1_load: Stage1LoadResult
