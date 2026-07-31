from decimal import Decimal
from typing import Tuple


def applied_customer_rate(
    *,
    reference_rate: Decimal,
    trade_type: str,
    bank_spread_bps: Decimal,
) -> Decimal:
    spread = bank_spread_bps / Decimal("10000")
    if trade_type == "IMPORT":
        return reference_rate * (Decimal("1") + spread)
    if trade_type == "EXPORT":
        sell_rate = reference_rate * (Decimal("1") - spread)
        if sell_rate <= 0:
            raise ValueError("은행 spread 적용 후 매도환율이 0 이하입니다.")
        return sell_rate
    raise ValueError("trade_type은 IMPORT 또는 EXPORT여야 합니다.")


def adverse_loss_vs_base(
    *,
    trade_type: str,
    scenario_inflow: Decimal,
    scenario_outflow: Decimal,
    base_inflow: Decimal,
    base_outflow: Decimal,
) -> Decimal:
    signed = signed_impact_vs_base(
        trade_type=trade_type,
        scenario_inflow=scenario_inflow,
        scenario_outflow=scenario_outflow,
        base_inflow=base_inflow,
        base_outflow=base_outflow,
    )
    return max(signed, Decimal("0"))


def signed_impact_vs_base(
    *,
    trade_type: str,
    scenario_inflow: Decimal,
    scenario_outflow: Decimal,
    base_inflow: Decimal,
    base_outflow: Decimal,
) -> Decimal:
    if trade_type == "IMPORT":
        return scenario_outflow - base_outflow
    return base_inflow - scenario_inflow
