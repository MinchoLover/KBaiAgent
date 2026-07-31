import unittest

from src.ui.presentation import (
    country_summary,
    no_feasible_reason_copy,
    priority_key_rationale,
    transaction_summary,
    world_bank_display,
)
from tests.golden_consultation_fixture import (
    build_golden_consultation_fixture,
)


class GoldenPresentationTests(unittest.TestCase):
    def setUp(self):
        self.golden = build_golden_consultation_fixture()
        self.consultation = (
            self.golden["decision"].consultation_packet
        )

    def test_transaction_summary_uses_confirmed_snapshot_and_packet(self):
        summary = transaction_summary(
            self.golden["extraction"],
            self.golden["confirmed_transaction"],
            self.consultation,
        )

        self.assertEqual(summary["trade_type_label"], "수출")
        self.assertEqual(summary["company_role_label"], "판매자")
        self.assertEqual(
            summary["route_label"],
            "한국 판매자 → 브라질 구매자",
        )
        self.assertEqual(summary["currency"], "USD")
        self.assertEqual(summary["amount_due"], "100000.00")
        self.assertEqual(summary["due_date"], "2026-08-20")
        self.assertEqual(
            summary["payment_method"],
            "Open Account / T/T",
        )
        self.assertEqual(
            summary["major_installment"]["amount"],
            "80000.00",
        )
        self.assertEqual(
            summary["missing_information"],
            "선지급 USD 20,000 실제 입금 여부 확인 필요",
        )
        self.assertEqual(
            summary["source_path"],
            "workflow.confirmed_transaction.due_date",
        )

    def test_world_bank_values_are_rounded_only_for_display(self):
        observations = (
            self.golden["country_environment"]
            .world_bank_macro_environment.observations
        )
        displayed = {
            item.indicator_code: world_bank_display(
                item.indicator_code,
                item.raw_value,
                item.raw_status,
            )
            for item in observations
        }

        self.assertEqual(
            displayed["NY.GDP.MKTP.KD.ZG"],
            "GDP 성장률 2.3%",
        )
        self.assertEqual(
            displayed["FP.CPI.TOTL.ZG"],
            "소비자물가 상승률 5.0%",
        )
        self.assertEqual(
            displayed["BN.CAB.XOKA.GD.ZS"],
            "경상수지 -2.9% of GDP",
        )
        self.assertEqual(
            observations[0].raw_value,
            "-2.92630139201733",
        )

    def test_country_summary_limits_default_review_needs(self):
        summary = country_summary(
            self.golden["country_environment"]
        )

        self.assertEqual(summary["country"], "브라질")
        self.assertEqual(summary["review_label"], "통상 검토")
        self.assertLessEqual(len(summary["review_needs"]), 2)
        self.assertEqual(summary["verified_at"], "2026-07-29")

    def test_consultation_cards_keep_at_most_three_key_values(self):
        priorities = (
            self.consultation.packet.consultation_priorities
        )
        selected = [
            priority_key_rationale(priority)
            for priority in priorities
        ]

        self.assertEqual(len(priorities), 3)
        self.assertTrue(all(len(items) <= 3 for items in selected))
        self.assertEqual(
            [item.label for item in selected[0]],
            [
                "분석 대상 예정 수취액",
                "잔금 예정",
                "결제방식",
            ],
        )

    def test_no_feasible_copy_uses_only_returned_reason_codes(self):
        copies = no_feasible_reason_copy(
            [
                "ACCEPTABLE_LOSS_EXCEEDED",
                "MINIMUM_CASH_BUFFER_NOT_MET",
                "UNKNOWN_REASON",
            ]
        )

        self.assertEqual(
            copies,
            [
                "허용 가능한 환율 추가부담 안에 드는 조합이 없습니다.",
                "반드시 남길 운영자금 조건을 만족하는 조합이 없습니다.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
