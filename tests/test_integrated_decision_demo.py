import unittest

from src.demo import run_integrated_decision_demo
from src.workflow.result import StageStatus


class IntegratedDecisionDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.import_demo = run_integrated_decision_demo("BUYER")
        cls.export_demo = run_integrated_decision_demo("SELLER")

    def test_import_fixture_runs_to_verified_report(self):
        demo = self.import_demo
        result = demo["stage2"]
        scenario = next(
            item
            for item in result.scenario_results
            if item.scenario_name == "UP_5"
        )

        self.assertEqual(
            demo["workflow_state"].final_status,
            StageStatus.SUCCEEDED,
        )
        self.assertTrue(demo["report"].critique.passed)
        self.assertEqual(result.open_exposure, "80000.00")
        self.assertEqual(
            result.base_required_or_proceeds_krw,
            "112000000.00",
        )
        self.assertEqual(scenario.scenario_rate, "1470.0000")
        self.assertEqual(scenario.fx_krw_outflow, "117600000.00")
        self.assertEqual(scenario.loss_vs_base, "5600000.00")
        self.assertEqual(scenario.ending_cash, "7400000.00")
        self.assertEqual(
            scenario.maximum_buffer_shortfall,
            "2600000.00",
        )
        self.assertEqual(scenario.post_credit_shortfall, "0.00")

    def test_export_fixture_uses_downside_path(self):
        demo = self.export_demo
        result = demo["stage2"]
        scenario = next(
            item
            for item in result.scenario_results
            if item.scenario_name == "DOWN_5"
        )

        self.assertEqual(
            demo["workflow_state"].final_status,
            StageStatus.SUCCEEDED,
        )
        self.assertEqual(result.trade_type, "EXPORT")
        self.assertEqual(scenario.scenario_rate, "1330.0000")
        self.assertEqual(scenario.fx_krw_inflow, "133000000.00")
        self.assertEqual(scenario.loss_vs_base, "7000000.00")

    def test_stage1_fixture_is_context_only_for_90_day_settlement(self):
        for demo in (self.import_demo, self.export_demo):
            integration = demo["market_integration"]
            self.assertEqual(integration.forecast_load.source, "MOCK")
            self.assertFalse(
                integration.forecast_load.forecast.direction
                .calibrated_probability
            )
            self.assertTrue(integration.scenario_build.horizon_mismatch)
            self.assertTrue(
                all(
                    not item.included_in_calculation
                    for item in integration.scenario_build
                    .model_path_scenarios
                )
            )
            self.assertIn(
                "HORIZON_MISMATCH",
                " ".join(integration.stage1_load.warnings),
            )


if __name__ == "__main__":
    unittest.main()
