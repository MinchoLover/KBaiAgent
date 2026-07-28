import unittest

from sample_data import sample_extraction
from schemas import TradeDocumentExtraction
from src.country_environment.assessment import (
    assess_country_trade_environment,
)
from src.document_intake.confirmation import (
    create_confirmation_record,
    discard_stale_evidence_after_review,
    validate_confirmation,
)
from src.domain.trade_risk_models import TradeSettlementRiskAssessment
from src.domain.country_environment_models import (
    CountryTradeEnvironmentAssessment,
    CountryTradeEnvironmentInput,
)
from src.ui.state import (
    clear_confirmation_and_later,
    clear_country_environment_and_related,
    clear_downstream,
    clear_trade_risk_and_related,
)
from src.ui.components import validation_issue_copy
from validators import apply_deterministic_review_state


class ReviewEvidenceSafetyTests(unittest.TestCase):
    def test_internal_evidence_code_has_plain_language_ui_copy(self):
        self.assertEqual(
            validation_issue_copy(
                "amount_due",
                "EVIDENCE_VALUE_MISMATCH",
            ),
            "실제 결제금액: 원문 근거와 현재 입력값이 서로 다릅니다.",
        )

    def test_user_edit_drops_model_evidence_and_requires_explicit_override(self):
        initial = sample_extraction("BUYER")
        edited = initial.model_copy(
            update={"seller_name": "Verified Vendor Ltd."}
        )

        evidence_safe = discard_stale_evidence_after_review(
            initial,
            edited,
        )
        self.assertFalse(
            any(
                item.field == "seller_name"
                for item in evidence_safe.evidence
            )
        )
        self.assertTrue(
            any(
                item.field == "buyer_name"
                for item in evidence_safe.evidence
            )
        )

        reviewed, validation = apply_deterministic_review_state(
            evidence_safe,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertTrue(
            any(
                item.code == "MISSING_CORE_EVIDENCE"
                and item.field == "seller_name"
                for item in validation.issues
            )
        )
        self.assertFalse(
            any(
                item.field == "seller_name" for item in reviewed.evidence
            )
        )

        record = create_confirmation_record(
            original=initial,
            confirmed=reviewed,
            confirmed_due_date="2026-10-18",
            company_role_confirmed=True,
            trade_type_confirmed=True,
            currency_confirmed=True,
            amount_due_confirmed=True,
            due_date_confirmed=True,
            source_filename="invoice.png",
            source_sha256="e" * 64,
            company_country="KR",
            evidence_override_fields=["seller_name"],
            confirmed_by="regression-test",
            confirmed_at="2026-07-27T12:00:00+09:00",
        )
        confirmed_validation = validate_confirmation(
            extraction=reviewed,
            record=record,
            company_country="KR",
        )
        self.assertTrue(confirmed_validation.stage2_allowed)
        self.assertTrue(record.checks.user_confirmed_override)
        self.assertEqual(
            record.checks.user_confirmed_override_fields,
            ["seller_name"],
        )

    def test_review_clear_invalidates_confirmation_and_workflow_state(self):
        state = {
            "extraction": {"document_type": "SALES_CONTRACT"},
            "extraction_validation": {"validation_pass": True},
            "confirmation": {"checks": {}},
            "confirmation_validation": {"stage2_allowed": True},
            "stage0_output": {"source": {}},
            "stage2_document_input": {"source": {}},
            "stage2_result": {"result": "stale"},
            "trade_risk_confirmation": {"risk": "stale"},
            "trade_risk_assessment": {"priority": "stale"},
            "country_environment_input": {"country": "US"},
            "country_environment_assessment": {"priority": "stale"},
            "country_environment_trace": {"country": "US"},
            "workflow_state": {"case_id": "stale"},
            "review_audit_trail": [{"before": "kept"}],
            "confirm_currency_widget": True,
        }
        clear_confirmation_and_later(state)
        self.assertIn("extraction", state)
        self.assertIn("extraction_validation", state)
        self.assertIn("review_audit_trail", state)
        for key in (
            "confirmation",
            "confirmation_validation",
            "stage0_output",
            "stage2_document_input",
            "stage2_result",
            "trade_risk_confirmation",
            "trade_risk_assessment",
            "country_environment_input",
            "country_environment_assessment",
            "country_environment_trace",
            "workflow_state",
            "confirm_currency_widget",
        ):
            self.assertNotIn(key, state)

    def test_stage2_recalculation_preserves_independent_trade_risk(self):
        state = {
            "stage2_input": {"cash": "old"},
            "stage2_result": {"cash": "old"},
            "trade_risk_confirmation": {"risk": "confirmed"},
            "trade_risk_assessment": {"priority": "HIGH_REVIEW"},
            "country_environment_assessment": {
                "priority": "STANDARD_REVIEW"
            },
            "stage3_result": {"hedge": "old"},
            "consultation_packet": {"packet": "old"},
        }

        clear_downstream(state, 2)

        self.assertIn("trade_risk_confirmation", state)
        self.assertIn("trade_risk_assessment", state)
        self.assertIn("country_environment_assessment", state)
        for key in (
            "stage2_input",
            "stage2_result",
            "stage3_result",
            "consultation_packet",
        ):
            self.assertNotIn(key, state)

    def test_trade_risk_change_only_clears_derived_shared_outputs(self):
        state = {
            "stage1_load": {"market": "kept"},
            "stage2_input": {"cash": "kept"},
            "stage2_result": {"cash": "kept"},
            "stage3_result": {"hedge": "kept"},
            "stage4_result": {"products": "kept"},
            "official_candidate_shortlist": {
                "products": "stale"
            },
            "trade_risk_confirmation": {"risk": "stale"},
            "trade_risk_assessment": {"priority": "stale"},
            "country_environment_input": {"country": "US"},
            "country_environment_assessment": {"priority": "stale"},
            "country_environment_trace": {"country": "US"},
            "consultation_topics": [{"topic": "stale"}],
            "consultation_packet": {"packet": "stale"},
            "report_result": {"report": "stale"},
        }

        clear_trade_risk_and_related(state)

        for key in (
            "stage1_load",
            "stage2_input",
            "stage2_result",
            "stage3_result",
            "stage4_result",
        ):
            self.assertIn(key, state)
        for key in (
            "trade_risk_confirmation",
            "trade_risk_assessment",
            "country_environment_input",
            "country_environment_assessment",
            "country_environment_trace",
            "consultation_topics",
            "official_candidate_shortlist",
            "consultation_packet",
            "report_result",
        ):
            self.assertNotIn(key, state)

    def test_country_change_preserves_stage_results_and_trade_risk(self):
        state = {
            "stage1_load": {"market": "kept"},
            "stage2_result": {"cash": "kept"},
            "stage3_result": {"hedge": "kept"},
            "stage4_result": {"products": "kept"},
            "official_candidate_shortlist": {"products": "kept"},
            "trade_risk_assessment": {"priority": "kept"},
            "country_environment_input": {"country": "US"},
            "country_environment_assessment": {"priority": "stale"},
            "country_environment_trace": {"country": "US"},
            "consultation_topics": [{"topic": "stale"}],
            "consultation_packet": {"packet": "stale"},
            "report_result": {"report": "stale"},
        }

        clear_country_environment_and_related(state)

        for key in (
            "stage1_load",
            "stage2_result",
            "stage3_result",
            "stage4_result",
            "official_candidate_shortlist",
            "trade_risk_assessment",
        ):
            self.assertIn(key, state)
        for key in (
            "country_environment_input",
            "country_environment_assessment",
            "country_environment_trace",
            "consultation_topics",
            "consultation_packet",
            "report_result",
        ):
            self.assertNotIn(key, state)


class StreamlitReviewEvidenceTests(unittest.TestCase):
    def test_demo_exposes_trade_risk_without_ui_exception(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=20).run()
        demo = next(
            button
            for button in app.button
            if button.label == "수입기업 대표 데모"
        )
        demo.click().run()

        self.assertEqual(len(app.exception), 0)
        self.assertIn("trade_risk_confirmation", app.session_state)
        self.assertIn("trade_risk_assessment", app.session_state)
        self.assertIn("country_environment_input", app.session_state)
        self.assertIn("country_environment_assessment", app.session_state)
        self.assertIn("country_environment_trace", app.session_state)
        assessment = TradeSettlementRiskAssessment.model_validate(
            app.session_state["trade_risk_assessment"]
        )
        self.assertEqual(assessment.review_priority, "HIGH_REVIEW")
        self.assertIn(
            "IMPORT_ADVANCE_PAYMENT_PROTECTION",
            {
                item["category"]
                for item in app.session_state["consultation_topics"]
            },
        )
        self.assertIn(
            "## 4. 거래·결제조건 위험",
            app.session_state["consultation_packet"]["markdown"],
        )
        country_assessment = CountryTradeEnvironmentAssessment.model_validate(
            app.session_state["country_environment_assessment"]
        )
        self.assertEqual(country_assessment.country, "US")
        self.assertEqual(
            country_assessment.oecd_payment_transfer.status,
            "HIGH_INCOME_OECD_UNCLASSIFIED",
        )
        self.assertIn(
            "## 4A. 국가·무역환경 검토",
            app.session_state["consultation_packet"]["markdown"],
        )
        self.assertIn(
            "official_candidate_shortlist",
            app.session_state,
        )
        self.assertLessEqual(
            len(
                app.session_state[
                    "official_candidate_shortlist"
                ]["candidates"]
            ),
            3,
        )
        self.assertIn("report_result", app.session_state)
        self.assertIn(
            "consultation",
            app.session_state["report_result"]["report_json"],
        )
        self.assertIn(
            "수입 선지급·계약이행 위험",
            app.session_state["report_result"]["markdown"],
        )
        self.assertIn(
            "국가·무역환경 검토",
            app.session_state["report_result"]["markdown"],
        )
        visible_text = " ".join(
            item.value for item in app.markdown
        )
        self.assertIn("국가·무역환경 검토", visible_text)
        self.assertIn("고소득 OECD 회원국 미분류", visible_text)
        stage3_before = app.session_state["stage3_result"]

        relationship = next(
            widget
            for widget in app.selectbox
            if widget.key == "trade_risk_relationship_widget"
        )
        relationship.set_value("EXISTING")
        confirmation = next(
            widget
            for widget in app.checkbox
            if widget.key == "trade_risk_confirm_widget"
        )
        confirmation.set_value(True)
        submit = next(
            button
            for button in app.button
            if button.label == "결제·회수 위험 확인"
        )
        submit.click().run()

        self.assertEqual(len(app.exception), 0)
        updated = TradeSettlementRiskAssessment.model_validate(
            app.session_state["trade_risk_assessment"]
        )
        self.assertEqual(updated.review_priority, "ELEVATED_REVIEW")
        self.assertEqual(app.session_state["stage3_result"], stage3_before)

    def test_information_insufficient_country_ui_is_explicit(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=20).run()
        demo = next(
            button
            for button in app.button
            if button.label == "수입기업 대표 데모"
        )
        demo.click().run()
        current = CountryTradeEnvironmentInput.model_validate(
            app.session_state["country_environment_input"]
        )
        unavailable = assess_country_trade_environment(
            current.model_copy(
                update={"counterparty_country": "CA"}
            )
        )
        app.session_state["country_environment_assessment"] = (
            unavailable.model_dump()
        )
        app.run()

        self.assertEqual(len(app.exception), 0)
        visible_text = " ".join(
            item.value for item in app.markdown
        )
        warnings = " ".join(item.value for item in app.warning)
        self.assertIn("정보 부족", visible_text)
        self.assertIn(
            "검증된 OECD 원자료를 확인할 수 없습니다",
            warnings,
        )

    def test_review_edit_clears_evidence_and_prior_confirmation_state(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=20).run()
        demo = next(
            button
            for button in app.button
            if button.label == "수입기업 대표 데모"
        )
        demo.click().run()
        self.assertIn("confirmation", app.session_state)
        self.assertIn("workflow_state", app.session_state)

        seller_name = next(
            widget
            for widget in app.text_input
            if widget.key == "review_seller_name_widget"
        )
        seller_name.set_value("Verified Vendor Ltd.")
        review = next(
            button
            for button in app.button
            if button.label == "수정 내용 저장 및 다시 검증"
        )
        review.click().run()
        self.assertEqual(len(app.exception), 0)

        extraction = TradeDocumentExtraction.model_validate(
            app.session_state["extraction"]
        )
        self.assertEqual(extraction.seller_name, "Verified Vendor Ltd.")
        self.assertFalse(
            any(
                item.field == "seller_name" for item in extraction.evidence
            )
        )
        for key in (
            "confirmation",
            "confirmation_validation",
            "stage0_output",
            "stage2_document_input",
            "stage2_result",
        ):
            self.assertNotIn(key, app.session_state)


if __name__ == "__main__":
    unittest.main()
