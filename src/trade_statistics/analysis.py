from decimal import Decimal
from typing import List, Optional, Tuple

from src.domain.trade_statistics_models import (
    TradeStatisticsComparisonStatus,
    TradeStatisticsObservation,
    TradeStatisticsRecentDirection,
    TradeStatisticsRequest,
    TradeStatisticsSnapshot,
    TradeStatisticsSourceReference,
    TradeStatisticsSummary,
)
from src.trade_statistics.periods import month_range, shift_month


COUNTRY_NAMES = {
    "KR": "한국",
    "BR": "브라질",
    "US": "미국",
}


def _sum_field(
    observations: List[TradeStatisticsObservation],
    field_name: str,
) -> Decimal:
    return sum(
        (Decimal(getattr(item, field_name)) for item in observations),
        Decimal("0"),
    )


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _comparison(
    current: Optional[Decimal],
    previous: Optional[Decimal],
    *,
    missing_months: bool,
    insufficient_history: bool,
) -> Tuple[Optional[str], TradeStatisticsComparisonStatus]:
    if insufficient_history:
        return None, "INSUFFICIENT_HISTORY"
    if missing_months:
        return None, "MISSING_MONTHS"
    if current is None or previous is None:
        return None, "INSUFFICIENT_HISTORY"
    if previous == 0:
        return None, "PREVIOUS_ZERO"
    percentage = ((current - previous) / abs(previous)) * Decimal("100")
    return _decimal_text(percentage), "AVAILABLE"


def _recent_direction(
    observations: List[TradeStatisticsObservation],
    trade_direction: str,
) -> TradeStatisticsRecentDirection:
    if len(observations) < 6:
        return "NOT_COMPARABLE"
    field_name = (
        "export_value_usd"
        if trade_direction == "EXPORT"
        else "import_value_usd"
    )
    previous = _sum_field(observations[-6:-3], field_name)
    current = _sum_field(observations[-3:], field_name)
    if previous == 0:
        return "NOT_COMPARABLE"
    difference_ratio = abs(current - previous) / abs(previous)
    if difference_ratio <= Decimal("0.01"):
        return "SIMILAR"
    return "INCREASED" if current > previous else "DECREASED"


def _source_reference(
    snapshot: TradeStatisticsSnapshot,
) -> TradeStatisticsSourceReference:
    return TradeStatisticsSourceReference(
        source_name=snapshot.source_name,
        official_url=snapshot.metadata.get(
            "official_page_url",
            "https://www.data.go.kr/data/15100475/openapi.do",
        ),
        source_title="관세청 품목별 국가별 수출입실적",
        observation_period="{}~{}".format(
            snapshot.observation_start,
            snapshot.observation_end,
        ),
        source_as_of=snapshot.source_as_of,
        collected_at=snapshot.collected_at,
        provider_status=snapshot.provider_status,
    )


def _summary_text(
    request: TradeStatisticsRequest,
    direction: TradeStatisticsRecentDirection,
    comparison_status: TradeStatisticsComparisonStatus,
    latest_period_complete: bool,
) -> str:
    reporter = COUNTRY_NAMES.get(
        request.reporter_country, request.reporter_country
    )
    partner = COUNTRY_NAMES.get(
        request.partner_country, request.partner_country
    )
    flow_name = "수출" if request.trade_direction == "EXPORT" else "수입"
    period_label = (
        "최근 12개월 동안"
        if latest_period_complete
        else "확인 가능한 관측기간 동안"
    )
    prefix = (
        "{} {}과 {} 사이의 공식 수출입 통계를 "
        "확인했습니다. 현재 거래는 {}의 대{} {}에 해당합니다."
    ).format(
        period_label,
        reporter,
        partner,
        reporter,
        partner,
        flow_name,
    )
    if comparison_status != "AVAILABLE":
        return (
            prefix
            + " 비교기간 데이터가 충분하지 않아 증감률을 계산하지 "
            "않았습니다."
        )
    direction_text = {
        "INCREASED": "증가했습니다.",
        "DECREASED": "감소했습니다.",
        "SIMILAR": "비슷한 수준이었습니다.",
        "NOT_COMPARABLE": "비교할 수 없습니다.",
    }[direction]
    return "{} 최근 3개월 해당 흐름은 직전 3개월보다 {}".format(
        prefix,
        direction_text,
    )


def summarize_trade_statistics(
    request: TradeStatisticsRequest,
    snapshot: TradeStatisticsSnapshot,
) -> TradeStatisticsSummary:
    if (
        request.reporter_country != snapshot.reporter_country
        or request.partner_country != snapshot.partner_country
        or request.hs_code != snapshot.hs_code
    ):
        raise ValueError("요청과 무역통계 snapshot 범위가 일치하지 않습니다.")
    observations = [
        item
        for item in snapshot.observations
        if request.period_start <= item.period <= request.period_end
    ]
    if not observations:
        raise ValueError("요청기간에 무역통계 관측값이 없습니다.")
    expected_periods = month_range(request.period_start, request.period_end)
    observed_periods = {item.period for item in observations}
    missing_periods = [
        period for period in expected_periods if period not in observed_periods
    ]
    latest_period = observations[-1].period
    latest_start = shift_month(latest_period, -11)
    previous_end = shift_month(latest_start, -1)
    previous_start = shift_month(previous_end, -11)
    latest_expected = set(month_range(latest_start, latest_period))
    previous_expected = set(month_range(previous_start, previous_end))
    latest = [
        item
        for item in observations
        if item.period in latest_expected
    ]
    previous = [
        item
        for item in observations
        if item.period in previous_expected
    ]
    latest_complete = {item.period for item in latest} == latest_expected
    previous_complete = (
        {item.period for item in previous} == previous_expected
    )
    latest_export = (
        _sum_field(latest, "export_value_usd")
        if latest_complete
        else None
    )
    latest_import = (
        _sum_field(latest, "import_value_usd")
        if latest_complete
        else None
    )
    latest_balance = (
        _sum_field(latest, "trade_balance_usd")
        if latest_complete
        else None
    )
    previous_export = (
        _sum_field(previous, "export_value_usd")
        if previous_complete
        else None
    )
    previous_import = (
        _sum_field(previous, "import_value_usd")
        if previous_complete
        else None
    )
    previous_balance = (
        _sum_field(previous, "trade_balance_usd")
        if previous_complete
        else None
    )
    comparison_insufficient = (
        request.period_start > previous_start
        or len(expected_periods) < 24
    )
    comparison_missing = bool(missing_periods) or not (
        latest_complete and previous_complete
    )
    export_yoy, export_status = _comparison(
        latest_export,
        previous_export,
        missing_months=comparison_missing,
        insufficient_history=comparison_insufficient,
    )
    import_yoy, import_status = _comparison(
        latest_import,
        previous_import,
        missing_months=comparison_missing,
        insufficient_history=comparison_insufficient,
    )
    direction = (
        _recent_direction(latest, request.trade_direction)
        if latest_complete
        else "NOT_COMPARABLE"
    )
    flow_status = (
        export_status
        if request.trade_direction == "EXPORT"
        else import_status
    )
    missing_information: List[str] = []
    if request.hs_code is None:
        missing_information.append(
            "HS Code 미확인: 품목별 통계는 HS Code 확인 후 제공합니다."
        )
    if missing_periods:
        missing_information.append(
            "미응답 관측월: {}".format(", ".join(missing_periods))
        )
    if not latest_complete or not previous_complete:
        missing_information.append(
            "비교기간 데이터가 충분하지 않아 12개월 증감률을 계산하지 "
            "않았습니다."
        )
    return TradeStatisticsSummary(
        provider_status=snapshot.provider_status,
        scope=snapshot.scope,
        reporter_country=snapshot.reporter_country,
        partner_country=snapshot.partner_country,
        trade_direction=request.trade_direction,
        hs_code=snapshot.hs_code,
        hs_level=snapshot.hs_level,
        observation_start=snapshot.observation_start,
        observation_end=snapshot.observation_end,
        latest_period=latest_period,
        latest_12m_export_usd=(
            _decimal_text(latest_export)
            if latest_export is not None
            else None
        ),
        latest_12m_import_usd=(
            _decimal_text(latest_import)
            if latest_import is not None
            else None
        ),
        latest_12m_balance_usd=(
            _decimal_text(latest_balance)
            if latest_balance is not None
            else None
        ),
        previous_12m_export_usd=(
            _decimal_text(previous_export)
            if previous_export is not None
            else None
        ),
        previous_12m_import_usd=(
            _decimal_text(previous_import)
            if previous_import is not None
            else None
        ),
        previous_12m_balance_usd=(
            _decimal_text(previous_balance)
            if previous_balance is not None
            else None
        ),
        export_yoy_pct=export_yoy,
        import_yoy_pct=import_yoy,
        export_comparison_status=export_status,
        import_comparison_status=import_status,
        recent_direction=direction,
        available_month_count=len(observations),
        missing_month_count=len(missing_periods),
        user_summary=_summary_text(
            request,
            direction,
            flow_status,
            latest_complete,
        ),
        missing_information=missing_information,
        limitations=list(snapshot.limitations),
        source_refs=[_source_reference(snapshot)],
    )
