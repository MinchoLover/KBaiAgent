from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from src.domain.stage1_models import NormalizedScenarioSet, ScenarioPoint
from src.domain.stage2_models import (
    ExposureComputation,
    ScenarioResult,
    Stage2Input,
    Stage2Result,
)
from src.stage2.cashflow import (
    add_daily_event,
    apply_composite_stress,
    build_ledger,
    new_daily_event_map,
)
from src.stage2.exposure import compute_exposure
from src.stage2.metrics import (
    date_value,
    decimal_percent,
    decimal_string,
    decimal_value,
    money_string,
)
from src.stage2.scenarios import (
    adverse_loss_vs_base,
    applied_customer_rate,
    signed_impact_vs_base,
)


PREPROCESSING_WARNING_MESSAGES: Dict[str, str] = {
    "EXCESS_USABLE_FX_IGNORED": (
        "거래금액을 초과한 보유외화 잔액은 이번 계산에 사용하지 않았습니다."
    ),
    "INELIGIBLE_SAME_CURRENCY_FLOW_IGNORED": (
        "결제일과 잔여 노출 조건에 맞지 않는 동일통화 흐름은 "
        "자연상계에 사용하지 않았습니다."
    ),
}


def _valid_currency(value: str) -> bool:
    return (
        len(value) == 3
        and value.isalpha()
        and value == value.upper()
    )


def _validate_stage2_contract(
    stage2_input: Stage2Input,
) -> Set[str]:
    as_of = date_value(stage2_input.as_of_date, "as_of_date")
    sequences = [item.sequence for item in stage2_input.exposures]
    if sequences != list(range(1, len(stage2_input.exposures) + 1)):
        raise ValueError("Stage 2 exposure sequence는 1부터 연속이어야 합니다.")

    trade_types = {item.trade_type for item in stage2_input.exposures}
    currencies = {item.currency for item in stage2_input.exposures}
    if len(trade_types) != 1 or len(currencies) != 1:
        raise ValueError("한 계산 실행의 거래 방향과 통화는 같아야 합니다.")
    for currency in currencies:
        if not _valid_currency(currency):
            raise ValueError(
                "Stage 2 currency는 대문자 ISO 형태 3글자여야 합니다."
            )

    decimal_value(
        stage2_input.current_krw_cash,
        "current_krw_cash",
        allow_negative=True,
    )
    decimal_value(stage2_input.minimum_cash_buffer, "minimum_cash_buffer")
    decimal_value(stage2_input.credit_limit, "credit_limit")
    decimal_value(stage2_input.acceptable_fx_loss, "acceptable_fx_loss")
    spread_bps = decimal_value(
        stage2_input.bank_spread_bps,
        "bank_spread_bps",
    )
    if spread_bps >= Decimal("10000"):
        raise ValueError("bank_spread_bps는 10000 미만이어야 합니다.")
    decimal_value(stage2_input.bank_fee, "bank_fee")
    decimal_percent(
        stage2_input.composite_stress.revenue_reduction_percent,
        "revenue_reduction_percent",
    )
    decimal_percent(
        stage2_input.composite_stress.cost_increase_percent,
        "cost_increase_percent",
    )

    for event in stage2_input.krw_cashflows:
        event_date = date_value(event.date, "krw_cashflow.date")
        if event_date < as_of:
            raise ValueError(
                "as_of_date 이전의 KRW cashflow는 current cash와 "
                "중복될 수 있습니다."
            )
        decimal_value(
            event.amount,
            "krw_cashflow.amount",
            allow_zero=False,
        )

    for exposure in stage2_input.exposures:
        settlement = date_value(
            exposure.settlement_date,
            "settlement_date",
        )
        if settlement < as_of:
            raise ValueError("settlement_date는 as_of_date보다 빠를 수 없습니다.")
        decimal_value(
            exposure.foreign_amount,
            "foreign_amount",
            allow_zero=False,
        )
        decimal_value(exposure.usable_fx_balance, "usable_fx_balance")
        if exposure.existing_hedge is not None:
            decimal_value(
                exposure.existing_hedge.amount,
                "existing_hedge.amount",
            )
            decimal_value(
                exposure.existing_hedge.locked_rate,
                "existing_hedge.locked_rate",
                allow_zero=False,
            )
            decimal_value(
                exposure.existing_hedge.fee,
                "existing_hedge.fee",
            )
        for flow in exposure.same_currency_flows:
            if not _valid_currency(flow.currency):
                raise ValueError(
                    "same_currency_flow.currency는 대문자 ISO 형태 "
                    "3글자여야 합니다."
                )
            flow_date = date_value(flow.date, "same_currency_flow.date")
            if flow_date < as_of:
                raise ValueError(
                    "as_of_date 이전의 동일통화 흐름은 현재 보유외화와 "
                    "중복될 수 있습니다."
                )
            decimal_value(
                flow.amount,
                "same_currency_flow.amount",
                allow_zero=False,
            )
    return currencies


def _base_scenario(scenarios: NormalizedScenarioSet) -> ScenarioPoint:
    bases = [point for point in scenarios.scenarios if point.is_base]
    if len(bases) != 1:
        raise ValueError("base 시나리오는 정확히 하나여야 합니다.")
    return bases[0]


def _scenario_fx_flow(
    *,
    stage2_input: Stage2Input,
    computations: List[ExposureComputation],
    scenario: ScenarioPoint,
) -> Tuple[Decimal, Decimal, Decimal]:
    scenario_rate = decimal_value(
        scenario.rate,
        "scenario.rate",
        allow_zero=False,
    )
    spread_bps = decimal_value(
        stage2_input.bank_spread_bps,
        "bank_spread_bps",
    )
    applied_rate = applied_customer_rate(
        reference_rate=scenario_rate,
        trade_type=computations[0].trade_type,
        bank_spread_bps=spread_bps,
    )
    total_inflow = Decimal("0")
    total_outflow = Decimal("0")
    bank_fee = decimal_value(stage2_input.bank_fee, "bank_fee")

    for exposure, computation in zip(
        stage2_input.exposures,
        computations,
    ):
        open_amount = decimal_value(
            computation.open_exposure,
            "open_exposure",
        )
        hedge_amount = decimal_value(
            computation.hedged_amount,
            "hedged_amount",
        )
        unhedged_krw = open_amount * applied_rate
        hedged_krw = Decimal("0")
        hedge_fee = Decimal("0")
        if exposure.existing_hedge is not None and hedge_amount > 0:
            locked_rate = decimal_value(
                exposure.existing_hedge.locked_rate,
                "locked_rate",
                allow_zero=False,
            )
            hedge_fee = decimal_value(
                exposure.existing_hedge.fee,
                "hedge_fee",
            )
            hedged_krw = hedge_amount * locked_rate

        if computation.trade_type == "IMPORT":
            total_outflow += (
                unhedged_krw + hedged_krw + hedge_fee + bank_fee
            )
        else:
            total_inflow += unhedged_krw + hedged_krw
            total_outflow += hedge_fee + bank_fee
    return total_inflow, total_outflow, applied_rate


def _build_scenario_result(
    *,
    stage2_input: Stage2Input,
    scenarios: NormalizedScenarioSet,
    computations: List[ExposureComputation],
    scenario: ScenarioPoint,
    base_fx_inflow: Decimal,
    base_fx_outflow: Decimal,
) -> ScenarioResult:
    as_of = date_value(stage2_input.as_of_date, "as_of_date")
    initial_cash = decimal_value(
        stage2_input.current_krw_cash,
        "current_krw_cash",
        allow_negative=True,
    )
    minimum_buffer = decimal_value(
        stage2_input.minimum_cash_buffer,
        "minimum_cash_buffer",
    )
    credit_limit = decimal_value(
        stage2_input.credit_limit,
        "credit_limit",
    )
    acceptable_loss = decimal_value(
        stage2_input.acceptable_fx_loss,
        "acceptable_fx_loss",
    )
    transformed_cashflows = apply_composite_stress(
        stage2_input.krw_cashflows,
        stage2_input.composite_stress,
    )
    event_map = new_daily_event_map()
    for item in transformed_cashflows:
        amount = decimal_value(
            item.amount,
            "krw_cashflow.amount",
        )
        add_daily_event(
            event_map,
            event_date=date_value(item.date, "krw_cashflow.date"),
            inflow=amount if item.direction == "INFLOW" else Decimal("0"),
            outflow=amount if item.direction == "OUTFLOW" else Decimal("0"),
            description=item.description or item.category,
        )

    scenario_rate = decimal_value(
        scenario.rate,
        "scenario.rate",
        allow_zero=False,
    )
    fx_inflow, fx_outflow, applied_rate = _scenario_fx_flow(
        stage2_input=stage2_input,
        computations=computations,
        scenario=scenario,
    )

    # Add each trade separately so installment dates remain visible. The
    # aggregate flow is allocated proportionally to each exposure's calculated
    # transaction flow, including its hedge fee.
    spread_bps = decimal_value(
        stage2_input.bank_spread_bps,
        "bank_spread_bps",
    )
    customer_rate = applied_customer_rate(
        reference_rate=scenario_rate,
        trade_type=computations[0].trade_type,
        bank_spread_bps=spread_bps,
    )
    bank_fee = decimal_value(stage2_input.bank_fee, "bank_fee")
    for exposure, computation in zip(
        stage2_input.exposures,
        computations,
    ):
        open_amount = decimal_value(
            computation.open_exposure,
            "open_exposure",
        )
        hedge_amount = decimal_value(
            computation.hedged_amount,
            "hedged_amount",
        )
        hedge_flow = Decimal("0")
        hedge_fee = Decimal("0")
        if exposure.existing_hedge is not None and hedge_amount > 0:
            hedge_flow = hedge_amount * decimal_value(
                exposure.existing_hedge.locked_rate,
                "locked_rate",
                allow_zero=False,
            )
            hedge_fee = decimal_value(
                exposure.existing_hedge.fee,
                "hedge_fee",
            )
        unhedged_flow = open_amount * customer_rate
        settlement = date_value(
            computation.settlement_date,
            "settlement_date",
        )
        if computation.trade_type == "IMPORT":
            add_daily_event(
                event_map,
                event_date=settlement,
                outflow=(
                    unhedged_flow + hedge_flow + hedge_fee + bank_fee
                ),
                description=(
                    "수입 결제 #{} (unhedged+hedged+fee)".format(
                        computation.sequence
                    )
                ),
            )
        else:
            add_daily_event(
                event_map,
                event_date=settlement,
                inflow=unhedged_flow + hedge_flow,
                outflow=hedge_fee + bank_fee,
                description=(
                    "수출 수취 #{} (unhedged+hedged-fee)".format(
                        computation.sequence
                    )
                ),
            )

    ledger, cash_metrics = build_ledger(
        event_map=event_map,
        as_of_date=as_of,
        initial_cash=initial_cash,
        minimum_buffer=minimum_buffer,
        credit_limit=credit_limit,
        scenario_name=scenario.name,
        source_status="CALCULATION",
    )
    loss = adverse_loss_vs_base(
        trade_type=computations[0].trade_type,
        scenario_inflow=fx_inflow,
        scenario_outflow=fx_outflow,
        base_inflow=base_fx_inflow,
        base_outflow=base_fx_outflow,
    )
    signed_impact = signed_impact_vs_base(
        trade_type=computations[0].trade_type,
        scenario_inflow=fx_inflow,
        scenario_outflow=fx_outflow,
        base_inflow=base_fx_inflow,
        base_outflow=base_fx_outflow,
    )
    return ScenarioResult(
        scenario_name=scenario.name,
        scenario_kind=scenarios.kind,
        probability=scenario.probability,
        scenario_rate=decimal_string(scenario_rate),
        applied_rate=decimal_string(applied_rate),
        fx_krw_inflow=money_string(fx_inflow),
        fx_krw_outflow=money_string(fx_outflow),
        signed_impact_vs_base=money_string(signed_impact),
        loss_vs_base=money_string(loss),
        ending_cash=money_string(cash_metrics["ending_cash"]),
        minimum_cash=money_string(cash_metrics["minimum_cash"]),
        first_buffer_shortfall_date=cash_metrics[
            "first_buffer_shortfall_date"
        ],
        first_cash_deficit_date=cash_metrics[
            "first_cash_deficit_date"
        ],
        maximum_buffer_shortfall=money_string(
            cash_metrics["maximum_buffer_shortfall"]
        ),
        cash_deficit=money_string(cash_metrics["cash_deficit"]),
        post_credit_shortfall=money_string(
            cash_metrics["post_credit_shortfall"]
        ),
        acceptable_loss_exceeded=loss > acceptable_loss,
        ledger=ledger,
        scenario_source_kind=scenario.source_kind,
        horizon_trading_days=scenario.horizon_trading_days,
        warnings=list(scenario.warnings),
        source_paths={
            "scenario_rate": (
                "stage1.scenario_set.scenarios[{}].rate".format(
                    scenario.name
                )
            ),
            "applied_rate": (
                "stage2.input.bank_spread_bps+stage1.scenario_rate"
            ),
            "loss_vs_base": (
                "stage2.scenario_results[{}].loss_vs_base".format(
                    scenario.name
                )
            ),
            "ending_cash": (
                "stage2.scenario_results[{}].ledger".format(
                    scenario.name
                )
            ),
        },
    )


def _probability_metrics(
    scenarios: NormalizedScenarioSet,
    results: List[ScenarioResult],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not scenarios.probability_valid:
        return None, None, None

    expected_loss = Decimal("0")
    buffer_probability = Decimal("0")
    deficit_probability = Decimal("0")
    for result in results:
        probability = Decimal(str(result.probability))
        loss = Decimal(result.loss_vs_base)
        expected_loss += max(loss, Decimal("0")) * probability
        if Decimal(result.maximum_buffer_shortfall) > 0:
            buffer_probability += probability
        if Decimal(result.cash_deficit) > 0:
            deficit_probability += probability
    return (
        money_string(expected_loss),
        decimal_string(buffer_probability),
        decimal_string(deficit_probability),
    )


def run_stage2(
    stage2_input: Stage2Input,
    scenarios: NormalizedScenarioSet,
) -> Stage2Result:
    currencies = _validate_stage2_contract(stage2_input)
    if scenarios.currency != next(iter(currencies)):
        raise ValueError("Stage 1/2 통화가 일치하지 않습니다.")

    computations: List[ExposureComputation] = []
    warnings: List[str] = list(scenarios.warnings)
    warnings.extend(
        PREPROCESSING_WARNING_MESSAGES[code]
        for code in stage2_input.preprocessing_warnings
    )
    for exposure in stage2_input.exposures:
        if exposure.settlement_date != scenarios.target_date:
            warnings.append(
                "Stage 1 target_date({}) 시나리오를 settlement_date({})에 "
                "대체 적용했습니다.".format(
                    scenarios.target_date,
                    exposure.settlement_date,
                )
            )
        computation, exposure_warnings = compute_exposure(exposure)
        computations.append(computation)
        warnings.extend(exposure_warnings)
    for scenario in scenarios.scenarios:
        warnings.extend(scenario.warnings)

    base = _base_scenario(scenarios)
    base_inflow, base_outflow, unused_rate = _scenario_fx_flow(
        stage2_input=stage2_input,
        computations=computations,
        scenario=base,
    )
    del unused_rate

    results = [
        _build_scenario_result(
            stage2_input=stage2_input,
            scenarios=scenarios,
            computations=computations,
            scenario=scenario,
            base_fx_inflow=base_inflow,
            base_fx_outflow=base_outflow,
        )
        for scenario in scenarios.scenarios
    ]
    expected_loss, buffer_probability, deficit_probability = (
        _probability_metrics(scenarios, results)
    )

    total_amount = sum(
        (
            decimal_value(item.foreign_amount, "foreign_amount")
            for item in computations
        ),
        Decimal("0"),
    )
    total_natural = sum(
        (
            decimal_value(item.natural_offset, "natural_offset")
            for item in computations
        ),
        Decimal("0"),
    )
    total_held_fx = sum(
        (
            decimal_value(item.held_fx_used, "held_fx_used")
            for item in computations
        ),
        Decimal("0"),
    )
    total_same_currency_offset = sum(
        (
            decimal_value(
                item.same_currency_offset,
                "same_currency_offset",
            )
            for item in computations
        ),
        Decimal("0"),
    )
    total_hedged = sum(
        (
            decimal_value(item.hedged_amount, "hedged_amount")
            for item in computations
        ),
        Decimal("0"),
    )
    total_open = sum(
        (
            decimal_value(item.open_exposure, "open_exposure")
            for item in computations
        ),
        Decimal("0"),
    )
    trade_type = computations[0].trade_type
    base_flow = base_outflow if trade_type == "IMPORT" else base_inflow
    acceptable_loss = decimal_value(
        stage2_input.acceptable_fx_loss,
        "acceptable_fx_loss",
    )
    minimum_buffer = decimal_value(
        stage2_input.minimum_cash_buffer,
        "minimum_cash_buffer",
    )
    credit_limit = decimal_value(
        stage2_input.credit_limit,
        "credit_limit",
    )

    assumptions = [
        "환율은 KRW_PER_1_FC 기준입니다.",
        "수동 시나리오는 예측이 아니라 스트레스 가정입니다."
        if scenarios.kind == "STRESS"
        else "외부 Stage 1 값은 FORECAST로 표시하되 보장값이 아닙니다.",
        "기존 헤지는 open exposure에서 제외하되 실제 KRW 현금흐름에는 포함했습니다.",
        "원화 현금흐름은 날짜 단위로 합산한 뒤 잔고를 계산했습니다.",
    ]
    scenario_constraints = [
        {
            "name": item.scenario_name,
            "loss_vs_base": item.loss_vs_base,
            "maximum_buffer_shortfall": item.maximum_buffer_shortfall,
            "probability": item.probability,
        }
        for item in results
    ]
    return Stage2Result(
        confirmed_trade_sha256=stage2_input.confirmed_trade_sha256,
        trade_type=trade_type,
        currency=next(iter(currencies)),
        total_foreign_amount=decimal_string(total_amount),
        natural_offset=decimal_string(total_natural),
        held_fx_used=decimal_string(total_held_fx),
        same_currency_offset=decimal_string(
            total_same_currency_offset
        ),
        hedged_amount=decimal_string(total_hedged),
        open_exposure=decimal_string(total_open),
        base_required_or_proceeds_krw=money_string(base_flow),
        comparison_basis=(
            "BASE scenario total KRW outflow"
            if trade_type == "IMPORT"
            else "BASE scenario total KRW inflow"
        ),
        exposure_computations=computations,
        scenario_results=results,
        expected_adverse_loss=expected_loss,
        buffer_shortfall_probability=buffer_probability,
        cash_deficit_probability=deficit_probability,
        assumptions=assumptions,
        warnings=list(dict.fromkeys(warnings)),
        stage3_constraints={
            "open_exposure": decimal_string(total_open),
            "held_fx_used": decimal_string(total_held_fx),
            "base_rate": base.rate,
            "acceptable_fx_loss": decimal_string(acceptable_loss),
            "minimum_cash_buffer": decimal_string(minimum_buffer),
            "credit_limit": decimal_string(credit_limit),
            "probability_valid": scenarios.probability_valid,
            "scenarios": scenario_constraints,
        },
        source_paths={
            "total_foreign_amount": "stage2.input.exposures[].foreign_amount",
            "settlement_date": (
                "stage0.confirmation.confirmed_values.settlement_date"
            ),
            "natural_offset": (
                "stage2.exposure_computations[].natural_offset"
            ),
            "hedged_amount": (
                "stage2.exposure_computations[].hedged_amount"
            ),
            "open_exposure": (
                "stage2.exposure_computations[].open_exposure"
            ),
            "base_required_or_proceeds_krw": (
                "stage2.scenario_results[BASE].fx_krw_flow"
            ),
        },
    )
