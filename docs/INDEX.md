# 제출판 문서 인덱스

기준일: 2026-08-03

내부 작업일지·감사 초안·구현 프롬프트·중복 최종보고서는 제거했다. 아래 문서는
심사 실행, 계산 계약, 안전 경계, 데모와 검증 근거에 직접 필요한 제출판 문서다.

## 심사와 제출

- `KB_AI_CHALLENGE_TECHNICAL_DESCRIPTION_KO.md`: 기술설명 기준
- `JUDGE_DEMO_RUNBOOK.md`: 심사위원 로컬 실행 절차
- `SUBMISSION_SECRET_DELIVERY.md`: API 키 비공개 전달 원칙
- `SUBMISSION_CHECKLIST.md`: 최종 제출 확인
- `SUBMISSION_FREEZE.md`: 기능 동결 범위
- `SUBMISSION_READINESS.md`: 제출 준비 상태
- `JUDGE_QA_KO.md`: 예상 질의응답
- `PITCH_3MIN_KO.md`: 발표 원고

## 데모와 화면 근거

- `FINAL_DEMO_SCRIPT.md`: 최종 데모 진행 순서
- `DEMO_SCRIPT_KO.md`: Golden 데모 상세 동선
- `DEMO_SCENARIO_MATRIX.md`: Demo A~E 입력과 기대 결과
- `SCREENSHOT_MANIFEST.md`: 화면 증거 목록
- `evidence/ui/`: 데스크톱·모바일 캡처
- `evidence/country_benchmark_v1_v2_summary.json`: 국가 benchmark 요약

## 실행 구조와 Stage 계약

- `ARCHITECTURE.md`, `REPOSITORY_MAP.md`, `AGENT_WORKFLOW.md`
- `STAGE0_DOCUMENT_INTAKE.md`
- `STAGE1_CONTRACT.md`, `STAGE1_INTEGRATION.md`, `STAGE1_JSON_MAPPING.md`
- `SPOT_PROVIDER_SETUP.md`, `STAGE1_CHANGE_REQUEST.md`
- `STAGE2_CALCULATION_SPEC.md`
- `STAGE3_OPTIMIZATION.md`, `STAGE3_OPTIMIZER_SPEC.md`
- `STAGE4_RAG_POLICY.md`
- `STAGE5_REPORT_POLICY.md`
- `TRADE_STATISTICS.md`, `T4_COUNTRY_ENVIRONMENT_DESIGN.md`
- `KB_MACRO_HEDGE_REFERENCE_RUNBOOK.md`

## 보안, 한계와 검증

- `SECURITY.md`, `SECURITY_PRIVACY.md`, `LIMITATIONS.md`
- `DATASET_AND_EVALS.md`
- `INTEGRATION_READINESS.md`
- `LIVE_BENCHMARK_RUNBOOK.md`, `LIVE_BENCHMARK_RESULTS.md`
- `VALIDATION_REPORT.md`, `REPOSITORY_AUDIT.md`

## 호환성 때문에 유지하는 검증 문서

- `TEAM_HANDOFF.md`, `TEAM_HANDOFF_KO.md`
- `repositioning/`의 4개 검증 문서

실제 테스트 수와 작업 트리 상태는 문서의 과거 숫자가 아니라 현재
`python scripts/verify.py`와 `git diff --check` 결과를 기준으로 판단한다.
