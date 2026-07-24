import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

from sample_data import sample_extraction
from src.config import Settings
from src.document_intake.confirmation import (
    create_confirmation_record,
    validate_confirmation,
)
from src.domain.stage2_models import (
    CompositeStress,
    ExposureInput,
    KrwCashflowEvent,
    Stage2Input,
)
from src.stage2.binding import confirmed_trade_from_confirmation
from src.workflow.orchestrator import (
    WorkflowOrchestrator,
    WorkflowRequest,
)
from src.workflow.state import WorkflowState


def _offline_stage2_input(confirmed_trade_sha256: str) -> Stage2Input:
    return Stage2Input(
        confirmed_trade_sha256=confirmed_trade_sha256,
        as_of_date="2026-07-23",
        exposures=[
            ExposureInput(
                sequence=1,
                trade_type="IMPORT",
                currency="USD",
                foreign_amount="100000.00",
                settlement_date="2026-10-18",
                usable_fx_balance="10000.00",
                same_currency_flows=[],
            )
        ],
        current_krw_cash="200000000",
        minimum_cash_buffer="50000000",
        credit_limit="30000000",
        acceptable_fx_loss="10000000",
        krw_cashflows=[
            KrwCashflowEvent(
                date="2026-08-31",
                amount="30000000",
                direction="INFLOW",
                category="REVENUE",
                description="예정 매출 입금",
            ),
            KrwCashflowEvent(
                date="2026-09-30",
                amount="20000000",
                direction="OUTFLOW",
                category="COST",
                description="예정 운영비",
            ),
        ],
        bank_spread_bps="15",
        bank_fee="50000",
        composite_stress=CompositeStress(),
    )


def _require_completed(state: WorkflowState) -> None:
    required = (
        state.market_risk,
        state.cashflow,
        state.hedge,
        state.product_search,
        state.final_report,
    )
    if any(item is None for item in required):
        raise RuntimeError("offline demo workflow did not complete")


def run_offline_demo(
    orchestrator: Optional[WorkflowOrchestrator] = None,
) -> Dict[str, Any]:
    extraction = sample_extraction("BUYER")
    confirmed_due_date = "2026-10-18"
    sample_path = (
        Path(__file__).resolve().parents[2]
        / "samples"
        / "sample_invoice.png"
    )
    record = create_confirmation_record(
        original=extraction,
        confirmed=extraction,
        confirmed_due_date=confirmed_due_date,
        currency_confirmed=True,
        amount_due_confirmed=True,
        due_date_confirmed=True,
        source_filename="sample_invoice.png",
        source_sha256=hashlib.sha256(sample_path.read_bytes()).hexdigest(),
        company_country="KR",
        confirmed_by="offline-demo",
        confirmed_at="2026-07-23T09:00:00+09:00",
    )
    validation = validate_confirmation(
        extraction=extraction,
        record=record,
        company_country="KR",
    )
    if not validation.stage2_allowed:
        raise RuntimeError("offline demo confirmation gate failed")

    confirmed_trade = confirmed_trade_from_confirmation(
        extraction=extraction,
        validation=validation,
        confirmation=record,
    )
    stage2_input = _offline_stage2_input(confirmed_trade.trade_sha256)
    workflow = orchestrator or WorkflowOrchestrator(settings=Settings())
    state = workflow.initialize(
        mode="OFFLINE",
        extraction=extraction,
        validation=validation,
        confirmation=record,
    )
    state = workflow.run(
        state,
        WorkflowRequest(
            stage2_input=stage2_input,
            manual_base_rate="1400",
            stage1_mode="MANUAL_STRESS",
            product_search_mode="OFFLINE_KB",
        ),
    )
    _require_completed(state)
    return {
        "extraction": extraction,
        "confirmation": record,
        "validation": validation,
        "stage1_load": state.market_risk.data,
        "stage1": state.market_risk.data.scenario_set,
        "stage2_input": stage2_input,
        "stage2": state.cashflow.data,
        "stage3": state.hedge.data,
        "stage4": state.product_search.data,
        "report": state.final_report,
        "workflow_state": state,
        "trace": state.trace,
    }
