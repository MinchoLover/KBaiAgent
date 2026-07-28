import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from pydantic import ValidationError

from src.country_environment.assessment import (
    assess_country_trade_environment,
    country_environment_trace,
)
from src.country_environment.snapshot import (
    DEFAULT_SNAPSHOT_PATH,
    CountrySnapshotError,
    canonical_snapshot_hash,
    load_country_environment_snapshot,
)
from src.domain.country_environment_models import (
    CountryEnvironmentSnapshot,
    CountrySnapshotSourceRecord,
    CountryTradeEnvironmentInput,
    is_official_https_url,
)


def representative_input(country: str) -> CountryTradeEnvironmentInput:
    return CountryTradeEnvironmentInput(
        confirmed_trade_sha256="a" * 64,
        country_confirmation_status="USER_CONFIRMED",
        trade_type="EXPORT",
        counterparty_country=country,
        currency="USD",
        counterparty_relationship="EXISTING",
        balance_payment_method="OPEN_ACCOUNT",
        payment_term_days=90,
        protection_information_status="NONE_CONFIRMED",
        protection_mechanisms=[],
    )


def snapshot_payload() -> dict:
    return json.loads(DEFAULT_SNAPSHOT_PATH.read_text(encoding="utf-8"))


def write_snapshot(payload: dict, directory: str) -> Path:
    path = Path(directory) / "snapshot.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


class CountryEnvironmentSnapshotTests(unittest.TestCase):
    def test_snapshot_deserializes_with_exact_version_and_hash(self):
        snapshot = load_country_environment_snapshot()
        self.assertEqual(snapshot.schema_version, "1.0")
        self.assertEqual(snapshot.snapshot_version, "2026.07.29-v1")
        self.assertEqual(
            canonical_snapshot_hash(snapshot),
            snapshot.snapshot_hash,
        )
        self.assertEqual(snapshot.supported_countries, ["BR", "US"])

    def test_snapshot_hash_is_independent_of_source_record_order(self):
        snapshot = load_country_environment_snapshot()
        reordered = snapshot.model_copy(
            update={"source_records": list(reversed(snapshot.source_records))}
        )
        self.assertEqual(
            canonical_snapshot_hash(reordered),
            snapshot.snapshot_hash,
        )

    def test_tampered_snapshot_fails_closed(self):
        payload = snapshot_payload()
        payload["source_records"][0]["interpretation"] = "tampered"
        with tempfile.TemporaryDirectory() as directory:
            path = write_snapshot(payload, directory)
            with self.assertRaises(CountrySnapshotError):
                load_country_environment_snapshot(path)

    def test_unsupported_snapshot_version_fails_closed(self):
        payload = snapshot_payload()
        payload["snapshot_version"] = "2099.01.01-v9"
        snapshot = CountryEnvironmentSnapshot.model_validate(payload)
        payload["snapshot_hash"] = canonical_snapshot_hash(snapshot)
        with tempfile.TemporaryDirectory() as directory:
            path = write_snapshot(payload, directory)
            with self.assertRaises(CountrySnapshotError):
                load_country_environment_snapshot(path)

    def test_official_https_allowlist_rejects_lookalikes(self):
        self.assertTrue(
            is_official_https_url(
                "https://api.worldbank.org/v2/country/US"
            )
        )
        self.assertTrue(
            is_official_https_url("https://ttd.wto.org/en/profiles/brazil")
        )
        self.assertFalse(
            is_official_https_url("http://www.oecd.org/example")
        )
        self.assertFalse(
            is_official_https_url("https://wto.org.example.com/profile")
        )
        self.assertFalse(
            is_official_https_url("https://example.com/wto.org")
        )

    def test_every_source_has_provenance_and_interpretation(self):
        snapshot = load_country_environment_snapshot()
        for record in snapshot.source_records:
            self.assertTrue(record.official_url)
            self.assertTrue(record.source_title)
            self.assertTrue(record.as_of_date)
            self.assertTrue(record.observation_period)
            self.assertTrue(record.interpretation)
            self.assertTrue(record.limitations)
            self.assertTrue(
                record.raw_value is not None or record.raw_status
            )

    def test_duplicate_source_record_id_is_rejected(self):
        payload = snapshot_payload()
        duplicate = deepcopy(payload["source_records"][0])
        payload["source_records"].append(duplicate)
        with self.assertRaises(ValidationError):
            CountryEnvironmentSnapshot.model_validate(payload)

    def test_source_country_mismatch_is_rejected(self):
        payload = snapshot_payload()
        payload["source_records"][0]["country"] = "CA"
        with self.assertRaises(ValidationError):
            CountryEnvironmentSnapshot.model_validate(payload)

    def test_float_and_scientific_decimal_are_rejected(self):
        record = snapshot_payload()["source_records"][2]
        record["raw_value"] = 2.5
        with self.assertRaises(ValidationError):
            CountrySnapshotSourceRecord.model_validate(record)
        record["raw_value"] = "2.5e0"
        with self.assertRaises(ValidationError):
            CountrySnapshotSourceRecord.model_validate(record)

    def test_oecd_contract_preserves_brazil_4_and_us_unclassified(self):
        snapshot = load_country_environment_snapshot()
        records = {
            item.country: item
            for item in snapshot.source_records
            if item.source_axis == "OECD_PAYMENT_TRANSFER"
        }
        self.assertEqual(records["BR"].as_of_date, "2026-06-26")
        self.assertEqual(records["BR"].raw_value, 4)
        self.assertEqual(records["BR"].raw_status, "CLASSIFIED")
        self.assertIsNone(records["US"].raw_value)
        self.assertEqual(
            records["US"].raw_status,
            "HIGH_INCOME_OECD_UNCLASSIFIED",
        )


class CountryEnvironmentAssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = load_country_environment_snapshot()
        cls.us_input = representative_input("US")
        cls.br_input = representative_input("BR")
        cls.us = assess_country_trade_environment(
            cls.us_input,
            snapshot=cls.snapshot,
        )
        cls.br = assess_country_trade_environment(
            cls.br_input,
            snapshot=cls.snapshot,
        )

    def test_representative_inputs_differ_only_by_country(self):
        us_payload = self.us_input.model_dump()
        br_payload = self.br_input.model_dump()
        self.assertEqual(us_payload.pop("counterparty_country"), "US")
        self.assertEqual(br_payload.pop("counterparty_country"), "BR")
        self.assertEqual(us_payload, br_payload)
        self.assertEqual(self.us_input.currency, "USD")
        self.assertEqual(self.us_input.trade_type, "EXPORT")
        self.assertEqual(
            self.us_input.balance_payment_method,
            "OPEN_ACCOUNT",
        )
        self.assertEqual(self.us_input.payment_term_days, 90)
        self.assertEqual(
            self.us_input.counterparty_relationship,
            "EXISTING",
        )
        self.assertEqual(
            self.us_input.protection_information_status,
            "NONE_CONFIRMED",
        )

    def test_us_is_elevated_without_unclassified_mitigation(self):
        self.assertEqual(self.us.review_priority, "ELEVATED_REVIEW")
        self.assertEqual(
            self.us.oecd_payment_transfer.status,
            "HIGH_INCOME_OECD_UNCLASSIFIED",
        )
        self.assertIsNone(
            self.us.oecd_payment_transfer.raw_classification
        )
        self.assertNotEqual(self.us.review_priority, "LOW")
        self.assertFalse(
            any(
                item.observed_value_or_status == "LOW"
                for item in self.us.rule_contributions
            )
        )
        contribution = next(
            item for item in self.us.rule_contributions
            if item.rule_code
            == "OECD_HIGH_INCOME_UNCLASSIFIED_NOT_MITIGANT"
        )
        self.assertEqual(contribution.priority_direction, "NO_CHANGE")

    def test_brazil_is_high_with_payment_transfer_action(self):
        self.assertEqual(self.br.review_priority, "HIGH_REVIEW")
        self.assertEqual(
            self.br.oecd_payment_transfer.raw_classification,
            4,
        )
        self.assertIn(
            "PAYMENT_TRANSFER_PROTECTION_REVIEW_REQUIRED",
            self.br.oecd_payment_transfer.action_signals,
        )
        self.assertIn(
            "PAYMENT_TRANSFER_PROTECTION_REVIEW",
            self.br.review_needs,
        )

    def test_three_axes_are_separate_and_not_scored(self):
        payload = self.br.model_dump()
        self.assertIn("oecd_payment_transfer", payload)
        self.assertIn("world_bank_macro_environment", payload)
        self.assertIn("wto_trade_market_access", payload)

        def all_keys(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield key
                    yield from all_keys(item)
            elif isinstance(value, list):
                for item in value:
                    yield from all_keys(item)

        prohibited = {
            "score",
            "composite_score",
            "credit_score",
            "default_probability",
            "country_rating",
            "internal_country_grade",
        }
        self.assertTrue(prohibited.isdisjoint(set(all_keys(payload))))

    def test_same_input_is_deterministic(self):
        repeated = assess_country_trade_environment(
            self.br_input,
            snapshot=self.snapshot,
        )
        self.assertEqual(repeated.review_priority, self.br.review_priority)
        self.assertEqual(repeated.reasons, self.br.reasons)
        self.assertEqual(
            repeated.input_fingerprint,
            self.br.input_fingerprint,
        )

    def test_fingerprint_binds_snapshot_and_source_records(self):
        self.assertEqual(
            self.br.snapshot_hash,
            self.snapshot.snapshot_hash,
        )
        self.assertTrue(self.br.source_record_ids)
        changed = self.br_input.model_copy(
            update={"payment_term_days": 91}
        )
        changed_result = assess_country_trade_environment(
            changed,
            snapshot=self.snapshot,
        )
        self.assertNotEqual(
            changed_result.input_fingerprint,
            self.br.input_fingerprint,
        )

    def test_unsupported_country_is_insufficient_information(self):
        result = assess_country_trade_environment(
            representative_input("CA"),
            snapshot=self.snapshot,
        )
        self.assertEqual(
            result.review_priority,
            "INSUFFICIENT_INFORMATION",
        )
        self.assertIn(
            "INFORMATION_COMPLETENESS_REVIEW",
            result.review_needs,
        )
        self.assertEqual(result.warning_codes, ["UNSUPPORTED_COUNTRY"])

    def test_missing_snapshot_is_insufficient_information(self):
        result = assess_country_trade_environment(
            self.us_input,
            snapshot_path=Path("/tmp/nonexistent-country-snapshot.json"),
        )
        self.assertEqual(
            result.review_priority,
            "INSUFFICIENT_INFORMATION",
        )
        self.assertEqual(
            result.warning_codes,
            ["SNAPSHOT_VALIDATION_FAILED"],
        )

    def test_missing_source_provenance_fails_closed(self):
        incomplete = self.snapshot.model_copy(
            update={
                "source_records": [
                    item
                    for item in self.snapshot.source_records
                    if not (
                        item.country == "US"
                        and item.source_axis
                        == "WTO_TRADE_MARKET_ACCESS"
                    )
                ]
            }
        )
        result = assess_country_trade_environment(
            self.us_input,
            snapshot=incomplete,
        )
        self.assertEqual(
            result.review_priority,
            "INSUFFICIENT_INFORMATION",
        )
        self.assertEqual(
            result.warning_codes,
            ["SOURCE_PROVENANCE_MISSING"],
        )

    def test_unclassified_and_data_unavailable_are_distinct(self):
        unavailable = assess_country_trade_environment(
            representative_input("CA"),
            snapshot=self.snapshot,
        )
        self.assertEqual(
            self.us.oecd_payment_transfer.status,
            "HIGH_INCOME_OECD_UNCLASSIFIED",
        )
        self.assertEqual(
            unavailable.oecd_payment_transfer.status,
            "DATA_UNAVAILABLE",
        )
        self.assertNotEqual(
            self.us.review_priority,
            unavailable.review_priority,
        )

    def test_world_bank_year_mismatch_is_explicit(self):
        self.assertEqual(
            {
                item.observation_period
                for item in self.us.world_bank_macro_environment.observations
            },
            {"2024", "2025"},
        )
        self.assertIn(
            "WORLD_BANK_OBSERVATION_PERIOD_MISMATCH",
            self.us.warning_codes,
        )
        self.assertEqual(
            {
                item.observation_period
                for item in self.br.world_bank_macro_environment.observations
            },
            {"2025"},
        )

    def test_trace_excludes_raw_payload_and_secrets(self):
        trace = country_environment_trace(self.br)
        payload = json.dumps(trace.model_dump(), ensure_ascii=False)
        self.assertEqual(trace.country, "BR")
        self.assertEqual(
            trace.review_priority,
            self.br.review_priority,
        )
        self.assertNotIn("raw_value", payload)
        self.assertNotIn("official_url", payload)
        self.assertNotIn("api_key", payload.lower())
        self.assertNotIn("2.2857464902475", payload)


if __name__ == "__main__":
    unittest.main()
