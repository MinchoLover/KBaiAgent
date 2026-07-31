from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, List, Optional

from src.domain.stage1_models import ScenarioPoint, Stage1ScenarioSet


DEFAULT_STRESS_PERCENTAGES = (
    Decimal("-0.10"),
    Decimal("-0.05"),
    Decimal("-0.03"),
    Decimal("0"),
    Decimal("0.03"),
    Decimal("0.05"),
    Decimal("0.10"),
)


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("환율은 decimal 문자열이어야 합니다.") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("기준 환율은 0보다 커야 합니다.")
    return parsed


def _name_for_percentage(value: Decimal) -> str:
    if value == 0:
        return "BASE"
    percent = value * Decimal("100")
    sign = "+" if percent > 0 else ""
    return "STRESS_{}{}PCT".format(sign, format(percent, "f"))


def build_manual_stress_scenarios(
    *,
    currency: str,
    base_rate: str,
    target_date: str,
    as_of: Optional[str] = None,
    percentages: Optional[Iterable[Decimal]] = None,
) -> Stage1ScenarioSet:
    normalized_currency = currency.strip().upper()
    if len(normalized_currency) != 3:
        raise ValueError("통화는 대문자 3글자여야 합니다.")
    rate = _decimal(base_rate)
    try:
        date.fromisoformat(target_date)
    except ValueError as exc:
        raise ValueError("target_date는 YYYY-MM-DD여야 합니다.") from exc

    kst = timezone(timedelta(hours=9))
    timestamp = as_of or datetime.now(kst).isoformat()
    points: List[ScenarioPoint] = []
    for change in percentages or DEFAULT_STRESS_PERCENTAGES:
        if not change.is_finite():
            raise ValueError("스트레스 변화율은 유한해야 합니다.")
        scenario_rate = rate * (Decimal("1") + change)
        if scenario_rate <= 0:
            raise ValueError("스트레스 적용 환율은 0보다 커야 합니다.")
        points.append(
            ScenarioPoint(
                name=_name_for_percentage(change),
                rate=format(scenario_rate, "f"),
                is_base=change == 0,
                probability=None,
                source_kind=(
                    "SPOT_BASE"
                    if change == 0
                    else "MANUAL_STRESS"
                ),
            )
        )

    return Stage1ScenarioSet(
        currency=normalized_currency,
        rate_unit_foreign_currency="1",
        as_of=timestamp,
        target_date=target_date,
        kind="STRESS",
        scenarios=points,
    )
