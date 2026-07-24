from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from schemas import StrictModel
from src.domain.stage2_models import (
    CompositeStress,
    ExistingHedge,
    ExposureInput,
    KrwCashflowEvent,
    SameCurrencyFlow,
    Stage2Input,
)
from src.stage2.allocation import (
    allocate_capped,
    allocate_capped_by_date,
    allocate_fee_proportionally,
)
from src.stage2.metrics import decimal_value


class Stage2FormInput(StrictModel):
    as_of_date: str
    current_krw_cash: str
    minimum_cash_buffer: str
    credit_limit: str
    usable_fx_balance: str
    acceptable_fx_loss: str
    same_currency_flow_amount: str
    same_currency_flow_date: str
    same_currency_flow_direction: Literal["INFLOW", "OUTFLOW"]
    existing_hedge_amount: str
    existing_hedge_rate: str
    existing_hedge_fee: str
    bank_spread_bps: str
    bank_fee: str
    krw_cashflow_rows: List[Dict[str, Any]] = Field(default_factory=list)
    revenue_reduction_percent: str = "0"
    revenue_delay_days: int = Field(default=0, ge=0, le=365)
    cost_increase_percent: str = "0"


def _decimal_text(
    value: Any,
    field_name: str,
    *,
    allow_zero: bool = True,
    allow_negative: bool = False,
) -> str:
    text = str(value).strip().replace(",", "")
    parsed = decimal_value(
        text,
        field_name,
        allow_zero=allow_zero,
        allow_negative=allow_negative,
    )
    return format(parsed, "f")


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text in {"", "nan", "NaN", "NaT", "<NA>"}:
        return None
    return text


def _krw_cashflows(
    rows: List[Dict[str, Any]],
) -> List[KrwCashflowEvent]:
    events: List[KrwCashflowEvent] = []
    for row in rows:
        amount = _optional_text(row.get("amount"))
        if amount is None:
            continue
        row_date = row.get("date")
        if hasattr(row_date, "isoformat"):
            row_date = row_date.isoformat()
        events.append(
            KrwCashflowEvent(
                date=str(row_date),
                amount=_decimal_text(
                    amount,
                    "원화 현금흐름",
                    allow_zero=False,
                ),
                direction=str(row.get("direction")),
                category=str(row.get("category")),
                description=str(row.get("description") or ""),
            )
        )
    return events


def build_stage2_input_from_form(
    *,
    document_input: Dict[str, Any],
    form: Stage2FormInput,
) -> Stage2Input:
    trade = document_input.get("trade")
    if not isinstance(trade, dict):
        raise ValueError("확인된 Stage 0 거래 입력이 필요합니다.")
    cash_events = trade.get("cashflow_events")
    if not isinstance(cash_events, list) or not cash_events:
        raise ValueError("확인된 결제 현금흐름이 필요합니다.")

    event_amounts = [
        str(item["foreign_amount"]) for item in cash_events
    ]
    total_trade_amount = sum(
        (Decimal(item) for item in event_amounts),
        Decimal("0"),
    )
    usable_total = _decimal_text(
        form.usable_fx_balance,
        "사용 가능한 보유외화",
    )
    hedge_total = _decimal_text(
        form.existing_hedge_amount,
        "기존 헤지 외화금액",
    )
    if Decimal(hedge_total) > total_trade_amount:
        raise ValueError("기존 헤지금액이 전체 거래금액보다 클 수 없습니다.")

    usable_allocations = allocate_capped(
        usable_total,
        event_amounts,
    )
    hedge_allocations = allocate_capped(
        hedge_total,
        event_amounts,
    )
    flow_amount = _decimal_text(
        form.same_currency_flow_amount,
        "동일통화 흐름",
    )
    flow_allocations = allocate_capped_by_date(
        flow_amount,
        event_amounts,
        [str(item["settlement_date"]) for item in cash_events],
        form.same_currency_flow_date,
    )
    hedge_fee_total = _decimal_text(
        form.existing_hedge_fee,
        "헤지 수수료",
    )
    if Decimal(hedge_total) == 0 and Decimal(hedge_fee_total) > 0:
        raise ValueError("헤지 수수료가 있으면 기존 헤지금액도 필요합니다.")
    hedge_fee_allocations = allocate_fee_proportionally(
        hedge_fee_total,
        hedge_allocations,
    )

    exposures: List[ExposureInput] = []
    for index, event in enumerate(cash_events):
        flows: List[SameCurrencyFlow] = []
        if Decimal(flow_allocations[index]) > 0:
            flows.append(
                SameCurrencyFlow(
                    date=form.same_currency_flow_date,
                    amount=flow_allocations[index],
                    currency=str(trade["currency"]),
                    direction=form.same_currency_flow_direction,
                    description="사용자 입력 자연헤지 후보",
                )
            )
        hedge: Optional[ExistingHedge] = None
        if Decimal(hedge_allocations[index]) > 0:
            hedge = ExistingHedge(
                amount=hedge_allocations[index],
                locked_rate=_decimal_text(
                    form.existing_hedge_rate,
                    "약정환율",
                    allow_zero=False,
                ),
                fee=hedge_fee_allocations[index],
            )
        exposures.append(
            ExposureInput(
                sequence=int(event["sequence"]),
                trade_type=str(trade["trade_type"]),
                currency=str(event["currency"]),
                foreign_amount=str(event["foreign_amount"]),
                settlement_date=str(event["settlement_date"]),
                usable_fx_balance=usable_allocations[index],
                same_currency_flows=flows,
                existing_hedge=hedge,
            )
        )

    return Stage2Input(
        as_of_date=form.as_of_date,
        exposures=exposures,
        current_krw_cash=_decimal_text(
            form.current_krw_cash,
            "현재 원화 현금",
            allow_negative=True,
        ),
        minimum_cash_buffer=_decimal_text(
            form.minimum_cash_buffer,
            "최소 운영자금",
        ),
        credit_limit=_decimal_text(
            form.credit_limit,
            "대출한도",
        ),
        acceptable_fx_loss=_decimal_text(
            form.acceptable_fx_loss,
            "손실한도",
        ),
        krw_cashflows=_krw_cashflows(form.krw_cashflow_rows),
        bank_spread_bps=_decimal_text(
            form.bank_spread_bps,
            "은행 spread",
        ),
        bank_fee=_decimal_text(form.bank_fee, "은행 수수료"),
        composite_stress=CompositeStress(
            revenue_reduction_percent=_decimal_text(
                form.revenue_reduction_percent,
                "매출 감소율",
            ),
            revenue_delay_days=form.revenue_delay_days,
            cost_increase_percent=_decimal_text(
                form.cost_increase_percent,
                "비용 증가율",
            ),
        ),
    )
