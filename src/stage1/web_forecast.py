import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field

from src.domain.stage1_web_models import (
    DirectionScore,
    ForecastHorizon,
    ForecastQuality,
    ForecastSource,
    MarketContext,
    MarketFactor,
    NewsEvent,
    NormalizedStage1Forecast,
    PathQuantiles,
    PathRisk,
)


EXPECTED_RAW_SCHEMA_VERSION = "krw_forecast_web_v1"
DEFAULT_MAX_PATH_RETURN = Decimal("0.50")
SCORE_TOLERANCE = Decimal("0.0001")
MAX_RAW_FORECAST_BYTES = 1024 * 1024


class _RawModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _RawHorizon(_RawModel):
    trading_days: int


class _RawDirection(_RawModel):
    p_usdkrw_up: Any
    p_usdkrw_down: Any
    direction: str
    probability_calibrated: bool
    interpretation: str


class _RawQuantiles(_RawModel):
    q10: Any
    q50: Any
    q75: Any
    q90: Any


class _RawExcursion(_RawModel):
    quantiles_simple_return: _RawQuantiles


class _RawCombined(_RawModel):
    summary: str
    action_recommendation_supplied: bool


class _RawForecastBlock(_RawModel):
    terminal_direction_21d: _RawDirection
    maximum_rise_21d: _RawExcursion
    maximum_fall_21d: _RawExcursion
    combined_interpretation: _RawCombined


class _RawDecisionItem(_RawModel):
    description: str = ""
    top_market_factors: List[Dict[str, Any]] = Field(
        default_factory=list
    )


class _RawDecisionBasis(_RawModel):
    terminal_direction_v25: _RawDecisionItem
    maximum_rise_v36: _RawDecisionItem
    maximum_fall_v34: _RawDecisionItem


class _RawNewsEvent(_RawModel):
    region: str
    category: str
    event_stage: str
    action_direction: str
    analysis_confidence: Any
    summary: str
    headline: str
    url: str


class _RawNewsContext(_RawModel):
    news_used_as_predictor: bool
    changed_model_forecast: bool
    role: str
    key_news_events: List[_RawNewsEvent] = Field(default_factory=list)
    warning: str


class _RawMarketRefresh(_RawModel):
    partial_fallback_used: bool
    failed_series: Dict[str, Any] = Field(default_factory=dict)


class _RawNewsRefresh(_RawModel):
    query_errors: Dict[str, Any] = Field(default_factory=dict)
    fallback_used: bool = False


class _RawDataQuality(_RawModel):
    market_data_latest_date: str
    model_bundle_trained_as_of: str
    market_refresh: _RawMarketRefresh
    news_refresh: _RawNewsRefresh
    research_only: bool


class _RawStage1Forecast(_RawModel):
    schema_version: str
    generated_at: str
    prediction_date: str
    horizon: _RawHorizon
    forecast: _RawForecastBlock
    decision_basis: _RawDecisionBasis
    news_market_context: _RawNewsContext
    data_quality: _RawDataQuality


def _decimal(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("{}은 decimal이어야 합니다.".format(field)) from exc
    if not parsed.is_finite():
        raise ValueError("{}은 유한한 decimal이어야 합니다.".format(field))
    return parsed


def _fraction(
    value: Any,
    field: str,
    *,
    maximum: Decimal,
) -> Decimal:
    parsed = _decimal(value, field)
    if parsed < 0 or parsed > maximum:
        raise ValueError(
            "{}은 0 이상 {} 이하여야 합니다.".format(field, maximum)
        )
    return parsed


def _iso_datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            "{}은 ISO 8601 datetime이어야 합니다.".format(field)
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError("{}에는 timezone이 필요합니다.".format(field))
    return parsed


def _iso_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            "{}은 YYYY-MM-DD이어야 합니다.".format(field)
        ) from exc


def add_market_days(start: date, trading_days: int) -> date:
    if trading_days <= 0:
        raise ValueError("trading_days는 0보다 커야 합니다.")
    cursor = start
    remaining = trading_days
    while remaining:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            remaining -= 1
    return cursor


def market_days_elapsed(start: date, end: date) -> int:
    if end <= start:
        return 0
    cursor = start
    count = 0
    while cursor < end:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            count += 1
    return count


def _quantiles(
    raw: _RawQuantiles,
    field: str,
    maximum: Decimal,
) -> PathQuantiles:
    values = [
        _fraction(
            getattr(raw, name),
            "{}.{}".format(field, name),
            maximum=maximum,
        )
        for name in ("q10", "q50", "q75", "q90")
    ]
    if values != sorted(values):
        raise ValueError(
            "{}은 q10 <= q50 <= q75 <= q90이어야 합니다.".format(
                field
            )
        )
    return PathQuantiles(
        q10=format(values[0], "f"),
        q50=format(values[1], "f"),
        q75=format(values[2], "f"),
        q90=format(values[3], "f"),
    )


def _normalized_text(value: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", " ", value.lower()).strip()


def _normalized_headline(value: str) -> str:
    first = re.split(r"\s[-–—]\s", value, maxsplit=1)[0]
    return _normalized_text(first)


def _normalized_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    path = re.sub(r"/+$", "", parsed.path or "/")
    return urlunsplit(("", hostname, path, "", ""))


def _news_key(item: _RawNewsEvent) -> Tuple[str, str, str]:
    summary = _normalized_text(item.summary)
    if summary:
        return item.category.lower(), item.event_stage.lower(), summary
    headline = _normalized_headline(item.headline)
    if headline:
        return item.category.lower(), item.event_stage.lower(), headline
    return (
        item.category.lower(),
        item.event_stage.lower(),
        _normalized_url(item.url),
    )


def _news_events(
    items: List[_RawNewsEvent],
) -> Tuple[List[NewsEvent], int]:
    result: List[NewsEvent] = []
    seen = set()
    duplicates = 0
    for item in items:
        key = _news_key(item)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        event_digest = hashlib.sha256(
            "|".join(key).encode("utf-8")
        ).hexdigest()[:16]
        result.append(
            NewsEvent(
                event_id="news_{}".format(event_digest),
                region=item.region,
                category=item.category,
                event_stage=item.event_stage,
                action_direction=item.action_direction,
                analysis_confidence=format(
                    _fraction(
                        item.analysis_confidence,
                        "news.analysis_confidence",
                        maximum=Decimal("1"),
                    ),
                    "f",
                ),
                summary=item.summary,
                headline=item.headline,
                url=item.url,
            )
        )
    return result, duplicates


def _market_factors(
    decision_basis: _RawDecisionBasis,
) -> List[MarketFactor]:
    factors: List[MarketFactor] = []
    groups = (
        (
            "terminal_direction_v25",
            decision_basis.terminal_direction_v25,
        ),
        ("maximum_rise_v36", decision_basis.maximum_rise_v36),
        ("maximum_fall_v34", decision_basis.maximum_fall_v34),
    )
    for model_name, group in groups:
        for item in group.top_market_factors:
            feature = str(item.get("feature") or "").strip()
            display_name = str(
                item.get("display_name") or feature
            ).strip()
            effect = str(item.get("effect") or "not_specified").strip()
            details = {
                str(key): value
                for key, value in item.items()
                if key not in {"feature", "display_name", "effect"}
            }
            if not feature:
                continue
            factors.append(
                MarketFactor(
                    model=model_name,
                    feature=feature,
                    display_name=display_name,
                    effect=effect,
                    details=details,
                )
            )
    return factors


def _string_dict(value: Dict[str, Any]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for key, item in value.items():
        if isinstance(item, str):
            result[str(key)] = item
        else:
            result[str(key)] = json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
            )
    return result


def parse_raw_stage1_forecast(payload: Any) -> _RawStage1Forecast:
    if isinstance(payload, bytes):
        if len(payload) > MAX_RAW_FORECAST_BYTES:
            raise ValueError("Stage 1 forecast 응답이 1MB를 초과합니다.")
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        if len(payload.encode("utf-8")) > MAX_RAW_FORECAST_BYTES:
            raise ValueError("Stage 1 forecast 응답이 1MB를 초과합니다.")
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("Stage 1 forecast는 JSON object여야 합니다.")
    return _RawStage1Forecast.model_validate(payload)


def normalize_stage1_web_forecast(
    payload: Any,
    *,
    provider: str,
    max_path_return: Decimal = DEFAULT_MAX_PATH_RETURN,
    max_staleness_market_days: int = 3,
    now: Optional[datetime] = None,
) -> NormalizedStage1Forecast:
    raw = parse_raw_stage1_forecast(payload)
    if raw.schema_version != EXPECTED_RAW_SCHEMA_VERSION:
        raise ValueError(
            "지원하지 않는 Stage 1 schema_version입니다: {}".format(
                raw.schema_version
            )
        )
    if raw.horizon.trading_days <= 0:
        raise ValueError("Stage 1 horizon은 0보다 커야 합니다.")
    if max_staleness_market_days < 0:
        raise ValueError("stale market day 기준은 음수일 수 없습니다.")
    if max_path_return <= 0 or max_path_return >= 1:
        raise ValueError("maximum path return은 0과 1 사이여야 합니다.")

    generated_at = _iso_datetime(raw.generated_at, "generated_at")
    prediction_date = _iso_date(raw.prediction_date, "prediction_date")
    market_date = _iso_date(
        raw.data_quality.market_data_latest_date,
        "data_quality.market_data_latest_date",
    )
    _iso_date(
        raw.data_quality.model_bundle_trained_as_of,
        "data_quality.model_bundle_trained_as_of",
    )
    reference_now = now or datetime.now(timezone.utc)
    if reference_now.tzinfo is None:
        raise ValueError("현재시각에는 timezone이 필요합니다.")
    elapsed = market_days_elapsed(market_date, reference_now.date())
    stale = elapsed > max_staleness_market_days

    direction = raw.forecast.terminal_direction_21d
    up_score = _fraction(
        direction.p_usdkrw_up,
        "forecast.terminal_direction_21d.p_usdkrw_up",
        maximum=Decimal("1"),
    )
    down_score = _fraction(
        direction.p_usdkrw_down,
        "forecast.terminal_direction_21d.p_usdkrw_down",
        maximum=Decimal("1"),
    )
    if abs(up_score + down_score - Decimal("1")) > SCORE_TOLERANCE:
        raise ValueError("Stage 1 up/down score 합은 1이어야 합니다.")
    label_map = {
        "usdkrw_up": "USD_KRW_UP",
        "usdkrw_down": "USD_KRW_DOWN",
    }
    if direction.direction not in label_map:
        raise ValueError("Stage 1 direction 값이 지원되지 않습니다.")
    if (
        raw.news_market_context.news_used_as_predictor
        or raw.news_market_context.changed_model_forecast
    ):
        raise ValueError(
            "뉴스가 수치 예측을 바꾸는 Stage 1 payload는 사용할 수 없습니다."
        )
    if raw.forecast.combined_interpretation.action_recommendation_supplied:
        raise ValueError(
            "행동 권고가 포함된 Stage 1 payload는 계산 입력으로 사용할 수 없습니다."
        )

    up_quantiles = _quantiles(
        raw.forecast.maximum_rise_21d.quantiles_simple_return,
        "forecast.maximum_rise_21d.quantiles_simple_return",
        max_path_return,
    )
    down_quantiles = _quantiles(
        raw.forecast.maximum_fall_21d.quantiles_simple_return,
        "forecast.maximum_fall_21d.quantiles_simple_return",
        max_path_return,
    )
    news, duplicates = _news_events(
        raw.news_market_context.key_news_events
    )
    failed_series = _string_dict(
        raw.data_quality.market_refresh.failed_series
    )
    query_errors = _string_dict(
        raw.data_quality.news_refresh.query_errors
    )
    warnings: List[str] = []
    if not direction.probability_calibrated:
        warnings.append(
            "UNCALIBRATED_DIRECTION_SCORE: v25 score는 실제 발생확률이 "
            "아니며 시장 문맥에만 사용합니다."
        )
    if stale:
        warnings.append(
            "STALE_MARKET_DATA: 시장 데이터가 기본 허용 기준 {} "
            "market days를 초과했습니다.".format(
                max_staleness_market_days
            )
        )
    if raw.data_quality.market_refresh.partial_fallback_used:
        warnings.append(
            "PARTIAL_FALLBACK_USED: 일부 시장 시계열이 과거 값으로 "
            "보완되었습니다."
        )
    if failed_series:
        warnings.append(
            "FAILED_MARKET_SERIES: 갱신 실패 시장 시계열이 있습니다."
        )
    if query_errors:
        warnings.append(
            "NEWS_QUERY_ERRORS: 뉴스 검색 일부가 실패했지만 가격모델 "
            "결과와는 분리된 상태입니다."
        )
    if raw.data_quality.news_refresh.fallback_used:
        warnings.append(
            "NEWS_FALLBACK_USED: 실시간 뉴스 대신 저장된 뉴스 문맥을 "
            "사용했습니다."
        )
    if duplicates:
        warnings.append(
            "NEWS_DEDUPLICATED: 중복 뉴스 {}건을 제거했습니다.".format(
                duplicates
            )
        )
    if raw.data_quality.research_only:
        warnings.append(
            "RESEARCH_ONLY: Stage 1은 연구·대회용 프로토타입입니다."
        )

    return NormalizedStage1Forecast(
        source=ForecastSource(
            provider=provider,
            raw_schema_version=raw.schema_version,
            prediction_date=prediction_date.isoformat(),
            generated_at=generated_at.isoformat(),
        ),
        horizon=ForecastHorizon(
            trading_days=raw.horizon.trading_days,
            end_date=add_market_days(
                prediction_date,
                raw.horizon.trading_days,
            ).isoformat(),
        ),
        direction=DirectionScore(
            label=label_map[direction.direction],
            up_score=format(up_score, "f"),
            down_score=format(down_score, "f"),
            calibrated_probability=direction.probability_calibrated,
            interpretation=direction.interpretation,
        ),
        path_risk=PathRisk(
            up=up_quantiles,
            down=down_quantiles,
        ),
        market_context=MarketContext(
            summary=raw.forecast.combined_interpretation.summary,
            decision_basis=(
                raw.decision_basis.terminal_direction_v25.description
            ),
            top_factors=_market_factors(raw.decision_basis),
            news=news,
            news_used_as_predictor=(
                raw.news_market_context.news_used_as_predictor
            ),
            changed_model_forecast=(
                raw.news_market_context.changed_model_forecast
            ),
            role=raw.news_market_context.role,
            warning=raw.news_market_context.warning,
            duplicate_news_removed=duplicates,
            query_errors=query_errors,
        ),
        quality=ForecastQuality(
            market_data_latest_date=market_date.isoformat(),
            model_trained_as_of=(
                raw.data_quality.model_bundle_trained_as_of
            ),
            partial_fallback_used=(
                raw.data_quality.market_refresh.partial_fallback_used
            ),
            failed_series=failed_series,
            research_only=raw.data_quality.research_only,
            stale_market_data=stale,
            news_degraded=bool(
                query_errors
                or raw.data_quality.news_refresh.fallback_used
            ),
            warnings=warnings,
        ),
    )
