import unittest
from datetime import date
from decimal import Decimal
from typing import Optional

from src.domain.stage1_models import ScenarioPoint, Stage1ScenarioSet
from src.domain.stage2_models import (
    CompositeStress,
    ExistingHedge,
    ExposureInput,
    KrwCashflowEvent,
    SameCurrencyFlow,
    Stage2Input,
)
from src.stage1.manual_scenarios import build_manual_stress_scenarios
from src.stage1.normalizer import normalize_stage1_scenarios
from src.stage2.allocation import (
    allocate_capped,
    allocate_capped_by_date,
    allocate_fee_proportionally,
)
from src.stage2.cashflow import (
    add_daily_event,
    apply_composite_stress,
    build_ledger,
    new_daily_event_map,
)
from src.stage2.engine import run_stage2
from src.stage2.exposure import compute_exposure
from src.stage2.scenarios import applied_customer_rate


def stress_scenarios(currency: str = "USD"):
    return normalize_stage1_scenarios(
        build_manual_stress_scenarios(
            currency=currency,
            base_rate="1400",
            target_date="2026-10-21",
            as_of="2026-07-23T09:00:00+09:00",
        )
    )


def stage2_input(
    trade_type: str = "IMPORT",
    exposure: Optional[ExposureInput] = None,
    **updates
) -> Stage2Input:
    default_exposure = exposure or ExposureInput(
        sequence=1,
        trade_type=trade_type,
        currency="USD",
        foreign_amount="100",
        settlement_date="2026-10-21",
    )
    data = {
        "as_of_date": "2026-07-23",
        "exposures": [default_exposure],
        "current_krw_cash": "200000",
        "minimum_cash_buffer": "50000",
        "credit_limit": "30000",
        "acceptable_fx_loss": "10000",
        "krw_cashflows": [],
        "bank_spread_bps": "0",
        "bank_fee": "0",
        "composite_stress": CompositeStress(),
    }
    data.update(updates)
    return Stage2Input(**data)


class AllocationTests(unittest.TestCase):
    def test_capped_allocation_preserves_remainder_for_later_events(self):
        self.assertEqual(
            allocate_capped("150", ["100", "100"]),
            ["100", "50"],
        )

    def test_dated_allocation_skips_ineligible_installment(self):
        self.assertEqual(
            allocate_capped_by_date(
                "100",
                ["60", "60"],
                ["2026-08-01", "2026-10-01"],
                "2026-09-01",
            ),
            ["0", "60"],
        )

    def test_hedge_fee_is_allocated_once(self):
        allocations = allocate_fee_proportionally(
            "100",
            ["30000", "70000"],
        )
        self.assertEqual(allocations, ["30.00", "70.00"])
        self.assertEqual(
            sum((Decimal(item) for item in allocations), Decimal("0")),
            Decimal("100"),
        )

    def test_small_hedge_fee_allocation_never_turns_negative(self):
        allocations = allocate_fee_proportionally(
            "0.02",
            ["1", "1", "1", "1"],
        )

        self.assertTrue(
            all(Decimal(item) >= 0 for item in allocations)
        )
        self.assertEqual(
            sum((Decimal(item) for item in allocations), Decimal("0")),
            Decimal("0.02"),
        )


class ExposureTests(unittest.TestCase):
    def test_import_natural_hedge_only_before_settlement(self):
        exposure = ExposureInput(
            sequence=1,
            trade_type="IMPORT",
            currency="USD",
            foreign_amount="100",
            settlement_date="2026-10-21",
            usable_fx_balance="10",
            same_currency_flows=[
                SameCurrencyFlow(
                    date="2026-10-20",
                    amount="20",
                    currency="USD",
                    direction="INFLOW",
                ),
                SameCurrencyFlow(
                    date="2026-10-22",
                    amount="30",
                    currency="USD",
                    direction="INFLOW",
                ),
            ],
        )
        computation, unused = compute_exposure(exposure)
        del unused
        self.assertEqual(computation.natural_offset, "30")
        self.assertEqual(computation.held_fx_used, "10")
        self.assertEqual(computation.same_currency_offset, "20")
        self.assertEqual(computation.open_exposure, "70")

    def test_held_fx_never_exceeds_trade_amount(self):
        exposure = ExposureInput(
            sequence=1,
            trade_type="IMPORT",
            currency="USD",
            foreign_amount="100",
            settlement_date="2026-10-21",
            usable_fx_balance="150",
            same_currency_flows=[
                SameCurrencyFlow(
                    date="2026-10-20",
                    amount="20",
                    currency="USD",
                    direction="INFLOW",
                )
            ],
        )

        computation, unused = compute_exposure(exposure)
        del unused
        self.assertEqual(computation.held_fx_used, "100")
        self.assertEqual(computation.same_currency_offset, "0")
        self.assertEqual(computation.natural_offset, "100")

    def test_export_balance_not_used_as_natural_hedge(self):
        exposure = ExposureInput(
            sequence=1,
            trade_type="EXPORT",
            currency="USD",
            foreign_amount="100",
            settlement_date="2026-10-21",
            usable_fx_balance="20",
        )
        computation, warnings = compute_exposure(exposure)
        self.assertEqual(computation.natural_offset, "0")
        self.assertTrue(warnings)

    def test_existing_hedge_reduces_open_but_remains_full(self):
        exposure = ExposureInput(
            sequence=1,
            trade_type="IMPORT",
            currency="USD",
            foreign_amount="100",
            settlement_date="2026-10-21",
            usable_fx_balance="20",
            existing_hedge=ExistingHedge(
                amount="40",
                locked_rate="1300",
                fee="100",
            ),
        )
        computation, warnings = compute_exposure(exposure)
        self.assertEqual(computation.hedged_amount, "40")
        self.assertEqual(computation.open_exposure, "40")
        self.assertFalse(warnings)

    def test_overhedge_is_not_silently_erased(self):
        exposure = ExposureInput(
            sequence=1,
            trade_type="IMPORT",
            currency="USD",
            foreign_amount="100",
            settlement_date="2026-10-21",
            existing_hedge=ExistingHedge(
                amount="120",
                locked_rate="1400",
            ),
        )
        computation, warnings = compute_exposure(exposure)
        self.assertEqual(computation.hedged_amount, "120")
        self.assertEqual(computation.open_exposure, "0")
        self.assertTrue(warnings)

    def test_wrong_direction_natural_hedge_is_disclosed(self):
        exposure = ExposureInput(
            sequence=1,
            trade_type="IMPORT",
            currency="USD",
            foreign_amount="100",
            settlement_date="2026-10-21",
            same_currency_flows=[
                SameCurrencyFlow(
                    date="2026-10-20",
                    amount="20",
                    currency="USD",
                    direction="OUTFLOW",
                )
            ],
        )
        computation, warnings = compute_exposure(exposure)
        self.assertEqual(computation.natural_offset, "0")
        self.assertTrue(any("자연상계 방향" in item for item in warnings))

    def test_flow_after_settlement_is_disclosed(self):
        exposure = ExposureInput(
            sequence=1,
            trade_type="IMPORT",
            currency="USD",
            foreign_amount="100",
            settlement_date="2026-10-21",
            same_currency_flows=[
                SameCurrencyFlow(
                    date="2026-10-22",
                    amount="20",
                    currency="USD",
                    direction="INFLOW",
                )
            ],
        )

        computation, warnings = compute_exposure(exposure)

        self.assertEqual(computation.natural_offset, "0")
        self.assertTrue(any("결제일 이후" in item for item in warnings))


class Stage2EngineTests(unittest.TestCase):
    def test_import_rate_rise_is_adverse(self):
        result = run_stage2(stage2_input("IMPORT"), stress_scenarios())
        low = result.scenario_results[0]
        high = result.scenario_results[-1]
        self.assertLess(Decimal(low.loss_vs_base), 0)
        self.assertGreater(Decimal(high.loss_vs_base), 0)

    def test_export_rate_fall_is_adverse(self):
        result = run_stage2(stage2_input("EXPORT"), stress_scenarios())
        low = result.scenario_results[0]
        high = result.scenario_results[-1]
        self.assertGreater(Decimal(low.loss_vs_base), 0)
        self.assertLess(Decimal(high.loss_vs_base), 0)

    def test_buy_and_sell_spread_directions(self):
        buy = applied_customer_rate(
            reference_rate=Decimal("1400"),
            trade_type="IMPORT",
            bank_spread_bps=Decimal("100"),
        )
        sell = applied_customer_rate(
            reference_rate=Decimal("1400"),
            trade_type="EXPORT",
            bank_spread_bps=Decimal("100"),
        )
        self.assertEqual(buy, Decimal("1414"))
        self.assertEqual(sell, Decimal("1386"))

    def test_existing_hedge_is_in_cashflow(self):
        exposure = ExposureInput(
            sequence=1,
            trade_type="IMPORT",
            currency="USD",
            foreign_amount="100",
            settlement_date="2026-10-21",
            existing_hedge=ExistingHedge(
                amount="40",
                locked_rate="1300",
                fee="100",
            ),
        )
        result = run_stage2(
            stage2_input(exposure=exposure),
            stress_scenarios(),
        )
        base = next(
            item
            for item in result.scenario_results
            if item.scenario_name == "BASE"
        )
        self.assertEqual(base.fx_krw_outflow, "136100.00")
        self.assertEqual(result.open_exposure, "60")

    def test_buffer_cash_and_credit_shortfalls_are_distinct(self):
        events = new_daily_event_map()
        add_daily_event(
            events,
            event_date=date(2026, 7, 24),
            outflow=Decimal("130"),
            description="stress",
        )
        ledger, metrics = build_ledger(
            event_map=events,
            as_of_date=date(2026, 7, 23),
            initial_cash=Decimal("100"),
            minimum_buffer=Decimal("50"),
            credit_limit=Decimal("20"),
            scenario_name="TEST",
            source_status="CALCULATION",
        )
        self.assertEqual(ledger[0].buffer_shortfall, "80.00")
        self.assertEqual(ledger[0].cash_deficit, "30.00")
        self.assertEqual(ledger[0].post_credit_shortfall, "10.00")
        self.assertEqual(metrics["first_buffer_shortfall_date"], "2026-07-24")

    def test_initial_buffer_shortfall_starts_on_as_of_date(self):
        unused_ledger, metrics = build_ledger(
            event_map=new_daily_event_map(),
            as_of_date=date(2026, 7, 23),
            initial_cash=Decimal("40"),
            minimum_buffer=Decimal("50"),
            credit_limit=Decimal("20"),
            scenario_name="TEST",
            source_status="CALCULATION",
        )
        del unused_ledger
        self.assertEqual(
            metrics["first_buffer_shortfall_date"],
            "2026-07-23",
        )
        self.assertEqual(
            metrics["maximum_buffer_shortfall"],
            Decimal("10"),
        )

    def test_probability_metrics_only_when_probabilities_valid(self):
        raw = Stage1ScenarioSet(
            currency="USD",
            as_of="2026-07-23T09:00:00+09:00",
            target_date="2026-10-21",
            kind="FORECAST",
            scenarios=[
                ScenarioPoint(
                    name="LOW",
                    rate="1300",
                    is_base=False,
                    probability="0.5",
                ),
                ScenarioPoint(
                    name="BASE",
                    rate="1400",
                    is_base=True,
                    probability="0.5",
                ),
            ],
        )
        scenarios = normalize_stage1_scenarios(raw)
        result = run_stage2(stage2_input(), scenarios)
        self.assertIsNotNone(result.expected_adverse_loss)
        no_probability = run_stage2(stage2_input(), stress_scenarios())
        self.assertIsNone(no_probability.expected_adverse_loss)

    def test_composite_revenue_delay_and_reduction_cost_increase(self):
        events = [
            KrwCashflowEvent(
                date="2026-07-24",
                amount="100",
                direction="INFLOW",
                category="REVENUE",
            ),
            KrwCashflowEvent(
                date="2026-07-24",
                amount="100",
                direction="OUTFLOW",
                category="COST",
            ),
        ]
        transformed = apply_composite_stress(
            events,
            CompositeStress(
                revenue_reduction_percent="0.1",
                revenue_delay_days=5,
                cost_increase_percent="0.2",
            ),
        )
        self.assertEqual(transformed[0].date, "2026-07-29")
        self.assertEqual(transformed[0].amount, "90.00")
        self.assertEqual(transformed[1].amount, "120.00")

    def test_full_revenue_reduction_produces_zero_inflow(self):
        result = run_stage2(
            stage2_input(
                krw_cashflows=[
                    KrwCashflowEvent(
                        date="2026-07-24",
                        amount="100",
                        direction="INFLOW",
                        category="REVENUE",
                    )
                ],
                composite_stress=CompositeStress(
                    revenue_reduction_percent="1",
                ),
            ),
            stress_scenarios(),
        )
        base = next(
            item
            for item in result.scenario_results
            if item.scenario_name == "BASE"
        )
        entry = next(
            item for item in base.ledger if item.date == "2026-07-24"
        )
        self.assertEqual(entry.krw_inflow, "0.00")

    def test_same_input_same_output(self):
        inputs = stage2_input()
        scenarios = stress_scenarios()
        first = run_stage2(inputs, scenarios).model_dump_json()
        second = run_stage2(inputs, scenarios).model_dump_json()
        self.assertEqual(first, second)
        result = run_stage2(inputs, scenarios)
        self.assertEqual(result.status, "CALCULATION")
        self.assertTrue(
            all(
                entry.source_status == "CALCULATION"
                for scenario in result.scenario_results
                for entry in scenario.ledger
            )
        )

    def test_currency_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            run_stage2(stage2_input(), stress_scenarios("EUR"))

    def test_non_uppercase_currency_rejected(self):
        exposure = ExposureInput(
            sequence=1,
            trade_type="IMPORT",
            currency="usd",
            foreign_amount="100",
            settlement_date="2026-10-21",
        )
        with self.assertRaises(ValueError):
            run_stage2(
                stage2_input(exposure=exposure),
                stress_scenarios(),
            )

    def test_scenario_target_date_substitution_is_disclosed(self):
        exposure = ExposureInput(
            sequence=1,
            trade_type="IMPORT",
            currency="USD",
            foreign_amount="100",
            settlement_date="2026-10-22",
        )
        result = run_stage2(
            stage2_input(exposure=exposure),
            stress_scenarios(),
        )
        self.assertTrue(
            any("대체 적용" in warning for warning in result.warnings)
        )

    def test_preprocessing_warning_is_preserved_in_result(self):
        warning_code = "INELIGIBLE_SAME_CURRENCY_FLOW_IGNORED"
        warning_message = (
            "결제일과 잔여 노출 조건에 맞지 않는 동일통화 흐름은 "
            "자연상계에 사용하지 않았습니다."
        )
        result = run_stage2(
            stage2_input(preprocessing_warnings=[warning_code]),
            stress_scenarios(),
        )

        self.assertIn(warning_message, result.warnings)
        self.assertNotIn(warning_code, result.warnings)

    def test_past_settlement_rejected(self):
        exposure = ExposureInput(
            sequence=1,
            trade_type="IMPORT",
            currency="USD",
            foreign_amount="100",
            settlement_date="2026-07-22",
        )
        with self.assertRaises(ValueError):
            run_stage2(
                stage2_input(exposure=exposure),
                stress_scenarios(),
            )

    def test_past_same_currency_flow_rejected(self):
        exposure = ExposureInput(
            sequence=1,
            trade_type="IMPORT",
            currency="USD",
            foreign_amount="100",
            settlement_date="2026-10-21",
            same_currency_flows=[
                SameCurrencyFlow(
                    date="2026-07-22",
                    amount="10",
                    currency="USD",
                    direction="INFLOW",
                )
            ],
        )
        with self.assertRaises(ValueError):
            run_stage2(
                stage2_input(exposure=exposure),
                stress_scenarios(),
            )

    def test_negative_current_cash_is_supported(self):
        result = run_stage2(
            stage2_input(current_krw_cash="-100"),
            stress_scenarios(),
        )
        self.assertGreater(
            Decimal(result.scenario_results[0].cash_deficit),
            0,
        )

    def test_non_finite_financial_input_rejected(self):
        with self.assertRaises(ValueError):
            run_stage2(
                stage2_input(current_krw_cash="NaN"),
                stress_scenarios(),
            )

    def test_scientific_notation_financial_input_rejected(self):
        with self.assertRaises(ValueError):
            run_stage2(
                stage2_input(current_krw_cash="2e5"),
                stress_scenarios(),
            )

    def test_exposure_sequence_must_be_contiguous(self):
        first = ExposureInput(
            sequence=1,
            trade_type="IMPORT",
            currency="USD",
            foreign_amount="50",
            settlement_date="2026-10-21",
        )
        second = ExposureInput(
            sequence=1,
            trade_type="IMPORT",
            currency="USD",
            foreign_amount="50",
            settlement_date="2026-10-21",
        )
        with self.assertRaises(ValueError):
            run_stage2(
                stage2_input(exposures=[first, second]),
                stress_scenarios(),
            )

    def test_bank_spread_below_one_hundred_percent(self):
        with self.assertRaises(ValueError):
            run_stage2(
                stage2_input(bank_spread_bps="10000"),
                stress_scenarios(),
            )

    def test_dates_require_extended_iso_format(self):
        with self.assertRaises(ValueError):
            run_stage2(
                stage2_input(as_of_date="20260723"),
                stress_scenarios(),
            )


if __name__ == "__main__":
    unittest.main()
