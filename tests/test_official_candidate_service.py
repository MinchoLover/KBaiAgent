import unittest

from pydantic import ValidationError

from src.application.consultation_service import build_decision_support
from src.application.official_candidate_service import (
    MAX_OFFICIAL_CANDIDATES,
    build_official_candidate_query,
    shortlist_official_candidates,
)
from src.demo import run_decision_support_demo
from src.domain.product_models import (
    OfficialCandidateShortlist,
    Stage4Result,
)
from src.stage4.local_kb import load_official_kb


class OfficialCandidateServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.import_demo = run_decision_support_demo("BUYER")
        cls.export_demo = run_decision_support_demo("SELLER")

    def test_official_snapshot_has_direction_specific_protection(self):
        records = load_official_kb()
        categories = {item.category for item in records}
        self.assertIn(
            "IMPORT_ADVANCE_PAYMENT_INSURANCE",
            categories,
        )
        self.assertIn("EXPORT_CREDIT_INSURANCE", categories)

    def test_query_is_deterministic_and_deduplicated(self):
        topics = self.import_demo["consultation_topics"]
        first = build_official_candidate_query(
            consultation_topics=topics,
            additional_terms=["선물환", "선물환"],
        )
        second = build_official_candidate_query(
            consultation_topics=topics,
            additional_terms=["선물환", "선물환"],
        )
        self.assertEqual(first, second)
        self.assertEqual(first.split().count("선물환"), 1)
        self.assertIn("수입보험", first)

    def test_import_protection_candidate_is_connected(self):
        shortlist = self.import_demo[
            "official_candidate_shortlist"
        ]
        self.assertLessEqual(
            len(shortlist.candidates),
            MAX_OFFICIAL_CANDIDATES,
        )
        candidate = shortlist.candidates[0]
        self.assertEqual(
            candidate.category,
            "IMPORT_ADVANCE_PAYMENT_INSURANCE",
        )
        self.assertIn(
            "IMPORT_ADVANCE_PAYMENT_PROTECTION",
            candidate.matched_consultation_categories,
        )
        self.assertEqual(candidate.eligibility, "unknown")
        self.assertEqual(
            candidate.approval_status,
            "consultation_required",
        )

    def test_export_receivable_candidate_is_connected(self):
        shortlist = self.export_demo[
            "official_candidate_shortlist"
        ]
        candidate = shortlist.candidates[0]
        self.assertEqual(
            candidate.category,
            "EXPORT_CREDIT_INSURANCE",
        )
        self.assertIn(
            "EXPORT_RECEIVABLE_PROTECTION",
            candidate.matched_consultation_categories,
        )

    def test_unmatched_category_stays_empty_without_invention(self):
        source = self.import_demo["stage4"]
        empty = Stage4Result(
            mode=source.mode,
            query=source.query,
            candidates=[],
        )
        protection_topic = next(
            item
            for item in self.import_demo["consultation_topics"]
            if item.category
            == "IMPORT_ADVANCE_PAYMENT_PROTECTION"
        )
        shortlist = shortlist_official_candidates(
            stage4_result=empty,
            trade_type="IMPORT",
            consultation_topics=[protection_topic],
        )
        self.assertEqual(shortlist.candidates, [])
        self.assertEqual(
            shortlist.unmatched_consultation_categories,
            ["IMPORT_ADVANCE_PAYMENT_PROTECTION"],
        )
        self.assertTrue(
            any(
                "상품을 만들지 않았습니다" in warning
                for warning in shortlist.warnings
            )
        )

    def test_unofficial_source_is_filtered(self):
        original = self.import_demo[
            "official_candidate_shortlist"
        ].candidates[0]
        unsafe_source = original.source.model_copy(
            update={"url": "https://example.com/not-official"}
        )
        unsafe_candidate = original.model_copy(
            update={"source": unsafe_source}
        )
        raw = Stage4Result(
            mode="OFFLINE_KB",
            query="수입보험",
            candidates=[unsafe_candidate],
        )
        topic = next(
            item
            for item in self.import_demo["consultation_topics"]
            if item.category
            == "IMPORT_ADVANCE_PAYMENT_PROTECTION"
        )
        shortlist = shortlist_official_candidates(
            stage4_result=raw,
            trade_type="IMPORT",
            consultation_topics=[topic],
        )
        self.assertEqual(shortlist.candidates, [])
        self.assertTrue(
            any("제외했습니다" in item for item in shortlist.warnings)
        )

    def test_wrong_trade_direction_is_filtered(self):
        original = self.import_demo[
            "official_candidate_shortlist"
        ].candidates[0]
        wrong_direction = original.model_copy(
            update={"trade_types": ["EXPORT"]}
        )
        raw = Stage4Result(
            mode="OFFLINE_KB",
            query="수입보험",
            candidates=[wrong_direction],
        )
        topic = next(
            item
            for item in self.import_demo["consultation_topics"]
            if item.category
            == "IMPORT_ADVANCE_PAYMENT_PROTECTION"
        )
        shortlist = shortlist_official_candidates(
            stage4_result=raw,
            trade_type="IMPORT",
            consultation_topics=[topic],
        )
        self.assertEqual(shortlist.candidates, [])

    def test_model_and_service_reject_more_than_three(self):
        source = self.import_demo[
            "official_candidate_shortlist"
        ]
        with self.assertRaises(ValueError):
            shortlist_official_candidates(
                stage4_result=self.import_demo["stage4"],
                trade_type="IMPORT",
                consultation_topics=(
                    self.import_demo["consultation_topics"]
                ),
                limit=4,
            )
        with self.assertRaises(ValidationError):
            OfficialCandidateShortlist(
                trade_type="IMPORT",
                source_mode="OFFLINE_KB",
                query="test",
                candidates=[source.candidates[0]] * 4,
            )

    def test_packet_binds_and_renders_shortlist(self):
        packet = self.import_demo["consultation_packet"]
        shortlist = self.import_demo[
            "official_candidate_shortlist"
        ]
        self.assertEqual(
            packet.packet.official_candidate_shortlist,
            shortlist,
        )
        self.assertIn(
            "## 6. 공식 출처 상담 후보",
            packet.markdown,
        )
        self.assertIn(
            shortlist.candidates[0].source.url,
            packet.markdown,
        )
        self.assertIn("후보는 최대 3개", packet.markdown)

    def test_packet_hash_changes_with_official_source_binding(self):
        shortlist = self.import_demo[
            "official_candidate_shortlist"
        ]
        first = shortlist.candidates[0]
        changed_source = first.source.model_copy(
            update={"verified_at": "2026-07-30"}
        )
        changed_candidate = first.model_copy(
            update={"source": changed_source}
        )
        changed_shortlist = shortlist.model_copy(
            update={
                "candidates": (
                    [changed_candidate] + shortlist.candidates[1:]
                )
            }
        )
        rebuilt = build_decision_support(
            case_id=self.import_demo["workflow_state"].case_id,
            extraction=self.import_demo["extraction"],
            confirmation=self.import_demo["confirmation"],
            stage1=self.import_demo["stage1"],
            stage2_input=self.import_demo["stage2_input"],
            stage2_result=self.import_demo["stage2"],
            trade_settlement_risk=self.import_demo[
                "trade_risk_assessment"
            ],
            official_candidate_shortlist=changed_shortlist,
            generated_at="2026-07-23T09:00:00+09:00",
        )
        self.assertNotEqual(
            rebuilt.consultation_packet.packet.input_hash,
            self.import_demo[
                "consultation_packet"
            ].packet.input_hash,
        )


if __name__ == "__main__":
    unittest.main()
