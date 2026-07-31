import unittest

from src.application.consultation_service import build_decision_support
from src.consultation.response_mapping import (
    map_consultation_topics,
    map_trade_risk_consultation_topics,
)
from src.consultation.risk_classifier import classify_stage2_risks
from src.consultation.trade_settlement_risk import (
    assess_trade_settlement_risk,
    create_trade_risk_confirmation,
)
from src.demo import run_decision_support_demo, run_offline_demo
from src.domain.trade_risk_models import TradeSettlementRiskInput


def _trade_risk_assessment(
    *,
    trade_type="EXPORT",
    relationship="EXISTING",
    ratio="0",
    method="DOCUMENTARY_CREDIT",
    term_days=30,
    term_basis="EXPLICIT_NET_TERM",
    protection_status="NONE_CONFIRMED",
):
    risk_input = TradeSettlementRiskInput(
        confirmed_trade_sha256="b" * 64,
        trade_type=trade_type,
        counterparty_relationship=relationship,
        advance_payment_ratio=ratio,
        balance_payment_method=method,
        payment_term_days=term_days,
        payment_term_basis=term_basis,
        protection_information_status=protection_status,
        protection_mechanisms=[],
        field_sources={
            "counterparty_relationship": "USER_CONFIRMED",
            "advance_payment_ratio": "USER_CONFIRMED",
            "balance_payment_method": "USER_CONFIRMED",
            "payment_term_days": "USER_CONFIRMED",
            "protection_information_status": "USER_CONFIRMED",
        },
    )
    confirmation = create_trade_risk_confirmation(
        confirmed_input=risk_input,
        confirmed_at="2026-07-29T09:00:00+09:00",
    )
    return assess_trade_settlement_risk(confirmation)


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

    def test_import_trade_risk_maps_to_protection_consultation(self):
        topics = self.demo["consultation_topics"]
        topic = next(
            item
            for item in topics
            if item.category == "IMPORT_ADVANCE_PAYMENT_PROTECTION"
        )

        self.assertIn(
            "ADVANCE_PAYMENT_PROTECTION_REVIEW",
            topic.trade_risk_review_needs,
        )
        self.assertIn(
            "IMPORT_ADVANCE_PAYMENT",
            topic.trade_risk_factor_codes,
        )
        self.assertIn(
            "선급금환급보증",
            " ".join(topic.required_documents),
        )
        packet = self.demo["consultation_packet"]
        self.assertIsNotNone(packet.packet.trade_settlement_risk)
        self.assertIn("## 4. 거래·결제조건 위험", packet.markdown)
        self.assertIn("수입 선지급 보호수단 상담", packet.markdown)
        self.assertIn("공식 심사등급이나 부도확률", packet.markdown)

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

    def test_export_liquidity_risk_maps_to_review_topic(self):
        assessment = self.demo["risk_assessment"]
        result = self.demo["stage2"]
        topic = next(
            item
            for item in self.demo["consultation_topics"]
            if item.category == "EXPORT_LIQUIDITY_REVIEW"
        )

        self.assertIn(
            "LIQUIDITY_BUFFER_RISK",
            assessment.risk_codes,
        )
        self.assertEqual(
            topic.title,
            "운영자금 버퍼·수출대금 회수시점 상담",
        )
        self.assertEqual(
            topic.triggered_by,
            ["LIQUIDITY_BUFFER_RISK"],
        )
        self.assertIn("지급불능이나 대출 필요성을 판단하지", topic.explanation)
        self.assertNotIn("대출이 반드시 필요", topic.explanation)

        stress = next(
            item
            for item in result.scenario_results
            if item.scenario_name == "STRESS_-5PCT"
        )
        self.assertEqual(stress.cash_deficit, "0.00")
        self.assertEqual(stress.post_credit_shortfall, "0.00")

    def test_import_liquidity_mapping_is_unchanged(self):
        import_demo = run_decision_support_demo("BUYER")
        categories = {
            item.category
            for item in import_demo["consultation_topics"]
        }

        self.assertIn("IMPORT_SETTLEMENT_FINANCE", categories)
        self.assertNotIn("EXPORT_LIQUIDITY_REVIEW", categories)

    def test_export_trade_risk_maps_only_to_receivable_protection(self):
        categories = {
            item.category for item in self.demo["consultation_topics"]
        }

        self.assertIn("EXPORT_RECEIVABLE_PROTECTION", categories)
        self.assertNotIn(
            "IMPORT_ADVANCE_PAYMENT_PROTECTION",
            categories,
        )
        topic = next(
            item
            for item in self.demo["consultation_topics"]
            if item.category == "EXPORT_RECEIVABLE_PROTECTION"
        )
        self.assertIn(
            "RECEIVABLE_PROTECTION_REVIEW",
            topic.trade_risk_review_needs,
        )
        self.assertIn("EXPORT_OPEN_ACCOUNT", topic.trade_risk_factor_codes)
        self.assertIn(
            "수출대금 회수 보호 상담",
            self.demo["consultation_packet"].markdown,
        )


class TradeRiskResponseMappingTests(unittest.TestCase):
    def test_legacy_packet_serialization_omits_optional_trade_risk(self):
        demo = run_offline_demo()
        packet = demo["consultation_packet"].packet

        self.assertIsNone(packet.trade_settlement_risk)
        self.assertIsNone(packet.country_environment)
        self.assertNotIn(
            "trade_settlement_risk",
            packet.model_dump(),
        )
        self.assertNotIn(
            "country_environment",
            packet.model_dump(),
        )
        legacy_topic = map_consultation_topics(
            trade_type="IMPORT",
            assessment=demo["risk_assessment"],
            stage2_result=demo["stage2"],
        )[0]
        self.assertNotIn(
            "trade_risk_factor_codes",
            legacy_topic.model_dump(),
        )
        self.assertNotIn(
            "country_environment_rule_codes",
            legacy_topic.model_dump(),
        )

    def test_documentary_credit_maps_to_terms_review_not_risk_removal(self):
        assessment = _trade_risk_assessment()

        topics = map_trade_risk_consultation_topics(assessment)

        self.assertEqual(
            [item.category for item in topics],
            ["DOCUMENTARY_CREDIT_TERMS_REVIEW"],
        )
        self.assertIn(
            "신용장 존재만으로 회수위험이 제거된다고 보지 않고",
            topics[0].explanation,
        )

    def test_unknown_values_map_to_information_review(self):
        assessment = _trade_risk_assessment(
            relationship="UNKNOWN",
            ratio=None,
            method="UNKNOWN",
            term_days=None,
            term_basis="UNKNOWN",
            protection_status="UNKNOWN",
        )

        topics = map_trade_risk_consultation_topics(assessment)

        information = next(
            item
            for item in topics
            if item.category == "TRADE_RISK_INFORMATION_REVIEW"
        )
        self.assertTrue(information.required_information)
        self.assertIn(
            "HUMAN_REVIEW",
            information.trade_risk_review_needs,
        )

    def test_packet_hash_is_bound_to_trade_risk_fingerprint(self):
        demo = run_decision_support_demo("BUYER")
        current = demo["trade_risk_assessment"]
        changed = current.model_copy(
            update={"input_fingerprint": "c" * 64}
        )

        rebuilt = build_decision_support(
            case_id=demo["workflow_state"].case_id,
            extraction=demo["extraction"],
            confirmation=demo["confirmation"],
            stage1=demo["stage1"],
            stage2_input=demo["stage2_input"],
            stage2_result=demo["stage2"],
            trade_settlement_risk=changed,
            generated_at="2026-07-23T09:00:00+09:00",
        )

        self.assertNotEqual(
            rebuilt.consultation_packet.packet.input_hash,
            demo["consultation_packet"].packet.input_hash,
        )


if __name__ == "__main__":
    unittest.main()
