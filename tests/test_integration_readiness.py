import hashlib
import os
import subprocess
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from src.application.integration_readiness_service import (
    build_integration_readiness_report,
    build_single_usd_import_readiness_fixture,
)
from src.application.kb_macro_hedge_service import (
    SUPPORTED_PROVIDER_COMMIT_SHA,
    inspect_kb_macro_exposure_support,
)
from src.config import Settings
from src.domain.kb_macro_hedge_models import (
    KbMacroHedgeCandidate,
    KbMacroHedgeProvenance,
    KbMacroHedgeReferenceResult,
    KbMacroHedgeValidation,
)
from src.stage1.forecast_provider import (
    FileStage1ForecastProvider,
    HttpStage1ForecastProvider,
    MockStage1ForecastProvider,
    Stage1ForecastService,
)
from src.ui.state import clear_downstream


ROOT = Path(__file__).resolve().parents[1]
STAGE1_FIXTURE = (
    ROOT
    / "src"
    / "integration_assets"
    / "stage1"
    / "latest_forecast.json"
)
NOW = datetime(2026, 7, 27, 9, 0, tzinfo=timezone.utc)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _PinnedRoot:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = {}
        for relative, content in (
            ("forecast.json", b'{"forecast":"fixture"}\n'),
            ("model.json", b'{"schema_version":"fixture"}\n'),
            ("history.csv", b"date,rate\n2026-07-29,1400\n"),
            ("quote.json", b'{"quotes":"mock"}\n'),
        ):
            path = self.root / relative
            path.write_bytes(content)
            self.paths[relative] = path
        python = self.root / ".venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text("#!/bin/sh\n", encoding="utf-8")
        python.chmod(0o700)
        module = (
            self.root
            / "src"
            / "krw_forecast"
            / "hedge_recommendation_v1_cli.py"
        )
        module.parent.mkdir(parents=True)
        module.write_text("# fixture\n", encoding="utf-8")

    def settings(self) -> Settings:
        return Settings(
            enable_kb_macro_hedge_reference=True,
            kb_macro_hedge_mode="local_cli",
            kb_macro_hedge_allowed_root=str(self.root),
            kb_macro_forecast_file="forecast.json",
            kb_macro_model_config_file="model.json",
            kb_macro_market_history_file="history.csv",
            kb_macro_quote_template_file="quote.json",
            kb_macro_expected_provider_commit_sha=(
                SUPPORTED_PROVIDER_COMMIT_SHA
            ),
            kb_macro_expected_forecast_sha256=_sha256(
                self.paths["forecast.json"]
            ),
            kb_macro_expected_model_config_sha256=_sha256(
                self.paths["model.json"]
            ),
            kb_macro_expected_market_history_sha256=_sha256(
                self.paths["history.csv"]
            ),
            kb_macro_expected_quote_template_sha256=_sha256(
                self.paths["quote.json"]
            ),
            stage1_provider="file",
            stage1_forecast_file=str(STAGE1_FIXTURE),
            spot_rate_provider="fixture",
            demo_mode=True,
        )

    def cleanup(self) -> None:
        self.temporary.cleanup()


def _clean_git_runner(command, **unused_kwargs):
    stdout = (
        (SUPPORTED_PROVIDER_COMMIT_SHA + "\n").encode("utf-8")
        if "rev-parse" in command
        else b""
    )
    return subprocess.CompletedProcess(
        command,
        0,
        stdout=stdout,
        stderr=b"",
    )


def _candidate(rank: int) -> KbMacroHedgeCandidate:
    return KbMacroHedgeCandidate(
        rank=rank,
        strategy_type=(
            "forward_only"
            if rank == 1
            else "forward_and_call_option"
        ),
        forward_ratio="1" if rank == 1 else "0.5",
        call_option_ratio="0" if rank == 1 else "0.5",
        unhedged_ratio="0",
        forward_notional_usd="90000" if rank == 1 else "45000",
        call_option_notional_usd="0" if rank == 1 else "45000",
        unhedged_notional_usd="0",
        option_premium_krw="0",
        expected_cost_krw=str(130000000 + rank),
        cvar_95_cost_krw=str(140000000 + rank),
        objective_score_krw=str(150000000 + rank),
    )


def _successful_local_cli_result() -> KbMacroHedgeReferenceResult:
    return KbMacroHedgeReferenceResult(
        status="REFERENCE_ONLY",
        provider_mode="local_cli",
        pricing_status="MOCK",
        validation=KbMacroHedgeValidation(
            passed=True,
            checks=[],
            failed_checks=[],
            warnings=[],
        ),
        candidates=[_candidate(1), _candidate(2), _candidate(3)],
        provenance=KbMacroHedgeProvenance(
            producer_commit_sha=SUPPORTED_PROVIDER_COMMIT_SHA,
            request_sha256="1" * 64,
            forecast_sha256="2" * 64,
            hedge_sha256="3" * 64,
            forecast_schema_version="krw_forecast_web_v1",
            hedge_schema_version="krw_hedge_recommendation_v1",
            prediction_date="2026-07-29",
            horizon_trading_days=21,
            forecast_filename="forecast.json",
            hedge_filename="hedge.json",
            execution_method="PINNED_LOCAL_CLI",
        ),
        warnings=[
            "MOCK_QUOTES",
            "TEMPORARY_RAW_OUTPUT_DELETED",
        ],
    )


class IntegrationReadinessServiceTests(unittest.TestCase):
    def test_default_off_is_explicit_and_does_not_touch_provider(self):
        def forbidden_runner(unused_command, **unused_kwargs):
            raise AssertionError("provider must not run in off mode")

        report = build_integration_readiness_report(
            settings=Settings(
                stage1_provider="file",
                stage1_forecast_file=str(STAGE1_FIXTURE),
                spot_rate_provider="fixture",
                demo_mode=True,
            ),
            active_stage1_check=False,
            command_runner=forbidden_runner,
            now=NOW,
        )

        self.assertEqual(report.status, "DISABLED")
        self.assertEqual(report.kb_macro_hedge.status, "DISABLED")
        self.assertFalse(report.kb_macro_hedge.feature_enabled)
        self.assertEqual(
            report.kb_macro_hedge.configured_mode,
            "off",
        )

    def test_stage1_freshness_and_spot_source_are_sanitized(self):
        secret = "readiness-secret-must-not-appear"
        report = build_integration_readiness_report(
            settings=Settings(
                stage1_provider="file",
                stage1_forecast_file=str(STAGE1_FIXTURE),
                spot_rate_provider="koreaexim",
                koreaexim_key=secret,
            ),
            now=NOW,
        )
        serialized = report.model_dump_json()

        self.assertIn(report.stage1.status, {"READY", "DEGRADED"})
        self.assertTrue(report.stage1.forecast_fresh)
        self.assertEqual(
            report.spot.configured_source,
            "KOREAEXIM_DEAL_BASE_RATE",
        )
        self.assertTrue(report.spot.credential_configured)
        self.assertFalse(report.spot.external_call_performed)
        self.assertFalse(report.secret_values_exposed)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("Authorization", serialized)

        from scripts.check_integration_readiness import _human_lines

        human = "\n".join(_human_lines(report))
        self.assertNotIn(secret, human)
        self.assertIn("API key values: NOT INCLUDED", human)
        self.assertIn("upstream_partial_fallback_used", human)

    def test_http_failure_discloses_file_fallback(self):
        def timeout(
            unused_url,
            unused_timeout,
            unused_maximum,
        ):
            raise TimeoutError("fixture")

        service = Stage1ForecastService(
            http_provider=HttpStage1ForecastProvider(
                fetcher=timeout,
                retries=0,
            ),
            file_provider=FileStage1ForecastProvider(STAGE1_FIXTURE),
            mock_provider=MockStage1ForecastProvider(STAGE1_FIXTURE),
            maximum_path_return=Decimal("0.50"),
            max_staleness_market_days=3,
        )
        report = build_integration_readiness_report(
            settings=Settings(
                stage1_provider="http",
                stage1_forecast_file=str(STAGE1_FIXTURE),
                spot_rate_provider="fixture",
                demo_mode=True,
            ),
            forecast_service=service,
            now=NOW,
        )

        self.assertEqual(report.stage1.status, "DEGRADED")
        self.assertEqual(report.stage1.active_source, "FILE_FALLBACK")
        self.assertTrue(report.stage1.fallback_used)
        self.assertIn(
            "FALLBACK_USED",
            " ".join(report.stage1.warnings),
        )

    def test_local_cli_commit_and_all_asset_hashes_are_visible(self):
        pinned = _PinnedRoot()
        try:
            stage2_input, unused_result = (
                build_single_usd_import_readiness_fixture()
            )
            del unused_result
            report = build_integration_readiness_report(
                settings=pinned.settings(),
                stage2_input=stage2_input,
                active_stage1_check=False,
                command_runner=_clean_git_runner,
                now=NOW,
            )
        finally:
            pinned.cleanup()

        macro = report.kb_macro_hedge
        self.assertEqual(macro.status, "READY")
        self.assertEqual(
            macro.actual_producer_commit_sha,
            SUPPORTED_PROVIDER_COMMIT_SHA,
        )
        self.assertTrue(macro.producer_commit_matches)
        self.assertTrue(macro.tracked_worktree_clean)
        self.assertTrue(macro.cli_available)
        self.assertTrue(macro.exposure.supported)
        self.assertEqual(len(macro.assets), 4)
        self.assertTrue(
            all(item.sha256_matches is True for item in macro.assets)
        )

    def test_sha_mismatch_blocks_provider_without_running_model(self):
        pinned = _PinnedRoot()
        settings = replace(
            pinned.settings(),
            kb_macro_expected_forecast_sha256="0" * 64,
        )
        try:
            report = build_integration_readiness_report(
                settings=settings,
                active_stage1_check=False,
                command_runner=_clean_git_runner,
                now=NOW,
            )
        finally:
            pinned.cleanup()

        self.assertEqual(report.kb_macro_hedge.status, "BLOCKED")
        forecast = next(
            item
            for item in report.kb_macro_hedge.assets
            if item.asset == "forecast"
        )
        self.assertFalse(forecast.sha256_matches)

    def test_export_is_unsupported_without_changing_stage2(self):
        stage2_input, stage2_result = (
            build_single_usd_import_readiness_fixture()
        )
        original_input = stage2_input.model_dump()
        original_result = stage2_result.model_dump()
        export_exposure = stage2_input.exposures[0].model_copy(
            update={"trade_type": "EXPORT"}
        )
        export_input = stage2_input.model_copy(
            update={"exposures": [export_exposure]}
        )

        supported = inspect_kb_macro_exposure_support(stage2_input)
        unsupported = inspect_kb_macro_exposure_support(export_input)

        self.assertTrue(supported.passed)
        self.assertFalse(unsupported.passed)
        self.assertIn("USD_PAYABLE_ONLY", unsupported.failed_checks)
        self.assertEqual(stage2_input.model_dump(), original_input)
        self.assertEqual(stage2_result.model_dump(), original_result)
        self.assertEqual(
            Decimal(stage2_result.total_foreign_amount),
            Decimal("100000.00"),
        )
        self.assertEqual(
            Decimal(stage2_result.open_exposure),
            Decimal("90000.00"),
        )

    def test_stage2_change_invalidates_transaction_readiness_snapshot(self):
        state = {
            "stage2_input": {"fixture": True},
            "integration_readiness": {"status": "READY"},
            "stage3_result": {"status": "SIMULATED_CANDIDATE"},
        }

        clear_downstream(state, 2, clear_widgets=False)

        self.assertNotIn("stage2_input", state)
        self.assertNotIn("integration_readiness", state)
        self.assertNotIn("stage3_result", state)

    def test_explicit_local_cli_e2e_uses_fixed_import_fixture(self):
        pinned = _PinnedRoot()
        try:
            with patch(
                (
                    "src.application.integration_readiness_service."
                    "run_kb_macro_hedge_for_confirmed_trade"
                ),
                return_value=_successful_local_cli_result(),
            ) as runner:
                report = build_integration_readiness_report(
                    settings=pinned.settings(),
                    active_stage1_check=False,
                    run_local_cli_e2e=True,
                    command_runner=_clean_git_runner,
                    now=NOW,
                )
        finally:
            pinned.cleanup()

        e2e = report.kb_macro_hedge.local_cli_e2e
        self.assertIsNotNone(e2e)
        assert e2e is not None
        self.assertEqual(e2e.status, "READY")
        self.assertTrue(e2e.executed)
        self.assertTrue(e2e.api_free)
        self.assertEqual(e2e.candidate_count, 3)
        self.assertEqual(e2e.candidate_ranks, [1, 2, 3])
        self.assertTrue(e2e.temporary_raw_output_deleted)
        call = runner.call_args.kwargs
        self.assertEqual(
            call["stage2_input"].exposures[0].foreign_amount,
            "100000",
        )
        self.assertEqual(
            call["stage2_input"].exposures[0].trade_type,
            "IMPORT",
        )
        self.assertTrue(call["constraints_confirmed"])


class IntegrationReadinessStreamlitTests(unittest.TestCase):
    def test_sidebar_check_renders_without_secret_or_external_api(self):
        from streamlit.testing.v1 import AppTest

        environment = {
            "APP_ENV": "development",
            "STAGE1_PROVIDER": "file",
            "STAGE1_FORECAST_FILE": str(STAGE1_FIXTURE),
            "SPOT_RATE_PROVIDER": "fixture",
            "DEMO_MODE": "true",
            "ENABLE_KB_MACRO_HEDGE_REFERENCE": "false",
            "KB_MACRO_HEDGE_MODE": "off",
        }
        with patch.dict(os.environ, environment, clear=False):
            app = AppTest.from_file(
                str(ROOT / "app.py"),
                default_timeout=30,
            ).run()
            button = next(
                item
                for item in app.button
                if item.key == "check_integration_readiness"
            )
            button.click().run()

        self.assertEqual(len(app.exception), 0)
        stored = app.session_state["integration_readiness"]
        self.assertFalse(stored["secret_values_exposed"])
        self.assertEqual(
            stored["stage1"]["configured_provider"],
            "file",
        )
        visible = " ".join(
            [item.value for item in app.markdown]
            + [item.value for item in app.caption]
            + [item.value for item in app.warning]
            + [item.value for item in app.success]
        )
        self.assertIn("분석 환경 및 고급 설정", [
            item.label for item in app.expander
        ])
        self.assertIn("환율 전망 최신성", visible)
        self.assertIn("API key 값은 표시하지 않습니다", visible)
        self.assertIn("기존 환헤지 결과", visible)


if __name__ == "__main__":
    unittest.main()
