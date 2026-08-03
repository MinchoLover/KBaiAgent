# 최종 Diff 사람 검토용 보고서

감사일: 2026-08-03

## 요약

- tracked modified: 40개
- tracked diff: 8,551 additions / 913 deletions (6.5 시작 기준)
- 실제 untracked 파일: 51개
- staged: 0개
- 보호 자산 diff: 없음
- Stage1·Stage2·Stage3 소스 diff: 없음

변경량이 크고 여러 선행 회차가 하나의 dirty tree에 누적되어 있으므로, 테스트 PASS만으로
사람의 전체 diff 승인을 대체하지 않는다.

## Tracked modified 전체 목록

| 경로 | 변경 목적 | 구분 | Stage1~3 금융 계산 | Golden/보호자산 | 제출 권고 | 사람 검토 |
| --- | --- | --- | --- | --- | --- | --- |
| `.gitignore` | local·재생성 파일 제외 | REPOSITORY_HYGIENE | 없음 | 없음 | 별도 hygiene commit | YES |
| `AGENTS.md` | freeze·탐색 범위 고정 | REPOSITORY_HYGIENE | 없음 | 없음 | 별도 hygiene commit | YES |
| `README.md` | 최종 4탭·707 tests·책임 경계 | 문서 | 없음 | 없음 | 포함 | YES |
| `app.py` | 사용자 UI·조건 입력·stale 차단 | 코드/UI | 없음 | 값 불변 | 포함 | **필수** |
| `dataset/country_validation/README.md` | 합성 검증 자산 설명 | 문서 | 없음 | Golden 아님 | 포함 | YES |
| `dataset/country_validation/manifest.jsonl` | non-Golden 텍스트 PDF manifest | 데이터 | 없음 | Golden 아님 | 포함 | YES |
| `env.template` | optional feature flag 예시 | 설정 | 없음 | 없음 | 포함 | secret 없음 확인 |
| `knowledge_base/official_products.json` | 공식 catalogue metadata·신호 | catalogue | 없음 | Golden 순서 회귀 PASS | 포함 | **필수** |
| `scripts/generate_country_validation_dataset.py` | 합성 텍스트 PDF 생성 계약 | 도구 | 없음 | Golden 불변 | 포함 | YES |
| `scripts/verify_golden_user_flow.py` | Golden 검증 artifact 연결 | 테스트 도구 | 없음 | 수치 회귀 PASS | 포함 | YES |
| `src/application/consultation_service.py` | review area·후보 packet 연결 | 코드 | 없음 | 순위 회귀 PASS | 포함 | **필수** |
| `src/application/demo_service.py` | 데모 reset 연결 | 코드 | 없음 | 값 불변 | 포함 | YES |
| `src/application/official_candidate_service.py` | catalogue 신호·explicit 우선·overflow·auxiliary | 코드 | 없음 | Golden Top3 PASS | 포함 | **필수** |
| `src/config.py` | debug·해석 flag 기본 false | 코드 | 없음 | 없음 | 포함 | YES |
| `src/consultation/packet.py` | profile·후보·해석 binding | 코드 | 없음 | Packet 수치 PASS | 포함 | **필수** |
| `src/domain/consultation_models.py` | optional 상담 projection 모델 | 코드 | 없음 | 역호환 PASS | 포함 | YES |
| `src/domain/product_models.py` | catalogue/profile/판정 모델 | 코드 | 없음 | Golden Top3 PASS | 포함 | **필수** |
| `src/domain/report_models.py` | Stage5 구조화 설명 모델 | 코드 | 없음 | 숫자 불변 | 포함 | YES |
| `src/stage4/local_kb.py` | active catalogue 검증 | 코드 | 없음 | 16개/순서 PASS | 포함 | **필수** |
| `src/stage5/critic.py` | grounding·숫자·순위 차단 | 코드 | 없음 | critic PASS | 포함 | **필수** |
| `src/stage5/deterministic_fallback.py` | canonical fallback 보고서 | 코드 | 없음 | Golden 수치 PASS | 포함 | **필수** |
| `src/stage5/report_agent.py` | 구조화 LLM 설명·fallback | 코드 | 없음 | Golden 수치·순위 PASS | 포함 | **필수** |
| `src/ui/layout.py` | 4개 사용자 탭 | UI | 없음 | 없음 | 포함 | YES |
| `src/ui/state.py` | 좁은 invalidation·검증 알림 clear | 상태 | 없음 | binding PASS | 포함 | **필수** |
| `src/ui/theme.py` | 반응형·production presentation | UI | 없음 | 없음 | 포함 | YES |
| `src/workflow/orchestrator.py` | optional 해석·후보 흐름 연결 | 상태 | 없음 | 단계 회귀 PASS | 포함 | **필수** |
| `src/workflow/state.py` | profile authoritative state·binding | 상태 | 없음 | stale 회귀 PASS | 포함 | **필수** |
| `tests/golden_consultation_fixture.py` | Golden 테스트 helper 확장 | 테스트 | 없음 | 보호 파일 아님 | 포함 | YES |
| `tests/test_completed_streamlit_service_journey.py` | one-click·stale·reset AppTest | 테스트 | 없음 | PASS | 포함 | YES |
| `tests/test_consultation_priority.py` | review area·supporting 경계 | 테스트 | 없음 | 순위 PASS | 포함 | YES |
| `tests/test_country_validation_dataset.py` | text PDF·manifest·SHA 경계 | 테스트 | 없음 | Golden SHA PASS | 포함 | YES |
| `tests/test_golden_transaction_e2e.py` | transaction/profile reset | 테스트 | 없음 | PASS | 포함 | YES |
| `tests/test_integration_readiness.py` | integration 표시 회귀 | 테스트 | 없음 | 없음 | 포함 | YES |
| `tests/test_kb_macro_hedge_reference.py` | UI 문구 경계 | 테스트 | 없음 | 없음 | 포함 | YES |
| `tests/test_live_benchmark.py` | test split 17건 경계 | 테스트 | 없음 | baseline 불변 | 포함 | YES |
| `tests/test_official_candidate_service.py` | catalogue·필터·Golden 회귀 | 테스트 | 없음 | PASS | 포함 | YES |
| `tests/test_stage3_4_5.py` | 상담·보고서 통합 회귀 | 테스트 | Stage3 계산 미변경 | PASS | 포함 | YES |
| `tests/test_stage5_decision_report.py` | grounding·critic·fallback | 테스트 | 없음 | PASS | 포함 | YES |
| `tests/test_trade_statistics.py` | 해석 fallback 경계 | 테스트 | 없음 | snapshot 불변 | 포함 | YES |
| `tests/test_ui_evidence_state.py` | production UI 사실·금지어 | 테스트 | 없음 | PASS | 포함 | YES |

## Untracked 전체 목록

현재 51개 파일은 `docs/UNTRACKED_FILE_CLASSIFICATION.md`에
경로·크기·목적·참조·staging 여부별로 모두 기록한다.
주요 그룹은 다음과 같다.

- 구현·테스트·합성 검증 자산: 제출 권고
- 제출 문서와 UI 캡처: 제출 권고
- `KBaiAgent_ACCOUNT_HANDOFF.md`, `PROJECT_DIRECTION.md`,
  `docs/T4_COUNTRY_ENVIRONMENT_IMPLEMENTATION_PROMPT.md`: 내부 선행자료로 stage 보류
- PPTX·기술설명서 PDF·영상: 현재 없음

## Diff 위험 관점 검사

| 검사 | 결과 |
| --- | --- |
| Stage1~3 계산 소스 변경 | 없음 |
| Golden/Baseline/국가·무역 snapshot/raw 변경 | 없음 |
| 새 network 호출 추가 패턴 | 발견 없음 |
| debug flag 기본 활성화 | 없음, `SHOW_INTERNAL_DEBUG=false` |
| production raw JSON | `st.json`은 developer debug gate 내부 |
| broad exception | Stage5 API 실패를 deterministic fallback으로 전환하는 기존 안전 경계에서 1개 추가 |
| test assertion lines | 추가 220 / 삭제 24, 삭제는 UI·dataset·LLM 계약 교체 구간으로 사람 검토 필요 |
| secret literal | 확정 의심 0 |
| catalogue 변경 | 존재, 16개 stable ID·Golden 회귀는 PASS이나 사람 검토 필수 |

## 사람 우선 검토 순서

1. `knowledge_base/official_products.json`, `product_models.py`,
   `official_candidate_service.py`
2. `packet.py`, workflow/state, Stage5 grounding·critic·fallback
3. `app.py`, UI state/layout/theme와 production debug gate
4. test assertion 삭제 24줄이 더 강한 새 계약으로 대체됐는지 확인
5. 합성 PDF·manifest·generator가 Golden/API-free 등록을 변경하지 않는지 확인
6. README·기술설명서·제출 문서의 과장 표현 확인

## 6.4 저장소 정리·탐색 범위 갱신

6.4는 source 구조나 실행 경로를 바꾸지 않고 탐색 안내와 ignore 경계만
보강했다. 파일 삭제·이동·quarantine·staging은 수행하지 않았다.

### 시작·정리 후 인벤토리

| 항목 | 시작 | 정리 후 | 해석 |
| --- | ---: | ---: | --- |
| `.git` 제외 전체 파일 | 9,347 | 9,349 | 문서 인덱스·맵 2개 추가 |
| 기본 `rg --files` 대상 | 410 | 412 | 위 canonical 문서 2개만 증가 |
| 실제 untracked 파일 | 49 | 51 | 삭제 없이 탐색 문서 추가 |
| tracked modified | 38 | 40 | `AGENTS.md`, `.gitignore` 보강 |
| `.git` 제외 전체 bytes | 316,730,837 | 316,748,239 | 문서만 증가 |
| `.venv`·cache 제외 bytes | 8,998,890 | 9,016,292 | 문서만 증가 |
| 기본 `rg` 측정 | 0.02초 | 0.01초 | 표본 오차, 개선율 주장 안 함 |
| `git status --short` 측정 | 0.02초 | 0.03초 | 표본 오차, 변화 없음으로 해석 |

실제 파일 수의 대부분은 ignore된 `.venv` 8,896개(약 315MB)다. 기본 검색은
이미 412개로 제한되어 있으므로 물리적 삭제보다 `AGENTS.md`, `docs/INDEX.md`,
`docs/REPOSITORY_MAP.md`로 시작 경로를 고정하는 것이 이번 회차의 실질적 효과다.

### 수행한 변경

| 경로 | 변경 | source·금융 영향 |
| --- | --- | --- |
| `AGENTS.md` | core entry point, canonical 문서, 보호 경로, freeze·검색 지침 병합 | 없음 |
| `.gitignore` | venv, ruff, swap, browser·Playwright 로컬 산출물 ignore 보강 | 없음 |
| `docs/INDEX.md` | canonical·architecture·audit·submission·historical 문서 분류 | 없음 |
| `docs/REPOSITORY_MAP.md` | runtime path와 기능별 핵심 파일 안내 | 없음 |
| `docs/UNTRACKED_FILE_CLASSIFICATION.md` | 실제 51개와 작업 성격별 분류 갱신 | 없음 |

`.vscode/settings.json`은 개인 IDE 설정을 강제하지 않기 위해 만들지 않았다.
cache와 duplicate 후보도 삭제하거나 이동하지 않았다.

### tracked duplicate 후보 정밀 판정

| 파일 | SHA-256 | canonical | line diff(추가/삭제) | runtime 참조 | 판정·조치 |
| --- | --- | --- | ---: | --- | --- |
| `src/demo 2.py` | `c1b00e53cf4c86be504ba4848a93f943f356234a8c79f7adcb28cfb359b66b6d` | `src/demo.py` | 10/129 | 없음 | HISTORICAL_COPY, 사람 판단 |
| `src/stage5/critic 2.py` | `aa6013ba029e72e2311c563c896afea02f0738b0987b82c6a3b4d83b7fce5584` | `src/stage5/critic.py` | 1668/14 | 없음 | HISTORICAL_COPY, 사람 판단 |
| `src/stage5/report_agent 2.py` | `1120f0793a1858eb9b0f5b6520154bde3469432b4cce0ca7b7cb89601def1a7e` | `src/stage5/report_agent.py` | 197/67 | 없음 | HISTORICAL_COPY, 사람 판단 |
| `docs/PROJECT_BRIEF 2.md` | `90c861a0b74f93c159a8b5fa5a49d63c468029a593b7bbdfba7a01e9367f790f` | `docs/PROJECT_BRIEF.md` | 171/31 | 문서 감사에서만 언급 | HISTORICAL_COPY, 사람 판단 |

4개 모두 tracked이고 canonical과 SHA가 다르므로
`EXACT_DUPLICATE_UNTRACKED`가 아니다. 자동 격리 조건을 충족하지 않아 원위치에
보존했다. 실행·테스트 import는 canonical 파일만 사용한다.

### app.py 판정

- 현재 9,332줄, `_render*` 함수 19개다.
- `src/ui/`로 layout, state, theme, presentation, user view 일부가 분리돼 있다.
- 거래 확인, 금융 입력, 상품 질문과 메인 Streamlit composition은 남아 있다.
- 지금 분할하면 widget key, session state, invalidation 회귀 위험이 크다.
- 판정: `PRE_SUBMISSION_REFACTOR_NOT_RECOMMENDED`.

### 문서·링크 점검

- canonical 제출 문서에서 686·692·693·701 구버전 테스트 수: 0건.
- canonical 문서의 로컬 Markdown 링크: 깨진 경로 0건.
- 과거 HEAD·branch가 있는 문서는 historical/audit 범주로 분리했다.
- 외부 URL은 네트워크로 검증하지 않았다.

## 6.5 tracked modified 최종 분류

| 분류 | 개수 | 파일 |
| --- | ---: | --- |
| REPOSITORY_HYGIENE | 2 | `.gitignore`, `AGENTS.md` |
| CANONICAL_DOCUMENT | 1 | `README.md` |
| UI | 4 | `app.py`, `src/ui/layout.py`, `src/ui/state.py`, `src/ui/theme.py` |
| FINANCIAL_LOGIC | 3 | `knowledge_base/official_products.json`, `src/application/official_candidate_service.py`, `src/domain/product_models.py` |
| CORE_RUNTIME | 13 | `env.template`, consultation/demo/config/Packet/report/Stage4/Stage5/workflow 파일 |
| TEST | 15 | `scripts/` 2개와 tracked test 13개 |
| EVIDENCE | 2 | `dataset/country_validation/README.md`, `manifest.jsonl` |
| **합계** | **40** | staged 0 |

`src/demo 2.py`, `src/stage5/critic 2.py`, `src/stage5/report_agent 2.py`,
`docs/PROJECT_BRIEF 2.md`는 tracked이지만 현재 modified 목록에는 없다. 이번 commit에서
정리하지 않고 제출 패키지 포함 여부만 사람이 결정한다.
