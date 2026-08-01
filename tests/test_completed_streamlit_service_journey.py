import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from src.application.registered_document_service import (
    extract_registered_document,
    presentation_document,
)
from src.application.stage2_input_service import (
    CashflowValidationError,
    Stage2FormInput,
    build_validated_stage2_input_from_form,
    classify_cashflow_error,
)
from src.config import Settings
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

    def test_registered_document_uses_content_identity_without_api(self):
        registered = presentation_document()
        result = extract_registered_document(
            file_bytes=registered.file_bytes,
            filename="renamed-upload.pdf",
            mime_type=registered.mime_type,
            company_role="SELLER",
            company_country="KR",
            settings=Settings(
                app_env="presentation",
                openai_api_key=None,
                enable_live_document_extraction=False,
            ),
        )

        self.assertIsNotNone(result)
        self.assertEqual(
            result.usage.model,
            "registered_api_free_fixture",
        )
        self.assertEqual(result.extraction.contract_date, "2026-07-29")
        self.assertEqual(result.extraction.shipment_date, "2026-08-05")
        self.assertEqual(result.extraction.explicit_due_date, "2026-08-20")
        self.assertEqual(result.extraction.amount_due, "100000.00")
        self.assertFalse(result.validation.stage2_allowed)

    def test_registered_document_corrects_wrong_default_role_from_source(self):
        registered = presentation_document()
        result = extract_registered_document(
            file_bytes=registered.file_bytes,
            filename=registered.filename,
            mime_type=registered.mime_type,
            company_role="BUYER",
            company_country="KR",
            settings=Settings(
                app_env="presentation",
                openai_api_key=None,
                enable_live_document_extraction=False,
            ),
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.auto_matched_company_role, "SELLER")
        self.assertEqual(result.extraction.company_role, "SELLER")
        self.assertEqual(result.extraction.trade_type, "EXPORT")
        self.assertNotIn(
            "COMPANY_COUNTRY_ROLE_MISMATCH",
            {item.code for item in result.validation.issues},
        )

    def test_registered_document_is_available_only_in_demo_boundaries(self):
        registered = presentation_document()
        development_result = extract_registered_document(
            file_bytes=registered.file_bytes,
            filename=registered.filename,
            mime_type=registered.mime_type,
            company_role="SELLER",
            company_country="KR",
            settings=Settings(
                app_env="development",
                demo_mode=True,
                openai_api_key=None,
                enable_live_document_extraction=False,
            ),
        )
        production_result = extract_registered_document(
            file_bytes=registered.file_bytes,
            filename=registered.filename,
            mime_type=registered.mime_type,
            company_role="SELLER",
            company_country="KR",
            settings=Settings(
                app_env="production",
                demo_mode=False,
                openai_api_key=None,
                enable_live_document_extraction=False,
            ),
        )

        self.assertIsNotNone(development_result)
        self.assertIsNone(production_result)

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
        _by_key(app.button, "analyze_document").click().run(timeout=30)
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
                "원문과 확인하고 금융분석 시작"
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
                "결제·회수 위험 확인"
            ),
        ).click().run(timeout=30)

    @staticmethod
    def _run_golden_cashflow(app):
        expected_text_defaults = {
            "stage2_current_cash_widget": "20000000.00",
            "stage2_minimum_buffer_widget": "10000000.00",
            "stage2_credit_limit_widget": "0.00",
            "stage2_acceptable_loss_widget": "5000000.00",
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

    def test_click_journey_reaches_report_then_invalidates_and_resets(self):
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

            self.assertEqual(len(app.exception), 0)
            self.assertEqual(
                _state(app, "upload_metadata")["provider"],
                "registered_api_free_fixture",
            )
            snapshot = _state(app, "confirmed_transaction")
            self.assertEqual(_state(app, "active_page"), "analysis")
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
            packet = _state(app, "consultation_packet")["packet"]
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
                    item["title"]
                    for item in packet["consultation_priorities"]
                ],
                [
                    "수출대금 회수 보호 상담",
                    "환율 관리 상담",
                    "운영자금 버퍼·수출대금 회수시점 상담",
                ],
            )
            self.assertEqual(
                packet["protection_summary"][
                    "advance_payment_receipt"
                ],
                "UNKNOWN",
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
                "허용손실 5,000,000원 초과",
                "스트레스 후 예상 현금 8,000,000원",
                "목표 버퍼 10,000,000원",
                "버퍼 부족 2,000,000원",
                "현금 적자 0원",
                "지급 또는 post-credit 부족 0원",
                "USD 80,000",
                "Open Account / T/T",
            ):
                self.assertIn(expected, result_cards[0])
            consultation_cards = [
                item.value
                for item in app.markdown
                if "<div class='consultation-card'>" in item.value
            ]
            self.assertEqual(len(consultation_cards), 3)
            for card, title in zip(
                consultation_cards,
                [
                    "수출대금 회수 보호 상담",
                    "환율 관리 상담",
                    "운영자금 버퍼·수출대금 회수시점 상담",
                ],
            ):
                self.assertIn(title, card)
                self.assertIn("상담에서 결정할 사항", card)
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
                self.assertIn(
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
                    ("KB국민은행", "은행 선물환·외환스왑 상담"),
                    ("한국무역보험공사", "환변동보험 검토"),
                ],
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
            self.assertIn("상담 준비서 다운로드", labels)
            self.assertIn("JSON 다운로드", labels)
            self.assertIn("통합 보고서 다운로드", labels)

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
            self.assertIn("STAGE3_UNEXPECTED_ERROR", technical)
            self.assertIn("stage3.hedge", technical)
            self.assertIn(
                workflow.confirmed_transaction.input_fingerprint,
                technical,
            )
            self.assertNotIn("Traceback", technical)
