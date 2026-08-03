import json
import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from scripts.verify_golden_user_flow import (
    build_golden_user_flow_artifacts,
)
from src.config import Settings
from src.domain.report_models import (
    Stage5NarrativeDraft,
    Stage5NarrativeItem,
)
from src.stage5.critic import critique_report
from src.stage5.grounding import (
    Stage5NarrativeValidationError,
    build_grounding_registry,
    build_narrative_prompt,
    render_grounded_narratives,
    resolve_canonical_path,
    validate_narrative_draft,
)
from src.stage5.report_agent import generate_report


class Stage5GroundingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = build_golden_user_flow_artifacts()
        cls.bundle = cls.artifacts["report"].report_json
        cls.registry = build_grounding_registry(cls.bundle)

    def _draft(self, text=None):
        explanation = text or (
            "확정된 입력의 의미를 확인하고 기관 상담에서 적용 범위를 "
            "점검해야 합니다."
        )
        return Stage5NarrativeDraft(
            narratives=[
                Stage5NarrativeItem(
                    source_id=item.source_id,
                    explanation=explanation,
                )
                for item in self.registry
            ]
        )

    def test_golden_registry_has_only_resolvable_canonical_paths(self):
        self.assertEqual(len(self.registry), 9)
        self.assertEqual(
            len({item.source_id for item in self.registry}),
            len(self.registry),
        )
        for item in self.registry:
            self.assertIsNotNone(
                resolve_canonical_path(
                    self.bundle,
                    item.canonical_path,
                )
            )

    def test_prompt_exposes_source_ids_without_paths_or_values(self):
        payload = build_narrative_prompt(self.registry)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(
            payload["required_source_id_order"],
            [item.source_id for item in self.registry],
        )
        for item in self.registry:
            self.assertNotIn(item.canonical_path, serialized)
        self.assertNotIn("100000.00", serialized)
        self.assertNotIn("ksure_short_term_export_insurance", serialized)

    def test_unknown_source_id_is_rejected_by_schema(self):
        with self.assertRaises(ValidationError):
            Stage5NarrativeDraft.model_validate(
                {
                    "narratives": [
                        {
                            "source_id": "INVENTED_SOURCE",
                            "explanation": "상담에서 확인합니다.",
                        }
                    ]
                }
            )

    def test_draft_rejects_order_values_and_product_rewrite(self):
        reversed_draft = self._draft().model_copy(
            update={
                "narratives": list(
                    reversed(self._draft().narratives)
                )
            }
        )
        with self.assertRaises(Stage5NarrativeValidationError):
            validate_narrative_draft(
                draft=reversed_draft,
                registry=self.registry,
                source_bundle=self.bundle,
            )
        with self.assertRaises(ValidationError):
            Stage5NarrativeItem(
                source_id=self.registry[0].source_id,
                explanation="확정 금액은 백 달러입니다. 100",
            )
        product_name = self.artifacts["shortlist"].candidates[0].name
        product_draft = self._draft(
            "{}의 적용 범위를 확인합니다.".format(product_name)
        )
        with self.assertRaises(Stage5NarrativeValidationError):
            validate_narrative_draft(
                draft=product_draft,
                registry=self.registry,
                source_bundle=self.bundle,
            )
        transaction_draft = self._draft(
            "EXPORT 거래조건을 상담에서 확인합니다."
        )
        with self.assertRaises(Stage5NarrativeValidationError):
            validate_narrative_draft(
                draft=transaction_draft,
                registry=self.registry,
                source_bundle=self.bundle,
            )

    def test_renderer_keeps_canonical_report_and_passes_critic(self):
        draft = self._draft()
        validate_narrative_draft(
            draft=draft,
            registry=self.registry,
            source_bundle=self.bundle,
        )
        markdown = render_grounded_narratives(
            deterministic_markdown=self.artifacts["report"].markdown,
            draft=draft,
            registry=self.registry,
        )
        state = self.artifacts["workflow"]
        critique = critique_report(
            markdown=markdown,
            source_bundle=self.bundle,
            scenario_kind=state.market_risk.data.scenario_set.kind,
            probability_valid=(
                state.market_risk.data.scenario_set.probability_valid
            ),
        )
        self.assertTrue(critique.passed, critique.issues)
        self.assertIn("100000.00", markdown)
        self.assertIn("20000.00", markdown)
        self.assertIn("80000.00", markdown)
        positions = [
            markdown.index(item.name)
            for item in self.artifacts["shortlist"].candidates
        ]
        self.assertEqual(positions, sorted(positions))

    def test_max_zero_invalid_draft_calls_once_and_falls_back(self):
        calls = []
        invalid = self._draft("가입 가능합니다.")

        def parse(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_parsed=invalid)

        artifact = self.artifacts
        golden = artifact["golden"]
        state = artifact["workflow"]
        result = generate_report(
            extraction=golden["extraction"],
            confirmation=golden["confirmation"],
            confirmed_transaction=state.confirmed_transaction,
            stage1=state.market_risk.data.scenario_set,
            stage2=state.cashflow.data,
            stage3=state.hedge.data,
            stage4=state.product_search.data,
            market_integration=state.market_integration,
            consultation_packet=(
                artifact["decision"].consultation_packet.packet
            ),
            settings=Settings(
                openai_api_key="test-only",
                enable_llm_report=True,
            ),
            client=SimpleNamespace(
                responses=SimpleNamespace(parse=parse)
            ),
            max_revisions=0,
        )
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0]["store"])
        self.assertEqual(result.status, "DETERMINISTIC_FALLBACK")
        self.assertEqual(result.fallback_reason, "CRITIC_REJECTED")
        self.assertTrue(result.critique.passed)


if __name__ == "__main__":
    unittest.main()
