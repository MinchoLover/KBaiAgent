# Stage 1 Integration

## 책임 경계

`kb_macro_ai`는 USD/KRW 21거래일 모델을 실행하고 `KBaiAgent`는 그 결과를
검증·정규화해 소비합니다. 팀 모델 학습·추론 코드는 이 저장소에서 재구현하지
않습니다.

팀 저장소 실행:

```bash
KRW_ENABLE_OPENAI_NEWS=1 zsh scripts/run_web_forecast.sh
zsh scripts/serve_web_forecast.sh
curl --fail --silent http://127.0.0.1:8765/health
curl --fail --silent http://127.0.0.1:8765/api/forecast
```

## Provider 계약

`src/stage1/forecast_provider.py`:

```text
Stage1ForecastProvider
├─ fetch_latest() -> raw JSON object
└─ health() -> ProviderHealth
```

- `HttpStage1ForecastProvider`: timeout, 0~3회 제한 재시도, 1MB 기본 제한,
  JSON content type, redirect 차단, remote HTTPS+exact allowlist
- `FileStage1ForecastProvider`: `STAGE1_FORECAST_FILE`
- `MockStage1ForecastProvider`: 저장소의 공개 demo fixture

`STAGE1_PROVIDER=http`일 때 HTTP 실패 후 file, 그다음 mock을 시도합니다. 자동
fallback은 조용히 일어나지 않으며 source가 `FILE_FALLBACK` 또는
`MOCK_FALLBACK`, warning이 `FALLBACK_USED`가 됩니다. `file`이나 `mock`을 직접
선택한 경우에는 다른 provider로 자동 전환하지 않습니다.

## 모델 의미

- v25: 21거래일 종착점의 상승/하락 **방향 점수**
- v36: 21거래일 중 USD/KRW 최대 상승폭 예측분포 분위수
- v34: 21거래일 중 USD/KRW 최대 하락폭 예측분포 분위수
- 뉴스: 정성적 시장 문맥

`probability_calibrated=false`인 v25 점수는 발생확률·기대손실 가중치로 사용하지
않습니다. q90은 90% 발생확률이 아닙니다.

## 검증

- raw `schema_version == krw_forecast_web_v1`
- horizon 양수
- q10 ≤ q50 ≤ q75 ≤ q90, 각 값 0 이상, 설정 상한 이하
- up/down score 각각 0~1, 합 1 허용오차
- `news_used_as_predictor=false`, `changed_model_forecast=false`
- generated/prediction/data date ISO 검증과 기본 3 market-day stale 경고
- partial fallback, failed series, news query 오류, research-only를 보존
- 같은 사건·제목·정규화 URL의 뉴스 중복 제거 건수 보존

## 환경설정

```dotenv
STAGE1_PROVIDER=http
STAGE1_BASE_URL=http://127.0.0.1:8765
STAGE1_FORECAST_FILE=src/integration_assets/stage1/latest_forecast.json
STAGE1_HTTP_TIMEOUT_SECONDS=10
STAGE1_HTTP_RETRIES=1
STAGE1_MAX_RESPONSE_BYTES=1048576
STAGE1_MAX_STALENESS_MARKET_DAYS=3
STAGE1_MAX_PATH_RETURN=0.50
STAGE1_ALLOWED_HOSTS=
STAGE1_ALLOW_PRIVATE_ENDPOINTS=false
```

로컬 `127.0.0.1`/`localhost`는 개발 연결로 허용됩니다. 원격 HTTPS host는
`STAGE1_ALLOWED_HOSTS`에 정확히 등록해야 합니다.

## Fixture

다음 공개 fixture가 API key 없는 테스트와 데모에 사용됩니다.

```text
src/integration_assets/stage1/latest_forecast.json
src/integration_assets/stage1/JSON_README.md
src/integration_assets/stage1/team_model_report_3page.docx
```

fixture spot은 실시간 환율이 아니며 결과에 `TEST_FIXTURE_NOT_LIVE_RATE`로
표시됩니다.

## 발표·운영 readiness

다음 명령은 configured provider의 health와 normalized forecast를 읽어 실제 source,
prediction date, market-data date, freshness, provider fallback과 upstream
partial fallback을 표시한다.

```bash
python scripts/check_integration_readiness.py
```

Streamlit에서는 사이드바 `Integration Readiness`의 `연동 상태 점검`을 누른다.
Spot은 실제 환율을 새로 조회하지 않고 설정 source와 자격증명 존재 여부만
표시한다. 현재 분석에 `MarketIntegrationResult`가 있으면 이미 사용된
`SpotQuote.source`를 함께 표시한다. API key 값과 Stage 1 URL의 자격정보는 상태
계약에 포함하지 않는다.

`health=OK`, `forecast_fresh=true`, `provider fallback=false`여도 원본 forecast가
`partial_fallback_used=true` 또는 `research_only=true`이면 전체 Stage 1 readiness는
`DEGRADED`다. 이는 연결 실패가 아니라 모델 데이터·용도 제한을 숨기지 않는
표시다. 자세한 상태 계약은
[INTEGRATION_READINESS.md](INTEGRATION_READINESS.md)를 따른다.
