# Live Benchmark Results

## 실행 식별

- run ID: `baseline-v1-smoke-20260729-0341-kst`
- baseline: `baseline-v1`
- 실행 시각: 2026-07-29 03:40:52~03:41:11 KST
- Git HEAD:
  `0a53847549683059e533b0fdf7b1496596dc897f`
- 실행 당시 tracked worktree: dirty
- Python: 3.9.6
- evaluator version/hash:
  `2.0` /
  `ac0aa62a5a4aefa275f425f90556eb690f3e9f50695de312e9f776b4e8542e89`
- extraction prompt version/hash:
  `1.6.0` /
  `396937636dfd843d242f2c7d3a2ec1634ef950bb0795b60e07e72ba1a403eef5`
- manifest hash:
  `be472519866db43f3e907da45da8ab95dd50ef594201374895846672f6ce0792`
- 요청·실제 사용 model: `gpt-4o-mini`
- fallback model: `gpt-4o` 미사용

Git SHA는 기준 T4 commit이고 `git_worktree_dirty=true`였습니다. 따라서 정확한 실행
코드는 위 evaluator hash, prompt hash와 manifest hash를 함께 사용해 식별합니다.
API key 값, `.env`, 전체 prompt·문서·payload·raw response는 기록하지 않았습니다.

## 데이터셋과 실행 사례

전체 합성 validation manifest 8건 중 처음 2건만 실행했습니다.

| 사례 | 범위 |
| --- | --- |
| `us_import_split_scan_001` | 미국 수입, 이미지형 PDF, 30/70 분할결제 |
| `br_import_advance_photo_002` | 브라질 수입, JPG 사진, 20% 선지급·80% 잔금 |

두 사례 모두 합성문서이고 실제 고객문서는 없습니다. 이 smoke run에는 수출,
의도적 차단, 통화 누락, 사건 기준일 미확정 사례가 포함되지 않았습니다.

## 실행 결과

| 구분 | 결과 |
| --- | ---: |
| 선택·실행 건수 | 2 |
| API/구조화 응답 성공 | 2 |
| API 실패 | 0 |
| timeout | 0 |
| 자동 document PASS | 0/2 |
| Stage 2 전달 허용 | 0/2 |
| 사용자 확인 필요 식별 | 2/2 |

`API 성공 2건`은 모델 호출과 schema parsing이 완료됐다는 뜻입니다. 자동 document
PASS 0건은 이미지 evidence가 독립 검증되지 않았고 국가 정규화·거래방향 오류가
남아 계산 전달이 차단됐다는 뜻입니다. 두 값을 섞어 성공률로 표현하지 않습니다.

## 핵심 필드

| 필드 | 정확 |
| --- | ---: |
| currency | 2/2 |
| amount_due | 2/2 |
| document_type | 2/2 |
| company_role | 2/2 |
| explicit_due_date | 2/2 |
| derived_due_date | 2/2 |
| buyer_country | 1/2 |
| seller_country | 0/2 |
| trade_type | 0/2 |

기존 core 계산 기준의 required date, 전체 due-date 표현, 통화와 금액은 두 사례 모두
label과 일치했습니다. 분할금액은 4/4, installment 합계는 2/2, 선지급 식별은
2/2가 일치했습니다.

## Abstention과 추측

- 문서에 없는 통화 추측: 0
- 문서에 없는 날짜 추측: 0
- 문서에 없는 금액 추측: 0
- false-positive field: 0
- 적용 가능한 null field abstention: 8/8
- 사건 기준일 미확정 사례: 이번 2건에는 없어 평가 불가
- manifest상 차단 사례: 이번 2건에는 없어 평가 불가

따라서 이 run은 통화 누락을 USD로 보정하는지, 가려진 due date를 만드는지,
B/L·final acceptance 조건을 날짜로 만드는지는 아직 검증하지 않았습니다.

## Evidence와 사용자 확인

| 항목 | 결과 |
| --- | ---: |
| 자동으로 수용된 핵심 evidence coverage | 0% |
| 자동으로 수용된 evidence field-link consistency | 0% |
| 수용 evidence가 없는 확정값 | 10 |
| 수용 source_text가 없는 확정값 | 10 |
| 이미지 evidence 안전 차단 | 2/2 |

저장된 Live prediction은 raw model response가 아니라 결정론 validator를 통과한
normalized extraction입니다. 두 문서 모두 독립 OCR text layer가 없으므로 모델이
제시한 인용을 자동 신뢰하지 않고 제거했으며 `OCR_REQUIRED`,
`EVIDENCE_UNVERIFIABLE`, `MISSING_CORE_EVIDENCE`로 Stage 2를 차단했습니다.
따라서 evidence 0%는 OCR 실패율이 아니라 “자동 검증된 evidence가 없음”을
뜻합니다. 사람이 원문을 field별로 확인해야 합니다.

## 사례별 오류

### `us_import_split_scan_001`

- 성공: 문서유형, USD 120,000, 계약일, 30/70 금액·결제일
- seller country: label `US`, 결과 `United States (US)`
- buyer country: label `KR`, 결과 `Republic of Korea (KR)`
- trade type: label `IMPORT`, 결과 `UNKNOWN`
- 결과: `needs_human_review=true`, Stage 2 차단
- 안전 issue:
  `EVIDENCE_UNVERIFIABLE`, `MISSING_CORE_EVIDENCE`,
  `MISSING_REQUIRED_FIELD`, `OCR_REQUIRED`, `UNKNOWN_COUNTRY_ALIAS`

### `br_import_advance_photo_002`

- 성공: 문서유형, USD 84,000, 계약일, 20/80 금액·결제일, 선지급 조건
- seller country: label `BR`, 결과 `Brazil`
- buyer country: label·결과 `KR`
- trade type: label `IMPORT`, 결과 `UNKNOWN`
- 결과: `needs_human_review=true`, Stage 2 차단
- 안전 issue:
  `EVIDENCE_UNVERIFIABLE`, `MISSING_CORE_EVIDENCE`,
  `MISSING_REQUIRED_FIELD`, `OCR_REQUIRED`, `UNKNOWN_COUNTRY_ALIAS`

두 사례 모두 자연어·괄호 포함 국가 표현이 canonical ISO alpha-2로 정규화되지 않아
거래방향을 확정하지 못했습니다. Baseline 결과를 수정하거나 덮어쓰지 않았습니다.

## Latency, token과 비용

| 사례 | latency | input tokens | output tokens | total |
| --- | ---: | ---: | ---: | ---: |
| `us_import_split_scan_001` | 9.58초 | 33,163 | 633 | 33,796 |
| `br_import_advance_photo_002` | 9.34초 | 44,460 | 621 | 45,081 |
| 합계·평균 | 평균 9.46초 | 77,623 | 1,254 | 78,877 |

실행 시점 공식 token 단가를 evaluator에 입력하지 않았으므로 추정 비용은
`UNKNOWN`입니다. 두 사례의 관측 token을 단순 확장하면 전체 8건은 문서 복잡도에
따라 크게 달라질 수 있으며, 비용 상한으로 간주할 수 없습니다.

## 전체 8건 실행 권고

API 오류와 timeout이 없고 latency가 안정적이어서 동일 prompt·model·baseline
정책으로 전체 8건을 실행해 누락된 수출·차단·통화 누락·사건 기준 사례를 측정하는
것을 권고합니다. 다만 다음 조건을 지켜야 합니다.

1. 사용자의 두 번째 명시적 비용 승인
2. 새 run ID 사용과 기존 2건 run 보존
3. prompt·model·국가 정규화 로직을 Baseline v1 전체 실행 전에 변경하지 않음
4. 예상 비용은 `UNKNOWN`이며 실행 후 실제 token만 기록

전체 8건 실행은 아직 승인받지 않았고 실행하지 않았습니다.

## 후속 개선 우선순위

1. Baseline v1 8건을 먼저 동결한 뒤, 괄호 포함 미국 표기와 브라질 국가 별칭의
   ISO 정규화를 별도 commit·별도 비교 run으로 검증
2. 통화 누락·가려진 날짜·B/L·final acceptance 사례의 abstention 확인
3. 이미지 evidence는 독립 OCR 또는 사람 확인 없이는 계속 fail closed 유지
4. 공식 단가를 실행 시점에 확인할 수 있을 때만 비용 산식 입력

추출 prompt나 model은 이 baseline 전에 변경하지 않았습니다.

## 주장 범위와 한계

말할 수 있는 내용:

- 합성 이미지형 문서 2건에서 OpenAI 구조화 호출이 모두 완료됐습니다.
- 통화·금액·분할 금액·결제일은 2건에서 label과 일치했습니다.
- 국가 canonicalization과 거래방향은 두 사례에서 실패했습니다.
- 독립 OCR evidence가 없어 두 사례 모두 사용자 확인 전 계산을 차단했습니다.
- 문서에 없는 통화·날짜·금액 추측은 이 2건에서 관측되지 않았습니다.

말할 수 없는 내용:

- 실제 고객문서, OCR 또는 전체 무역문서 정확도
- “AI 추출 성공률 100%” 또는 “문서 인식률 100%”
- 2건 결과의 통계적 일반화
- 국가 신용등급·상품 승인·실거래 자동화 성능
