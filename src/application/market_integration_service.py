from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from src.config import Settings
from src.domain.stage1_models import Stage1LoadResult
from src.domain.stage1_web_models import (
    MarketIntegrationResult,
    Stage1ForecastLoadResult,
)
from src.stage1.forecast_provider import (
    FileStage1ForecastProvider,
    HttpStage1ForecastProvider,
    MockStage1ForecastProvider,
    Stage1ForecastService,
)
from src.stage1.scenario_builder import build_fx_scenarios
from src.stage1.spot_rate import KoreaEximFetcher, resolve_spot_quote


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STAGE1_FIXTURE = (
    ROOT
    / "src"
    / "integration_assets"
    / "stage1"
    / "latest_forecast.json"
)


def _configured_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _maximum_path_return(value: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(
            "STAGE1_MAX_PATH_RETURN은 decimal이어야 합니다."
        ) from exc
    if not parsed.is_finite() or parsed <= 0 or parsed >= 1:
        raise ValueError(
            "STAGE1_MAX_PATH_RETURN은 0과 1 사이여야 합니다."
        )
    return parsed


def build_stage1_forecast_service(
    settings: Settings,
) -> Stage1ForecastService:
    return Stage1ForecastService(
        http_provider=HttpStage1ForecastProvider(
            base_url=settings.stage1_base_url,
            timeout_seconds=settings.stage1_http_timeout_seconds,
            retries=settings.stage1_http_retries,
            maximum_bytes=settings.stage1_max_response_bytes,
            allow_private_endpoints=(
                settings.stage1_allow_private_endpoints
            ),
            allowed_hosts=settings.stage1_allowed_hosts,
        ),
        file_provider=FileStage1ForecastProvider(
            _configured_path(settings.stage1_forecast_file)
        ),
        mock_provider=MockStage1ForecastProvider(
            DEFAULT_STAGE1_FIXTURE
        ),
        maximum_path_return=_maximum_path_return(
            settings.stage1_max_path_return
        ),
        max_staleness_market_days=(
            settings.stage1_max_staleness_market_days
        ),
    )


def integrate_stage1_market(
    *,
    settings: Settings,
    currency: str,
    settlement_date: str,
    provider_name: Optional[str] = None,
    spot_provider_name: Optional[str] = None,
    manual_spot_rate: Optional[str] = None,
    manual_spot_confirmed: bool = False,
    now: Optional[datetime] = None,
    forecast_service: Optional[Stage1ForecastService] = None,
    koreaexim_fetcher: Optional[KoreaEximFetcher] = None,
) -> MarketIntegrationResult:
    normalized_currency = currency.strip().upper()
    pair = "{}/KRW".format(normalized_currency)
    try:
        settlement = date.fromisoformat(settlement_date)
    except ValueError as exc:
        raise ValueError("settlement_date는 YYYY-MM-DD여야 합니다.") from exc

    warnings = []
    forecast_load: Optional[Stage1ForecastLoadResult] = None
    if normalized_currency == "USD":
        service = forecast_service or build_stage1_forecast_service(settings)
        try:
            forecast_load = service.load(
                provider_name or settings.stage1_provider,
                now=now,
            )
            warnings.extend(forecast_load.warnings)
        except Exception as exc:
            warnings.extend(
                [
                    "FALLBACK_USED: Stage 1 forecast를 사용할 수 없어 "
                    "고정 스트레스만 계산합니다.",
                    "Stage 1 forecast 실패 ({})".format(
                        type(exc).__name__
                    ),
                ]
            )
    else:
        warnings.append(
            "STAGE1_UNSUPPORTED_CURRENCY: Stage 1 모델은 USD/KRW만 "
            "지원합니다."
        )

    quote = resolve_spot_quote(
        provider_name=(
            spot_provider_name or settings.spot_rate_provider
        ),
        pair=pair,
        manual_rate=(
            manual_spot_rate
            if manual_spot_rate is not None
            else settings.manual_usdkrw_rate
        ),
        manual_confirmed=manual_spot_confirmed,
        koreaexim_key=settings.koreaexim_key,
        demo_mode=settings.demo_mode,
        as_of=settlement if settlement <= date.today() else None,
        koreaexim_fetcher=koreaexim_fetcher,
    )
    if quote.rate_type == "TEST_FIXTURE":
        warnings.append(
            "FIXTURE_SPOT_USED: 데모 기준환율이며 실시간 환율이 아닙니다."
        )

    scenario_build = build_fx_scenarios(
        spot_quote=quote,
        settlement_date=settlement_date,
        currency=normalized_currency,
        forecast=(
            forecast_load.forecast
            if forecast_load is not None
            else None
        ),
    )
    warnings.extend(scenario_build.warnings)
    fallback_used = bool(
        forecast_load is None
        or forecast_load.fallback_used
    )
    stage1_load = Stage1LoadResult(
        source=(
            "STAGE1_MODEL_FALLBACK"
            if fallback_used
            else "STAGE1_MODEL"
        ),
        scenario_set=scenario_build.calculation_set,
        warnings=list(dict.fromkeys(warnings)),
    )
    return MarketIntegrationResult(
        forecast_load=forecast_load,
        spot_quote=quote,
        scenario_build=scenario_build,
        stage1_load=stage1_load,
    )
