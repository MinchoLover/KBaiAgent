# Submission Readiness

상태: `READY_API_FREE_WITH_GROUNDED_CONSULTATION_HANDOFF`

## 기준 상태

- 작업 branch: `feature/submission-benchmark-evidence`
- 국가 canonicalization: `9bdffd91becca3fe8546d8a16186f0469cfdb948`
- V1/V2 제출 증거: `432678f`
- Golden text-layer 자료: `73e457f`, `e466912`
- Python: 3.9 호환
- 실제 고객문서 사용: 없음
- 역사적 Golden Live v1: API 성공 1건, evidence 검증 차단
- source-grounded recovery 이후 승인된 Golden Live 1건:
  `validation_pass=true`, 사용자 확인 후 `stage2_allowed=true`
- 이번 상담 Top 3·handoff 작업의 OpenAI Live 호출: 없음
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

역사적 Golden Live v1은 핵심값과 installment 합계가 expected와 일치했지만
`EVIDENCE_VALUE_MISMATCH:amount_due`,
`EVIDENCE_NOT_IN_SOURCE:explicit_due_date`로 `validation_pass=false`,
`stage2_allowed=false`였습니다. 이후 source-grounded recovery가 적용된 상태의
승인된 Golden Live 1건에서 `validation_pass=true`와 사용자 확인 후
`stage2_allowed=true`를 확인했습니다. 이번 작업은 이 기록을 문서화했을 뿐
Live API를 다시 호출하지 않았습니다. 단일 합성문서 결과를 전체 문서 또는 실제
고객환경 성능으로 일반화하지 않습니다.

Golden 상담 결과는 같은 `ConsultationPacket` JSON에서 다음 순서로 생성됩니다.

1. 수출대금 회수 보호 상담
2. 환율 관리 상담
3. 운영자금 버퍼·수출대금 회수시점 상담

이는 승인·인수·대출 등급이 아니라 기존 위험 finding과 명시적 category tie-break를
사용한 검토 순서입니다. Top 3 밖 topic은 `기타 확인사항`에 유지됩니다.

## 검증 상태

| 항목 | 상태 | 근거 |
| --- | --- | --- |
| compile | PASS | `PYTHONPYCACHEPREFIX=/tmp/invoice_intake_pycache python -m compileall -q app.py src scripts tests` |
| 전체 API-free suite | 456/456 PASS | `python -m unittest discover -s tests -v` |
| Golden 전용 | 14/14 PASS | `python -m unittest tests.test_golden_trade_demo -v` |
| country canonicalization | 8/8 PASS | `python -m unittest tests.test_country_canonicalization -v` |
| Stage 1~5 통합 회귀 | PASS | 전체 suite와 `python scripts/run_regression.py` |
| release gate | PASS | `python scripts/verify.py` |
| country fixture | 8건 evaluator pipeline 검증 | `reports/country_validation/eval_summary.json` |
| fixture 모델 정확도 주장 | 금지 | `evaluation_mode=FIXTURE` |
| V1/V2 합성 Live | 각 8건 완료 | `docs/LIVE_BENCHMARK_RESULTS.md` |
| 역사적 Golden Live v1 | API 1건 성공, evidence 차단 | historical baseline |
| recovery 이후 Golden Live | 1건 validation PASS, 확인 후 Stage 2 허용 | 승인된 완료 기록; 이번 작업 재호출 없음 |
| Golden 상담 Top 3 | 회수 보호 → 환율 → 유동성 | `tests.test_consultation_priority` |
| 실제 고객문서 benchmark | 미실행·범위 밖 | 운영 개인정보 통제 필요 |

## 심사위원에게 말할 수 있는 주장

- 제한된 합성 8건을 동일 model/evaluator/prompt/manifest로 V1/V2 비교했습니다.
- 검증된 국가 canonicalization으로 seller/buyer 국가와 그에 따른 거래방향이
  개선됐습니다.
- 금액·통화·날짜·분할결제와 abstention 30/30, hallucination 0은 유지됐습니다.
- 독립 검증할 수 없는 스캔형 문서는 사용자 확인 전 금융 계산으로 보내지 않습니다.
- 텍스트 레이어 Golden 계약서의 expected evidence와 기존 도메인 입력·계산을
  API-free로 검증했습니다.
- 역사적 Golden Live v1은 값이 맞아도 근거가 틀리면 Stage 2를 차단했습니다.
- source-grounded recovery 이후 제한된 Golden Live 1건에서
  `validation_pass=true`, 확인 후 `stage2_allowed=true`를 확인했습니다.
- 상담 Top 3는 LLM이 생성·재정렬하지 않으며, UI·Markdown·Stage 5가 같은
  `ConsultationPacket` JSON의 rank와 숫자를 사용합니다.
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
- 역사적 Golden Live v1의 evidence 차단은 삭제하지 않고 과거 baseline으로
  보존합니다.
- recovery 이후 Golden Live 성공도 단일 합성문서 1건에 한정됩니다.
- 실제 KB 상담 예약·RM 전송·상품 자격·승인 연동은 구현하지 않았습니다.
- 실제 배포에는 인증·tenant 분리, malware scan, sandbox rendering, 동의·보존·
  삭제, secret manager, rate limit, 중앙 감사와 은행 내부 계약이 필요합니다.

## 데모 전 확인

```bash
shasum -a 256 dataset/golden_demo/golden_export_contract.pdf
python -m unittest tests.test_golden_trade_demo -v
python scripts/verify.py
python scripts/run_decision_demo.py --company-role SELLER --format summary
python -m streamlit run app.py
```

기대 Golden PDF SHA-256은
`5330a1a572488005f7b02cccfc7150fbaa8b38c84bb9290da1e0c6e1c3a0a91c`입니다.
제출 preflight에서는 generator로 Golden을 덮어쓰지 않습니다.

Live 재실행은 이번 제출 점검에 필요하지 않습니다. 추가로 실행하려면 별도 승인,
고유 실행 식별값, 합성문서 제한을 지키고 결과가 불안정하면
`docs/DEMO_SCRIPT_KO.md`의 API-free fallback을 사용합니다.

## API 없는 fallback

- Golden PDF와 expected exact evidence를 나란히 표시
- Golden test의 국가·evidence·Stage 2 결과 제시
- 앱에서는 기존 `수출기업 대표 데모`로 네 탭의 Stage 1~5 흐름 실행
- T4 versioned snapshot과 offline KB 후보 사용
- Stage 5는 결정론 report fallback 사용

이 fallback을 Golden Live 추출 또는 모델 정확도 검증이라고 표현하지 않습니다.
