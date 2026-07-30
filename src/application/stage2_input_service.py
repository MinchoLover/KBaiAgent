import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from schemas import StrictModel
from src.domain.stage2_models import (
    CashflowErrorDetail,
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


class CashflowValidationError(ValueError):
    def __init__(self, detail: CashflowErrorDetail) -> None:
        self.detail = detail
        super().__init__(detail.user_message)


def stage2_input_fingerprint(
    stage2_input: Optional[Stage2Input],
) -> Optional[str]:
    if stage2_input is None:
        return None
    serialized = json.dumps(
        stage2_input.model_dump(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def cashflow_error_detail(
    *,
    code: str,
    user_message: str,
    stage2_input: Optional[Stage2Input] = None,
    due_date: Optional[str] = None,
    cashflow_base_date: Optional[str] = None,
    field_path: Optional[str] = None,
    exception_type: Optional[str] = None,
) -> CashflowErrorDetail:
    return CashflowErrorDetail(
        code=code,
        user_message=user_message,
        input_fingerprint=stage2_input_fingerprint(stage2_input),
        due_date=due_date,
        cashflow_base_date=cashflow_base_date,
        field_path=field_path,
        exception_type=exception_type,
    )


def classify_cashflow_error(
    exc: Exception,
    *,
    stage2_input: Optional[Stage2Input] = None,
) -> CashflowErrorDetail:
    if isinstance(exc, CashflowValidationError):
        return exc.detail

    message = str(exc)
    lowered = message.lower()
    due_date = None
    cashflow_base_date = None
    field_path = None
    if stage2_input is not None:
        cashflow_base_date = stage2_input.as_of_date
        if stage2_input.exposures:
            due_date = stage2_input.exposures[0].settlement_date

    if (
        (
            "settlement_date" in lowered
            and "as_of_date" in lowered
        )
        or (
            "as_of_date" in lowered
            and ("이전" in message or "빠를" in message)
        )
        or ("기준일" in message and "결제일" in message)
    ):
        code = "INVALID_DATE_ORDER"
        if "krw cashflow" in lowered:
            field_path = "stage2.krw_cashflows[].date"
            user_message = (
                "예정 원화 현금흐름 중 현금 계산 기준일보다 이전인 "
                "항목이 있습니다. 기준일 이전 이력은 현재 현금과 "
                "중복되지 않도록 다시 확인하세요."
            )
        else:
            field_path = "stage2.exposures[].settlement_date"
            user_message = (
                "확정 결제일({})이 현금 계산 기준일({})보다 이전입니다. "
                "거래 확인 단계의 결제일과 계산 기준일을 다시 확인하세요."
            ).format(due_date or "UNKNOWN", cashflow_base_date or "UNKNOWN")
    elif any(
        token in lowered
        for token in (
            "confirmed_due_date",
            "settlement_date가 필요",
            "date가 필요",
            "결제일이 없습니다",
            "결제일 확인",
        )
    ):
        code = "MISSING_REQUIRED_DATE"
        field_path = "stage0.confirmation.confirmed_values.settlement_date"
        user_message = (
            "확정 결제일이 없습니다. 거래 확인 단계에서 결제일을 "
            "확인한 뒤 다시 계산하세요."
        )
    elif any(
        token in lowered
        for token in (
            "fingerprint",
            "확인 기록",
            "확정 거래",
            "결속",
            "snapshot",
        )
    ):
        code = "STALE_CONFIRMED_STATE"
        field_path = "stage0.confirmation"
        user_message = (
            "확정 거래와 현재 금융 입력이 서로 다릅니다. 거래 확인을 "
            "다시 실행해 최신 확정값으로 분석하세요."
        )
    elif any(
        token in lowered
        for token in (
            "amount",
            "금액",
            "decimal",
        )
    ):
        code = "INVALID_AMOUNT"
        field_path = "stage2.exposures[].foreign_amount"
        user_message = (
            "분석 금액이 유효하지 않거나 확정 거래금액과 다릅니다. "
            "거래금액과 분할결제 합계를 다시 확인하세요."
        )
    elif any(
        token in lowered
        for token in (
            "trade_type",
            "direction",
            "거래 방향",
            "수입 또는 수출",
        )
    ):
        code = "UNSUPPORTED_DIRECTION"
        field_path = "stage2.exposures[].trade_type"
        user_message = (
            "확정 거래 방향을 금융 계산에 적용할 수 없습니다. "
            "수입·수출 방향을 다시 확인하세요."
        )
    else:
        code = "INTERNAL_CALCULATION_ERROR"
        user_message = (
            "현금흐름 계산 중 내부 오류가 발생했습니다. 입력을 "
            "보존했으므로 기술정보의 오류 코드를 확인하세요."
        )

    return cashflow_error_detail(
        code=code,
        user_message=user_message,
        stage2_input=stage2_input,
        due_date=due_date,
        cashflow_base_date=cashflow_base_date,
        field_path=field_path,
        exception_type=type(exc).__name__,
    )


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

    try:
        as_of = date.fromisoformat(stage2_input.as_of_date)
        settlement_dates = [
            date.fromisoformat(item.settlement_date)
            for item in stage2_input.exposures
        ]
    except (TypeError, ValueError) as exc:
        detail = cashflow_error_detail(
            code="MISSING_REQUIRED_DATE",
            user_message=(
                "현금 계산 기준일과 확정 결제일은 YYYY-MM-DD "
                "형식으로 모두 필요합니다."
            ),
            stage2_input=stage2_input,
            field_path="stage2.as_of_date|stage2.exposures[].settlement_date",
            exception_type=type(exc).__name__,
        )
        raise CashflowValidationError(detail) from exc
    if not settlement_dates:
        detail = cashflow_error_detail(
            code="MISSING_REQUIRED_DATE",
            user_message="확정 결제일이 있는 금융 노출이 필요합니다.",
            stage2_input=stage2_input,
            field_path="stage2.exposures[].settlement_date",
        )
        raise CashflowValidationError(detail)
    earliest_settlement = min(settlement_dates)
    if earliest_settlement < as_of:
        detail = cashflow_error_detail(
            code="INVALID_DATE_ORDER",
            user_message=(
                "확정 결제일({})이 현금 계산 기준일({})보다 이전입니다. "
                "거래 확인 단계의 결제일과 계산 기준일을 다시 확인하세요. "
                "이미 이행된 금액이 있다면 계약서만으로 추정하지 말고 "
                "실제 입금·지급 내역을 먼저 반영해야 합니다."
            ).format(
                earliest_settlement.isoformat(),
                as_of.isoformat(),
            ),
            stage2_input=stage2_input,
            due_date=earliest_settlement.isoformat(),
            cashflow_base_date=as_of.isoformat(),
            field_path="stage2.exposures[].settlement_date",
        )
        raise CashflowValidationError(detail)


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
