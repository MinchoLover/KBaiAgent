import unittest

from src.consultation.response_mapping import map_consultation_topics
from src.consultation.risk_classifier import classify_stage2_risks
from src.demo import run_decision_support_demo


class DecisionSupportImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = run_decision_support_demo("BUYER")

    def test_import_representative_calculation(self):
        result = self.demo["stage2"]
        self.assertEqual(result.open_exposure, "80000.00")
        self.assertEqual(
            result.base_required_or_proceeds_krw,
            "112000000.00",
        )
        stress = next(
            item
            for item in result.scenario_results
            if item.scenario_name == "STRESS_+5PCT"
        )
        self.assertEqual(stress.scenario_rate, "1470")
        self.assertEqual(stress.fx_krw_outflow, "117600000.00")
        self.assertEqual(stress.loss_vs_base, "5600000.00")

    def test_buffer_shortfall_is_not_payment_gap(self):
        assessment = self.demo["risk_assessment"]
        packet = self.demo["consultation_packet"].packet
        self.assertEqual(assessment.status, "BUFFER_SHORTFALL")
        self.assertIn(
            "LIQUIDITY_BUFFER_RISK",
            assessment.risk_codes,
        )
        self.assertNotIn(
            "PAYMENT_CAPACITY_RISK",
            assessment.risk_codes,
        )
        self.assertEqual(
            packet.risk_summary.cash_after_settlement_krw,
            "7400000.00",
        )
        self.assertEqual(
            packet.risk_summary.buffer_shortfall_krw,
            "2600000.00",
        )
        self.assertEqual(packet.risk_summary.payment_gap_krw, "0.00")

    def test_import_consultation_topics_are_generic_and_reviewed(self):
        topics = self.demo["consultation_topics"]
        titles = [item.title for item in topics]
        self.assertIn("환율 관리 상담", titles)
        self.assertIn("수입 결제자금 상담", titles)
        self.assertIn("보유 외화 활용 검토", titles)
        self.assertEqual(
            len({item.category for item in topics}),
            len(topics),
        )
        for item in topics:
            self.assertTrue(item.human_review_required)
            self.assertEqual(
                item.eligibility_status,
                "REQUIRES_BANK_REVIEW",
            )
            self.assertEqual(
                item.source_status,
                "GENERIC_CONSULTATION_CATEGORY",
            )

    def test_packet_numbers_and_audit_fields_match_engine(self):
        packet_result = self.demo["consultation_packet"]
        packet = packet_result.packet
        self.assertEqual(
            packet.exposure_summary.open_exposure_fx,
            self.demo["stage2"].open_exposure,
        )
        self.assertEqual(
            packet.risk_summary.additional_cost_or_receipt_loss_krw,
            "5600000.00",
        )
        self.assertEqual(
            packet.user_confirmed_fields,
            [
                "company_role",
                "trade_type",
                "currency",
                "trade_amount_fx",
                "settlement_date",
            ],
        )
        self.assertEqual(len(packet.input_hash), 64)
        self.assertTrue(packet.calculation_version)
        self.assertTrue(packet.required_documents)
        self.assertIn("금융상품 가입", packet.disclaimer)
        self.assertIn("확정 예측이 아닙니다", packet.disclaimer)
        self.assertIn("대출한도 반영 후 지급 부족", packet_result.markdown)

    def test_negative_cash_and_payment_capacity_are_separate_codes(self):
        result = self.demo["stage2"]
        scenario_results = []
        for item in result.scenario_results:
            if item.scenario_name == "STRESS_+5PCT":
                item = item.model_copy(
                    update={
                        "ending_cash": "-2000000.00",
                        "minimum_cash": "-2000000.00",
                        "maximum_buffer_shortfall": "12000000.00",
                        "cash_deficit": "2000000.00",
                        "post_credit_shortfall": "1000000.00",
                    }
                )
            scenario_results.append(item)
        stressed = result.model_copy(
            update={"scenario_results": scenario_results}
        )
        assessment = classify_stage2_risks(
            stage2_result=stressed,
            stage2_input=self.demo["stage2_input"],
        )
        self.assertEqual(assessment.status, "PAYMENT_GAP")
        self.assertIn("NEGATIVE_CASH_RISK", assessment.risk_codes)
        self.assertIn(
            "PAYMENT_CAPACITY_RISK",
            assessment.risk_codes,
        )

    def test_information_gap_maps_to_document_review_once(self):
        assessment = classify_stage2_risks(
            stage2_result=self.demo["stage2"],
            stage2_input=self.demo["stage2_input"],
            missing_information=[
                "실제 대출한도 확인 필요",
                "실제 대출한도 확인 필요",
            ],
        )
        self.assertIn(
            "DOCUMENT_INFORMATION_GAP",
            assessment.risk_codes,
        )
        topics = map_consultation_topics(
            trade_type="IMPORT",
            assessment=assessment,
            stage2_result=self.demo["stage2"],
        )
        categories = [item.category for item in topics]
        self.assertEqual(categories.count("TRADE_INFORMATION_REVIEW"), 1)


class DecisionSupportExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = run_decision_support_demo("SELLER")

    def test_export_rate_fall_reduces_receipt(self):
        result = self.demo["stage2"]
        self.assertEqual(result.trade_type, "EXPORT")
        self.assertEqual(
            result.base_required_or_proceeds_krw,
            "140000000.00",
        )
        stress = next(
            item
            for item in result.scenario_results
            if item.scenario_name == "STRESS_-5PCT"
        )
        self.assertEqual(stress.scenario_rate, "1330")
        self.assertEqual(stress.fx_krw_inflow, "133000000.00")
        self.assertEqual(stress.loss_vs_base, "7000000.00")
        self.assertEqual(stress.ending_cash, "8000000.00")

    def test_export_risk_and_consultation_packet(self):
        assessment = self.demo["risk_assessment"]
        packet = self.demo["consultation_packet"].packet
        self.assertIn("FX_RECEIPT_RISK", assessment.risk_codes)
        self.assertNotIn("FX_COST_RISK", assessment.risk_codes)
        self.assertIn(
            "수출대금 회수·환율 관리 상담",
            [item.title for item in self.demo["consultation_topics"]],
        )
        self.assertEqual(
            packet.risk_summary.additional_cost_or_receipt_loss_krw,
            "7000000.00",
        )
        self.assertEqual(packet.company_summary.trade_type, "EXPORT")


if __name__ == "__main__":
    unittest.main()
