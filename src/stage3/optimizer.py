from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from src.domain.stage2_models import Stage2Result
from src.domain.stage3_models import Stage3Result, StrategyCandidate
from src.stage2.metrics import money_string
from src.stage3.constraints import constraint_penalties, ratio_sum_is_one
from src.stage3.explanations import candidate_reason


FORWARD_COST_RATE = Decimal("0.0015")
STAGED_COST_RATE = Decimal("0.0005")
STAGED_RISK_FACTOR = Decimal("0.5")


def _ratio(value: int) -> Decimal:
    return Decimal(value) / Decimal("100")


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Stage 2 제약 숫자가 올바르지 않습니다.") from exc
    if not parsed.is_finite():
        raise ValueError("Stage 2 제약 숫자는 유한해야 합니다.")
    return parsed


def generate_strategy_candidates(
    stage2_result: Stage2Result,
    *,
    grid_step_percent: int = 10,
    stability_preference: str = "0.7",
) -> Stage3Result:
    if grid_step_percent not in {5, 10}:
        raise ValueError("grid step은 5 또는 10이어야 합니다.")
    preference = _decimal(stability_preference)
    if preference < 0 or preference > 1:
        raise ValueError("stability_preference는 0과 1 사이여야 합니다.")

    constraints = stage2_result.stage3_constraints
    acceptable_loss = _decimal(
        str(constraints.get("acceptable_fx_loss", "0"))
    )
    full_worst_loss = max(
        [
            max(_decimal(item.loss_vs_base), Decimal("0"))
            for item in stage2_result.scenario_results
        ]
        or [Decimal("0")]
    )
    worst_buffer_shortfall = max(
        [
            _decimal(item.maximum_buffer_shortfall)
            for item in stage2_result.scenario_results
        ]
        or [Decimal("0")]
    )
    open_exposure = _decimal(
        str(constraints.get("open_exposure", stage2_result.open_exposure))
    )
    total_foreign_amount = _decimal(stage2_result.total_foreign_amount)
    held_fx_used = _decimal(stage2_result.held_fx_used)
    held_fx_ratio = (
        held_fx_used / total_foreign_amount
        if total_foreign_amount > 0
        else Decimal("0")
    )
    base_rate = _decimal(str(constraints.get("base_rate", "0")))
    if open_exposure < 0 or base_rate <= 0:
        raise ValueError(
            "Stage 3 open exposure와 base rate가 올바르지 않습니다."
        )
    new_hedge_reference_flow = open_exposure * base_rate
    expected_full = (
        _decimal(stage2_result.expected_adverse_loss)
        if stage2_result.expected_adverse_loss is not None
        else None
    )

    scored: List[Tuple[Decimal, Dict[str, object]]] = []
    for forward_percent in range(
        0,
        101,
        grid_step_percent,
    ):
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

            risk_factor = unhedged + staged * STAGED_RISK_FACTOR
            hedge_cost = new_hedge_reference_flow * (
                forward * FORWARD_COST_RATE
                + staged * STAGED_COST_RATE
            )
            candidate_worst_loss = full_worst_loss * risk_factor + hedge_cost
            expected_loss = (
                expected_full * risk_factor + hedge_cost
                if expected_full is not None
                else None
            )
            estimated_shortfall = worst_buffer_shortfall * (
                Decimal("1")
                - forward * Decimal("0.5")
                - staged * Decimal("0.25")
            )
            penalties = constraint_penalties(
                worst_case_loss=candidate_worst_loss,
                acceptable_loss=acceptable_loss,
                estimated_buffer_shortfall=estimated_shortfall,
            )
            score = (
                candidate_worst_loss
                * (Decimal("0.5") + preference)
                + hedge_cost * (Decimal("1") - preference)
                + penalties["loss_limit_violation"] * Decimal("10")
                + penalties["buffer_shortfall"] * Decimal("5")
            )
            satisfied = (
                penalties["loss_limit_violation"] == 0
                and penalties["buffer_shortfall"] == 0
            )
            product_types: List[str] = []
            if forward > 0:
                product_types.append("FORWARD")
            if staged > 0:
                product_types.extend(["STAGED_CONVERSION", "FX_DEPOSIT"])
            if stage2_result.trade_type in {"IMPORT", "EXPORT"}:
                product_types.append("FX_RISK_INSURANCE_REVIEW")

            scored.append(
                (
                    score,
                    {
                        "forward": forward,
                        "staged": staged,
                        "unhedged": unhedged,
                        "worst_loss": candidate_worst_loss,
                        "expected_loss": expected_loss,
                        "hedge_cost": hedge_cost,
                        "shortfall": estimated_shortfall,
                        "satisfied": satisfied,
                        "product_types": list(dict.fromkeys(product_types)),
                    },
                )
            )

    scored.sort(
        key=lambda item: (
            item[0],
            item[1]["hedge_cost"],
            item[1]["unhedged"],
        )
    )
    candidates: List[StrategyCandidate] = []
    for rank, unused_and_data in enumerate(scored[:3], start=1):
        unused_score, data = unused_and_data
        del unused_score
        expected_loss_value = data["expected_loss"]
        candidates.append(
            StrategyCandidate(
                rank=rank,
                forward_ratio=format(data["forward"], "f"),
                staged_conversion_ratio=format(data["staged"], "f"),
                unhedged_ratio=format(data["unhedged"], "f"),
                held_fx_ratio=format(held_fx_ratio, "f"),
                worst_case_loss=money_string(data["worst_loss"]),
                expected_loss=(
                    money_string(expected_loss_value)
                    if isinstance(expected_loss_value, Decimal)
                    else None
                ),
                assumed_hedge_cost=money_string(data["hedge_cost"]),
                estimated_buffer_shortfall=money_string(data["shortfall"]),
                liquidity_impact=money_string(data["shortfall"]),
                constraints_satisfied=bool(data["satisfied"]),
                acceptable_loss_exceeded=(
                    data["worst_loss"] > acceptable_loss
                ),
                rationale=candidate_reason(
                    data["forward"],
                    data["staged"],
                    data["unhedged"],
                    bool(data["satisfied"]),
                ),
                limitations=[
                    "비용률과 분할환전 잔여 위험계수는 데모 가정입니다.",
                    "실제 가격·한도·회계 영향은 금융기관 확인이 필요합니다.",
                ],
                required_product_types=data["product_types"],
            )
        )

    objective_mode = (
        "PROBABILITY_WEIGHTED"
        if stage2_result.expected_adverse_loss is not None
        else "WORST_CASE_ROBUST"
    )
    return Stage3Result(
        grid_step_percent=grid_step_percent,
        objective_mode=objective_mode,
        candidates=candidates,
        assumptions=[
            "후보는 자문이 아니라 입력 가정 아래 grid 탐색한 검토안입니다.",
            "선물환 비용률 0.15%, 분할환전 비용률 0.05%를 데모 가정으로 사용했습니다.",
            "신규 헤지 비용은 기존 헤지·자연상계 제외 후 open exposure에만 적용했습니다.",
            "분할환전 잔여 위험은 미헤지의 50%로 근사했습니다.",
        ],
        warnings=[
            "실제 가격, 신용한도, 세무·회계 영향은 금융기관과 확인해야 합니다."
        ],
    )
