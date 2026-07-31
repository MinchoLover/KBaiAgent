from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from src.domain.stage2_models import ScenarioResult, Stage2Result
from src.domain.stage3_models import (
    Stage3Assumptions,
    Stage3Result,
    StrategyCandidate,
)
from src.stage2.metrics import money_string
from src.stage3.constraints import ratio_sum_is_one
from src.stage3.explanations import candidate_reason


PROFILE_WEIGHTS = (
    (
        "STABILITY_FIRST",
        Decimal("1.50"),
        Decimal("0.25"),
        Decimal("10"),
        Decimal("2"),
    ),
    (
        "BALANCED",
        Decimal("1.00"),
        Decimal("1.00"),
        Decimal("7"),
        Decimal("1"),
    ),
    (
        "COST_FIRST",
        Decimal("0.50"),
        Decimal("2.00"),
        Decimal("5"),
        Decimal("0.5"),
    ),
)


def _ratio(value: int) -> Decimal:
    return Decimal(value) / Decimal("100")


def _decimal(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("{} 숫자가 올바르지 않습니다.".format(field)) from exc
    if not parsed.is_finite():
        raise ValueError("{} 숫자는 유한해야 합니다.".format(field))
    return parsed


def _bounded_ratio(value: Any, field: str) -> Decimal:
    parsed = _decimal(value, field)
    if parsed < 0 or parsed > 1:
        raise ValueError("{}은 0과 1 사이여야 합니다.".format(field))
    return parsed


def _nonnegative(value: Any, field: str) -> Decimal:
    parsed = _decimal(value, field)
    if parsed < 0:
        raise ValueError("{}은 음수일 수 없습니다.".format(field))
    return parsed


def _find_scenario(
    results: List[ScenarioResult],
    names: Tuple[str, ...],
) -> Optional[ScenarioResult]:
    for name in names:
        for item in results:
            if item.scenario_name == name:
                return item
    return None


def _adverse_scenarios(
    stage2_result: Stage2Result,
) -> Tuple[Optional[ScenarioResult], Optional[ScenarioResult]]:
    if stage2_result.trade_type == "IMPORT":
        q90_names = ("MODEL_UP_Q90",)
        fixed_names = (
            "UP_10",
            "STRESS_+10.00PCT",
            "STRESS_+10PCT",
        )
    else:
        q90_names = ("MODEL_DOWN_Q90",)
        fixed_names = (
            "DOWN_10",
            "STRESS_-10.00PCT",
            "STRESS_-10PCT",
        )
    return (
        _find_scenario(stage2_result.scenario_results, q90_names),
        _find_scenario(stage2_result.scenario_results, fixed_names),
    )


def _candidate_cash_metrics(
    *,
    scenarios: List[ScenarioResult],
    risk_factor: Decimal,
    hedge_cost: Decimal,
    minimum_cash_buffer: Decimal,
    credit_limit: Decimal,
) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    minimum_cash_values: List[Decimal] = []
    residual_losses: List[Decimal] = []
    for item in scenarios:
        original_loss = _nonnegative(
            item.loss_vs_base,
            "{} loss".format(item.scenario_name),
        )
        residual_loss = original_loss * risk_factor + hedge_cost
        residual_losses.append(residual_loss)
        base_equivalent_minimum = (
            _decimal(
                item.minimum_cash,
                "{} minimum_cash".format(item.scenario_name),
            )
            + original_loss
        )
        minimum_cash_values.append(
            base_equivalent_minimum - residual_loss
        )
    minimum_cash = min(minimum_cash_values or [Decimal("0")])
    buffer_shortfall = max(
        minimum_cash_buffer - minimum_cash,
        Decimal("0"),
    )
    actual_deficit = max(-minimum_cash, Decimal("0"))
    post_credit_deficit = max(
        actual_deficit - credit_limit,
        Decimal("0"),
    )
    worst_loss = max(residual_losses or [Decimal("0")])
    return (
        minimum_cash,
        buffer_shortfall,
        post_credit_deficit,
        worst_loss,
    )


def _scenario_residual_loss(
    scenario: Optional[ScenarioResult],
    *,
    risk_factor: Decimal,
    hedge_cost: Decimal,
) -> Optional[Decimal]:
    if scenario is None:
        return None
    return (
        _nonnegative(
            scenario.loss_vs_base,
            "{} loss".format(scenario.scenario_name),
        )
        * risk_factor
        + hedge_cost
    )


def generate_strategy_candidates(
    stage2_result: Stage2Result,
    *,
    grid_step_percent: int = 5,
    stability_preference: str = "0.7",
    assumptions: Optional[Stage3Assumptions] = None,
) -> Stage3Result:
    if grid_step_percent not in {5, 10}:
        raise ValueError("grid step은 5 또는 10이어야 합니다.")
    effective_assumptions = assumptions or Stage3Assumptions(
        risk_aversion_weight=stability_preference,
    )
    preference = _bounded_ratio(
        effective_assumptions.risk_aversion_weight,
        "risk_aversion_weight",
    )
    forward_fee_rate = (
        _nonnegative(
            effective_assumptions.forward_fee_bps,
            "forward_fee_bps",
        )
        / Decimal("10000")
    )
    staged_fee_rate = (
        _nonnegative(
            effective_assumptions.staged_conversion_fee_bps,
            "staged_conversion_fee_bps",
        )
        / Decimal("10000")
    )
    staged_risk_factor = _bounded_ratio(
        effective_assumptions.staged_risk_factor,
        "staged_risk_factor",
    )
    liquidity_penalty = _nonnegative(
        effective_assumptions.liquidity_shortfall_penalty,
        "liquidity_shortfall_penalty",
    )
    concentration_penalty = _nonnegative(
        effective_assumptions.concentration_penalty,
        "concentration_penalty",
    )
    maximum_forward_ratio = _bounded_ratio(
        effective_assumptions.maximum_forward_ratio,
        "maximum_forward_ratio",
    )
    minimum_trade_ratio = _bounded_ratio(
        effective_assumptions.minimum_trade_ratio,
        "minimum_trade_ratio",
    )

    constraints = stage2_result.stage3_constraints
    acceptable_loss = _nonnegative(
        constraints.get("acceptable_fx_loss", "0"),
        "acceptable_fx_loss",
    )
    minimum_cash_buffer = _nonnegative(
        constraints.get("minimum_cash_buffer", "0"),
        "minimum_cash_buffer",
    )
    credit_limit = _nonnegative(
        constraints.get("credit_limit", "0"),
        "credit_limit",
    )
    open_exposure = _nonnegative(
        constraints.get("open_exposure", stage2_result.open_exposure),
        "open_exposure",
    )
    total_foreign_amount = _nonnegative(
        stage2_result.total_foreign_amount,
        "total_foreign_amount",
    )
    held_fx_used = _nonnegative(
        stage2_result.held_fx_used,
        "held_fx_used",
    )
    hedged_amount = _nonnegative(
        stage2_result.hedged_amount,
        "hedged_amount",
    )
    base_rate = _decimal(
        constraints.get("base_rate", "0"),
        "base_rate",
    )
    if base_rate <= 0:
        raise ValueError("Stage 3 base rate는 0보다 커야 합니다.")
    forward_effective_rate = (
        _decimal(
            effective_assumptions.forward_effective_rate,
            "forward_effective_rate",
        )
        if effective_assumptions.forward_effective_rate is not None
        else base_rate
    )
    if forward_effective_rate <= 0:
        raise ValueError("forward_effective_rate는 0보다 커야 합니다.")

    held_fx_ratio = (
        held_fx_used / total_foreign_amount
        if total_foreign_amount > 0
        else Decimal("0")
    )
    existing_hedge_ratio = (
        hedged_amount / total_foreign_amount
        if total_foreign_amount > 0
        else Decimal("0")
    )
    new_hedge_reference_flow = open_exposure * base_rate
    q90_scenario, fixed_10_scenario = _adverse_scenarios(stage2_result)
    expected_full = (
        _nonnegative(
            stage2_result.expected_adverse_loss,
            "expected_adverse_loss",
        )
        if stage2_result.expected_adverse_loss is not None
        else None
    )

    evaluated: List[Dict[str, Any]] = []
    all_failures: List[str] = []
    for forward_percent in range(0, 101, grid_step_percent):
        remaining = 100 - forward_percent
        for staged_percent in range(
            0,
            remaining + 1,
            grid_step_percent,
        ):
            unhedged_percent = remaining - staged_percent
            forward = _ratio(forward_percent)
            staged = _ratio(staged_percent)
            unhedged = _ratio(unhedged_percent)
            if not ratio_sum_is_one(forward, staged, unhedged):
                continue

            failures: List[str] = []
            if forward > maximum_forward_ratio:
                failures.append("MAXIMUM_FORWARD_RATIO_EXCEEDED")
            total_hedge_ratio = existing_hedge_ratio + (
                open_exposure * forward / total_foreign_amount
                if total_foreign_amount > 0
                else Decimal("0")
            )
            if total_hedge_ratio > 1:
                failures.append("TOTAL_HEDGE_RATIO_EXCEEDED")
            for ratio_value in (forward, staged):
                if 0 < ratio_value < minimum_trade_ratio:
                    failures.append("MINIMUM_TRADE_RATIO_NOT_MET")

            risk_factor = unhedged + staged * staged_risk_factor
            forward_rate_difference = abs(
                forward_effective_rate - base_rate
            )
            hedge_cost = (
                open_exposure
                * forward
                * (
                    forward_rate_difference
                    + base_rate * forward_fee_rate
                )
                + new_hedge_reference_flow
                * staged
                * staged_fee_rate
            )
            (
                minimum_cash,
                buffer_shortfall,
                post_credit_deficit,
                worst_loss,
            ) = _candidate_cash_metrics(
                scenarios=stage2_result.scenario_results,
                risk_factor=risk_factor,
                hedge_cost=hedge_cost,
                minimum_cash_buffer=minimum_cash_buffer,
                credit_limit=credit_limit,
            )
            q90_loss = _scenario_residual_loss(
                q90_scenario,
                risk_factor=risk_factor,
                hedge_cost=hedge_cost,
            )
            fixed_10_loss = _scenario_residual_loss(
                fixed_10_scenario,
                risk_factor=risk_factor,
                hedge_cost=hedge_cost,
            )
            if worst_loss > acceptable_loss:
                failures.append("ACCEPTABLE_LOSS_EXCEEDED")
            if (
                q90_loss is not None
                and q90_loss > acceptable_loss
            ):
                failures.append("Q90_LOSS_LIMIT_EXCEEDED")
            if fixed_10_scenario is None:
                failures.append("FIXED_10_SCENARIO_MISSING")
            if buffer_shortfall > 0:
                failures.append("MINIMUM_CASH_BUFFER_NOT_MET")
            if post_credit_deficit > 0:
                failures.append("POST_CREDIT_PAYMENT_GAP")

            expected_loss = (
                expected_full * risk_factor + hedge_cost
                if expected_full is not None
                else None
            )
            concentration = (
                new_hedge_reference_flow
                * concentration_penalty
                * (
                    forward * forward
                    + staged * staged
                    + unhedged * unhedged
                )
            )
            data: Dict[str, Any] = {
                "forward": forward,
                "staged": staged,
                "unhedged": unhedged,
                "worst_loss": worst_loss,
                "expected_loss": expected_loss,
                "hedge_cost": hedge_cost,
                "shortfall": buffer_shortfall,
                "minimum_cash": minimum_cash,
                "post_credit_deficit": post_credit_deficit,
                "q90_loss": q90_loss,
                "fixed_10_loss": fixed_10_loss,
                "concentration": concentration,
                "failures": list(dict.fromkeys(failures)),
            }
            evaluated.append(data)
            all_failures.extend(data["failures"])

    feasible = [
        item for item in evaluated if not item["failures"]
    ]
    selected: List[Tuple[str, Dict[str, Any]]] = []
    selected_ids = set()
    for (
        profile,
        risk_weight,
        cost_weight,
        buffer_weight,
        concentration_weight,
    ) in PROFILE_WEIGHTS:
        ranked = sorted(
            feasible,
            key=lambda item: (
                item["worst_loss"]
                * risk_weight
                * (Decimal("0.5") + preference)
                + item["hedge_cost"] * cost_weight
                + item["shortfall"]
                * buffer_weight
                * liquidity_penalty
                + item["concentration"] * concentration_weight,
                item["hedge_cost"],
                item["unhedged"],
            ),
        )
        choice = next(
            (
                item
                for item in ranked
                if (
                    item["forward"],
                    item["staged"],
                    item["unhedged"],
                )
                not in selected_ids
            ),
            None,
        )
        if choice is None:
            continue
        selected.append((profile, choice))
        selected_ids.add(
            (
                choice["forward"],
                choice["staged"],
                choice["unhedged"],
            )
        )

    candidates: List[StrategyCandidate] = []
    for rank, profile_and_data in enumerate(selected, start=1):
        profile, data = profile_and_data
        product_types: List[str] = []
        if data["forward"] > 0:
            product_types.append("FORWARD")
        if data["staged"] > 0:
            product_types.extend(["STAGED_CONVERSION", "FX_DEPOSIT"])
        product_types.append("FX_RISK_INSURANCE_REVIEW")
        candidates.append(
            StrategyCandidate(
                rank=rank,
                profile=profile,
                forward_ratio=format(data["forward"], "f"),
                staged_conversion_ratio=format(data["staged"], "f"),
                unhedged_ratio=format(data["unhedged"], "f"),
                held_fx_ratio=format(held_fx_ratio, "f"),
                worst_case_loss=money_string(data["worst_loss"]),
                expected_loss=(
                    money_string(data["expected_loss"])
                    if isinstance(data["expected_loss"], Decimal)
                    else None
                ),
                assumed_hedge_cost=money_string(data["hedge_cost"]),
                estimated_buffer_shortfall=money_string(
                    data["shortfall"]
                ),
                liquidity_impact=money_string(data["shortfall"]),
                q90_adverse_loss=(
                    money_string(data["q90_loss"])
                    if isinstance(data["q90_loss"], Decimal)
                    else None
                ),
                fixed_10_adverse_loss=(
                    money_string(data["fixed_10_loss"])
                    if isinstance(data["fixed_10_loss"], Decimal)
                    else None
                ),
                minimum_cash_balance=money_string(
                    data["minimum_cash"]
                ),
                post_credit_deficit=money_string(
                    data["post_credit_deficit"]
                ),
                constraints_satisfied=True,
                acceptable_loss_exceeded=False,
                constraint_failures=[],
                rationale=candidate_reason(
                    data["forward"],
                    data["staged"],
                    data["unhedged"],
                    True,
                ),
                limitations=[
                    "실제 상품 가격이 아닌 명시된 시뮬레이션 가정입니다.",
                    "실제 한도·가격·회계 영향은 금융기관 확인이 필요합니다.",
                ],
                required_product_types=list(
                    dict.fromkeys(product_types)
                ),
            )
        )

    objective_mode = (
        "PROBABILITY_WEIGHTED"
        if stage2_result.expected_adverse_loss is not None
        else "WORST_CASE_ROBUST"
    )
    no_candidate = not candidates
    return Stage3Result(
        status=(
            "NO_FEASIBLE_CANDIDATE"
            if no_candidate
            else "CANDIDATES_NOT_ADVICE"
        ),
        grid_step_percent=grid_step_percent,
        objective_mode=objective_mode,
        candidates=candidates,
        assumptions_contract=effective_assumptions,
        infeasible_reasons=(
            list(dict.fromkeys(all_failures))
            if no_candidate
            else []
        ),
        assumptions=[
            "후보는 자문이 아니라 입력 가정 아래 grid 탐색한 검토안입니다.",
            "선물환·분할환전 비용은 assumptions_contract의 bps 가정입니다.",
            "신규 헤지 비용은 자연상계·보유외화·기존헤지 제외 후 open exposure에만 적용했습니다.",
            "q90은 발생확률이 아니라 모델 예측분포의 경로위험 분위수입니다.",
        ],
        warnings=(
            [
                "제약을 모두 충족하는 후보가 없습니다. 추가 자금, "
                "결제조건 조정 또는 은행 상담이 필요합니다."
            ]
            if no_candidate
            else [
                "SIMULATED_CANDIDATE: 실제 가격, 신용한도, 세무·회계 "
                "영향은 금융기관과 확인해야 합니다."
            ]
        ),
    )
