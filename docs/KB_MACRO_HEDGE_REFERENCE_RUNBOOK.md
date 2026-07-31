# kb_macro_ai 외부 헤지 참고 결과 실행 안내

## 1. 무엇이 연결됐나

KBaiAgent는 `kb_macro_ai`가 미리 생성한 forecast/hedge JSON을 읽거나, 고정된
로컬 producer commit의 공식 CLI를 현재 확정 거래로 실행한다. 어느 경로든 결과를
다시 검증해 Streamlit 3단계 하단의 **외부 환헤지 조합 참고 결과**에 별도로
표시한다.

이 경로는 다음 경계를 유지한다.

- 단일 USD 수입 지급 한 건만 지원한다.
- 기존 KBaiAgent Stage 3 계산은 항상 유지한다.
- 외부 후보를 Stage 4, ConsultationPacket, Stage 5에 전달하지 않는다.
- 목업 가격이면 검증을 통과해도 `REFERENCE_ONLY`다.
- 수출, 수취, 분할 지급, 복수 거래, 비USD는
  `UNSUPPORTED_EXPOSURE`로 처리하며 파일을 실행하지 않는다.
- provider는 `off`, `fixture`, `file`, `local_cli`다. `local_cli`는 고정 commit,
  clean tracked worktree, forecast/config/history/quote SHA를 모두 확인하고 공식
  `krw_forecast.hedge_recommendation_v1_cli`만 실행한다.
- 임의 shell, HTTP, 원격 다운로드는 실행하지 않는다. CLI에는 API key를 전달하지
  않으며 기업 입력과 raw 결과는 권한을 제한한 임시 디렉터리에서 삭제한다.

현재 `kb_macro_ai@7d3efa41cdc8bbb8da61b6b0c6108bdf55713e3e`는 공식
hedge request/response JSON Schema와 manifest를 제공하지 않는다. 따라서
KBaiAgent의 내부 엄격 계약으로 필수 필드와 수학을 재검증하되, 이 결과를
`READY`나 실제 은행 가격으로 승격하지 않는다.

## 2. 현재 USD 수입 거래로 실제 로컬 모델 실행

로컬 producer 저장소가 다음 위치에 있고 commit과 tracked worktree가 깨끗해야
한다.

```text
/Users/jeongminchan/Desktop/kb_macro_ai
7d3efa41cdc8bbb8da61b6b0c6108bdf55713e3e
```

현재 검증한 고정 입력 fingerprint로 Streamlit을 시작한다.

```bash
cd /Users/jeongminchan/Desktop/invoice_intake_mvp

ENABLE_KB_MACRO_HEDGE_REFERENCE=true \
KB_MACRO_HEDGE_MODE=local_cli \
KB_MACRO_HEDGE_ALLOWED_ROOT=/Users/jeongminchan/Desktop/kb_macro_ai \
KB_MACRO_FORECAST_FILE=web_runtime/output/latest_forecast.json \
KB_MACRO_MODEL_CONFIG_FILE=configs/hedge_recommendation_v1.json \
KB_MACRO_MARKET_HISTORY_FILE=web_runtime/bundle_v1/market_history.csv \
KB_MACRO_QUOTE_TEMPLATE_FILE=examples/mock_company_exposure.json \
KB_MACRO_EXPECTED_PROVIDER_COMMIT_SHA=7d3efa41cdc8bbb8da61b6b0c6108bdf55713e3e \
KB_MACRO_EXPECTED_FORECAST_SHA256=b565cfa283ba93541541bce0ef88e8f9e4e5bb2b5557fefdc8429638c678318c \
KB_MACRO_EXPECTED_MODEL_CONFIG_SHA256=56904f5fe31312bca5cdf4f8910870c7d02b93faf3c60eade6731d224126e1a3 \
KB_MACRO_EXPECTED_MARKET_HISTORY_SHA256=78feb433e43f51ba556b39f737db2616cbe3c3bd34d6cd02b68372e473b51c39 \
KB_MACRO_EXPECTED_QUOTE_TEMPLATE_SHA256=c537c65b1d33398bd5de7007c56c8189833c04ebfaf46ab04a0b8e1e3213168f \
.venv/bin/python -m streamlit run app.py
```

같은 환경변수로 앱을 열기 전 한 번에 무결성과 합성 수입 E2E를 확인할 수 있다.

```bash
python scripts/check_integration_readiness.py --run-local-cli-e2e
```

이 명령은 `USD 100,000`, 지급일 `2026-08-27`, 보유 USD `10,000`, 기존
선물환 `0`인 합성 단일 수입 지급만 사용한다. 기존 local CLI gate와 응답
validator를 그대로 통과하며 성공 시 `REFERENCE_ONLY / MOCK`, validation PASS,
후보 rank `1,2,3`, 임시 raw 삭제를 표시한다. 환율·OpenAI API는 호출하지 않는다.
결과 필드와 상태 해석은
[INTEGRATION_READINESS.md](INTEGRATION_READINESS.md)를 본다.

### 고정 Golden 수입계약을 직접 첨부하는 경우

업로드 문서는 다음 합성 텍스트 PDF 한 건이다.

```text
dataset/golden_import_hedge_demo/golden_import_payable_contract.pdf
SHA-256:
fbd4c4dbdf0f92d459e19acf2af4a1e2ee3cd0916f43576290d54b040662550b
```

API-free 사전점검:

```bash
shasum -a 256 \
  dataset/golden_import_hedge_demo/golden_import_payable_contract.pdf
python scripts/verify_golden_import_hedge_flow.py
python -m unittest tests.test_golden_import_hedge_demo -v
```

두 번째 명령은 실제 PDF bytes의 upload guard, 2페이지 텍스트 레이어와 정확한
evidence를 확인한 뒤 expected extraction test double로 confirmation, Stage 2,
기존 Stage 3와 외부 fixture validator를 실행한다. OpenAI, 환율 API,
`kb_macro_ai` CLI와 외부 네트워크는 호출하지 않는다. 따라서 이 PASS는
직접 업로드 이후의 데이터 흐름과 어댑터 검증이지 Live 추출 정확도가 아니다.

브라우저에서는 다음 순서로 진행한다.

1. `거래문서 등록하기`를 누른다.
2. `실제 문서 분석`, `구매자 · BUYER`, 회사 국가 `KR`을 선택한다.
3. 위 Golden 수입 PDF를 첨부하고 `문서 분석하고 거래정보 채우기`를 누른다.
4. `SALES_CONTRACT / IMPORT / USD / 100000.00 / 2026-08-27`과
   단일 지급을 원문 evidence와 대조한다.
5. 역할·방향·통화·분석 대상 예정 지급액·지급일 확인을 체크하고 거래를
   확정한다.
6. 금융 리스크 분석에서 계산 기준일 `2026-07-29`, 현재 원화 현금
   `140000000`, 최소 운영자금 `10000000`, 신용한도 `0`, 보유 USD
   `10000`, 허용 환손실 `5000000`, 기존 선물환 `0`을 입력한다.
7. 현금영향 계산 후 기존 Stage 3의 계산상 비교안 3개를 확인한다.
8. `3 · 상담 준비` 탭 아래 `외부 환헤지 조합 참고 결과`로 이동한다.
9. 지급 확정도 `1.0`, 최대 원화 지급액 `135000000`,
   최대 예산초과확률 `0.15`, 위험성향 `medium`, 최대 헤지비율 `1.0`,
   옵션 예산 `1500000`, 허용 상품 `forward`와 `vanilla_usd_call`을
   확인한다.
10. 목업 견적 사용 확인을 체크한다.
11. `현재 수입 거래로 kb_macro_ai 계산하기`를 누른다.
12. `REFERENCE_ONLY`, `MOCK`, 예정 지급액 USD 100,000, 보유 USD 10,000,
    순노출 USD 90,000, 지급일 2026-08-27, 후보 3개와 provenance를 확인한다.

수출, 비USD, 분할 지급, 복수 노출, 자연상계 흐름은 CLI 실행 전에
`UNSUPPORTED_EXPOSURE`로 차단된다. 외부 실행이 실패해도 기존 Stage 3 결과는
유지된다.

위 3단계 실제 문서 분석에는 기존 OpenAI 추출 설정이 필요하다. key 값은 UI,
명령 출력이나 저장 파일에 넣지 않는다. API 없이 재현할 때는 expected JSON을
Streamlit production 경로에 주입하지 말고 위 검증 스크립트를 사용한다.

## 3. 사전 생성 파일 Streamlit 검증

먼저 `kb_macro_ai`에서 다음 두 파일을 생성한다.

```text
web_runtime/output/latest_forecast.json
web_runtime/output/latest_hedge_recommendation.json
```

두 파일의 SHA-256을 확인한다.

```bash
shasum -a 256 web_runtime/output/latest_forecast.json
shasum -a 256 web_runtime/output/latest_hedge_recommendation.json
```

KBaiAgent를 실행하는 터미널에서 아래 값을 실제 경로와 SHA로 바꾼다.

```bash
export ENABLE_KB_MACRO_HEDGE_REFERENCE=true
export KB_MACRO_HEDGE_MODE=file
export KB_MACRO_HEDGE_ALLOWED_ROOT=/absolute/path/to/kb_macro_ai
export KB_MACRO_FORECAST_FILE=web_runtime/output/latest_forecast.json
export KB_MACRO_HEDGE_FILE=web_runtime/output/latest_hedge_recommendation.json
export KB_MACRO_EXPECTED_PROVIDER_COMMIT_SHA=7d3efa41cdc8bbb8da61b6b0c6108bdf55713e3e
export KB_MACRO_EXPECTED_FORECAST_SHA256=replace_with_64_hex_forecast_sha
export KB_MACRO_EXPECTED_HEDGE_SHA256=replace_with_64_hex_hedge_sha
python -m streamlit run app.py
```

브라우저에서 다음 순서로 누른다.

1. 상단의 `3 · 상담 준비` 탭을 누른다.
2. 화면 아래 `외부 환헤지 조합 참고 결과`까지 내린다.
3. `검증 범위`에서 `외부 fixture 파일 자체 검증`을 선택한다.
4. `외부 파일에 고정된 목업 제약조건을 참고 검증에 사용합니다`를 체크한다.
5. `외부 헤지 파일 검증하기`를 누른다.
6. `참고 전용`, `목업 가격`, 후보 3개와 검증 경고를 확인한다.
7. `고급 · 정규화된 외부 참고 데이터`에서 raw response가 아닌 정규화 결과만
   내려받을 수 있다.

이 자체 검증은 현재 앱에 입력한 거래와 연결됐다는 뜻이 아니다. 방금 생성한 두
외부 파일의 교차 참조, 금액·날짜 echo, 순노출, 후보 순위, 비율, notional,
certificate를 검사한다.

## 4. 사전 생성 파일을 현재 확정 거래와 대조하려면

`검증 범위`에서 `현재 확정 거래와 금액·지급일 대조`를 선택한다. 이때
KBaiAgent에서 사용자 확인을 마치고 Stage 2를 계산한 거래가 다음 조건을 모두
충족해야 한다.

| KBaiAgent 확정 거래 | 외부 `company_exposure` |
|---|---|
| 거래 한 건 | 단일 `usd_payable` |
| `IMPORT` | `exposure_type=usd_payable` |
| `USD` | `amount_usd`의 통화 의미 |
| 거래 예정 지급액 | `amount_usd` |
| 확정 지급일 | `payment_date` |
| 지급에 사용할 보유 USD | `existing_usd_cash` |
| 기존 선물환 USD | `existing_forward_usd` |
| Stage 2 open exposure | `net_exposure_usd` |

현재 생성된 합성 파일을 대조할 경우 입력은 다음과 같아야 한다.

| 항목 | 값 |
|---|---:|
| 거래 방향 | 수입 `IMPORT` |
| 통화 | `USD` |
| 예정 지급액 | `100000` |
| 지급일 | `2026-08-27` |
| 지급에 사용할 보유 USD | `10000` |
| 기존 선물환 | `0` |
| 예상 순노출 | `90000` |

하나라도 다르면 `VALIDATION_FAILED`로 외부 후보를 숨긴다. 앱 내부 Stage 3
후보는 그대로 남는다.

## 5. 자동으로 매핑하지 않는 값

다음 값은 기존 Stage 3 입력에서 변환하지 않는다. 외부 파일에 있는 목업
제약조건을 사용한다는 체크를 사용자가 명시적으로 눌러야 한다.

- `payment_certainty`
- `maximum_acceptable_cost_krw`
- `maximum_budget_exceedance_probability`
- `risk_tolerance`
- `maximum_total_hedge_ratio`
- `option_premium_budget_krw`
- `allowed_instruments`

특히 다음 변환은 하지 않는다.

- `acceptable_fx_loss` → `maximum_acceptable_cost_krw`
- `risk_aversion_weight` → `risk_tolerance`
- `maximum_forward_ratio` → `maximum_total_hedge_ratio`
- 외부 USD call option → 기존 Stage 3 `staged_conversion_ratio`

## 6. 검증 항목

구현은 다음을 fail-closed로 검사한다.

- 허용 디렉터리, 일반 파일, 최대 크기, UTF-8 JSON
- 고정 producer commit과 두 파일 SHA-256
- forecast/hedge schema allowlist
- prediction date와 horizon 교차 일치
- 입력 amount/date/cash/forward echo와 순노출
- 후보 정확히 3개, rank `1, 2, 3`, objective 오름차순
- 모든 비율 범위와 합 `1`
- 모든 notional 비음수, 순노출 이하, 합계와 비율 일치
- 알려진 선물환·USD call option만 사용
- certificate 필수 boolean
- prototype 고지와 목업/비목업 표시

하나라도 실패하면 `VALIDATION_FAILED`, 파일을 읽을 수 없으면
`UPSTREAM_UNAVAILABLE`이며 외부 후보를 게시하지 않는다.

## 7. API-free 회귀 fixture

저장소의 `tests/fixtures/kb_macro_hedge_reference/`는 어댑터 테스트용으로
축소한 합성 fixture다. 공식 upstream 계약이나 모델 정확도 증거가 아니다.

```bash
python -m unittest tests.test_kb_macro_hedge_reference -v
python scripts/verify.py
```

fixture 모드도 파일 경로와 SHA를 명시해야 한다. feature flag 기본값은
항상 `false`, mode 기본값은 `off`다.

## 8. 표시하면 안 되는 주장

- 최적 상품 추천
- 실행 권고 또는 가입 승인
- 은행 실제 가격
- Golden 수출 거래에 적용됨
- AI가 헤지 비율을 직접 생성함
- 외부 Top 3가 KBaiAgent 상담·공식상품 Top 3와 같은 순위임
