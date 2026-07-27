import json
import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from src.config import Settings
from src.domain.stage1_models import ScenarioPoint, Stage1ScenarioSet
from src.stage1.adapter import (
    MAX_STAGE1_RESPONSE_BYTES,
    load_stage1,
    validate_stage1_endpoint,
)
from src.stage1.manual_scenarios import build_manual_stress_scenarios
from src.stage1.normalizer import normalize_stage1_scenarios


def scenario_set(**updates):
    data = {
        "schema_version": "1.0",
        "currency": "USD",
        "quote_convention": "KRW_PER_1_FC",
        "rate_unit_foreign_currency": "1",
        "as_of": "2026-07-23T09:00:00+09:00",
        "target_date": "2026-10-21",
        "kind": "FORECAST",
        "scenarios": [
            {
                "name": "LOW",
                "rate": "1330",
                "is_base": False,
                "probability": "0.20",
            },
            {
                "name": "BASE",
                "rate": "1400",
                "is_base": True,
                "probability": "0.60",
            },
            {
                "name": "HIGH",
                "rate": "1515",
                "is_base": False,
                "probability": "0.20",
            },
        ],
    }
    data.update(updates)
    return Stage1ScenarioSet.model_validate(data)


class Stage1Tests(unittest.TestCase):
    def test_manual_stress_has_seven_points_and_one_base(self):
        result = build_manual_stress_scenarios(
            currency="USD",
            base_rate="1400",
            target_date="2026-10-21",
            as_of="2026-07-23T09:00:00+09:00",
        )
        self.assertEqual(len(result.scenarios), 7)
        self.assertEqual(sum(item.is_base for item in result.scenarios), 1)
        self.assertEqual(result.kind, "STRESS")

    def test_manual_stress_is_not_probability_forecast(self):
        loaded = load_stage1(
            expected_currency="USD",
            expected_target_date="2026-10-21",
            manual_base_rate="1400",
        )
        self.assertFalse(loaded.scenario_set.probability_valid)
        self.assertEqual(loaded.scenario_set.kind, "STRESS")

    def test_probability_complete_and_sum_one(self):
        normalized = normalize_stage1_scenarios(scenario_set())
        self.assertTrue(normalized.probability_valid)

    def test_partial_probability_disables_probability_metrics(self):
        raw = scenario_set(
            scenarios=[
                ScenarioPoint(
                    name="LOW",
                    rate="1330",
                    is_base=False,
                    probability="0.4",
                ),
                ScenarioPoint(
                    name="BASE",
                    rate="1400",
                    is_base=True,
                    probability=None,
                ),
            ]
        )
        normalized = normalize_stage1_scenarios(raw)
        self.assertFalse(normalized.probability_valid)
        self.assertTrue(normalized.warnings)

    def test_bad_probability_sum_rejected(self):
        raw = scenario_set(
            scenarios=[
                ScenarioPoint(
                    name="LOW",
                    rate="1330",
                    is_base=False,
                    probability="0.4",
                ),
                ScenarioPoint(
                    name="BASE",
                    rate="1400",
                    is_base=True,
                    probability="0.4",
                ),
            ]
        )
        with self.assertRaises(ValueError):
            normalize_stage1_scenarios(raw)

    def test_non_finite_rate_and_probability_rejected(self):
        with self.assertRaises(ValueError):
            normalize_stage1_scenarios(
                scenario_set(
                    scenarios=[
                        ScenarioPoint(
                            name="BASE",
                            rate="NaN",
                            is_base=True,
                        )
                    ]
                )
            )
        with self.assertRaises(ValueError):
            normalize_stage1_scenarios(
                scenario_set(
                    scenarios=[
                        ScenarioPoint(
                            name="BASE",
                            rate="1400",
                            is_base=True,
                            probability="NaN",
                        )
                    ]
                )
            )

    def test_exactly_one_base_required(self):
        raw = scenario_set(
            scenarios=[
                ScenarioPoint(
                    name="LOW",
                    rate="1330",
                    is_base=False,
                )
            ]
        )
        with self.assertRaises(ValueError):
            normalize_stage1_scenarios(raw)

    def test_currency_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            normalize_stage1_scenarios(
                scenario_set(),
                expected_currency="EUR",
            )

    def test_target_date_mismatch_is_disclosed(self):
        normalized = normalize_stage1_scenarios(
            scenario_set(),
            expected_target_date="2026-10-22",
        )
        self.assertIn("대체 적용", normalized.application_rule)
        self.assertTrue(normalized.warnings)

    def test_jpy_100_unit_normalized_to_one(self):
        raw = scenario_set(
            currency="JPY",
            rate_unit_foreign_currency="100",
            scenarios=[
                ScenarioPoint(
                    name="BASE",
                    rate="950",
                    is_base=True,
                )
            ],
        )
        normalized = normalize_stage1_scenarios(raw)
        self.assertEqual(normalized.scenarios[0].rate, "9.5")
        self.assertEqual(normalized.rate_unit_foreign_currency, "1")

    def test_external_json_payload(self):
        loaded = load_stage1(
            expected_currency="USD",
            expected_target_date="2026-10-21",
            manual_base_rate="1400",
            mode="EXTERNAL_STAGE1",
            payload=json.dumps(scenario_set().model_dump()),
        )
        self.assertEqual(loaded.source, "EXTERNAL")
        self.assertEqual(loaded.scenario_set.kind, "FORECAST")

    def test_external_failure_falls_back_to_manual_stress(self):
        def failing_fetch(url: str, timeout: float) -> bytes:
            del url, timeout
            raise RuntimeError("offline")

        loaded = load_stage1(
            expected_currency="USD",
            expected_target_date="2026-10-21",
            manual_base_rate="1400",
            mode="EXTERNAL_STAGE1",
            endpoint="https://stage1.invalid/scenarios",
            settings=Settings(stage1_timeout_seconds=0.1),
            fetcher=failing_fetch,
        )
        self.assertEqual(loaded.source, "MANUAL_FALLBACK")
        self.assertEqual(loaded.scenario_set.kind, "STRESS")

    def test_unsupported_schema_version_is_rejected(self):
        payload = scenario_set().model_dump()
        payload["schema_version"] = "2.0"
        with self.assertRaises(ValidationError):
            Stage1ScenarioSet.model_validate(payload)

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            load_stage1(
                expected_currency="USD",
                expected_target_date="2026-10-21",
                manual_base_rate="1400",
                mode="UNKNOWN_MODE",
            )

    def test_oversized_external_payload_uses_safe_fallback(self):
        loaded = load_stage1(
            expected_currency="USD",
            expected_target_date="2026-10-21",
            manual_base_rate="1400",
            mode="EXTERNAL_STAGE1",
            payload=b"x" * (MAX_STAGE1_RESPONSE_BYTES + 1),
        )
        self.assertEqual(loaded.source, "MANUAL_FALLBACK")

    def test_stage1_endpoint_blocks_private_and_metadata_addresses(self):
        for endpoint in (
            "https://127.0.0.1/scenarios",
            "https://10.0.0.10/scenarios",
            "https://169.254.169.254/latest/meta-data",
            "https://[::1]/scenarios",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    validate_stage1_endpoint(endpoint)

    def test_stage1_endpoint_requires_https_and_rejects_userinfo(self):
        public_resolver = lambda unused_host, unused_port: [
            "93.184.216.34"
        ]
        with self.assertRaises(ValueError):
            validate_stage1_endpoint(
                "http://stage1.example.com/scenarios",
                resolver=public_resolver,
            )
        with self.assertRaises(ValueError):
            validate_stage1_endpoint(
                "https://user:password@stage1.example.com/scenarios",
                resolver=public_resolver,
            )

    def test_stage1_endpoint_enforces_exact_host_allowlist(self):
        public_resolver = lambda unused_host, unused_port: [
            "93.184.216.34"
        ]
        validated = validate_stage1_endpoint(
            "https://stage1.example.com/scenarios",
            allowed_hosts=("stage1.example.com",),
            resolver=public_resolver,
        )
        self.assertEqual(
            validated,
            "https://stage1.example.com/scenarios",
        )
        with self.assertRaises(ValueError):
            validate_stage1_endpoint(
                "https://stage1.example.com.evil.test/scenarios",
                allowed_hosts=("stage1.example.com",),
                resolver=public_resolver,
            )

    def test_blocked_stage1_endpoint_never_calls_fetcher(self):
        calls = []

        def fetcher(url: str, timeout: float) -> bytes:
            calls.append((url, timeout))
            return scenario_set().model_dump_json().encode("utf-8")

        loaded = load_stage1(
            expected_currency="USD",
            expected_target_date="2026-10-21",
            manual_base_rate="1400",
            mode="EXTERNAL_STAGE1",
            endpoint="https://127.0.0.1/scenarios",
            fetcher=fetcher,
        )
        self.assertEqual(loaded.source, "MANUAL_FALLBACK")
        self.assertEqual(calls, [])
        self.assertTrue(
            any("outbound 보안 정책" in item for item in loaded.warnings)
        )

    def test_explicit_private_endpoint_setting_preserves_local_development(self):
        calls = []

        def fetcher(url: str, timeout: float) -> bytes:
            calls.append((url, timeout))
            return scenario_set().model_dump_json().encode("utf-8")

        loaded = load_stage1(
            expected_currency="USD",
            expected_target_date="2026-10-21",
            manual_base_rate="1400",
            mode="EXTERNAL_STAGE1",
            endpoint="http://localhost:8080/scenarios",
            settings=Settings(
                stage1_allow_private_endpoints=True,
                stage1_allowed_hosts=("localhost",),
            ),
            fetcher=fetcher,
            resolver=lambda unused_host, unused_port: ["127.0.0.1"],
        )
        self.assertEqual(loaded.source, "EXTERNAL")
        self.assertEqual(len(calls), 1)

    def test_security_and_cache_settings_are_loaded_from_environment(self):
        with patch.dict(
            os.environ,
            {
                "STAGE1_ALLOW_PRIVATE_ENDPOINTS": "true",
                "STAGE1_ALLOWED_HOSTS": (
                    "stage1.example.com, stage1-backup.example.com"
                ),
                "OFFICIAL_SEARCH_CACHE_TTL_HOURS": "12",
                "OFFICIAL_DOMAINS": "ksure.or.kr, kibo.or.kr",
            },
            clear=True,
        ):
            settings = Settings.from_env()
        self.assertTrue(settings.stage1_allow_private_endpoints)
        self.assertEqual(
            settings.stage1_allowed_hosts,
            (
                "stage1.example.com",
                "stage1-backup.example.com",
            ),
        )
        self.assertEqual(settings.official_search_cache_ttl_hours, 12)
        self.assertEqual(
            settings.official_domains,
            ("ksure.or.kr", "kibo.or.kr"),
        )

    def test_legacy_openai_key_and_document_switch_are_normalized(self):
        with patch.dict(
            os.environ,
            {
                "OPEN_AI_API_KEY": "test-only-key",
                "ENABLE_DOCUMENT_AI": "false",
            },
            clear=True,
        ):
            settings = Settings.from_env()
        self.assertEqual(settings.openai_api_key, "test-only-key")
        self.assertFalse(settings.enable_live_document_extraction)


if __name__ == "__main__":
    unittest.main()
