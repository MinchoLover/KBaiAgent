import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from src.application.market_integration_service import integrate_stage1_market
from src.config import Settings
from src.domain.stage2_models import ExposureInput, Stage2Input
from src.stage2.engine import run_stage2
from src.ui.layout import NAV_ITEMS, PAGE_LABELS
from src.ui.user_views import (
    build_fx_forecast_view,
    build_market_news_views,
)


ROOT = Path(__file__).resolve().parents[1]
FORECAST_FIXTURE = (
    ROOT
    / "src"
    / "integration_assets"
    / "stage1"
    / "latest_forecast.json"
)


class UserCenteredUiProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.integration = integrate_stage1_market(
            settings=Settings(
                demo_mode=True,
                stage1_provider="file",
                stage1_forecast_file=str(FORECAST_FIXTURE),
                spot_rate_provider="fixture",
            ),
            currency="USD",
            settlement_date="2026-08-10",
            provider_name="file",
            spot_provider_name="fixture",
            now=datetime(2026, 7, 27, 9, 0, tzinfo=timezone.utc),
        )

    def test_four_user_pages_are_ordered_by_customer_journey(self):
        self.assertEqual(
            [item["label"] for item in NAV_ITEMS[1:]],
            [
                "거래 분석",
                "환율 전망·위험",
                "금융지원 추천",
                "상담 준비·보고서",
            ],
        )
        self.assertEqual(
            list(PAGE_LABELS.values())[1:],
            [
                "거래 분석",
                "환율 전망·위험",
                "금융지원 추천",
                "상담 준비·보고서",
            ],
        )

    def test_forecast_view_uses_stage1_direction_center_and_range(self):
        view = build_fx_forecast_view(self.integration)

        self.assertIsNotNone(view)
        assert view is not None
        self.assertEqual(view.pair, "USD/KRW")
        self.assertEqual(view.direction, "하락")
        self.assertEqual(view.center_rate, Decimal("1386.0000"))
        self.assertEqual(view.center_move, Decimal("-0.010"))
        self.assertEqual(view.lower_rate, Decimal("1349.6000"))
        self.assertEqual(view.upper_rate, Decimal("1449.0000"))
        self.assertEqual(view.target_date, "2026-08-10")
        self.assertIn("보장하지 않습니다", view.disclaimer)

    def test_forecast_view_does_not_invent_confidence(self):
        view = build_fx_forecast_view(self.integration)

        self.assertIsNotNone(view)
        assert view is not None
        serialized = " ".join(
            [
                view.direction_sentence,
                view.uncertainty_copy,
                view.disclaimer,
            ]
        )
        self.assertNotIn("95%", serialized)
        self.assertNotIn("확실히", serialized)
        self.assertIn("범위", serialized)

    def test_model_center_and_cashflow_customer_rate_are_not_mixed(self):
        view = build_fx_forecast_view(self.integration)
        self.assertIsNotNone(view)
        assert view is not None
        stage2_input = Stage2Input(
            as_of_date="2026-07-29",
            exposures=[
                ExposureInput(
                    sequence=1,
                    trade_type="EXPORT",
                    currency="USD",
                    foreign_amount="100000",
                    settlement_date="2026-08-10",
                    usable_fx_balance="0",
                )
            ],
            current_krw_cash="0",
            minimum_cash_buffer="0",
            bank_spread_bps="15",
        )
        result = run_stage2(
            stage2_input,
            self.integration.stage1_load.scenario_set,
        )
        center_result = next(
            item
            for item in result.scenario_results
            if item.scenario_name == "MODEL_DOWN_Q50"
        )

        self.assertEqual(view.center_rate, Decimal("1386.0000"))
        self.assertEqual(center_result.scenario_rate, "1386.0000")
        self.assertEqual(center_result.applied_rate, "1383.92100000")
        self.assertEqual(result.open_exposure, "100000")
        self.assertEqual(result.natural_offset, "0")
        self.assertEqual(result.hedged_amount, "0")
        self.assertEqual(center_result.fx_krw_inflow, "138392100.00")
        self.assertEqual(
            Decimal(center_result.fx_krw_inflow),
            Decimal(result.open_exposure)
            * Decimal(center_result.applied_rate),
        )
        self.assertEqual(
            center_result.source_paths["applied_rate"],
            "stage2.input.bank_spread_bps+stage1.scenario_rate",
        )

    def test_fx_forecast_top_uses_readable_compact_disclosure_contract(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        theme_source = (ROOT / "src" / "ui" / "theme.py").read_text(
            encoding="utf-8"
        )

        for expected in (
            'with st.expander("적용값 계산 기준", expanded=False):',
            "모델 중심환율 raw 값",
            "화면 표시값은 소수 둘째 자리 반올림",
            "거래 스프레드",
            "자연상계",
            "기존 헤지",
            "엔진 적용환율은 거래 방향에 따른 은행 스프레드를 반영하므로",
            "AI 전망은 참고 정보이며 확정 환율이나",
            "실제 수취·지급 금액을 보장하지 않습니다.",
        ):
            self.assertIn(expected, app_source)
        self.assertNotIn("st.info(forecast_notice)", app_source)

        for expected in (
            ".st-key-workflow_analysis .page-header h1",
            ".fx-forecast-copy h2",
            ".fx-primary-metric strong",
            ".fx-forecast-metrics strong",
            ".fx-range-chart .range-heading strong",
            ".fx-business-impact .impact-metrics b",
            ".fx-calculation-basis",
            ".fx-forecast-notice",
            ".fx-forecast-metrics {grid-template-columns: 1fr;}",
            ".fx-business-impact .impact-metrics {grid-template-columns: 1fr;}",
        ):
            self.assertIn(expected, theme_source)

    def test_news_views_preserve_only_stored_articles_and_cap_count(self):
        source_news = self.integration.forecast_load.forecast.market_context.news
        views = build_market_news_views(self.integration, limit=1)

        self.assertEqual(len(views), 1)
        self.assertEqual(views[0].headline, source_news[0].headline)
        self.assertEqual(views[0].summary, source_news[0].summary)
        self.assertEqual(views[0].url, source_news[0].url)
        self.assertEqual(views[0].published_at, "게시일 미확인")
        self.assertIn("압력", views[0].pressure_label)

    def test_news_absence_is_safe_and_does_not_change_forecast(self):
        without_news = self.integration.model_copy(
            update={
                "forecast_load": self.integration.forecast_load.model_copy(
                    update={
                        "forecast": (
                            self.integration.forecast_load.forecast.model_copy(
                                update={
                                    "market_context": self.integration
                                    .forecast_load.forecast.market_context
                                    .model_copy(update={"news": []})
                                }
                            )
                        )
                    }
                )
            }
        )

        original = build_fx_forecast_view(self.integration)
        projected = build_fx_forecast_view(without_news)
        self.assertEqual(build_market_news_views(without_news), [])
        self.assertEqual(original, projected)

    def test_internal_debug_flag_defaults_false(self):
        self.assertFalse(Settings().show_internal_debug)


if __name__ == "__main__":
    unittest.main()
