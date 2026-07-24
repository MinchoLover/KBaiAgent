# 수출입 환율·현금흐름 리스크 Copilot

상업송장·국제매매계약서·구매주문서를 근거와 함께 구조화하고, 사용자가 핵심값을
확인한 뒤 환율 시나리오별 원화 현금흐름을 `Decimal`로 계산하는 로컬 Streamlit
MVP입니다. 헤지 전략과 금융상품은 확정 자문이 아닌 검토 후보로만 제시합니다.
완전 자율형 멀티에이전트가 아니라, 사용자 확인과 결정론 검증을 선행 조건으로 하는
상태 기반 통제형 워크플로입니다.

## 5분 실행

Python 3.9 환경에서 다음 명령을 실행합니다.

```bash
cd /Users/jeongminchan/Desktop/invoice_intake_mvp
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

브라우저에서 `http://localhost:8501`을 엽니다. API 키가 없어도 데모 모드와
`전체 오프라인 데모 실행`이 동작합니다.

- macOS: `chmod +x run_mac.command && ./run_mac.command`
- Windows: `run_windows.bat` 더블클릭
- 빠른 안내: [START_HERE.md](START_HERE.md)

## 실제 문서 추출

`.env`의 `OPENAI_API_KEY`를 채우고 앱에서 `실제 API 모드`를 선택합니다. 키는
서버 환경변수에서만 읽고 화면·로그에 출력하지 않습니다. 모델 접근 오류가 나면
계정에서 사용 가능한 vision 및 Structured Outputs 지원 모델로 `OPENAI_MODEL`과
`OPENAI_FALLBACK_MODEL`을 변경합니다.

OpenAI 연결은 한 adapter에 격리되어 있습니다. 공식 Python SDK의 Responses API
`responses.parse(..., text_format=TradeDocumentExtraction)`를 사용하고, 이미지에는
`input_image`, PDF에는 base64 `input_file`을 보냅니다. 기본 모델을 두 번 시도한 뒤
선택적 fallback 모델을 한 번 시도합니다. 참고:
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[File inputs](https://developers.openai.com/api/docs/guides/file-inputs),
[Images and vision](https://developers.openai.com/api/docs/guides/images-vision).

비용이 발생하는 한 건 smoke test:

```bash
python scripts/live_smoke_test.py samples/sample_invoice.png
```

## 앱 흐름

```text
0 문서 업로드·추출
→ 사용자 수정 및 통화·금액·결제일 확인 gate
→ 1 수동 스트레스 또는 외부 Stage 1
→ 2 환위험·날짜별 현금잔고 계산
→ 3 헤지 비율 후보 grid 탐색
→ 4 공식 출처 상품·제도 후보
→ 5 critic 검수 보고서 또는 결정론 fallback
→ case ID 기반 실행 trace
```

`STRESS`, `FORECAST`, `CALCULATION`, `EXPLICIT`, `DERIVED`, `INFERRED` 상태를
화면과 JSON에서 구분합니다. 모델 추출값은 확인 전 금융 계산에 들어가지 않습니다.

`src/workflow/orchestrator.py`가 순서, 확인 gate, 실패·fallback, 보고서 재작성 상한,
종료 상태를 관리합니다. `app.py`는 입력 수집과 결과 표시를 담당하고 금융 계산은
`src/stage2/`, 헤지 탐색은 `src/stage3/`에서 수행합니다. offline demo도 같은
orchestrator를 사용합니다.

- 상세 구조와 Mermaid: [ARCHITECTURE.md](ARCHITECTURE.md)
- 감사·변경·잔여 위험: [REFACTORING_REPORT.md](REFACTORING_REPORT.md)

## Stage 1 팀 연결

앱에서 JSON 업로드 또는 REST endpoint를 선택합니다. 최소 계약은 다음과 같습니다.

```json
{
  "schema_version": "1.0",
  "currency": "USD",
  "quote_convention": "KRW_PER_1_FC",
  "rate_unit_foreign_currency": "1",
  "as_of": "2026-07-23T09:00:00+09:00",
  "target_date": "2026-10-21",
  "kind": "FORECAST",
  "scenarios": [
    {"name": "LOW", "rate": "1330", "is_base": false, "probability": "0.20"},
    {"name": "BASE", "rate": "1400", "is_base": true, "probability": "0.60"},
    {"name": "HIGH", "rate": "1515", "is_base": false, "probability": "0.20"}
  ]
}
```

통화·기준일·base 개수·양수 환율·확률 합계를 검증합니다. `rate_unit_foreign_currency`
가 `100`이면 JPY 등 100통화 단위 표시를 내부 1통화 단위로 정규화합니다. endpoint
오류나 schema 오류가 나면 명시적으로 `MANUAL_FALLBACK` 스트레스로 전환합니다.
상세 계약은 [docs/STAGE1_CONTRACT.md](docs/STAGE1_CONTRACT.md)에 있습니다.

REST endpoint는 기본적으로 HTTPS와 public IP만 허용하고 URL userinfo, fragment,
redirect, 사설·loopback·link-local·예약 IP를 차단합니다. 운영 환경에서는 exact
hostname allowlist도 설정합니다.

```dotenv
STAGE1_ALLOWED_HOSTS=stage1.example.com
STAGE1_ALLOW_PRIVATE_ENDPOINTS=false
```

로컬 개발 서버가 꼭 필요할 때만 `STAGE1_ALLOW_PRIVATE_ENDPOINTS=true`와
`STAGE1_ALLOWED_HOSTS=localhost`를 함께 명시합니다.

공식 web 상품 검색이 실패하면 offline 공식 KB로 전환합니다. 공식 출처가 확인되지
않은 경우 candidates를 빈 배열로 유지하며 보고서 LLM이 상품을 새로 만들지 못하도록
prompt와 critic 양쪽에서 검사합니다. 검색 cache는 timezone 포함 생성시각과 24시간
기본 TTL을 검증하며, TTL은 `OFFICIAL_SEARCH_CACHE_TTL_HOURS`로 조정합니다.

## 데이터셋·평가

16건의 가상 합성 문서와 기존 샘플 참조 1건을 `dataset/manifest.jsonl`로 관리합니다.
모든 합성 문서 상단에는 `TEST DOCUMENT - NO LEGAL EFFECT`가 있습니다. 기존 샘플은
`dataset/documents/`로 복사하지 않고 원본 경로를 manifest에서 참조합니다.

```bash
python scripts/generate_synthetic_dataset.py
python scripts/evaluate_extraction.py --mode offline
python scripts/evaluate_extraction.py --mode live --max-cases 2
python scripts/run_regression.py
```

offline fixture는 평가 코드와 label 계약을 검사하며 실제 모델 품질 점수가 아닙니다.
live 결과가 실제 baseline입니다. 비용 단가는 CLI의
`--input-cost-per-million`, `--output-cost-per-million`으로 기록할 수 있습니다.

Few-shot 파일은 모델 파인튜닝 데이터가 아니라 각 요청에 참고 문맥으로 포함되는 정답
예시입니다. 현재 프로젝트는 파인튜닝하지 않습니다.

1. 먼저 baseline 평가를 수행합니다.
2. 프롬프트와 결정론 검증으로 해결되지 않는 반복 오류가 수치로 확인될 때만
   파인튜닝을 검토합니다.
3. 학습셋과 테스트셋을 분리합니다.
4. 테스트셋을 파인튜닝 데이터에 절대 포함하지 않습니다.
5. 사용자 확인, 모든 필수 evidence, 검증 PASS, 사람 승인을 모두 만족한 train 사례만
   후보로 내보냅니다.

```bash
python scripts/export_finetuning_candidates.py
# 호환 명령
python scripts/export_finetuning_dataset.py
```

이 명령은 job을 실행하지 않으며 `artifacts/fine_tuning_candidate.jsonl`과 제외 사유를
기록한 `artifacts/fine_tuning_excluded.jsonl`만 만듭니다.

## 품질 검사

```bash
PYTHONPYCACHEPREFIX=/tmp/invoice_intake_pycache \
  python -m compileall -q app.py src tests
python -m unittest discover -s tests -v
python scripts/evaluate_extraction.py --mode offline
python scripts/run_regression.py
python scripts/verify.py
```

현재 suite는 API 키 없이 158개 테스트를 실행합니다. 확인 전 Cashflow 차단, Stage 1
fallback, 상품 empty-state, critic 1회 재작성, report fallback, trace privacy,
Streamlit 없는 orchestrator 실행, REST SSRF 경계와 cache TTL을 포함합니다. 검증 근거와 실제 결과는
[docs/VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md), 알려진 한계는
[docs/LIMITATIONS.md](docs/LIMITATIONS.md)에 있습니다.

## 보안·범위

- PDF/PNG/JPG/JPEG, 기본 15MB 이하, PDF 20페이지 이하
- 확장자·브라우저 MIME·magic bytes·실제 이미지/PDF 파싱을 교차 검증
- archive·암호화/손상 PDF·위장 파일 거부
- 원문 전체와 API 키를 로그에 기록하지 않음
- 실제 업로드를 dataset에 자동 복사하지 않음
- 문서 안의 지시는 신뢰하지 않는 데이터로 취급
- 웹 검색은 공식 도메인 allowlist만 허용하고 기본값은 OFF
- Stage 1 REST는 기본적으로 HTTPS/public IP 및 선택적 exact host allowlist 적용
- 공식 검색 cache는 timezone 포함 생성시각과 TTL 검증

본 앱은 금융·법률·회계 자문, 상품 승인, 수익 또는 손실 회피를 보장하지 않습니다.
