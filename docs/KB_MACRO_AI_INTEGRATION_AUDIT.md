# kb_macro_ai 최신 계약 통합 감사

> 감사 성격: 읽기 전용 원격 계약 감사 및 통합 설계
>
> 감사 시각: 2026-07-29 19:23 KST 시작
>
> KBaiAgent 실제 시작 브랜치: `feature/submission-benchmark-evidence`
>
> KBaiAgent 실제 시작 HEAD: `6eaeb8987233896d089245072d3578dc17307027`
>
> 사용자 제시 KBaiAgent 기준 HEAD: `35f7c128e81d65214f737246d9a79e81c2338211`
>
> kb_macro_ai 감사 SHA: `7d3efa41cdc8bbb8da61b6b0c6108bdf55713e3e`
>
> 원격 저장소: [saniolsida/kb_macro_ai](https://github.com/saniolsida/kb_macro_ai/tree/7d3efa41cdc8bbb8da61b6b0c6108bdf55713e3e)

## 1. 결론

`kb_macro_ai@7d3efa4`의 **환율 forecast 계약은 KBaiAgent가 이미
HTTP/file/mock provider로 소비할 수 있다**. 반면 이번에 추가된 헤지 조합 계약은
현재 다음 범위다.

- 단일 `usd_payable`, 즉 USD 지급 노출만 지원한다.
- 기업 입력은 설정에 고정된 JSON 파일 한 건이다.
- HTTP 서버는 생성된 forecast와 hedge JSON을 GET으로 읽어 주는 정적 서버다.
- 기업별 POST 요청, `usd_receivable`, 분할 지급·수취, 다중 거래 요청은 없다.
- 선물환·달러 콜옵션·무헤지의 10% 격자 후보를 결정론적으로 전수 계산해 목적함수
  최저 3개를 반환한다.
- 가격은 목업이고 출력은 연구·대회 프로토타입이다.
- 추적된 `latest_forecast.json`과 `latest_hedge_recommendation.json` 실행 산출물은
  원격 저장소에 없다. `web_runtime/output/` 자체가 `.gitignore:9` 대상이다.
- 헤지 전용 JSON Schema/Pydantic 모델과 구조화된 실패 응답은 없다.

따라서 전체 통합 판정은 **PARTIALLY_READY**다. 더 좁게 보면 다음과 같다.

> 2026-07-31 후속 구현: 위 감사에서 권장한 request-file/pinned CLI adapter가
> 추가됐다. 현재는 확정된 단일 USD 수입 지급 거래와 사용자가 확인한 제약조건을
> 임시 파일로 전달해 `kb_macro_ai@7d3efa4`의 공식 CLI를 실행하고, raw 결과를
> 삭제하기 전에 KBaiAgent가 다시 검증한다. 이는 POST API나 수출 지원이 생겼다는
> 뜻이 아니며 결과는 목업 가격 기반 `REFERENCE_ONLY`다.

| 대상 | 판정 | 이유 |
|---|---|---|
| KBaiAgent의 기존 Stage 1 forecast 연결 | READY | `krw_forecast_web_v1`과 GET `/api/forecast`를 이미 검증·정규화 |
| 단일 USD 수입 지급 건의 API-free 참고 결과 | READY_WITH_ADAPTER | 실제 파일 입력·결과 구조가 있으나 계약 검증 adapter와 고정 fixture가 필요 |
| 기업별 동적 HTTP 요청 | NOT_READY | POST/request body가 없음 |
| Golden USD 수출 수취 거래의 헤지 조합 | NOT_READY | `usd_receivable`을 런타임에서 명시적으로 거부 |
| 분할 지급·수취 또는 복수 거래 | NOT_READY | 단일 `amount_usd`와 단일 `payment_date`만 읽음 |
| 현재 Stage 3 교체 | NOT_READY / DO_NOT_BUILD | 의미·상품·목적함수·런타임 계약이 다르고 회귀 위험이 큼 |

제출 전 안전한 주장은 “`kb_macro_ai`의 USD/KRW forecast를 현재 앱이
계약 기반으로 소비한다”까지다. “수출입 모두에 외부 헤지 최적화가 연결됐다”,
“기업별 API로 실시간 헤지 추천을 받는다”는 현재 사실이 아니다.

## 2. 감사 무결성과 범위

### 2.1 KBaiAgent 시작 상태

사용자가 제시한 기준 HEAD와 실제 시작 HEAD가 달랐다. 임의 reset·checkout은 하지
않았다.

| 항목 | 실제 시작 상태 |
|---|---|
| branch | `feature/submission-benchmark-evidence` |
| HEAD | `6eaeb8987233896d089245072d3578dc17307027` |
| tracked/staged/unstaged 변경 | 없음 |
| 보호 대상 미추적 파일 | 3개 존재, 수정·추적하지 않음 |
| Golden PDF SHA-256 | `5330a1a572488005f7b02cccfc7150fbaa8b38c84bb9290da1e0c6e1c3a0a91c` |

보호 파일 시작 SHA-256:

| 파일 | SHA-256 |
|---|---|
| `PROJECT_DIRECTION.md` | `4739d0db7087cdd61e20f5c444114ba661f46972b655528bac5307bc042f8e63` |
| `docs/FEATURE_MAPPING.md` | `e0e6ae03a3d40614da8a739e6f641bcaaa0bd66a4f53808a0c71449986c33a08` |
| `docs/T4_COUNTRY_ENVIRONMENT_IMPLEMENTATION_PROMPT.md` | `40685eea8f4ee52fea69cb4229ead52edc29a76c66d34142eb93f988f571b0e9` |

### 2.2 원격 고정

감사용 shallow clone은 `/tmp/kb_macro_ai_integration_audit`에 만들었고 KBaiAgent
안에 vendor 또는 submodule로 추가하지 않았다.

| 항목 | 값 |
|---|---|
| origin | `https://github.com/saniolsida/kb_macro_ai.git` |
| branch | `main` |
| 원격/clone HEAD | `7d3efa41cdc8bbb8da61b6b0c6108bdf55713e3e` |
| commit date | `2026-07-29T17:20:35+09:00` |
| commit message | `add hedge json readme` |
| author | `songsan` |
| clone dirty 여부 | clean |

### 2.3 판정 우선순위

요청에 따라 충돌 시 실행 코드 → 테스트 → 실제 sample/output JSON → schema →
README 순으로 판정했다. 원격에 hedge 실행 output이 추적되어 있지 않으므로 그
부분은 실행 코드와 테스트가 우선 근거다.

## 3. 확인한 kb_macro_ai 파일

다음 파일의 존재와 내용을 확인했다.

| 영역 | 확인 파일 |
|---|---|
| 계약 설명 | `HEDGE_JSON_README.md`, `JSON_README.md`, `README.md`, `project.md` |
| 기업 입력 | `examples/mock_company_exposure.json` |
| 실행 설정 | `configs/hedge_recommendation_v1.json`, `configs/web_forecast_v1.json` |
| forecast 구현 | `src/krw_forecast/web_forecast_v1.py`, `web_forecast_v1_cli.py` |
| hedge 구현 | `src/krw_forecast/hedge_recommendation_v1.py`, `hedge_recommendation_v1_cli.py` |
| API | `src/krw_forecast/web_forecast_server_v1.py` |
| 테스트 | `tests/test_web_forecast_v1.py`, `tests/test_hedge_recommendation_v1.py` |
| 실행 script | `scripts/run_web_forecast.sh`, `run_web_forecast_offline.sh`, `run_hedge_recommendation.sh`, `run_web_report_pipeline.sh`, `serve_web_forecast.sh` |
| runtime | `pyproject.toml`, `web_runtime/bundle_v1/*` |
| forecast artifact | `artifacts/multiscale_gkg_excursion_v34/interface_forecast_v34.json` 등 |

존재하지 않거나 추적되지 않은 항목:

- `web_runtime/output/latest_forecast.json`
- `web_runtime/output/latest_hedge_recommendation.json`
- hedge request/response JSON Schema
- hedge Pydantic/domain model
- requirements/lock 파일
- API route 통합 테스트
- 전체 hedge pipeline 통합 테스트

`pyproject.toml:9`는 Python `>=3.11`을 선언하지만 NumPy, Pandas, scikit-learn,
joblib 같은 runtime dependency를 `[project.dependencies]`에 선언하지 않는다.
따라서 clean clone 하나만으로 실행 환경을 재현할 수 없다.

## 4. 실제 지원 exposure

### 4.1 판정표

| 항목 | 실제 지원 | 판정 근거 |
|---|---|---|
| exposure type | `usd_payable`만 | `HEDGE_JSON_README.md:24`, `hedge_recommendation_v1.py:520-521` |
| `usd_receivable` | 미지원 | 다른 값은 `ValueError` |
| 통화 | USD 노출 / USD-KRW 가격만 | `amount_usd`, `usdkrw_spot`, USD call option 고정 |
| 방향 | 수입 지급 의미만 | call option 비용식과 `usd_payable` hard gate |
| 분할 지급 | 미지원 | 단일 `amount_usd`, `payment_date` |
| 분할 수취 | 미지원 | receivable 자체 미지원 |
| 복수 거래 | 미지원 | config의 단일 `company_input_path` 한 건 |
| 기존 보유 USD | 지원 | `existing_usd_cash`, 순노출에서 차감 |
| 기존 선물환 | 지원 | `existing_forward_usd`, 순노출에서 차감 |
| 동일통화 자연상계 흐름 | 미지원 | 관련 입력·계산 필드 없음 |

코드는 순노출을 다음처럼 0 이상으로 제한한다
(`hedge_recommendation_v1.py:279-284`).

```text
net_exposure_usd
= max(amount_usd - existing_usd_cash - existing_forward_usd, 0)
```

그러나 공개 추천의 상품별 notional은 같은 차감식에 `max(..., 0)`을 적용하지 않는다
(`hedge_recommendation_v1.py:455-479`). 보유 USD와 기존 선물환 합이 gross 노출보다
크면 계산용 순노출은 0이지만 출력 notional이 음수가 될 수 있다. 현재 테스트는 이
경계를 다루지 않는다. 외부 결과 adapter는 **모든 notional이 0 이상인지 반드시
재검증**해야 하고, 원격 코드가 수정되기 전에는 해당 입력을
`VALIDATION_FAILED`로 처리해야 한다.

## 5. 실제 기업 입력 방식

### 5.1 실행 경로

현재 입력은 POST body가 아니다.

1. `configs/hedge_recommendation_v1.json:5`의 `company_input_path`가
   `examples/mock_company_exposure.json`을 가리킨다.
2. CLI는 `--config`만 받는다
   (`hedge_recommendation_v1_cli.py:9-22`).
3. engine이 config, forecast, company JSON, market history를 파일에서 읽는다
   (`hedge_recommendation_v1.py:509-519`).
4. 생성된 결과 파일을 별도 GET 서버가 읽어 준다.

따라서 “기업별 요청을 API로 전달”하는 계약은 없다. 여러 클라이언트가 정적 GET을
동시에 읽는 것과 여러 기업 계산을 동시에 요청하는 것은 다른 기능이다.

### 5.2 필드 의미와 강제 수준

JSON Schema가 없으므로 아래 required 판정은 코드의 direct indexing 여부를
기준으로 했다.

| field | 코드상 required | 실제 의미 | 검증/누락 동작 |
|---|---:|---|---|
| `company_id` | 아니오 | sample 식별자, 결과 pass-through | 별도 검증 없음 |
| `company_name` | 아니오 | sample 표시명, 결과 pass-through | 별도 검증 없음 |
| `exposure_id` | 아니오 | sample 노출 식별자 | 별도 검증 없음 |
| `exposure_type` | 예 | 지원 노출 방향 | `usd_payable` 아니면 `ValueError` |
| `amount_usd` | 예 | gross USD 지급액 | `float()`만 사용, 양수·유한성 schema 검증 없음 |
| `payment_date` | 예 | 단일 지급 예정일 | `np.busday_count`가 해석, 명시적 ISO validator 없음 |
| `payment_certainty` | 예 | 선물환 비율 상한 | 0~1 명시 검증 없음 |
| `budget_exchange_rate` | 아니오 | sample 예산환율처럼 보임 | 실행 코드에서 사용하지 않음 |
| `maximum_acceptable_cost_krw` | 예 | 총 원화 지급비용 초과확률의 임계금액 | `acceptable_fx_loss`와 다른 의미 |
| `maximum_budget_exceedance_probability` | 예 | 허용 초과확률, 목적함수 penalty 기준 | 0~1 명시 검증 없음 |
| `risk_tolerance` | 예 | `low/medium/high`의 위험회피계수 선택 | 다른 값은 config key 오류 |
| `existing_usd_cash` | 아니오 | 지급에 사용할 기존 USD | 누락 시 0 |
| `existing_forward_usd` | 아니오 | 기존 선물환 USD | 누락 시 0 |
| `maximum_total_hedge_ratio` | 예 | 신규 선물환+옵션 비율 상한 | 범위 schema 검증 없음 |
| `option_premium_budget_krw` | 예 | 옵션 프리미엄 한도 | 비음수 schema 검증 없음 |
| `allowed_instruments` | 예 | `forward`, `vanilla_usd_call` 허용 집합 | unknown 값 자체를 거부하지 않음 |
| `mock_hedge_quotes` | 예 | 목업 선물환 point·콜옵션 견적 | 실제 quote 검증 없음 |
| `prototype_notice` | 아니오 | sample 고지 | 입력값은 사용하지 않고 출력 고지를 코드가 새로 생성 |

누락·type 오류는 `KeyError`, `ValueError` 등으로 CLI가 실패한다. API용
`400` validation response나 `failed_fields` 구조는 없다.

## 6. forecast JSON 계약

실행 코드가 만드는 forecast의 버전은 `krw_forecast_web_v1`이다
(`configs/web_forecast_v1.json:2`, `web_forecast_v1.py:1398-1471`).

주요 블록:

- `generated_at`, `prediction_date`
- `horizon.trading_days`
- `market_snapshot.currency_pair`, `usdkrw_spot`, `as_of_date`, `unit`
- v25 종착 방향 score
- v36 최대 상승폭 q10/q50/q75/q90
- v34 최대 하락폭 q10/q50/q75/q90
- `decision_basis`
- 설명 전용 `news_market_context`
- `data_quality`

원격의 tracked `artifacts/*forecast*.json`은 연구 artifact이며
`krw_forecast_web_v1` runtime output과 같은 schema가 아니다. 예를 들어
`artifacts/multiscale_gkg_excursion_v34/interface_forecast_v34.json`은
`version=multiscale_gkg_excursion_v34`다. `JSON_README.md`에 runtime output 예시는
있지만 실제 `web_runtime/output/latest_forecast.json`은 추적되어 있지 않다.

KBaiAgent에는 별도로 고정한
`src/integration_assets/stage1/latest_forecast.json`이 있고,
`schema_version=krw_forecast_web_v1`, prediction date `2026-07-27`, horizon
21거래일이다. SHA-256은
`97b81476690f23b43e4f7ddc2a926b392ec3bdc4f94d4c2cae0e743b76218b4f`다.

## 7. hedge JSON 계약

### 7.1 버전과 결과

버전은 `krw_hedge_recommendation_v1`이다
(`configs/hedge_recommendation_v1.json:2`).

실행 성공 시 주요 블록은 다음과 같다
(`hedge_recommendation_v1.py:657-817`).

| 블록 | 내용 |
|---|---|
| `forecast_json_reference` | forecast path, schema, prediction date, horizon |
| `company_exposure` | mock quote를 제외한 입력 pass-through |
| `horizon_alignment` | payment까지 영업일, 21일과 차이, ±3일 여부 |
| `exposure_calculation` | gross, USD cash, 기존 선물환, net |
| `pricing_snapshot` | spot, 선물환율, 옵션 quote, `quotes_are_mock=true` |
| `ai_conditioned_exchange_rate_paths` | 역사 경로와 forecast 조건화 검증 |
| `recommended_hedge_combinations` | 목적함수 최저 3개 |
| `mathematical_formulas` | 비용·VaR·CVaR·목적함수 |
| `verification` | 전수조사·제약·역사 경로 stress |
| `news_context_reference` | 설명 전용 뉴스 |
| `prototype_notice` | 목업·비권고 고지 |

각 추천에는 rank, 선물환·옵션·무헤지 비율, 상품별 notional,
`expected_cost_krw`, `var_95_cost_krw`, `cvar_95_cost_krw`,
`q99_cost_krw`, `maximum_cost_krw`, 예산초과확률, 목적함수 구성,
결정론 문장형 이유가 들어간다
(`hedge_recommendation_v1.py:46-73`, `383-480`).

### 7.2 추천 순서

후보는 10% 격자로 생성된다
(`configs/hedge_recommendation_v1.json:11`,
`hedge_recommendation_v1.py:268-340`). 모든 feasible 후보의 score를 계산한 뒤
오름차순 정렬하고 앞의 3개를 선택한다
(`hedge_recommendation_v1.py:577-592`).

목적함수는 다음 합이다.

```text
expected cost
+ risk-aversion × (CVaR95 - expected cost)
+ budget-exceedance penalty
```

이 순위는 다음과 완전히 별개다.

1. KBaiAgent 상담 Top 3
2. KBaiAgent 현재 Stage 3의 안정성·균형·비용 비교 후보
3. KBaiAgent 공식 상담 후보 global shortlist

외부 hedge rank를 상담 rank나 상품 후보 score로 변환하면 안 된다.

## 8. 실제 API 계약

`web_forecast_server_v1.py:23-81`이 구현한 route는 다음뿐이다.

| endpoint | method | 성공 | 실패 |
|---|---|---|---|
| `/` | GET | 200, endpoint 목록 | 해당 없음 |
| `/api/forecast` | GET | 200, 파일 JSON | 파일 없음: 503 `forecast_not_generated` |
| `/api/hedge-recommendation` | GET | 200, 파일 JSON | 파일 없음: 503 `hedge_recommendation_not_generated` |
| `/health` | GET | 200, 두 파일 availability | 파일이 없어도 HTTP status와 `status`는 `ok` |
| 그 외 | GET | 해당 없음 | 404 `not_found` |

명시적으로 없는 것:

- POST endpoint
- request body
- 기업별 계산 trigger
- 입력 validation error 400
- 인증/권한
- version negotiation
- response JSON Schema 검증
- server-side timeout
- OPTIONS handler

서버는 `ThreadingHTTPServer`, 기본 `127.0.0.1:8765`이며
`Access-Control-Allow-Origin: *`를 반환한다
(`web_forecast_server_v1.py:5`, `18`, `89-119`). 로컬 프로토타입에는 쓸 수
있지만 공개 배포 계약은 아니다.

## 9. 검증 규칙 감사

| 검증 항목 | 실행 코드 | 테스트 | 판정 |
|---|---|---|---|
| forecast schema version 일치 | 출력에 복사만 함 | 없음 | FAIL |
| hedge schema version | config 값을 출력 | 없음 | PARTIAL |
| prediction date 일치 | 같은 forecast에서 reference 생성 | 두 파일 소비자 검증 없음 | PARTIAL |
| forecast horizon=21 | config와 다르면 `ValueError` | full pipeline 없음 | PASS_BY_CODE |
| payment horizon ±3일 | boolean과 warning만 생성 | 없음 | WARNING, fail-closed 아님 |
| 추천 3개 | feasible 3개 미만이면 실패, 성공 시 top 3 | full pipeline 없음 | PASS_BY_CODE |
| 후보 전수조사 | finite grid loop | 없음 | PASS_BY_CODE |
| 목적함수 오름차순 | 정렬 후 top 3 | 없음 | PASS_BY_CODE |
| ratio 합 100% | 생성식·certificate | 후보 test 일부 | PASS |
| 총 hedge ratio 상한 | 생성 시 제한·certificate | 후보 test 일부 | PASS |
| 옵션 premium 예산 | 생성 시 필터·certificate | 후보 test | PASS |
| 기존 노출 초과 방지 | net은 0 floor | negative notional 미검증 | PARTIAL |
| 목업 quote 표시 | `quotes_are_mock=true`, prototype notice | 없음 | PASS_BY_CODE |
| unsupported exposure | `ValueError` | 없음 | PASS_BY_CODE |
| missing value fail-closed | 예외로 중단 | 구조화 실패상태 없음 | PARTIAL |

특히 `HEDGE_JSON_README.md:209-249`는 후속 report consumer가 두 JSON을 검증하고
실패 시 `validation_failed`를 반환해야 한다고 설명한다. 이 report consumer는
현재 실행 코드나 API에 없다. 문서의 “필수 검증”을 hedge engine 자체의
fail-closed 구현으로 해석하면 안 된다.

또한 payment date가 21거래일 horizon에서 3일 넘게 벗어나도 engine은 추천을
계속 생성한다 (`hedge_recommendation_v1.py:671-686`). KBaiAgent adapter는 이 값을
받으면 `REFERENCE_ONLY`로 낮추거나 `VALIDATION_FAILED`로 차단해야 한다.

## 10. 테스트와 재현성

### 10.1 원격 테스트의 실제 범위

`tests/test_hedge_recommendation_v1.py`의 hedge 관련 테스트는 4개다.

1. weighted quantile
2. forecast 조건화 방향 확률
3. 후보의 hedge ratio·premium 제약
4. USD call payable 비용식

다음은 테스트되지 않는다.

- full forecast → hedge pipeline
- 정확히 3개 및 objective 정렬
- output schema 전체
- unsupported receivable
- horizon ±3일 경계
- forecast/hedge date 교차 검증
- API route/status
- missing/malformed input
- 음수 notional 경계
- atomic output write

### 10.2 이번 감사에서 실행한 범위

- Python 3.11 `compileall`로 `src`, `tests` 문법 컴파일: PASS
- 원격 hedge/web 집중 unittest: **미실행이 아니라 실행 실패**
  - Python 3.11 환경에 NumPy/Pandas가 없어 import error
  - 저장소 `pyproject.toml`에 runtime dependency 선언이 없음
- offline forecast/hedge 산출물 재생성: 미실행
  - 같은 dependency blocker
  - 외부 API는 호출하지 않음

따라서 이번 문서에서 원격 테스트를 PASS라고 주장하지 않는다. 원격 clone에
dependency lock 또는 설치 가능한 manifest가 추가되어야 clean-room 재현이 가능하다.

## 11. 모델과 결정론의 역할

정확한 역할은 다음과 같다.

- v25 방향 score와 v34/v36 경로 분위수가 과거 경로의 가중치를 바꾼다
  (`hedge_recommendation_v1.py:111-215`).
- 이 가중치가 expected cost, VaR, CVaR, 예산초과확률과 목적함수에 영향을 주므로
  모델 forecast는 **간접적으로 추천 순서에 영향을 준다**.
- 실제 후보 비율은 LLM이 생성하지 않는다. 정해진 10% 격자와 제약을 결정론 코드가
  전수조사한다.
- 뉴스는 숫자 입력으로 쓰지 않고 비율도 바꾸지 않는다
  (`hedge_recommendation_v1.py:797-812`).
- `recommended_reason`도 LLM 문장이 아니라 결정론 template이다
  (`hedge_recommendation_v1.py:343-380`).

주의할 표현이 하나 있다. reason template은 미보정 v25 값을
“상승확률”이라고 부른다 (`hedge_recommendation_v1.py:356-364`). 같은 저장소
문서는 그 값이 미보정이라고 명시한다. KBaiAgent가 표시한다면 현재 Stage 1 정책처럼
“방향 score/시장 문맥”으로 낮춰 표현해야 한다.

## 12. KBaiAgent 현재 계약

### 12.1 Stage 1

- GET `/api/forecast`, file, mock provider가 있다
  (`src/stage1/forecast_provider.py:181-239`, `277-437`).
- `krw_forecast_web_v1` schema, 날짜, score 합, quantile 순서, 뉴스 비수치 사용,
  research/stale/fallback을 검증한다
  (`src/stage1/web_forecast.py:349-553`).
- 별도 spot source와 결합해 Decimal 문자열 absolute scenario를 만든다.
- HTTP 실패는 file/mock fallback으로 공개한다.

즉 forecast 연결은 이미 완료되어 있고 hedge 결과를 읽는 route만 없다.

### 12.2 Stage 2

- 수입·수출을 모두 지원한다.
- 여러 `ExposureInput`으로 분할 회차를 표현한다
  (`src/domain/stage2_models.py:28-75`).
- 수입 보유외화, 같은 통화 자연상계, 기존 헤지를 구분한다
  (`src/stage2/exposure.py:27-104`).
- 계약상 예정 결제 노출, open exposure, 현금흐름·버퍼·신용 후 부족을
  `Decimal`로 계산한다.

### 12.3 현재 Stage 3

현재 Stage 3은 선물환·분할환전·무헤지 조합을 5% 또는 10% 격자로 탐색하고,
`STABILITY_FIRST`, `BALANCED`, `COST_FIRST` 비교안을 최대 3개 만든다
(`src/stage3/optimizer.py:166-547`,
`src/domain/stage3_models.py:24-72`).

외부 engine과 다른 점:

| KBaiAgent 현재 Stage 3 | kb_macro_ai hedge v1 |
|---|---|
| 수입·수출 모두 | `usd_payable`만 |
| Decimal | float 후 JSON 3자리 반올림 |
| 선물환·분할환전·무헤지 | 선물환·USD call·무헤지 |
| Stage 2 현금·버퍼·손실 제약 | 지급비용·CVaR·초과확률 목적함수 |
| 앱의 내부 가정 계약 | 외부 목업 quote |
| profile 3종 | 단일 목적함수 최저 3개 |

이 차이 때문에 외부 response를 현재 `Stage3Result`로 단순 cast하거나 Stage 3를
교체하면 안 된다.

### 12.4 상담·공식 후보·Stage 5

- 상담 Top 3는 `ConsultationPacket.consultation_priorities`, 최대 3개다
  (`src/domain/consultation_models.py:136-159`, `246-250`).
- 공식 후보는 global shortlist 하나이며 최대 3개다
  (`src/domain/product_models.py:55-70`).
- shortlist의 product score는 상담 priority를 바꾸지 않는다
  (`src/application/official_candidate_service.py:167-278`).
- Stage 5는 현재 `Stage3Result`, ConsultationPacket, Stage 4를 근거 bundle로
  사용하고 critic 실패 시 결정론 보고서로 fallback한다.
- Streamlit은 Stage 3 비교, 상담 Top 3, 공식 후보를 별도 영역으로 표시한다.

외부 hedge Top 3를 연결하더라도 세 기존 순위와 이름·source path를 분리해야 한다.

### 12.5 데모 증거

- Golden은 KR 판매자 → BR 구매자, USD 100,000 예정 수취의 `EXPORT`다.
- `tests/golden_consultation_fixture.py:35-155`가 confirmation, Stage 1 stress,
  Stage 2, 거래위험, 국가환경, ConsultationPacket을 API-free로 구성한다.
- `tests/test_golden_trade_demo.py:174-352`가 USD 100,000, 분할
  20,000/80,000, -5% 손실 7,000,000원, buffer shortfall 2,000,000원,
  post-credit shortfall 0원을 검증한다.
- 기존 수입·수출 양방향 fixture는
  `src/application/demo_service.py:337-523`와
  `tests/test_integrated_decision_demo.py`에 있다.

Golden 수출에 외부 hedge를 적용할 수 없다는 판정은 Golden의 부족이 아니라 외부
v1의 `usd_receivable` 미지원 때문이다.

## 13. 통합 적합성 상세 판정

| 질문 | 판정 | 근거 |
|---|---|---|
| Golden 수출에 직접 적용 가능한가 | NOT_READY | receivable 미지원 |
| 단일 USD 수입 지급에 적용 가능한가 | READY_WITH_ADAPTER | payable 지원, 단 사용자 제약·목업 quote·검증 필요 |
| `usd_receivable`이 실제 존재하는가 | NOT_READY | runtime hard reject |
| API로 기업별 요청을 전달할 수 있는가 | NOT_READY | GET static output뿐 |
| request-file/CLI adapter가 필요한가 | READY_WITH_ADAPTER | 현재 현실적인 연결 방식 |
| forecast와 hedge JSON을 함께 읽어야 하는가 | READY | 날짜·기간·reference·검증 교차 확인에 둘 다 필요 |
| KBaiAgent Stage 3를 교체해야 하는가 | DO_NOT_BUILD | 계산 의미·coverage·fallback이 다름 |
| 선택적 provider로 추가 가능한가 | READY_WITH_ADAPTER | feature flag 기본 off, 별도 DTO가 전제 |
| 검증 실패 시 기존 Stage 3 fallback 가능한가 | READY_WITH_ADAPTER | 기존 Stage 3가 독립되어 있으나 external adapter가 아직 없음 |
| API-free fixture 통합 테스트 가능한가 | PARTIALLY_READY | forecast fixture는 있으나 고정 hedge output이 원격에 없음 |

## 14. 권장 통합 경계

### 14.1 현재 바로 가능한 연결

- KBaiAgent의 기존 Stage 1 provider로 forecast GET/file/mock 소비
- 고정 SHA의 forecast JSON을 현재 validator로 검증
- 외부 저장소를 별도 Python 3.11 프로세스로 유지

### 14.2 adapter가 있으면 가능한 연결

초기 범위는 **단일 USD 수입 지급, reference-only**로 제한한다.

```text
KBaiAgent confirmed single IMPORT/USD exposure
  ├─ confirmed amount/date
  ├─ existing USD cash/forward
  └─ explicit user constraints
          │
          ▼
versioned request-file writer
          │
          ▼
kb_macro_ai pinned CLI @ exact SHA
  ├─ forecast JSON
  └─ hedge JSON
          │
          ▼
KBaiAgent read-only response validator
  ├─ cross-file schema/date/horizon
  ├─ input echo/net exposure
  ├─ rank/objective/ratio/notional
  ├─ certificate/mock/prototype boundary
  └─ status = READY or REFERENCE_ONLY
          │
          ├─ valid: 별도 “외부 헤지 조합 참고 결과”
          └─ invalid/unavailable: 기존 Stage 3 + 공개된 fallback
```

adapter는 다음을 지켜야 한다.

1. Stage 2를 다시 계산하거나 외부 float를 Stage 2에 역주입하지 않는다.
2. 외부 결과는 전용 DTO에 보존한다.
3. 금액은 `Decimal(str(value))`로 재검증하되 외부 계산이 float였다는 사실을 숨기지
   않는다.
4. source commit, raw file SHA, request hash, forecast/hedge schema와 prediction date를
   trace에 남긴다.
5. validation이 하나라도 실패하면 외부 Top 3를 게시하지 않는다.
6. 기존 Stage 3를 기본 provider로 유지하고 feature flag 기본값은 off다.

### 14.3 kb_macro_ai 변경이 필요한 연결

- `usd_receivable`
- 복수 installment/transaction request
- POST 기업별 계산 endpoint
- request/response JSON Schema
- typed 4xx validation errors
- dependency manifest/lock
- payment horizon fail-closed 또는 명시적 reference status
- 음수/초과 notional 방지
- 실제 quote provider와 quote timestamp/provenance
- atomic output write

### 14.4 제출 후 확장

- 인증된 서비스 배포
- idempotency/concurrency 계약
- 실제 은행 quote
- 회계·세무·실거래 처리
- ConsultationPacket과 Stage 5의 외부 결과 전용 section
- USD 이외 통화

## 15. 요청 계약 초안

### 15.1 현재 원격 input과 제안 계약의 차이

아래는 **제안 계약**이다. 원격 engine은 아직 이 envelope를 받지 않는다. 초기
request-file adapter가 `company_exposure`를 현재 flat JSON으로 풀어 써야 한다.

```json
{
  "schema_version": "kbaiagent_kb_macro_hedge_request_v0",
  "request_id": "opaque-id",
  "provider_commit_sha": "7d3efa41cdc8bbb8da61b6b0c6108bdf55713e3e",
  "source_trade_sha256": "64-lowercase-hex",
  "forecast_reference": {
    "schema_version": "krw_forecast_web_v1",
    "sha256": "64-lowercase-hex"
  },
  "company_exposure": {
    "exposure_type": "usd_payable",
    "amount_usd": "100000.00",
    "payment_date": "2026-08-27",
    "payment_certainty": null,
    "maximum_acceptable_cost_krw": null,
    "maximum_budget_exceedance_probability": null,
    "risk_tolerance": null,
    "existing_usd_cash": "10000.00",
    "existing_forward_usd": "0.00",
    "maximum_total_hedge_ratio": null,
    "option_premium_budget_krw": null,
    "allowed_instruments": [],
    "mock_hedge_quotes": null
  }
}
```

`null`은 임의 default를 쓰라는 뜻이 아니라 **사용자 입력 또는 upstream 견적이
필요하므로 실행을 차단**한다는 뜻이다.

### 15.2 필드별 producer와 missing 동작

| field | type | required | producer/source | validation | missing behavior | 금융 의미 |
|---|---|---:|---|---|---|---|
| `schema_version` | string | 예 | adapter constant | exact allowlist | 차단 | 통합 envelope 버전 |
| `request_id` | string | 예 | KBaiAgent | opaque/non-empty | 차단 | 요청 상관관계 |
| `provider_commit_sha` | SHA-1 | 예 | 배포 설정 | exact pin | 차단 | 재현 가능한 외부 코드 |
| `source_trade_sha256` | SHA-256 | 예 | confirmed trade | 64 hex | 차단 | 확인된 거래 binding |
| `forecast_reference.schema_version` | string | 예 | Stage 1 | `krw_forecast_web_v1` | 차단 | forecast 계약 |
| `forecast_reference.sha256` | SHA-256 | 예 | adapter | 파일 bytes | 차단 | forecast 불변성 |
| `exposure_type` | enum | 예 | trade direction mapping | 현재 `IMPORT`→`usd_payable`만 | `UNSUPPORTED_EXPOSURE` | 지급/수취 방향 |
| `amount_usd` | decimal string | 예 | `Stage2Input.exposures[i].foreign_amount` | >0, USD, 단일 회차 | 차단 | gross 예정 지급액 |
| `payment_date` | date | 예 | `ExposureInput.settlement_date` | ISO, horizon | reference/차단 | 예정 지급일 |
| `payment_certainty` | decimal | 예 | 사용자 | 0~1 | missing information | 선물환 비율 상한 |
| `maximum_acceptable_cost_krw` | decimal string | 예 | 사용자 | >0 | missing information | 총 지급비용 threshold |
| `maximum_budget_exceedance_probability` | decimal | 예 | 사용자 | 0~1 | missing information | 허용 threshold 초과확률 |
| `risk_tolerance` | enum | 예 | 사용자 | low/medium/high | missing information | 목적함수 위험회피계수 |
| `existing_usd_cash` | decimal string | 예 | import exposure allocation | 0~gross | 확인 없으면 UNKNOWN | 지급에 실제 사용할 USD |
| `existing_forward_usd` | decimal string | 예 | existing hedge amount | 0~gross | 확인 없으면 UNKNOWN | 기존 선물환 notional |
| `maximum_total_hedge_ratio` | decimal | 예 | 사용자/정책 | 0~1 | missing information | 신규 forward+option 상한 |
| `option_premium_budget_krw` | decimal string | 예 | 사용자 | ≥0 | missing information | premium 현금 예산 |
| `allowed_instruments` | enum array | 예 | 사용자+상품 가용성 확인 | known values only | missing information | 비교 허용 수단 |
| `mock_hedge_quotes` | object | 예(v1) | kb_macro_ai fixture/향후 quote provider | quote timestamp·nonnegative | 차단 | 목업 가격 입력 |

중요한 비매핑:

- KBaiAgent `acceptable_fx_loss`를
  `maximum_acceptable_cost_krw`로 바꾸지 않는다. 전자는 기준 대비 허용손실,
  후자는 총 원화 지급비용 threshold다.
- KBaiAgent `risk_aversion_weight`를 `risk_tolerance`로 자동 변환하지 않는다.
- `maximum_forward_ratio`를 옵션까지 포함하는
  `maximum_total_hedge_ratio`로 자동 변환하지 않는다.
- 같은 통화 자연상계가 있으면 외부 v1 순노출과 KBaiAgent open exposure가 달라질 수
  있으므로 자동 합산하지 않고 unsupported/reference-only로 처리한다.

## 16. 응답 계약 초안

이 역시 **KBaiAgent adapter의 제안 wrapper**다. 원격 raw hedge JSON에는
`status`가 없다.

```json
{
  "schema_version": "kbaiagent_kb_macro_hedge_response_v0",
  "status": "REFERENCE_ONLY",
  "provider_commit_sha": "7d3efa41cdc8bbb8da61b6b0c6108bdf55713e3e",
  "request_sha256": "64-lowercase-hex",
  "forecast_sha256": "64-lowercase-hex",
  "hedge_sha256": "64-lowercase-hex",
  "forecast_schema_version": "krw_forecast_web_v1",
  "hedge_schema_version": "krw_hedge_recommendation_v1",
  "validation": {
    "passed": true,
    "checks": [],
    "warnings": ["MOCK_QUOTES", "PROTOTYPE_ONLY"]
  },
  "raw_result_reference": {
    "recommendation_count": 3,
    "ranks": [1, 2, 3]
  }
}
```

제안 status:

| status | 의미 |
|---|---|
| `READY` | 모든 계약·입력·horizon·notional·certificate 검증 통과. 그래도 가입·실행 권고는 아님 |
| `REFERENCE_ONLY` | 목업 quote, horizon warning 또는 prototype 경계 때문에 비교 참고만 가능 |
| `VALIDATION_FAILED` | schema/date/rank/ratio/notional/certificate 중 하나 이상 실패, 추천 미게시 |
| `UNSUPPORTED_EXPOSURE` | receivable, 비USD, 다중/분할 등 v1 범위 밖 |
| `UPSTREAM_UNAVAILABLE` | 파일/CLI/GET 서비스 없음·timeout·invalid JSON |

필수 response 검증:

- forecast/hedge schema exact match
- 두 JSON prediction date와 horizon match
- request amount/date/existing cash/forward와 response echo match
- external net exposure와 KB Stage 2 open exposure match
- `within_three_trading_days=true`
- 추천 정확히 3개, rank 1/2/3, 중복 없음
- objective score 오름차순
- 각 ratio 0~1, 합 1
- 각 notional 0 이상이고 net exposure를 초과하지 않음
- certificate booleans true
- `quotes_are_mock=true`이면 최소 `REFERENCE_ONLY`
- prototype notice 존재
- 알려진 instrument만 존재

## 17. fallback 정책

권장 정책은 “외부 결과가 없으면 억지로 변환”이 아니다.

| 상황 | 외부 결과 | KBaiAgent 동작 |
|---|---|---|
| feature flag off | 사용 안 함 | 기존 Stage 3 |
| payable + 모든 검증 통과 | 별도 reference section | 기존 Stage 3도 보존 |
| mock quote | `REFERENCE_ONLY` | 실제 가격/최적/승인 표현 금지 |
| receivable/분할/비USD | `UNSUPPORTED_EXPOSURE` | 기존 Stage 3 |
| schema/date/horizon/certificate 실패 | `VALIDATION_FAILED` | 외부 Top 3 미표시, 기존 Stage 3 |
| 파일/API unavailable | `UPSTREAM_UNAVAILABLE` | 공개된 fallback warning + 기존 Stage 3 |

기존 Stage 3를 외부 provider의 파싱 실패 때문에 지우지 않는다. 단, 외부 결과를
선택한 것처럼 보이게 하면서 내부 결과로 조용히 대체해서도 안 된다. provider와
fallback을 UI·trace·Stage 5에 명시해야 한다.

## 18. P0/P1/P2/DO_NOT_BUILD

| 우선순위 | 작업 | 이유 | 담당 |
|---|---|---|---|
| P0 | exact commit SHA와 두 raw JSON SHA 고정 | 재현성과 schema drift 차단 | 양 팀 |
| P0 | forecast+hedge API-free sample fixture를 검토 후 제공 | 현재 hedge output이 추적되어 있지 않음 | kb_macro_ai |
| P0 | versioned request/response schema와 field semantics 합의 | flat sample만으로 missing/error 계약이 불명확 | 양 팀 |
| P0 | adapter 검증 목록 구현 전 음수 notional·horizon 경계 해결 | 잘못된 notional 또는 기간 결과 게시 방지 | kb_macro_ai + KBaiAgent |
| P1 | payable-only read-only provider, feature flag 기본 off | 현재 가능한 최소 vertical integration | KBaiAgent |
| P1 | 원격 full pipeline·API route·unsupported input tests | 문서상 검증과 실행 보장 간 gap 축소 | kb_macro_ai |
| P1 | POST endpoint + typed 4xx/5xx contract | 기업별 동적 요청에 필요 | kb_macro_ai |
| P1 | 외부 Top 3 전용 비교 UI | 기존 Stage 3·상담·상품 순위와 분리 | KBaiAgent |
| P2 | ConsultationPacket/Stage 5에 외부 결과 전용 section | source-of-truth 합의와 UX 검증 후 | KBaiAgent |
| P2 | `usd_receivable`과 수출 옵션/선물환 의미 구현 | Golden 적용의 선행조건 | kb_macro_ai |
| P2 | 분할·복수 거래 batch/idempotency | 운영 규모 확장 | kb_macro_ai |
| P2 | dependency lock, container/서비스 운영 계약 | clean-room·배포 재현성 | kb_macro_ai |
| DO_NOT_BUILD | 현재 Stage 3 즉시 교체 | 수출 coverage·Decimal·현금 제약 회귀 |
| DO_NOT_BUILD | Golden export에 payable 결과 주입 | 방향과 상품 payoff가 금융적으로 반대 |
| DO_NOT_BUILD | 세 Top 3 순위를 하나로 합산 | 서로 다른 의사결정 단위 |
| DO_NOT_BUILD | 실제 은행 견적·실거래·회계 처리처럼 표현 | 현재 quote와 결과는 목업 |
| DO_NOT_BUILD | model binary/vendor/submodule 복사 | 저장소 경계와 재현성 악화 |

## 19. 양 팀 역할 분담

### kb_macro_ai

- forecast와 hedge raw contract, 정확한 schema version 유지
- 지원 exposure와 payoff 의미 명시
- fixture quote provenance와 prototype 고지
- 입력 validation, 후보 전수조사, certificate
- 실행 가능한 dependency manifest와 API-free output fixture
- 향후 POST/receivable/multi-exposure 계약

### KBaiAgent

- 문서 추출·evidence·사용자 확인
- 거래 방향·USD 지급 노출·결제일 확정
- 제약조건을 임의 default 없이 사용자에게 수집
- request hash와 provider commit 고정
- 두 response의 schema/date/horizon/certificate 재검증
- 외부 결과를 별도 reference DTO/UI로 표시
- ConsultationPacket·Stage 5에 연결할 때 source path와 한계 유지
- 실패 시 기존 Stage 3 fallback과 provider 상태 공개

### 공동 승인 항목

- `amount_usd`가 gross인지 open인지
- 기존 cash/forward/같은 통화 자연상계 처리 순서
- payment certainty의 정의와 확인 주체
- 비용 threshold와 손실 threshold의 구분
- risk tolerance와 최대 hedge ratio의 사용자 언어
- mock/actual quote 상태
- horizon mismatch 처리
- response status와 backward compatibility 기간

## 20. 다음 구현 단계

통합 코드는 이 감사에서 구현하지 않았다. 다음 별도 작업의 최소 순서는 다음이다.

1. kb_macro_ai 팀이 exact SHA에서 offline forecast와 hedge output을 생성하고 hash와
   함께 전달한다.
2. 양 팀이 제안 request/response field semantics를 승인한다.
3. KBaiAgent에 순수 read-only validator를 먼저 구현한다.
4. payable 단일 fixture만으로 API-free contract test를 추가한다.
5. feature flag 기본 off로 별도 reference section을 연결한다.
6. invalid/unavailable/unsupported 시 기존 Stage 3 fallback을 검증한다.
7. 그 후에만 UI·ConsultationPacket·Stage 5 연결 범위를 승인한다.

## 21. 공식 한계와 금지 주장

사용 가능한 표현:

- “USD/KRW forecast JSON/REST adapter가 연결되어 있다.”
- “외부 prototype은 단일 USD 지급 노출에서 목업 견적 기반 헤지 조합 3개를
  결정론적으로 전수 비교한다.”
- “뉴스는 설명용이며 hedge ratio를 직접 바꾸지 않는다.”
- “외부 hedge 통합은 exact SHA 계약 감사와 adapter 설계 단계다.”

금지 표현:

- “Golden 수출 거래에 외부 헤지 최적화가 적용됐다.”
- “USD 수취와 지급을 모두 지원한다.”
- “기업별 POST API가 있다.”
- “실제 은행 가격으로 최적 상품을 추천한다.”
- “AI가 직접 최적 비율을 생성한다.”
- “검증서가 미래 최적성이나 실제 거래 적합성을 보장한다.”
- “헤지 조합 Top 3가 상담 Top 3 또는 공식 상품 Top 3다.”
- “21거래일 밖 결제도 검증 통과 상태다.”

## 22. 관련 KBaiAgent 문서

forecast의 기존 canonical 계약은 다음 문서가 유지한다.

- [STAGE1_INTEGRATION.md](STAGE1_INTEGRATION.md)
- [STAGE1_JSON_MAPPING.md](STAGE1_JSON_MAPPING.md)
- [STAGE1_CONTRACT.md](STAGE1_CONTRACT.md)
- [STAGE1_CHANGE_REQUEST.md](STAGE1_CHANGE_REQUEST.md)

이 문서는 위 forecast 계약을 대체하지 않는다. `kb_macro_ai@7d3efa4`에 새로 확인된
hedge 조합의 지원 범위와 향후 통합 경계를 고정한다.

## 22.1 후속 구현 상태 (2026-07-31)

감사 후 KBaiAgent에 payable-only read-only adapter가 추가되었다.

- `src/domain/kb_macro_hedge_models.py`: 기존 `Stage3Result`와 분리된 엄격 DTO
- `src/application/kb_macro_hedge_service.py`: 허용 디렉터리 file/fixture와
  pinned `local_cli` provider, SHA pin, Decimal 재검증, 입력 echo·순위·비율·
  notional·certificate 검증
- `app.py`: 3단계 하단의 `외부 환헤지 조합 참고 결과`
- `tests/test_kb_macro_hedge_reference.py`: API-free 정상·실패·지원범위·UI 회귀
- `docs/KB_MACRO_HEDGE_REFERENCE_RUNBOOK.md`: Streamlit 실행과 클릭 순서

feature flag 기본값은 off다. 외부 결과는 기존 Stage 3, Stage 4,
ConsultationPacket, Stage 5에 전달되지 않는다. upstream의 공식 hedge JSON
Schema·manifest와 response 내장 producer/request/forecast hash는 여전히 없으므로,
검증을 통과해도 현재 상태는 최대 `REFERENCE_ONLY`다.

`local_cli`는 다음을 모두 확인한 뒤에만 실행한다.

- producer checkout exact commit과 tracked worktree clean
- forecast, model config, market history, mock quote template SHA-256
- upstream Python 3.11 CLI 모듈과 실행환경
- 단일 `IMPORT`/`USD`/단일 지급일/양수 금액과 보유 USD·기존 선물환 범위
- Stage 2 open exposure와 외부 response echo
- 사용자가 직접 확인한 위험·예산·허용상품 제약

실행 프로세스에는 API key를 전달하지 않으며 요청과 raw output은 권한 제한 임시
디렉터리에서 삭제한다. 실제 로컬 producer smoke에서 `USD 100,000`, 보유 USD
`10,000`, 순노출 `90,000`이 `REFERENCE_ONLY`, validation pass, 후보 rank
`1/2/3`으로 반환됨을 확인했다.

## 23. 이번 감사 검증 결과

### 23.1 KBaiAgent

| 검사 | 실제 결과 |
|---|---|
| 관련 집중 테스트 | 105개 PASS |
| `python scripts/verify.py` | compileall 및 전체 489개 테스트 PASS, `VERIFY PASSED` |
| `python -m pip check` | `No broken requirements found` |
| Markdown 내부 링크·기록 경로 | 존재 여부 검사 PASS |
| `git diff --check` | PASS |
| 문서 secret pattern 검사 | 발견 없음 |

집중 테스트는 Stage 1 web integration, import/export 통합 demo, Golden trade,
consultation priority, Stage 3~5, Stage 5 decision report 경로를 포함했다. Live
API, 환율·뉴스·금융 데이터 API와 유료 API는 호출하지 않았다.

### 23.2 kb_macro_ai

| 검사 | 실제 결과 |
|---|---|
| source compileall | Python 3.11에서 PASS |
| 관련 unit test 실행 | **미통과**: test import 중 NumPy/Pandas 의존성 부재로 중단 |
| dependency 설치 | 수행하지 않음 |
| forecast/hedge pipeline 재생성 | 수행하지 않음 |
| clone status | clean |

외부 집중 테스트는 assertion 실패가 아니라 감사 환경의
`/opt/homebrew/bin/python3.11`에 NumPy/Pandas가 없어 수집 단계에서 중단됐다.
원격 저장소가 runtime dependency를 선언하지 않는 재현성 gap과 결합되므로, 이
감사에서는 외부 테스트를 PASS로 기록하지 않는다.

### 23.3 보호 자산 불변 확인

Golden PDF와 보호 대상 파일의 종료 SHA-256은 2.1의 시작값과 동일했다.
Baseline prediction/report 디렉터리 지문도 다음과 같이 시작·종료가 일치했다.

| Baseline | SHA-256 directory fingerprint |
|---|---|
| prediction v1 full | `5ecb950f6b3a05b69575508a52f060389d3f94cdd40291bb27602d2b271e2c36` |
| prediction v1 smoke | `3830001616ed2ae05c03c5bbbfa7acbb3aa7bd708d67bd1d7e3c2dc16872a649` |
| prediction v2 full | `a206fe474494845265c034b19d2f7a5109975de64bb1300616eca4013e0e45f9` |
| report v1 full | `97ed239027120a2a4fff98d18fe53590b57b8e99117f4c285b6eb44948338670` |
| report v1 smoke | `7966c6b8001c73d8cf310cf9b239845f85e4495f034d24bb43f8f9c2af6c3e4d` |
| report v2 full | `0d629162c305a4179ebabd8b64e7951c6c47b50429c854f9f1b07cec0b54ab03` |

이번 변경은 이 감사 문서 한 파일뿐이며 `app.py`, Stage 0~5, 금융 계산,
ConsultationPacket, 상담 순위, Golden, Baseline, 테스트 fixture, dependency는
수정하지 않았다.
