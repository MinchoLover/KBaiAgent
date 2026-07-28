# T4 국가·무역환경 검토 설계

## 제품·문제·대상 사용자

KBaiAgent T4는 한국 수출입기업 담당자가 사용자 확인을 마친 미국·브라질
거래에 대해 지급·이전, 거시환경, 무역·시장접근 근거를 구분해 보고
은행·보험·보증·신용장·결제조건 상담 순서를 준비하도록 돕는다.

주요 여정은 거래 문서 확인 → 거래 상대국과 결제·보호조건 확인 → offline
snapshot 검증 → 세 축별 원값과 거래 검토 우선순위 확인 → 상담 패킷과 최종
보고서 확인이다.

완료 기준은 같은 snapshot과 입력이 같은 결과를 만들고, US 90일 무보호
Open Account가 `ELEVATED_REVIEW`, 동일한 BR 거래가 `HIGH_REVIEW`이며,
Stage 1~3 숫자·헤지 후보와 공식 상품 자격·승인을 바꾸지 않는 것이다.

## P0 범위

1. US·BR 공식 원값의 versioned offline snapshot과 strict loader
2. OECD·World Bank·WTO를 합산하지 않는 결정론 분석
3. optional `ConsultationPacket`, T5 상담 질문, T7 보고서·critic 연결
4. 최소 UI와 fail-closed·불변성·회귀 테스트

비목표는 국가 신용등급, 0~100 점수, 부도확률, 실시간 수집, 환율·현금흐름·
헤지 계산 변경, 상품 승인 예측, US·BR 외 국가 확장이다.

## 공식 source table

| 축 | 국가 | 공식 자료·URL | 기준일·관측기간 | raw value/status | 한계 |
|---|---|---|---|---|---|
| OECD 지급·이전 | BR | [OECD Country Risk Classifications](https://www.oecd.org/content/dam/oecd/en/topics/policy-sub-issues/country-risk-classification/cre-crc-current-english.pdf) | 2026-06-26 | `4`, `CLASSIFIED` | OECD 원값이며 KBaiAgent 국가등급이 아님 |
| OECD 지급·이전 | US | [OECD Country Risk Classifications](https://www.oecd.org/content/dam/oecd/en/topics/policy-sub-issues/country-risk-classification/cre-crc-current-english.pdf) | 2026-06-26 | `null`, `HIGH_INCOME_OECD_UNCLASSIFIED` | 0·LOW·안전 또는 정보 부족으로 바꾸지 않음 |
| World Bank GDP 성장률 | BR | [World Bank API](https://api.worldbank.org/v2/country/BR/indicator/NY.GDP.MKTP.KD.ZG?format=json&date=2020:2026&per_page=100) | 갱신 2026-07-13, 관측 2025 | `2.2857464902475` annual % | 개정 가능, 임의 임계값 없음 |
| World Bank 물가상승률 | BR | [World Bank API](https://api.worldbank.org/v2/country/BR/indicator/FP.CPI.TOTL.ZG?format=json&date=2020:2026&per_page=100) | 갱신 2026-07-13, 관측 2025 | `5.01675279604836` annual % | 점수·등급·환율 예측에 사용하지 않음 |
| World Bank 경상수지 | BR | [World Bank API](https://api.worldbank.org/v2/country/BR/indicator/BN.CAB.XOKA.GD.ZS?format=json&date=2020:2026&per_page=100) | 갱신 2026-07-13, 관측 2025 | `-2.92630139201733` % GDP | 지급불능·승인 판단으로 변환하지 않음 |
| World Bank GDP 성장률 | US | [World Bank API](https://api.worldbank.org/v2/country/US/indicator/NY.GDP.MKTP.KD.ZG?format=json&date=2020:2026&per_page=100) | 갱신 2026-07-13, 관측 2025 | `2.16138195623856` annual % | 개정 가능, 임의 임계값 없음 |
| World Bank 물가상승률 | US | [World Bank API](https://api.worldbank.org/v2/country/US/indicator/FP.CPI.TOTL.ZG?format=json&date=2020:2026&per_page=100) | 갱신 2026-07-13, 최신 비결측 관측 2024 | `2.94952520485207` annual % | 2025 값은 null, 다른 지표와 관측연도가 다름 |
| World Bank 경상수지 | US | [World Bank API](https://api.worldbank.org/v2/country/US/indicator/BN.CAB.XOKA.GD.ZS?format=json&date=2020:2026&per_page=100) | 갱신 2026-07-13, 관측 2025 | `-3.62698693844919` % GDP | 지급불능·승인 판단으로 변환하지 않음 |
| WTO MFN 시장접근 | BR | [WTO trade profile](https://ttd.wto.org/en/profiles/brazil/) | 관세 2025 | MFN 단순평균 `12.0%` | 품목별·특혜·실효관세와 다를 수 있음 |
| WTO MFN 시장접근 | US | [WTO trade profile](https://ttd.wto.org/en/profiles/united-states-of-america) | 관세 2025 | MFN 단순평균 `3.4%` | 2026 임시조치와 품목별 관세를 확정하지 않음 |
| WTO 회원 | BR | [WTO Brazil member page](https://www.wto.org/english/thewto_e/countries_e/brazil_e.htm) | 1995-01-01~2026-07-29 | member since `1995-01-01` | 개별 품목 통관·관세 충족을 보장하지 않음 |
| WTO 회원 | US | [WTO US member page](https://www.wto.org/english/thewto_e/countries_e/usa_e.htm) | 1995-01-01~2026-07-29 | member since `1995-01-01` | 개별 품목 통관·관세 충족을 보장하지 않음 |
| WTO 무역정책검토 | BR | [2022 TPR](https://www.wto.org/english/tratop_e/tpr_e/tp532_crc_e.htm) | 2022 | `EIGHTH_TRADE_POLICY_REVIEW` | 현재 거래 조건을 확정하지 않음 |
| WTO 무역정책검토 | US | [2022 TPR](https://www.wto.org/english/tratop_e/tpr_e/tp534_crc_e.htm) | 2022 | `FIFTEENTH_TRADE_POLICY_REVIEW` | 현재 거래 조건을 확정하지 않음 |

검증일은 모두 `2026-07-29`이다. OECD 기준일을 World Bank·WTO에 적용하지
않는다.

## snapshot schema와 재현

snapshot metadata는 `schema_version`, `snapshot_version`, `snapshot_id`,
`supported_countries`, 고정 `generated_or_curated_at`, `source_records`,
`snapshot_hash`를 가진다. 각 source record는 ID, source·axis·country,
indicator, 공식 URL·제목, source 기준일, 실제 관측기간, 게시·갱신일,
검증일, 원값/status, 단위, 제한적 해석, 한계와 검증 상태를 가진다.

소수는 과학표기 없는 Decimal 문자열로 저장하고 float를 거부한다. 공식 URL은
정확한 OECD·World Bank·WTO HTTPS host 또는 그 하위 host만 허용한다.
canonical hash는 hash 필드를 제외하고 국가·source ID 순으로 정렬한 JSON의
SHA-256이다. schema·version·hash·핵심 provenance가 맞지 않으면
`INSUFFICIENT_INFORMATION`으로 닫힌다.

## 아키텍처 결정

### 독립 auxiliary domain/service

- context: 기존 runtime Stage 4는 공식 상품검색이며 T4 티켓과 이름만 겹친다.
- alternatives: 새 runtime stage, trade-risk 모델 내부 결합, 독립 auxiliary
  domain/service
- decision: `src/country_environment/`의 독립 loader·engine과
  `src/application/country_environment_service.py` adapter를 사용한다.
- rationale: Stage 1~3과 기존 Stage 4를 건드리지 않고 optional packet·report
  연결과 독립 fingerprint/invalidation을 구현할 수 있다.
- trade-off: workflow 주 경로 외에 auxiliary state를 별도 관리해야 한다.
- revisit: 지원 국가나 갱신 주기가 확대되어 독립 배치가 필요할 때 재검토한다.

### 국가등급 대신 거래 검토 우선순위

세 축은 합산하지 않고 `STANDARD_REVIEW`, `ELEVATED_REVIEW`, `HIGH_REVIEW`,
`INSUFFICIENT_INFORMATION`만 사용한다. 이는 국가 위험등급이 아니라 동일한
거래에서 보호수단과 조건을 확인할 상담 순서다.

### versioned offline snapshot

runtime API 대신 commit된 snapshot을 사용한다. 수동 검증과 새 version 검토
없이 자동 refresh·덮어쓰기를 하지 않는다.

## 데이터 흐름과 무효화

사용자 확인 문서와 거래·결제 확인 기록에서 상대국·통화·Open Account·결제기간·
보호수단만 adapter가 복사한다. engine은 committed snapshot을 검증한 뒤 세 축과
공개 rule contribution을 만들고, optional workflow auxiliary result와 안전한
trace를 저장한다. T5 topic과 packet, T7 보고서는 이 구조화 결과만 설명한다.

상대국 또는 T4 입력이 바뀌면 T4 input·assessment·trace, 상담 topic, packet,
report를 지운다. Stage 1~3, 기존 거래·결제 assessment, runtime Stage 4 retrieval은
유지한다. 전체 snapshot payload·문서 원문·비밀값은 trace나 dataset으로 전달하지
않는다.

## 공개 priority rule table

| rule code | 관측 | review need | priority 방향 |
|---|---|---|---|
| `SNAPSHOT_VALIDATION_FAILED` | schema/version/hash 실패 | 정보 완전성 | `INSUFFICIENT_INFORMATION` |
| `UNSUPPORTED_COUNTRY` | snapshot record 없음 | 정보 완전성 | `INSUFFICIENT_INFORMATION` |
| `SOURCE_PROVENANCE_MISSING` | 세 핵심 축 중 하나 누락 | 정보 완전성 | `INSUFFICIENT_INFORMATION` |
| `OECD_HIGH_INCOME_UNCLASSIFIED_NOT_MITIGANT` | US 미분류 | 없음 | 감경 없음 |
| `OECD_CLASSIFICATION_4_PROTECTION_REVIEW` | BR raw `4` | 지급·이전 보호 검토 | 단독 변경 없음 |
| `OPEN_ACCOUNT_90_DAY_UNPROTECTED` | 90일 이상 OA·무보호 | 보험·보증·L/C·결제조건 | 최소 `ELEVATED_REVIEW` |
| `PAYMENT_TRANSFER_SIGNAL_WITH_UNPROTECTED_TERMS` | 위 조건 + BR OECD 행동 신호 | 지급·이전 보호 검토 | `HIGH_REVIEW` |
| `WORLD_BANK_CONTEXT_ONLY` | 분리된 거시 원값 | 모니터링 | 변경 없음 |
| `WTO_MARKET_ACCESS_CONTEXT_ONLY` | 회원·관세·TPR | 시장접근 확인 | 변경 없음 |

모든 contribution은 code, source axis, raw/status, review need, priority 방향과
사람이 읽는 이유를 남긴다.

## 대표 동일조건 비교

SELLER, EXPORT, USD, 기존 거래처, Open Account, 90 calendar days,
무보험·무보증, 동일 금액·현금흐름·환율·기존 헤지에서 국가만 바꾼다.

- US: OECD `HIGH_INCOME_OECD_UNCLASSIFIED`, raw `null`, 감경 없음,
  `ELEVATED_REVIEW`
- BR: OECD raw `4`,
  `PAYMENT_TRANSFER_PROTECTION_REVIEW_REQUIRED`, `HIGH_REVIEW`

## 보안·한계

문서 원문·기업정보·API key·전체 공식 웹 payload를 snapshot·trace에 저장하지
않는다. trace에는 country, snapshot ID, rule version, priority, 사용한 source
record IDs와 warning code만 둔다. 모든 공식값은 개정될 수 있고 개별 품목,
계약, 통관, 보험 인수, 은행 승인 판단을 대신하지 않는다.

## 테스트 전략

snapshot schema/version/hash/공식 host와 US·BR 원값 계약을 먼저 검증하고,
동일한 대표 입력으로 결정성·우선순위·금지 필드 부재를 확인한다. 통합 테스트는
Stage 1~4 dump와 상품 eligibility·approval 불변, packet hash binding, 안전한
trace를 비교한다. 보고서 critic에는 잘못된 자체등급, US `LOW·0`, 합산점수,
source 변조, 헤지·현금흐름 변경과 승인 주장을 주입한다. Streamlit AppTest는
정상 미분류와 `INSUFFICIENT_INFORMATION` 표시를 모두 실행한다.
