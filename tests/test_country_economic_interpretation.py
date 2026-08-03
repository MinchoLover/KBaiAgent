import json
import re
import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from src.application.consultation_service import build_decision_support
from src.application.country_economic_interpretation_service import (
    interpret_country_economic_environment,
)
from src.config import Settings
from src.country_environment.assessment import (
    assess_country_trade_environment,
)
from src.country_environment.interpretation_fallback import (
    build_deterministic_interpretation,
)
from src.country_environment.interpretation_input import (
    build_country_economic_interpretation_input,
)
from src.country_environment.interpretation_validator import (
    CountryEconomicInterpretationValidationError,
    validate_country_economic_interpretation,
)
from src.demo import run_decision_support_demo
from src.domain.consultation_models import ConsultationPacket
from src.domain.country_economic_interpretation_models import (
    CountryEconomicInterpretationDraft,
    CountryEconomicInterpretationSection,
)
from src.stage5.report_agent import generate_report
from src.ui.state import (
    clear_country_environment_and_related,
    clear_trade_risk_and_related,
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


class CountryEconomicInterpretationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = build_golden_consultation_fixture()
        cls.disabled_settings = Settings(
            enable_country_economic_interpretation=False,
            openai_api_key=None,
        )
        cls.enabled_settings = Settings(
            enable_country_economic_interpretation=True,
            openai_api_key="test-only-key",
        )
        cls.interpretation_input = (
            build_country_economic_interpretation_input(
                assessment=cls.golden["country_environment"],
                country_input=cls.golden["country_environment_input"],
                confirmed_transaction=cls.golden[
                    "confirmed_transaction"
                ],
                settings=cls.disabled_settings,
            )
        )
        cls.valid_draft = build_deterministic_interpretation(
            cls.interpretation_input.indicators
        )

    def test_brazil_verified_input_contains_four_bound_sources(self):
        value = self.interpretation_input
        self.assertEqual(value.country_code, "BR")
        self.assertEqual(value.transaction_context.trade_direction, "EXPORT")
        self.assertEqual(
            [item.indicator_id for item in value.indicators],
            [
                "GDP_GROWTH",
                "INFLATION",
                "CURRENT_ACCOUNT",
                "OECD_CLASSIFICATION",
            ],
        )
        assessment = self.golden["country_environment"]
        self.assertEqual(
            value.country_environment_snapshot_fingerprint,
            assessment.input_fingerprint,
        )
        self.assertEqual(
            value.country_environment_snapshot_hash,
            assessment.snapshot_hash,
        )
        self.assertTrue(
            all(item.source.official_url for item in value.indicators)
        )

    def test_explanation_output_never_carries_deterministic_values(self):
        result = interpret_country_economic_environment(
            interpretation_input=self.interpretation_input,
            settings=self.disabled_settings,
        )
        explanation = " ".join(
            [result.overall_summary]
            + [
                text
                for item in result.sections
                for text in [item.observation, item.transaction_check]
            ]
            + result.limitations
        )
        self.assertIsNone(re.search(r"[0-9]", explanation))
        self.assertNotIn("deterministic_value", result.model_dump())

    def test_ai_disabled_and_missing_key_use_fallback(self):
        disabled = interpret_country_economic_environment(
            interpretation_input=self.interpretation_input,
            settings=self.disabled_settings,
        )
        missing_key = interpret_country_economic_environment(
            interpretation_input=self.interpretation_input,
            settings=Settings(
                enable_country_economic_interpretation=True,
                openai_api_key=None,
            ),
        )
        self.assertEqual(disabled.fallback_reason, "AI_DISABLED")
        self.assertEqual(missing_key.fallback_reason, "NO_API_KEY")
        self.assertEqual(disabled.sections, missing_key.sections)

    def test_valid_structured_ai_output_is_used_once_without_storage(self):
        client = FakeClient(self.valid_draft)
        result = interpret_country_economic_environment(
            interpretation_input=self.interpretation_input,
            settings=self.enabled_settings,
            client=client,
        )
        self.assertEqual(result.status, "AI_VALIDATED")
        self.assertEqual(len(client.responses.calls), 1)
        call = client.responses.calls[0]
        self.assertFalse(call["store"])
        self.assertEqual(call["model"], self.enabled_settings.openai_model)

    def test_parse_and_call_failures_use_fallback(self):
        parse_failure = interpret_country_economic_environment(
            interpretation_input=self.interpretation_input,
            settings=self.enabled_settings,
            client=FakeClient(None),
        )
        call_failure = interpret_country_economic_environment(
            interpretation_input=self.interpretation_input,
            settings=self.enabled_settings,
            client=FakeClient(error=RuntimeError("offline")),
        )
        self.assertEqual(parse_failure.fallback_reason, "PARSE_FAILURE")
        self.assertEqual(call_failure.fallback_reason, "API_FAILURE")

    def test_validator_rejects_numbers_and_prohibited_claims(self):
        for text in (
            "공식 관측값은 삼 퍼센트가 아니라 3퍼센트입니다.",
            "공식 관측값은 삼 퍼센트입니다.",
            "환율 상승 예상입니다.",
            "이 국가는 안전한 국가입니다.",
        ):
            with self.subTest(text=text):
                draft = self.valid_draft.model_copy(
                    update={"overall_summary": text}
                )
                with self.assertRaises(
                    CountryEconomicInterpretationValidationError
                ):
                    validate_country_economic_interpretation(
                        draft=draft,
                        interpretation_input=self.interpretation_input,
                    )

    def test_validator_rejects_unknown_and_duplicate_indicators(self):
        unknown = self.valid_draft.sections[0].model_copy(
            update={"indicator_id": "UNSEEN_INDICATOR"}
        )
        duplicate = self.valid_draft.sections[0]
        for sections in (
            [unknown] + self.valid_draft.sections[1:],
            [duplicate, duplicate] + self.valid_draft.sections[2:],
        ):
            with self.assertRaises(
                CountryEconomicInterpretationValidationError
            ):
                validate_country_economic_interpretation(
                    draft=self.valid_draft.model_copy(
                        update={"sections": sections}
                    ),
                    interpretation_input=self.interpretation_input,
                )

    def test_validator_rejects_products_institutions_scores_and_ranks(self):
        for text in (
            "한국무역보험공사 상담을 준비하세요.",
            "추천 점수를 확인하세요.",
            "상담 순위를 높이세요.",
        ):
            with self.subTest(text=text):
                section = self.valid_draft.sections[0].model_copy(
                    update={"transaction_check": text}
                )
                draft = self.valid_draft.model_copy(
                    update={
                        "sections": [section]
                        + self.valid_draft.sections[1:]
                    }
                )
                with self.assertRaises(
                    CountryEconomicInterpretationValidationError
                ):
                    validate_country_economic_interpretation(
                        draft=draft,
                        interpretation_input=self.interpretation_input,
                    )

    def test_invalid_ai_output_falls_back_without_rewrite(self):
        invalid = self.valid_draft.model_copy(
            update={"overall_summary": "위험점수는 9점입니다."}
        )
        client = FakeClient(invalid)
        result = interpret_country_economic_environment(
            interpretation_input=self.interpretation_input,
            settings=self.enabled_settings,
            client=client,
        )
        self.assertEqual(result.fallback_reason, "VALIDATION_FAILED")
        self.assertEqual(len(client.responses.calls), 1)

    def test_packet_optional_field_is_backward_compatible_and_bound(self):
        fallback = interpret_country_economic_environment(
            interpretation_input=self.interpretation_input,
            settings=self.disabled_settings,
        )
        original_packet = self.golden["decision"].consultation_packet.packet
        legacy_payload = original_packet.model_dump()
        legacy_payload.pop("country_economic_interpretation", None)
        restored = ConsultationPacket.model_validate(legacy_payload)
        self.assertIsNone(restored.country_economic_interpretation)

        value = self.golden
        decision = build_decision_support(
            case_id="country-interpretation-test",
            extraction=value["extraction"],
            confirmation=value["confirmation"],
            stage1=value["stage1"],
            stage2_input=value["stage2_input"],
            stage2_result=value["stage2"],
            trade_settlement_risk=value["trade_risk"],
            country_environment=value["country_environment"],
            country_economic_interpretation=fallback,
            trade_statistics=value["trade_statistics"],
            confirmed_transaction=value["confirmed_transaction"],
            generated_at="2026-07-29T09:00:00+09:00",
        )
        packet = decision.consultation_packet.packet
        self.assertEqual(packet.country_economic_interpretation, fallback)
        self.assertIn(
            fallback.overall_summary,
            decision.consultation_packet.markdown,
        )

    def test_stage5_report_uses_packet_interpretation_verbatim(self):
        demo = run_decision_support_demo("SELLER")
        workflow = demo["workflow_state"]
        value_input = build_country_economic_interpretation_input(
            assessment=demo["country_environment_assessment"],
            country_input=demo["country_environment_input"],
            confirmed_transaction=workflow.confirmed_transaction,
            settings=self.disabled_settings,
        )
        interpretation = interpret_country_economic_environment(
            interpretation_input=value_input,
            settings=self.disabled_settings,
        )
        decision = build_decision_support(
            case_id=workflow.case_id,
            extraction=demo["extraction"],
            confirmation=demo["confirmation"],
            stage1=demo["stage1"],
            stage2_input=demo["stage2_input"],
            stage2_result=demo["stage2"],
            trade_settlement_risk=demo["trade_risk_assessment"],
            country_environment=demo["country_environment_assessment"],
            country_economic_interpretation=interpretation,
            trade_statistics=demo["trade_statistics_result"],
            official_candidate_shortlist=demo[
                "official_candidate_shortlist"
            ],
            confirmed_transaction=workflow.confirmed_transaction,
            generated_at="2026-07-23T09:00:00+09:00",
        )
        report = generate_report(
            extraction=demo["extraction"],
            confirmation=demo["confirmation"],
            stage1=demo["stage1"],
            stage2=demo["stage2"],
            stage3=demo["stage3"],
            stage4=demo["stage4"],
            consultation_packet=decision.consultation_packet.packet,
            confirmed_transaction=workflow.confirmed_transaction,
            settings=Settings(enable_llm_report=False),
        )
        self.assertTrue(report.critique.passed)
        self.assertIn(interpretation.overall_summary, report.markdown)
        for section in interpretation.sections:
            self.assertIn(section.observation, report.markdown)
            self.assertIn(section.transaction_check, report.markdown)

    def test_interpretation_does_not_change_stages_one_to_three(self):
        demo = run_decision_support_demo("SELLER")
        before = {
            "stage1": demo["stage1"].model_dump(),
            "stage2": demo["stage2"].model_dump(),
            "stage3": demo["stage3"].model_dump(),
        }
        value_input = build_country_economic_interpretation_input(
            assessment=demo["country_environment_assessment"],
            country_input=demo["country_environment_input"],
            confirmed_transaction=demo["workflow_state"].confirmed_transaction,
            settings=self.disabled_settings,
        )
        interpret_country_economic_environment(
            interpretation_input=value_input,
            settings=self.disabled_settings,
        )
        self.assertEqual(demo["stage1"].model_dump(), before["stage1"])
        self.assertEqual(demo["stage2"].model_dump(), before["stage2"])
        self.assertEqual(demo["stage3"].model_dump(), before["stage3"])

    def test_changed_transaction_context_changes_fingerprint(self):
        changed_country_input = self.golden[
            "country_environment_input"
        ].model_copy(update={"balance_payment_method": "OTHER"})
        changed_assessment = assess_country_trade_environment(
            changed_country_input
        )
        changed = build_country_economic_interpretation_input(
            assessment=changed_assessment,
            country_input=changed_country_input,
            confirmed_transaction=self.golden["confirmed_transaction"],
            settings=self.disabled_settings,
        )
        self.assertNotEqual(
            changed.input_fingerprint,
            self.interpretation_input.input_fingerprint,
        )

    def test_state_invalidation_removes_only_authoritative_result(self):
        for clear in (
            clear_trade_risk_and_related,
            clear_country_environment_and_related,
        ):
            state = {
                "country_economic_interpretation_result": {"old": True},
                "stage2_result": {"preserved": True},
            }
            clear(state)
            self.assertNotIn(
                "country_economic_interpretation_result",
                state,
            )
            self.assertIn("stage2_result", state)

    def test_draft_schema_rejects_empty_required_fields(self):
        with self.assertRaises(ValidationError):
            CountryEconomicInterpretationDraft(
                overall_summary="",
                sections=[
                    CountryEconomicInterpretationSection(
                        indicator_id="GDP_GROWTH",
                        observation="",
                        transaction_check="확인하세요.",
                    )
                ],
                limitations=["한계입니다."],
            )


if __name__ == "__main__":
    unittest.main()
