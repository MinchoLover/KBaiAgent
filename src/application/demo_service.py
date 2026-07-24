import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

from sample_data import sample_extraction
from src.application.consultation_service import build_decision_support
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
from src.domain.stage1_models import ScenarioPoint, Stage1ScenarioSet
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


def _decision_stage2_input(
    *,
    company_role: str,
    confirmed_trade_sha256: str,
) -> Stage2Input:
    trade_type = "IMPORT" if company_role == "BUYER" else "EXPORT"
    is_import = trade_type == "IMPORT"
    return Stage2Input(
        confirmed_trade_sha256=confirmed_trade_sha256,
        as_of_date="2026-07-23",
        exposures=[
            ExposureInput(
                sequence=1,
                trade_type=trade_type,
                currency="USD",
                foreign_amount="100000.00",
                settlement_date="2026-10-18",
                usable_fx_balance=(
                    "20000.00" if is_import else "0"
                ),
                same_currency_flows=[],
            )
        ],
        current_krw_cash=(
            "130000000" if is_import else "20000000"
        ),
        minimum_cash_buffer="10000000",
        credit_limit="0",
        acceptable_fx_loss="5000000",
        krw_cashflows=[
            KrwCashflowEvent(
                date=(
                    "2026-10-01" if is_import else "2026-10-18"
                ),
                amount=(
                    "3000000" if is_import else "145000000"
                ),
                direction="OUTFLOW",
                category="COST",
                description=(
                    "결제 전 확정 운영비"
                    if is_import
                    else "수출대금으로 충당할 확정 운영비"
                ),
            )
        ],
        bank_spread_bps="0",
        bank_fee="0",
        composite_stress=CompositeStress(),
    )


def _decision_scenarios(company_role: str) -> Stage1ScenarioSet:
    stress_name = (
        "STRESS_+5PCT"
        if company_role == "BUYER"
        else "STRESS_-5PCT"
    )
    stress_rate = "1470" if company_role == "BUYER" else "1330"
    return Stage1ScenarioSet(
        currency="USD",
        rate_unit_foreign_currency="1",
        as_of="2026-07-23T09:00:00+09:00",
        target_date="2026-10-18",
        kind="STRESS",
        scenarios=[
            ScenarioPoint(
                name="BASE",
                rate="1400",
                is_base=True,
            ),
            ScenarioPoint(
                name=stress_name,
                rate=stress_rate,
                is_base=False,
            ),
        ],
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
        trade_type_confirmed=True,
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
    decision_support = build_decision_support(
        case_id=state.case_id,
        extraction=extraction,
        confirmation=record,
        stage1=state.market_risk.data.scenario_set,
        stage2_input=stage2_input,
        stage2_result=state.cashflow.data,
        generated_at="2026-07-23T09:00:00+09:00",
    )
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
        "risk_assessment": decision_support.risk_assessment,
        "consultation_topics": decision_support.consultation_topics,
        "consultation_packet": decision_support.consultation_packet,
        "workflow_state": state,
        "trace": state.trace,
    }


def run_decision_support_demo(
    company_role: str = "BUYER",
    orchestrator: Optional[WorkflowOrchestrator] = None,
) -> Dict[str, Any]:
    if company_role not in {"BUYER", "SELLER"}:
        raise ValueError("회사 역할은 BUYER 또는 SELLER여야 합니다.")
    extraction = sample_extraction(company_role)
    source_path = (
        Path(__file__).resolve().parents[2]
        / "samples"
        / (
            "sample_invoice.png"
            if company_role == "BUYER"
            else "demo_export_invoice.pdf"
        )
    )
    record = create_confirmation_record(
        original=extraction,
        confirmed=extraction,
        confirmed_due_date="2026-10-18",
        currency_confirmed=True,
        amount_due_confirmed=True,
        due_date_confirmed=True,
        source_filename=source_path.name,
        source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        company_country="KR",
        trade_type_confirmed=True,
        confirmed_by="offline-decision-demo",
        confirmed_at="2026-07-23T09:00:00+09:00",
    )
    validation = validate_confirmation(
        extraction=extraction,
        record=record,
        company_country="KR",
    )
    if not validation.stage2_allowed:
        raise RuntimeError("offline decision demo confirmation gate failed")
    confirmed_trade = confirmed_trade_from_confirmation(
        extraction=extraction,
        validation=validation,
        confirmation=record,
    )
    stage2_input = _decision_stage2_input(
        company_role=company_role,
        confirmed_trade_sha256=confirmed_trade.trade_sha256,
    )
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
            stage1_mode="EXTERNAL_STAGE1",
            stage1_payload=_decision_scenarios(
                company_role
            ).model_dump(),
            product_search_mode="OFFLINE_KB",
        ),
    )
    _require_completed(state)
    decision_support = build_decision_support(
        case_id=state.case_id,
        extraction=extraction,
        confirmation=record,
        stage1=state.market_risk.data.scenario_set,
        stage2_input=stage2_input,
        stage2_result=state.cashflow.data,
        generated_at="2026-07-23T09:00:00+09:00",
    )
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
        "risk_assessment": decision_support.risk_assessment,
        "consultation_topics": decision_support.consultation_topics,
        "consultation_packet": decision_support.consultation_packet,
        "workflow_state": state,
        "trace": state.trace,
    }
