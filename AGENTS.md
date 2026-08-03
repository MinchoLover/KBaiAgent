# Repository Working Agreement

- Python 3.9 호환을 유지하고 타입은 `Optional`, `List`, `Dict`를 사용한다.
- 금융 계산은 `Decimal`, 날짜는 `date`/`datetime`을 사용한다.
- LLM 출력은 사용자 확인과 결정론 검증 전 계산에 전달하지 않는다.
- 문서 원문, 비밀값, 실제 업로드를 로그·dataset에 자동 저장하지 않는다.
- Stage 1 팀 모델을 재구현하지 않고 JSON/REST adapter 계약을 유지한다.
- 테스트셋은 파인튜닝 후보에서 항상 제외한다.
- 변경 후 `python scripts/verify.py`를 실행한다.

## Project

KBaiAgent는 확인된 수출입 거래 사실을 환율 전망, 현금흐름,
공식 금융지원 후보와 상담 패킷으로 연결하는 Streamlit 기반 MVP다.

## Core entry points

- UI: `app.py`
- 전체 흐름: `src/workflow/orchestrator.py`
- authoritative state: `src/workflow/state.py`
- 금융지원 추천: `src/application/official_candidate_service.py`
- UI 스타일: `src/ui/theme.py`
- 전체 검증: `scripts/verify.py`

## Canonical documents

일반 작업에서는 다음 문서부터 읽고, 나머지는 작업에 직접 필요할 때만 읽는다.

- `README.md`
- `docs/KB_AI_CHALLENGE_TECHNICAL_DESCRIPTION_KO.md`
- `docs/SUBMISSION_FREEZE.md`
- `docs/FINAL_DEMO_SCRIPT.md`
- `docs/SUBMISSION_CHECKLIST.md`
- `docs/DEMO_SCENARIO_MATRIX.md`
- `docs/SCREENSHOT_MANIFEST.md`
- `docs/FINAL_DIFF_REVIEW.md`
- `docs/INDEX.md`
- `docs/REPOSITORY_MAP.md`

## Protected assets and invariants

- `dataset/golden_demo/`와 `dataset/golden_import_hedge_demo/`
- `knowledge_base/official_products.json`
- 보호 baseline, 국가환경 snapshot, 무역통계 snapshot/raw, Golden expected
- Golden Top 3와 순서, catalogue 16개, 금융후보 최대 3개
- Stage1~3 계산과 transaction/profile/Packet/report binding
- 뉴스는 숫자 예측을 만들지 않으며 AI는 승인·가입 여부를 결정하지 않는다.

## Freeze and search guidance

- 신규 기능·상품·외부 API, 금융 계산 변경, 구조 리팩터링을 하지 않는다.
- commit/push는 사용자가 명시적으로 승인한 뒤에만 수행한다.
- 기본 작업은 `AGENTS.md`, `README.md`, 사용자가 지정한 source와 직접 관련된
  테스트부터 읽고, 구조 안내가 필요할 때만 `docs/REPOSITORY_MAP.md`를 연다.
- 저장소 전체 tree·docs·tests·dataset을 먼저 훑지 말고, 확인된 관련 파일만
  단계적으로 추가한다. 이미지·PDF binary도 작업에 직접 필요할 때만 연다.
- 기본 탐색에서 `.venv/`, cache, `__pycache__/`, browser profile,
  generated output, historical live report와 evidence 이미지 bytes를 읽지 않는다.
- 보호 데이터, 전체 historical docs와 전체 audit 문서는 사용자가 요청하거나
  해당 계약 검증에 필요한 경우에만 연다.
- `src/demo 2.py`, `src/stage5/critic 2.py`,
  `src/stage5/report_agent 2.py`, `docs/PROJECT_BRIEF 2.md`는
  실행 경로가 아닌 historical copy 후보이며 자동 삭제·import하지 않는다.
- 전체 검증은 `python scripts/verify.py`, whitespace 검사는
  `git diff --check`를 사용한다.
