from typing import Any, Dict, List

from src.domain.stage2_models import Stage2Result


def scenario_table_rows(result: Stage2Result) -> List[Dict[str, Any]]:
    return [
        {
            "scenario": item.scenario_name,
            "status": item.scenario_kind,
            "rate": item.scenario_rate,
            "applied_rate": item.applied_rate,
            "required_or_proceeds_krw": (
                item.fx_krw_outflow
                if result.trade_type == "IMPORT"
                else item.fx_krw_inflow
            ),
            "loss_vs_base": item.loss_vs_base,
            "ending_cash": item.ending_cash,
            "buffer_shortfall": item.maximum_buffer_shortfall,
            "cash_deficit": item.cash_deficit,
            "post_credit_shortfall": item.post_credit_shortfall,
        }
        for item in result.scenario_results
    ]
