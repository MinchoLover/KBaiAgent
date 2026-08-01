import json
import socket
import unittest
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from pydantic import ValidationError

from src.application.consultation_service import build_decision_support
from src.application.trade_statistics_service import (
    TradeStatisticsRequestError,
    build_trade_statistics_request,
    retrieve_trade_statistics,
    trade_statistics_request_fingerprint,
)
from src.config import Settings
from src.domain.trade_statistics_models import (
    TradeStatisticsObservation,
    TradeStatisticsRequest,
    TradeStatisticsSnapshot,
)
from src.stage3.optimizer import generate_strategy_candidates
from src.stage4.local_kb import search_offline_kb
from src.stage5.deterministic_fallback import (
    generate_deterministic_report,
)
from src.stage5.critic import critique_report
from src.trade_statistics.analysis import summarize_trade_statistics
from src.trade_statistics.fixture import (
    DEFAULT_FIXTURE_PATH,
    DEFAULT_RAW_PATH,
    TRADE_STATISTICS_FIXTURE_VERSION,
    canonical_snapshot_hash,
    file_sha256,
    load_trade_statistics_fixture,
)
from src.trade_statistics.periods import (
    month_range,
    split_period_range,
)
from src.trade_statistics.provider import (
    CustomsOpenApiProvider,
    TradeStatisticsProviderError,
    parse_customs_xml,
)
from src.ui.state import clear_confirmation_and_later
from src.workflow.orchestrator import WorkflowOrchestrator
from src.workflow.result import StageStatus
from tests.golden_consultation_fixture import (
    build_golden_consultation_fixture,
)


def _request(**updates):
    values = {
        "reporter_country": "KR",
        "partner_country": "BR",
        "trade_direction": "EXPORT",
        "period_start": "2024-07",
        "period_end": "2026-06",
        "source_preference": "LIVE",
        "confirmed_transaction_fingerprint": "a" * 64,
    }
    values.update(updates)
    return TradeStatisticsRequest(**values)


def _xml_item(
    period,
    *,
    country="BR",
    hs_code=None,
    export="100",
    imported="40",
    balance="60",
    export_weight="10",
    import_weight="5",
):
    hs_element = (
        "<hsCd>{}</hsCd>".format(hs_code)
        if hs_code is not None
        else "<hsCd></hsCd>"
    )
    return (
        "<item><year>{}</year><statCdCntnKor1>브라질</statCdCntnKor1>"
        "<statCd>{}</statCd><statKor>공식 응답 테스트 품목</statKor>{}"
        "<expWgt>{}</expWgt><expDlr>{}</expDlr>"
        "<impWgt>{}</impWgt><impDlr>{}</impDlr>"
        "<balPayments>{}</balPayments></item>"
    ).format(
        period,
        country,
        hs_element,
        export_weight,
        export,
        import_weight,
        imported,
        balance,
    )


def _xml(*items, result_code="00"):
    return (
        "<?xml version='1.0' encoding='UTF-8'?><response><header>"
        "<resultCode>{}</resultCode><resultMsg>OK</resultMsg></header>"
        "<body><items>{}</items></body></response>"
    ).format(result_code, "".join(items)).encode("utf-8")


def _synthetic_snapshot(
    periods,
    *,
    previous_export="100",
    current_export="120",
):
    observations = []
    for index, period in enumerate(periods):
        export = (
            previous_export
            if index < max(0, len(periods) - 12)
            else current_export
        )
        imported = "50"
        observations.append(
            TradeStatisticsObservation(
                period=period,
                reporter_country="KR",
                partner_country="BR",
                export_value_usd=export,
                import_value_usd=imported,
                trade_balance_usd=str(
                    Decimal(export) - Decimal(imported)
                ),
                source_record_id="synthetic-{}".format(period),
            )
        )
    return TradeStatisticsSnapshot(
        snapshot_version="test-v1",
        snapshot_id="test-snapshot",
        source_name="TEST_OFFICIAL_TRANSPORT",
        provider_status="LIVE",
        collected_at="2026-08-01T00:00:00+00:00",
        observation_start=periods[0],
        observation_end=periods[-1],
        source_as_of=periods[-1],
        reporter_country="KR",
        partner_country="BR",
        observations=observations,
        raw_sha256="b" * 64,
        normalized_sha256="c" * 64,
        limitations=[
            "개별 거래의 신용위험이나 금융상품 승인 결과가 아닙니다."
        ],
        metadata={},
    )


class TradeStatisticsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = build_golden_consultation_fixture()

    def test_customs_xml_normal_parsing(self):
        request = _request(
            period_start="2025-01",
            period_end="2025-01",
            hs_code="0202",
            hs_level=4,
            hs_code_confirmed=True,
        )
        observations = parse_customs_xml(
            _xml(_xml_item("2025.01", hs_code="0202")),
            request,
            as_of=date(2026, 8, 1),
        )

        self.assertEqual(len(observations), 1)
        item = observations[0]
        self.assertEqual(item.period, "2025-01")
        self.assertEqual(item.partner_country, "BR")
        self.assertEqual(item.hs_code, "0202")
        self.assertEqual(item.export_value_usd, "100")
        self.assertEqual(item.import_value_usd, "40")
        self.assertEqual(item.trade_balance_usd, "60")
        self.assertEqual(item.export_weight_kg, "10")

    def test_country_total_request_from_confirmed_transaction(self):
        request = build_trade_statistics_request(
            confirmed_transaction=self.golden["confirmed_transaction"],
            source_preference="OFFICIAL_FIXTURE",
        )

        self.assertEqual(request.reporter_country, "KR")
        self.assertEqual(request.partner_country, "BR")
        self.assertEqual(request.trade_direction, "EXPORT")
        self.assertEqual(request.scope, "COUNTRY_TOTAL")
        self.assertIsNone(request.hs_code)

    def test_hs_2_4_6_10_are_supported_only_when_confirmed(self):
        for value in ("02", "0202", "020230", "0202301000"):
            with self.subTest(value=value):
                request = build_trade_statistics_request(
                    confirmed_transaction=(
                        self.golden["confirmed_transaction"]
                    ),
                    source_preference="LIVE",
                    hs_code=value,
                    hs_code_confirmed=True,
                    as_of=date(2026, 8, 1),
                )
                self.assertEqual(request.hs_code, value)
                self.assertEqual(request.hs_level, len(value))
                self.assertEqual(request.scope, "HS_ITEM")

    def test_invalid_hs_length_fails_closed(self):
        with self.assertRaises(TradeStatisticsRequestError) as context:
            build_trade_statistics_request(
                confirmed_transaction=self.golden[
                    "confirmed_transaction"
                ],
                source_preference="LIVE",
                hs_code="020",
                hs_code_confirmed=True,
            )
        self.assertEqual(context.exception.code, "INVALID_HS_CODE")

    def test_non_numeric_hs_fails_closed(self):
        with self.assertRaises(TradeStatisticsRequestError) as context:
            build_trade_statistics_request(
                confirmed_transaction=self.golden[
                    "confirmed_transaction"
                ],
                source_preference="LIVE",
                hs_code="02AB",
                hs_code_confirmed=True,
            )
        self.assertEqual(context.exception.code, "INVALID_HS_CODE")

    def test_unconfirmed_hs_fails_closed(self):
        with self.assertRaises(TradeStatisticsRequestError):
            build_trade_statistics_request(
                confirmed_transaction=self.golden[
                    "confirmed_transaction"
                ],
                source_preference="LIVE",
                hs_code="0202",
                hs_code_confirmed=False,
            )

    def test_product_description_is_never_inferred_as_hs(self):
        extraction = self.golden["extraction"].model_copy(
            update={"payment_terms": "precision equipment machinery parts"}
        )
        self.assertIn("precision equipment", extraction.payment_terms)
        request = build_trade_statistics_request(
            confirmed_transaction=self.golden["confirmed_transaction"],
            source_preference="OFFICIAL_FIXTURE",
        )
        self.assertIsNone(request.hs_code)
        self.assertFalse(request.hs_code_confirmed)

    def test_country_alias_is_canonicalized(self):
        request = _request(
            reporter_country="Republic of Korea",
            partner_country="Brazil",
        )
        self.assertEqual(request.reporter_country, "KR")
        self.assertEqual(request.partner_country, "BR")

    def test_invalid_country_code_is_rejected(self):
        with self.assertRaises(ValidationError):
            _request(partner_country="BRAZIL-UNKNOWN")

    def test_live_default_period_excludes_unpublished_month(self):
        request = build_trade_statistics_request(
            confirmed_transaction=self.golden["confirmed_transaction"],
            source_preference="LIVE",
            as_of=date(2026, 8, 1),
        )
        self.assertEqual(request.period_start, "2024-07")
        self.assertEqual(request.period_end, "2026-06")


class TradeStatisticsProviderTests(unittest.TestCase):
    def test_more_than_one_year_is_split_into_safe_requests(self):
        self.assertEqual(
            split_period_range("2024-07", "2026-06"),
            [("2024-07", "2025-06"), ("2025-07", "2026-06")],
        )

    def test_two_period_results_are_merged_and_sorted(self):
        seen_urls = []

        def transport(url, timeout):
            del timeout
            seen_urls.append(url)
            query = parse_qs(urlparse(url).query)
            if query["strtYymm"] == ["202407"]:
                return _xml(_xml_item("2024.07"))
            return _xml(_xml_item("2026.06", export="200", balance="160"))

        snapshot = CustomsOpenApiProvider(
            api_key="test-key",
            transport=transport,
            as_of=date(2026, 8, 1),
        ).fetch(_request())

        self.assertEqual(
            [item.period for item in snapshot.observations],
            ["2024-07", "2026-06"],
        )
        self.assertEqual(len(seen_urls), 2)
        first = parse_qs(urlparse(seen_urls[0]).query)
        second = parse_qs(urlparse(seen_urls[1]).query)
        self.assertEqual(first["strtYymm"], ["202407"])
        self.assertEqual(first["endYymm"], ["202506"])
        self.assertEqual(second["strtYymm"], ["202507"])
        self.assertEqual(second["endYymm"], ["202606"])
        self.assertEqual(first["cntyCd"], ["BR"])

    def test_duplicate_observation_is_blocked(self):
        provider = CustomsOpenApiProvider(
            api_key="test-key",
            transport=lambda _url, _timeout: _xml(
                _xml_item("2025.01"),
                _xml_item("2025.01"),
            ),
            as_of=date(2026, 8, 1),
        )
        with self.assertRaises(TradeStatisticsProviderError) as context:
            provider.fetch(
                _request(period_start="2025-01", period_end="2025-01")
            )
        self.assertEqual(context.exception.code, "VALIDATION_FAILED")

    def test_live_trade_balance_uses_one_usd_tolerance(self):
        request = _request(period_start="2025-01", period_end="2025-01")
        with self.assertRaises(TradeStatisticsProviderError) as context:
            parse_customs_xml(
                _xml(_xml_item("2025.01", balance="62")),
                request,
                as_of=date(2026, 8, 1),
            )
        self.assertEqual(context.exception.code, "VALIDATION_FAILED")

    def test_country_mismatch_is_blocked(self):
        request = _request(period_start="2025-01", period_end="2025-01")
        with self.assertRaises(TradeStatisticsProviderError) as context:
            parse_customs_xml(
                _xml(_xml_item("2025.01", country="US")),
                request,
                as_of=date(2026, 8, 1),
            )
        self.assertEqual(context.exception.code, "VALIDATION_FAILED")

    def test_hs_mismatch_is_blocked(self):
        request = _request(
            period_start="2025-01",
            period_end="2025-01",
            hs_code="0202",
            hs_level=4,
            hs_code_confirmed=True,
        )
        with self.assertRaises(TradeStatisticsProviderError) as context:
            parse_customs_xml(
                _xml(_xml_item("2025.01", hs_code="0303")),
                request,
                as_of=date(2026, 8, 1),
            )
        self.assertEqual(context.exception.code, "VALIDATION_FAILED")

    def test_negative_weight_is_blocked(self):
        request = _request(period_start="2025-01", period_end="2025-01")
        with self.assertRaises(ValidationError):
            parse_customs_xml(
                _xml(_xml_item("2025.01", export_weight="-1")),
                request,
                as_of=date(2026, 8, 1),
            )

    def test_non_finite_number_is_parse_error(self):
        request = _request(period_start="2025-01", period_end="2025-01")
        with self.assertRaises(TradeStatisticsProviderError) as context:
            parse_customs_xml(
                _xml(_xml_item("2025.01", export="NaN")),
                request,
                as_of=date(2026, 8, 1),
            )
        self.assertEqual(context.exception.code, "RESPONSE_PARSE_ERROR")

    def test_empty_response_is_no_data(self):
        result = retrieve_trade_statistics(
            _request(period_start="2025-01", period_end="2025-01"),
            settings=Settings(customs_trade_api_key="test-key"),
            transport=lambda _url, _timeout: _xml(),
        )
        self.assertEqual(result.status, "NO_DATA")
        self.assertEqual(result.error_code, "NO_DATA")
        self.assertIsNone(result.summary)

    def test_xml_parse_failure_is_structured(self):
        result = retrieve_trade_statistics(
            _request(period_start="2025-01", period_end="2025-01"),
            settings=Settings(customs_trade_api_key="test-key"),
            transport=lambda _url, _timeout: b"not xml",
        )
        self.assertEqual(result.status, "VALIDATION_FAILED")
        self.assertEqual(result.error_code, "RESPONSE_PARSE_ERROR")

    def test_timeout_is_structured_and_does_not_include_key(self):
        def timeout(_url, _timeout):
            raise socket.timeout("timed out")

        result = retrieve_trade_statistics(
            _request(period_start="2025-01", period_end="2025-01"),
            settings=Settings(customs_trade_api_key="secret-test-key"),
            transport=timeout,
        )
        self.assertEqual(result.status, "UPSTREAM_UNAVAILABLE")
        self.assertEqual(result.error_code, "UPSTREAM_TIMEOUT")
        self.assertNotIn("secret-test-key", result.model_dump_json())

    def test_missing_api_key_is_explicit(self):
        result = retrieve_trade_statistics(
            _request(period_start="2025-01", period_end="2025-01"),
            settings=Settings(customs_trade_api_key=None),
        )
        self.assertEqual(result.status, "MISSING_API_KEY")
        self.assertEqual(result.error_code, "MISSING_API_KEY")
        self.assertIn("API 키 설정", result.user_message)

    def test_upstream_error_result_code_is_blocked(self):
        result = retrieve_trade_statistics(
            _request(period_start="2025-01", period_end="2025-01"),
            settings=Settings(customs_trade_api_key="test-key"),
            transport=lambda _url, _timeout: _xml(result_code="99"),
        )
        self.assertEqual(result.status, "UPSTREAM_UNAVAILABLE")
        self.assertEqual(result.error_code, "UPSTREAM_ERROR")

    def test_future_or_unpublished_period_is_rejected(self):
        result = retrieve_trade_statistics(
            _request(period_start="2026-07", period_end="2026-07"),
            settings=Settings(customs_trade_api_key="test-key"),
            transport=lambda _url, _timeout: _xml(
                _xml_item("2026.07")
            ),
        )
        self.assertEqual(result.status, "VALIDATION_FAILED")
        self.assertEqual(result.error_code, "INVALID_PERIOD")


class TradeStatisticsFixtureAndSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = build_golden_consultation_fixture()
        cls.request = cls.golden["trade_statistics_request"]
        cls.result = cls.golden["trade_statistics"]

    def test_official_raw_fixture_hash_matches(self):
        self.assertEqual(
            file_sha256(DEFAULT_RAW_PATH),
            "16fcfc5222aab3e9b58dc3481cd130c411dbbcb4b103f994a1b42d872edb9cb5",
        )

    def test_normalized_snapshot_hash_matches(self):
        snapshot = load_trade_statistics_fixture(self.request)
        self.assertEqual(
            canonical_snapshot_hash(snapshot),
            snapshot.normalized_sha256,
        )
        self.assertEqual(
            snapshot.normalized_sha256,
            "3e3120223e00013fcfbe9168bb794be21834c3c329b58d618fa84c09308e6b5b",
        )

    def test_fixture_has_24_real_months_and_no_zero_fill(self):
        snapshot = load_trade_statistics_fixture(self.request)
        self.assertEqual(len(snapshot.observations), 24)
        self.assertEqual(snapshot.observation_start, "2024-07")
        self.assertEqual(snapshot.observation_end, "2026-06")
        self.assertEqual(
            [item.period for item in snapshot.observations],
            month_range("2024-07", "2026-06"),
        )

    def test_latest_and_previous_12_month_totals(self):
        summary = self.result.summary
        self.assertIsNotNone(summary)
        self.assertEqual(summary.latest_12m_export_usd, "8282425000")
        self.assertEqual(summary.latest_12m_import_usd, "6154122000")
        self.assertEqual(summary.latest_12m_balance_usd, "2128302000")
        self.assertEqual(summary.previous_12m_export_usd, "5296893000")
        self.assertEqual(summary.previous_12m_import_usd, "7385792000")
        self.assertEqual(summary.previous_12m_balance_usd, "-2088899000")

    def test_yoy_is_decimal_and_recent_direction_is_deterministic(self):
        summary = self.result.summary
        self.assertEqual(
            summary.export_yoy_pct,
            "56.36383442142403103102139311",
        )
        self.assertEqual(
            summary.import_yoy_pct,
            "-16.67620750760378846303822258",
        )
        self.assertEqual(summary.recent_direction, "INCREASED")

    def test_previous_zero_is_not_rendered_as_infinity(self):
        periods = month_range("2024-07", "2026-06")
        snapshot = _synthetic_snapshot(
            periods,
            previous_export="0",
            current_export="100",
        )
        summary = summarize_trade_statistics(_request(), snapshot)
        self.assertIsNone(summary.export_yoy_pct)
        self.assertEqual(
            summary.export_comparison_status,
            "PREVIOUS_ZERO",
        )

    def test_missing_month_is_not_converted_to_zero(self):
        periods = month_range("2024-07", "2026-06")
        periods.remove("2025-12")
        snapshot = _synthetic_snapshot(periods)
        summary = summarize_trade_statistics(_request(), snapshot)
        self.assertEqual(summary.missing_month_count, 1)
        self.assertIsNone(summary.latest_12m_export_usd)
        self.assertEqual(
            summary.export_comparison_status,
            "MISSING_MONTHS",
        )

    def test_insufficient_history_does_not_claim_12_month_comparison(self):
        periods = month_range("2026-01", "2026-06")
        snapshot = _synthetic_snapshot(periods)
        request = _request(period_start="2026-01", period_end="2026-06")
        summary = summarize_trade_statistics(request, snapshot)
        self.assertIsNone(summary.latest_12m_export_usd)
        self.assertEqual(
            summary.export_comparison_status,
            "INSUFFICIENT_HISTORY",
        )
        self.assertIn("충분하지 않아", summary.user_summary)
        self.assertIn("확인 가능한 관측기간", summary.user_summary)
        self.assertNotIn("최근 12개월 동안", summary.user_summary)

    def test_country_total_fixture_does_not_create_hs_code(self):
        summary = self.result.summary
        self.assertEqual(summary.scope, "COUNTRY_TOTAL")
        self.assertIsNone(summary.hs_code)
        self.assertTrue(
            any("HS Code 미확인" in item for item in summary.missing_information)
        )

    def test_raw_monthly_sums_match_official_total_rounding_tolerance(self):
        raw = json.loads(DEFAULT_RAW_PATH.read_text(encoding="utf-8"))
        snapshot = load_trade_statistics_fixture(self.request)
        calculated = sum(
            Decimal(item.export_value_usd)
            for item in snapshot.observations
        )
        reported = Decimal(
            raw["total_record"]["expUsdAmt"].replace(",", "")
        ) * Decimal("1000")
        self.assertLessEqual(abs(calculated - reported), Decimal("1000"))
        self.assertEqual(DEFAULT_FIXTURE_PATH.exists(), True)


class TradeStatisticsIntegrationBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = build_golden_consultation_fixture()

    def test_request_fingerprint_changes_with_every_binding_axis(self):
        base = self.golden["trade_statistics_request"].model_copy(
            update={"source_preference": "LIVE", "snapshot_version": None}
        )
        base_fingerprint = trade_statistics_request_fingerprint(base)
        variants = [
            base.model_copy(update={"partner_country": "US"}),
            base.model_copy(update={"trade_direction": "IMPORT"}),
            base.model_copy(
                update={
                    "hs_code": "02",
                    "hs_level": 2,
                    "hs_code_confirmed": True,
                }
            ),
            base.model_copy(update={"period_start": "2024-08"}),
            base.model_copy(
                update={
                    "source_preference": "OFFICIAL_FIXTURE",
                    "snapshot_version": TRADE_STATISTICS_FIXTURE_VERSION,
                }
            ),
            base.model_copy(
                update={"confirmed_transaction_fingerprint": "f" * 64}
            ),
        ]
        for variant in variants:
            with self.subTest(variant=variant.model_dump()):
                self.assertNotEqual(
                    trade_statistics_request_fingerprint(variant),
                    base_fingerprint,
                )

    def test_workflow_rejects_stale_trade_statistics_request(self):
        workflow = WorkflowOrchestrator(settings=Settings())
        state = workflow.initialize(
            mode="OFFLINE",
            extraction=self.golden["extraction"],
            validation=self.golden["validation"],
            confirmation=self.golden["confirmation"],
        )
        stale = self.golden["trade_statistics_request"].model_copy(
            update={"partner_country": "US"}
        )
        state = workflow.run_trade_statistics(state, stale)
        self.assertEqual(state.trade_statistics.status, StageStatus.FAILED)
        self.assertIsNone(state.trade_statistics.data)

    def test_new_analysis_clear_removes_trade_statistics_keys(self):
        state = {
            "confirmation": {"value": "old"},
            "trade_statistics_request": {"partner_country": "BR"},
            "trade_statistics_result": {"status": "OFFICIAL_FIXTURE"},
            "trade_statistics_trace": {"snapshot_id": "old"},
            "trade_statistics_error": {"error_code": "OLD"},
            "trade_statistics_hs_code_widget": "0202",
            "trade_statistics_hs_confirmed_widget": True,
        }
        clear_confirmation_and_later(state)
        for key in (
            "trade_statistics_request",
            "trade_statistics_result",
            "trade_statistics_trace",
            "trade_statistics_error",
            "trade_statistics_hs_code_widget",
            "trade_statistics_hs_confirmed_widget",
        ):
            self.assertNotIn(key, state)

    def test_packet_uses_same_statistics_object_without_priority_change(self):
        fixture = self.golden
        with_statistics = fixture["decision"]
        without_statistics = build_decision_support(
            case_id="golden_export_br_001",
            extraction=fixture["extraction"],
            confirmation=fixture["confirmation"],
            stage1=fixture["stage1"],
            stage2_input=fixture["stage2_input"],
            stage2_result=fixture["stage2"],
            trade_settlement_risk=fixture["trade_risk"],
            country_environment=fixture["country_environment"],
            generated_at="2026-07-29T09:00:00+09:00",
            confirmed_transaction=fixture["confirmed_transaction"],
        )
        packet = with_statistics.consultation_packet.packet
        self.assertEqual(
            packet.trade_statistics.model_dump(),
            fixture["trade_statistics"].model_dump(),
        )
        self.assertEqual(
            [item.title for item in packet.consultation_priorities],
            [
                item.title
                for item in (
                    without_statistics.consultation_packet.packet
                    .consultation_priorities
                )
            ],
        )
        self.assertEqual(
            with_statistics.risk_assessment,
            without_statistics.risk_assessment,
        )
        self.assertEqual(
            fixture["country_environment"].review_priority,
            "STANDARD_REVIEW",
        )

    def test_packet_rejects_statistics_from_another_transaction(self):
        fixture = self.golden
        stale_result = fixture["trade_statistics"].model_copy(
            update={
                "request": fixture["trade_statistics_request"].model_copy(
                    update={"partner_country": "US"}
                )
            }
        )
        with self.assertRaises(ValueError):
            build_decision_support(
                case_id="golden_export_br_001",
                extraction=fixture["extraction"],
                confirmation=fixture["confirmation"],
                stage1=fixture["stage1"],
                stage2_input=fixture["stage2_input"],
                stage2_result=fixture["stage2"],
                trade_settlement_risk=fixture["trade_risk"],
                country_environment=fixture["country_environment"],
                trade_statistics=stale_result,
                confirmed_transaction=fixture["confirmed_transaction"],
            )

    def test_stage5_json_and_markdown_use_packet_values(self):
        fixture = self.golden
        stage3 = generate_strategy_candidates(fixture["stage2"])
        stage4 = search_offline_kb(
            query="수출대금 회수 환율 관리 운영자금",
            trade_type="EXPORT",
        )
        report = generate_deterministic_report(
            extraction=fixture["extraction"],
            confirmation=fixture["confirmation"],
            stage1=fixture["stage1"],
            stage2=fixture["stage2"],
            stage3=stage3,
            stage4=stage4,
            consultation_packet=(
                fixture["decision"].consultation_packet.packet
            ),
            confirmed_transaction=fixture["confirmed_transaction"],
        )
        payload = json.loads(report.model_dump_json())
        statistics = payload["report_json"]["consultation"][
            "trade_statistics"
        ]
        self.assertEqual(
            statistics["summary"]["latest_12m_export_usd"],
            "8282425000",
        )
        self.assertEqual(
            statistics["summary"]["latest_period"],
            "2026-06",
        )
        self.assertIn("## 8. 거래국 무역 통계", report.markdown)
        self.assertIn("USD 8,282,425,000", report.markdown)
        self.assertIn("+56.4%", report.markdown)
        self.assertIn("-16.7%", report.markdown)
        self.assertNotIn(
            "56.36383442142403103102139311%",
            report.markdown,
        )
        self.assertIn("HS Code가 확인되지 않아", report.markdown)
        self.assertTrue(report.critique.passed, report.critique.issues)
        altered = critique_report(
            markdown=report.markdown.replace("+56.4%", "+56.5%"),
            source_bundle=report.report_json,
            scenario_kind=fixture["stage1"].kind,
            probability_valid=fixture["stage1"].probability_valid,
        )
        self.assertFalse(altered.passed)
        self.assertIn("근거 JSON에 없는 숫자: +56.5%", altered.issues)

    def test_stage5_critic_blocks_trade_statistics_policy_leakage(self):
        fixture = self.golden
        report = generate_deterministic_report(
            extraction=fixture["extraction"],
            confirmation=fixture["confirmation"],
            stage1=fixture["stage1"],
            stage2=fixture["stage2"],
            stage3=generate_strategy_candidates(fixture["stage2"]),
            stage4=search_offline_kb(
                query="수출대금 회수 환율 관리 운영자금",
                trade_type="EXPORT",
            ),
            consultation_packet=(
                fixture["decision"].consultation_packet.packet
            ),
            confirmed_transaction=fixture["confirmed_transaction"],
        )
        critique = critique_report(
            markdown=(
                report.markdown
                + "\n- 무역통계 증가를 환율 하락 가능성의 근거로 "
                "사용합니다."
            ),
            source_bundle=report.report_json,
            scenario_kind=fixture["stage1"].kind,
            probability_valid=fixture["stage1"].probability_valid,
        )
        self.assertFalse(critique.passed)
        self.assertIn(
            "무역통계를 환율 방향 예측 근거로 사용했습니다.",
            critique.issues,
        )

    def test_statistics_do_not_change_stage2_or_stage3(self):
        fixture = self.golden
        stage2_before = fixture["stage2"].model_dump_json()
        stage3_before = generate_strategy_candidates(fixture["stage2"])
        retrieve_trade_statistics(fixture["trade_statistics_request"])
        stage3_after = generate_strategy_candidates(fixture["stage2"])
        self.assertEqual(fixture["stage2"].model_dump_json(), stage2_before)
        self.assertEqual(stage3_after, stage3_before)

    def test_trade_statistics_failure_does_not_block_financial_result(self):
        result = retrieve_trade_statistics(
            _request(period_start="2025-01", period_end="2025-01"),
            settings=Settings(customs_trade_api_key=None),
        )
        self.assertEqual(result.status, "MISSING_API_KEY")
        self.assertEqual(
            self.golden["stage2"].base_required_or_proceeds_krw,
            "140000000.00",
        )
        self.assertEqual(
            [
                item.title
                for item in self.golden["decision"]
                .consultation_packet.packet.consultation_priorities
            ],
            [
                "수출대금 회수 보호 상담",
                "환율 관리 상담",
                "운영자금 버퍼·수출대금 회수시점 상담",
            ],
        )


class TradeStatisticsStreamlitTests(unittest.TestCase):
    def test_unavailable_demo_fixture_is_explicit_and_finance_remains(self):
        from streamlit.testing.v1 import AppTest

        with patch.dict(
            "os.environ",
            {
                "APP_ENV": "development",
                "TRADE_STATISTICS_PROVIDER": "auto",
                "OPENAI_API_KEY": "",
                "ENABLE_LIVE_DOCUMENT_EXTRACTION": "false",
                "ENABLE_LLM_REPORT": "false",
                "ENABLE_OFFICIAL_WEB_SEARCH": "false",
            },
            clear=False,
        ):
            app = AppTest.from_file("app.py", default_timeout=30).run()
            next(
                button
                for button in app.button
                if button.label == "미국 수출 샘플"
            ).click().run()

        self.assertEqual(len(app.exception), 0)
        result = app.session_state["trade_statistics_result"]
        self.assertEqual(result["status"], "FIXTURE_NOT_AVAILABLE")
        self.assertEqual(result["request"]["partner_country"], "US")
        self.assertIn("stage2_result", app.session_state)
        visible = " ".join(
            [item.value for item in app.markdown]
            + [item.value for item in app.caption]
            + [item.value for item in app.info]
        )
        self.assertIn("거래국 무역 통계", visible)
        self.assertIn("검증된 공식 통계 fixture", visible)
        self.assertIn(
            "현재 환율·현금흐름 계산에는 영향을 주지 않습니다",
            visible,
        )
        self.assertIn(
            "출처 및 기술정보",
            [item.label for item in app.expander],
        )


if __name__ == "__main__":
    unittest.main()
