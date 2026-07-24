from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import DefaultDict, Dict, List, Tuple

from src.domain.stage2_models import (
    CompositeStress,
    KrwCashflowEvent,
    LedgerEntry,
)
from src.stage2.metrics import (
    decimal_percent,
    decimal_value,
    money_string,
)


DailyEventMap = DefaultDict[
    date,
    Dict[str, object],
]


def apply_composite_stress(
    events: List[KrwCashflowEvent],
    stress: CompositeStress,
) -> List[KrwCashflowEvent]:
    revenue_reduction = decimal_percent(
        stress.revenue_reduction_percent,
        "revenue_reduction_percent",
    )
    cost_increase = decimal_percent(
        stress.cost_increase_percent,
        "cost_increase_percent",
    )
    transformed: List[KrwCashflowEvent] = []
    for event in events:
        event_date = date.fromisoformat(event.date)
        amount = decimal_value(
            event.amount,
            "krw_cashflow.amount",
            allow_zero=False,
        )
        if event.category == "REVENUE" and event.direction == "INFLOW":
            amount *= Decimal("1") - revenue_reduction
            event_date += timedelta(days=stress.revenue_delay_days)
        elif event.category == "COST" and event.direction == "OUTFLOW":
            amount *= Decimal("1") + cost_increase

        transformed.append(
            event.model_copy(
                update={
                    "date": event_date.isoformat(),
                    "amount": money_string(amount),
                }
            )
        )
    return transformed


def new_daily_event_map() -> DailyEventMap:
    return defaultdict(
        lambda: {
            "inflow": Decimal("0"),
            "outflow": Decimal("0"),
            "descriptions": [],
        }
    )


def add_daily_event(
    event_map: DailyEventMap,
    *,
    event_date: date,
    inflow: Decimal = Decimal("0"),
    outflow: Decimal = Decimal("0"),
    description: str,
) -> None:
    item = event_map[event_date]
    item["inflow"] = item["inflow"] + inflow
    item["outflow"] = item["outflow"] + outflow
    descriptions = item["descriptions"]
    if isinstance(descriptions, list):
        descriptions.append(description)


def build_ledger(
    *,
    event_map: DailyEventMap,
    as_of_date: date,
    initial_cash: Decimal,
    minimum_buffer: Decimal,
    credit_limit: Decimal,
    scenario_name: str,
    source_status: str,
) -> Tuple[List[LedgerEntry], Dict[str, object]]:
    balance = initial_cash
    minimum_cash = initial_cash
    first_buffer_shortfall_date = (
        as_of_date.isoformat()
        if initial_cash < minimum_buffer
        else None
    )
    maximum_buffer_shortfall = max(
        minimum_buffer - initial_cash,
        Decimal("0"),
    )
    maximum_cash_deficit = max(-initial_cash, Decimal("0"))
    maximum_post_credit_shortfall = max(
        -(initial_cash + credit_limit),
        Decimal("0"),
    )
    ledger: List[LedgerEntry] = []

    for event_date in sorted(event_map):
        if event_date < as_of_date:
            raise ValueError(
                "as_of_date 이전의 KRW cashflow는 current cash와 중복될 수 있습니다."
            )
        item = event_map[event_date]
        inflow = item["inflow"]
        outflow = item["outflow"]
        if not isinstance(inflow, Decimal) or not isinstance(outflow, Decimal):
            raise ValueError("내부 일자별 원화 이벤트가 올바르지 않습니다.")

        balance = balance + inflow - outflow
        minimum_cash = min(minimum_cash, balance)
        buffer_shortfall = max(minimum_buffer - balance, Decimal("0"))
        cash_deficit = max(-balance, Decimal("0"))
        post_credit_shortfall = max(
            -(balance + credit_limit),
            Decimal("0"),
        )
        if buffer_shortfall > 0 and first_buffer_shortfall_date is None:
            first_buffer_shortfall_date = event_date.isoformat()
        maximum_buffer_shortfall = max(
            maximum_buffer_shortfall,
            buffer_shortfall,
        )
        maximum_cash_deficit = max(maximum_cash_deficit, cash_deficit)
        maximum_post_credit_shortfall = max(
            maximum_post_credit_shortfall,
            post_credit_shortfall,
        )
        descriptions = item["descriptions"]
        ledger.append(
            LedgerEntry(
                date=event_date.isoformat(),
                scenario=scenario_name,
                source_status=source_status,
                descriptions=(
                    list(descriptions)
                    if isinstance(descriptions, list)
                    else []
                ),
                krw_inflow=money_string(inflow),
                krw_outflow=money_string(outflow),
                balance=money_string(balance),
                buffer_shortfall=money_string(buffer_shortfall),
                cash_deficit=money_string(cash_deficit),
                post_credit_shortfall=money_string(
                    post_credit_shortfall
                ),
            )
        )

    return ledger, {
        "ending_cash": balance,
        "minimum_cash": minimum_cash,
        "first_buffer_shortfall_date": first_buffer_shortfall_date,
        "maximum_buffer_shortfall": maximum_buffer_shortfall,
        "cash_deficit": maximum_cash_deficit,
        "post_credit_shortfall": maximum_post_credit_shortfall,
    }
