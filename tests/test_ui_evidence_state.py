import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

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
from src.domain.consultation_models import ConsultationPacketResult
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
from src.ui.components import (
    SCHEDULED_EXPOSURE_WARNING,
    amount_due_user_label,
    consultation_priority_reason_copy,
    consultation_rationale_label,
    consultation_status_label,
    validation_issue_copy,
)
from tests.golden_consultation_fixture import (
    build_golden_consultation_fixture,
)
from validators import apply_deterministic_review_state


class ReviewEvidenceSafetyTests(unittest.TestCase):
    def test_consultation_display_copy_hides_internal_rule_terms(self):
        self.assertEqual(
            consultation_priority_reason_copy(
                "기존 LOSS_LIMIT_EXCEEDED finding과 허용손실을 "
                "함께 확인합니다."
            ),
            "기존 허용손실 초과 신호와 허용손실을 함께 확인합니다.",
        )
        self.assertEqual(
            consultation_rationale_label("trade review"),
            "거래 검토 우선도",
        )
        self.assertEqual(
            consultation_rationale_label("buffer shortfall"),
            "목표 현금 버퍼 부족",
        )
        self.assertEqual(
            consultation_status_label("HIGH_REVIEW"),
            "높은 검토 우선도",
        )

    def test_internal_evidence_code_has_plain_language_ui_copy(self):
        self.assertEqual(
            validation_issue_copy(
                "amount_due",
                "EVIDENCE_VALUE_MISMATCH",
            ),
            "분석 대상 예정 결제액: 원문 근거와 현재 입력값이 서로 다릅니다.",
        )

    def test_amount_due_user_labels_distinguish_trade_direction(self):
        self.assertEqual(
            amount_due_user_label("EXPORT"),
            "분석 대상 예정 수취액",
        )
        self.assertEqual(
            amount_due_user_label("IMPORT"),
            "분석 대상 예정 지급액",
        )
        self.assertEqual(
            amount_due_user_label("UNKNOWN"),
            "분석 대상 예정 결제액",
        )
        self.assertEqual(
            SCHEDULED_EXPOSURE_WARNING,
            (
                "현재 분석은 계약서에 명시된 예정 결제액을 기준으로 합니다. "
                "실제 입금·지급 이력을 반영한 현재 미수·미지급 잔액은 "
                "별도 확인이 필요합니다."
            ),
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
    def test_service_entry_uses_customer_journey_and_primary_ctas(self):
        from streamlit.testing.v1 import AppTest

        environment = patch.dict(
            "os.environ",
            {"APP_ENV": "development"},
        )
        environment.start()
        self.addCleanup(environment.stop)
        app = AppTest.from_file(
            "app.py",
            default_timeout=20,
        ).run()

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(
            [item.label for item in app.tabs],
            [
                "1  거래 확인",
                "2  금융 리스크 분석",
                "3  상담 준비",
                "4  결과 및 전달",
            ],
        )
        button_labels = [item.label for item in app.button]
        self.assertIn("거래문서 등록하기", button_labels)
        self.assertIn("미국 수출 샘플로 체험하기", button_labels)
        visible_text = " ".join(
            [item.value for item in app.markdown]
            + [item.value for item in app.caption]
        )
        for expected in (
            "수출입 거래 금융 리스크 분석",
            "합성문서",
            "실제 고객정보가 없는",
            "API-free",
            "금융상품 가입·승인 결과가 아닙니다",
            "원문 근거가 확인된 값만 분석",
            "사용자 확인 전 금융계산 차단",
            "미국 수출 샘플",
            "발표용 검증 사례",
            "브라질 Golden 수출 계약",
            "미국 샘플과 결과를 혼합하지 않음",
        ):
            self.assertIn(expected, visible_text)
        self.assertNotIn("Golden 데모 시작", visible_text)

        register = next(
            button
            for button in app.button
            if button.key == "service_register_document"
        )
        register.click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(
            app.session_state["run_mode_widget"],
            "실제 문서 분석",
        )
        self.assertIn(
            "거래문서 업로드",
            [item.label for item in app.get("file_uploader")],
        )

    def test_presentation_mode_shows_only_golden_registration_path(self):
        from streamlit.testing.v1 import AppTest

        with patch.dict(
            "os.environ",
            {"APP_ENV": "presentation"},
        ):
            app = AppTest.from_file(
                "app.py",
                default_timeout=20,
            ).run()

            self.assertEqual(len(app.exception), 0)
            button_labels = [item.label for item in app.button]
            self.assertIn(
                "브라질 Golden 문서 등록하기",
                button_labels,
            )
            for hidden_sample in (
                "미국 수출 샘플로 체험하기",
                "미국 수출 샘플",
                "수입기업 대표 데모",
            ):
                self.assertNotIn(hidden_sample, button_labels)

            visible_text = " ".join(
                [item.value for item in app.markdown]
                + [item.value for item in app.caption]
            )
            self.assertIn(
                "브라질 Golden 수출 계약 검증 시작",
                visible_text,
            )
            self.assertIn(
                "문서 등록 전용 진입 화면",
                visible_text,
            )
            self.assertNotIn(
                "미국 수출 샘플",
                visible_text,
            )
            self.assertNotIn(
                "consultation_packet",
                app.session_state,
            )
            self.assertNotIn(
                "분석할 문서",
                [item.label for item in app.radio],
            )

            register = next(
                button
                for button in app.button
                if button.key == "service_register_document"
            )
            register.click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(
                app.session_state["run_mode_widget"],
                "실제 문서 분석",
            )
            self.assertIn(
                "거래문서 업로드",
                [item.label for item in app.get("file_uploader")],
            )
            self.assertNotIn(
                "consultation_packet",
                app.session_state,
            )

    def test_export_sample_summary_uses_existing_packet_values(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=20).run()
        sample = next(
            button
            for button in app.button
            if button.key == "service_sample_export"
        )
        sample.click().run()

        self.assertEqual(len(app.exception), 0)
        consultation = ConsultationPacketResult.model_validate(
            app.session_state["consultation_packet"]
        )
        packet = consultation.packet
        self.assertEqual(
            packet.company_summary.trade_amount_fx,
            "100000.00",
        )
        self.assertEqual(
            packet.risk_summary.additional_cost_or_receipt_loss_krw,
            "7000000.00",
        )
        self.assertEqual(
            packet.risk_summary.cash_after_settlement_krw,
            "8000000.00",
        )
        self.assertEqual(
            packet.risk_summary.buffer_shortfall_krw,
            "2000000.00",
        )
        self.assertEqual(
            Decimal(packet.risk_summary.cash_deficit_krw),
            Decimal("0"),
        )
        self.assertEqual(
            Decimal(packet.risk_summary.payment_gap_krw),
            Decimal("0"),
        )
        self.assertIsNotNone(packet.official_candidate_shortlist)
        self.assertLessEqual(
            len(packet.official_candidate_shortlist.candidates),
            3,
        )

        visible_text = " ".join(
            [item.value for item in app.markdown]
            + [item.value for item in app.caption]
            + [item.value for item in app.warning]
            + [item.value for item in app.info]
            + [
                "{} {}".format(item.label, item.value)
                for item in app.metric
            ]
        )
        for expected in (
            "한국 (KR) 판매자 → 미국 (US) 구매자",
            "금융 리스크 분석 요약",
            "분석 대상 예정 수취액",
            "USD 100,000",
            "환율 변동 시 원화 수취 감소",
            "7,000,000원",
            "스트레스 후 예상 현금",
            "8,000,000원",
            "목표 현금 버퍼",
            "10,000,000원",
            "목표 현금 버퍼 부족",
            "2,000,000원",
            "현금 적자 / 지급 부족",
            "0원 / 0원",
            "현재 미수·미지급 잔액은",
            "지급불능 또는 필요 대출금이 아닙니다",
            "준비자료",
            "은행에 물어볼 질문",
            "상담에서 기대하는 결정",
            "공식 출처 확인",
        ):
            self.assertIn(expected, visible_text)
        download_labels = [
            item.label for item in app.get("download_button")
        ]
        self.assertIn("상담 준비서 다운로드", download_labels)
        self.assertIn("JSON 데이터 내려받기", download_labels)
        self.assertLess(
            download_labels.index("상담 준비서 다운로드"),
            download_labels.index("JSON 데이터 내려받기"),
        )
        self.assertNotIn(
            "한국 (KR) 판매자 → 브라질 (BR) 구매자",
            visible_text,
        )
        self.assertNotIn("잔금 예정: USD 80,000", visible_text)
        self.assertIn(
            "상담 준비서 미리보기",
            [item.label for item in app.expander],
        )
        self.assertIn(
            "통합 상담 리포트 미리보기",
            [item.label for item in app.expander],
        )
        for prohibited in (
            "상담사에게 전송 완료",
            "상담 예약 완료",
            "신청 완료되었습니다",
            "KB 내부 전달 완료",
            "금융상품 가입 가능",
            "승인 예상",
        ):
            self.assertNotIn(prohibited, visible_text)

    def test_service_ctas_keep_explicit_narrow_screen_layout(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=20).run()

        self.assertEqual(len(app.exception), 0)
        css = next(
            item.value
            for item in app.markdown
            if "@media (max-width: 640px)" in item.value
        )
        self.assertIn(".st-key-service_entry_actions", css)
        self.assertIn("grid-template-columns: 1fr", css)
        self.assertIn("overflow-x: auto", css)
        self.assertIn("padding: 0 0.2rem", css)
        self.assertIn(":has(.journey-step)", css)
        self.assertIn(
            'div[data-testid="stDownloadButton"] > '
            'button[kind="primary"]',
            css,
        )
        self.assertIn("initial_sidebar_state=\"auto\"", Path(
            "app.py"
        ).read_text(encoding="utf-8"))
        self.assertIn(
            "거래문서 등록하기",
            [item.label for item in app.button],
        )
        self.assertIn(
            "미국 수출 샘플로 체험하기",
            [item.label for item in app.button],
        )

    def test_demo_script_separates_us_sample_from_golden_presentation(self):
        script = Path("docs/DEMO_SCRIPT_KO.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(script.split())
        self.assertIn("미국 수출 샘플로 체험하기", normalized)
        self.assertIn("브라질 Golden", normalized)
        self.assertIn("발표에서는 브라질 Golden", normalized)
        self.assertIn("APP_ENV=presentation", normalized)
        self.assertIn("브라질 Golden 문서 등록하기", normalized)
        self.assertIn("Golden 결과를 자동 주입하거나", normalized)
        self.assertNotIn("수출기업 대표 데모", normalized)

    def test_amount_due_widget_uses_directional_scheduled_label(self):
        from streamlit.testing.v1 import AppTest

        cases = (
            ("수입기업 대표 데모", "분석 대상 예정 지급액"),
            ("미국 수출 샘플", "분석 대상 예정 수취액"),
        )
        for button_label, expected_label in cases:
            with self.subTest(button_label=button_label):
                app = AppTest.from_file(
                    "app.py",
                    default_timeout=20,
                ).run()
                demo = next(
                    button
                    for button in app.button
                    if button.label == button_label
                )
                demo.click().run()
                amount_due = next(
                    widget
                    for widget in app.text_input
                    if widget.key == "review_amount_due_widget"
                )
                self.assertEqual(amount_due.label, expected_label)
                self.assertTrue(
                    any(
                        item.value == SCHEDULED_EXPOSURE_WARNING
                        for item in app.caption
                    )
                )
                self.assertEqual(len(app.exception), 0)

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

    def test_export_demo_shows_ranked_consultation_cards_and_cta(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=20).run()
        demo = next(
            button
            for button in app.button
            if button.label == "미국 수출 샘플"
        )
        demo.click().run()

        self.assertEqual(len(app.exception), 0)
        visible_text = " ".join(
            [item.value for item in app.markdown]
            + [item.value for item in app.caption]
            + [item.value for item in app.warning]
            + [item.value for item in app.info]
        )
        for expected in (
            "먼저 확인할 상담",
            "1순위",
            "수출대금 회수 보호 상담",
            "2순위",
            "환율 관리 상담",
            "3순위",
            "운영자금 버퍼·수출대금 회수시점 상담",
            "7,000,000원",
            "2,000,000원",
            "현금 적자",
            "지급·신용한도 반영 후 부족",
            "높은 검토 우선도",
            "상품 승인·보험 인수·대출 심사 결과가 아닙니다",
        ):
            self.assertIn(expected, visible_text)
        self.assertIn(
            "상담 준비서 다운로드",
            [item.label for item in app.get("download_button")],
        )
        for prohibited in (
            "승인될 것입니다",
            "최적 상품입니다",
            "상담 예약 완료",
            "RM에게 전송 완료",
        ):
            self.assertNotIn(prohibited, visible_text)

    def test_golden_packet_ui_marks_advance_receipt_unknown(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=20).run()
        demo = next(
            button
            for button in app.button
            if button.label == "미국 수출 샘플"
        )
        demo.click().run()
        golden = build_golden_consultation_fixture()
        packet_result = golden["decision"].consultation_packet
        app.session_state["extraction"] = golden[
            "extraction"
        ].model_dump()
        app.session_state["consultation_packet"] = (
            packet_result.model_dump()
        )
        app.session_state["installment_payment_statuses"] = [
            item.model_dump()
            for item in packet_result.packet.installment_payment_statuses
        ]
        app.run()

        self.assertEqual(len(app.exception), 0)
        visible_text = " ".join(
            [item.value for item in app.markdown]
            + [item.value for item in app.warning]
            + [item.value for item in app.caption]
            + [
                "{} {}".format(item.label, item.value)
                for item in app.metric
            ]
        )
        self.assertIn(
            "USD 20,000 선지급의 실제 입금 여부와 입금일",
            visible_text,
        )
        for expected in (
            "한국 (KR) 판매자 → 브라질 (BR) 구매자",
            "USD 100,000",
            "7,000,000원",
            "8,000,000원",
            "10,000,000원",
            "2,000,000원",
            "0원 / 0원",
            "현재 미수·미지급 잔액은",
        ):
            self.assertIn(expected, visible_text)
        self.assertIn("선지급 실제 입금 여부", visible_text)
        self.assertIn("UNKNOWN", visible_text)
        self.assertIn(
            "선지급 입금 상태 반영",
            [item.label for item in app.button],
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
