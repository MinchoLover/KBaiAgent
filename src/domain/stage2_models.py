from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from schemas import StrictModel


class SameCurrencyFlow(StrictModel):
    date: str
    amount: str
    currency: str
    direction: Literal["INFLOW", "OUTFLOW"]
    description: str = ""


class ExistingHedge(StrictModel):
    amount: str
    locked_rate: str
    fee: str = "0"


class ExposureInput(StrictModel):
    sequence: int = Field(ge=1)
    trade_type: Literal["IMPORT", "EXPORT"]
    currency: str
    foreign_amount: str
    settlement_date: str
    usable_fx_balance: str = "0"
    same_currency_flows: List[SameCurrencyFlow] = Field(
        default_factory=list
    )
    existing_hedge: Optional[ExistingHedge] = None


class KrwCashflowEvent(StrictModel):
    date: str
    amount: str
    direction: Literal["INFLOW", "OUTFLOW"]
    category: Literal["REVENUE", "COST", "OTHER"] = "OTHER"
    description: str = ""


class CompositeStress(StrictModel):
    revenue_reduction_percent: str = "0"
    revenue_delay_days: int = Field(default=0, ge=0, le=365)
    cost_increase_percent: str = "0"


class Stage2Input(StrictModel):
    schema_version: str = "1.0"
    as_of_date: str
    exposures: List[ExposureInput] = Field(min_length=1)
    current_krw_cash: str
    minimum_cash_buffer: str
    credit_limit: str = "0"
    acceptable_fx_loss: str = "0"
    krw_cashflows: List[KrwCashflowEvent] = Field(default_factory=list)
    bank_spread_bps: str = "0"
    bank_fee: str = "0"
    composite_stress: CompositeStress = Field(
        default_factory=CompositeStress
    )


class ExposureComputation(StrictModel):
    sequence: int
    trade_type: Literal["IMPORT", "EXPORT"]
    foreign_amount: str
    natural_offset: str
    held_fx_used: str = "0"
    same_currency_offset: str = "0"
    hedged_amount: str
    open_exposure: str
    settlement_date: str


class LedgerEntry(StrictModel):
    date: str
    scenario: str
    source_status: Literal["CALCULATION"]
    descriptions: List[str] = Field(default_factory=list)
    krw_inflow: str
    krw_outflow: str
    balance: str
    buffer_shortfall: str
    cash_deficit: str
    post_credit_shortfall: str


class ScenarioResult(StrictModel):
    scenario_name: str
    scenario_kind: Literal["STRESS", "FORECAST"]
    probability: Optional[str] = None
    scenario_rate: str
    applied_rate: str
    fx_krw_inflow: str
    fx_krw_outflow: str
    loss_vs_base: str
    ending_cash: str
    minimum_cash: str
    first_buffer_shortfall_date: Optional[str] = None
    maximum_buffer_shortfall: str
    cash_deficit: str
    post_credit_shortfall: str
    acceptable_loss_exceeded: bool
    ledger: List[LedgerEntry] = Field(default_factory=list)


class Stage2Result(StrictModel):
    schema_version: str = "1.0"
    status: Literal["CALCULATION"] = "CALCULATION"
    trade_type: Literal["IMPORT", "EXPORT"]
    currency: str
    total_foreign_amount: str
    natural_offset: str
    held_fx_used: str = "0"
    same_currency_offset: str = "0"
    hedged_amount: str
    open_exposure: str
    base_required_or_proceeds_krw: str
    comparison_basis: str
    exposure_computations: List[ExposureComputation]
    scenario_results: List[ScenarioResult]
    expected_adverse_loss: Optional[str] = None
    buffer_shortfall_probability: Optional[str] = None
    cash_deficit_probability: Optional[str] = None
    assumptions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    stage3_constraints: Dict[str, Any] = Field(default_factory=dict)
