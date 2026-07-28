# Live 추출 Benchmark Runbook

## 목적과 범위

이 절차는 `dataset/country_validation`의 미국·브라질 합성 무역문서 8건으로
OpenAI 문서 추출 경로의 제한된 baseline을 측정합니다. 실제 고객문서, 운영 품질
인증, OCR 일반 성능, 파인튜닝 효과를 평가하는 절차가 아닙니다.

대상 세트는 미국 4건·브라질 4건, 수입 4건·수출 4건, 이미지형 PDF 4건·JPG
사진 4건입니다. 8건 모두 `split=test`, `fine_tuning_eligible=false`,
`synthetic_document=true`, `real_customer_document=false`입니다. evaluator는 이
표시가 없거나 승인된 디렉터리 밖의 문서면 Live 실행을 차단합니다.

## Fixture와 Live의 차이

| 구분 | Fixture | Live |
| --- | --- | --- |
| 목적 | evaluator 로딩·정규화·지표·보고서 검증 | 실제 OpenAI 추출 baseline |
| API 호출 | 없음 | 있음 |
| 결과 분류 | `evaluation_mode=FIXTURE` | `evaluation_mode=LIVE` |
| 모델 정확도 주장 | 금지 | 실행한 합성 사례에 한해 제한적으로만 설명 |
| 저장 경로 | 추적되는 `predictions/fixture` | Git에서 제외된 run별 디렉터리 |
| 일반화 | 불가 | 불가 |

Fixture의 필드 일치율 100%는 label을 복사한 prediction을 다시 평가한 결과입니다.
AI 또는 OCR 정확도가 아닙니다. Live 결과도 8건 이하의 합성 세트이므로 실제
고객문서나 전체 무역문서 분포로 일반화할 수 없습니다.

## 환경 준비와 key 안전 규칙

Python 3.9 환경과 `requirements.txt` 의존성을 사용합니다. `.env`에는 key를 둘 수
있지만 파일 내용을 터미널, 로그, trace, 보고서에 출력하지 않습니다.

필수 설정:

```dotenv
OPENAI_API_KEY=
ENABLE_LIVE_DOCUMENT_EXTRACTION=true
OPENAI_MODEL=gpt-4o-mini
OPENAI_FALLBACK_MODEL=gpt-4o
OPENAI_TIMEOUT_SECONDS=60
```

evaluator는 `.env`를 조용히 로드하고 preflight에서 key의 존재 여부만
`true/false`로 표시합니다. key 값, Authorization header, 전체 prompt, 문서
바이너리, 전체 API payload와 raw model response는 기록하지 않습니다.

## API 없는 선행 검증

```bash
PYTHONPYCACHEPREFIX=/tmp/invoice_intake_pycache \
  python -m compileall -q app.py src scripts tests

python -m unittest discover -s tests -v

python scripts/evaluate_extraction.py \
  --mode offline \
  --manifest dataset/country_validation/manifest.jsonl \
  --predictions-dir dataset/country_validation/predictions/fixture \
  --reports-dir reports/country_validation

python scripts/run_regression.py
python scripts/verify.py
```

이 단계가 모두 통과하기 전에는 Live baseline을 실행하지 않습니다.

## 호출 없는 Live 준비 점검

아래 명령은 안전조건과 경로만 확인하고 API를 호출하거나 결과 디렉터리를 만들지
않습니다.

```bash
python scripts/evaluate_extraction.py \
  --mode live \
  --manifest dataset/country_validation/manifest.jsonl \
  --predictions-dir dataset/country_validation/predictions/live \
  --reports-dir reports/country_validation_live \
  --max-cases 2 \
  --confirm-live \
  --run-id baseline-v1-smoke-prepare \
  --baseline-version baseline-v1 \
  --prepare-only
```

성공 상태는 `READY_FOR_AUTHORIZED_LIVE_RUN`입니다.

## 최초 2건 Smoke Live

같은 세션에서 비용 발생 호출에 대한 사용자 승인을 받은 경우에만 실행합니다.
`RUN_ID`는 재사용하지 않습니다.

```bash
python scripts/evaluate_extraction.py \
  --mode live \
  --manifest dataset/country_validation/manifest.jsonl \
  --predictions-dir dataset/country_validation/predictions/live \
  --reports-dir reports/country_validation_live \
  --max-cases 2 \
  --confirm-live \
  --run-id baseline-v1-smoke-YYYYMMDD-HHMM \
  --baseline-version baseline-v1
```

evaluator는 다음 run별 경로를 만듭니다.

```text
dataset/country_validation/predictions/live/<run-id>/
reports/country_validation_live/<run-id>/
```

동일한 run ID 또는 기존 디렉터리는 덮어쓰지 않습니다. Live 파일에는 검증된
구조화 extraction과 안전한 metadata만 저장하며 raw extraction/API response는
저장하지 않습니다.

## 전체 8건 Live

2건 결과를 검토한 뒤 전체 실행에 대한 두 번째 사용자 승인을 받은 경우에만
실행합니다.

```bash
python scripts/evaluate_extraction.py \
  --mode live \
  --manifest dataset/country_validation/manifest.jsonl \
  --predictions-dir dataset/country_validation/predictions/live \
  --reports-dir reports/country_validation_live \
  --max-cases 8 \
  --confirm-live \
  --run-id baseline-v1-full-YYYYMMDD-HHMM \
  --baseline-version baseline-v1
```

2건 승인은 8건 승인으로 간주하지 않습니다.

## Baseline 동결과 재현 metadata

API 호출 전에 `run_metadata.json`을 `RUNNING` 상태로 먼저 기록하고, 완료·부분실패·
중단 상태로 갱신합니다. 포함 항목은 다음과 같습니다.

- Git HEAD SHA와 tracked worktree dirty 여부
- timezone 포함 시작·완료 시각과 Python 버전
- evaluator version/hash
- extraction prompt version/hash
- 요청 model, fallback model, 실제 사용 model
- manifest 경로/hash와 전체·선택·실행 건수
- 성공·실패·timeout 건수
- run ID, baseline version, 출력 경로
- 합성 데이터·실고객문서 미사용·통계 일반화 금지 표시

API key, `.env` 내용, 문서 바이너리, 전체 prompt, Authorization header, 전체 raw
payload·response는 포함하지 않습니다. 첫 결과가 나쁜 경우에도 같은 run을 지우거나
덮어쓰지 않습니다. prompt·model 개선은 별도 commit과 새 run ID로 분리합니다.

## 지표와 결과 해석

`eval_summary.json`과 `eval_report.md`에는 다음이 포함됩니다.

- 통화·금액·명시/파생 날짜·거래방향·회사역할·당사국·문서유형 정확도
- 분할 금액·합계, 선지급 식별, 사건 기준 조건 보존, null abstention
- 문서에 없는 통화·날짜·금액 추측과 false-positive 수
- 사용자 확인·차단 사례 식별
- 핵심 evidence coverage, field 연결, evidence/source_text 없는 확정값
- 이미지 문서를 독립 검증된 OCR로 오인하지 않는지
- 성공·실패·timeout, 사례별/평균 latency, token usage
- 확인된 token 단가를 입력한 경우에만 추정 비용, 아니면 `UNKNOWN`
- PDF/JPG, 미국/브라질, 수입/수출, 정상/차단, 날짜·통화 유형별 breakdown

API timeout 또는 오류 사례는 안전한 실패 record로 남고 성공 건수에 포함되지
않습니다. 문서가 의도대로 `UNKNOWN`을 유지해 자동 document PASS가 실패하는
경우와 API 실행 실패는 서로 다른 지표입니다.

## 비용과 개인정보

가격은 바뀔 수 있으므로 저장소가 임의의 token 단가를 기본값으로 사용하지
않습니다. 실행 시점의 공식 단가를 사람이 확인한 경우에만
`--input-cost-per-million`, `--output-cost-per-million`을 함께 전달합니다. 그렇지
않으면 비용은 `UNKNOWN`입니다.

이 절차에는 실제 고객·회사 문서, 계좌, 주소, 식별번호, 서명·도장을 추가하지
않습니다. 테스트셋과 Live prediction은 파인튜닝 후보로 사용하지 않습니다.

## 실패 복구

- key 없음: 설정을 확인하고 `--prepare-only`를 다시 실행합니다.
- timeout/API 오류: 기존 run은 보존하고 원인을 기록한 뒤 새 run ID로 재시도합니다.
- 일부 실패: exit code 1과 `COMPLETED_WITH_FAILURES`를 유지하며 성공으로 발표하지
  않습니다.
- 중단: `INTERRUPTED` metadata를 보존하고 새 run ID를 사용합니다.
- 기존 run ID 충돌: 파일을 삭제하지 말고 새 run ID를 정합니다.
- fixture 경로 지정: 호출 전 차단되므로 Live 전용 root로 수정합니다.

## 절대 해서는 안 되는 주장

- fixture 또는 Live 8건을 근거로 AI·OCR·실제 고객문서 정확도 100%라고 말하지 않음
- 8건 결과를 전체 무역문서 성능으로 일반화하지 않음
- 이미지 evidence를 독립 검증된 OCR 근거라고 말하지 않음
- 국가·무역환경 결과를 금융기관 공식 신용등급·승인 예측이라고 말하지 않음
- LLM 추출값이 사용자 확인 없이 계산에 전달된다고 말하지 않음
- 은행 내부 시스템 연동, 실거래 실행, 상품 가입 가능성을 보장하지 않음
