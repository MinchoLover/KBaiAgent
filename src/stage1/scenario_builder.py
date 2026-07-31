from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import List, Optional, Tuple

from src.domain.stage1_models import ScenarioPoint, Stage1ScenarioSet
from src.domain.stage1_web_models import (
    NormalizedStage1Forecast,
    ScenarioBuildResult,
    ScenarioMetadata,
    SpotQuote,
)
from src.stage1.normalizer import normalize_stage1_scenarios


FIXED_STRESS_MOVES = (
    ("DOWN_10", Decimal("-0.10")),
    ("DOWN_5", Decimal("-0.05")),
    ("DOWN_3", Decimal("-0.03")),
    ("BASE", Decimal("0")),
    ("UP_3", Decimal("0.03")),
    ("UP_5", Decimal("0.05")),
    ("UP_10", Decimal("0.10")),
)
MODEL_QUANTILES = ("q50", "q75", "q90")


def _decimal(value: str, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("{}은 decimal이어야 합니다.".format(field)) from exc
    if not parsed.is_finite():
        raise ValueError("{}은 유한해야 합니다.".format(field))
    return parsed


def _rate(value: Decimal) -> str:
    rounded = value.quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )
    return format(rounded, "f")


def _as_of_datetime(value: str) -> str:
    try:
        parsed_date = date.fromisoformat(value)
    except ValueError:
        parsed_date = None
    if parsed_date is not None:
        return datetime.combine(
            parsed_date,
            datetime.min.time(),
            tzinfo=timezone(timedelta(hours=9)),
        ).isoformat()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            "spot as_of는 ISO date 또는 timezone datetime이어야 합니다."
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError("spot as_of datetime에는 timezone이 필요합니다.")
    return parsed.isoformat()


def _scenario_metadata(
    *,
    scenario_id: str,
    spot: Decimal,
    move: Decimal,
    source_kind: str,
    horizon_trading_days: Optional[int],
    included: bool,
    warnings: List[str],
) -> ScenarioMetadata:
    scenario_rate = spot * (Decimal("1") + move)
    if scenario_rate <= 0:
        raise ValueError("시나리오 환율은 0보다 커야 합니다.")
    direction = "BASE"
    if move > 0:
        direction = "UP"
    elif move < 0:
        direction = "DOWN"
    return ScenarioMetadata(
        id=scenario_id,
        rate=_rate(scenario_rate),
        move=format(move, "f"),
        direction=direction,
        source_kind=source_kind,
        horizon_trading_days=horizon_trading_days,
        probability=None,
        is_base=move == 0,
        included_in_calculation=included,
        warnings=warnings,
    )


def _fixed_scenarios(
    spot: Decimal,
) -> Tuple[List[ScenarioMetadata], List[ScenarioPoint]]:
    metadata: List[ScenarioMetadata] = []
    points: List[ScenarioPoint] = []
    for scenario_id, move in FIXED_STRESS_MOVES:
        source_kind = (
            "SPOT_BASE"
            if scenario_id == "BASE"
            else "DETERMINISTIC_STRESS"
        )
        item = _scenario_metadata(
            scenario_id=scenario_id,
            spot=spot,
            move=move,
            source_kind=source_kind,
            horizon_trading_days=None,
            included=True,
            warnings=(
                []
                if scenario_id == "BASE"
                else ["예측이 아닌 고정 스트레스 가정입니다."]
            ),
        )
        metadata.append(item)
        points.append(
            ScenarioPoint(
                name=item.id,
                rate=item.rate,
                is_base=item.is_base,
                probability=None,
                source_kind=source_kind,
                warnings=item.warnings,
            )
        )
    return metadata, points


def _model_scenarios(
    *,
    spot: Decimal,
    forecast: NormalizedStage1Forecast,
    included: bool,
    horizon_warning: Optional[str],
) -> Tuple[List[ScenarioMetadata], List[ScenarioPoint]]:
    metadata: List[ScenarioMetadata] = []
    points: List[ScenarioPoint] = []
    directions = (
        ("UP", forecast.path_risk.up, Decimal("1")),
        ("DOWN", forecast.path_risk.down, Decimal("-1")),
    )
    for direction, quantiles, sign in directions:
        for quantile in MODEL_QUANTILES:
            magnitude = _decimal(
                getattr(quantiles, quantile),
                "{}.{}".format(direction, quantile),
            )
            move = magnitude * sign
            warnings = [
                "모델 예측분포의 경로위험 분위수이며 발생확률이 아닙니다.",
                "뉴스는 이 환율 숫자를 변경하지 않았습니다.",
            ]
            if horizon_warning:
                warnings.append(horizon_warning)
            item = _scenario_metadata(
                scenario_id="MODEL_{}_{}".format(
                    direction,
                    quantile.upper(),
                ),
                spot=spot,
                move=move,
                source_kind="STAGE1_MODEL_QUANTILE",
                horizon_trading_days=forecast.horizon.trading_days,
                included=included,
                warnings=warnings,
            )
            metadata.append(item)
            if included:
                points.append(
                    ScenarioPoint(
                        name=item.id,
                        rate=item.rate,
                        is_base=False,
                        probability=None,
                        source_kind="STAGE1_MODEL_QUANTILE",
                        horizon_trading_days=(
                            forecast.horizon.trading_days
                        ),
                        warnings=warnings,
                    )
                )
    return metadata, points


def build_fx_scenarios(
    *,
    spot_quote: SpotQuote,
    settlement_date: str,
    currency: str,
    forecast: Optional[NormalizedStage1Forecast],
) -> ScenarioBuildResult:
    normalized_currency = currency.strip().upper()
    if len(normalized_currency) != 3:
        raise ValueError("통화는 대문자 3글자여야 합니다.")
    expected_pair = "{}/KRW".format(normalized_currency)
    if spot_quote.pair != expected_pair:
        raise ValueError("spot pair와 거래 통화가 일치하지 않습니다.")
    expected_convention = "KRW_PER_1_{}".format(normalized_currency)
    if spot_quote.quote_convention != expected_convention:
        raise ValueError("spot quote convention이 지원되지 않습니다.")
    spot = _decimal(spot_quote.rate, "spot rate")
    if spot <= 0:
        raise ValueError("spot rate는 0보다 커야 합니다.")
    try:
        settlement = date.fromisoformat(settlement_date)
    except ValueError as exc:
        raise ValueError("settlement_date는 YYYY-MM-DD여야 합니다.") from exc

    fixed_metadata, calculation_points = _fixed_scenarios(spot)
    warnings: List[str] = []
    model_metadata: List[ScenarioMetadata] = []
    horizon_end_date: Optional[str] = None
    horizon_mismatch = False

    if forecast is not None and normalized_currency == "USD":
        prediction_date = date.fromisoformat(
            forecast.source.prediction_date
        )
        horizon_end = date.fromisoformat(forecast.horizon.end_date)
        horizon_end_date = horizon_end.isoformat()
        horizon_mismatch = not (
            prediction_date <= settlement <= horizon_end
        )
        horizon_warning = None
        if horizon_mismatch:
            horizon_warning = (
                "HORIZON_MISMATCH: 결제일이 Stage 1의 21거래일 "
                "검증범위 밖이므로 계산에는 적용하지 않습니다."
            )
            warnings.append(horizon_warning)
        model_metadata, model_points = _model_scenarios(
            spot=spot,
            forecast=forecast,
            included=not horizon_mismatch,
            horizon_warning=horizon_warning,
        )
        calculation_points.extend(model_points)
        warnings.extend(forecast.quality.warnings)
    elif forecast is not None:
        warnings.append(
            "STAGE1_UNSUPPORTED_CURRENCY: Stage 1 모델은 USD/KRW만 "
            "지원하므로 고정 스트레스만 계산합니다."
        )

    raw = Stage1ScenarioSet(
        currency=normalized_currency,
        quote_convention="KRW_PER_1_FC",
        rate_unit_foreign_currency="1",
        as_of=_as_of_datetime(spot_quote.as_of),
        target_date=settlement_date,
        kind="STRESS",
        scenarios=calculation_points,
    )
    normalized = normalize_stage1_scenarios(
        raw,
        expected_currency=normalized_currency,
        expected_target_date=settlement_date,
    )
    application_rule = (
        "결제일이 21거래일 범위 안이므로 모델 경로위험 분위수와 "
        "고정 스트레스를 함께 계산"
        if forecast is not None
        and normalized_currency == "USD"
        and not horizon_mismatch
        else "고정 ±3/5/10% 스트레스만 결제기간 계산에 적용"
    )
    normalized = normalized.model_copy(
        update={
            "application_rule": application_rule,
            "warnings": list(dict.fromkeys(
                normalized.warnings + warnings
            )),
        }
    )
    return ScenarioBuildResult(
        spot_quote=spot_quote,
        calculation_set=normalized,
        model_path_scenarios=model_metadata,
        fixed_stress_scenarios=fixed_metadata,
        horizon_end_date=horizon_end_date,
        horizon_mismatch=horizon_mismatch,
        warnings=list(dict.fromkeys(warnings)),
    )
