# Refactoring Report

감사·리팩터링 기준일: 2026-07-24  
검증 환경: macOS, Python 3.9.6

## 현재 시스템 판정

- 실제 구조: 역할별 클래스를 늘린 멀티에이전트가 아니라 Stage 함수와 외부 adapter를
  연결한 상태 기반 통제형 워크플로
- 실제 오케스트레이션: 변경 전에는 `app.py`와 `src/demo.py`가 Stage 1~5를 각각 직접
  호출했고, 변경 후에는 공통 `WorkflowOrchestrator`가 순서·게이트·fallback·trace를 관리
- 자율성: 완전 자율형이 아니라 사용자 확인과 결정론 검증을 선행 조건으로 하는
  Human-in-the-loop 방식

## 감사한 실제 실행 경로

- `app.py`: 존재, Streamlit session state와 Stage 0~5 UI
- `src/demo.py`: 존재, 현재는 application demo service 호환 wrapper
- `src/stage5/report_agent.py`: 존재
- `run_offline_demo`: `src/application/demo_service.py`
- `run_stage2`: `src/stage2/engine.py`
- `generate_strategy_candidates`: `src/stage3/optimizer.py`
- `search_offline_kb`: `src/stage4/local_kb.py`
- `generate_report`: `src/stage5/report_agent.py`
- critic/rewrite: `src/stage5/critic.py`, `report_agent.py`
- API key 분기: `src/config.py`, document adapter, report agent, Streamlit mode
- 확인 gate: `validators.py`, `src/document_intake/confirmation.py`,
  `src/workflow/gates.py`
- 테스트: `tests/`, API-free `unittest`

## 발견한 문제와 위험도

### 치명적

이번 감사 시점에 기존 금융 계산을 즉시 오염시키는 미해결 치명적 결함은 재현되지
않았다. 기존 confirmation gate와 `Decimal` Stage 2 테스트가 이미 동작했다.

### 높음

| 문제 | 위험 | 조치 |
|---|---|---|
| UI와 offline demo가 Stage 순서를 별도로 직접 구현 | 두 경로의 gate/fallback drift | 공통 orchestrator와 demo service 도입 |
| 공통 workflow state/result가 없음 | 실패·provider·fallback·종료 상태 추적 불가 | `WorkflowState`, generic `StageResult`, `StageStatus` 도입 |
| 상품 web 실패가 UI 오류에서 종료 | 전체 workflow의 안전한 degradation 불완전 | orchestrator에서 offline 공식 KB fallback |
| trace가 없음 | 한 case의 실행·근거·critic 재작성 감사 불가 | case ID와 payload-free `TraceEvent` 및 UI expander |
| Stage 1 REST URL에 outbound 경계가 없음 | 내부망·metadata endpoint 접근 가능성 | HTTPS/public IP 검증, exact host allowlist, redirect 차단과 명시적 local opt-in |

### 보통

| 문제 | 위험 | 조치 |
|---|---|---|
| critic 결과가 passed/issues만 제공 | 실패 원인과 수정 정책 자동 판독 어려움 | 점수, 수치·근거·추천 일관성, 금지 표현, 누락 섹션, 수정 지시 추가 |
| 보고서 결과에 재작성 횟수/fallback 사유 없음 | 실제 retry 동작 확인 어려움 | provider, revision count, fallback reason 추가 |
| RAG empty 상태의 LLM 상품 생성 방어가 prompt 중심 | 무근거 상품 문구 통과 가능 | LLM 호출 전 결정론 보고서 전환, prompt와 Stage 4 근거 critic 검사 |
| 공식 web cache에 TTL과 요청 재검증이 없음 | 오래되거나 다른 조건의 근거 재사용 가능 | 24시간 TTL, timezone timestamp, query/trade/domain 재검증과 원자적 저장 |
| Stage 2 form 배분이 `app.py`에 존재 | UI 없이 입력 조립 테스트 어려움 | application input service로 이동 |
| Stage 3 설명과 점수 코드가 한 파일 | 계산과 표시 설명 책임 혼합 | 설명 생성 함수를 별도 모듈로 이동 |
| Stage 3/4 출력 필드가 요구사항보다 축약됨 | UI와 보고서에서 제약·공식 확인 상태가 모호 | 손실한도·유동성·보유외화, 상품 조건·서류·한계 필드 보강 |

### 낮음

| 문제 | 위험 | 조치 |
|---|---|---|
| architecture 문서가 이전 직접 호출 구조를 설명 | 유지보수 오해 | root architecture와 Mermaid 갱신 |
| 테스트 수·실행 설명이 이전 상태 | 인계 오류 | README와 validation 문서 갱신 |
| `.git` 메타데이터 없음 | diff/commit/push 근거 생성 불가 | 파일·명령 근거로 인계하고 Git 작업 미수행 |

## 변경한 내용

### Workflow

- `src/workflow/result.py`: 공통 Stage status/result와 timing/provider/fallback 계약
- `src/workflow/state.py`: case 단위 typed state와 범주형 추출 신뢰 상태
- `src/workflow/gates.py`: confirmation 선행 조건을 독립 함수로 분리
- `src/workflow/trace.py`: 원문·금액 payload를 제외한 trace event
- `src/workflow/orchestrator.py`: Stage 순서, downstream 무효화, fallback, 종료 상태

### Application/UI

- `src/application/demo_service.py`: offline fixture를 공통 orchestrator로 실행
- `src/application/stage2_input_service.py`: UI의 자연상계·헤지·수수료 배분 입력 조립 이동
- `src/demo.py`: 기존 import 호환 wrapper
- `app.py`: Stage 직접 호출 제거, orchestrator 호출과 결과 렌더링 유지
- `src/ui/state.py`: 문서 signature 변경 시 workflow state도 폐기
- `src/ui/components.py`: Stage trace expander

### Stage 2~5

- `src/domain/stage2_models.py`, `src/stage2/exposure.py`, `src/stage2/engine.py`:
  총 자연상계 안에서 보유외화 사용과 기타 동일통화 상계를 분리하되 기존 합계·현금흐름
  계산은 유지
- `src/domain/stage3_models.py`: held FX ratio, 손실한도 초과, liquidity, limitations
- `src/stage3/explanations.py`: 자연어 설명을 점수 계산에서 분리
- `src/domain/product_models.py`, `src/stage4/`: 공식 확인·조건·서류·전략 연결·한계
- `src/domain/report_models.py`: 구조화 critic과 report 실행 메타데이터
- `src/stage5/critic.py`: 수치/근거/표현/섹션/상품 grounding 검사
- `src/stage5/report_agent.py`: critic 수정 지시 전달, 0/1 revision 정책, fallback 사유

### Test

- `tests/test_workflow.py`: standalone E2E, gate, Stage 1/product fallback, failure stop,
  trace privacy, 금액 전달, timing
- `tests/test_application_services.py`: UI 없는 Stage 2 입력·배분
- `tests/test_stage3_4_5.py`: 구조화 critic, 정확히 한 번 revision, API 실패,
  RAG empty 상품 생성 차단, 확장된 후보 계약
- `tests/test_security_eval_demo.py`: demo와 production workflow 동일성, trace UI,
  session invalidation

## 변경하지 않은 내용과 이유

- Stage 1 팀 JSON/REST schema: 팀 adapter 계약 유지 요구 때문에 변경하지 않았다.
- Stage 2 계산식·반올림·ledger: 기존 133개 기준선이 보호하고 있어 재작성하지 않았다.
- Stage 3 grid 점수와 상위 3개 선택: 계산 결과 변경 금지에 따라 유지했다.
- 공식 KB의 상품 사실: 새 상품이나 환율 자료를 생성하지 않고 기존 snapshot만 사용했다.
- Streamlit 탭·버튼·다운로드 흐름: 사용자 데모 흐름 보존을 위해 유지했다.
- document live 실패의 demo 자동 대체: 실제 문서를 다른 fixture로 바꾸는 오인 위험 때문에
  의도적으로 하지 않았다.

## 테스트 결과

기준선:

- `python -m unittest discover -s tests -v`: 133/133 PASS
- `python scripts/verify.py`: PASS

리팩터링 후 최종 suite:

- `python -m unittest discover -s tests -v`: 158/158 PASS
- API key 없는 offline E2E: `SUCCEEDED`, trace 6개, deterministic report, critic PASS
- `python -m pip check`: PASS
- Python 3.9 compile: PASS
- `python scripts/evaluate_extraction.py --mode offline`: 17건, document PASS 82.35%,
  hallucination 0.00%
- `python scripts/run_regression.py`: `REGRESSION PASSED`
- `python scripts/export_finetuning_candidates.py`: 후보 0, 테스트셋 포함 17건 제외
- `python scripts/verify.py`: `VERIFY PASSED`
- Streamlit `AppTest`: PASS
- 실제 Streamlit 서버 socket health check: PASS — `127.0.0.1:8765` 기동,
  `/_stcore/health` HTTP 200 및 `ok` 응답 확인 후 정상 종료

## 남은 기술부채

- `app.py`는 계산을 수행하지 않지만 입력 form과 렌더링 때문에 여전히 길다. 탭별 view
  함수 분리는 기능 회귀 위험을 고려해 이번 범위에서 강제하지 않았다.
- Stage 1 계약은 환율 시나리오 중심이라 변동성·경제 이벤트·뉴스·위험등급을 아직
  표현하지 않는다. 팀 계약 확장 없이는 임의 필드를 만들지 않았다.
- Stage 3 비용률과 잔여 위험계수는 검증된 시장가격이 아닌 명시된 데모 가정이다.
- offline KB는 snapshot이다. 공식 web cache에는 24시간 기본 TTL을 추가했지만
  source 자체의 최신성은 기관 확인이 필요하다.
- 실제 OpenAI 호출, 실제 공식 web search, Windows launcher는 자격정보/환경 부재로
  실행하지 않았다.
- 인증, 중앙 감사로그, malware scanner, egress proxy와 CI는 production 후속 범위다.
- import되지 않는 Finder식 중복 사본 `src/demo 2.py`, `src/stage5/critic 2.py`,
  `src/stage5/report_agent 2.py`, `docs/PROJECT_BRIEF 2.md`가 남아 있다. 참조가 없음을
  확인했지만 `.git` 복구 이력이 없어 자동 삭제하지 않았다.
- `.git` 디렉터리가 없어 logical commit과 push는 수행할 수 없다.

## 다음 우선순위

- P0: 승인된 실제 Stage 1 계약에 volatility/event/source 필드를 추가하고 adapter
  contract test로 합의
- P0: 실제 은행 quote와 기업 cashflow로 Stage 3 계수 검증
- P1: 탭별 Streamlit view 함수 분리와 manual journey AppTest 확대
- P1 완료: official web cache TTL/source freshness 정책과 Stage 1 endpoint
  outbound SSRF 경계
- P1: 인증·권한·중앙 trace sink와 민감정보 보존 정책
- P2: CI, Windows smoke test, live API 비용 제한 baseline
