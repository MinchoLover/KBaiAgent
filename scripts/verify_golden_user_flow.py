#!/usr/bin/env python3
"""Run the Golden confirmed-transaction flow without network or model calls."""

import json
import sys
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.application.consultation_service import build_decision_support
from src.application.official_candidate_service import (
    shortlist_official_candidates,
)
from src.config import Settings
from src.domain.stage1_models import Stage1LoadResult
from src.stage5.deterministic_fallback import generate_deterministic_report
from src.workflow.orchestrator import WorkflowOrchestrator
from tests.golden_consultation_fixture import (
    build_golden_consultation_fixture,
)


def _deterministic_report_only(**kwargs: Any) -> Any:
    kwargs.pop("settings", None)
    kwargs.pop("max_revisions", None)
    return generate_deterministic_report(**kwargs)


def build_golden_user_flow_artifacts() -> Dict[str, Any]:
    golden = build_golden_consultation_fixture()
    stage1_load = Stage1LoadResult(
        source="EXTERNAL",
        scenario_set=golden["stage1"],
    )

    def stage1_loader(**kwargs: Any) -> Stage1LoadResult:
        del kwargs
        return stage1_load

    orchestrator = WorkflowOrchestrator(
        settings=Settings(
            openai_api_key=None,
            enable_live_document_extraction=False,
            enable_official_web_search=False,
            enable_llm_report=False,
        ),
        stage1_loader=stage1_loader,
        report_generator=_deterministic_report_only,
    )
    state = orchestrator.initialize(
        mode="OFFLINE",
        extraction=golden["extraction"],
        validation=golden["validation"],
        confirmation=golden["confirmation"],
        case_id="golden_export_br_e2e",
        intake_provider="golden_text_layer_fixture",
    )
    state = orchestrator.run_market_risk(
        state,
        expected_currency="USD",
        expected_target_date="2026-08-20",
        manual_base_rate="1400",
        mode="EXTERNAL_STAGE1",
    )
    state = orchestrator.run_cashflow(
        state,
        golden["stage2_input"],
    )
    state = orchestrator.run_hedge(state)
    state = orchestrator.run_product_search(
        state,
        mode="OFFLINE_KB",
    )
    if (
        state.market_risk is None
        or state.market_risk.data is None
        or state.cashflow is None
        or state.cashflow.data is None
        or state.hedge is None
        or state.hedge.data is None
        or state.product_search is None
        or state.product_search.data is None
    ):
        raise ValueError("Golden Stage 1~4 오프라인 실행이 완료되지 않았습니다.")

    first_decision = golden["decision"]
    shortlist = shortlist_official_candidates(
        stage4_result=state.product_search.data,
        trade_type=state.cashflow.data.trade_type,
        consultation_topics=first_decision.consultation_topics,
    )
    decision = build_decision_support(
        case_id=state.case_id,
        extraction=golden["extraction"],
        confirmation=golden["confirmation"],
        stage1=state.market_risk.data.scenario_set,
        stage2_input=golden["stage2_input"],
        stage2_result=state.cashflow.data,
        trade_settlement_risk=golden["trade_risk"],
        country_environment=golden["country_environment"],
        official_candidate_shortlist=shortlist,
        generated_at="2026-07-29T09:00:00+09:00",
        confirmed_transaction=state.confirmed_transaction,
    )
    state = orchestrator.run_report(
        state,
        consultation_packet=decision.consultation_packet.packet,
    )
    if state.report is None or state.report.data is None:
        raise ValueError("Golden Stage 5 보고서 생성이 완료되지 않았습니다.")

    return {
        "golden": golden,
        "document_input": golden["document_input"],
        "workflow": state,
        "decision": decision,
        "shortlist": shortlist,
        "report": state.report.data,
    }


def golden_user_flow_summary() -> Dict[str, Any]:
    artifacts = build_golden_user_flow_artifacts()
    golden = artifacts["golden"]
    state = artifacts["workflow"]
    decision = artifacts["decision"]
    packet = decision.consultation_packet.packet
    report = artifacts["report"]
    stage2 = state.cashflow.data
    down_five = next(
        item
        for item in stage2.scenario_results
        if item.scenario_name == "DOWN_5"
    )
    report_due_date = report.report_json["stage0"]["confirmation"][
        "confirmed_values"
    ]["settlement_date"]

    return {
        "api_free": True,
        "external_network_used": False,
        "steps": {
            "document_text_and_evidence": (
                "SUCCEEDED"
                if golden["validation"].validation_pass
                else "FAILED"
            ),
            "human_confirmation": (
                "SUCCEEDED"
                if golden["validation"].stage2_allowed
                else "FAILED"
            ),
            "stage1": state.market_risk.status.value,
            "stage2": state.cashflow.status.value,
            "stage3": state.hedge.status.value,
            "stage4": state.product_search.status.value,
            "consultation_packet": "SUCCEEDED",
            "stage5": state.report.status.value,
        },
        "dates": {
            "contract_date": golden["extraction"].contract_date,
            "shipment_date": golden["extraction"].shipment_date,
            "confirmed_ui_due_date": (
                golden["confirmation"].checks.confirmed_due_date
            ),
            "document_input_due_date": artifacts["document_input"]["trade"][
                "settlement_date"
            ],
            "stage1_target_date": (
                state.market_risk.data.scenario_set.target_date
            ),
            "stage2_date": (
                stage2.exposure_computations[0].settlement_date
            ),
            "consultation_packet_date": (
                packet.company_summary.settlement_date
            ),
            "stage5_date": report_due_date,
        },
        "date_source_paths": {
            "document_input": artifacts["document_input"]["trade"][
                "settlement_date_source"
            ],
            "stage2": stage2.source_paths["settlement_date"],
            "stage5": "workflow.confirmed_transaction.due_date",
        },
        "amounts": {
            "scheduled_exposure_usd": stage2.total_foreign_amount,
            "advance_installment_usd": (
                golden["extraction"].installments[0].amount
            ),
            "balance_installment_usd": (
                golden["extraction"].installments[1].amount
            ),
            "advance_receipt_status": (
                packet.protection_summary.advance_payment_receipt
            ),
        },
        "down_5_financials_krw": {
            "receipt_loss": down_five.loss_vs_base,
            "ending_cash": down_five.ending_cash,
            "minimum_cash_buffer": (
                golden["stage2_input"].minimum_cash_buffer
            ),
            "buffer_shortfall": down_five.maximum_buffer_shortfall,
            "cash_deficit": down_five.cash_deficit,
            "post_credit_shortfall": down_five.post_credit_shortfall,
        },
        "consultation_top_3": [
            {
                "rank": item.rank,
                "title": item.title,
            }
            for item in packet.consultation_priorities
        ],
        "official_candidate_unique_count": len(
            {
                item.product_id
                for item in artifacts["shortlist"].candidates
            }
        ),
        "stage3_candidate_status": state.hedge.data.status,
    }


def main() -> int:
    print(
        json.dumps(
            golden_user_flow_summary(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
