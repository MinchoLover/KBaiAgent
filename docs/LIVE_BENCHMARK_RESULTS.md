# Country Validation Live Benchmark Results

검증일: 2026-07-29 KST

## 제출용 결론

동일한 합성 test split 8건, `gpt-4o-mini`, evaluator, extraction prompt,
manifest, schema와 안전 정책으로 Baseline v1과 v2를 실행했습니다. 의도된 차이는
국가 canonicalization commit `9bdffd9` 적용 여부입니다.

- `seller_country`: 4/8 → 8/8
- `buyer_country`: 3/8 → 8/8
- `trade_type`: 2/8 → 8/8
- 통화·금액·명시/파생 결제일·분할결제 결과: 불변
- 문서에 없는 값의 hallucination: 0 → 0
- 필요한 null/UNKNOWN abstention: 30/30 → 30/30

위 세 국가·거래방향 개선만 canonicalization의 직접 효과로 주장합니다.
`document_type`, 전체 document match, token, latency와 법인명 표현 차이는
LLM 재호출 변동 가능성이 있어 인과 효과로 주장하지 않습니다.

이 결과는 제한된 합성문서 8건의 Live baseline이며 실제 고객문서, OCR 또는 전체
무역문서 성능으로 일반화할 수 없습니다.

## 실행 식별과 동결 조건

| 항목 | Baseline v1 | Baseline v2 |
| --- | --- | --- |
| Run ID | `baseline-v1-full-20260729-0404-kst` | `baseline-v2-full-20260729-0443-kst` |
| Git SHA | `0a53847549683059e533b0fdf7b1496596dc897f` | `9bdffd91becca3fe8546d8a16186f0469cfdb948` |
| tracked worktree | dirty | clean |
| model | `gpt-4o-mini` | `gpt-4o-mini` |
| cases | 8 | 8 |
| API 성공/실패/timeout | 8/0/0 | 8/0/0 |

공통 동결값:

- evaluator `2.0`:
  `ac0aa62a5a4aefa275f425f90556eb690f3e9f50695de312e9f776b4e8542e89`
- extraction prompt `1.6.0`:
  `396937636dfd843d242f2c7d3a2ec1634ef950bb0795b60e07e72ba1a403eef5`
- manifest:
  `be472519866db43f3e907da45da8ab95dd50ef594201374895846672f6ce0792`
- extraction schema, evidence/confirmation policy, timeout과 호출 옵션
- 미국 4건·브라질 4건, 수입 4건·수출 4건의 합성 test split

V1은 기준 T4 SHA에서 benchmark 코드가 tracked dirty 상태였으므로 SHA만으로 실행
코드를 식별하지 않습니다. 위 evaluator/prompt/manifest hash와 run metadata를 함께
사용합니다. V2 metadata의 `git_worktree_dirty=false`는 tracked 변경 기준이며,
실행 당시 보호 대상 사용자 미추적 파일은 별도로 보존했습니다.

## V1/V2 직접 비교

| 항목 | Baseline v1 | Baseline v2 | 해석 |
| --- | ---: | ---: | --- |
| seller_country | 4/8 | 8/8 | canonicalization 직접 효과 |
| buyer_country | 3/8 | 8/8 | canonicalization 직접 효과 |
| trade_type | 2/8 | 8/8 | 정규화 국가 기반 결정론 파생 |
| document_type | 7/8 | 8/8 | LLM 재호출 변동 가능 |
| 전체 document match | 1/8 | 3/8 | canonicalization 단독 효과로 주장 금지 |
| currency | 8/8 | 8/8 | 불변 |
| amount_due | 8/8 | 8/8 | 불변 |
| explicit_due_date | 8/8 | 8/8 | 불변 |
| derived_due_date | 8/8 | 8/8 | 불변 |
| contract_date | 7/8 | 7/8 | 하루 차이 오류 유지 |
| installment 금액 | 6/6 | 6/6 | 불변 |
| installment 합계 | 3/3 | 3/3 | 불변 |
| event 조건 보존 | 2/2 | 2/2 | 불변 |
| unknown due-date abstention | 3/3 | 3/3 | 불변 |
| 전체 abstention | 30/30 | 30/30 | 불변 |
| hallucination | 0 | 0 | 불변 |
| validation PASS | 0/8 | 0/8 | fail closed |
| Stage 2 전달 허용 | 0/8 | 0/8 | 사용자 확인 전 전부 차단 |
| accepted evidence coverage | 0% | 0% | 독립 검증 근거 없음 |

국가 정규화 전후 각 사례의 `currency`, `grand_total`, `amount_due`, 모든 날짜,
`payment_terms`, `installments`가 문자 단위로 동일했습니다. 통화 누락 사례는
USD로 보정되지 않고 null을 유지했고, 사건 기준 결제조건은 날짜로 변환되지
않았습니다.

## 사례별 국가 정규화

| 사례 | V1 seller/buyer/trade | V2 seller/buyer/trade |
| --- | --- | --- |
| `us_import_split_scan_001` | `US/KR/IMPORT` | `US/KR/IMPORT` |
| `br_import_advance_photo_002` | `Brazil/KR/UNKNOWN` | `BR/KR/IMPORT` |
| `us_export_net60_scan_003` | `KR/US/EXPORT` | `KR/US/EXPORT` |
| `br_export_bl_event_photo_004` | `KR/Brazil/UNKNOWN` | `KR/BR/EXPORT` |
| `us_import_balance_scan_005` | `United States (US)/Republic of Korea (KR)/UNKNOWN` | `US/KR/IMPORT` |
| `br_export_mixed_split_scan_006` | `Republic of Korea (KR)/Brazil (BR)/UNKNOWN` | `KR/BR/EXPORT` |
| `us_import_missing_currency_photo_007` | `United States (US)/Republic of Korea (KR)/UNKNOWN` | `US/KR/IMPORT` |
| `br_export_occluded_due_photo_008` | `KR/Brazil/UNKNOWN` | `KR/BR/EXPORT` |

`br_export_bl_event_photo_004`의 `document_type`은 V1 `UNKNOWN`에서 V2
`SALES_CONTRACT`로 달라졌지만 국가 정규화 코드가 document type을 변경하지 않으므로
canonicalization 성과에 포함하지 않습니다.

## Evidence와 fail-closed 정책

8건은 모두 이미지형 PDF 또는 JPG이며 독립적으로 검증 가능한 텍스트 레이어가
없습니다. Vision 모델이 반환한 인용은 자기 증명이 아니므로 자동으로 신뢰하지
않았습니다.

- `OCR_REQUIRED`
- `EVIDENCE_UNVERIFIABLE`
- `MISSING_CORE_EVIDENCE`
- 사용자 확인 필요: 8/8
- 이미지 evidence 안전 차단: 8/8
- accepted evidence 없는 확정값: 42
- accepted source text 없는 확정값: 42
- `validation_pass=false`: 8/8
- `stage2_allowed=false`: 8/8

Evidence coverage 0%는 OCR 정확도 0%가 아니라 “독립적으로 검증되어 자동 수용된
field evidence가 없음”을 뜻합니다. 추출값은 사람이 원문과 확인하기 전 금융
계산으로 전달되지 않았습니다.

## Abstention과 hallucination

- 문서에 없는 통화 추측: 0
- 문서에 없는 날짜 추측: 0
- 문서에 없는 금액 추측: 0
- false-positive field: 0
- null/UNKNOWN이 필요한 field abstention: 30/30
- 사용자 확인 필요 식별: 8/8
- 의도적 차단 사례 차단: 3/3

한 사례 `us_import_split_scan_001`의 contract date는 label `2026-08-05`에
대해 `2026-08-06`으로 추출되어 하루 차이 오류가 V1과 V2 모두 남았습니다.

## Token, latency와 비용

| 항목 | Baseline v1 | Baseline v2 |
| --- | ---: | ---: |
| input tokens | 310,495 | 310,495 |
| output tokens | 4,539 | 4,660 |
| cached input tokens | UNKNOWN | UNKNOWN |
| 평균 latency | 11.776초 | 8.836초 |
| 비캐시 비용 상한 | USD 0.04929765 | USD 0.04937025 |

비용 상한은 input USD 0.15/1M, output USD 0.60/1M을 사용한 사후 추정입니다.
cached input token을 evaluator가 수집하지 않았으므로 실제 비용은 `UNKNOWN`입니다.
상한은 실제 청구액이 아닙니다. 출력 token과 latency 변화도 canonicalization
효과로 해석하지 않습니다.

## 보안과 산출물 경계

Run metadata는 API key 값, Authorization header, 전체 prompt·payload·문서,
raw model response를 기록하지 않습니다. Live prediction과 report 원본은
`.gitignore` 경로에서 보존하며 제출 문서에는 집계와 필요한 식별 hash만 옮겼습니다.
실제 고객문서와 파인튜닝 데이터는 사용하지 않았습니다.

Sanitized machine-readable 제출 요약은
[`docs/evidence/country_benchmark_v1_v2_summary.json`](evidence/country_benchmark_v1_v2_summary.json)
에 있습니다. 이 파일에는 raw extraction이나 문서 원문이 없습니다.

## 제출 가능한 주장

- 제한된 합성 무역문서 8건을 같은 evaluator와 model로 V1/V2 비교했습니다.
- 검증된 국가 별칭 정규화로 seller/buyer 국가와 그에 따른 거래방향 결과가
  개선됐습니다.
- 금액·통화·결제일·분할결제와 abstention/hallucination 결과는 유지됐습니다.
- 독립 검증할 수 없는 스캔형 입력은 사용자 확인 전 Stage 2로 전달하지 않았습니다.
- Fixture pipeline 검증과 실제 Live model baseline을 분리했습니다.

## 제출하면 안 되는 주장

- 실제 고객문서, OCR 또는 전체 무역문서 정확도 100%
- `document_type`, 전체 document match, latency 개선이 canonicalization의 효과
- evidence coverage 0%가 OCR 정확도 0%라는 해석
- 합성 8건을 운영 환경으로 일반화
- 비용 상한이 실제 청구액이라는 표현
- 금융기관 공식 국가신용등급·상품 승인·실거래 자동화 성능

Baseline smoke와 full 원본은 기존 run ID 경로에 그대로 보존되며, 이 제출 문서는
원본을 수정하거나 덮어쓰지 않습니다.
