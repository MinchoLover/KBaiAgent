# 거래국 무역 통계

## 목적과 경계

거래국 무역 통계는 확정 거래의 우리 회사 국가, 상대국, 수출입 방향과 사용자가
명시적으로 확인한 HS Code를 기준으로 공식 월별 수출·수입·무역수지를 조회하고
요약한다. 이 결과는 양국 교역 규모와 최근 흐름을 이해하기 위한 참고 맥락이다.

다음 값에는 입력하지 않는다.

- Stage 1 환율 경로·stress
- Stage 2 현금흐름
- Stage 3 헤지 목적함수·비율
- 결제·회수 위험과 국가환경 priority
- 상담 Top 3와 공식 상품 후보
- eligibility·승인·보험 인수 판단

따라서 통계로 개별 거래처 신용위험, 국가위험 점수, 부도확률, 환율 방향 또는
금융상품 승인 가능성을 생성하지 않는다. 무역통계가 실패해도 기존 금융분석은
계속 실행된다.

## 지원 범위

- 국가 전체 양국 교역: 필수
- 월별 수출금액·수입금액·무역수지: 필수
- 최근 12개월 합계와 직전 12개월 대비 증감: 24개월이 완전할 때 제공
- 최근 3개월과 직전 3개월의 단순 증가·감소·유사·비교 불가: 제공
- 확인된 HS 2·4·6·10단위 품목 통계: 조건부
- HS 자동 추론, 주요 품목 Top N, 관세·FTA·원산지 판정: 미지원
- UN Comtrade: provider interface의 향후 확장점만 유지하며 이번 버전에서는
  관세청 값과 혼합하거나 무음 fallback하지 않음

## 공식 provider 계약

1차 provider는 공공데이터포털의
[관세청 품목별 국가별 수출입실적 OpenAPI](https://www.data.go.kr/data/15100475/openapi.do)다.

- method: REST GET
- endpoint: `https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList`
- request: `serviceKey`, `strtYymm`, `endYymm`, `cntyCd`, 선택 `hsSgn`
- 기간: `YYYYMM`, 요청 1회 최대 12개월
- response header: `resultCode`, `resultMsg`
- response item: `year`, `statCdCntnKor1`, `statCd`, `statKor`, `hsCd`,
  `expWgt`, `expDlr`, `impWgt`, `impDlr`, `balPayments`
- 수출금액: FOB, USD
- 수입금액: CIF, USD
- 중량: 순중량 kg
- 과거 값: 수출입 신고 정정·취하에 따라 변경 가능

24개월 요청은 최근·직전 기간을 최대 12개월 단위로 분할한 뒤
`period/reporter/partner/hs/source` 기준으로 병합한다. 같은 키가 중복되면 값을
고르지 않고 fail closed한다. 미응답 월과 공식 0은 구분하고 미래·미게시 월은
요청하지 않는다. 게시월 cutoff 판단은 관세청 기준인 `Asia/Seoul` 날짜를 사용하고,
수집시각은 timezone offset이 포함된 ISO-8601로 저장한다.

## 도메인 계약

- `TradeStatisticsRequest`: 확정 거래 fingerprint와 reporter/partner/direction,
  기간, 선택 HS, provider와 snapshot version
- `TradeStatisticsObservation`: 월, 수출·수입·수지, 선택 중량, 원기록 ID
- `TradeStatisticsSnapshot`: 출처·수집일·관측기간·raw/normalized hash와 검증된
  observations
- `TradeStatisticsSummary`: 최근·직전 12개월 합계, 증감률, 최근 3개월 방향,
  결측 수와 사용자 설명
- `TradeStatisticsResult`: 가용 상태 또는 구조화 오류 상태

금액과 증감 계산은 `Decimal`로 수행하고 JSON에는 과학표기 없는 문자열로
보존한다. 화면에서만 천 단위와 소수 자릿수를 반올림한다.

## 요청 생성과 HS Code

요청은 `ConfirmedTransactionSnapshot`이 있을 때만 생성한다. 한국 회사의 EXPORT는
buyer 국가, IMPORT는 seller 국가를 상대국으로 사용한다. 원자료의 한국 수출·수입
정의 자체는 뒤집지 않고 거래 방향은 강조할 카드만 결정한다.

HS Code는 다음을 모두 만족할 때만 `hsSgn`에 전달한다.

1. 사용자가 신고·계약 자료에서 직접 확인함
2. 숫자로만 구성됨
3. 길이가 2·4·6·10 중 하나임

상품명·설명·회사명·파일명으로 HS Code를 추측하지 않는다. HS가 없으면
`COUNTRY_TOTAL`을 제공하며 품목 통계에는 `MISSING_HS_CODE` 안내를 표시한다.

## 결정론 요약

최신 관측월을 끝으로 완전한 12개월과 그 직전 12개월을 구분한다.

```text
yoy = (current - previous) / abs(previous) * 100
```

- previous가 0이면 `PREVIOUS_ZERO`; 무한대나 100%를 생성하지 않음
- 월이 빠지면 `MISSING_MONTHS`; 빠진 월을 0으로 채우지 않음
- 24개월 미만이면 `INSUFFICIENT_HISTORY`; 12개월 비교라고 표현하지 않음
- 최근 방향은 최신 3개월 합계와 직전 3개월 합계의 단순 비교이며 예측이 아님
- 수지는 음수일 수 있지만 수출·수입금액과 중량은 음수를 거부함

## Live와 API-free

`TRADE_STATISTICS_PROVIDER=auto`가 기본이다.

- 등록된 Golden/데모: 검증된 `OFFICIAL_FIXTURE`
- 실제 업로드: `LIVE`
- 실제 업로드에서 key가 없으면 `MISSING_API_KEY`; fixture를 최신 live처럼 대체하지 않음
- `fixture` 또는 `live`를 명시적으로 선택할 수 있으나 실제 상태를 UI와 보고서에 표시

```dotenv
TRADE_STATISTICS_PROVIDER=auto
CUSTOMS_TRADE_API_KEY=
TRADE_STATISTICS_TIMEOUT_SECONDS=10
TRADE_STATISTICS_SNAPSHOT_VERSION=2026.08.01-kr-br-country-v1
```

API key는 코드·로그·UI·trace·다운로드에 포함하지 않는다.

## Golden 공식 fixture

- 범위: 한국–브라질 국가 전체, `2024-07`~`2026-06`
- 출처: 관세청 [수출입무역통계 공개 조회](https://tradedata.go.kr/cts/index.do)
- 수집일: `2026-08-01T22:55:18+09:00`
- raw SHA-256:
  `16fcfc5222aab3e9b58dc3481cd130c411dbbcb4b103f994a1b42d872edb9cb5`
- normalized SHA-256:
  `3e3120223e00013fcfbe9168bb794be21834c3c329b58d618fa84c09308e6b5b`
- 최근 12개월 수출: USD 8,282,425,000
- 최근 12개월 수입: USD 6,154,122,000
- 최근 12개월 수지: USD 2,128,302,000

공개 화면 월별 값은 천 USD 단위로 반올림돼 있다. raw record 문자열을 바꾸지 않고
정규화 시 1,000을 곱하며 월별 합계와 공식 TOTAL에는 USD 1,000의 반올림 허용차만
둔다. 상세 provenance는
`src/integration_assets/trade_statistics/README.md`에 기록한다.

## 검증과 오류 상태

provider는 result code, 국가, 요청기간, HS, 월 형식, 숫자, 음수 금액·중량,
`balance=export-import`, 중복, 시간순서, 미래월, observation 수와 raw hash를
검증한다. 정상 통계로 표시하지 않는 상태는 다음과 같다.

- `MISSING_PARTNER_COUNTRY`, `INVALID_COUNTRY_CODE`, `INVALID_HS_CODE`
- `MISSING_API_KEY`, `INVALID_PERIOD`
- `UPSTREAM_TIMEOUT`, `UPSTREAM_ERROR`, `RESPONSE_PARSE_ERROR`
- `NO_DATA`, `INSUFFICIENT_HISTORY`, `STALE_DATA`
- `FIXTURE_NOT_AVAILABLE`, `VALIDATION_FAILED`, `UNSUPPORTED_COUNTRY`

fallback은 무음으로 수행하지 않는다. demo fixture와 live 상태, 관측기간, 출처는
화면과 ConsultationPacket, Stage 5 JSON·Markdown에서 동일한 객체를 사용한다.

## UI·보고서·상태

금융분석의 국가환경과 별개인 “거래국 무역 통계” 섹션에 12개월 metric 3개,
증감, 거래방향 해석, 최근 12개월 월별 수출·수입 차트를 표시한다. 결측월은 0으로
그리거나 임의 연결하지 않는다. endpoint·request parameter·hash·warning code는
“출처 및 기술정보” expander에 둔다.

ConsultationPacket과 Stage 5는 같은 `TradeStatisticsResult`를 직렬화한다. 통계
입력 hash는 reporter, partner, direction, HS, 기간, provider, source preference,
snapshot version과 confirmed transaction fingerprint를 포함한다. 거래·문서·국가·
방향·HS·provider·기간이 바뀌면 이전 결과를 재사용하지 않는다.

## 실행과 테스트

```bash
python scripts/verify_trade_statistics_fixture.py
python -m unittest tests.test_trade_statistics -v
python scripts/verify_golden_user_flow.py
python scripts/verify.py
```

테스트 transport와 recorded fixture만 사용하며 단위·AppTest에서 실제 네트워크를
호출하지 않는다. keyed OpenAPI live 호출은 별도 key와 운영 환경에서만 수행한다.
