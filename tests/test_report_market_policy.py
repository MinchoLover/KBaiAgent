import json
import unittest

from src.demo import run_integrated_decision_demo
from src.stage5.critic import critique_report


class ReportMarketPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = run_integrated_decision_demo("BUYER")
        cls.report = cls.demo["report"]

    def _critique(self, unsafe_line):
        return critique_report(
            markdown="{}\n{}".format(
                self.report.markdown,
                unsafe_line,
            ),
            source_bundle=self.report.report_json,
            scenario_kind=self.demo["stage1"].kind,
            probability_valid=self.demo["stage1"].probability_valid,
        )

    def test_report_bundle_excludes_raw_document_evidence(self):
        serialized = json.dumps(
            self.report.report_json,
            ensure_ascii=False,
        )
        self.assertNotIn("source_text", serialized)
        self.assertNotIn("original_values", serialized)

    def test_critic_rejects_q90_as_occurrence_probability(self):
        critique = self._critique(
            "q90은 90% 확률로 발생합니다. "
            "[source: market_integration.scenario_build."
            "model_path_scenarios]"
        )
        self.assertIn(
            "q90을 90% 발생확률로 오해하게 표현했습니다.",
            critique.issues,
        )

    def test_critic_rejects_uncalibrated_direction_as_probability(self):
        critique = self._critique(
            "방향 점수 0.712는 실제 발생확률입니다. "
            "[source: market_integration.forecast_load.forecast."
            "direction]"
        )
        self.assertIn(
            "미보정 방향 점수를 실제 발생확률로 표현했습니다.",
            critique.issues,
        )

    def test_critic_rejects_horizon_extrapolation(self):
        critique = self._critique(
            "결제기간 90일 환율을 예측했습니다. "
            "[source: market_integration.scenario_build."
            "horizon_mismatch]"
        )
        self.assertIn(
            "21거래일 모델을 결제기간 밖으로 외삽했습니다.",
            critique.issues,
        )

    def test_critic_rejects_news_in_numeric_calculation(self):
        critique = self._critique(
            "뉴스를 환율 숫자 계산에 반영했습니다. "
            "[source: market_integration.forecast_load.forecast."
            "market_context]"
        )
        self.assertIn(
            "설명용 뉴스를 금융 숫자 계산에 사용한 것처럼 표현했습니다.",
            critique.issues,
        )


if __name__ == "__main__":
    unittest.main()
