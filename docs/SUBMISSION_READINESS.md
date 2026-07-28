# Submission Readiness

상태: `LIVE_SMOKE_2_COMPLETED_AWAITING_FULL_RUN_APPROVAL`

이 문서는 제출 직전 사실 확인표입니다. Live 결과가 없을 때 실제 AI 정확도 수치를
작성하지 않습니다.

## 기준 상태

- 기준 기능 commit: `0a53847549683059e533b0fdf7b1496596dc897f`
- 기준 기능 branch: `feature/t4-country-risk`
- benchmark 작업 branch: `feature/submission-benchmark-evidence`
- benchmark evidence commit: 이 문서를 포함한 branch tip이며, 정확한 SHA는 최종 전달 보고에 기록
- Python: 3.9 호환
- Stage 1 팀 JSON/REST adapter: 유지
- 실제 고객문서 사용: 없음

## 구현 완료 기능

- T1 팀 Stage 1 연결과 별도 Spot provenance
- T2 거래·결제 입력과 사용자 확인
- T3 결정론 결제·회수 위험
- T4 미국·브라질 국가·무역환경 검토
- T5 위험에서 금융 대응 mapping
- T6 공식 후보 shortlist
- T7 검증된 최종 보고서와 결정론 fallback
- 문서 추출값의 Pydantic·evidence·결정론 검증·사용자 확인 gate
- guarded Live evaluator와 fixture/Live 분리

T1~T7, Stage 1 모델, Stage 2 현금흐름과 Stage 3 환헤지 계산은 P1-A에서
변경하지 않습니다.

## T4 공식 snapshot 재현성

- snapshot version: `2026.07.29-v1`
- dataset ID: `country-environment-2026-07-29`
- content hash:
  `095c5e38a88403449214ba899e05d07831f1b2a44932f2ebe2beaa65045fb757`
- 공식 축: OECD, World Bank, WTO를 별도 유지
- 미국 OECD: `HIGH_INCOME_OECD_UNCLASSIFIED`, raw `null`
- 브라질 OECD: 공식 raw classification `4`를 원값으로만 유지
- 출력: 국가 신용등급이 아닌 거래 검토 우선도

동일 거래에서 국가만 바꿔도 Stage 1, Stage 2, Stage 3, runtime Stage 4와 상품
eligibility·approval은 바뀌지 않습니다. 국가 신호는 보험·보증·신용장·결제조건
상담 우선순위에만 반영됩니다.

## 검증 상태

| 항목 | 현재 상태 | 근거 |
| --- | --- | --- |
| 전체 API-free suite | 394/394 PASS | `python -m unittest discover -s tests -v` |
| release gate | PASS | `python scripts/verify.py` |
| 기존 regression | PASS | `python scripts/run_regression.py` |
| country fixture | 8건 실행, evaluator pipeline 검증 | `reports/country_validation/eval_summary.json` |
| fixture 모델 정확도 주장 | 금지 | `evaluation_mode=FIXTURE`, `model_accuracy_claim_allowed=false` |
| Live synthetic smoke | 2건 실행, API 성공 2·실패 0 | `docs/LIVE_BENCHMARK_RESULTS.md` |
| 전체 8건 Live | 미실행 | 두 번째 명시적 승인 필요 |
| 실제 고객문서 benchmark | 미실행·범위 밖 | 개인정보·동의·운영통제 필요 |

Fixture의 통화·금액·날짜 등 100% 일치는 label 복사 prediction으로 evaluator를
검증한 수치입니다. 의도적으로 정보가 부족한 4·6·7·8번 때문에 자동 document
PASS는 4/8입니다. 이 값은 AI/OCR 정확도가 아닙니다.

## Live 상태

- 상태: `LIVE_SMOKE_2_COMPLETED_AWAITING_FULL_RUN_APPROVAL`
- run ID: `baseline-v1-smoke-20260729-0341-kst`
- 모델: `gpt-4o-mini`
- 실행한 Live case 수: 2
- API 성공·실패·timeout: 2·0·0
- 자동 document PASS: 0/2
- Stage 2 전달 허용: 0/2
- 핵심 결과: 통화·금액·문서유형·회사역할·날짜 2/2, seller country 0/2,
  buyer country 1/2, trade type 0/2
- 독립 검증 evidence: 0%; 두 이미지 문서 모두 안전하게 사용자 확인 요구
- latency: 사례별 9.58초·9.34초, 평균 9.46초
- token usage: input 77,623, output 1,254, total 78,877
- 비용: `UNKNOWN`
- 준비된 안전 게이트: `--confirm-live`, 양수 `--max-cases`, 고유 `--run-id`
- 전체 8건: 2건 결과 보고 뒤 별도 승인 필요
- raw Live 결과와 보고서: Git 제외

실행 절차는 [LIVE_BENCHMARK_RUNBOOK.md](LIVE_BENCHMARK_RUNBOOK.md)를 따릅니다.
실제 결과와 한계는 [LIVE_BENCHMARK_RESULTS.md](LIVE_BENCHMARK_RESULTS.md)에
기록했습니다. Fixture 100%와 이 Live 수치를 섞지 않습니다.

## 심사위원에게 말할 수 있는 주장

- 합성 미국·브라질 무역문서 8건과 정답 label로 평가 파이프라인을 검증했습니다.
- fixture 평가와 실제 OpenAI Live 평가를 metadata·경로·주장 범위로 분리합니다.
- 사건 기준 결제조건은 기준 사건일이 없으면 확정 날짜로 임의 변환하지 않습니다.
- 문서에 없는 통화는 USD로 추측하지 않고 `UNKNOWN/null`을 유지합니다.
- LLM 추출값은 사용자 확인과 결정론 검증 전에 금융 계산으로 전달하지 않습니다.
- 국가환경 분석은 versioned 공식 snapshot을 사용하며 OECD·World Bank·WTO를
  단일 국가 신용점수로 합치지 않습니다.
- 금융 숫자는 `Decimal` 일반 코드가 계산하므로 같은 입력과 규칙은 같은 결과를
  만듭니다.

## 말하면 안 되는 주장

- 실제 고객문서, AI 추출 또는 OCR 정확도 100%
- 8건 결과를 전체 무역문서에 일반화
- 금융기관 공식 국가·기업 신용등급, 부도확률, 대출·보험 승인 예측
- 모든 국가의 실시간 국가위험 분석
- 실거래·헤지 주문·상품 가입·은행 내부 시스템 연동 완료
- 실제 상품 가입 가능성·가격·한도 보장

## 확인된 한계

- 합성 8건은 실제 언어·레이아웃·스캔 품질 분포를 대표하지 않습니다.
- 이미지형 PDF/JPG에는 독립 OCR ground-truth verifier가 없습니다.
- vision evidence는 사용자 원문 대조 전 자동 검증된 근거가 아닙니다.
- 실제 고객문서 처리에는 동의·보존/삭제 정책, 인증·tenant 분리, secret manager,
  malware 검사, sandboxed rendering, rate limit과 중앙 감사가 필요합니다.
- Live token 비용은 실행 시점 공식 단가를 확인하지 않으면 `UNKNOWN`입니다.

## 데모 전 확인

```bash
python scripts/verify.py

python scripts/evaluate_extraction.py \
  --mode offline \
  --manifest dataset/country_validation/manifest.jsonl \
  --predictions-dir dataset/country_validation/predictions/fixture \
  --reports-dir reports/country_validation

python scripts/run_regression.py
python scripts/run_decision_demo.py --company-role BUYER --format summary
python scripts/run_decision_demo.py --company-role SELLER --format summary
```

## API 없는 Fallback 데모

OpenAI key, Stage 1 서버와 공식 web search가 없어도 다음을 보여줄 수 있습니다.

- 합성 fixture 문서와 사용자 확인 gate
- 팀 Stage 1 forecast fixture와 명시된 fixture spot
- 고정 스트레스 기반 Stage 2 `Decimal` 현금흐름
- 수입·수출 결제 위험과 금융 대응 mapping
- T4 versioned 국가환경 snapshot
- 공식 후보 offline snapshot
- 결정론 상담 패킷과 보고서 fallback

이 fallback을 Live 모델 품질 검증이라고 표현하지 않습니다.
