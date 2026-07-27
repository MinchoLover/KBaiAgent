import json
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from src.application.market_integration_service import (
    integrate_stage1_market,
)
from src.config import Settings
from src.stage1.forecast_provider import (
    FileStage1ForecastProvider,
    HttpStage1ForecastProvider,
    MockStage1ForecastProvider,
    Stage1ForecastService,
    Stage1ProviderError,
)
from src.stage1.scenario_builder import build_fx_scenarios
from src.stage1.spot_rate import (
    FixtureSpotRateProvider,
    KoreaEximSpotRateProvider,
    ManualSpotRateProvider,
    SpotRateError,
)
from src.stage1.web_forecast import normalize_stage1_web_forecast
from src.domain.stage2_models import ExposureInput, Stage2Input
from src.domain.stage3_models import Stage3Assumptions
from src.stage2.engine import run_stage2
from src.stage3.optimizer import generate_strategy_candidates


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT
    / "src"
    / "integration_assets"
    / "stage1"
    / "latest_forecast.json"
)
NOW = datetime(2026, 7, 27, 9, 0, tzinfo=timezone.utc)


def fixture_payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def normalized_forecast(payload=None, now=NOW):
    return normalize_stage1_web_forecast(
        payload or fixture_payload(),
        provider="test",
        now=now,
    )


class Stage1WebNormalizationTests(unittest.TestCase):
    def test_provided_fixture_is_normalized_without_probability_claim(self):
        result = normalized_forecast()

        self.assertEqual(result.source.raw_schema_version, "krw_forecast_web_v1")
        self.assertEqual(result.horizon.trading_days, 21)
        self.assertEqual(result.direction.label, "USD_KRW_DOWN")
        self.assertEqual(result.direction.up_score, "0.288")
        self.assertEqual(result.direction.down_score, "0.712")
        self.assertFalse(result.direction.calibrated_probability)
        self.assertEqual(result.direction.usage, "MARKET_CONTEXT_ONLY")
        self.assertEqual(result.path_risk.up.q90, "0.035")
        self.assertEqual(result.path_risk.down.q90, "0.036")
        self.assertEqual(result.market_context.duplicate_news_removed, 2)
        self.assertEqual(len(result.market_context.news), 2)
        self.assertTrue(result.quality.news_degraded)
        self.assertTrue(result.quality.research_only)

    def test_schema_mismatch_is_rejected(self):
        payload = fixture_payload()
        payload["schema_version"] = "unknown"
        with self.assertRaises(ValueError):
            normalized_forecast(payload)

    def test_invalid_quantile_order_is_rejected(self):
        payload = fixture_payload()
        values = payload["forecast"]["maximum_rise_21d"][
            "quantiles_simple_return"
        ]
        values["q50"] = 0.2
        values["q75"] = 0.1
        with self.assertRaises(ValueError):
            normalized_forecast(payload)

    def test_score_sum_is_rejected(self):
        payload = fixture_payload()
        payload["forecast"]["terminal_direction_21d"][
            "p_usdkrw_down"
        ] = 0.5
        with self.assertRaises(ValueError):
            normalized_forecast(payload)

    def test_news_cannot_change_numeric_forecast(self):
        payload = fixture_payload()
        payload["news_market_context"]["changed_model_forecast"] = True
        with self.assertRaises(ValueError):
            normalized_forecast(payload)

    def test_stale_and_partial_fallback_are_explicit(self):
        payload = fixture_payload()
        payload["data_quality"]["market_refresh"][
            "partial_fallback_used"
        ] = True
        payload["data_quality"]["market_refresh"]["failed_series"] = {
            "fred:vix": "timeout"
        }
        result = normalized_forecast(
            payload,
            now=datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc),
        )
        warning_text = " ".join(result.quality.warnings)
        self.assertTrue(result.quality.stale_market_data)
        self.assertIn("STALE_MARKET_DATA", warning_text)
        self.assertIn("PARTIAL_FALLBACK_USED", warning_text)
        self.assertIn("FAILED_MARKET_SERIES", warning_text)


class Stage1ProviderTests(unittest.TestCase):
    def _service(self, http_fetcher):
        return Stage1ForecastService(
            http_provider=HttpStage1ForecastProvider(
                fetcher=http_fetcher,
                retries=0,
            ),
            file_provider=FileStage1ForecastProvider(FIXTURE),
            mock_provider=MockStage1ForecastProvider(FIXTURE),
            maximum_path_return=Decimal("0.50"),
            max_staleness_market_days=3,
        )

    def test_file_and_mock_modes_work_without_api(self):
        service = self._service(
            lambda unused_url, unused_timeout, unused_maximum: b"{}"
        )
        file_result = service.load("file", now=NOW)
        mock_result = service.load("mock", now=NOW)
        self.assertEqual(file_result.source, "FILE")
        self.assertEqual(mock_result.source, "MOCK")
        self.assertFalse(file_result.fallback_used)

    def test_http_success_uses_forecast_and_health(self):
        forecast_body = FIXTURE.read_bytes()

        def fetcher(url, unused_timeout, unused_maximum):
            if url.endswith("/health"):
                return b'{"status":"ok","forecast_available":true}'
            return forecast_body

        service = self._service(fetcher)
        result = service.load("http", now=NOW)
        self.assertEqual(result.source, "HTTP")
        self.assertEqual(result.provider_health.status, "OK")
        self.assertFalse(result.fallback_used)

    def test_http_timeout_uses_disclosed_file_fallback(self):
        def timeout(
            unused_url,
            unused_timeout,
            unused_maximum,
        ):
            raise TimeoutError("test timeout")

        result = self._service(timeout).load("http", now=NOW)
        self.assertEqual(result.source, "FILE_FALLBACK")
        self.assertTrue(result.fallback_used)
        self.assertIn("FALLBACK_USED", " ".join(result.warnings))

    def test_http_invalid_json_uses_disclosed_file_fallback(self):
        service = self._service(
            lambda unused_url, unused_timeout, unused_maximum: b"not-json"
        )
        result = service.load("http", now=NOW)
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.source, "FILE_FALLBACK")

    def test_remote_http_and_unlisted_https_hosts_are_blocked(self):
        with self.assertRaises(Stage1ProviderError):
            HttpStage1ForecastProvider(
                base_url="http://stage1.example.com",
            )
        with self.assertRaises(Stage1ProviderError):
            HttpStage1ForecastProvider(
                base_url="https://stage1.example.com",
            )
        provider = HttpStage1ForecastProvider(
            base_url="https://stage1.example.com",
            allowed_hosts=("stage1.example.com",),
            fetcher=lambda unused_url, unused_timeout, unused_maximum: (
                FIXTURE.read_bytes()
            ),
        )
        self.assertEqual(
            provider.fetch_latest()["schema_version"],
            "krw_forecast_web_v1",
        )


class SpotRateProviderTests(unittest.TestCase):
    def test_manual_rate_requires_user_confirmation(self):
        provider = ManualSpotRateProvider(
            rate="1400",
            user_confirmed=False,
        )
        with self.assertRaises(SpotRateError):
            provider.get_quote("USD/KRW")

    def test_fixture_rate_is_clearly_labeled(self):
        quote = FixtureSpotRateProvider().get_quote("USD/KRW")
        self.assertEqual(quote.rate, "1400.00")
        self.assertEqual(quote.rate_type, "TEST_FIXTURE")
        self.assertFalse(quote.user_confirmed)

    def test_koreaexim_reference_rate_is_parsed_and_normalized(self):
        body = json.dumps(
            [
                {
                    "cur_unit": "USD",
                    "deal_bas_r": "1,400.50",
                }
            ]
        ).encode("utf-8")
        quote = KoreaEximSpotRateProvider(
            api_key="test-key",
            fetcher=lambda unused_url, unused_timeout: body,
        ).get_quote("USD/KRW", as_of=date(2026, 7, 27))
        self.assertEqual(quote.rate, "1400.50")
        self.assertEqual(quote.source, "KOREAEXIM_DEAL_BASE_RATE")

    def test_koreaexim_hundred_yen_is_per_one_normalized(self):
        body = json.dumps(
            [
                {
                    "cur_unit": "JPY(100)",
                    "deal_bas_r": "950.00",
                }
            ]
        ).encode("utf-8")
        quote = KoreaEximSpotRateProvider(
            api_key="test-key",
            fetcher=lambda unused_url, unused_timeout: body,
        ).get_quote("JPY/KRW", as_of=date(2026, 7, 27))
        self.assertEqual(quote.rate, "9.50")
        self.assertEqual(quote.quote_convention, "KRW_PER_1_JPY")


class ScenarioBuilderTests(unittest.TestCase):
    def test_model_quantiles_and_fixed_stress_use_decimal_spot(self):
        result = build_fx_scenarios(
            spot_quote=FixtureSpotRateProvider().get_quote("USD/KRW"),
            settlement_date="2026-08-10",
            currency="USD",
            forecast=normalized_forecast(),
        )
        rates = {
            item.id: Decimal(item.rate)
            for item in result.model_path_scenarios
        }
        self.assertEqual(rates["MODEL_UP_Q50"], Decimal("1421.0000"))
        self.assertEqual(rates["MODEL_UP_Q75"], Decimal("1436.4000"))
        self.assertEqual(rates["MODEL_UP_Q90"], Decimal("1449.0000"))
        self.assertEqual(rates["MODEL_DOWN_Q50"], Decimal("1386.0000"))
        self.assertEqual(rates["MODEL_DOWN_Q75"], Decimal("1370.6000"))
        self.assertEqual(rates["MODEL_DOWN_Q90"], Decimal("1349.6000"))
        fixed = {
            item.id: Decimal(item.rate)
            for item in result.fixed_stress_scenarios
        }
        self.assertEqual(fixed["DOWN_10"], Decimal("1260.0000"))
        self.assertEqual(fixed["UP_10"], Decimal("1540.0000"))
        self.assertFalse(result.calculation_set.probability_valid)
        self.assertTrue(
            all(
                item.probability is None
                for item in result.calculation_set.scenarios
            )
        )

    def test_horizon_mismatch_keeps_model_context_out_of_calculation(self):
        result = build_fx_scenarios(
            spot_quote=FixtureSpotRateProvider().get_quote("USD/KRW"),
            settlement_date="2026-10-27",
            currency="USD",
            forecast=normalized_forecast(),
        )
        calculation_names = {
            item.name for item in result.calculation_set.scenarios
        }
        self.assertTrue(result.horizon_mismatch)
        self.assertFalse(
            any(name.startswith("MODEL_") for name in calculation_names)
        )
        self.assertTrue(
            all(
                not item.included_in_calculation
                for item in result.model_path_scenarios
            )
        )
        self.assertIn("HORIZON_MISMATCH", " ".join(result.warnings))

    def test_market_integration_uses_real_fixture_contract(self):
        settings = Settings(
            demo_mode=False,
            stage1_provider="file",
            stage1_forecast_file=str(FIXTURE),
            spot_rate_provider="manual",
        )
        result = integrate_stage1_market(
            settings=settings,
            currency="USD",
            settlement_date="2026-08-10",
            manual_spot_rate="1400",
            manual_spot_confirmed=True,
            now=NOW,
        )
        self.assertIsNotNone(result.forecast_load)
        self.assertEqual(result.spot_quote.rate, "1400")
        self.assertEqual(result.stage1_load.source, "STAGE1_MODEL")
        self.assertTrue(
            any(
                item.name == "MODEL_UP_Q90"
                for item in result.stage1_load.scenario_set.scenarios
            )
        )


class Stage2ModelScenarioTests(unittest.TestCase):
    def _scenario_set(self):
        return build_fx_scenarios(
            spot_quote=FixtureSpotRateProvider().get_quote("USD/KRW"),
            settlement_date="2026-08-10",
            currency="USD",
            forecast=normalized_forecast(),
        ).calculation_set

    def _input(self, trade_type, usable_fx="0"):
        return Stage2Input(
            as_of_date="2026-07-27",
            exposures=[
                ExposureInput(
                    sequence=1,
                    trade_type=trade_type,
                    currency="USD",
                    foreign_amount="100000",
                    settlement_date="2026-08-10",
                    usable_fx_balance=usable_fx,
                )
            ],
            current_krw_cash="200000000",
            minimum_cash_buffer="10000000",
            credit_limit="0",
            acceptable_fx_loss="5000000",
        )

    def test_import_uses_v36_up_path_as_adverse(self):
        result = run_stage2(
            self._input("IMPORT", usable_fx="20000"),
            self._scenario_set(),
        )
        by_name = {
            item.scenario_name: item for item in result.scenario_results
        }
        self.assertEqual(
            by_name["MODEL_UP_Q90"].loss_vs_base,
            "3920000.00",
        )
        self.assertEqual(
            by_name["MODEL_DOWN_Q90"].loss_vs_base,
            "0.00",
        )
        self.assertEqual(
            by_name["MODEL_UP_Q90"].scenario_source_kind,
            "STAGE1_MODEL_QUANTILE",
        )
        self.assertIsNone(result.expected_adverse_loss)

    def test_export_uses_v34_down_path_as_adverse(self):
        result = run_stage2(
            self._input("EXPORT"),
            self._scenario_set(),
        )
        by_name = {
            item.scenario_name: item for item in result.scenario_results
        }
        self.assertEqual(
            by_name["MODEL_DOWN_Q90"].loss_vs_base,
            "5040000.00",
        )
        self.assertEqual(
            by_name["MODEL_UP_Q90"].loss_vs_base,
            "0.00",
        )

    def test_horizon_mismatch_never_reaches_stage2_model_results(self):
        scenarios = build_fx_scenarios(
            spot_quote=FixtureSpotRateProvider().get_quote("USD/KRW"),
            settlement_date="2026-10-27",
            currency="USD",
            forecast=normalized_forecast(),
        ).calculation_set
        stage2_input = self._input("IMPORT", usable_fx="20000")
        stage2_input.exposures[0].settlement_date = "2026-10-27"
        result = run_stage2(stage2_input, scenarios)
        self.assertFalse(
            any(
                item.scenario_name.startswith("MODEL_")
                for item in result.scenario_results
            )
        )
        self.assertIn("HORIZON_MISMATCH", " ".join(result.warnings))

    def test_stage3_exposes_q90_fixed_stress_and_cost_assumptions(self):
        stage2 = run_stage2(
            self._input("IMPORT", usable_fx="20000"),
            self._scenario_set(),
        )
        result = generate_strategy_candidates(stage2)

        self.assertEqual(
            [item.profile for item in result.candidates],
            ["STABILITY_FIRST", "BALANCED", "COST_FIRST"],
        )
        self.assertEqual(
            result.assumptions_contract.simulation_status,
            "SIMULATED_CANDIDATE",
        )
        for item in result.candidates:
            self.assertIsNotNone(item.q90_adverse_loss)
            self.assertIsNotNone(item.fixed_10_adverse_loss)
            self.assertEqual(item.post_credit_deficit, "0.00")
            self.assertTrue(item.constraints_satisfied)

    def test_stage3_returns_no_forced_candidate_when_infeasible(self):
        stage2 = run_stage2(
            self._input("IMPORT", usable_fx="20000"),
            self._scenario_set(),
        )
        result = generate_strategy_candidates(
            stage2,
            assumptions=Stage3Assumptions(
                maximum_forward_ratio="0",
                staged_risk_factor="1",
            ),
        )

        self.assertEqual(result.status, "NO_FEASIBLE_CANDIDATE")
        self.assertEqual(result.candidates, [])
        self.assertIn(
            "ACCEPTABLE_LOSS_EXCEEDED",
            result.infeasible_reasons,
        )


if __name__ == "__main__":
    unittest.main()
