import unittest
from types import SimpleNamespace

from src.application.consultation_service import build_decision_support
from src.application.trade_statistics_interpretation_service import (
    interpret_trade_statistics,
)
from src.config import Settings
from src.domain.consultation_models import ConsultationPacket
from src.domain.trade_statistics_interpretation_models import (
    TradeStatisticsInterpretationDraft,
)
from src.stage5.deterministic_fallback import (
    generate_deterministic_report,
)
from src.stage5.critic import critique_report
from src.stage3.optimizer import generate_strategy_candidates
from src.stage4.local_kb import search_offline_kb
from src.trade_statistics.interpretation_fallback import (
    build_trade_statistics_fallback,
)
from src.trade_statistics.interpretation_input import (
    build_trade_statistics_interpretation_input,
)
from src.trade_statistics.interpretation_validator import (
    TradeStatisticsInterpretationValidationError,
    validate_trade_statistics_interpretation,
)
from tests.golden_consultation_fixture import (
    build_golden_consultation_fixture,
)


class FakeResponses:
    def __init__(self, output_parsed=None, error=None):
        self.output_parsed = output_parsed
        self.error = error
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(output_parsed=self.output_parsed)


class FakeClient:
    def __init__(self, output_parsed=None, error=None):
        self.responses = FakeResponses(output_parsed, error)


class TradeStatisticsInterpretationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = build_golden_consultation_fixture()
        cls.disabled = Settings(
            enable_trade_statistics_interpretation=False,
            openai_api_key=None,
        )
        cls.enabled = Settings(
            enable_trade_statistics_interpretation=True,
            openai_api_key="test-only-key",
        )
        cls.interpretation_input = (
            build_trade_statistics_interpretation_input(
                result=cls.golden["trade_statistics"],
                settings=cls.disabled,
            )
        )
        cls.valid_draft = build_trade_statistics_fallback("INCREASED")

    def test_golden_input_preserves_four_indicators_and_directions(self):
        value = self.interpretation_input
        self.assertEqual(value.reporting_country_code, "KR")
        self.assertEqual(value.partner_country_code, "BR")
        self.assertEqual(value.export_change_direction, "INCREASED")
        self.assertEqual(value.trade_balance_direction, "SURPLUS")
        self.assertEqual(value.latest_12m_export_value, "8282425000")
        self.assertEqual(value.latest_12m_import_value, "6154122000")
        self.assertEqual(value.latest_12m_trade_balance, "2128302000")
        self.assertEqual(
            value.export_change_rate,
            "56.36383442142403103102139311",
        )

    def test_disabled_and_missing_key_use_deterministic_fallback(self):
        disabled = interpret_trade_statistics(
            interpretation_input=self.interpretation_input,
            settings=self.disabled,
        )
        missing_key = interpret_trade_statistics(
            interpretation_input=self.interpretation_input,
            settings=Settings(
                enable_trade_statistics_interpretation=True,
                openai_api_key=None,
            ),
        )
        self.assertEqual(disabled.fallback_reason, "AI_DISABLED")
        self.assertEqual(missing_key.fallback_reason, "NO_API_KEY")
        self.assertEqual(disabled.summary, missing_key.summary)

    def test_structured_output_is_used_once_without_storage(self):
        client = FakeClient(self.valid_draft)
        result = interpret_trade_statistics(
            interpretation_input=self.interpretation_input,
            settings=self.enabled,
            client=client,
        )
        self.assertEqual(result.status, "AI_VALIDATED")
        self.assertEqual(len(client.responses.calls), 1)
        self.assertFalse(client.responses.calls[0]["store"])

    def test_call_parse_and_validation_failures_use_fallback(self):
        call_failure = interpret_trade_statistics(
            interpretation_input=self.interpretation_input,
            settings=self.enabled,
            client=FakeClient(error=RuntimeError("offline")),
        )
        parse_failure = interpret_trade_statistics(
            interpretation_input=self.interpretation_input,
            settings=self.enabled,
            client=FakeClient(None),
        )
        invalid = interpret_trade_statistics(
            interpretation_input=self.interpretation_input,
            settings=self.enabled,
            client=FakeClient(
                self.valid_draft.model_copy(
                    update={"summary": "수출이 56퍼센트 증가했습니다."}
                )
            ),
        )
        self.assertEqual(call_failure.fallback_reason, "API_FAILURE")
        self.assertEqual(parse_failure.fallback_reason, "PARSE_FAILURE")
        self.assertEqual(invalid.fallback_reason, "VALIDATION_FAILED")

    def test_validator_rejects_numbers_values_dates_urls_and_markup(self):
        for text in (
            "수출이 1만큼 증가했습니다.",
            "수출이 퍼센트 단위로 증가했습니다.",
            "수출이 USD 기준으로 증가했습니다.",
            "수출이 https://example.com 자료에서 증가했습니다.",
            "**수출**이 증가했습니다.",
        ):
            with self.subTest(text=text):
                with self.assertRaises(
                    TradeStatisticsInterpretationValidationError
                ):
                    validate_trade_statistics_interpretation(
                        draft=self.valid_draft.model_copy(
                            update={"summary": text}
                        ),
                        interpretation_input=self.interpretation_input,
                    )

    def test_validator_rejects_financial_judgments_and_products(self):
        for text in (
            "수출이 증가해 안전한 국가입니다.",
            "수출이 증가해 거래처 부도 가능성이 낮습니다.",
            "수출이 증가해 대금 회수 가능성이 높습니다.",
            "수출이 증가해 환율 상승이 예상됩니다.",
            "수출이 증가해 환변동보험 가입이 필요합니다.",
            "수출이 증가해 금융상품을 추천합니다.",
            "수출이 증가해 추천 점수가 높습니다.",
        ):
            with self.subTest(text=text):
                with self.assertRaises(
                    TradeStatisticsInterpretationValidationError
                ):
                    validate_trade_statistics_interpretation(
                        draft=self.valid_draft.model_copy(
                            update={"summary": text}
                        ),
                        interpretation_input=self.interpretation_input,
                    )

    def test_validator_requires_complete_limitation(self):
        with self.assertRaises(
            TradeStatisticsInterpretationValidationError
        ):
            validate_trade_statistics_interpretation(
                draft=self.valid_draft.model_copy(
                    update={"limitation": "양국 전체 교역 참고자료입니다."}
                ),
                interpretation_input=self.interpretation_input,
            )

    def test_packet_is_optional_backward_compatible_and_bound(self):
        original = self.golden["decision"].consultation_packet.packet
        parsed = ConsultationPacket.model_validate(original.model_dump())
        self.assertIsNone(parsed.trade_statistics_interpretation)
        interpretation = interpret_trade_statistics(
            interpretation_input=self.interpretation_input,
            settings=self.disabled,
        )
        decision = self._decision(interpretation)
        packet = decision.consultation_packet.packet
        self.assertEqual(
            packet.trade_statistics_interpretation,
            interpretation,
        )
        self.assertIn(
            "trade_statistics_interpretation",
            packet.model_dump(),
        )

    def test_report_uses_the_exact_verified_interpretation(self):
        interpretation = interpret_trade_statistics(
            interpretation_input=self.interpretation_input,
            settings=self.disabled,
        )
        packet_result = self._decision(interpretation).consultation_packet
        stage3 = generate_strategy_candidates(
            self.golden["stage2"],
        )
        stage4 = search_offline_kb(
            trade_type=self.golden["stage2"].trade_type,
            query="수출대금 회수 보호 환율 관리 운영자금",
        )
        report = generate_deterministic_report(
            extraction=self.golden["extraction"],
            confirmation=self.golden["confirmation"],
            stage1=self.golden["stage1"],
            stage2=self.golden["stage2"],
            stage3=stage3,
            stage4=stage4,
            consultation_packet=packet_result.packet,
            confirmed_transaction=self.golden["confirmed_transaction"],
        )
        self.assertIn(interpretation.summary, report.markdown)
        self.assertIn(interpretation.limitation, report.markdown)
        altered = critique_report(
            markdown=report.markdown.replace(
                interpretation.summary,
                "최근 양국 교역 자료의 수출 흐름을 별도로 확인합니다.",
            ),
            source_bundle=report.report_json,
            scenario_kind=self.golden["stage1"].kind,
            probability_valid=self.golden["stage1"].probability_valid,
        )
        self.assertFalse(altered.passed)
        self.assertIn(
            "검증 완료된 무역통계 해석이 보고서에서 재작성되거나 누락됐습니다.",
            altered.issues,
        )

    def test_fingerprint_changes_and_hs_result_is_not_reinterpreted(self):
        changed = self.golden["trade_statistics"].model_copy(
            update={
                "request": self.golden["trade_statistics"].request.model_copy(
                    update={"trade_direction": "IMPORT"}
                )
            }
        )
        changed_input = build_trade_statistics_interpretation_input(
            result=changed,
            settings=self.disabled,
        )
        self.assertNotEqual(
            self.interpretation_input.input_fingerprint,
            changed_input.input_fingerprint,
        )
        hs_result = self.golden["trade_statistics"].model_copy(
            update={
                "request": self.golden["trade_statistics"].request.model_copy(
                    update={"hs_code": "02", "hs_level": 2,
                            "hs_code_confirmed": True}
                ),
                "summary": self.golden["trade_statistics"].summary.model_copy(
                    update={"scope": "HS_ITEM", "hs_code": "02",
                            "hs_level": 2}
                ),
            }
        )
        with self.assertRaises(ValueError):
            build_trade_statistics_interpretation_input(
                result=hs_result,
                settings=self.disabled,
            )

    def _decision(self, interpretation):
        value = self.golden
        return build_decision_support(
            case_id="golden_export_br_001",
            extraction=value["extraction"],
            confirmation=value["confirmation"],
            stage1=value["stage1"],
            stage2_input=value["stage2_input"],
            stage2_result=value["stage2"],
            trade_settlement_risk=value["trade_risk"],
            country_environment=value["country_environment"],
            trade_statistics=value["trade_statistics"],
            trade_statistics_interpretation=interpretation,
            generated_at="2026-07-29T09:00:00+09:00",
            confirmed_transaction=value["confirmed_transaction"],
        )


if __name__ == "__main__":
    unittest.main()
