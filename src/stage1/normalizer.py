from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

from src.domain.stage1_models import (
    NormalizedScenarioSet,
    ScenarioPoint,
    Stage1ScenarioSet,
)


PROBABILITY_TOLERANCE = Decimal("0.0001")


def _positive_decimal(value: str, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(
            "{}은 decimal 문자열이어야 합니다.".format(field)
        ) from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("{}은 0보다 커야 합니다.".format(field))
    return parsed


def _validate_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("as_of는 ISO 8601 datetime이어야 합니다.") from exc
    if parsed.tzinfo is None:
        raise ValueError("as_of에는 timezone offset이 필요합니다.")


def _probability_status(
    scenarios: List[ScenarioPoint],
) -> Tuple[bool, List[str]]:
    provided = [point.probability is not None for point in scenarios]
    if not any(provided):
        return False, []
    if not all(provided):
        return False, [
            "probability가 일부 시나리오에만 있어 확률 지표를 생성하지 않습니다."
        ]

    total = Decimal("0")
    for point in scenarios:
        try:
            probability = Decimal(str(point.probability))
        except InvalidOperation as exc:
            raise ValueError(
                "probability는 decimal 문자열이어야 합니다."
            ) from exc
        if (
            not probability.is_finite()
            or probability < 0
            or probability > 1
        ):
            raise ValueError("probability는 0과 1 사이여야 합니다.")
        total += probability

    if abs(total - Decimal("1")) > PROBABILITY_TOLERANCE:
        raise ValueError("scenario probability 합계는 1이어야 합니다.")
    return True, []


def normalize_stage1_scenarios(
    scenario_set: Stage1ScenarioSet,
    *,
    expected_currency: Optional[str] = None,
    expected_target_date: Optional[str] = None,
) -> NormalizedScenarioSet:
    currency = scenario_set.currency.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency는 대문자 3글자여야 합니다.")
    if expected_currency and currency != expected_currency.strip().upper():
        raise ValueError("Stage 0 거래 통화와 Stage 1 통화가 다릅니다.")

    _validate_timestamp(scenario_set.as_of)
    try:
        date.fromisoformat(scenario_set.target_date)
    except ValueError as exc:
        raise ValueError("target_date는 YYYY-MM-DD여야 합니다.") from exc

    unit = _positive_decimal(
        scenario_set.rate_unit_foreign_currency,
        "rate_unit_foreign_currency",
    )
    base_count = sum(
        1 for point in scenario_set.scenarios if point.is_base
    )
    if base_count != 1:
        raise ValueError("base 시나리오는 정확히 하나여야 합니다.")

    names = [point.name for point in scenario_set.scenarios]
    if len(names) != len(set(names)):
        raise ValueError("scenario name은 중복될 수 없습니다.")

    normalized_points: List[ScenarioPoint] = []
    for point in scenario_set.scenarios:
        rate = _positive_decimal(point.rate, "scenario rate") / unit
        normalized_points.append(
            point.model_copy(update={"rate": format(rate, "f")})
        )

    probability_valid, warnings = _probability_status(normalized_points)
    application_rule = (
        "Stage 1 target_date가 거래 settlement_date와 일치하여 직접 적용"
    )
    if (
        expected_target_date
        and scenario_set.target_date != expected_target_date
    ):
        application_rule = (
            "단일 Stage 1 scenario set을 거래 settlement_date에 대체 적용; "
            "target_date 불일치를 사용자에게 표시"
        )
        warnings.append(
            "Stage 1 target_date({})와 거래 settlement_date({})가 "
            "다릅니다.".format(
                scenario_set.target_date,
                expected_target_date,
            )
        )

    if unit != Decimal("1"):
        warnings.append(
            "{} 외화 단위당 환율을 1통화 단위로 정규화했습니다.".format(
                format(unit, "f")
            )
        )

    return NormalizedScenarioSet(
        schema_version=scenario_set.schema_version,
        currency=currency,
        quote_convention="KRW_PER_1_FC",
        rate_unit_foreign_currency="1",
        as_of=scenario_set.as_of,
        target_date=scenario_set.target_date,
        kind=scenario_set.kind,
        scenarios=normalized_points,
        probability_valid=probability_valid,
        application_rule=application_rule,
        warnings=warnings,
    )
