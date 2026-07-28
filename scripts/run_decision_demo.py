#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.demo import (
    run_decision_support_demo,
    run_integrated_decision_demo,
)


def _summary(result: Dict[str, Any]) -> Dict[str, Any]:
    stage2 = result["stage2"]
    assessment = result["risk_assessment"]
    trade_risk = result["trade_risk_assessment"]
    packet = result["consultation_packet"].packet
    worst = next(
        item
        for item in stage2.scenario_results
        if item.scenario_name == assessment.worst_scenario_id
    )
    five_percent_name = (
        "UP_5" if stage2.trade_type == "IMPORT" else "DOWN_5"
    )
    five_percent = next(
        (
            item
            for item in stage2.scenario_results
            if item.scenario_name == five_percent_name
        ),
        None,
    )
    summary = {
        "company_role": (
            "BUYER" if stage2.trade_type == "IMPORT" else "SELLER"
        ),
        "trade_type": stage2.trade_type,
        "currency": stage2.currency,
        "gross_exposure_fx": stage2.total_foreign_amount,
        "open_exposure_fx": stage2.open_exposure,
        "base_required_or_proceeds_krw": (
            stage2.base_required_or_proceeds_krw
        ),
        "worst_scenario_id": assessment.worst_scenario_id,
        "worst_scenario_rate": worst.scenario_rate,
        "additional_cost_or_receipt_loss_krw": worst.loss_vs_base,
        "cash_after_settlement_krw": worst.ending_cash,
        "buffer_shortfall_krw": worst.maximum_buffer_shortfall,
        "payment_gap_krw": worst.post_credit_shortfall,
        "risk_status": assessment.status,
        "risk_codes": assessment.risk_codes,
        "trade_settlement_risk": {
            "risk_type": trade_risk.risk_type,
            "review_priority": trade_risk.review_priority,
            "review_needs": trade_risk.review_needs,
            "reasons": [
                item.reason for item in trade_risk.factors
            ],
        },
        "consultation_topics": [
            item.title for item in result["consultation_topics"]
        ],
        "financial_review_categories": [
            item.category for item in result["consultation_topics"]
        ],
        "case_id": packet.case_id,
        "input_hash": packet.input_hash,
        "calculation_version": packet.calculation_version,
    }
    if five_percent is not None:
        summary["five_percent_stress"] = {
            "scenario_id": five_percent.scenario_name,
            "rate": five_percent.scenario_rate,
            "required_or_receipt_krw": (
                five_percent.fx_krw_outflow
                if stage2.trade_type == "IMPORT"
                else five_percent.fx_krw_inflow
            ),
            "loss_vs_base_krw": five_percent.loss_vs_base,
            "ending_cash_krw": five_percent.ending_cash,
            "buffer_shortfall_krw": (
                five_percent.maximum_buffer_shortfall
            ),
            "post_credit_deficit_krw": (
                five_percent.post_credit_shortfall
            ),
        }
    integration = result.get("market_integration")
    if integration is not None and integration.forecast_load is not None:
        forecast = integration.forecast_load.forecast
        summary["stage1"] = {
            "source": integration.forecast_load.source,
            "direction": forecast.direction.label,
            "up_score": forecast.direction.up_score,
            "down_score": forecast.direction.down_score,
            "calibrated_probability": (
                forecast.direction.calibrated_probability
            ),
            "horizon_trading_days": forecast.horizon.trading_days,
            "horizon_mismatch": (
                integration.scenario_build.horizon_mismatch
            ),
            "spot_rate": integration.spot_quote.rate,
            "spot_source": integration.spot_quote.source,
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="외부 API 없이 수출입 금융 의사결정 데모를 실행합니다."
    )
    parser.add_argument(
        "--company-role",
        choices=["BUYER", "SELLER"],
        default="BUYER",
    )
    parser.add_argument(
        "--format",
        choices=["summary", "json", "markdown"],
        default="summary",
    )
    parser.add_argument(
        "--stage1-mode",
        choices=["fixture", "legacy"],
        default="fixture",
        help="fixture는 팀 Stage 1 JSON+fixture spot을 사용합니다.",
    )
    args = parser.parse_args()
    result = (
        run_integrated_decision_demo(args.company_role)
        if args.stage1_mode == "fixture"
        else run_decision_support_demo(args.company_role)
    )
    if args.format == "markdown":
        print(result["consultation_packet"].markdown)
        return 0
    payload = (
        result["consultation_packet"].packet.model_dump()
        if args.format == "json"
        else _summary(result)
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
