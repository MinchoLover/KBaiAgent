from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from schemas import StrictModel
from src.domain.stage2_models import (
    CompositeStress,
    ExistingHedge,
    ExposureInput,
    KrwCashflowEvent,
    PreprocessingWarningCode,
    SameCurrencyFlow,
    Stage2Input,
)
from src.stage2.allocation import (
    allocate_capped,
    allocate_capped_by_date,
    allocate_fee_proportionally,
)
from src.stage2.binding import confirmed_trade_from_document_input
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


def recommended_stage2_as_of_date(
    document_input: Dict[str, Any],
    *,
    current_date: Optional[date] = None,
) -> date:
    """Choose a valid default without changing the confirmed trade schedule."""

    confirmed_trade = confirmed_trade_from_document_input(document_input)
    settlement_dates = [
        date.fromisoformat(item.settlement_date)
        for item in confirmed_trade.events
    ]
    today = current_date or date.today()
    if not settlement_dates:
        return today
    return min(today, min(settlement_dates))


def validate_stage2_as_of_date(stage2_input: Stage2Input) -> None:
    """Give the UI an actionable error before the cashflow engine runs."""

    as_of = date.fromisoformat(stage2_input.as_of_date)
    settlement_dates = [
        date.fromisoformat(item.settlement_date)
        for item in stage2_input.exposures
    ]
    if not settlement_dates:
        return
    earliest_settlement = min(settlement_dates)
    if earliest_settlement < as_of:
        raise ValueError(
            "현금 계산 기준일({})은 가장 이른 예정 결제일({})보다 "
            "늦을 수 없습니다. 기준일을 {} 이하로 선택하세요. 이미 "
            "이행된 금액이 있다면 계약서만으로 추정하지 말고 실제 "
            "입금·지급 내역을 먼저 반영해야 합니다.".format(
                as_of.isoformat(),
                earliest_settlement.isoformat(),
                earliest_settlement.isoformat(),
            )
        )


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
    confirmed_trade = confirmed_trade_from_document_input(document_input)
    cash_events = confirmed_trade.events
    event_amounts = [
        item.foreign_amount for item in cash_events
    ]
    total_trade_amount = sum(
        (
            decimal_value(item, "confirmed trade event amount")
            for item in event_amounts
        ),
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
    natural_flow_caps = list(event_amounts)
    if confirmed_trade.trade_type == "IMPORT":
        natural_flow_caps = [
            format(
                decimal_value(amount, "confirmed trade event amount")
                - decimal_value(allocation, "usable FX allocation"),
                "f",
            )
            for amount, allocation in zip(
                event_amounts,
                usable_allocations,
            )
        ]
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
        natural_flow_caps,
        [item.settlement_date for item in cash_events],
        form.same_currency_flow_date,
    )
    preprocessing_warnings: List[PreprocessingWarningCode] = []
    if decimal_value(usable_total, "usable FX balance") > sum(
        (
            decimal_value(item, "usable FX allocation")
            for item in usable_allocations
        ),
        Decimal("0"),
    ):
        preprocessing_warnings.append("EXCESS_USABLE_FX_IGNORED")
    if decimal_value(flow_amount, "same currency flow") > sum(
        (
            decimal_value(item, "same currency flow allocation")
            for item in flow_allocations
        ),
        Decimal("0"),
    ):
        preprocessing_warnings.append(
            "INELIGIBLE_SAME_CURRENCY_FLOW_IGNORED"
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
                    currency=confirmed_trade.currency,
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
                sequence=event.sequence,
                trade_type=event.trade_type,
                currency=event.currency,
                foreign_amount=event.foreign_amount,
                settlement_date=event.settlement_date,
                usable_fx_balance=usable_allocations[index],
                same_currency_flows=flows,
                existing_hedge=hedge,
            )
        )

    return Stage2Input(
        confirmed_trade_sha256=confirmed_trade.trade_sha256,
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
        preprocessing_warnings=preprocessing_warnings,
    )
