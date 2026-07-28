# Submission Readiness

상태: `GOLDEN_LIVE_V1_EVIDENCE_BLOCKED_AWAITING_REVALIDATION`

## 기준 상태

- 작업 branch: `feature/submission-benchmark-evidence`
- 국가 canonicalization: `9bdffd91becca3fe8546d8a16186f0469cfdb948`
- V1/V2 제출 증거: `432678f`
- Golden text-layer 자료: `73e457f`, `e466912`
- Python: 3.9 호환
- 실제 고객문서 사용: 없음
- 승인된 Golden Live v1: API 성공 1건, evidence 검증 차단
- 이번 evidence 복구 작업의 OpenAI Live 호출: 없음
- Git push: 최종 사용자 지시 전 수행하지 않음

기존 T1~T7, T4, Stage 1 JSON/REST adapter, Stage 2 현금흐름, Stage 3 환헤지,
Stage 4 공식 후보, Stage 5 report/critic 정책과 extraction prompt/schema는
변경하지 않았습니다.

## Baseline v1/v2 제출 증거

| 항목 | Baseline v1 | Baseline v2 |
| --- | --- | --- |
| Run ID | `baseline-v1-full-20260729-0404-kst` | `baseline-v2-full-20260729-0443-kst` |
| Git SHA | `0a53847549683059e533b0fdf7b1496596dc897f` | `9bdffd91becca3fe8546d8a16186f0469cfdb948` |
| model | `gpt-4o-mini` | `gpt-4o-mini` |
| API 성공/실패/timeout | 8/0/0 | 8/0/0 |
| seller_country | 4/8 | 8/8 |
| buyer_country | 3/8 | 8/8 |
| trade_type | 2/8 | 8/8 |
| validation PASS·Stage 2 allowed | 0/8·0/8 | 0/8·0/8 |

공통 evaluator, prompt와 manifest hash는
`docs/LIVE_BENCHMARK_RESULTS.md`에 전체 값으로 기록했습니다. 국가·거래방향
세 항목만 canonicalization의 직접 효과로 주장합니다. `document_type`,
전체 document match, token, latency와 법인명 표현은 LLM 재호출 변동 가능성이 있어
인과 효과로 주장하지 않습니다.

스캔형 8건의 accepted evidence coverage 0%는 OCR 정확도 0%가 아닙니다. 독립
텍스트 레이어가 없어 모델 인용을 자동 수용하지 않았고 사용자 확인 전 Stage 2를
전부 차단한 fail-closed 결과입니다.

## T4 공식 snapshot 재현성

- snapshot version: `2026.07.29-v1`
- dataset ID: `country-environment-2026-07-29`
- content hash:
  `095c5e38a88403449214ba899e05d07831f1b2a44932f2ebe2beaa65045fb757`
- 공식 축: OECD, World Bank, WTO를 별도 유지
- 미국 OECD: `HIGH_INCOME_OECD_UNCLASSIFIED`, raw `null`
- 브라질 OECD: 공식 raw classification `4`
- 출력: 국가 신용등급이 아닌 거래 검토 우선도

국가 신호는 보험·보증·신용장·결제조건 상담 순서에만 반영하며 Stage 1,
Stage 2, Stage 3이나 상품 eligibility·approval을 변경하지 않습니다.

## Golden 메인 데모

- PDF: `dataset/golden_demo/golden_export_contract.pdf`
- expected extraction: `dataset/golden_demo/expected_extraction.json`
- 사용자·기업 입력: `dataset/golden_demo/demo_inputs.json`
- 생성기: `scripts/generate_golden_trade_demo.py`
- 테스트: `tests/test_golden_trade_demo.py`

Golden 계약서는 2페이지 영문 텍스트 PDF이며 모든 페이지에
`SYNTHETIC SAMPLE - NOT LEGALLY BINDING`을 표시합니다. 판매자 KR, 구매자 BR,
EXPORT, USD 100,000, 계약일 2026-07-29, 선적일 2026-08-05, 20/80 분할결제,
잔금일 2026-08-20과 Open Account/T/T를 포함합니다.

Expected data는 기존 `TradeDocumentExtraction` schema만 사용합니다. Schema에 없는
신용장·보증 계약 사실은 별도 document fact로, 거래처 관계·신용보험·기존 헤지·
현금·신용한도는 사용자 입력으로 분리했습니다.

Golden의 API-free 확인 결과:

- PDF byte 결정론: PASS
- 텍스트 레이어 2/2 페이지: PASS
- expected exact evidence 16개 페이지 대조: PASS
- `Republic of Korea (KR)→KR`, `Brazil (BR)→BR`: PASS
- trade type `EXPORT`: PASS
- USD 20,000 + USD 80,000 = USD 100,000: PASS
- 사용자 확인 후 `validation_pass=true`, `stage2_allowed=true`: PASS
- Stage 1 21거래일 종료 2026-08-25 안에 잔금일 2026-08-20: PASS
- Golden 전용 API-free tests: 14/14 PASS
- Text-PDF amount/date recovery tests: 18/18 PASS

Golden Live v1은 핵심값과 installment 합계가 expected와 일치했지만
`EVIDENCE_VALUE_MISMATCH:amount_due`,
`EVIDENCE_NOT_IN_SOURCE:explicit_due_date`로 `validation_pass=false`,
`stage2_allowed=false`였습니다. 복구 수정은 API-free로만 검증했으므로 수정 후
Live end-to-end 성공을 아직 주장하지 않습니다.

## 검증 상태

| 항목 | 상태 | 근거 |
| --- | --- | --- |
| compile | PASS | `PYTHONPYCACHEPREFIX=/tmp/invoice_intake_pycache python -m compileall -q app.py src scripts tests` |
| 전체 API-free suite | 436/436 PASS | `python -m unittest discover -s tests -v` |
| Golden 전용 | 14/14 PASS | `python -m unittest tests.test_golden_trade_demo -v` |
| country canonicalization | 8/8 PASS | `python -m unittest tests.test_country_canonicalization -v` |
| Stage 1~5 통합 회귀 | PASS | 전체 suite와 `python scripts/run_regression.py` |
| release gate | PASS | `python scripts/verify.py` |
| country fixture | 8건 evaluator pipeline 검증 | `reports/country_validation/eval_summary.json` |
| fixture 모델 정확도 주장 | 금지 | `evaluation_mode=FIXTURE` |
| V1/V2 합성 Live | 각 8건 완료 | `docs/LIVE_BENCHMARK_RESULTS.md` |
| Golden Live v1 | API 1건 성공, evidence 차단 | `docs/VALIDATION_REPORT.md` |
| 수정 후 Golden Live 재검증 | 미실행 | 별도 승인 필요 |
| 실제 고객문서 benchmark | 미실행·범위 밖 | 운영 개인정보 통제 필요 |

## 심사위원에게 말할 수 있는 주장

- 제한된 합성 8건을 동일 model/evaluator/prompt/manifest로 V1/V2 비교했습니다.
- 검증된 국가 canonicalization으로 seller/buyer 국가와 그에 따른 거래방향이
  개선됐습니다.
- 금액·통화·날짜·분할결제와 abstention 30/30, hallucination 0은 유지됐습니다.
- 독립 검증할 수 없는 스캔형 문서는 사용자 확인 전 금융 계산으로 보내지 않습니다.
- 텍스트 레이어 Golden 계약서의 expected evidence와 기존 도메인 입력·계산을
  API-free로 검증했습니다.
- Golden Live v1은 값이 맞아도 근거가 틀리면 Stage 2를 차단했습니다.
- OECD·World Bank·WTO는 자체 국가 신용점수로 합치지 않습니다.
- 같은 확인 입력과 규칙의 금융 계산은 `Decimal` 기반으로 결정론적입니다.

## 말하면 안 되는 주장

- 실제 고객문서, 전체 무역문서, AI 추출 또는 OCR 정확도 100%
- Fixture 또는 Golden expected data가 Live model 정확도라는 주장
- `document_type`·전체 match·latency 개선이 canonicalization 효과라는 주장
- Evidence 0%가 OCR 정확도 0%라는 주장
- 비용 상한이 실제 청구액이라는 주장
- 금융기관 공식 국가·기업 신용등급, 부도확률, 대출·보험 승인
- 모든 국가의 실시간 국가위험, 실거래·헤지 주문·은행 내부 연동 완료

## 확인된 한계

- 합성 8건은 운영 문서 분포로 일반화할 수 없습니다.
- 스캔형 평가문서에는 독립 OCR verifier가 없습니다.
- 한 사례에 contract date 하루 차이 오류가 남았습니다.
- Cached input token 미수집으로 Baseline 실제 API 비용은 `UNKNOWN`입니다.
- Golden Live v1은 단일 합성문서이며 evidence 차단 상태였습니다.
- 수정된 recovery의 Live end-to-end 결과는 아직 미검증입니다.
- 실제 배포에는 인증·tenant 분리, malware scan, sandbox rendering, 동의·보존·
  삭제, secret manager, rate limit, 중앙 감사와 은행 내부 계약이 필요합니다.

## 데모 전 확인

```bash
python scripts/generate_golden_trade_demo.py
python -m unittest tests.test_golden_trade_demo -v
python scripts/verify.py
python scripts/run_decision_demo.py --company-role SELLER --format summary
python -m streamlit run app.py
```

수정된 Golden Live를 사용하려면 별도 승인 후 현재 commit과 새 실행 식별값을
기록해 재검증하고, 실패하면 `docs/DEMO_SCRIPT_KO.md`의 API-free fallback을
사용합니다.

## API 없는 fallback

- Golden PDF와 expected exact evidence를 나란히 표시
- Golden test의 국가·evidence·Stage 2 결과 제시
- 앱에서는 기존 `수출기업 대표 데모`로 네 탭의 Stage 1~5 흐름 실행
- T4 versioned snapshot과 offline KB 후보 사용
- Stage 5는 결정론 report fallback 사용

이 fallback을 Golden Live 추출 또는 모델 정확도 검증이라고 표현하지 않습니다.
