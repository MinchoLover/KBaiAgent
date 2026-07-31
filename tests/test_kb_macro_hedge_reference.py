import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import patch

from pydantic import ValidationError

from src.application.kb_macro_hedge_service import (
    SUPPORTED_PROVIDER_COMMIT_SHA,
    evaluate_kb_macro_hedge_reference,
    run_kb_macro_hedge_for_confirmed_trade,
)
from src.config import Settings
from src.domain.kb_macro_hedge_models import (
    KbMacroHedgeExecutionConstraints,
    KbMacroHedgeRequest,
)
from src.domain.stage1_models import ScenarioPoint, Stage1ScenarioSet
from src.domain.stage2_models import (
    ExistingHedge,
    ExposureInput,
    SameCurrencyFlow,
    Stage2Input,
)
from src.ui.state import clear_downstream
from src.stage2.engine import run_stage2
from src.stage1.normalizer import normalize_stage1_scenarios


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = (
    ROOT / "tests" / "fixtures" / "kb_macro_hedge_reference"
)
FORECAST_NAME = "forecast.json"
HEDGE_NAME = "hedge.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _settings(
    *,
    root: Path = FIXTURE_ROOT,
    forecast_name: str = FORECAST_NAME,
    hedge_name: str = HEDGE_NAME,
    enabled: bool = True,
    mode: str = "fixture",
    forecast_sha: Optional[str] = None,
    hedge_sha: Optional[str] = None,
    commit_sha: str = SUPPORTED_PROVIDER_COMMIT_SHA,
) -> Settings:
    forecast_path = root / forecast_name
    hedge_path = root / hedge_name
    return Settings(
        enable_kb_macro_hedge_reference=enabled,
        kb_macro_hedge_mode=mode,
        kb_macro_hedge_allowed_root=str(root),
        kb_macro_forecast_file=forecast_name,
        kb_macro_hedge_file=hedge_name,
        kb_macro_expected_provider_commit_sha=commit_sha,
        kb_macro_expected_forecast_sha256=(
            forecast_sha
            if forecast_sha is not None
            else _sha256(forecast_path)
        ),
        kb_macro_expected_hedge_sha256=(
            hedge_sha
            if hedge_sha is not None
            else _sha256(hedge_path)
        ),
        kb_macro_max_file_bytes=1024 * 1024,
    )


def _stage2_input(
    *,
    trade_type: str = "IMPORT",
    currency: str = "USD",
    exposures: Optional[List[ExposureInput]] = None,
    same_currency_flows: Optional[List[SameCurrencyFlow]] = None,
    amount: str = "100000",
    cash: str = "10000",
    forward: str = "0",
    payment_date: str = "2026-08-27",
) -> Stage2Input:
    if exposures is None:
        hedge = (
            ExistingHedge(
                amount=forward,
                locked_rate="1450",
                fee="0",
            )
            if forward != "0"
            else None
        )
        exposures = [
            ExposureInput(
                sequence=1,
                trade_type=trade_type,
                currency=currency,
                foreign_amount=amount,
                settlement_date=payment_date,
                usable_fx_balance=cash,
                same_currency_flows=same_currency_flows or [],
                existing_hedge=hedge,
            )
        ]
    return Stage2Input(
        confirmed_trade_sha256="a" * 64,
        as_of_date="2026-07-29",
        exposures=exposures,
        current_krw_cash="200000000",
        minimum_cash_buffer="50000000",
        credit_limit="0",
        acceptable_fx_loss="10000000",
        krw_cashflows=[],
        bank_spread_bps="0",
        bank_fee="0",
    )


def _stage2_result(stage2_input: Stage2Input):
    return run_stage2(
        stage2_input,
        normalize_stage1_scenarios(Stage1ScenarioSet(
            currency="USD",
            rate_unit_foreign_currency="1",
            as_of="2026-07-29T09:00:00+09:00",
            target_date="2026-08-27",
            kind="STRESS",
            scenarios=[
                ScenarioPoint(
                    name="BASE",
                    rate="1400",
                    is_base=True,
                ),
                ScenarioPoint(
                    name="STRESS_+10PCT",
                    rate="1540",
                    is_base=False,
                ),
            ],
        )),
    )


def _cli_constraints() -> KbMacroHedgeExecutionConstraints:
    return KbMacroHedgeExecutionConstraints(
        payment_certainty="1.0",
        maximum_acceptable_cost_krw="135000000",
        maximum_budget_exceedance_probability="0.15",
        risk_tolerance="medium",
        maximum_total_hedge_ratio="1.0",
        option_premium_budget_krw="1500000",
        allowed_instruments=["forward", "vanilla_usd_call"],
    )


class _FakePinnedCli:
    def __init__(self) -> None:
        self.cli_calls = 0
        self.temporary_paths: List[Path] = []
        self.cli_environment: Dict[str, str] = {}

    def __call__(self, command, **kwargs):
        if command[0] == "git":
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
        self.cli_calls += 1
        self.cli_environment = dict(kwargs["env"])
        config_path = Path(command[-1])
        runtime_config = json.loads(
            config_path.read_text(encoding="utf-8")
        )
        output_path = Path(runtime_config["output_path"])
        self.temporary_paths.extend(
            [
                config_path,
                Path(runtime_config["company_input_path"]),
                output_path,
            ]
        )
        shutil.copyfile(
            FIXTURE_ROOT / HEDGE_NAME,
            output_path,
        )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=b"hedge_recommendation=temporary\n",
            stderr=b"",
        )


class _TemporaryCliRepository:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "configs").mkdir(parents=True)
        (self.root / "web_runtime" / "bundle_v1").mkdir(
            parents=True
        )
        (self.root / "web_runtime" / "output").mkdir(parents=True)
        (self.root / "examples").mkdir(parents=True)
        (self.root / ".venv" / "bin").mkdir(parents=True)
        (
            self.root
            / "src"
            / "krw_forecast"
        ).mkdir(parents=True)
        self.forecast = (
            self.root / "web_runtime" / "output" / "forecast.json"
        )
        shutil.copyfile(
            FIXTURE_ROOT / FORECAST_NAME,
            self.forecast,
        )
        self.config = (
            self.root / "configs" / "hedge_recommendation_v1.json"
        )
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": "krw_hedge_recommendation_v1",
                    "horizon_trading_days": 21,
                }
            ),
            encoding="utf-8",
        )
        self.history = (
            self.root
            / "web_runtime"
            / "bundle_v1"
            / "market_history.csv"
        )
        self.history.write_text(
            "date,usdkrw_close\n2026-07-29,1400\n",
            encoding="utf-8",
        )
        self.quote = (
            self.root / "examples" / "mock_company_exposure.json"
        )
        self.quote.write_text(
            json.dumps(
                {
                    "mock_hedge_quotes": {
                        "forward_points_krw_per_usd": "-2.5",
                        "usd_call_options": [],
                    }
                }
            ),
            encoding="utf-8",
        )
        self.python = self.root / ".venv" / "bin" / "python"
        self.python.write_text("#!/bin/sh\n", encoding="utf-8")
        self.python.chmod(0o700)
        self.cli_module = (
            self.root
            / "src"
            / "krw_forecast"
            / "hedge_recommendation_v1_cli.py"
        )
        self.cli_module.write_text("# test fixture\n", encoding="utf-8")

    def settings(self) -> Settings:
        return Settings(
            enable_kb_macro_hedge_reference=True,
            kb_macro_hedge_mode="local_cli",
            kb_macro_hedge_allowed_root=str(self.root),
            kb_macro_forecast_file=str(
                self.forecast.relative_to(self.root)
            ),
            kb_macro_model_config_file=str(
                self.config.relative_to(self.root)
            ),
            kb_macro_market_history_file=str(
                self.history.relative_to(self.root)
            ),
            kb_macro_quote_template_file=str(
                self.quote.relative_to(self.root)
            ),
            kb_macro_expected_provider_commit_sha=(
                SUPPORTED_PROVIDER_COMMIT_SHA
            ),
            kb_macro_expected_forecast_sha256=_sha256(self.forecast),
            kb_macro_expected_model_config_sha256=_sha256(self.config),
            kb_macro_expected_market_history_sha256=_sha256(
                self.history
            ),
            kb_macro_expected_quote_template_sha256=_sha256(
                self.quote
            ),
        )

    def close(self) -> None:
        self.temporary.cleanup()


class _MutatedFixture:
    def __init__(
        self,
        mutate: Callable[[Dict[str, Any], Dict[str, Any]], None],
    ) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        forecast = json.loads(
            (FIXTURE_ROOT / FORECAST_NAME).read_text(
                encoding="utf-8"
            )
        )
        hedge = json.loads(
            (FIXTURE_ROOT / HEDGE_NAME).read_text(
                encoding="utf-8"
            )
        )
        mutate(forecast, hedge)
        (self.root / FORECAST_NAME).write_text(
            json.dumps(
                forecast,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (self.root / HEDGE_NAME).write_text(
            json.dumps(
                hedge,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def close(self) -> None:
        self.temporary.cleanup()


class KbMacroHedgeReferenceTests(unittest.TestCase):
    def test_pinned_local_cli_runs_current_import_and_keeps_reference_only(self):
        repository = _TemporaryCliRepository()
        runner = _FakePinnedCli()
        stage2_input = _stage2_input()
        try:
            result = run_kb_macro_hedge_for_confirmed_trade(
                settings=repository.settings(),
                stage2_input=stage2_input,
                stage2_result=_stage2_result(stage2_input),
                constraints=_cli_constraints(),
                constraints_confirmed=True,
                command_runner=runner,
            )
        finally:
            repository.close()

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, "REFERENCE_ONLY")
        self.assertEqual(result.provider_mode, "local_cli")
        self.assertTrue(result.validation.passed)
        self.assertEqual(len(result.candidates), 3)
        self.assertEqual(runner.cli_calls, 1)
        self.assertTrue(result.fallback_to_internal_stage3)
        self.assertFalse(result.published_to_stage4)
        self.assertEqual(
            result.request.constraints_source
            if result.request
            else None,
            "USER_CONFIRMED_UI",
        )
        self.assertEqual(
            result.request.amount_usd if result.request else None,
            "100000",
        )
        self.assertEqual(
            result.provenance.execution_method
            if result.provenance
            else None,
            "PINNED_LOCAL_CLI",
        )
        self.assertIn(
            "TEMPORARY_RAW_OUTPUT_DELETED",
            result.warnings,
        )
        self.assertNotIn("OPENAI_API_KEY", runner.cli_environment)
        self.assertNotIn("KOREAEXIM_KEY", runner.cli_environment)
        self.assertTrue(
            all(not path.exists() for path in runner.temporary_paths)
        )

    def test_local_cli_requires_explicit_constraints_before_execution(self):
        repository = _TemporaryCliRepository()
        runner = _FakePinnedCli()
        stage2_input = _stage2_input()
        try:
            result = run_kb_macro_hedge_for_confirmed_trade(
                settings=repository.settings(),
                stage2_input=stage2_input,
                stage2_result=_stage2_result(stage2_input),
                constraints=_cli_constraints(),
                constraints_confirmed=False,
                command_runner=runner,
            )
        finally:
            repository.close()

        self.assertEqual(
            result.status if result else None,
            "VALIDATION_FAILED",
        )
        self.assertEqual(runner.cli_calls, 0)

    def test_local_cli_rejects_export_before_external_execution(self):
        repository = _TemporaryCliRepository()
        runner = _FakePinnedCli()
        stage2_input = _stage2_input(trade_type="EXPORT")
        try:
            result = run_kb_macro_hedge_for_confirmed_trade(
                settings=repository.settings(),
                stage2_input=stage2_input,
                stage2_result=_stage2_result(stage2_input),
                constraints=_cli_constraints(),
                constraints_confirmed=True,
                command_runner=runner,
            )
        finally:
            repository.close()

        self.assertEqual(
            result.status if result else None,
            "UNSUPPORTED_EXPOSURE",
        )
        self.assertEqual(runner.cli_calls, 0)

    def test_local_cli_rejects_pinned_input_hash_mismatch(self):
        repository = _TemporaryCliRepository()
        runner = _FakePinnedCli()
        stage2_input = _stage2_input()
        settings = repository.settings()
        settings = Settings(
            **{
                **settings.__dict__,
                "kb_macro_expected_market_history_sha256": "0" * 64,
            }
        )
        try:
            result = run_kb_macro_hedge_for_confirmed_trade(
                settings=settings,
                stage2_input=stage2_input,
                stage2_result=_stage2_result(stage2_input),
                constraints=_cli_constraints(),
                constraints_confirmed=True,
                command_runner=runner,
            )
        finally:
            repository.close()

        self.assertEqual(
            result.status if result else None,
            "VALIDATION_FAILED",
        )
        self.assertEqual(runner.cli_calls, 0)

    def test_fixture_result_is_validated_and_reference_only(self):
        result = evaluate_kb_macro_hedge_reference(
            settings=_settings(),
            fixture_constraints_confirmed=True,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, "REFERENCE_ONLY")
        self.assertTrue(result.validation.passed)
        self.assertEqual(result.pricing_status, "MOCK")
        self.assertEqual(len(result.candidates), 3)
        self.assertEqual(
            result.request.amount_usd if result.request else None,
            "100000",
        )
        self.assertEqual(
            result.request.net_exposure_usd
            if result.request
            else None,
            "90000",
        )
        self.assertIn("MOCK_QUOTES", result.warnings)
        self.assertIn(
            "UPSTREAM_JSON_SCHEMAS_NOT_PROVIDED",
            result.warnings,
        )
        self.assertTrue(result.fallback_to_internal_stage3)
        self.assertFalse(result.published_to_stage4)

    def test_feature_flag_off_returns_no_external_serialized_result(self):
        settings = _settings(enabled=False)

        result = evaluate_kb_macro_hedge_reference(
            settings=settings,
            fixture_constraints_confirmed=True,
        )

        self.assertIsNone(result)
        self.assertFalse(Settings().enable_kb_macro_hedge_reference)
        self.assertEqual(Settings().kb_macro_hedge_mode, "off")

    def test_legacy_settings_without_new_flag_fails_closed(self):
        class LegacySettings:
            pass

        result = evaluate_kb_macro_hedge_reference(
            settings=LegacySettings(),
        )

        self.assertIsNone(result)

    def test_environment_settings_are_loaded_without_secret_values(self):
        values = {
            "ENABLE_KB_MACRO_HEDGE_REFERENCE": "true",
            "KB_MACRO_HEDGE_MODE": "file",
            "KB_MACRO_HEDGE_ALLOWED_ROOT": "/tmp/provider",
            "KB_MACRO_FORECAST_FILE": "forecast.json",
            "KB_MACRO_HEDGE_FILE": "hedge.json",
            "KB_MACRO_EXPECTED_PROVIDER_COMMIT_SHA": (
                SUPPORTED_PROVIDER_COMMIT_SHA
            ),
            "KB_MACRO_EXPECTED_FORECAST_SHA256": "b" * 64,
            "KB_MACRO_EXPECTED_HEDGE_SHA256": "c" * 64,
            "KB_MACRO_EXPECTED_MODEL_CONFIG_SHA256": "d" * 64,
            "KB_MACRO_EXPECTED_MARKET_HISTORY_SHA256": "e" * 64,
            "KB_MACRO_EXPECTED_QUOTE_TEMPLATE_SHA256": "f" * 64,
            "KB_MACRO_MAX_FILE_BYTES": "4096",
            "KB_MACRO_CLI_TIMEOUT_SECONDS": "12.5",
            "KB_MACRO_CLI_MAX_OUTPUT_BYTES": "8192",
        }
        with patch.dict(os.environ, values, clear=False):
            settings = Settings.from_env()

        self.assertTrue(settings.enable_kb_macro_hedge_reference)
        self.assertEqual(settings.kb_macro_hedge_mode, "file")
        self.assertEqual(settings.kb_macro_max_file_bytes, 4096)
        self.assertEqual(settings.kb_macro_cli_timeout_seconds, 12.5)
        self.assertEqual(settings.kb_macro_cli_max_output_bytes, 8192)
        self.assertEqual(
            settings.kb_macro_expected_model_config_sha256,
            "d" * 64,
        )
        self.assertEqual(
            settings.kb_macro_expected_provider_commit_sha,
            SUPPORTED_PROVIDER_COMMIT_SHA,
        )

    def test_current_confirmed_trade_echo_matches(self):
        result = evaluate_kb_macro_hedge_reference(
            settings=_settings(mode="file"),
            stage2_input=_stage2_input(),
            binding_mode="CURRENT_CONFIRMED_TRADE",
            fixture_constraints_confirmed=True,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, "REFERENCE_ONLY")
        self.assertTrue(result.validation.passed)
        self.assertIsNotNone(result.request)
        self.assertEqual(
            result.request.binding_mode if result.request else None,
            "CURRENT_CONFIRMED_TRADE",
        )
        self.assertEqual(
            result.request.source_trade_sha256
            if result.request
            else None,
            "a" * 64,
        )

    def test_unsupported_exposures_do_not_read_provider(self):
        invalid_settings = Settings(
            enable_kb_macro_hedge_reference=True,
            kb_macro_hedge_mode="file",
            kb_macro_hedge_allowed_root="/does/not/exist",
            kb_macro_forecast_file="forecast.json",
            kb_macro_hedge_file="hedge.json",
        )
        cases = {
            "export_receivable": _stage2_input(trade_type="EXPORT"),
            "non_usd": _stage2_input(currency="EUR"),
            "same_currency_flow": _stage2_input(
                same_currency_flows=[
                    SameCurrencyFlow(
                        date="2026-08-20",
                        amount="1000",
                        currency="USD",
                        direction="INFLOW",
                    )
                ]
            ),
            "over_offset": _stage2_input(cash="100001"),
            "multiple": _stage2_input(
                exposures=[
                    ExposureInput(
                        sequence=1,
                        trade_type="IMPORT",
                        currency="USD",
                        foreign_amount="50000",
                        settlement_date="2026-08-27",
                    ),
                    ExposureInput(
                        sequence=2,
                        trade_type="IMPORT",
                        currency="USD",
                        foreign_amount="50000",
                        settlement_date="2026-08-27",
                    ),
                ]
            ),
        }
        for name, stage2_input in cases.items():
            with self.subTest(name=name):
                result = evaluate_kb_macro_hedge_reference(
                    settings=invalid_settings,
                    stage2_input=stage2_input,
                    binding_mode="CURRENT_CONFIRMED_TRADE",
                    fixture_constraints_confirmed=True,
                )
                self.assertIsNotNone(result)
                assert result is not None
                self.assertEqual(
                    result.status,
                    "UNSUPPORTED_EXPOSURE",
                )
                self.assertNotEqual(
                    result.status,
                    "UPSTREAM_UNAVAILABLE",
                )

    def test_fixture_constraints_require_explicit_confirmation(self):
        result = evaluate_kb_macro_hedge_reference(
            settings=_settings(),
            fixture_constraints_confirmed=False,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, "VALIDATION_FAILED")
        self.assertFalse(result.validation.passed)
        self.assertEqual(result.candidates, [])
        self.assertIn(
            "EXPLICIT_FIXTURE_CONSTRAINT_CONFIRMATION",
            result.validation.failed_checks,
        )

    def test_current_trade_echo_mismatch_hides_candidates(self):
        result = evaluate_kb_macro_hedge_reference(
            settings=_settings(),
            stage2_input=_stage2_input(payment_date="2026-08-28"),
            binding_mode="CURRENT_CONFIRMED_TRADE",
            fixture_constraints_confirmed=True,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, "VALIDATION_FAILED")
        self.assertEqual(result.candidates, [])
        self.assertIn(
            "CURRENT_TRADE_ECHO_MATCH",
            result.validation.failed_checks,
        )

    def test_schema_commit_and_sha_mismatches_fail_closed(self):
        cases = {
            "forecast_schema": (
                lambda forecast, hedge: forecast.update(
                    {"schema_version": "unknown"}
                ),
                {},
            ),
            "hedge_schema": (
                lambda forecast, hedge: hedge.update(
                    {"schema_version": "unknown"}
                ),
                {},
            ),
            "forecast_reference": (
                lambda forecast, hedge: hedge[
                    "forecast_json_reference"
                ].update({"prediction_date": "2026-07-28"}),
                {},
            ),
            "producer_commit": (
                lambda forecast, hedge: None,
                {"commit_sha": "f" * 40},
            ),
        }
        for name, (mutate, settings_updates) in cases.items():
            fixture = _MutatedFixture(mutate)
            try:
                result = evaluate_kb_macro_hedge_reference(
                    settings=_settings(
                        root=fixture.root,
                        **settings_updates
                    ),
                    fixture_constraints_confirmed=True,
                )
            finally:
                fixture.close()
            self.assertIsNotNone(result)
            assert result is not None
            with self.subTest(name=name):
                self.assertEqual(
                    result.status,
                    "VALIDATION_FAILED",
                )
                self.assertEqual(result.candidates, [])

        sha_result = evaluate_kb_macro_hedge_reference(
            settings=_settings(forecast_sha="0" * 64),
            fixture_constraints_confirmed=True,
        )
        self.assertIsNotNone(sha_result)
        assert sha_result is not None
        self.assertEqual(sha_result.status, "VALIDATION_FAILED")
        self.assertIn(
            "FORECAST_SHA256",
            sha_result.validation.failed_checks,
        )

    def test_candidate_math_rank_and_certificate_fail_closed(self):
        mutators = {
            "candidate_count": lambda forecast, hedge: hedge[
                "recommended_hedge_combinations"
            ].pop(),
            "duplicate_rank": lambda forecast, hedge: hedge[
                "recommended_hedge_combinations"
            ][1].update({"rank": 1}),
            "negative_ratio": lambda forecast, hedge: hedge[
                "recommended_hedge_combinations"
            ][1].update(
                {
                    "forward_ratio": -0.1,
                    "option_ratio": 1.1,
                }
            ),
            "ratio_sum": lambda forecast, hedge: hedge[
                "recommended_hedge_combinations"
            ][1].update({"option_ratio": 0.2}),
            "negative_notional": lambda forecast, hedge: hedge[
                "recommended_hedge_combinations"
            ][1]["notional_usd"].update({"call_option": -9000}),
            "notional_over_net": lambda forecast, hedge: hedge[
                "recommended_hedge_combinations"
            ][1]["notional_usd"].update({"forward": 99000}),
            "notional_sum": lambda forecast, hedge: hedge[
                "recommended_hedge_combinations"
            ][1]["notional_usd"].update({"forward": 80000}),
            "objective_order": lambda forecast, hedge: hedge[
                "recommended_hedge_combinations"
            ][1]["objective_components_krw"].update(
                {"total_objective_score": 129000000}
            ),
            "certificate": lambda forecast, hedge: hedge[
                "verification"
            ]["constraints"].update({"ratios_sum_to_one": False}),
        }
        for name, mutate in mutators.items():
            fixture = _MutatedFixture(mutate)
            try:
                result = evaluate_kb_macro_hedge_reference(
                    settings=_settings(root=fixture.root),
                    fixture_constraints_confirmed=True,
                )
            finally:
                fixture.close()
            self.assertIsNotNone(result)
            assert result is not None
            with self.subTest(name=name):
                self.assertEqual(
                    result.status,
                    "VALIDATION_FAILED",
                )
                self.assertEqual(result.candidates, [])

    def test_input_echo_net_and_known_instrument_checks_fail_closed(self):
        mutators = {
            "net_exposure": lambda forecast, hedge: hedge[
                "exposure_calculation"
            ].update({"net_exposure_usd": 80000}),
            "unknown_instrument": lambda forecast, hedge: hedge[
                "company_exposure"
            ].update(
                {
                    "allowed_instruments": [
                        "forward",
                        "unknown_swap",
                    ]
                }
            ),
            "unknown_option": lambda forecast, hedge: hedge[
                "recommended_hedge_combinations"
            ][1]["option"].update({"option_id": "not_quoted"}),
            "missing_constraint": lambda forecast, hedge: hedge[
                "company_exposure"
            ].pop("payment_certainty"),
        }
        for name, mutate in mutators.items():
            fixture = _MutatedFixture(mutate)
            try:
                result = evaluate_kb_macro_hedge_reference(
                    settings=_settings(root=fixture.root),
                    fixture_constraints_confirmed=True,
                )
            finally:
                fixture.close()
            self.assertIsNotNone(result)
            assert result is not None
            with self.subTest(name=name):
                self.assertEqual(
                    result.status,
                    "VALIDATION_FAILED",
                )
                self.assertEqual(result.candidates, [])

    def test_missing_invalid_oversized_and_outside_files_are_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = Settings(
                enable_kb_macro_hedge_reference=True,
                kb_macro_hedge_mode="file",
                kb_macro_hedge_allowed_root=str(root),
                kb_macro_forecast_file="missing-forecast.json",
                kb_macro_hedge_file="missing-hedge.json",
                kb_macro_max_file_bytes=1024,
            )
            missing_result = evaluate_kb_macro_hedge_reference(
                settings=missing,
                fixture_constraints_confirmed=True,
            )
            self.assertEqual(
                missing_result.status if missing_result else None,
                "UPSTREAM_UNAVAILABLE",
            )

            (root / "forecast.json").write_text(
                "{invalid",
                encoding="utf-8",
            )
            (root / "hedge.json").write_text(
                "{}",
                encoding="utf-8",
            )
            invalid = missing.__class__(
                **{
                    **missing.__dict__,
                    "kb_macro_forecast_file": "forecast.json",
                    "kb_macro_hedge_file": "hedge.json",
                }
            )
            invalid_result = evaluate_kb_macro_hedge_reference(
                settings=invalid,
                fixture_constraints_confirmed=True,
            )
            self.assertEqual(
                invalid_result.status if invalid_result else None,
                "UPSTREAM_UNAVAILABLE",
            )

            (root / "forecast.json").write_text(
                "{}" * 100,
                encoding="utf-8",
            )
            oversized = invalid.__class__(
                **{
                    **invalid.__dict__,
                    "kb_macro_max_file_bytes": 10,
                }
            )
            oversized_result = evaluate_kb_macro_hedge_reference(
                settings=oversized,
                fixture_constraints_confirmed=True,
            )
            self.assertEqual(
                oversized_result.status
                if oversized_result
                else None,
                "UPSTREAM_UNAVAILABLE",
            )

            outside = invalid.__class__(
                **{
                    **invalid.__dict__,
                    "kb_macro_forecast_file": (
                        str(FIXTURE_ROOT / FORECAST_NAME)
                    ),
                }
            )
            outside_result = evaluate_kb_macro_hedge_reference(
                settings=outside,
                fixture_constraints_confirmed=True,
            )
            self.assertEqual(
                outside_result.status if outside_result else None,
                "UPSTREAM_UNAVAILABLE",
            )

    def test_internal_request_model_forbids_unknown_contract_fields(self):
        valid = {
            "request_id": "request-1",
            "binding_mode": "UPSTREAM_FIXTURE_SELF_TEST",
            "amount_usd": "100000",
            "payment_date": "2026-08-27",
            "existing_usd_cash": "10000",
            "existing_forward_usd": "0",
            "net_exposure_usd": "90000",
            "payment_certainty": "1",
            "maximum_acceptable_cost_krw": "135000000",
            "maximum_budget_exceedance_probability": "0.15",
            "risk_tolerance": "medium",
            "maximum_total_hedge_ratio": "1",
            "option_premium_budget_krw": "1500000",
            "allowed_instruments": [
                "forward",
                "vanilla_usd_call",
            ],
        }
        with self.assertRaises(ValidationError):
            KbMacroHedgeRequest(
                **{
                    **valid,
                    "unexpected_stage3_conversion": "forbidden",
                }
            )

    def test_state_invalidation_clears_external_reference_with_stage2(self):
        state = {
            "stage2_input": {"value": "old"},
            "stage2_result": {"value": "old"},
            "stage3_result": {"value": "kept only until recalculation"},
            "kb_macro_hedge_reference": {"status": "REFERENCE_ONLY"},
        }

        clear_downstream(state, 2)

        self.assertNotIn("kb_macro_hedge_reference", state)
        self.assertNotIn("stage3_result", state)

    def test_golden_export_asset_is_unchanged_and_never_supported(self):
        golden = (
            ROOT
            / "dataset"
            / "golden_demo"
            / "golden_export_contract.pdf"
        )
        self.assertEqual(
            _sha256(golden),
            (
                "5330a1a572488005f7b02cccfc7150fbaa8b38c84"
                "bb9290da1e0c6e1c3a0a91c"
            ),
        )
        result = evaluate_kb_macro_hedge_reference(
            settings=_settings(),
            stage2_input=_stage2_input(trade_type="EXPORT"),
            binding_mode="CURRENT_CONFIRMED_TRADE",
            fixture_constraints_confirmed=True,
        )
        self.assertEqual(
            result.status if result else None,
            "UNSUPPORTED_EXPOSURE",
        )


class KbMacroHedgeStreamlitTests(unittest.TestCase):
    def test_streamlit_local_cli_controls_are_visible_and_fail_closed(self):
        from streamlit.testing.v1 import AppTest

        with patch.dict(
            os.environ,
            {
                "ENABLE_KB_MACRO_HEDGE_REFERENCE": "true",
                "KB_MACRO_HEDGE_MODE": "local_cli",
            },
            clear=False,
        ):
            app = AppTest.from_file(
                str(ROOT / "app.py"),
                default_timeout=25,
            ).run()
            app.session_state["active_page"] = "analysis"
            app.run()

        self.assertEqual(len(app.exception), 0)
        button = next(
            item
            for item in app.button
            if item.key == "run_kb_macro_hedge_model"
        )
        self.assertTrue(button.disabled)
        visible = " ".join(
            [item.value for item in app.markdown]
            + [item.value for item in app.caption]
            + [item.value for item in app.info]
        )
        self.assertIn(
            "현재 수입 거래로 kb_macro_ai 계산하기",
            button.label,
        )
        self.assertIn("고정된 kb_macro_ai 모델", visible)
        self.assertIn("목업 견적", visible)

    def test_streamlit_can_validate_fixture_in_separate_reference_area(self):
        from streamlit.testing.v1 import AppTest

        environment = {
            "ENABLE_KB_MACRO_HEDGE_REFERENCE": "true",
            "KB_MACRO_HEDGE_MODE": "fixture",
            "KB_MACRO_HEDGE_ALLOWED_ROOT": str(FIXTURE_ROOT),
            "KB_MACRO_FORECAST_FILE": FORECAST_NAME,
            "KB_MACRO_HEDGE_FILE": HEDGE_NAME,
            "KB_MACRO_EXPECTED_PROVIDER_COMMIT_SHA": (
                SUPPORTED_PROVIDER_COMMIT_SHA
            ),
            "KB_MACRO_EXPECTED_FORECAST_SHA256": _sha256(
                FIXTURE_ROOT / FORECAST_NAME
            ),
            "KB_MACRO_EXPECTED_HEDGE_SHA256": _sha256(
                FIXTURE_ROOT / HEDGE_NAME
            ),
        }
        with patch.dict(os.environ, environment, clear=False):
            app = AppTest.from_file(
                str(ROOT / "app.py"),
                default_timeout=25,
            ).run()
            app.session_state["active_page"] = "analysis"
            app.run()
            checkbox = next(
                item
                for item in app.checkbox
                if item.key
                == "kb_macro_hedge_constraints_confirmed_widget"
            )
            checkbox.check().run()
            button = next(
                item
                for item in app.button
                if item.key
                == "validate_kb_macro_hedge_reference"
            )
            button.click().run()

        self.assertEqual(len(app.exception), 0)
        stored = app.session_state["kb_macro_hedge_reference"]
        self.assertEqual(stored["status"], "REFERENCE_ONLY")
        self.assertEqual(len(stored["candidates"]), 3)
        visible = " ".join(
            [item.value for item in app.markdown]
            + [item.value for item in app.caption]
            + [item.value for item in app.success]
        )
        self.assertIn("외부 환헤지 조합 참고 결과", visible)
        self.assertIn("단일 USD 수입 지급 전용", visible)
        self.assertNotIn("최적 상품 추천", visible)


if __name__ == "__main__":
    unittest.main()
