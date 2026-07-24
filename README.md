# 수출입 금융 의사결정 지원 에이전트

## 1. 프로젝트 한 줄 설명

수출입 거래의 환율 위험을 기업의 실제 현금 문제로 변환하고, 필요한 금융 상담까지
연결하는 AI 에이전트입니다.

이 서비스의 핵심은 환율을 예측하는 것이 아니라, 환율 변화가 특정 기업의 실제
결제와 현금흐름에 미치는 영향을 계산하고 다음 금융 상담을 준비하게 하는 것입니다.

주 사용자는 수출입 기업의 재무·자금 담당자입니다. KB 담당자는 사용자가 공유한
상담 패킷을 검토하는 후속 사용자입니다.

## 2. 해결하려는 문제

수출입 계약의 통화·금액·결제일만 알아도 환산액은 계산할 수 있지만, 기업의 의사결정에
필요한 질문은 더 구체적입니다.

- 보유 외화와 기존 헤지를 제외하면 실제로 얼마가 환율에 노출되는가?
- 불리한 환율에서 결제액 또는 원화 수취액이 얼마나 달라지는가?
- 예정 매출·비용까지 반영했을 때 최소 운영자금을 지킬 수 있는가?
- 현금과 사용 가능한 대출한도를 모두 반영해도 지급 부족이 남는가?
- 은행 상담 전에 어떤 정보와 서류를 준비해야 하는가?

이 MVP는 이 질문을 하나의 재현 가능한 흐름으로 연결합니다.

## 3. 일반 환율 계산기와의 차이

```text
거래 문서 또는 샘플 거래
→ AI 추출 및 사용자 확인
→ 보유 현금·외화·예정 입출금 입력
→ 환율 스트레스 시나리오
→ 환노출·날짜별 현금흐름 결정론 계산
→ 구조화 위험 코드
→ 규칙 기반 금융 대응 후보
→ KB 상담 준비 패킷
```

`buffer_shortfall`은 결제 후 현금이 최소 운영자금 기준보다 모자란 금액이고,
`payment_gap`은 현금과 입력한 대출한도를 반영해도 남는 실제 자금 부족입니다.
두 값을 같은 의미로 사용하지 않습니다.

## 4. 핵심 사용자 흐름

1. PDF·PNG·JPG·JPEG 거래 문서를 업로드하거나 수입·수출 샘플을 선택합니다.
2. 거래 방향, 통화, 외화금액, 결제일을 원문과 대조해 사용자가 확인합니다.
3. 수동 스트레스 또는 기존 Stage 1 JSON/REST 시나리오를 연결합니다.
4. 현재 원화 현금, 최소 운영자금, 대출한도, 보유 외화, 기존 헤지와 예정 입출금을
   입력합니다.
5. 기존 Stage 2 엔진이 `Decimal`과 날짜순 ledger로 모든 금융 숫자를 계산합니다.
6. 규칙 엔진이 위험 원인과 검토할 상담 범주를 만듭니다.
7. JSON·Markdown KB 상담 준비 패킷을 내려받습니다.
8. 헤지 조합 시뮬레이션, 공식 자료 검색과 확장 보고서는 선택 단계로 실행합니다.

`src/workflow/orchestrator.py`가 사용자 확인 gate, Stage 순서, 실패·fallback과
payload 없는 실행 trace를 관리합니다. 상세 구조는 [ARCHITECTURE.md](ARCHITECTURE.md),
변경 및 감사 기록은 [REFACTORING_REPORT.md](REFACTORING_REPORT.md)에 있습니다.

## 5. AI가 맡는 역할

AI는 다음처럼 비정형 정보를 다루는 곳에만 사용합니다.

- `src/document_intake/openai_adapter.py`: 문서 이미지/PDF를
  `TradeDocumentExtraction` 구조로 추출
- `src/stage4/official_search.py`: 명시적으로 활성화한 경우 공식 도메인 자료 검색
- `src/stage5/report_agent.py`: 결정론 계산 JSON을 사용자가 읽기 쉬운 설명으로 변환

문서 추출은 OpenAI Responses Structured Outputs를 사용하지만 결과를 바로 계산에
전달하지 않습니다. Pydantic 검증, 결정론 규칙과 거래 방향·통화·금액·결제일의 사용자
확인이 모두 통과해야 Stage 2가 열립니다. 보고서 설명이 계산값과 다르면 critic 또는
결정론 템플릿으로 전환합니다.

## 6. 결정론적 계산 엔진이 맡는 역할

다음 값은 LLM이 아니라 `src/stage2/`의 Python 코드가 `Decimal`로 계산합니다.

- 총 외화 거래금액, 보유 외화 사용액, 자연상계, 기존 헤지, 열린 환노출
- 기준·스트레스 시나리오의 원화 지급액 또는 수취액
- 기준 대비 추가 비용 또는 원화 수취 감소
- 날짜별 현금 잔고, 최소 운영자금 부족, 실제 현금 적자
- 사용 가능한 대출한도 반영 후 지급 부족
- 입력한 손실한도 초과 여부

내부 환율 단위는 `KRW_PER_1_FC`입니다. JPY처럼 외부 입력이 100통화 단위인 경우
Stage 1 adapter가 1통화 단위로 정규화합니다. Stage 1 팀의 JSON/REST 계약은
[docs/STAGE1_CONTRACT.md](docs/STAGE1_CONTRACT.md)에 있습니다.

## 7. 금융 안전장치

- 스트레스 시나리오는 미래 환율의 확률 예측으로 표시하지 않습니다.
- 구체적인 상품 가입, 대출 승인, 적격성, 최적 헤지 비율과 주문 실행을 확정하지
  않습니다.
- 위험 판정은 LLM 자유생성이 아니라 계산 결과와 임계값 규칙에서 생성합니다.
- 공식 근거가 없는 KB 상품명·금리·한도·조건을 만들지 않습니다.
- 일반 상담 범주는 `REQUIRES_BANK_REVIEW`, `human_review_required=true`로 표시합니다.
- 업로드 원문, 실제 문서와 비밀값을 로그·dataset에 자동 저장하지 않습니다.
- 업로드 확장자, MIME, magic bytes, 파일 크기와 PDF 페이지 수를 검증합니다.
- Stage 1 REST는 기본적으로 HTTPS/public IP와 선택적 exact host allowlist를
  요구합니다.

모든 상담 패킷에는 다음 고지 의미가 포함됩니다.

> 본 결과는 금융상품 가입, 대출 승인 또는 헤지 실행을 결정하지 않습니다. 환율
> 시나리오는 미래 환율의 확정 예측이 아닙니다. 실제 이용 가능 여부와 조건은 KB를
> 포함한 거래은행 상담과 심사를 통해 확인해야 합니다.

## 8. 대표 수입·수출 데모

외부 API나 API 키 없이 두 대표 흐름을 실행할 수 있습니다.

```bash
python scripts/run_decision_demo.py --company-role BUYER --format summary
python scripts/run_decision_demo.py --company-role SELLER --format summary
python scripts/run_decision_demo.py --company-role BUYER --format markdown
```

수입기업 고정 사례:

- 수입대금 USD 100,000, 결제 사용 보유외화 USD 20,000
- 기준환율 1,400원, 상승 스트레스 1,470원(+5%)
- 열린 환노출 USD 80,000
- 기준 원화 필요액 112,000,000원
- 스트레스 원화 필요액 117,600,000원
- 추가 비용 5,600,000원
- 예정 운영비 3,000,000원 반영 후 현금 9,400,000원
- 최소 운영자금 부족 600,000원, 대출한도 반영 후 지급 부족 0원
- 판정: `LIQUIDITY_BUFFER_RISK`, `PAYMENT_CAPACITY_RISK` 아님

수출기업 고정 사례:

- 수출대금 USD 100,000, 기준환율 1,400원, 하락 스트레스 1,330원(-5%)
- 기준 원화 수취액 140,000,000원, 스트레스 수취액 133,000,000원
- 원화 수취 감소 7,000,000원
- 판정에 `FX_RECEIPT_RISK`가 포함되며 수입 비용 위험과 구분

Streamlit 왼쪽 메뉴의 `수입기업 대표 데모`, `수출기업 대표 데모`도 같은
orchestrator와 계산·상담 패킷 코드를 사용합니다.

## 9. 실행 방법

Python 3.9 환경에서 실행합니다. 데이터베이스와 Docker는 필요하지 않습니다.

```bash
git clone https://github.com/MinchoLover/KBaiAgent.git
cd KBaiAgent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

브라우저에서 `http://localhost:8501`을 엽니다. macOS는 `./run_mac.command`,
Windows는 `run_windows.bat`도 사용할 수 있습니다.

오프라인 데모에는 환경변수가 필요하지 않습니다. 실제 AI 문서 추출을 사용할 때만
로컬 `.env` 또는 실행 환경에 아래 값을 설정합니다.

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_FALLBACK_MODEL=gpt-4o
OPENAI_REPORT_MODEL=gpt-4o-mini
ENABLE_LIVE_DOCUMENT_EXTRACTION=true
ENABLE_OFFICIAL_WEB_SEARCH=false
STAGE1_MODE=manual
STAGE1_BASE_URL=
STAGE1_ALLOWED_HOSTS=
STAGE1_ALLOW_PRIVATE_ENDPOINTS=false
```

비용이 발생하는 실제 추출 smoke test는 외부 자격증명과 사용자 의도가 있을 때만
`python scripts/live_smoke_test.py samples/sample_invoice.png`로 실행합니다.

## 10. 테스트 방법

저장소의 표준 테스트 러너는 `unittest`입니다. `pytest`는 의존성에 없습니다.

```bash
PYTHONPYCACHEPREFIX=/tmp/invoice_intake_pycache \
  python -m compileall -q -x '(^|/)(\.venv|\.git|__pycache__)(/|$)' .
python -m unittest discover -s tests -v
python scripts/evaluate_extraction.py --mode offline
python scripts/run_regression.py
python scripts/verify.py
```

2026-07-24 기준 API 없이 184개 테스트가 통과합니다. 수입·수출 방향, 보유 외화와
기존 헤지 차감, 운영자금 부족과 지급 부족 분리, 음수 금액·비양수 환율 차단,
Stage 1 fallback, 위험 매핑, 패킷 숫자 일치, 사람 검토 필드, Streamlit 수입·수출
원클릭 E2E를 포함합니다.

오프라인 extraction 평가는 fixture와 label 계약 검사이며 실제 LLM 정확도 점수로
해석하면 안 됩니다. 테스트셋은 파인튜닝 후보에서 항상 제외합니다.

## 11. 현재 구현 상태

| 영역 | 상태 | 근거 |
| --- | --- | --- |
| 샘플 및 실제 문서 입력 | 완료 | `app.py`, `src/document_intake/` |
| AI 구조화 추출 | 완료, 실제 호출은 외부 자격증명 필요 | `openai_adapter.py` |
| 네 핵심값 사용자 확인 | 완료 | `confirmation.py`, `workflow/gates.py` |
| 수동 및 Stage 1 adapter | 완료 | `src/stage1/` |
| 환노출·현금흐름 계산 | 완료 | `src/stage2/` |
| 구조화 위험 분류 | 완료 | `src/consultation/risk_classifier.py` |
| 규칙 기반 상담 대응 | 완료 | `src/consultation/response_mapping.py` |
| JSON·Markdown 상담 패킷 | 완료 | `src/consultation/packet.py` |
| 수입·수출 오프라인 E2E | 완료 | `run_decision_support_demo`, 관련 테스트 |
| 헤지 조합 | 프로토타입 | 고정 비용 가정 기반 Stage 3 |
| 공식 금융상품 자료 | 부분 구현 | 로컬 공식 스냅샷, 선택적 web 검색 |
| LLM 설명 보고서 | 부분 구현 | API 없으면 결정론 fallback |
| 데이터베이스·인증·은행 내부 API | 미구현 | P0 비범위 |

구체적인 변경 전 상태와 구현 계획은
[CURRENT_STATE.md](docs/repositioning/CURRENT_STATE.md),
[IMPLEMENTATION_PLAN.md](docs/repositioning/IMPLEMENTATION_PLAN.md)에서 확인할 수
있습니다.

## 12. 미구현 기능과 향후 확장

다음 기능은 P0 수직 슬라이스와 무관하거나 금융·운영 위험이 커서 구현하지 않았습니다.

- 실시간 환율 예측, 뉴스 감성분석과 시나리오 확률 추정
- KB 내부 상품·심사·한도·금리 API 연동
- 자동 상품 적격성 판정, 자동 대출 승인, 자동 헤지 주문
- 다중 기업 tenant, 인증·권한, 상담 이력과 운영 데이터베이스
- 운영용 악성파일 검사, 비동기 작업 큐, 모니터링과 배포 인프라
- 실제 문서 live benchmark와 공식자료 최신성 운영 절차

한 달 MVP에서는 현재 수직 슬라이스의 실제 문서 검증, 데모 안정성, 설명과 계산 숫자
일치율을 먼저 높입니다. 팀 포지셔닝과 발표 흐름은
[TEAM_POSITIONING.md](docs/repositioning/TEAM_POSITIONING.md), 최종 구현 결과는
[FINAL_REPORT.md](docs/repositioning/FINAL_REPORT.md)에 기록합니다.
