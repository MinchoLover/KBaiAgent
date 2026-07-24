from typing import List, Optional

from pydantic import Field

from schemas import StrictModel


class StrategyCandidate(StrictModel):
    rank: int
    forward_ratio: str
    staged_conversion_ratio: str
    unhedged_ratio: str
    held_fx_ratio: str = "0"
    worst_case_loss: str
    expected_loss: Optional[str] = None
    assumed_hedge_cost: str
    estimated_buffer_shortfall: str
    liquidity_impact: str = "0.00"
    constraints_satisfied: bool
    acceptable_loss_exceeded: bool = False
    rationale: str
    limitations: List[str] = Field(default_factory=list)
    required_product_types: List[str] = Field(default_factory=list)


class Stage3Result(StrictModel):
    schema_version: str = "1.0"
    status: str = "CANDIDATES_NOT_ADVICE"
    grid_step_percent: int
    objective_mode: str
    candidates: List[StrategyCandidate] = Field(min_length=3, max_length=3)
    assumptions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
