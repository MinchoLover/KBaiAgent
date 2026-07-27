import copy
import unittest
from decimal import Decimal

from src.application.stage2_input_service import (
    Stage2FormInput,
    build_stage2_input_from_form,
)


class Stage2InputServiceTests(unittest.TestCase):
    def setUp(self):
        self.document_input = {
            "source": {
                "sha256": "a" * 64,
                "user_confirmed": True,
                "confirmed_fields": [
                    "company_role",
                    "trade_type",
                    "currency",
                    "amount_due",
                    "due_date",
                ],
            },
            "trade": {
                "trade_type": "IMPORT",
                "currency": "USD",
                "foreign_amount": "100000.00",
                "cashflow_events": [
                    {
                        "sequence": 1,
                        "foreign_amount": "60000.00",
                        "currency": "USD",
                        "settlement_date": "2026-10-18",
                    },
                    {
                        "sequence": 2,
                        "foreign_amount": "40000.00",
                        "currency": "USD",
                        "settlement_date": "2026-11-18",
                    },
                ],
            }
        }

    def _form(self, **updates):
        values = {
            "as_of_date": "2026-07-23",
            "current_krw_cash": "200,000,000",
            "minimum_cash_buffer": "50000000",
            "credit_limit": "30000000",
            "usable_fx_balance": "70000",
            "acceptable_fx_loss": "10000000",
            "same_currency_flow_amount": "10000",
            "same_currency_flow_date": "2026-09-01",
            "same_currency_flow_direction": "INFLOW",
            "existing_hedge_amount": "20000",
            "existing_hedge_rate": "1400",
            "existing_hedge_fee": "100000",
            "bank_spread_bps": "15",
            "bank_fee": "50000",
            "krw_cashflow_rows": [
                {
                    "date": "2026-08-31",
                    "amount": "30000000",
                    "direction": "INFLOW",
                    "category": "REVENUE",
                    "description": "예정 매출",
                }
            ],
            "revenue_reduction_percent": "0",
            "revenue_delay_days": 0,
            "cost_increase_percent": "0",
        }
        values.update(updates)
        return Stage2FormInput(**values)

    def test_builds_capped_allocations_outside_streamlit(self):
        result = build_stage2_input_from_form(
            document_input=self.document_input,
            form=self._form(),
        )

        self.assertEqual(result.current_krw_cash, "200000000")
        self.assertIsNotNone(result.confirmed_trade_sha256)
        self.assertEqual(
            [item.usable_fx_balance for item in result.exposures],
            ["60000.00", "10000.00"],
        )
        self.assertEqual(
            [
                sum(
                    (
                        Decimal(flow.amount)
                        for flow in item.same_currency_flows
                    ),
                    Decimal("0"),
                )
                for item in result.exposures
            ],
            [Decimal("0"), Decimal("10000")],
        )
        self.assertEqual(
            [
                item.existing_hedge.amount
                if item.existing_hedge is not None
                else None
                for item in result.exposures
            ],
            ["20000", None],
        )
        self.assertEqual(
            [
                item.existing_hedge.fee
                if item.existing_hedge is not None
                else None
                for item in result.exposures
            ],
            ["100000", None],
        )
        self.assertEqual(len(result.krw_cashflows), 1)
        self.assertEqual(result.preprocessing_warnings, [])

    def test_rejects_hedge_larger_than_trade(self):
        with self.assertRaises(ValueError):
            build_stage2_input_from_form(
                document_input=self.document_input,
                form=self._form(existing_hedge_amount="100001"),
            )

    def test_rejects_document_input_without_confirmation_binding(self):
        document_input = copy.deepcopy(self.document_input)
        document_input["source"]["user_confirmed"] = False

        with self.assertRaises(ValueError):
            build_stage2_input_from_form(
                document_input=document_input,
                form=self._form(),
            )

    def test_rejects_document_total_different_from_event_sum(self):
        document_input = copy.deepcopy(self.document_input)
        document_input["trade"]["foreign_amount"] = "99999.00"

        with self.assertRaises(ValueError):
            build_stage2_input_from_form(
                document_input=document_input,
                form=self._form(),
            )

    def test_discloses_same_currency_flow_that_cannot_be_allocated(self):
        result = build_stage2_input_from_form(
            document_input=self.document_input,
            form=self._form(
                usable_fx_balance="100000",
                same_currency_flow_date="2026-12-01",
            ),
        )

        self.assertTrue(result.preprocessing_warnings)
        self.assertTrue(
            "INELIGIBLE_SAME_CURRENCY_FLOW_IGNORED"
            in result.preprocessing_warnings
        )


if __name__ == "__main__":
    unittest.main()
