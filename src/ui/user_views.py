from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional
from urllib.parse import urlparse

from src.domain.stage1_web_models import MarketIntegrationResult, NewsEvent


@dataclass(frozen=True)
class FxForecastView:
    pair: str
    direction: str
    direction_symbol: str
    direction_sentence: str
    reference_rate: Decimal
    reference_as_of: str
    target_date: str
    horizon_end_date: str
    center_rate: Optional[Decimal]
    center_move: Optional[Decimal]
    lower_rate: Optional[Decimal]
    upper_rate: Optional[Decimal]
    source_label: str
    data_as_of: str
    uncertainty_copy: str
    disclaimer: str


@dataclass(frozen=True)
class MarketNewsView:
    headline: str
    source_label: str
    published_at: str
    summary: str
    pressure_label: str
    factor_tags: List[str]
    relevance: str
    url: Optional[str]


def _scenario_rate(
    integration: MarketIntegrationResult,
    scenario_id: str,
) -> Optional[Decimal]:
    for item in integration.scenario_build.model_path_scenarios:
        if item.id == scenario_id:
            return Decimal(item.rate)
    return None


def _scenario_move(
    integration: MarketIntegrationResult,
    scenario_id: str,
) -> Optional[Decimal]:
    for item in integration.scenario_build.model_path_scenarios:
        if item.id == scenario_id:
            return Decimal(item.move)
    return None


def _date_label(value: str) -> str:
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except (TypeError, ValueError):
        return value


def build_fx_forecast_view(
    integration: Optional[MarketIntegrationResult],
) -> Optional[FxForecastView]:
    """Project existing Stage1 values into a user-facing forecast view."""

    if integration is None or integration.forecast_load is None:
        return None
    forecast = integration.forecast_load.forecast
    direction_is_down = forecast.direction.label == "USD_KRW_DOWN"
    preferred_id = (
        "MODEL_DOWN_Q50" if direction_is_down else "MODEL_UP_Q50"
    )
    center = _scenario_rate(integration, preferred_id)
    center_move = _scenario_move(integration, preferred_id)
    lower = _scenario_rate(integration, "MODEL_DOWN_Q90")
    upper = _scenario_rate(integration, "MODEL_UP_Q90")
    source_labels = {
        "HTTP": "연결된 AI 환율 전망",
        "FILE": "검증된 AI 전망 자료",
        "MOCK": "모의 AI 전망 자료",
        "FILE_FALLBACK": "보관된 AI 전망 자료",
        "MOCK_FALLBACK": "모의 전망 대체자료",
    }
    uncertainty = (
        "예측 범위가 넓어 방향보다 범위 관리가 중요합니다."
        if lower is not None
        and upper is not None
        and (upper - lower) / Decimal(integration.spot_quote.rate)
        >= Decimal("0.05")
        else "중심 전망과 함께 상·하한 범위를 확인하세요."
    )
    return FxForecastView(
        pair=forecast.pair,
        direction="하락" if direction_is_down else "상승",
        direction_symbol="↓" if direction_is_down else "↑",
        direction_sentence=(
            "AI 모델은 하락 방향을 우세하게 전망합니다."
            if direction_is_down
            else "AI 모델은 상승 방향을 우세하게 전망합니다."
        ),
        reference_rate=Decimal(integration.spot_quote.rate),
        reference_as_of=_date_label(integration.spot_quote.as_of),
        target_date=integration.stage1_load.scenario_set.target_date,
        horizon_end_date=forecast.horizon.end_date,
        center_rate=center,
        center_move=center_move,
        lower_rate=lower,
        upper_rate=upper,
        source_label=source_labels.get(
            integration.forecast_load.source,
            "AI 환율 전망",
        ),
        data_as_of=_date_label(forecast.quality.market_data_latest_date),
        uncertainty_copy=uncertainty,
        disclaimer=(
            "본 전망은 참고 정보이며 실제 환율이나 수취·지급 금액을 "
            "보장하지 않습니다."
        ),
    )


def _news_source_label(value: NewsEvent) -> str:
    if not value.url:
        return "출처 미확인"
    host = (urlparse(value.url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "출처 미확인"


def _news_pressure(value: NewsEvent) -> str:
    direction = value.action_direction.strip().lower()
    if direction in {"weaken", "usd_krw_down", "down"}:
        return "USD/KRW 하락 압력"
    if direction in {"tighten", "usd_krw_up", "up"}:
        return "USD/KRW 상승 압력"
    return "영향 혼재"


def _news_tags(value: NewsEvent) -> List[str]:
    text = " ".join(
        [value.region, value.category, value.headline, value.summary]
    ).lower()
    candidates = [
        ("fed", "미국 금리"),
        ("rate", "금리"),
        ("dollar", "달러"),
        ("oil", "원자재·유가"),
        ("tariff", "관세·통상"),
        ("inflation", "물가"),
        ("geopolit", "지정학"),
        ("risk", "위험회피"),
        ("trade", "무역"),
        ("brazil", "브라질"),
        ("korea", "한국"),
        ("united states", "미국"),
    ]
    tags = [label for token, label in candidates if token in text]
    return list(dict.fromkeys(tags))[:3] or ["시장 환경"]


def build_market_news_views(
    integration: Optional[MarketIntegrationResult],
    limit: int = 5,
) -> List[MarketNewsView]:
    """Return stored news only; never synthesize an article or URL."""

    if (
        integration is None
        or integration.forecast_load is None
        or limit < 1
    ):
        return []
    news = integration.forecast_load.forecast.market_context.news[:limit]
    result: List[MarketNewsView] = []
    for item in news:
        pressure = _news_pressure(item)
        result.append(
            MarketNewsView(
                headline=item.headline or "제목 미확인",
                source_label=_news_source_label(item),
                published_at="게시일 미확인",
                summary=item.summary,
                pressure_label=pressure,
                factor_tags=_news_tags(item),
                relevance=(
                    "이 시장 요인은 {} 요인으로 전망 해석에 참고됩니다."
                ).format(pressure),
                url=item.url or None,
            )
        )
    return result
