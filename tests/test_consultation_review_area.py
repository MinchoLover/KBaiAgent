import unittest

from src.consultation.prioritization import CATEGORY_PRIORITY_RULES
from src.consultation.packet import _markdown
from src.consultation.review_area import (
    CATEGORY_TO_REVIEW_AREA,
    CATEGORY_TO_SUPPORTING_CHECK,
    REVIEW_AREA_DISPLAY_NAMES,
    SUPPORTING_CHECK_DISPLAY_NAMES,
    UnmappedConsultationCategoryError,
    project_consultation_presentation,
    project_consultation_review_areas,
    validate_category_classification,
    validate_review_area_mapping,
)
from src.domain.consultation_models import ConsultationPacket
from src.demo import run_decision_support_demo
from tests.golden_consultation_fixture import (
    build_golden_consultation_fixture,
)


class ConsultationReviewAreaProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = build_golden_consultation_fixture()
        cls.packet = cls.fixture[
            "decision"
        ].consultation_packet.packet
        cls.priorities = cls.packet.consultation_priorities
        cls.fingerprint = cls.packet.consultation_priority_fingerprint
        cls.product_packet = run_decision_support_demo(
            "SELLER"
        )["consultation_packet"].packet

    def test_every_priority_category_has_an_explicit_mapping(self):
        validate_review_area_mapping()
        validate_category_classification()
        self.assertEqual(
            set(CATEGORY_TO_REVIEW_AREA)
            | set(CATEGORY_TO_SUPPORTING_CHECK),
            set(CATEGORY_PRIORITY_RULES),
        )
        self.assertFalse(
            set(CATEGORY_TO_REVIEW_AREA)
            & set(CATEGORY_TO_SUPPORTING_CHECK)
        )
        self.assertEqual(
            set(REVIEW_AREA_DISPLAY_NAMES),
            {
                "COLLECTION_PROTECTION",
                "FX_MANAGEMENT",
                "PAYMENT_TERMS",
                "WORKING_CAPITAL_TRADE_FINANCE",
                "POLICY_FINANCE",
            },
        )
        self.assertNotIn(
            "POLICY_FINANCE",
            set(CATEGORY_TO_REVIEW_AREA.values()),
        )
        self.assertEqual(
            set(SUPPORTING_CHECK_DISPLAY_NAMES),
            set(CATEGORY_TO_SUPPORTING_CHECK.values()),
        )

    def test_six_information_monitoring_categories_are_supporting(self):
        self.assertEqual(
            dict(CATEGORY_TO_SUPPORTING_CHECK),
            {
                "TRADE_RISK_INFORMATION_REVIEW": (
                    "TRADE_RISK_INFORMATION"
                ),
                "TRADE_INFORMATION_REVIEW": (
                    "TRADE_INFORMATION_COMPLETENESS"
                ),
                "COUNTRY_INFORMATION_COMPLETENESS": (
                    "COUNTRY_INFORMATION_COMPLETENESS"
                ),
                "COUNTRY_MACRO_ENVIRONMENT_MONITORING": (
                    "COUNTRY_MACRO_MONITORING"
                ),
                "TRADE_MARKET_ACCESS_REVIEW": (
                    "MARKET_ACCESS_AND_TRADE_ENVIRONMENT"
                ),
                "ROUTINE_TRADE_REVIEW": "ROUTINE_TRADE_CHECK",
            },
        )
        for category in CATEGORY_TO_SUPPORTING_CHECK:
            self.assertNotIn(category, CATEGORY_TO_REVIEW_AREA)

    def test_unknown_category_fails_closed(self):
        unknown = self.priorities[0].model_copy(
            update={"category": "UNMAPPED_CATEGORY"}
        )
        with self.assertRaises(UnmappedConsultationCategoryError):
            project_consultation_review_areas(
                priorities=[unknown],
                priority_fingerprint=self.fingerprint,
            )

    def test_golden_rank_category_and_display_names_are_preserved(self):
        self.assertEqual(
            [
                (item.rank, item.category)
                for item in self.priorities
            ],
            [
                (1, "EXPORT_RECEIVABLE_PROTECTION"),
                (2, "FX_RISK_MANAGEMENT"),
                (3, "EXPORT_LIQUIDITY_REVIEW"),
            ],
        )
        self.assertEqual(self.packet.consultation_supporting_checks, [])
        self.assertEqual(
            [
                (
                    item.rank,
                    item.review_area_id,
                    item.display_name,
                )
                for item in self.packet.consultation_review_areas
            ],
            [
                (1, "COLLECTION_PROTECTION", "수출대금 회수 보호"),
                (2, "FX_MANAGEMENT", "환율 관리"),
                (
                    3,
                    "WORKING_CAPITAL_TRADE_FINANCE",
                    "무역금융·운영자금",
                ),
            ],
        )

    def test_reason_evidence_paths_and_binding_are_preserved(self):
        for priority, review_area in zip(
            self.priorities,
            self.packet.consultation_review_areas,
        ):
            self.assertEqual(review_area.rank, priority.rank)
            self.assertEqual(review_area.summary, priority.priority_reason)
            self.assertEqual(
                review_area.source_priority_reasons,
                [priority.priority_reason],
            )
            self.assertEqual(
                [item.model_dump() for item in review_area.evidence_items],
                [item.model_dump() for item in priority.numeric_rationale],
            )
            self.assertEqual(
                review_area.missing_information,
                priority.missing_information,
            )
            self.assertEqual(
                review_area.source_priority_fingerprint,
                self.fingerprint,
            )

    def test_projection_has_no_score_sort_or_product_fields(self):
        candidate_names = {
            item.name
            for item in (
                self.product_packet.official_candidate_shortlist.candidates
            )
        }
        presentation_items = (
            self.product_packet.consultation_review_areas
            + self.product_packet.consultation_supporting_checks
        )
        for presentation_item in presentation_items:
            payload = presentation_item.model_dump()
            for forbidden in (
                "score",
                "tier",
                "tie_break",
                "official_candidates",
                "product_id",
                "official_url",
            ):
                self.assertNotIn(forbidden, payload)
            serialized = presentation_item.model_dump_json()
            self.assertTrue(
                all(name not in serialized for name in candidate_names)
            )

    def test_products_do_not_change_projection_content(self):
        without_products = [
            item.model_copy(update={"official_candidates": []})
            for item in self.product_packet.consultation_priorities
        ]
        projected = project_consultation_review_areas(
            priorities=without_products,
            priority_fingerprint=(
                self.product_packet.consultation_priority_fingerprint
            ),
        )
        self.assertEqual(
            [item.model_dump() for item in projected],
            [
                item.model_dump()
                for item in self.product_packet.consultation_review_areas
            ],
        )

    def test_duplicate_area_keeps_first_rank_and_merges_only_top3(self):
        first = self.priorities[0].model_copy(
            update={
                "rank": 1,
                "category": "IMPORT_ADVANCE_PAYMENT_PROTECTION",
                "priority_reason": "첫 번째 기존 이유",
            }
        )
        second = self.priorities[1].model_copy(
            update={
                "rank": 2,
                "category": "DOCUMENTARY_CREDIT_TERMS_REVIEW",
                "priority_reason": "두 번째 기존 이유",
            }
        )
        third = self.priorities[2].model_copy(
            update={
                "rank": 3,
                "category": "FX_RISK_MANAGEMENT",
            }
        )
        projected = project_consultation_review_areas(
            priorities=[first, second, third],
            priority_fingerprint=self.fingerprint,
        )
        self.assertEqual(
            [(item.rank, item.review_area_id) for item in projected],
            [(1, "PAYMENT_TERMS"), (3, "FX_MANAGEMENT")],
        )
        self.assertEqual(
            projected[0].source_priority_categories,
            [
                "IMPORT_ADVANCE_PAYMENT_PROTECTION",
                "DOCUMENTARY_CREDIT_TERMS_REVIEW",
            ],
        )
        self.assertEqual(
            projected[0].source_priority_reasons,
            ["첫 번째 기존 이유", "두 번째 기존 이유"],
        )
        self.assertEqual(projected[0].summary, "첫 번째 기존 이유")

    def test_projection_rejects_out_of_order_or_duplicate_rank(self):
        with self.assertRaises(ValueError):
            project_consultation_review_areas(
                priorities=list(reversed(self.priorities)),
                priority_fingerprint=self.fingerprint,
            )

    def test_supporting_checks_preserve_source_rank_without_refill(self):
        first = self.priorities[0].model_copy(
            update={"rank": 1}
        )
        second = self.priorities[1].model_copy(
            update={
                "rank": 2,
                "category": "COUNTRY_MACRO_ENVIRONMENT_MONITORING",
            }
        )
        third = self.priorities[2].model_copy(
            update={
                "rank": 3,
                "category": "FX_RISK_MANAGEMENT",
            }
        )
        projection = project_consultation_presentation(
            priorities=[first, second, third],
            priority_fingerprint=self.fingerprint,
        )
        self.assertEqual(
            [
                (item.rank, item.review_area_id)
                for item in projection.review_areas
            ],
            [(1, "COLLECTION_PROTECTION"), (3, "FX_MANAGEMENT")],
        )
        self.assertEqual(
            [
                (
                    item.source_rank,
                    item.check_id,
                    item.display_name,
                )
                for item in projection.supporting_checks
            ],
            [
                (
                    2,
                    "COUNTRY_MACRO_MONITORING",
                    "거래국 거시환경 모니터링",
                )
            ],
        )
        self.assertNotIn(
            "POLICY_FINANCE",
            [item.review_area_id for item in projection.review_areas],
        )

    def test_supporting_check_preserves_reason_evidence_and_paths(self):
        priority = self.priorities[0].model_copy(
            update={"category": "ROUTINE_TRADE_REVIEW"}
        )
        projection = project_consultation_presentation(
            priorities=[priority],
            priority_fingerprint=self.fingerprint,
        )
        self.assertEqual(projection.review_areas, [])
        self.assertEqual(len(projection.supporting_checks), 1)
        supporting = projection.supporting_checks[0]
        self.assertEqual(supporting.display_name, "정기 거래 점검")
        self.assertEqual(supporting.source_rank, priority.rank)
        self.assertEqual(supporting.summary, priority.priority_reason)
        self.assertEqual(
            [item.model_dump() for item in supporting.evidence_items],
            [item.model_dump() for item in priority.numeric_rationale],
        )
        self.assertEqual(
            supporting.missing_information,
            priority.missing_information,
        )
        self.assertNotIn("환율 관리", supporting.model_dump_json())
        self.assertNotIn("정책자금 검토", supporting.model_dump_json())
        supporting_packet = self.packet.model_copy(
            update={
                "consultation_priorities": [priority],
                "consultation_review_areas": projection.review_areas,
                "consultation_supporting_checks": (
                    projection.supporting_checks
                ),
            }
        )
        markdown = _markdown(supporting_packet)
        primary_section = markdown.split(
            "## 2. 상담 우선순위",
            1,
        )[1].split("## 2A. 추가 확인사항", 1)[0]
        self.assertIn(
            "현재 입력에서 생성된 우선 상담 카드가 없습니다.",
            primary_section,
        )
        self.assertNotIn("정기 거래 점검", primary_section)
        self.assertIn("## 2A. 추가 확인사항", markdown)
        duplicate = self.priorities[1].model_copy(update={"rank": 1})
        with self.assertRaises(ValueError):
            project_consultation_review_areas(
                priorities=[self.priorities[0], duplicate],
                priority_fingerprint=self.fingerprint,
            )

    def test_packet_without_projection_field_remains_loadable(self):
        legacy = self.packet.model_dump()
        legacy.pop("consultation_review_areas")
        legacy.pop("consultation_supporting_checks", None)
        restored = ConsultationPacket.model_validate(legacy)
        self.assertEqual(restored.consultation_review_areas, [])
        self.assertEqual(restored.consultation_supporting_checks, [])
        self.assertEqual(
            [item.model_dump() for item in restored.consultation_priorities],
            [item.model_dump() for item in self.priorities],
        )


if __name__ == "__main__":
    unittest.main()
