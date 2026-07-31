from typing import List, Literal, Optional

from pydantic import Field

from schemas import StrictModel


class Stage3Assumptions(StrictModel):
    forward_effective_rate: Optional[str] = None
    forward_fee_bps: str = "15"
    staged_conversion_fee_bps: str = "5"
    staged_risk_factor: str = "0.5"
    staged_dates: List[str] = Field(default_factory=list)
    risk_aversion_weight: str = "0.7"
    liquidity_shortfall_penalty: str = "5"
    concentration_penalty: str = "0.02"
    maximum_forward_ratio: str = "1"
    minimum_trade_ratio: str = "0"
    simulation_status: Literal[
        "SIMULATED_CANDIDATE"
    ] = "SIMULATED_CANDIDATE"


class StrategyCandidate(StrictModel):
    rank: int
    profile: Literal[
        "STABILITY_FIRST",
        "BALANCED",
        "COST_FIRST",
    ] = "BALANCED"
    forward_ratio: str
    staged_conversion_ratio: str
    unhedged_ratio: str
    held_fx_ratio: str = "0"
    worst_case_loss: str
    expected_loss: Optional[str] = None
    assumed_hedge_cost: str
    estimated_buffer_shortfall: str
    liquidity_impact: str = "0.00"
    q90_adverse_loss: Optional[str] = None
    fixed_10_adverse_loss: Optional[str] = None
    minimum_cash_balance: str = "0.00"
    post_credit_deficit: str = "0.00"
    constraints_satisfied: bool
    acceptable_loss_exceeded: bool = False
    constraint_failures: List[str] = Field(default_factory=list)
    simulation_status: Literal[
        "SIMULATED_CANDIDATE"
    ] = "SIMULATED_CANDIDATE"
    rationale: str
    limitations: List[str] = Field(default_factory=list)
    required_product_types: List[str] = Field(default_factory=list)


class Stage3Result(StrictModel):
    schema_version: str = "1.0"
    status: Literal[
        "CANDIDATES_NOT_ADVICE",
        "NO_FEASIBLE_CANDIDATE",
    ] = "CANDIDATES_NOT_ADVICE"
    grid_step_percent: int
    objective_mode: str
    candidates: List[StrategyCandidate] = Field(
        default_factory=list,
        max_length=3,
    )
    assumptions_contract: Stage3Assumptions = Field(
        default_factory=Stage3Assumptions
    )
    infeasible_reasons: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
