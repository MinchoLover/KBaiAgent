import copy
import hashlib
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from schemas import PaymentInstallment
from scripts.verify_golden_user_flow import (
    build_golden_user_flow_artifacts,
    golden_user_flow_summary,
)
from src.application.stage2_input_service import (
    CashflowValidationError,
    validate_stage2_as_of_date,
)
from src.config import Settings
from src.document_intake.confirmation import create_confirmation_record
from src.stage2.binding import (
    confirmed_analysis_due_date_from_document_input,
    validate_downstream_due_date,
)
from src.ui.state import (
    PIPELINE_KEYS,
    clear_confirmation_and_later,
    clear_downstream,
    input_signature,
    sync_input_signature,
)
from src.workflow.orchestrator import WorkflowOrchestrator


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PDF = (
    ROOT / "dataset" / "golden_demo" / "golden_export_contract.pdf"
)


class GoldenConfirmedTransactionE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = build_golden_user_flow_artifacts()
        cls.summary = golden_user_flow_summary()

    def test_contract_and_shipment_dates_never_replace_confirmed_due_date(self):
        dates = self.summary["dates"]
        self.assertEqual(dates["contract_date"], "2026-07-29")
        self.assertEqual(dates["shipment_date"], "2026-08-05")
        for field in (
            "confirmed_ui_due_date",
            "document_input_due_date",
            "stage1_target_date",
            "stage2_date",
            "consultation_packet_date",
            "stage5_date",
        ):
            self.assertEqual(dates[field], "2026-08-20", field)

    def test_document_input_preserves_installments_as_schedule_only(self):
        document_input = self.artifacts["golden"]["document_input"]
        trade = document_input["trade"]
        schedule = trade["installment_schedule"]

        self.assertEqual(trade["settlement_date"], "2026-08-20")
        self.assertEqual(len(trade["cashflow_events"]), 1)
        self.assertEqual(
            trade["cashflow_events"][0]["foreign_amount"],
            "100000.00",
        )
        self.assertEqual(
            sum(
                (
                    Decimal(item["foreign_amount"])
                    for item in schedule
                ),
                Decimal("0"),
            ),
            Decimal("100000.00"),
        )
        self.assertEqual(
            [item["foreign_amount"] for item in schedule],
            ["20000.00", "80000.00"],
        )
        self.assertEqual(
            trade["settlement_date_source"],
            "workflow.confirmed_transaction.due_date",
        )

    def test_golden_financial_values_and_consultation_order_are_unchanged(self):
        financials = self.summary["down_5_financials_krw"]
        self.assertEqual(financials["receipt_loss"], "7000000.00")
        self.assertEqual(financials["ending_cash"], "8000000.00")
        self.assertEqual(
            financials["minimum_cash_buffer"],
            "10000000.00",
        )
        self.assertEqual(financials["buffer_shortfall"], "2000000.00")
        self.assertEqual(financials["cash_deficit"], "0.00")
        self.assertEqual(financials["post_credit_shortfall"], "0.00")
        self.assertEqual(
            [
                item["title"]
                for item in self.summary["consultation_top_3"]
            ],
            [
                "수출대금 회수 보호 상담",
                "환율 관리 상담",
                "운영자금 버퍼·수출대금 회수시점 상담",
            ],
        )
        self.assertLessEqual(
            self.summary["official_candidate_unique_count"],
            3,
        )

    def test_scheduled_exposure_is_not_actual_outstanding_balance(self):
        amounts = self.summary["amounts"]
        self.assertEqual(amounts["scheduled_exposure_usd"], "100000.00")
        self.assertEqual(amounts["balance_installment_usd"], "80000.00")
        self.assertEqual(amounts["advance_receipt_status"], "UNKNOWN")
        self.assertNotEqual(
            amounts["scheduled_exposure_usd"],
            amounts["balance_installment_usd"],
        )

    def test_past_due_date_is_blocked_with_structured_error(self):
        stage2_input = self.artifacts["golden"][
            "stage2_input"
        ].model_copy(
            update={"as_of_date": "2026-08-21"}
        )

        with self.assertRaises(CashflowValidationError) as raised:
            validate_stage2_as_of_date(stage2_input)

        detail = raised.exception.detail
        self.assertEqual(detail.code, "INVALID_DATE_ORDER")
        self.assertEqual(detail.due_date, "2026-08-20")
        self.assertEqual(detail.cashflow_base_date, "2026-08-21")
        self.assertEqual(
            detail.field_path,
            "stage2.exposures[].settlement_date",
        )
        self.assertEqual(detail.offending_value, "2026-08-20")
        self.assertIsNotNone(detail.input_fingerprint)

    def test_cashflow_engine_failure_retains_structured_inputs(self):
        state = self.artifacts["workflow"].model_copy(deep=True)
        bad_input = self.artifacts["golden"]["stage2_input"].model_copy(
            update={
                "as_of_date": "2026-08-21",
                "krw_cashflows": [],
            }
        )
        orchestrator = WorkflowOrchestrator(
            settings=Settings(
                openai_api_key=None,
                enable_live_document_extraction=False,
                enable_official_web_search=False,
                enable_llm_report=False,
            )
        )

        state = orchestrator.run_cashflow(state, bad_input)

        self.assertIsNotNone(state.cashflow_error)
        self.assertEqual(
            state.cashflow_error.code,
            "INVALID_DATE_ORDER",
        )
        self.assertEqual(state.cashflow_error.due_date, "2026-08-20")
        self.assertEqual(
            state.cashflow_error.cashflow_base_date,
            "2026-08-21",
        )
        self.assertIsNone(state.cashflow.data)

    def test_stage1_rejects_contract_date_as_target_date(self):
        state = self.artifacts["workflow"].model_copy(deep=True)
        orchestrator = WorkflowOrchestrator(
            settings=Settings(
                openai_api_key=None,
                enable_live_document_extraction=False,
                enable_official_web_search=False,
                enable_llm_report=False,
            )
        )

        state = orchestrator.run_market_risk(
            state,
            expected_currency="USD",
            expected_target_date="2026-07-29",
            manual_base_rate="1400",
            mode="MANUAL_STRESS",
        )

        self.assertIsNone(state.market_risk.data)
        self.assertIn(
            "확정 결제일과 일치하지 않습니다",
            state.market_risk.errors[0],
        )

    def test_missing_canonical_due_date_does_not_fallback_to_first_event(self):
        document_input = copy.deepcopy(
            self.artifacts["golden"]["document_input"]
        )
        document_input["trade"]["settlement_date"] = None
        self.assertEqual(
            document_input["trade"]["cashflow_events"][0][
                "settlement_date"
            ],
            "2026-08-20",
        )

        with self.assertRaisesRegex(
            ValueError,
            "대신 사용하지 않습니다",
        ):
            confirmed_analysis_due_date_from_document_input(
                document_input
            )

    def test_downstream_date_contract_fails_closed_on_any_divergence(self):
        golden = self.artifacts["golden"]
        self.assertEqual(
            validate_downstream_due_date(
                confirmation=golden["confirmation"],
                stage1_target_date="2026-08-20",
                stage2_dates=["2026-08-20"],
            ),
            "2026-08-20",
        )
        with self.assertRaisesRegex(ValueError, "Stage 1 target_date"):
            validate_downstream_due_date(
                confirmation=golden["confirmation"],
                stage1_target_date="2026-07-29",
                stage2_dates=["2026-08-20"],
            )

    def test_due_date_edit_replaces_snapshot_and_invalidates_old_results(self):
        golden = self.artifacts["golden"]
        extraction = golden["extraction"]
        installments = list(extraction.installments)
        installments[1] = PaymentInstallment(
            sequence=2,
            amount="80000.00",
            currency="USD",
            due_date="2026-08-21",
            condition=installments[1].condition,
        )
        edited = extraction.model_copy(
            update={
                "explicit_due_date": "2026-08-21",
                "installments": installments,
            }
        )
        record = create_confirmation_record(
            original=extraction,
            confirmed=edited,
            confirmed_due_date="2026-08-21",
            currency_confirmed=True,
            amount_due_confirmed=True,
            due_date_confirmed=True,
            source_filename="golden_export_contract.pdf",
            source_sha256=hashlib.sha256(
                GOLDEN_PDF.read_bytes()
            ).hexdigest(),
            company_country="KR",
            company_role_confirmed=True,
            trade_type_confirmed=True,
            confirmed_by="state-regression-test",
            confirmed_at="2026-07-29T10:00:00+09:00",
        )
        self.assertEqual(
            record.confirmed_values["settlement_date"],
            "2026-08-21",
        )

        state = {
            "confirmation": golden["confirmation"].model_dump(),
            "stage1_load": {"target_date": "2026-08-20"},
            "stage2_input": {"date": "2026-08-20"},
            "stage2_result": {"date": "2026-08-20"},
            "cashflow_error": {"code": "stale"},
            "consultation_packet": {"date": "2026-08-20"},
            "report_result": {"date": "2026-08-20"},
        }
        clear_confirmation_and_later(state)
        for key in (
            "confirmation",
            "stage1_load",
            "stage2_input",
            "stage2_result",
            "cashflow_error",
            "consultation_packet",
            "report_result",
        ):
            self.assertNotIn(key, state)

    def test_new_document_signature_removes_other_transaction_state(self):
        state = {
            key: {"stale": True}
            for key in PIPELINE_KEYS
        }
        first = input_signature(
            mode="DEMO",
            company_role="SELLER",
            company_country="KR",
            filename="us_sample.pdf",
            file_bytes=b"us",
        )
        second = input_signature(
            mode="LIVE",
            company_role="SELLER",
            company_country="KR",
            filename="golden_export_contract.pdf",
            file_bytes=b"golden",
        )
        state["input_signature"] = first

        self.assertTrue(sync_input_signature(state, second))
        for key in PIPELINE_KEYS:
            self.assertNotIn(key, state)
        self.assertEqual(state["input_signature"], second)

    def test_submitted_stage2_edit_invalidates_results_but_keeps_widgets(self):
        state = {
            "stage2_input": {"date": "old"},
            "stage2_result": {"date": "old"},
            "cashflow_error": {"code": "old"},
            "stage3_result": {"candidate": "old"},
            "consultation_packet": {"date": "old"},
            "report_result": {"date": "old"},
            "stage2_as_of_widget": "2026-08-21",
            "stage2_current_cash_widget": "20000000",
        }

        clear_downstream(state, 2, clear_widgets=False)

        for key in (
            "stage2_input",
            "stage2_result",
            "cashflow_error",
            "stage3_result",
            "consultation_packet",
            "report_result",
        ):
            self.assertNotIn(key, state)
        self.assertEqual(
            state["stage2_as_of_widget"],
            "2026-08-21",
        )
        self.assertEqual(
            state["stage2_current_cash_widget"],
            "20000000",
        )

    def test_golden_pdf_and_flow_are_api_free(self):
        self.assertEqual(
            hashlib.sha256(GOLDEN_PDF.read_bytes()).hexdigest(),
            "5330a1a572488005f7b02cccfc7150fbaa8b38c84bb9290da1e0c6e1c3a0a91c",
        )
        self.assertTrue(self.summary["api_free"])
        self.assertFalse(self.summary["external_network_used"])
        self.assertTrue(
            all(
                value in {"SUCCEEDED", "FALLBACK"}
                for value in self.summary["steps"].values()
            )
        )


class GoldenStreamlitStateTests(unittest.TestCase):
    def test_cashflow_error_is_actionable_and_has_safe_technical_detail(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=30).run()
        sample = next(
            item
            for item in app.button
            if item.key == "service_sample_export"
        )
        sample.click().run()
        app.session_state["cashflow_error"] = {
            "code": "INVALID_DATE_ORDER",
            "stage": "cashflow",
            "user_message": (
                "확정 결제일(2026-08-20)이 현금 계산 기준일"
                "(2026-08-21)보다 이전입니다. 거래 확인 단계의 "
                "결제일과 계산 기준일을 다시 확인하세요."
            ),
            "input_fingerprint": "a" * 64,
            "due_date": "2026-08-20",
            "cashflow_base_date": "2026-08-21",
            "field_path": "stage2.exposures[].settlement_date",
            "exception_type": "ValueError",
        }
        app.run()

        self.assertEqual(len(app.exception), 0)
        errors = " ".join(item.value for item in app.error)
        self.assertIn("결제일과 계산 기준일을 다시 확인", errors)
        self.assertIn(
            "오류 기술 정보",
            [item.label for item in app.expander],
        )
        technical = " ".join(item.value for item in app.markdown)
        self.assertIn("INVALID_DATE_ORDER", technical)
        self.assertNotIn("Traceback", technical)

    def test_new_analysis_clears_all_sample_pipeline_state(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=30).run()
        sample = next(
            item
            for item in app.button
            if item.key == "service_sample_export"
        )
        sample.click().run()
        before_keys = {
            key
            for key in PIPELINE_KEYS
            if key in app.session_state
        }
        self.assertIn("stage2_result", before_keys)
        self.assertIn("consultation_packet", before_keys)

        reset = next(
            item
            for item in app.button
            if item.label == "새 분석 시작"
        )
        reset.click().run()

        self.assertEqual(len(app.exception), 0)
        after_keys = {
            key
            for key in PIPELINE_KEYS
            if key in app.session_state
        }
        self.assertEqual(after_keys, set())

    def test_import_buyer_to_export_seller_demo_does_not_mix_state(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=30).run()
        import_demo = next(
            item
            for item in app.button
            if item.label == "수입기업 대표 데모"
        )
        import_demo.click().run()
        self.assertEqual(
            app.session_state["extraction"]["trade_type"],
            "IMPORT",
        )
        app.session_state["kb_macro_hedge_reference"] = {
            "status": "stale"
        }
        export_demo = next(
            item
            for item in app.button
            if item.label == "미국 수출 샘플"
        )
        export_demo.click().run()

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(
            app.session_state["extraction"]["company_role"],
            "SELLER",
        )
        self.assertEqual(
            app.session_state["extraction"]["trade_type"],
            "EXPORT",
        )
        self.assertNotIn(
            "kb_macro_hedge_reference",
            app.session_state,
        )

    def test_golden_confirmed_date_matches_rendered_stage_inputs(self):
        from streamlit.testing.v1 import AppTest

        artifacts = build_golden_user_flow_artifacts()
        golden = artifacts["golden"]
        workflow = artifacts["workflow"]
        decision = artifacts["decision"]
        report = artifacts["report"]
        with patch.dict(
            "os.environ",
            {
                "APP_ENV": "presentation",
                "ENABLE_LIVE_DOCUMENT_EXTRACTION": "false",
                "ENABLE_LLM_REPORT": "false",
            },
        ):
            app = AppTest.from_file(
                "app.py",
                default_timeout=30,
            ).run()
            app.session_state["run_mode_widget"] = "실제 문서 분석"
            app.session_state["company_role_widget"] = "판매자 · SELLER"
            app.session_state["company_country_widget"] = "KR"
            app.session_state["input_signature"] = input_signature(
                mode="LIVE",
                company_role="SELLER",
                company_country="KR",
                filename="uploaded_document",
                file_bytes=b"",
            )
            app.session_state["extraction"] = golden[
                "extraction"
            ].model_dump()
            app.session_state["extraction_original"] = golden[
                "extraction"
            ].model_dump()
            app.session_state["extraction_validation"] = golden[
                "validation"
            ].model_dump()
            app.session_state["confirmation"] = golden[
                "confirmation"
            ].model_dump()
            app.session_state["confirmation_validation"] = golden[
                "validation"
            ].model_dump()
            app.session_state["upload_metadata"] = {
                "filename": "golden_export_contract.pdf",
                "mime_type": "application/pdf",
                "size_bytes": GOLDEN_PDF.stat().st_size,
                "sha256": hashlib.sha256(
                    GOLDEN_PDF.read_bytes()
                ).hexdigest(),
                "page_count": 2,
            }
            app.session_state["stage2_document_input"] = golden[
                "document_input"
            ]
            app.session_state["stage1_load"] = (
                workflow.market_risk.data.model_dump()
            )
            app.session_state["stage2_input"] = golden[
                "stage2_input"
            ].model_dump()
            app.session_state["stage2_result"] = (
                workflow.cashflow.data.model_dump()
            )
            app.session_state["trade_risk_assessment"] = golden[
                "trade_risk"
            ].model_dump()
            app.session_state["country_environment_assessment"] = golden[
                "country_environment"
            ].model_dump()
            app.session_state["risk_assessment"] = (
                decision.risk_assessment.model_dump()
            )
            app.session_state["consultation_topics"] = [
                item.model_dump()
                for item in decision.consultation_topics
            ]
            app.session_state["consultation_packet"] = (
                decision.consultation_packet.model_dump()
            )
            app.session_state["stage3_result"] = (
                workflow.hedge.data.model_dump()
            )
            app.session_state["stage4_result"] = (
                workflow.product_search.data.model_dump()
            )
            app.session_state["official_candidate_shortlist"] = (
                artifacts["shortlist"].model_dump()
            )
            app.session_state["report_result"] = report.model_dump()
            app.session_state["workflow_state"] = workflow.model_dump()
            app.session_state["active_page"] = "analysis"
            app.run()

        self.assertEqual(len(app.exception), 0)
        visible = " ".join(
            [item.value for item in app.markdown]
            + [item.value for item in app.caption]
            + [
                "{} {}".format(item.label, item.value)
                for item in app.metric
            ]
        )
        self.assertIn("결제 예정일 2026-08-20", visible)
        self.assertIn("결제일 2026-08-20", visible)
        self.assertIn("확정 결제일 2026-08-20", visible)
        self.assertIn("브라질", visible)
        self.assertNotIn("미국 수출 샘플의 전체 분석 결과", visible)
        downloads = [
            item.label for item in app.get("download_button")
        ]
        self.assertIn("상담 준비서 다운로드", downloads)
        self.assertIn("JSON 데이터 다운로드", downloads)
        self.assertLess(
            downloads.index("상담 준비서 다운로드"),
            downloads.index("JSON 데이터 다운로드"),
        )


if __name__ == "__main__":
    unittest.main()
