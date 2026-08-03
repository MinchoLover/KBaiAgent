import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from src.application.registered_document_service import (
    PRESENTATION_EXTRACTION_PATH,
    analyze_document,
    presentation_document,
)
from src.application.stage2_input_service import (
    CashflowValidationError,
    Stage2FormInput,
    build_validated_stage2_input_from_form,
    classify_cashflow_error,
)
from src.config import Settings
from src.document_intake.extractor import ExtractionError
from src.document_intake.openai_adapter import (
    AdapterExtractionResult,
    ExtractionUsage,
    OpenAIAdapterError,
)
from src.domain.document_analysis_models import FALLBACK_WARNING_CODE
from schemas import TradeDocumentExtraction
from src.stage2.binding import (
    confirmed_transaction_from_confirmation,
    document_input_from_confirmed_transaction,
)
from src.stage2.engine import run_stage2
from src.domain.stage3_models import Stage3Result
from src.ui.state import PIPELINE_KEYS
from src.workflow.result import StageResult, StageStatus
from src.workflow.state import WorkflowState
from tests.golden_consultation_fixture import (
    build_golden_consultation_fixture,
)


def _by_key(elements, key):
    return next(item for item in elements if item.key == key)


def _state(app, key, default=None):
    try:
        return app.session_state[key]
    except KeyError:
        return default


class ConfirmedTransactionProductionTests(unittest.TestCase):
    def setUp(self):
        self.golden = build_golden_consultation_fixture()

    @staticmethod
    def _successful_adapter():
        extraction = TradeDocumentExtraction.model_validate_json(
            PRESENTATION_EXTRACTION_PATH.read_text(encoding="utf-8")
        )

        class Adapter:
            def extract(self, **_kwargs):
                return AdapterExtractionResult(
                    extraction=extraction,
                    usage=ExtractionUsage(
                        model="mock-live-model",
                        prompt_version="test-prompt",
                        request_id="mock-request",
                        latency_seconds=0.01,
                        input_tokens=10,
                        output_tokens=20,
                        total_tokens=30,
                        attempts=1,
                    ),
                )

        return Adapter()

    @staticmethod
    def _failing_adapter():
        class Adapter:
            def extract(self, **_kwargs):
                raise OpenAIAdapterError("mock transport failure")

        return Adapter()

    def test_golden_live_success_does_not_use_fixture(self):
        registered = presentation_document()
        with patch(
            "src.application.registered_document_service."
            "extract_registered_document",
            side_effect=AssertionError("fixture must not be loaded"),
        ):
            result = analyze_document(
                file_bytes=registered.file_bytes,
                filename="renamed-upload.pdf",
                mime_type=registered.mime_type,
                company_role="SELLER",
                company_country="KR",
                document_source="golden_sample",
                analysis_mode="live_api",
                settings=Settings(openai_api_key="test-key"),
                adapter=self._successful_adapter(),
            )

        self.assertEqual(result.usage.model, "mock-live-model")
        self.assertIsNotNone(result.provenance)
        self.assertEqual(result.provenance.document_source, "golden_sample")
        self.assertEqual(result.provenance.analysis_source, "openai")
        self.assertFalse(result.provenance.fallback_used)
        self.assertEqual(result.provenance.warnings, [])
        self.assertEqual(result.extraction.contract_date, "2026-07-29")
        self.assertEqual(result.extraction.shipment_date, "2026-08-05")
        self.assertEqual(result.extraction.explicit_due_date, "2026-08-20")
        self.assertEqual(result.extraction.amount_due, "100000.00")
        self.assertFalse(result.validation.stage2_allowed)

    def test_golden_live_failure_uses_disclosed_fixture_fallback(self):
        registered = presentation_document()
        result = analyze_document(
            file_bytes=registered.file_bytes,
            filename=registered.filename,
            mime_type=registered.mime_type,
            company_role="BUYER",
            company_country="KR",
            document_source="golden_sample",
            analysis_mode="live_api",
            settings=Settings(
                openai_api_key="test-key",
            ),
            adapter=self._failing_adapter(),
        )

        self.assertEqual(result.auto_matched_company_role, "SELLER")
        self.assertEqual(result.extraction.company_role, "SELLER")
        self.assertEqual(result.extraction.trade_type, "EXPORT")
        self.assertEqual(result.provenance.analysis_mode, "live_api")
        self.assertEqual(
            result.provenance.analysis_source,
            "verified_fixture",
        )
        self.assertTrue(result.provenance.fallback_used)
        self.assertEqual(
            result.provenance.warnings,
            [FALLBACK_WARNING_CODE],
        )
        self.assertNotIn(
            "COMPANY_COUNTRY_ROLE_MISMATCH",
            {item.code for item in result.validation.issues},
        )

    def test_user_upload_live_failure_never_uses_golden_fixture(self):
        registered = presentation_document()
        with self.assertRaises(ExtractionError):
            analyze_document(
                file_bytes=registered.file_bytes,
                filename=registered.filename,
                mime_type=registered.mime_type,
                company_role="SELLER",
                company_country="KR",
                document_source="user_upload",
                analysis_mode="live_api",
                settings=Settings(openai_api_key="test-key"),
                adapter=self._failing_adapter(),
            )

    def test_golden_input_validation_failure_does_not_use_fixture(self):
        registered = presentation_document()
        with patch(
            "src.application.registered_document_service."
            "extract_registered_document",
            side_effect=AssertionError("fixture must not be loaded"),
        ):
            with self.assertRaises(ExtractionError):
                analyze_document(
                    file_bytes=registered.file_bytes,
                    filename=registered.filename,
                    mime_type=registered.mime_type,
                    company_role="INVALID",
                    company_country="KR",
                    document_source="golden_sample",
                    analysis_mode="live_api",
                    settings=Settings(openai_api_key="test-key"),
                    adapter=self._successful_adapter(),
                )

    def test_verified_fixture_is_explicit_and_golden_only(self):
        registered = presentation_document()
        result = analyze_document(
            file_bytes=registered.file_bytes,
            filename=registered.filename,
            mime_type=registered.mime_type,
            company_role="SELLER",
            company_country="KR",
            document_source="golden_sample",
            analysis_mode="verified_fixture",
            settings=Settings(openai_api_key=None),
        )
        self.assertEqual(result.provenance.analysis_mode, "verified_fixture")
        self.assertFalse(result.provenance.fallback_used)
        with self.assertRaises(ExtractionError):
            analyze_document(
                file_bytes=registered.file_bytes,
                filename=registered.filename,
                mime_type=registered.mime_type,
                company_role="SELLER",
                company_country="KR",
                document_source="user_upload",
                analysis_mode="verified_fixture",
                settings=Settings(openai_api_key=None),
            )

    def test_snapshot_is_the_stage_contract_and_keeps_dates_separate(self):
        snapshot = confirmed_transaction_from_confirmation(
            extraction=self.golden["extraction"],
            validation=self.golden["validation"],
            confirmation=self.golden["confirmation"],
        )
        document_input = document_input_from_confirmed_transaction(
            snapshot
        )

        self.assertEqual(snapshot.contract_date, "2026-07-29")
        self.assertEqual(snapshot.shipment_date, "2026-08-05")
        self.assertEqual(snapshot.due_date, "2026-08-20")
        self.assertEqual(snapshot.amount_due, "100000.00")
        self.assertEqual(len(snapshot.input_fingerprint), 64)
        self.assertEqual(
            document_input["trade"]["settlement_date"],
            snapshot.due_date,
        )
        self.assertEqual(
            document_input["trade"]["settlement_date_source"],
            "workflow.confirmed_transaction.due_date",
        )
        self.assertEqual(
            document_input["source"][
                "confirmed_transaction_fingerprint"
            ],
            snapshot.input_fingerprint,
        )

    def test_invalid_cash_input_has_complete_structured_error(self):
        form = Stage2FormInput(
            as_of_date="2026-07-30",
            current_krw_cash="not-a-number",
            minimum_cash_buffer="5000000",
            credit_limit="3000000",
            usable_fx_balance="10000",
            acceptable_fx_loss="1000000",
            same_currency_flow_amount="0",
            same_currency_flow_date="2026-07-30",
            same_currency_flow_direction="OUTFLOW",
            existing_hedge_amount="0",
            existing_hedge_rate="1400",
            existing_hedge_fee="0",
            bank_spread_bps="15",
            bank_fee="50000",
        )

        with self.assertRaises(CashflowValidationError) as raised:
            build_validated_stage2_input_from_form(
                document_input=self.golden["document_input"],
                form=form,
            )

        detail = raised.exception.detail
        self.assertEqual(detail.code, "INVALID_CASH_INPUT")
        self.assertEqual(detail.stage, "cashflow")
        self.assertEqual(detail.field_path, "stage2.current_krw_cash")
        self.assertEqual(detail.offending_value, "not-a-number")
        self.assertEqual(len(detail.input_fingerprint), 64)
        self.assertIn("ValueError", detail.technical_message)
        self.assertNotIn("Traceback", detail.technical_message)

    def test_invalid_editor_direction_is_not_misclassified_as_trade_type(self):
        detail = classify_cashflow_error(
            ValueError(
                "KrwCashflowEvent direction Input should be "
                "'INFLOW' or 'OUTFLOW'"
            ),
            input_fingerprint="f" * 64,
            supplied_offending_value="invalid-direction",
        )

        self.assertEqual(detail.code, "INVALID_CASH_INPUT")
        self.assertEqual(
            detail.field_path,
            "stage2.krw_cashflows[].direction",
        )
        self.assertEqual(detail.offending_value, "invalid-direction")
        self.assertIn("INFLOW", detail.user_message)
        self.assertIn("OUTFLOW", detail.user_message)

    def test_export_held_fx_is_retained_as_non_applicable_context(self):
        stage2_input = build_validated_stage2_input_from_form(
            document_input=self.golden["document_input"],
            form=Stage2FormInput(
                as_of_date="2026-07-30",
                current_krw_cash="20000000",
                minimum_cash_buffer="5000000",
                credit_limit="3000000",
                usable_fx_balance="10000",
                acceptable_fx_loss="1000000",
                same_currency_flow_amount="0",
                same_currency_flow_date="2026-07-30",
                same_currency_flow_direction="OUTFLOW",
                existing_hedge_amount="0",
                existing_hedge_rate="1400",
                existing_hedge_fee="0",
                bank_spread_bps="15",
                bank_fee="50000",
            ),
        )
        result = run_stage2(stage2_input, self.golden["stage1"])

        self.assertEqual(stage2_input.as_of_date, "2026-07-30")
        self.assertEqual(
            stage2_input.non_applicable_inputs,
            {"usable_fx_balance": "10000"},
        )
        self.assertIn(
            "EXPORT_USABLE_FX_NOT_APPLIED",
            stage2_input.preprocessing_warnings,
        )
        self.assertEqual(
            stage2_input.exposures[0].usable_fx_balance,
            "0",
        )
        self.assertEqual(result.held_fx_used, "0")
        self.assertEqual(result.open_exposure, "100000.00")


class CompletedGoldenStreamlitJourneyTests(unittest.TestCase):
    @staticmethod
    def _confirm_document(app):
        _by_key(
            app.button,
            "service_sample_export",
        ).click().run(timeout=30)
        assert _state(app, "extraction") is not None
        _by_key(
            app.button,
            (
                "FormSubmitter:review_extraction-"
                "수정 내용 저장 및 다시 검증"
            ),
        ).click().run(timeout=30)
        for key in (
            "confirm_company_role_widget",
            "confirm_trade_type_widget",
            "confirm_currency_widget",
            "confirm_amount_widget",
            "confirm_due_widget",
        ):
            _by_key(app.checkbox, key).set_value(True)
        _by_key(
            app.button,
            (
                "FormSubmitter:critical_confirmation-"
                "거래 기본정보 확정"
            ),
        ).click().run(timeout=30)

    @staticmethod
    def _run_stage1_and_trade_risk(app):
        _by_key(
            app.radio,
            "stage1_mode_widget",
        ).set_value("MANUAL_STRESS")
        _by_key(
            app.text_input,
            "stage1_base_rate_widget",
        ).set_value("1400")
        _by_key(app.button, "load_stage1").click().run(timeout=30)
        _by_key(
            app.selectbox,
            "trade_risk_relationship_widget",
        ).set_value("EXISTING")
        _by_key(
            app.selectbox,
            "trade_risk_advance_status_widget",
        ).set_value("RATIO_CONFIRMED").run(timeout=30)
        _by_key(
            app.number_input,
            "trade_risk_advance_percent_widget",
        ).set_value(20.0)
        _by_key(
            app.selectbox,
            "trade_risk_balance_method_widget",
        ).set_value("OPEN_ACCOUNT")
        _by_key(
            app.selectbox,
            "trade_risk_term_basis_widget",
        ).set_value("CONFIRMED_DATE_INTERVAL").run(timeout=30)
        _by_key(
            app.number_input,
            "trade_risk_term_days_widget",
        ).set_value(22)
        _by_key(
            app.selectbox,
            "trade_risk_protection_status_widget",
        ).set_value("NONE_CONFIRMED")
        _by_key(
            app.checkbox,
            "trade_risk_confirm_widget",
        ).set_value(True)
        _by_key(
            app.button,
            (
                "FormSubmitter:trade_risk_confirmation_form-"
                "대금 회수조건 확인"
            ),
        ).click().run(timeout=30)

    @staticmethod
    def _run_golden_cashflow(app):
        expected_text_defaults = {
            "stage2_current_cash_widget": "20,000,000.00",
            "stage2_minimum_buffer_widget": "10,000,000.00",
            "stage2_credit_limit_widget": "0.00",
            "stage2_acceptable_loss_widget": "5,000,000.00",
            "stage2_usable_fx_widget": "0.00",
            "stage2_bank_spread_widget": "0",
            "stage2_bank_fee_widget": "0.00",
        }
        for key, value in expected_text_defaults.items():
            assert _by_key(app.text_input, key).value == value
        assert _by_key(
            app.date_input,
            "stage2_as_of_widget",
        ).value == date(2026, 7, 29)
        _by_key(
            app.button,
            (
                "FormSubmitter:stage2_company_input-"
                "환율·자금 위험 계산하기"
            ),
        ).click().run(timeout=30)

    def test_financial_support_page_is_not_blank_before_hedge(self):
        from streamlit.testing.v1 import AppTest

        environment = {
            "APP_ENV": "presentation",
            "OPENAI_API_KEY": "",
            "ENABLE_LIVE_DOCUMENT_EXTRACTION": "false",
            "ENABLE_LLM_REPORT": "false",
            "ENABLE_OFFICIAL_WEB_SEARCH": "false",
            "STAGE1_MODE": "manual",
        }
        with patch.dict(os.environ, environment, clear=False):
            app = AppTest.from_file(
                "app.py",
                default_timeout=30,
            ).run(timeout=30)
            self._confirm_document(app)
            self._run_stage1_and_trade_risk(app)
            self._run_golden_cashflow(app)

            self.assertIsNone(_state(app, "stage3_result"))
            _by_key(
                app.button,
                "go_to_consultation_from_summary",
            ).click().run(timeout=30)
            self.assertEqual(_state(app, "active_page"), "consultation")
            self.assertIn(
                "금융지원 후보 준비를 한 번만 완료해 주세요",
                " ".join(item.value for item in app.markdown),
            )
            prepare = _by_key(
                app.button,
                "prepare_hedge_for_financial_support",
            )
            self.assertFalse(prepare.disabled)

            prepare.click().run(timeout=30)
            self.assertIsNotNone(_state(app, "stage3_result"))
            self.assertIn(
                "search_stage4",
                {item.key for item in app.button},
            )

    def test_company_cashflow_submit_prepares_missing_fx_range(self):
        from streamlit.testing.v1 import AppTest

        environment = {
            "APP_ENV": "presentation",
            "OPENAI_API_KEY": "",
            "ENABLE_LIVE_DOCUMENT_EXTRACTION": "false",
            "ENABLE_LLM_REPORT": "false",
            "ENABLE_OFFICIAL_WEB_SEARCH": "false",
            "STAGE1_MODE": "manual",
        }
        with patch.dict(os.environ, environment, clear=False):
            app = AppTest.from_file(
                "app.py",
                default_timeout=30,
            ).run(timeout=30)
            self._confirm_document(app)
            _by_key(
                app.radio,
                "stage1_mode_widget",
            ).set_value("MANUAL_STRESS")
            _by_key(
                app.text_input,
                "stage1_base_rate_widget",
            ).set_value("1400")

            self.assertIsNone(_state(app, "stage1_load"))
            submit = _by_key(
                app.button,
                (
                    "FormSubmitter:stage2_company_input-"
                    "환율·자금 위험 계산하기"
                ),
            )
            self.assertFalse(submit.disabled)

            self._run_golden_cashflow(app)

            self.assertEqual(len(app.exception), 0)
            self.assertIsNotNone(_state(app, "stage1_load"))
            stage2 = _state(app, "stage2_result")
            self.assertIsNotNone(stage2)
            down_five = next(
                item
                for item in stage2["scenario_results"]
                if item["scenario_name"] == "STRESS_-5.00PCT"
            )
            self.assertEqual(
                Decimal(down_five["loss_vs_base"]),
                Decimal("7000000.00"),
            )

    def test_web_forecast_ui_uses_five_percent_representative_scenario(self):
        from streamlit.testing.v1 import AppTest

        environment = {
            "APP_ENV": "presentation",
            "DEMO_MODE": "true",
            "SHOW_INTERNAL_DEBUG": "false",
            "OPENAI_API_KEY": "",
            "ENABLE_LIVE_DOCUMENT_EXTRACTION": "false",
            "ENABLE_LLM_REPORT": "false",
            "ENABLE_OFFICIAL_WEB_SEARCH": "false",
            "STAGE1_MODE": "web_forecast",
            "STAGE1_PROVIDER": "file",
            "SPOT_RATE_PROVIDER": "fixture",
            "TRADE_STATISTICS_PROVIDER": "fixture",
        }
        with patch.dict(os.environ, environment, clear=False):
            app = AppTest.from_file(
                "app.py",
                default_timeout=30,
            ).run(timeout=30)
            self._confirm_document(app)
            _by_key(
                app.checkbox,
                "trade_risk_confirm_widget",
            ).set_value(True)
            _by_key(
                app.button,
                (
                    "FormSubmitter:trade_risk_confirmation_form-"
                    "대금 회수조건 확인"
                ),
            ).click().run(timeout=30)
            self._run_golden_cashflow(app)

            stage2 = _state(app, "stage2_result")
            self.assertIsNotNone(
                stage2,
                [item.value for item in app.error],
            )
            down_five = next(
                item
                for item in stage2["scenario_results"]
                if item["scenario_name"] == "DOWN_5"
            )
            self.assertEqual(
                Decimal(down_five["loss_vs_base"]),
                Decimal("7000000.00"),
            )
            _by_key(
                app.button,
                "go_to_analysis_after_transaction_inputs",
            ).click().run(timeout=30)
            visible = " ".join(
                [item.value for item in app.markdown]
                + [item.value for item in app.caption]
            )
            for expected in (
                "환율 -5%",
                "기준 원화 수취액",
                "140,000,000원",
                "환율 -5% 원화 수취액",
                "133,000,000원",
                "7,000,000원",
                "8,000,000원",
                "2,000,000원",
            ):
                self.assertIn(expected, visible)
            self.assertNotIn("DOWN_5", visible)

    def test_click_journey_reaches_report_then_invalidates_and_resets(self):
        from streamlit.testing.v1 import AppTest

        environment = {
            "APP_ENV": "presentation",
            "SHOW_INTERNAL_DEBUG": "true",
            "OPENAI_API_KEY": "",
            "ENABLE_LIVE_DOCUMENT_EXTRACTION": "false",
            "ENABLE_LLM_REPORT": "false",
            "ENABLE_OFFICIAL_WEB_SEARCH": "false",
            "STAGE1_MODE": "manual",
        }
        with patch.dict(os.environ, environment, clear=False):
            app = AppTest.from_file(
                "app.py",
                default_timeout=30,
            ).run(timeout=30)
            self._confirm_document(app)

            self.assertEqual(len(app.exception), 0)
            self.assertEqual(
                _state(app, "upload_metadata")["provider"],
                "verified_fixture",
            )
            snapshot = _state(app, "confirmed_transaction")
            self.assertEqual(_state(app, "active_page"), "transaction")
            self.assertEqual(snapshot["contract_date"], "2026-07-29")
            self.assertEqual(snapshot["shipment_date"], "2026-08-05")
            self.assertEqual(snapshot["due_date"], "2026-08-20")
            self.assertEqual(snapshot["amount_due"], "100000.00")
            self.assertEqual(len(snapshot["input_fingerprint"]), 64)

            self._run_stage1_and_trade_risk(app)
            self.assertEqual(
                _state(app, "stage1_load")["scenario_set"]["target_date"],
                "2026-08-20",
            )
            self.assertIsNotNone(
                _state(app, "country_environment_assessment")
            )
            held_fx_labels = [
                item.label
                for item in app.text_input
                if item.key == "stage2_usable_fx_widget"
            ]
            self.assertEqual(
                held_fx_labels,
                ["현재 보유외화 · USD · 수취액 계산 미적용"],
            )

            self._run_golden_cashflow(app)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.error), 0)
            stage2_input = _state(app, "stage2_input")
            stage2 = _state(app, "stage2_result")
            consultation = _state(app, "consultation_packet")
            packet = consultation["packet"]
            trade_statistics = _state(app, "trade_statistics_result")
            self.assertEqual(
                packet["document_analysis"]["document_source"],
                "golden_sample",
            )
            self.assertEqual(
                packet["document_analysis"]["analysis_source"],
                "verified_fixture",
            )
            self.assertTrue(
                packet["document_analysis"]["fallback_used"]
            )
            self.assertEqual(
                packet["document_analysis"]["warnings"],
                ["FALLBACK_USED"],
            )
            self.assertIn(
                "실제 분석 source: `verified_fixture`",
                consultation["markdown"],
            )
            self.assertIn("FALLBACK_USED", consultation["markdown"])
            self.assertEqual(
                stage2_input["exposures"][0]["settlement_date"],
                "2026-08-20",
            )
            self.assertEqual(
                stage2["source_paths"]["settlement_date"],
                "workflow.confirmed_transaction.due_date",
            )
            self.assertEqual(stage2["total_foreign_amount"], "100000.00")
            down_five = next(
                item
                for item in stage2["scenario_results"]
                if item["scenario_name"] == "STRESS_-5.00PCT"
            )
            self.assertEqual(
                Decimal(down_five["loss_vs_base"]),
                Decimal("7000000.00"),
            )
            self.assertEqual(
                Decimal(down_five["ending_cash"]),
                Decimal("8000000.00"),
            )
            self.assertEqual(
                Decimal(down_five["maximum_buffer_shortfall"]),
                Decimal("2000000.00"),
            )
            self.assertEqual(
                Decimal(down_five["cash_deficit"]),
                Decimal("0.00"),
            )
            self.assertEqual(
                Decimal(down_five["post_credit_shortfall"]),
                Decimal("0.00"),
            )
            self.assertEqual(
                packet["company_summary"]["settlement_date"],
                "2026-08-20",
            )
            self.assertEqual(
                [
                    item["display_name"]
                    for item in packet["consultation_review_areas"]
                ],
                [
                    "수출대금 회수 보호",
                    "환율 관리",
                    "무역금융·운영자금",
                ],
            )
            self.assertNotIn(
                "consultation_supporting_checks",
                packet,
            )
            self.assertEqual(
                packet["protection_summary"][
                    "advance_payment_receipt"
                ],
                "UNKNOWN",
            )
            self.assertEqual(
                trade_statistics["status"],
                "OFFICIAL_FIXTURE",
            )
            self.assertEqual(
                trade_statistics["summary"]["scope"],
                "COUNTRY_TOTAL",
            )
            self.assertEqual(
                trade_statistics["summary"][
                    "latest_12m_export_usd"
                ],
                "8282425000",
            )
            self.assertEqual(
                packet["trade_statistics"]["request_fingerprint"],
                trade_statistics["request_fingerprint"],
            )
            self.assertEqual(
                packet["trade_statistics_interpretation"]["status"],
                "DETERMINISTIC_FALLBACK",
            )
            result_cards = [
                item.value
                for item in app.markdown
                if "<div class='result-grid'>" in item.value
            ]
            self.assertEqual(len(result_cards), 1)
            for expected in (
                "환율 -5% 시 원화 수취액 7,000,000원 감소",
                "기준 원화 수취액",
                "140,000,000원",
                "환율 -5% 원화 수취액",
                "133,000,000원",
                "감당 가능한 최대 환율손실 5,000,000원 초과",
                "스트레스 후 예상 현금 8,000,000원",
                "최소 유지 운영자금 10,000,000원",
                "최소 운영자금 대비 부족액 2,000,000원",
                "실제 현금 적자 0원",
                "대출한도 반영 후 부족액 0원",
                "USD 80,000",
                "Open Account / T/T",
            ):
                self.assertIn(expected, result_cards[0])
            financial_page_text = " ".join(
                [item.value for item in app.markdown]
                + [item.value for item in app.caption]
                + [item.value for item in app.info]
                + [item.value for item in app.warning]
                + [
                    "{} {} {}".format(
                        item.label,
                        item.value,
                        item.delta or "",
                    )
                    for item in app.metric
                ]
            )
            for expected in (
                "거래국 무역 통계",
                "한국–브라질 교역 동향",
                "국가 전체 교역",
                "USD 8,282,425,000",
                "USD 6,154,122,000",
                "USD 2,128,302,000",
                "수출 증감률",
                "+56.4%",
                "2024-07~2026-06",
                "이전 비교기간보다 증가했습니다",
                "개별 거래처의 신용도나 대금 회수 가능성을 의미하지 않습니다",
                "HS Code가 없어 국가 전체 교역 통계만",
                "수출 FOB / 수입 CIF",
            ):
                self.assertIn(expected, financial_page_text)
            for internal_code in (
                "UNCALIBRATED_DIRECTION_SCORE",
                "PARTIAL_FALLBACK_USED",
                "FAILED_MARKET_SERIES",
                "NEWS_QUERY_ERRORS",
                "RESEARCH_ONLY",
            ):
                self.assertNotIn(internal_code, financial_page_text)
            self.assertNotIn(
                "출처 및 기술정보",
                [item.label for item in app.expander],
            )
            self.assertIn(
                "품목별 통계 조회 (선택)",
                [item.label for item in app.expander],
            )
            self.assertIn(
                "월별 상세 추이 보기",
                [item.label for item in app.expander],
            )
            self.assertGreaterEqual(
                len(app.get("arrow_vega_lite_chart")),
                1,
            )
            consultation_cards = [
                item.value
                for item in app.markdown
                if "<div class='consultation-card'>" in item.value
            ]
            self.assertEqual(len(consultation_cards), 3)
            for card, title in zip(
                consultation_cards,
                [
                    "수출대금 회수 보호",
                    "환율 관리",
                    "무역금융·운영자금",
                ],
            ):
                self.assertIn(title, card)
                self.assertIn("상담 목적", card)
                self.assertIn("핵심 이유", card)
                self.assertIn("다음 행동", card)

            _by_key(
                app.button,
                "go_to_consultation_from_summary",
            ).click().run(timeout=30)
            self.assertEqual(
                _state(app, "active_page"),
                "consultation",
            )

            _by_key(
                app.button,
                "optimize_stage3",
            ).click().run(timeout=30)
            stage3_result = _state(app, "stage3_result")
            self.assertIsNotNone(stage3_result)
            if not stage3_result["candidates"]:
                self.assertTrue(
                    any(
                        "현재 입력된 조건에서는 제시할 수 있는 "
                        "헤지 비교안이 없습니다."
                        in item.value
                        for item in app.info
                    )
                )
                self.assertNotIn(
                    "헤지 비교 기술정보",
                    [item.label for item in app.expander],
                )
            _by_key(
                app.button,
                "search_stage4",
            ).click().run(timeout=30)
            shortlist = _state(app, "official_candidate_shortlist")
            identities = {
                (
                    item["institution"],
                    item["name"],
                    item["source"]["url"],
                )
                for item in shortlist["candidates"]
            }
            self.assertLessEqual(len(shortlist["candidates"]), 3)
            self.assertEqual(
                len(identities),
                len(shortlist["candidates"]),
            )
            self.assertEqual(
                [
                    (item["institution"], item["name"])
                    for item in shortlist["candidates"]
                ],
                [
                    ("한국무역보험공사", "단기수출보험 검토"),
                    (
                        "KB국민은행",
                        "KB Star FX 선물환·외환스왑 상담",
                    ),
                    ("한국무역보험공사", "환변동보험 검토"),
                ],
            )
            consultation_expanders = {
                item.label for item in app.expander
            }
            for internal_label in (
                "개발자용 · 전략 후보 데이터",
                "개발자용 · 공식 후보 데이터",
                "분석 근거 및 기술 정보 보기",
            ):
                self.assertNotIn(
                    internal_label,
                    consultation_expanders,
                )
            _by_key(
                app.button,
                "generate_report",
            ).click().run(timeout=30)
            report = _state(app, "report_result")
            self.assertEqual(
                report["report_json"]["stage0"]["confirmation"][
                    "confirmed_values"
                ]["settlement_date"],
                "2026-08-20",
            )
            self.assertIn("2026-08-20", report["markdown"])
            self.assertIn(
                "[source: workflow.confirmed_transaction.due_date]",
                report["markdown"],
            )
            self.assertEqual(
                report["report_json"]["workflow"][
                    "confirmed_transaction"
                ]["due_date"],
                "2026-08-20",
            )
            labels = {
                item.label for item in app.get("download_button")
            }
            self.assertIn("상담 준비서 PDF 다운로드", labels)
            self.assertNotIn("JSON 다운로드", labels)
            self.assertNotIn("개발자용 원문 Markdown", labels)
            self.assertIn("통합 보고서 다운로드", labels)
            report_expanders = {
                item.label for item in app.expander
            }
            for internal_label in (
                "개발자용 · JSON 데이터 및 분석 근거",
                "분석 근거 및 기술 정보 보기",
            ):
                self.assertNotIn(internal_label, report_expanders)

            _by_key(
                app.text_input,
                "review_amount_due_widget",
            ).set_value("110000.00")
            _by_key(
                app.button,
                (
                    "FormSubmitter:review_extraction-"
                    "수정 내용 저장 및 다시 검증"
                ),
            ).click().run(timeout=30)
            self.assertNotIn("confirmed_transaction", app.session_state)
            self.assertNotIn("stage2_result", app.session_state)
            self.assertNotIn("report_result", app.session_state)

            reset = next(
                item
                for item in app.button
                if item.label == "새 분석 시작"
            )
            reset.click().run(timeout=30)
            remaining = {
                key for key in PIPELINE_KEYS if key in app.session_state
            }
            self.assertEqual(remaining, set())
            self.assertEqual(len(app.exception), 0)

    def test_profile_submit_refreshes_recommendations_in_one_user_action(self):
        from streamlit.testing.v1 import AppTest

        environment = {
            "APP_ENV": "presentation",
            "OPENAI_API_KEY": "",
            "ENABLE_LIVE_DOCUMENT_EXTRACTION": "false",
            "ENABLE_LLM_REPORT": "false",
            "ENABLE_OFFICIAL_WEB_SEARCH": "false",
            "STAGE1_MODE": "manual",
        }
        with patch.dict(os.environ, environment, clear=False):
            app = AppTest.from_file(
                "app.py",
                default_timeout=30,
            ).run(timeout=30)
            self._confirm_document(app)
            self._run_stage1_and_trade_risk(app)
            self._run_golden_cashflow(app)
            _by_key(
                app.button,
                "go_to_consultation_from_summary",
            ).click().run(timeout=30)
            _by_key(app.button, "optimize_stage3").click().run(timeout=30)
            _by_key(app.button, "search_stage4").click().run(timeout=30)
            _by_key(app.button, "generate_report").click().run(timeout=30)

            stage1_before = _state(app, "stage1_load")
            stage2_before = _state(app, "stage2_result")
            stage3_before = _state(app, "stage3_result")
            self.assertIsNotNone(_state(app, "report_result"))

            values = {
                "shipment_status": "PRE_SHIPMENT",
                "receivable_status": "NOT_YET",
                "trade_form": "PROCESSING_TRADE",
                "customs_clearance": "NO",
                "relationship_scope": "SINGLE_ONE_OFF",
                "credit_information_status": "SUFFICIENT",
                "credit_investigation_intent": "NO",
                "funding_purposes": "MANUFACTURING",
                "receivable_financing_intent": "NONE",
                "early_cash_conversion_intent": "NOT_APPLICABLE",
                "bank_financing_intent": "YES",
                "repayment_responsibility_acknowledgement": (
                    "NOT_APPLICABLE"
                ),
                "short_term_export_insurance_linkage_review": (
                    "NOT_APPLICABLE"
                ),
                "sme_status": "CONFIRMED",
                "annual_export_band": "AT_LEAST_USD_100K",
                "market_entry_purpose": "YES",
                "policy_finance_need": "YES",
                "production_or_working_capital_need": "YES",
            }
            for field_name, value in values.items():
                _by_key(
                    app.selectbox,
                    "official_profile_{}_widget".format(field_name),
                ).set_value(value)

            _by_key(
                app.button,
                (
                    "FormSubmitter:official_candidate_input_profile_form-"
                    "선택 내용 반영해 추천 업데이트"
                ),
            ).click().run(timeout=30)

            self.assertEqual(len(app.exception), 0)
            self.assertEqual(_state(app, "stage1_load"), stage1_before)
            self.assertEqual(_state(app, "stage2_result"), stage2_before)
            self.assertEqual(_state(app, "stage3_result"), stage3_before)
            shortlist = _state(app, "official_candidate_shortlist")
            self.assertEqual(
                [item["product_id"] for item in shortlist["candidates"]],
                [
                    "ksure_export_credit_guarantee_pre_shipment",
                    "kosmes_export_funding",
                    "kb_star_fx_forward",
                ],
            )
            self.assertNotIn("report_result", app.session_state)
            self.assertNotIn("report_download_payload", app.session_state)
            self.assertNotIn(
                "official_candidate_auto_refresh",
                app.session_state,
            )
            self.assertTrue(
                any(
                    "선택한 조건을 반영해 상담 후보를 업데이트했습니다."
                    in item.value
                    for item in app.success
                )
            )

    def test_conflicting_profile_hides_previous_recommendation_artifacts(self):
        from streamlit.testing.v1 import AppTest

        environment = {
            "APP_ENV": "presentation",
            "OPENAI_API_KEY": "",
            "ENABLE_LIVE_DOCUMENT_EXTRACTION": "false",
            "ENABLE_LLM_REPORT": "false",
            "ENABLE_OFFICIAL_WEB_SEARCH": "false",
            "STAGE1_MODE": "manual",
        }
        with patch.dict(os.environ, environment, clear=False):
            app = AppTest.from_file(
                "app.py",
                default_timeout=30,
            ).run(timeout=30)
            self._confirm_document(app)
            self._run_stage1_and_trade_risk(app)
            self._run_golden_cashflow(app)
            _by_key(
                app.button,
                "go_to_consultation_from_summary",
            ).click().run(timeout=30)
            _by_key(app.button, "optimize_stage3").click().run(timeout=30)
            _by_key(app.button, "search_stage4").click().run(timeout=30)
            _by_key(app.button, "generate_report").click().run(timeout=30)

            valid_profile_values = {
                "shipment_status": "COMPLETED",
                "receivable_status": "EXISTS",
                "trade_form": "GENERAL_EXPORT",
                "customs_clearance": "YES",
                "relationship_scope": "SINGLE_ONE_OFF",
                "credit_information_status": "SUFFICIENT",
                "credit_investigation_intent": "NO",
                "funding_purposes": "RECEIVABLE_EARLY_CASH_CONVERSION",
                "receivable_financing_intent": "NEGO_OR_PURCHASE",
                "early_cash_conversion_intent": "YES",
                "bank_financing_intent": "YES",
                "repayment_responsibility_acknowledgement": "ACKNOWLEDGED",
                "short_term_export_insurance_linkage_review": (
                    "AGREED_TO_REVIEW"
                ),
                "sme_status": "UNKNOWN",
                "annual_export_band": "UNKNOWN",
                "market_entry_purpose": "NO",
                "policy_finance_need": "NO",
                "production_or_working_capital_need": "NO",
            }
            for field_name, value in valid_profile_values.items():
                _by_key(
                    app.selectbox,
                    "official_profile_{}_widget".format(field_name),
                ).set_value(value)
            _by_key(
                app.button,
                (
                    "FormSubmitter:official_candidate_input_profile_form-"
                    "선택 내용 반영해 추천 업데이트"
                ),
            ).click().run(timeout=30)
            _by_key(
                app.button,
                "workflow_nav_download",
            ).click().run(timeout=30)
            _by_key(app.button, "generate_report").click().run(timeout=30)

            stage1_before = _state(app, "stage1_load")
            stage2_before = _state(app, "stage2_result")
            stage3_before = _state(app, "stage3_result")
            self.assertIsNotNone(_state(app, "official_candidate_shortlist"))
            self.assertIsNotNone(_state(app, "consultation_packet"))
            self.assertIsNotNone(_state(app, "report_result"))

            conflicting_values = {
                "shipment_status": "PRE_SHIPMENT",
                "receivable_status": "NOT_YET",
                "customs_clearance": "YES",
                "credit_information_status": "INSUFFICIENT",
                "credit_investigation_intent": "NO",
            }
            for field_name, value in conflicting_values.items():
                _by_key(
                    app.selectbox,
                    "official_profile_{}_widget".format(field_name),
                ).set_value(value)

            _by_key(
                app.button,
                (
                    "FormSubmitter:official_candidate_input_profile_form-"
                    "선택 내용 반영해 추천 업데이트"
                ),
            ).click().run(timeout=30)

            self.assertEqual(len(app.exception), 0)
            self.assertTrue(
                any("현재 매입할 수출채권이 없는데" in item.value for item in app.error)
            )
            visible_warnings = " ".join(item.value for item in app.warning)
            self.assertIn("선적 전인데 수출 통관", visible_warnings)
            self.assertIn("신용정보는 부족", visible_warnings)
            self.assertEqual(_state(app, "stage1_load"), stage1_before)
            self.assertEqual(_state(app, "stage2_result"), stage2_before)
            self.assertEqual(_state(app, "stage3_result"), stage3_before)
            for stale_key in (
                "official_candidate_shortlist",
                "auxiliary_service_candidates",
                "consultation_packet",
                "report_result",
                "report_download_payload",
            ):
                self.assertNotIn(stale_key, app.session_state)

            visible_text = " ".join(item.value for item in app.markdown)
            self.assertNotIn("단기수출보험 검토", visible_text)
            self.assertNotIn("KB Star FX 선물환·외환스왑 상담", visible_text)
            self.assertNotIn(
                "상담 준비서 PDF 다운로드",
                [
                    item.label
                    for item in app.get("download_button")
                ],
            )

    def test_stage3_internal_failure_is_persistent_and_actionable(self):
        from streamlit.testing.v1 import AppTest

        environment = {
            "APP_ENV": "presentation",
            "OPENAI_API_KEY": "",
            "ENABLE_LIVE_DOCUMENT_EXTRACTION": "false",
            "ENABLE_LLM_REPORT": "false",
            "ENABLE_OFFICIAL_WEB_SEARCH": "false",
            "STAGE1_MODE": "manual",
        }
        with patch.dict(os.environ, environment, clear=False):
            app = AppTest.from_file(
                "app.py",
                default_timeout=30,
            ).run(timeout=30)
            self._confirm_document(app)
            self._run_stage1_and_trade_risk(app)
            self._run_golden_cashflow(app)

            workflow = WorkflowState.model_validate(
                app.session_state["workflow_state"]
            )
            workflow.hedge = StageResult[Stage3Result](
                status=StageStatus.FAILED,
                errors=["hedge 단계 실패 (RuntimeError)"],
                provider="grid_hedge_optimizer",
            )
            workflow.product_search = None
            workflow.report = None
            workflow.final_report = None
            app.session_state["workflow_state"] = workflow.model_dump()
            app.session_state["active_page"] = "consultation"
            if "stage3_result" in app.session_state:
                del app.session_state["stage3_result"]
            app.run(timeout=30)

            self.assertEqual(len(app.exception), 0)
            visible_errors = " ".join(
                item.value for item in app.error
            )
            self.assertIn("시스템 오류", visible_errors)
            self.assertIn("헤지 대응안 비교", visible_errors)
            technical = " ".join(
                item.value for item in app.markdown
            )
            self.assertNotIn("STAGE3_UNEXPECTED_ERROR", technical)
            self.assertNotIn("stage3.hedge", technical)
            self.assertNotIn(
                workflow.confirmed_transaction.input_fingerprint,
                technical,
            )
            self.assertNotIn("Traceback", technical)
