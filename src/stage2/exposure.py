from decimal import Decimal
from typing import List, Tuple

from src.domain.stage2_models import (
    ExposureComputation,
    ExposureInput,
)
from src.stage2.metrics import date_value, decimal_string, decimal_value


def compute_exposure(
    exposure: ExposureInput,
) -> Tuple[ExposureComputation, List[str]]:
    settlement = date_value(exposure.settlement_date, "settlement_date")
    trade_amount = decimal_value(
        exposure.foreign_amount,
        "foreign_amount",
        allow_zero=False,
    )
    usable_balance = decimal_value(
        exposure.usable_fx_balance,
        "usable_fx_balance",
    )
    warnings: List[str] = []
    eligible_flow_amount = Decimal("0")

    if exposure.trade_type == "IMPORT":
        offset_direction = "INFLOW"
        available_offset = usable_balance
    else:
        offset_direction = "OUTFLOW"
        available_offset = Decimal("0")
        if usable_balance > 0:
            warnings.append(
                "수출 receivable에는 보유외화를 자연상계로 사용하지 않았습니다."
            )

    for flow in exposure.same_currency_flows:
        flow_date = date_value(flow.date, "same_currency_flow.date")
        amount = decimal_value(
            flow.amount,
            "same_currency_flow.amount",
            allow_zero=False,
        )
        if flow.currency.strip().upper() != exposure.currency.strip().upper():
            warnings.append(
                "다른 통화의 자연상계 후보를 제외했습니다: {}".format(
                    flow.currency
                )
            )
            continue
        if flow.direction != offset_direction:
            warnings.append(
                "{} 거래에 {} 동일통화 흐름은 자연상계 방향이 아니어서 "
                "제외했습니다.".format(
                    exposure.trade_type,
                    flow.direction,
                )
            )
            continue
        if flow_date <= settlement:
            eligible_flow_amount += amount
        else:
            warnings.append(
                "결제일 이후의 동일통화 흐름을 자연상계에서 제외했습니다."
            )

    held_fx_used = min(trade_amount, available_offset)
    remaining_after_held_fx = trade_amount - held_fx_used
    same_currency_offset = min(
        remaining_after_held_fx,
        eligible_flow_amount,
    )
    natural_offset = held_fx_used + same_currency_offset
    remaining_after_natural = trade_amount - natural_offset

    hedge_amount = Decimal("0")
    if exposure.existing_hedge is not None:
        requested_hedge = decimal_value(
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
        # A signed hedge is a real cash-flow contract. Do not erase or cap it
        # merely because a natural offset also exists; flag over-hedging while
        # keeping the full contracted amount in the cash-flow calculation.
        hedge_amount = requested_hedge
        if requested_hedge > remaining_after_natural:
            warnings.append(
                "기존 헤지금액이 자연상계 후 노출보다 커 over-hedge 가능성이 있습니다."
            )

    open_exposure = max(
        trade_amount - natural_offset - hedge_amount,
        Decimal("0"),
    )
    return (
        ExposureComputation(
            sequence=exposure.sequence,
            trade_type=exposure.trade_type,
            foreign_amount=decimal_string(trade_amount),
            natural_offset=decimal_string(natural_offset),
            held_fx_used=decimal_string(held_fx_used),
            same_currency_offset=decimal_string(same_currency_offset),
            hedged_amount=decimal_string(hedge_amount),
            open_exposure=decimal_string(open_exposure),
            settlement_date=exposure.settlement_date,
        ),
        warnings,
    )
