#!/usr/bin/env python3
"""Verify the Golden import payable and isolated hedge reference API-free."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.application.kb_macro_hedge_service import (
    run_kb_macro_hedge_for_confirmed_trade,
)
from src.config import Settings
from src.domain.kb_macro_hedge_models import (
    KbMacroHedgeExecutionConstraints,
)
from tests.golden_import_hedge_fixture import (
    build_golden_import_hedge_fixture,
)


def _local_cli_reference(
    artifacts: Dict[str, Any],
) -> Any:
    constraints = KbMacroHedgeExecutionConstraints.model_validate(
        artifacts["demo_inputs"]["kb_macro_user_constraints"]
    )
    result = run_kb_macro_hedge_for_confirmed_trade(
        settings=Settings.from_env(),
        stage2_input=artifacts["stage2_input"],
        stage2_result=artifacts["stage2"],
        constraints=constraints,
        constraints_confirmed=True,
    )
    if result is None:
        raise ValueError("local_cli 외부 헤지 결과가 없습니다.")
    return result


def golden_import_hedge_summary(
    *,
    run_local_cli: bool = False,
) -> Dict[str, Any]:
    artifacts = build_golden_import_hedge_fixture()
    extraction = artifacts["extraction"]
    validation = artifacts["validation"]
    document_input = artifacts["document_input"]
    stage1 = artifacts["stage1"]
    stage2_input = artifacts["stage2_input"]
    stage2 = artifacts["stage2"]
    stage3 = artifacts["stage3"]
    reference = (
        _local_cli_reference(artifacts)
        if run_local_cli
        else artifacts["kb_macro_reference"]
    )
    request = reference.request
    if request is None:
        raise ValueError("검증된 외부 헤지 request가 없습니다.")

    expected_dates = {
        extraction.explicit_due_date,
        document_input["trade"]["settlement_date"],
        stage1.target_date,
        stage2_input.exposures[0].settlement_date,
        stage2.exposure_computations[0].settlement_date,
        request.payment_date,
    }
    if expected_dates != {"2026-08-27"}:
        raise ValueError("확정 지급일이 downstream 단계에서 달라졌습니다.")
    if (
        not validation.validation_pass
        or not validation.stage2_allowed
        or stage2.trade_type != "IMPORT"
        or stage2.currency != "USD"
        or stage2.total_foreign_amount != "100000.00"
        or stage2.held_fx_used != "10000.00"
        or stage2.open_exposure != "90000.00"
        or stage3.status != "CANDIDATES_NOT_ADVICE"
        or len(stage3.candidates) != 3
        or reference.status != "REFERENCE_ONLY"
        or reference.pricing_status != "MOCK"
        or not reference.validation.passed
        or len(reference.candidates) != 3
        or reference.published_to_stage4
    ):
        raise ValueError("Golden 수입 헤지 E2E invariant가 깨졌습니다.")

    up_five = next(
        item
        for item in stage2.scenario_results
        if item.scenario_name == "UP_5"
    )
    up_ten = next(
        item
        for item in stage2.scenario_results
        if item.scenario_name == "UP_10"
    )
    return {
        "api_free": True,
        "external_network_used": False,
        "live_document_extraction": False,
        "document": {
            "filename": artifacts["upload"].filename,
            "sha256": artifacts["upload"].sha256,
            "page_count": artifacts["upload"].page_count,
            "text_layer_pages": len(artifacts["page_texts"]),
            "synthetic": True,
            "not_legally_binding": True,
        },
        "steps": {
            "upload_guard": "SUCCEEDED",
            "text_layer_and_exact_evidence": "SUCCEEDED",
            "country_normalization": "SUCCEEDED",
            "human_confirmation": "SUCCEEDED",
            "stage1_fixture": "SUCCEEDED",
            "stage2": "SUCCEEDED",
            "internal_stage3": "SUCCEEDED",
            "kb_macro_reference": "SUCCEEDED",
        },
        "confirmed_trade": {
            "company_role": extraction.company_role,
            "trade_type": extraction.trade_type,
            "seller_country": extraction.seller_country,
            "buyer_country": extraction.buyer_country,
            "currency": extraction.currency,
            "amount_due": extraction.amount_due,
            "payment_date": extraction.explicit_due_date,
            "installment_count": len(extraction.installments),
            "settlement_date_source": document_input["trade"][
                "settlement_date_source"
            ],
        },
        "stage2": {
            "gross_exposure_usd": stage2.total_foreign_amount,
            "held_usd_used": stage2.held_fx_used,
            "existing_forward_usd": "0",
            "open_exposure_usd": stage2.open_exposure,
            "base_krw_outflow": stage2.base_required_or_proceeds_krw,
            "up_5_loss_krw": up_five.loss_vs_base,
            "up_5_ending_cash_krw": up_five.ending_cash,
            "up_5_buffer_shortfall_krw": (
                up_five.maximum_buffer_shortfall
            ),
            "up_10_loss_krw": up_ten.loss_vs_base,
        },
        "internal_stage3": {
            "status": stage3.status,
            "candidate_count": len(stage3.candidates),
            "ranks": [item.rank for item in stage3.candidates],
            "source": "KBaiAgent deterministic comparison",
        },
        "kb_macro_ai_reference": {
            "provider_mode": reference.provider_mode,
            "status": reference.status,
            "pricing_status": reference.pricing_status,
            "validation_pass": reference.validation.passed,
            "candidate_count": len(reference.candidates),
            "ranks": [item.rank for item in reference.candidates],
            "gross_exposure_usd": request.amount_usd,
            "held_usd": request.existing_usd_cash,
            "existing_forward_usd": request.existing_forward_usd,
            "net_exposure_usd": request.net_exposure_usd,
            "payment_date": request.payment_date,
            "producer_commit_sha": (
                reference.provenance.producer_commit_sha
                if reference.provenance is not None
                else "UNKNOWN"
            ),
            "published_to_stage4": reference.published_to_stage4,
            "fallback_to_internal_stage3": (
                reference.fallback_to_internal_stage3
            ),
            "temporary_raw_output_deleted": (
                "TEMPORARY_RAW_OUTPUT_DELETED" in reference.warnings
                if run_local_cli
                else None
            ),
        },
        "claim_boundary": {
            "expected_extraction_test_double_used": True,
            "external_hedge_local_cli_executed": run_local_cli,
            "model_accuracy_claim_allowed": False,
            "actual_bank_price": False,
            "product_advice_or_execution": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the text-layer Golden USD import payable through "
            "Stage 2, internal Stage 3, and the isolated kb_macro_ai "
            "reference adapter."
        )
    )
    parser.add_argument(
        "--run-local-cli",
        action="store_true",
        help=(
            "Use the operator-pinned local kb_macro_ai CLI instead of "
            "the checked-in adapter fixture. Still makes no network call."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(
        json.dumps(
            golden_import_hedge_summary(
                run_local_cli=args.run_local_cli,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
