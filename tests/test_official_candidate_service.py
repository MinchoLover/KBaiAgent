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
    ProductRecord,
    Stage4Result,
)
from src.stage4.local_kb import (
    CATALOGUE_ALLOWED_DOMAINS,
    active_official_catalogue,
    load_official_kb,
    search_offline_kb,
)
from src.stage4.official_search import is_official_url


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

    def test_catalogue_ids_and_active_sources_are_validated(self):
        records = load_official_kb()
        self.assertEqual(
            len({item.product_id for item in records}),
            len(records),
        )
        active = active_official_catalogue()
        self.assertTrue(active)
        for item in active:
            self.assertEqual(item.catalogue_id, item.product_id)
            self.assertEqual(item.source_status, "VERIFIED")
            self.assertTrue(item.official_name)
            self.assertTrue(item.candidate_family)
            self.assertTrue(item.source.verified_at)
            self.assertTrue(
                is_official_url(
                    item.source.url,
                    CATALOGUE_ALLOWED_DOMAINS,
                )
            )

    def test_expired_emergency_funding_is_not_active(self):
        by_id = {item.product_id: item for item in load_official_kb()}
        expired = by_id["kosmes_trade_risk_emergency_funding"]
        self.assertFalse(expired.active)
        self.assertEqual(expired.source_status, "EXPIRED")
        self.assertNotIn(
            expired.product_id,
            {item.product_id for item in active_official_catalogue()},
        )

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

    def test_export_shortlist_uses_declared_product_type_order(self):
        shortlist = self.export_demo[
            "official_candidate_shortlist"
        ]
        self.assertEqual(
            [
                (item.institution, item.name)
                for item in shortlist.candidates
            ],
            [
                ("한국무역보험공사", "단기수출보험 검토"),
                ("KB국민은행", "KB Star FX 선물환·외환스왑 상담"),
                ("한국무역보험공사", "환변동보험 검토"),
            ],
        )
        self.assertEqual(
            len(
                {
                    item.candidate_family
                    for item in shortlist.candidates
                }
            ),
            len(shortlist.candidates),
        )
        self.assertTrue(
            all(item.catalogue_id for item in shortlist.candidates)
        )

    def test_golden_catalogue_descriptions_keep_consultation_boundaries(self):
        by_id = {item.product_id: item for item in load_official_kb()}
        golden_ids = [
            "ksure_short_term_export_insurance",
            "kb_star_fx_forward",
            "ksure_fx_insurance_general",
        ]
        self.assertEqual(
            [
                item.product_id
                for item in self.export_demo[
                    "official_candidate_shortlist"
                ].candidates
            ],
            golden_ids,
        )
        self.assertTrue(all(by_id[item].active for item in golden_ids))

        insurance = by_id["ksure_short_term_export_insurance"]
        self.assertEqual(insurance.official_name, "단기수출보험(선적후)")
        self.assertIn("결제기간 2년 이하", " ".join(insurance.key_conditions))
        self.assertIn("한도 심사", insurance.summary)
        self.assertIn("인수 절차", insurance.summary)

        kb_star_fx = by_id["kb_star_fx_forward"]
        self.assertEqual(kb_star_fx.official_name, "KB Star FX")
        self.assertEqual(
            kb_star_fx.display_name,
            "KB Star FX 선물환·외환스왑 상담",
        )
        self.assertTrue(kb_star_fx.branch_limit_review_required)
        self.assertFalse(kb_star_fx.customer_rate_available)
        self.assertFalse(kb_star_fx.live_quote_available)
        self.assertIn("선물환·외환스왑", kb_star_fx.summary)
        self.assertNotIn("KB Star FX 기준환율", kb_star_fx.model_dump_json())

    def test_fx_insurance_variants_never_become_automatic_candidates(self):
        records = load_official_kb()
        by_id = {item.product_id: item for item in records}
        product = by_id["ksure_fx_insurance_general"]
        self.assertTrue(product.has_variants)
        self.assertFalse(product.auto_select_variant)
        self.assertTrue(product.variant_consultation_required)
        self.assertEqual(
            [item.official_name for item in product.variants],
            [
                "환변동보험(선물환) 일반형",
                "부분보장 옵션형",
                "완전보장 옵션형(조기결제형)",
                "완전보장 옵션형(조기결제 불가형)",
            ],
        )
        variant_ids = {item.variant_id for item in product.variants}
        self.assertTrue(variant_ids.isdisjoint(by_id))
        self.assertEqual(
            [
                item.product_id
                for item in self.export_demo[
                    "official_candidate_shortlist"
                ].candidates
            ],
            [
                "ksure_short_term_export_insurance",
                "kb_star_fx_forward",
                "ksure_fx_insurance_general",
            ],
        )

    def test_legacy_product_json_defaults_new_boundaries_safely(self):
        legacy = ProductRecord.model_validate(
            {
                "product_id": "legacy_product",
                "name": "기존 상담 후보",
                "institution": "기존 기관",
                "category": "LEGACY",
                "summary": "기존 JSON 계약",
                "source": {
                    "title": "기존 공식 출처",
                    "url": "https://www.ksure.or.kr/legacy",
                    "verified_at": "2026-08-02",
                    "evidence_summary": "기존 필드만 포함",
                },
            }
        )
        self.assertFalse(legacy.has_variants)
        self.assertFalse(legacy.auto_select_variant)
        self.assertEqual(legacy.variants, [])
        self.assertIsNone(legacy.live_quote_available)
        self.assertEqual(legacy.required_any_signals, [])
        self.assertTrue(legacy.financial_shortlist_eligible)
        self.assertIsNone(legacy.current_application_status)
        legacy_auxiliary_payload = legacy.model_dump(mode="json")
        legacy_auxiliary_payload["product_type"] = "AUXILIARY_SERVICE"
        legacy_auxiliary_payload.pop("financial_shortlist_eligible")
        legacy_auxiliary_payload.pop("required_any_signals")
        legacy_auxiliary_payload.pop("current_application_status")
        legacy_auxiliary = ProductRecord.model_validate(
            legacy_auxiliary_payload
        )
        self.assertTrue(legacy_auxiliary.financial_shortlist_eligible)

    def test_verified_boundary_items_keep_stable_catalogue_ids(self):
        records = load_official_kb()
        by_id = {item.product_id: item for item in records}
        target_ids = {
            "ksure_export_credit_guarantee_pre_shipment",
            "ksure_export_credit_guarantee_post_shipment",
            "ksure_export_credit_guarantee_purchase",
            "ksure_export_credit_guarantee_comprehensive_purchase",
            "kb_non_lc_export_bill_purchase",
            "ksure_foreign_company_credit_investigation",
            "kosmes_export_funding",
        }
        self.assertEqual(len(records), 16)
        self.assertTrue(target_ids.issubset(by_id))
        for product_id in target_ids:
            self.assertEqual(by_id[product_id].catalogue_id, product_id)
            self.assertTrue(by_id[product_id].active)
            self.assertEqual(by_id[product_id].source_status, "VERIFIED")

    def test_export_guarantees_require_their_distinct_confirmed_signals(self):
        by_id = {item.product_id: item for item in load_official_kb()}
        pre = by_id["ksure_export_credit_guarantee_pre_shipment"]
        self.assertIn(
            "EXPORT_PRE_SHIPMENT_FUNDING_NEED",
            pre.required_signals,
        )
        self.assertIn("BANK_FINANCING_INTENT", pre.required_signals)
        self.assertIn("MANUFACTURING_FUNDING_USE", pre.required_any_signals)

        post = by_id["ksure_export_credit_guarantee_post_shipment"]
        self.assertIn("SHIPMENT_COMPLETED", post.required_signals)
        self.assertIn(
            "RECEIVABLE_PURCHASE_OR_NEGO_INTENT",
            post.required_signals,
        )
        self.assertIn(
            "SHORT_TERM_EXPORT_INSURANCE_LINKAGE_REVIEW",
            post.required_signals,
        )
        self.assertIn("단기수출보험 연계가입 필수", post.key_conditions)

        purchase = by_id["ksure_export_credit_guarantee_purchase"]
        self.assertIn("NON_LC_CONFIRMED", purchase.required_signals)
        self.assertIn(
            "REPAYMENT_RESPONSIBILITY_ACKNOWLEDGED",
            purchase.required_signals,
        )
        self.assertIn(
            "최종 상환책임은 수출자",
            " ".join(purchase.limitations),
        )

        comprehensive = by_id[
            "ksure_export_credit_guarantee_comprehensive_purchase"
        ]
        self.assertIn(
            "RECURRING_EXPORT_TRANSACTIONS",
            comprehensive.required_signals,
        )
        self.assertIn("MULTIPLE_BUYERS", comprehensive.required_signals)
        self.assertIn("SINGLE_TRANSACTION_ONLY", comprehensive.excluded_signals)

    def test_bank_purchase_and_auxiliary_service_boundaries_are_explicit(self):
        by_id = {item.product_id: item for item in load_official_kb()}
        bank = by_id["kb_non_lc_export_bill_purchase"]
        for signal in (
            "SHIPMENT_COMPLETED",
            "NON_LC_CONFIRMED",
            "ELIGIBLE_NON_LC_PAYMENT_METHOD",
            "EARLY_CASH_CONVERSION_INTENT",
            "BANK_RECEIVABLE_PURCHASE_INTENT",
        ):
            self.assertIn(signal, bank.required_signals)
        self.assertIn("D/P·D/A·O/A", " ".join(bank.prerequisite_information))
        self.assertIn("K-SURE 보증서 발급", " ".join(bank.limitations))

        service = by_id["ksure_foreign_company_credit_investigation"]
        self.assertEqual(service.product_type, "AUXILIARY_SERVICE")
        self.assertFalse(service.financial_shortlist_eligible)
        self.assertEqual(
            set(service.required_any_signals),
            {
                "COUNTERPARTY_NEW",
                "COUNTERPARTY_CREDIT_INFORMATION_INSUFFICIENT",
                "BUYER_CREDIT_INVESTIGATION_REQUIRED",
            },
        )
        self.assertIn("통상 2~3주", service.summary)

        candidate = next(
            item
            for item in search_offline_kb(
                query="국외기업 신용조사",
                trade_type="EXPORT",
            ).candidates
            if item.product_id
            == "ksure_foreign_company_credit_investigation"
        ).model_copy(
            update={
                "matched_consultation_categories": [
                    "EXPORT_RECEIVABLE_PROTECTION"
                ]
            }
        )
        with self.assertRaises(ValidationError):
            OfficialCandidateShortlist(
                trade_type="EXPORT",
                source_mode="OFFLINE_KB",
                query="신용조사",
                candidates=[candidate],
            )

    def test_policy_funding_requires_all_explicit_domain_signals(self):
        by_id = {item.product_id: item for item in load_official_kb()}
        policy = by_id["kosmes_export_funding"]
        self.assertEqual(policy.product_type, "POLICY_LOAN")
        self.assertEqual(policy.current_application_status, "UNKNOWN")
        for signal in (
            "COMPANY_SME_STATUS_CONFIRMED",
            "EXPORT_EXPANSION_OR_MARKET_ENTRY_PURPOSE",
            "EXPLICIT_POLICY_FINANCE_REVIEW",
            "PRODUCTION_FACILITY_OR_WORKING_CAPITAL_NEED",
        ):
            self.assertIn(signal, policy.required_signals)
        self.assertIn(
            "시장접근 추가 확인사항",
            " ".join(policy.limitations),
        )
        self.assertIn(
            "수출실적이 확인되지 않으면 세부 유형을 자동 선택하지 않음",
            policy.key_conditions,
        )

    def test_new_catalogue_items_do_not_enter_golden_shortlist(self):
        product_ids = {
            item.product_id
            for item in self.export_demo[
                "official_candidate_shortlist"
            ].candidates
        }
        self.assertTrue(
            {
                "ksure_export_credit_guarantee_pre_shipment",
                "ksure_export_credit_guarantee_post_shipment",
                "ksure_export_credit_guarantee_purchase",
                "kb_non_lc_export_bill_purchase",
                "ksure_foreign_company_credit_investigation",
                "kosmes_export_funding",
            }.isdisjoint(product_ids)
        )

    def test_policy_funding_is_not_selected_without_policy_review(self):
        for demo in (self.import_demo, self.export_demo):
            self.assertNotIn(
                "kosmes_export_funding",
                {
                    item.product_id
                    for item in demo[
                        "official_candidate_shortlist"
                    ].candidates
                },
            )

    def test_supporting_check_does_not_create_product_candidate(self):
        supporting_topic = next(
            item
            for item in self.export_demo["consultation_topics"]
            if item.category == "COUNTRY_MACRO_ENVIRONMENT_MONITORING"
        )
        shortlist = shortlist_official_candidates(
            stage4_result=self.export_demo["stage4"],
            trade_type="EXPORT",
            consultation_topics=[supporting_topic],
        )
        self.assertEqual(shortlist.candidates, [])

    def test_pre_shipment_guarantee_needs_explicit_funding_signal(self):
        liquidity_topic = next(
            item
            for item in self.export_demo["consultation_topics"]
            if item.category == "EXPORT_LIQUIDITY_REVIEW"
        )
        shortlist = shortlist_official_candidates(
            stage4_result=self.export_demo["stage4"],
            trade_type="EXPORT",
            consultation_topics=[liquidity_topic],
        )
        self.assertNotIn(
            "ksure_export_credit_guarantee_pre_shipment",
            {item.product_id for item in shortlist.candidates},
        )

    def test_unknown_insurance_status_defers_instead_of_assuming_absent(self):
        packet = self.export_demo["consultation_packet"].packet
        protection = packet.protection_summary.model_copy(
            update={"credit_insurance": "UNKNOWN"}
        )
        changed_packet = packet.model_copy(
            update={"protection_summary": protection}
        )
        shortlist = shortlist_official_candidates(
            stage4_result=self.export_demo["stage4"],
            trade_type="EXPORT",
            consultation_topics=self.export_demo["consultation_topics"],
            consultation_packet=changed_packet,
        )
        self.assertIn(
            "ksure_short_term_export_insurance",
            shortlist.deferred_catalogue_ids,
        )
        self.assertNotIn(
            "ksure_short_term_export_insurance",
            {item.product_id for item in shortlist.candidates},
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

    def test_catalogue_metadata_tampering_is_filtered(self):
        original = self.export_demo[
            "official_candidate_shortlist"
        ].candidates[0]
        tampered = original.model_copy(
            update={"name": "AI가 만든 임의 상품명"}
        )
        raw = Stage4Result(
            mode="OFFICIAL_WEB_SEARCH",
            query="수출보험",
            candidates=[tampered],
        )
        topic = next(
            item
            for item in self.export_demo["consultation_topics"]
            if item.category == "EXPORT_RECEIVABLE_PROTECTION"
        )
        shortlist = shortlist_official_candidates(
            stage4_result=raw,
            trade_type="EXPORT",
            consultation_topics=[topic],
        )
        self.assertEqual(shortlist.candidates, [])

    def test_official_web_result_without_catalogue_id_is_filtered(self):
        original = self.export_demo[
            "official_candidate_shortlist"
        ].candidates[0]
        web_candidate = original.model_copy(
            update={
                "product_id": "web_0",
                "catalogue_id": None,
                "category": "OFFICIAL_WEB_RESULT",
            }
        )
        raw = Stage4Result(
            mode="OFFICIAL_WEB_SEARCH",
            query="수출보험",
            candidates=[web_candidate],
        )
        topic = next(
            item
            for item in self.export_demo["consultation_topics"]
            if item.category == "EXPORT_RECEIVABLE_PROTECTION"
        )
        shortlist = shortlist_official_candidates(
            stage4_result=raw,
            trade_type="EXPORT",
            consultation_topics=[topic],
        )
        self.assertEqual(shortlist.candidates, [])

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

    def test_legacy_shortlist_json_remains_loadable(self):
        current = self.export_demo[
            "official_candidate_shortlist"
        ].model_dump(mode="json")
        current["selection_policy"] = "CONSULTATION_CATEGORY_MATCH"
        current.pop("deferred_catalogue_ids", None)
        for candidate in current["candidates"]:
            candidate.pop("catalogue_id", None)
            candidate.pop("official_name", None)
            candidate.pop("display_name", None)
            candidate.pop("candidate_family", None)
            candidate.pop("source_status", None)
            candidate.pop("active", None)
            candidate.pop("matched_review_areas", None)
            candidate.pop("selection_reasons", None)
        loaded = OfficialCandidateShortlist.model_validate(current)
        self.assertEqual(
            loaded.selection_policy,
            "CONSULTATION_CATEGORY_MATCH",
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
