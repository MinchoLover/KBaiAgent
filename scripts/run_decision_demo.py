#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.demo import run_decision_support_demo


def _summary(result: Dict[str, Any]) -> Dict[str, Any]:
    stage2 = result["stage2"]
    assessment = result["risk_assessment"]
    packet = result["consultation_packet"].packet
    worst = next(
        item
        for item in stage2.scenario_results
        if item.scenario_name == assessment.worst_scenario_id
    )
    return {
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
        "consultation_topics": [
            item.title for item in result["consultation_topics"]
        ],
        "case_id": packet.case_id,
        "input_hash": packet.input_hash,
        "calculation_version": packet.calculation_version,
    }


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
    args = parser.parse_args()
    result = run_decision_support_demo(args.company_role)
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
