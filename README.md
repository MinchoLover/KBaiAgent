# 수출입 금융 의사결정 지원 에이전트

## 1. 프로젝트 한 줄 설명

수출입 거래의 환율 위험을 기업의 실제 현금 문제로 변환하고, 필요한 금융 상담까지
연결하는 AI 에이전트입니다.

> 이 서비스의 핵심은 환율을 예측하는 것이 아니라, 환율 변화가 특정 기업의 실제
> 결제와 현금흐름에 미치는 영향을 계산하고 다음 금융 상담을 준비하게 하는 것입니다.

주 사용자는 수출입 기업의 재무·자금 담당자이고, KB 담당자는 사용자가 공유한 상담
패킷을 검토하는 후속 사용자입니다.

## 2. 해결하려는 문제

환율 계산기만으로는 다음 질문에 답하기 어렵습니다.

- 보유 외화·확정 외화 유입·기존 헤지를 빼면 실제 열린 노출은 얼마인가?
- 불리한 환율에서 지급액 또는 원화 수취액은 얼마나 변하는가?
- 예정 매출·비용 뒤에도 최소 운영자금을 지키는가?
- 현금과 대출한도를 반영해도 실제 지급 부족이 남는가?
- 어떤 대응을 검토하고 은행 상담에 무엇을 준비해야 하는가?

## 3. 일반 환율 계산기와의 차이

```text
거래 문서 또는 샘플
→ AI 구조화 추출
→ 규칙 검증과 사용자 확인
→ 팀 Stage 1 시장모델 + 별도 Spot
→ 모델 경로위험 / 고정 스트레스 분리
→ Decimal 환노출·날짜별 현금흐름
→ 구조화 위험 코드
→ 제약 기반 헤지 시뮬레이션 후보
→ 공식자료 후보
→ KB 상담 패킷과 검증된 보고서
```

`buffer_shortfall`은 최소 운영자금 기준 부족이고, `actual_cash_deficit`은 음수
현금잔고, `post_credit_deficit`은 대출한도 뒤에도 남는 실제 부족입니다.

## 4. 핵심 사용자 흐름

1. PDF·PNG·JPG/JPEG 거래 문서를 올리거나 수입·수출 샘플을 선택합니다.
2. 국가명을 ISO 코드로 정규화하고 회사 역할·거래 방향·통화·금액·결제일을
   원문 evidence와 대조해 확인합니다.
3. `위험 진단`에서 확인된 기준환율과 회사 현금·최소운영자금·신용한도를 입력합니다.
4. 불리한 환율에서의 추가 부담, 최저 현금잔고와 신용한도 사용 후 부족을 확인합니다.
5. `대응안 비교`에서 안정성·균형·비용 관점의 계산상 후보와 선택적 공식자료를 봅니다.
6. `상담자료`에서 은행에 확인할 질문과 준비서류가 포함된 Markdown을 내려받습니다.

내부 Stage 1 provider, 21거래일 모델 결과, 전체 계산표, JSON과 실행 trace는 삭제하지
않고 각 화면의 접힌 상세 영역에서 확인할 수 있습니다.

결제일이 모델의 21거래일 범위 밖이면 `HORIZON_MISMATCH`가 발생합니다. 이때
Stage 1은 초기 21일 시장 문맥으로만 표시하고 전체 결제기간 숫자는 고정
스트레스로만 계산합니다.

## 5. AI가 맡는 역할

- `src/document_intake/openai_adapter.py`: 비정형 문서를 구조화
- 별도 `kb_macro_ai`: USD/KRW 방향·경로위험 모델
- `src/stage4/official_search.py`: 활성화한 경우 공식 도메인 자료 검색
- `src/stage5/report_agent.py`: 이미 계산된 JSON을 자연어로 설명

AI 추출값은 Pydantic·결정론 규칙·사용자 확인 전에는 계산에 전달하지 않습니다.
`United States`, `Republic of Korea` 같은 자연어 국가는 검증 전에 `US`, `KR`로
정규화하고 원본과 변경 이력을 audit에 보존합니다. 금액 원문에 실제 통화 코드가
있을 때만 currency evidence를 안전하게 연결합니다.
당사자 이름·국가는 각각 정확한 field evidence와 현재 값의 원문 일치를 요구합니다.
텍스트 PDF는 메모리 안에서 인용문이 실제 페이지에 있는지와 당사자·통화·금액·날짜·
지급조건 값이 일치하는지를 결정론적으로 대조합니다. 이미지·스캔 문서는 독립 텍스트
원문이 없어 `OCR_REQUIRED`와 field-level 사용자 확인 전 계산을 차단합니다. 사용자가
값을 수정하면 이전 evidence를 자동 폐기한 뒤 전체 검증을 다시 실행합니다.
Stage 1 v25 방향 점수는 시장 문맥 전용이며
`probability_calibrated=false`이면 실제 발생확률이나 기대손실 가중치가 아닙니다.
뉴스는 가격 예측 입력이 아니고 금융 숫자를 변경하지 않습니다.

## 6. 결정론적 계산 엔진이 맡는 역할

`src/stage2/`는 `Decimal`과 날짜순 ledger로 다음을 계산합니다.

- 보유 외화·동일통화 확정 흐름·기존 헤지와 열린 환노출
- 기준/모델 분위수/고정 스트레스의 원화 지급 또는 수취
- 수입 추가비용, 수출 원화 수취 감소
- 날짜별 잔고, 최초·최대 운영자금 부족, 현금 적자, 신용 후 실제 부족
- 손실한도 초과와 모든 숫자의 source path

내부 환율은 항상 외화 1단위당 원화입니다. JPY(100) 고시는 provider에서
`KRW_PER_1_JPY`로 정규화합니다. 유리한 시나리오는 음수 손실이 아니라
`loss_vs_base=0`, 방향값은 `signed_impact_vs_base`로 분리합니다.

## 7. 금융 안전장치

- q90을 90% 발생확률로 표현하지 않음
- 21거래일 모델을 90일 결제일로 외삽하지 않음
- Stage 1에 없는 spot을 임의 추정하지 않음
- 수동 spot은 사용자 확인 전 차단
- LLM이 환율·손실·잔고·부족·헤지비율을 계산하지 않음
- 헤지 결과는 `SIMULATED_CANDIDATE`, 해가 없으면 강제 추천하지 않음
- 상품 가입·대출 승인·보험 인수·헤지 주문·적격성을 확정하지 않음
- 출처·기준일 없는 상품을 최종 후보에서 제외
- 보고서 숫자와 JSON path 불일치, 확률/q90/horizon/news 오용 시 critic 차단
- API key가 없거나 critic이 실패하면 결정론 보고서

## 8. 대표 수입·수출 데모

외부 API 없이 팀 Stage 1 fixture와 fixture spot으로 실행합니다.

```bash
python scripts/run_decision_demo.py --company-role BUYER --format summary
python scripts/run_decision_demo.py --company-role SELLER --format summary
python scripts/run_decision_demo.py --company-role BUYER --format markdown
```

수입 대표값:

- 수입 USD 100,000, 결제용 보유 USD 20,000, 열린 노출 USD 80,000
- 기준 1,400원 필요액 112,000,000원
- +5% 1,470원 필요액 117,600,000원, 추가비용 5,600,000원
- 현재 현금 130,000,000원, 확정 유입 40,000,000원, 확정 비용 45,000,000원
- +5% 결제 후 7,400,000원, 최소 운영자금 부족 2,600,000원
- 현금은 양수이므로 실제 지급부족 0원

수출 데모는 환율 하락 → 원화 수취 감소 → 현금 위험의 반대 방향을 검증합니다.
두 사례의 결제일은 21거래일 밖이므로 모델 분위수는 시장 문맥으로만 보이고
결제 숫자는 고정 스트레스에서 나옵니다.

메인 발표용 텍스트 레이어 Golden 수출계약서는 별도로 생성합니다.

```bash
python scripts/generate_golden_trade_demo.py
python -m unittest tests.test_golden_trade_demo -v
```

`dataset/golden_demo/golden_export_contract.pdf`는 KR 판매자·BR 구매자,
USD 100,000, 20/80 분할결제와 2026-08-20 잔금일을 가진 합성 계약서입니다.
Expected evidence와 사용자 입력은 같은 디렉터리의 JSON에 있으며 Golden Live
추출은 별도 승인 전 실행하지 않습니다. 발표 순서는
[docs/DEMO_SCRIPT_KO.md](docs/DEMO_SCRIPT_KO.md)를 따릅니다.

## 9. 실행 방법

Python 3.9, Streamlit 단일 앱입니다. DB와 Docker는 필요하지 않습니다.

```bash
git clone https://github.com/MinchoLover/KBaiAgent.git
cd KBaiAgent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

팀 Stage 1 HTTP 연결:

```bash
curl --fail --silent http://127.0.0.1:8765/health
```

```dotenv
STAGE1_PROVIDER=http
STAGE1_BASE_URL=http://127.0.0.1:8765
STAGE1_FORECAST_FILE=src/integration_assets/stage1/latest_forecast.json
SPOT_RATE_PROVIDER=manual
MANUAL_USDKRW_RATE=1400
```

전체 변수는 `env.template`, 빠른 시작은 [START_HERE.md](START_HERE.md)를 봅니다.
팀 모델 연결은
[docs/STAGE1_INTEGRATION.md](docs/STAGE1_INTEGRATION.md), 환율 출처 설정은
[docs/SPOT_PROVIDER_SETUP.md](docs/SPOT_PROVIDER_SETUP.md)를 봅니다.
현재 순수 Streamlit 구조라 독립 REST endpoint 대신 typed 서비스 계층을
구현했습니다. API 분리는 인증·tenant 설계와 함께 후속 범위입니다.

## 10. 테스트 방법

```bash
PYTHONPYCACHEPREFIX=/tmp/invoice_intake_pycache \
  python -m compileall -q -x '(^|/)(\.venv|\.git|__pycache__)(/|$)' .
python -m unittest discover -s tests -v
python scripts/evaluate_extraction.py --mode offline
python scripts/run_regression.py
python scripts/verify.py
```

`python scripts/verify.py`가 compile, 전체 unittest, fixture E2E, README·schema·비밀
검사를 한 명령으로 실행합니다. 2026-07-29 기준 416개 테스트가 통과했습니다.
최신 실제 실행 결과는
[docs/VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md)에 기록합니다. fixture 평가는
live LLM 정확도가 아니며 테스트셋은 파인튜닝 후보에서 제외합니다.

미국·브라질 합성문서 Live 평가는 기본 비활성이고, 양수 사례 제한·명시적 확인·
고유 run ID가 모두 필요합니다. 실행·비용·주장 범위는
[docs/LIVE_BENCHMARK_RUNBOOK.md](docs/LIVE_BENCHMARK_RUNBOOK.md), 제출 전 사실
확인은 [docs/SUBMISSION_READINESS.md](docs/SUBMISSION_READINESS.md), 실행한
Baseline v1/v2 합성 8건씩의 결과는
[docs/LIVE_BENCHMARK_RESULTS.md](docs/LIVE_BENCHMARK_RESULTS.md)를 봅니다.

## 11. 현재 구현 상태

| 영역 | 상태 | 근거 |
| --- | --- | --- |
| 문서 인테이크·사용자 확인 | 완료 | 국가·날짜·evidence 정규화, 5필드 workflow gate |
| Stage 1 HTTP/file/mock | 완료 | `forecast_provider.py` |
| 제공 Stage 1 JSON 정규화 | 완료 | `web_forecast.py`, fixture tests |
| Spot 공식/수동/fixture | 완료 | `spot_rate.py`; live 공식 호출은 자격증명 필요 |
| 모델/고정 scenario·horizon | 완료 | `scenario_builder.py` |
| Decimal Stage 2 ledger | 완료 | `src/stage2/` |
| 위험 코드·상담 패킷 | 완료 | `src/consultation/` |
| Stage 3 제약 후보 | 프로토타입 | 실제 은행 가격 없이 명시적 가정 |
| 공식자료 검색 | 부분 구현 | 검증된 local snapshot, 선택적 web |
| 설명 보고서·critic | 완료 | API 없는 template fallback 포함 |
| 수입·수출 fixture E2E | 완료 | `run_integrated_decision_demo`, tests |
| Golden text-layer 발표자료 | 완료 | 결정론 PDF·expected evidence·14개 API-free tests |
| 인증·DB·독립 API·은행 내부연동 | 미구현 | 운영 확장 범위 |

구조는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), 기존 canonical 설명은
[ARCHITECTURE.md](ARCHITECTURE.md), 감사는
[docs/REPOSITORY_AUDIT.md](docs/REPOSITORY_AUDIT.md), 과거 리팩터링 내역은
[REFACTORING_REPORT.md](REFACTORING_REPORT.md)를 봅니다.

## 12. 미구현 기능과 향후 확장

- 42·63거래일 모델과 USD/KRW 외 통화 모델
- 실제 은행 forward quote·한도·회계·세무 반영
- KB 내부 상품·심사·대출 API
- 자동 적격성·승인·주문
- 사용자 인증·tenant 분리·중앙 감사로그·운영 DB
- malware scan, 비동기 queue, CI/CD와 production observability
- 허가된 실제 문서·live LLM·공식 환율 API 운영 benchmark

현재 한계는 [docs/LIMITATIONS.md](docs/LIMITATIONS.md), 팀 인계는
[docs/TEAM_HANDOFF_KO.md](docs/TEAM_HANDOFF_KO.md), 데모 대본은
[docs/DEMO_SCRIPT_KO.md](docs/DEMO_SCRIPT_KO.md)를 확인하세요.
