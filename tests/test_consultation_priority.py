import unittest

from src.consultation.prioritization import (
    PRIORITY_DISCLAIMER,
    build_consultation_priorities,
)
from src.domain.consultation_models import InstallmentPaymentStatus
from tests.golden_consultation_fixture import (
    build_golden_consultation_fixture,
)


class GoldenConsultationPriorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = build_golden_consultation_fixture()
        cls.packet = cls.fixture[
            "decision"
        ].consultation_packet.packet

    def test_golden_priority_order_is_collection_fx_liquidity(self):
        self.assertEqual(
            [
                (item.rank, item.category, item.title)
                for item in self.packet.consultation_priorities
            ],
            [
                (
                    1,
                    "EXPORT_RECEIVABLE_PROTECTION",
                    "수출대금 회수 보호 상담",
                ),
                (2, "FX_RISK_MANAGEMENT", "환율 관리 상담"),
                (
                    3,
                    "EXPORT_LIQUIDITY_REVIEW",
                    "운영자금 버퍼·수출대금 회수시점 상담",
                ),
            ],
        )
        for item in self.packet.consultation_priorities:
            self.assertEqual(item.disclaimer, PRIORITY_DISCLAIMER)
            self.assertTrue(item.priority_rule_code)
            self.assertTrue(item.category_tie_break)

    def test_golden_numeric_rationale_uses_existing_results(self):
        collection, fx, liquidity = (
            self.packet.consultation_priorities
        )
        collection_values = {
            item.label: item.value
            for item in collection.numeric_rationale
        }
        self.assertEqual(
            collection_values["분석 대상 예정 수취액"],
            "100000.00",
        )
        self.assertEqual(collection_values["잔금 예정"], "80000.00")
        self.assertEqual(
            collection_values["결제방식"],
            "Open Account / T/T",
        )
        self.assertEqual(
            collection_values["확인된 보험·보증·신용장 보호"],
            "없음",
        )
        self.assertEqual(
            collection_values["선지급 실제 입금 여부"],
            "UNKNOWN",
        )
        self.assertEqual(
            collection_values["trade review"],
            "ELEVATED_REVIEW",
        )

        fx_values = {
            item.label: item.value for item in fx.numeric_rationale
        }
        self.assertEqual(fx_values["예정 수취 노출액"], "100000.00")
        self.assertEqual(fx_values["기준 원화 수취"], "140000000.00")
        self.assertEqual(fx_values["-5% 수취"], "133000000.00")
        self.assertEqual(fx_values["기준 대비 감소"], "7000000.00")
        self.assertEqual(fx_values["사용자 허용손실"], "5000000.00")
        self.assertEqual(fx_values["기존 헤지"], "0")
        self.assertEqual(fx_values["보유 USD"], "0")

        liquidity_values = {
            item.label: item.value
            for item in liquidity.numeric_rationale
        }
        self.assertEqual(
            liquidity_values["-5% ending cash"],
            "8000000.00",
        )
        self.assertEqual(
            liquidity_values["목표 buffer"],
            "10000000.00",
        )
        self.assertEqual(
            liquidity_values["buffer shortfall"],
            "2000000.00",
        )
        self.assertEqual(liquidity_values["cash deficit"], "0.00")
        self.assertEqual(
            liquidity_values["payment/post-credit deficit"],
            "0.00",
        )
        self.assertIn(
            "지급불능이나 대출 필요성 판단이 아니라",
            liquidity.priority_reason,
        )

    def test_unknown_advance_receipt_is_first_missing_item(self):
        expected = "USD 20,000 선지급의 실제 입금 여부와 입금일"
        self.assertEqual(self.packet.missing_information[0], expected)
        self.assertEqual(
            self.packet.consultation_priorities[
                0
            ].missing_information[0],
            expected,
        )
        self.assertEqual(
            self.packet.installment_payment_statuses[0].status,
            "UNKNOWN",
        )

    def test_user_confirmation_removes_only_advance_missing_item(self):
        confirmed = build_golden_consultation_fixture(
            payment_status=InstallmentPaymentStatus(
                installment_sequence=1,
                status="CONFIRMED_RECEIVED",
                actual_payment_date="2026-07-29",
                confirmed_by="fixture-user",
                confirmed_at="2026-07-29T10:00:00+09:00",
                source="USER_CONFIRMED",
            )
        )["decision"].consultation_packet.packet

        expected = "USD 20,000 선지급의 실제 입금 여부와 입금일"
        self.assertNotIn(expected, confirmed.missing_information)
        self.assertIn(
            "거래처의 과거 지급·연체·분쟁 이력",
            confirmed.missing_information,
        )
        self.assertNotEqual(
            confirmed.consultation_priority_fingerprint,
            self.packet.consultation_priority_fingerprint,
        )
        self.assertNotEqual(confirmed.input_hash, self.packet.input_hash)

    def test_priority_is_independent_of_topic_insertion_order(self):
        fixture = self.fixture
        topics = fixture["decision"].consultation_topics
        stage2_before = fixture["stage2"].model_dump()
        forward = build_consultation_priorities(
            extraction=fixture["extraction"],
            stage2_input=fixture["stage2_input"],
            stage2_result=fixture["stage2"],
            assessment=fixture["decision"].risk_assessment,
            consultation_topics=topics,
            trade_settlement_risk=fixture["trade_risk"],
            country_environment=fixture["country_environment"],
        )
        reversed_result = build_consultation_priorities(
            extraction=fixture["extraction"],
            stage2_input=fixture["stage2_input"],
            stage2_result=fixture["stage2"],
            assessment=fixture["decision"].risk_assessment,
            consultation_topics=list(reversed(topics)),
            trade_settlement_risk=fixture["trade_risk"],
            country_environment=fixture["country_environment"],
        )

        self.assertEqual(
            [item.model_dump() for item in forward[0]],
            [item.model_dump() for item in reversed_result[0]],
        )
        self.assertEqual(forward[2], reversed_result[2])
        self.assertEqual(stage2_before, fixture["stage2"].model_dump())

    def test_non_top_topics_remain_as_other_review_items(self):
        categories = {
            item.category
            for item in self.packet.other_consultation_topics
        }
        self.assertIn(
            "COUNTRY_MACRO_ENVIRONMENT_MONITORING",
            categories,
        )
        self.assertIn("TRADE_MARKET_ACCESS_REVIEW", categories)
        top_categories = {
            item.category
            for item in self.packet.consultation_priorities
        }
        self.assertTrue(categories.isdisjoint(top_categories))

    def test_documents_and_questions_are_deduplicated(self):
        for priority in self.packet.consultation_priorities:
            self.assertEqual(
                len(priority.preparation_documents),
                len(set(priority.preparation_documents)),
            )
            self.assertEqual(
                len(priority.bank_questions),
                len(set(priority.bank_questions)),
            )
            self.assertTrue(priority.expected_decision)
            self.assertTrue(priority.next_action)


if __name__ == "__main__":
    unittest.main()
