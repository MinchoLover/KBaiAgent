# USD/KRW 예측 JSON 읽는 방법

이 문서는 `web_runtime/output/latest_forecast.json`의 각 항목을
설명한다. 이 JSON은 약 1개월인 향후 21거래일의 원/달러 방향과
기간 중 최대 상승·하락폭을 제공한다.

## 1. 가장 먼저 확인할 항목

```json
{
  "prediction_date": "2026-07-27",
  "horizon": {
    "trading_days": 21,
    "description": "약 1개월"
  }
}
```

- `prediction_date`: 예측에 사용한 최신 시장 데이터 날짜
- `trading_days`: 예측 기간이다. 21거래일은 달력 기준 약 1개월이다.
- `generated_at`: JSON을 생성한 UTC 시각이다.

## 2. 사용 모델

```json
{
  "models": {
    "terminal_direction": {"version": "v25"},
    "maximum_rise": {"version": "v36"},
    "maximum_fall": {"version": "v34"}
  }
}
```

- `v25`: 정확히 21거래일 뒤 USD/KRW가 현재보다 상승할지 하락할지
  확률로 계산하는 Logistic Regression
- `v36`: 향후 21거래일 동안 발생할 수 있는 최대 USD/KRW 상승폭을
  계산하는 Quantile Gradient Boosting
- `v34`: 향후 21거래일 동안 발생할 수 있는 최대 USD/KRW 하락폭을
  계산하는 Quantile Gradient Boosting

`market_39`는 시장 데이터 원본이 39개라는 의미가 아니라, 환율·금리·
달러인덱스·주식·유가·변동성 등에서 계산한 모델 입력 특징이
39개라는 뜻이다. v36은 여기에 USD/KRW OHLC 특징 12개를 추가해
총 51개를 사용한다.

## 3. 방향확률

```json
{
  "p_usdkrw_up": 0.276,
  "p_usdkrw_down": 0.724,
  "direction": "usdkrw_down"
}
```

- `usdkrw_up`: USD/KRW 상승, 즉 달러 강세·원화 약세
- `usdkrw_down`: USD/KRW 하락, 즉 달러 약세·원화 강세
- `p_usdkrw_up`: 21거래일 뒤 환율이 현재보다 높을 모델 확률
- `p_usdkrw_down`: 21거래일 뒤 환율이 현재보다 낮을 모델 확률

위 예시는 모델이 USD/KRW 하락 가능성을 0.724, 즉 약 72.4%로
계산했다는 뜻이다. `probability_calibrated: false`는 이 수치를
통계적으로 완전히 보정된 실제 발생확률로 보장할 수 없다는 뜻이다.

## 4. 최대 상승폭과 최대 하락폭

```json
{
  "quantiles_simple_return": {
    "q10": 0.001,
    "q50": 0.015,
    "q75": 0.026,
    "q90": 0.035
  }
}
```

숫자는 비율이다. `0.015`는 약 1.5%를 뜻한다.

- `q10`: 낮은 변동 시나리오
- `q50`: 중앙 시나리오. 모델 예측분포의 중간값
- `q75`: 비교적 큰 변동 시나리오
- `q90`: 상위 위험 시나리오

예를 들어 v36의 q50이 `0.015`라면 향후 21일 중 최대 USD/KRW
상승폭의 중앙 추정치가 약 1.5%라는 뜻이다. v34의 q90이 `0.036`
이라면 큰 하락 시나리오에서 최대 하락폭이 약 3.6% 수준이라는
뜻이다. q90은 환율이 반드시 그만큼 움직인다는 의미가 아니다.

종착점 방향과 기간 중 움직임은 서로 모순되지 않는다. 21일 뒤에는
환율이 하락하더라도 그 전에 일시적으로 상승할 수 있기 때문이다.

## 5. decision_basis

`decision_basis`는 각 모델이 왜 그런 결과를 냈는지 보여주는 설명
영역이다.

### v25

```json
{
  "method": "standardized_feature_x_logistic_coefficient",
  "description": "…모델이 USD/KRW 하락 확률을 더 높게 판단했다.",
  "top_market_factors": []
}
```

v25는 39개 특징을 모두 사용한다. 각 특징의 현재 값을 표준화한 뒤
학습된 계수를 곱하고, 이를 모두 합쳐 상승·하락 확률을 계산한다.

- `current_value`: 현재 특징값
- `training_median`: 최근 5년 학습자료의 중앙값
- `standardized_value`: 서로 단위가 다른 특징을 비교하기 위해
  표준화한 값
- `log_odds_contribution`: 이번 예측에서 해당 특징이 방향확률에
  기여한 정도
- `supports_usdkrw_up`: USD/KRW 상승 쪽 기여
- `supports_usdkrw_down`: USD/KRW 하락 쪽 기여

`top_market_factors`에는 39개 전체가 아니라 이번 예측에서 기여도의
절댓값이 가장 컸던 8개만 표시한다. `description`은 최종 선택
방향과 같은 쪽으로 가장 크게 기여한 특징 두 개를 한 문장으로
요약한다.

### v34와 v36

Gradient Boosting에는 Logistic처럼 특징별 단일 계수가 없다.
따라서 특징 하나를 학습기간 중앙값으로 바꿨을 때 q50 예측이 얼마나
달라지는지를 계산한다.

- `local_effect_on_q50_percentage_points`: 해당 특징을 중앙값으로
  바꿨을 때와 비교한 q50 최대 변동폭 차이
- `increases_expected_excursion`: 예상 최대 변동폭을 키운 방향
- `decreases_expected_excursion`: 예상 최대 변동폭을 줄인 방향

여기에도 전체 특징이 아니라 영향이 큰 8개만 표시한다. 이 값은
국소적인 모델 설명이며 각 값을 단순히 더해서 최종 예측을 재현할
수는 없다.

## 6. 뉴스 기반 시장 상황

```json
{
  "news_used_as_predictor": false,
  "changed_model_forecast": false
}
```

현재 뉴스는 환율 수치 예측 입력으로 사용하지 않는다. 최근 시장
상황을 설명하는 보조 정보이며 v25·v34·v36 결과를 바꾸지 않는다.

- `event_count`: 해당 지역으로 정확히 분류된 주요 사건 수
- `risk_level`: 기사에서 파악한 정성적 위험 수준
- `key_news_events`: 주요 사건의 요약, 단계, 방향, 신뢰도
- `analysis_confidence`: 뉴스 구조화 결과에 대한 분석 신뢰도

`MULTI`는 미국·한국·글로벌 중 하나에만 귀속하기 어려운 복수지역
사건이고 `OTHER`는 세 범주 밖의 사건이다. 이 사건들은
`key_news_events`에는 나타나지만 현재 `US`, `KR`, `GLOBAL`의
`event_count`에는 포함되지 않는다.

`news_used_as_predictor: false`인 만큼 뉴스 사건을 환율 변동의
확정적인 원인으로 읽으면 안 된다.

## 7. 데이터 품질

`data_quality`에서 실제 실행 상태를 확인한다.

- `market_data_latest_date`: 시장 데이터 최신일
- `model_bundle_trained_as_of`: 모델 번들의 마지막 학습 기준일
- `successful_series`: 정상적으로 갱신한 공개 시계열
- `failed_series`: 갱신에 실패해 번들 데이터로 보완한 시계열
- `partial_fallback_used`: 일부 데이터를 과거 값으로 보완했는지
- `query_errors`: 뉴스 검색 실패 내역
- `fallback_used`: 실시간 뉴스 대신 번들 뉴스를 사용했는지
- `ssd_used_at_runtime`: 실행 중 외장 SSD를 사용했는지
- `research_only`: 연구·대회 프로토타입인지

## 8. 숫자 표시

가독성을 위해 JSON의 실수는 소수점 셋째 자리까지 저장한다.
내부 모델은 반올림 전 원래 정밀도로 계산하고, 최종 JSON을 저장할
때만 반올림한다. 정수인 기사 수, 토큰 수, 거래일 수는 그대로
표시한다.

## 9. 실행과 확인

```bash
cd /Users/songsan/Developer/kb
KRW_ENABLE_OPENAI_NEWS=1 zsh scripts/run_web_forecast.sh
jq . web_runtime/output/latest_forecast.json
```

웹 API:

```bash
zsh scripts/serve_web_forecast.sh
```

```text
GET http://127.0.0.1:8765/api/forecast
GET http://127.0.0.1:8765/health
```

이 결과는 환율 방향과 위험 범위를 제공하는 연구용 분석 결과이며,
확정 환율·투자 지시·환헤지 행동 권고가 아니다.
