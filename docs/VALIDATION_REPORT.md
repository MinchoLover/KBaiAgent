# Validation Report

검증일: 2026-07-24  
환경: macOS, Python 3.9.6, Streamlit 1.50.0, streamlit-pdf 1.0.8,
pandas 2.3.3, OpenAI SDK 2.47.0, Pydantic 2.13.4.

## 결과 요약

- Python 3.9 compile: PASS
- dependency check: PASS
- offline unit/integration tests: 158/158 PASS
- offline end-to-end Stage 0~5: PASS
- standalone WorkflowOrchestrator, confirmation gate, fallback, safe trace: PASS
- Streamlit AppTest: PASS
- 실제 Streamlit 서버와 `/_stcore/health`: PASS — HTTP 200, 응답 `ok`
- extraction fixture evaluation: 17건 실행
- prompt regression: PASS
- fine-tuning export gate: 후보 0, 제외 17 — 의도한 안전 결과
- official offline KB: 8개 공식 자료, 요청한 6개 상품군 포함
- Stage 1 outbound HTTPS/public IP/host allowlist tests: PASS
- official search fresh/stale cache TTL tests: PASS
- app import: PASS
- live OpenAI call: NOT RUN — API key 없음
- official web search live: NOT RUN — API key 없음, 기본 OFF

## 평가 결과

`dataset/predictions/fixture`는 label과 일치하는 evaluator 검증 fixture입니다.

- field exact/normalized: 100%
- currency: 100%
- amount exact/tolerance: 100%
- date: 100%
- required completion: 100%
- hallucination: 0%
- evidence coverage: 100%
- human review recall: 100%
- document PASS: 82.35% (14/17)

PASS하지 않은 3건은 의도한 안전 차단입니다.

- `invoice_missing_due_008`: 문서에 결제일/조건 없음
- `invoice_multi_currency_010`: 여러 통화 CRITICAL
- `invoice_due_conflict_016`: explicit due와 Net 30 계산 충돌 CRITICAL

이 수치는 실제 모델 품질이 아닙니다. 실제 baseline은 live mode로 생성해야 합니다.

## 실행한 명령

```bash
python scripts/generate_synthetic_dataset.py
python scripts/generate_demo_outputs.py
PYTHONPYCACHEPREFIX=/tmp/invoice_intake_compile_pycache \
  python -m compileall -q app.py src tests
python -m pip check
python -m unittest discover -s tests -v
python scripts/evaluate_extraction.py --mode offline
python scripts/run_regression.py
python scripts/export_finetuning_candidates.py
python scripts/verify.py
```

## 테스트가 고정한 핵심 위험

업로드 MIME/magic/page/size, schema serialization, amount/date/Net N, balance due,
installment 합, due 충돌, 다중통화, prompt injection, missing evidence, 역할 매핑,
confirmation gate, Stage 1 fallback/JPY/probability, 수입·수출 손실 방향, natural hedge
날짜, 기존 hedge cashflow, buffer/cash/credit 부족, Stage 3 비율, 비공식 URL 차단,
보고서 숫자와 JSON path의 실제 연관성, secret redaction, 상태 무효화, PDF 미리보기,
offline end-to-end를 포함합니다. 추가로 UI 없는 orchestrator, 확인 전 Cashflow
미호출, Stage 1·상품 검색 fallback, RAG empty 상품 생성 차단, critic 정확히 1회
재작성, report API fallback, trace payload 비포함을 고정합니다. 분할결제에서는
동일 통화 자연상계 잔여량과 기존
헤지 수수료가 여러 회차에 중복 적용되지 않는 것도 고정합니다. Stage 1 REST의
private/loopback/metadata IP 차단, exact host allowlist, 명시적 로컬 opt-in과 공식
검색 cache의 fresh hit·stale refresh도 포함합니다.

공식 KB는 선물환, 환변동보험, 외화예금, 수출입대출, 정책자금, 보증상품을 모두
포함합니다. 거래방향과 맞지 않는 상품은 ranking 단계에서 제외하고, 자격·한도·승인은
항상 `unknown` 또는 상담 필요 상태로 유지합니다.

## Live 실행

API 키 설정 후 비용이 발생하는 호출을 한 건으로 제한해 실행합니다.

```bash
python scripts/live_smoke_test.py samples/sample_invoice.png
python scripts/evaluate_extraction.py --mode live --max-cases 2
```

현재 계정에서 기본 모델을 사용할 수 없으면 `.env`의 모델 ID를 접근 가능한
vision/Structured Outputs 모델로 바꿉니다.

## 최종 인계

### 1. 감사에서 확인한 핵심 문제

- CRITICAL: 추출값이 통화·금액·결제일 확인 없이 계산으로 전달될 수 있었고, 문서·역할
  변경 뒤 session 결과가 섞일 수 있었습니다.
- HIGH: evidence·다중통화·날짜충돌 검증, 업로드 magic/parse 검사, Decimal 계산,
  기존 hedge와 자연상계의 분할결제 배분이 부족했습니다.
- MEDIUM: prompt version/few-shot, 정답셋·평가·회귀, 공식 출처 정책, 보고서 숫자
  추적성이 없거나 약했습니다.
- LOW: README와 지원 형식·제한이 달랐고 의존성 재현성이 부족했습니다.
- 저장소에 `.git` 디렉터리가 없어 branch/commit은 만들지 않았습니다.

### 2. 실제 구현 범위

Stage 0 strict extraction/검증/사람 확인, typed workflow orchestrator와 trace,
Stage 1 manual·JSON·REST adapter, Stage 2
Decimal exposure·ledger·복합 stress, Stage 3 top-3 후보, Stage 4 official KB와 선택적
allowlist web search, Stage 5 critic·fallback, 단일 Streamlit UI, 다운로드, dataset,
offline/live evaluator, regression과 fine-tuning export gate를 구현했습니다.

### 3. 핵심 파일

- 앱: `app.py`
- 스키마·검증: `schemas.py`, `validators.py`, `src/domain/`,
  `src/document_intake/`
- 계산·후속 단계: `src/stage1/`~`src/stage5/`
- 평가: `scripts/evaluate_extraction.py`, `scripts/run_regression.py`,
  `scripts/export_finetuning_candidates.py`, `scripts/verify.py`
- 문서: `README.md`, `START_HERE.md`, `docs/`

### 4. 실행 명령

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

API 키가 없으면 앱의 데모 모드와 전체 오프라인 데모를 사용합니다.

### 5. 테스트

Python 3.9 compile, dependency check, 158/158 API-free unit/integration tests,
`scripts/verify.py`, Streamlit AppTest가 모두 PASS했습니다. 또한
`127.0.0.1:8765`에서 headless Streamlit 서버를 기동해 `/_stcore/health`의 HTTP 200과
`ok` 응답을 확인한 뒤 정상 종료했습니다.

### 6. Offline 평가

17건에서 exact/normalized/currency/amount/date/evidence/review 지표 100%,
hallucination 0%, document PASS 82.35%입니다. 실패 3건은 누락 due·다중통화·due 충돌을
의도적으로 자동 차단한 사례입니다. fixture 점수는 live 모델 품질 점수가 아닙니다.

### 7. Live API

API 키가 없어 실행하지 않았습니다. adapter의 이미지 `input_image`, PDF `input_file`,
Structured Output parse, retry/fallback 경로는 mock과 설치 SDK signature로
검증했습니다.

### 8. 남은 한계

실문서 OCR baseline, 실제 공식 web search, Windows launcher, production 인증·malware
scan과 egress proxy 수준 DNS rebinding 방어는 현재 환경에서 검증하지 못했습니다.
Stage 3 비용·위험계수와 Stage 4 자격 조건은 상담 전제의 데모 가정입니다.

### 9. Stage 1 연결 계약

`schema_version=1.0`, 거래 통화, `KRW_PER_1_FC`, 환율 표시 단위, as-of, target date,
`FORECAST` 또는 `STRESS`, scenario 이름·환율·base 여부·선택적 probability를 JSON
파일이나 REST 응답으로 전달합니다. 전체 예시는 `docs/STAGE1_CONTRACT.md`와
`samples/stage1_scenarios.json`에 있습니다.

### 10. 다음 우선 작업

1. 고정 test split 1~2건으로 비용 제한 live baseline을 생성하고 raw/validated 실패를
   분리 분석합니다.
2. 실제 은행 quote·기업 cashflow 계약으로 Stage 2/3 가정과 비용계수를 보정합니다.
3. 공개 배포 전에 인증, malware scan, egress allowlist와 CI를 추가합니다.
