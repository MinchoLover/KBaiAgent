# Stage 1 JSON Mapping

| Raw JSON path | 정규화 필드 | 사용 |
| --- | --- | --- |
| `schema_version` | `source.raw_schema_version` | 계약 검증 |
| `generated_at` | `source.generated_at` | 생성시각·감사 |
| `prediction_date` | `source.prediction_date` | horizon 시작 |
| `horizon.trading_days` | `horizon.trading_days` | 기본 21일 범위 |
| `forecast.terminal_direction_21d.p_usdkrw_up` | `direction.up_score` | 시장 문맥만 |
| `forecast.terminal_direction_21d.p_usdkrw_down` | `direction.down_score` | 시장 문맥만 |
| `forecast.terminal_direction_21d.direction` | `direction.label` | 시장 문맥만 |
| `forecast.terminal_direction_21d.probability_calibrated` | `direction.calibrated_probability` | 확률 사용 차단 |
| `forecast.maximum_rise_21d.quantiles_simple_return.q10/q50/q75/q90` | `path_risk.up.*` | 수입 경로위험 |
| `forecast.maximum_fall_21d.quantiles_simple_return.q10/q50/q75/q90` | `path_risk.down.*` | 수출 경로위험 |
| `forecast.combined_interpretation.summary` | `market_context.summary` | 설명 |
| `decision_basis.terminal_direction_v25.description` | `market_context.decision_basis` | 방향 근거 |
| `decision_basis.*.top_market_factors` | `market_context.top_factors` | 설명 근거 |
| `news_market_context.news_used_as_predictor` | `market_context.news_used_as_predictor` | 반드시 false |
| `news_market_context.changed_model_forecast` | `market_context.changed_model_forecast` | 반드시 false |
| `news_market_context.role` | `market_context.role` | 설명 범위 |
| `news_market_context.key_news_events` | `market_context.news` | 중복 제거 후 설명 |
| `news_market_context.warning` | `market_context.warning` | UI·보고서 |
| `data_quality.market_data_latest_date` | `quality.market_data_latest_date` | stale 판정 |
| `data_quality.model_bundle_trained_as_of` | `quality.model_trained_as_of` | 모델 기준일 |
| `data_quality.market_refresh.partial_fallback_used` | `quality.partial_fallback_used` | 품질 경고 |
| `data_quality.market_refresh.failed_series` | `quality.failed_series` | 품질 경고 |
| `data_quality.news_refresh.query_errors` | `market_context.query_errors` | 뉴스만 degraded |
| `data_quality.research_only` | `quality.research_only` | 연구용 고지 |

모든 score·return 문자열은 `Decimal`로 재검증됩니다. Stage 1에는 절대 spot이
없으므로 분위수만으로 환율을 추정하지 않습니다.
