# 문서 인덱스

기준일: 2026-08-03

이 파일은 문서를 이동하거나 폐기하는 목록이 아니라 읽기 우선순위를 정하는
인덱스다. 일반 작업은 `CANONICAL`부터 시작하고, 과거 감사·계획서는 현재 작업에
직접 필요한 경우에만 읽는다.

## CANONICAL

| 파일 | canonical | 현재 사용처 | 대체 문서 | 조치 권고 |
| --- | --- | --- | --- | --- |
| `KB_AI_CHALLENGE_TECHNICAL_DESCRIPTION_KO.md` | YES | 제출 기술설명 기준 | - | 유지 |
| `FINAL_DEMO_SCRIPT.md` | YES | 5~7분 최종 데모 | - | 유지 |
| `SUBMISSION_CHECKLIST.md` | YES | 제출 전 수동 확인 | - | 유지 |
| `SUBMISSION_FREEZE.md` | YES | 기능 동결 기준 | - | 유지 |
| `DEMO_SCENARIO_MATRIX.md` | YES | Demo A~E 입력·기대값 | - | 유지 |
| `SCREENSHOT_MANIFEST.md` | YES | 제출 UI 증거 목록 | - | 유지 |
| `FINAL_DIFF_REVIEW.md` | YES | 사람의 전체 diff 검토 | - | 변경 때 갱신 |
| `PROPOSED_STAGING_PLAN.md` | YES | 승인 후 명시적 staging | - | 실제 stage 전 재확인 |
| `INDEX.md` | YES | 문서 탐색 시작점 | - | 유지 |
| `REPOSITORY_MAP.md` | YES | 기능별 코드 탐색 시작점 | - | 구조 변경 때 갱신 |

## ARCHITECTURE

| 파일 | canonical | 현재 사용처 | 대체 문서 | 조치 권고 |
| --- | --- | --- | --- | --- |
| `AGENT_WORKFLOW.md` | NO | 에이전트 작업 흐름 참고 | 루트 `AGENTS.md` | 필요할 때만 읽기 |
| `ARCHITECTURE.md` | YES | 전체 계층·데이터 흐름 | `REPOSITORY_MAP.md`는 빠른 안내 | 유지 |
| `DATASET_AND_EVALS.md` | YES | dataset·평가 정책 | - | 유지 |
| `DECISIONS.md` | YES | 설계 결정 이력 | - | 해당 결정 조사 때 사용 |
| `FEATURE_MAPPING.md` | YES | 기능과 구현 대응 | `REPOSITORY_MAP.md`는 핵심 경로만 제공 | 유지 |
| `LIMITATIONS.md` | YES | 제품·모델 한계 | 기술설명서에 요약 | 유지 |
| `SECURITY.md` | YES | 기본 보안 계약 | `SECURITY_PRIVACY.md` | 통합은 제출 후 검토 |
| `SECURITY_PRIVACY.md` | YES | 개인정보·운영 보안 | - | 유지 |
| `SPOT_PROVIDER_SETUP.md` | YES | 현물환율 provider 설정 | - | 관련 작업 때 사용 |
| `STAGE0_DOCUMENT_INTAKE.md` | YES | 문서 추출 계약 | - | 유지 |
| `STAGE1_CONTRACT.md` | YES | Stage1 adapter 계약 | - | 보호 |
| `STAGE1_INTEGRATION.md` | YES | Stage1 통합 흐름 | - | 유지 |
| `STAGE1_JSON_MAPPING.md` | YES | Stage1 JSON mapping | - | 유지 |
| `STAGE1_CHANGE_REQUEST.md` | NO | 과거 변경 요청 | Stage1 현재 계약 문서 | historical 취급 |
| `STAGE2_CALCULATION_SPEC.md` | YES | 현금흐름 계산 계약 | - | 보호 |
| `STAGE3_OPTIMIZATION.md` | YES | Stage3 개요 | `STAGE3_OPTIMIZER_SPEC.md` | 짧은 안내로 유지 |
| `STAGE3_OPTIMIZER_SPEC.md` | YES | Stage3 상세 계약 | - | 보호 |
| `STAGE4_RAG_POLICY.md` | YES | 공식 출처 검색 정책 | - | 유지 |
| `STAGE5_REPORT_POLICY.md` | YES | 보고서·Critic 정책 | - | 유지 |
| `T4_COUNTRY_ENVIRONMENT_DESIGN.md` | YES | 국가환경 설계 | - | 관련 작업 때 사용 |
| `TRADE_STATISTICS.md` | YES | 무역통계 계약 | - | 관련 작업 때 사용 |
| `KB_MACRO_HEDGE_REFERENCE_RUNBOOK.md` | YES | 외부 헤지 참고 runbook | - | optional 경로에서 사용 |

## VALIDATION_AND_AUDIT

| 파일 | canonical | 현재 사용처 | 대체 문서 | 조치 권고 |
| --- | --- | --- | --- | --- |
| `AI_LOG.md` | NO | AI 사용 이력 | 최종 기술설명서 요약 | 감사 요청 때만 읽기 |
| `AUDIT.md` | NO | 초기 저장소 감사 | `REPOSITORY_AUDIT.md` | archive 후보 |
| `BASELINE_V1_FOLLOW_UP_TICKETS.md` | NO | 과거 baseline 후속 | 현재 테스트·감사 | archive 후보 |
| `CONSULTATION_STRENGTHENING_REPORT.md` | NO | 상담 강화 회차 결과 | 현재 기술설명서 | historical |
| `FINAL_TECHNICAL_AUDIT.md` | NO | 누적 기술 감사 | 현재 기술설명서·최종 diff | 근거 조사 때만 읽기 |
| `INTEGRATION_READINESS.md` | YES | integration 운영 점검 | - | 관련 작업 때 사용 |
| `KB_MACRO_AI_INTEGRATION_AUDIT.md` | NO | 외부 모델 통합 감사 | runbook·현재 테스트 | historical |
| `LARGE_AND_TEMP_FILE_AUDIT.md` | YES | 대용량·임시파일 감사 | - | 저장소 구성 변경 때 갱신 |
| `LIVE_BENCHMARK_RESULTS.md` | NO | 과거 live 평가 결과 | 현재 검증 문서 | 요청 시에만 읽기 |
| `LIVE_BENCHMARK_RUNBOOK.md` | YES | optional live 평가 절차 | - | 기본 실행 금지 |
| `PPT_CHECK_STATUS.md` | YES | PPT 수동 반영 감사 | `SUBMISSION_PPT_UPDATE_NOTES.md` | PPT 도착 후 갱신 |
| `PROGRESS.md` | NO | 과거 진행 기록 | checklist·freeze | archive 후보 |
| `REPOSITORY_AUDIT.md` | NO | 과거 저장소 감사 | `FINAL_DIFF_REVIEW.md` | historical |
| `SECRET_AUDIT_REPORT.md` | YES | secret·개인정보 감사 | - | 제출 전 재검증 |
| `SUBMISSION_READINESS.md` | NO | 이전 제출 readiness | 현재 checklist·freeze | historical |
| `UNTRACKED_FILE_CLASSIFICATION.md` | YES | untracked 전체 분류 | - | 파일 추가 때 갱신 |
| `VALIDATION_REPORT.md` | NO | 누적 검증 기록 | 현재 `scripts/verify.py` 결과 | 과거 근거로만 사용 |

## SUBMISSION_EVIDENCE

| 파일 | canonical | 현재 사용처 | 대체 문서 | 조치 권고 |
| --- | --- | --- | --- | --- |
| `FINAL_PROJECT_REPORT.md` | NO | 종합 프로젝트 근거 | 기술설명서 | 필요할 때만 읽기 |
| `JUDGE_QA_KO.md` | YES | 심사 질의 대응 | - | 발표 전 사용 |
| `PITCH_3MIN_KO.md` | NO | 3분 발표 원고 | `FINAL_DEMO_SCRIPT.md` | 짧은 발표 요청 때만 사용 |
| `SUBMISSION_PPT_UPDATE_NOTES.md` | YES | PPT 수동 교체 계약 | - | PPT 편집 때 사용 |
| `DEMO_SCRIPT_KO.md` | NO | 이전 Golden 데모 동선 | `FINAL_DEMO_SCRIPT.md` | archive 후보 |
| `evidence/ui/` | YES | 실제 UI 캡처 8개 | `SCREENSHOT_MANIFEST.md` | 이미지 bytes는 검색 제외 |
| `evidence/country_benchmark_v1_v2_summary.json` | NO | 국가 benchmark 요약 | live 결과 문서 | 관련 감사 때만 읽기 |

## HISTORICAL_AND_ARCHIVE_CANDIDATE

| 파일 | canonical | 현재 사용처 | 대체 문서 | 조치 권고 |
| --- | --- | --- | --- | --- |
| `FINAL_ACTION_PLAN.md` | NO | 과거 제출 계획 | checklist·freeze | archive 후보 |
| `PROJECT_BRIEF.md` | NO | 초기 MVP brief | 기술설명서 | historical |
| `PROJECT_BRIEF 2.md` | NO | tracked modified copy | `PROJECT_BRIEF.md` | 자동 삭제 금지, 사람 판단 |
| `TEAM_HANDOFF.md` | NO | 이전 영문 handoff | 현재 canonical 문서 | archive 후보 |
| `TEAM_HANDOFF_KO.md` | NO | 이전 국문 handoff | 현재 canonical 문서 | archive 후보 |
| `T4_COUNTRY_ENVIRONMENT_IMPLEMENTATION_PROMPT.md` | NO | 선행 구현 지시서 | T4 설계·현재 코드 | stage 보류·historical |
| `repositioning/CURRENT_STATE.md` | NO | 재포지셔닝 이전 상태 | 기술설명서 | historical |
| `repositioning/FINAL_REPORT.md` | NO | 재포지셔닝 회차 결과 | 기술설명서 | historical |
| `repositioning/IMPLEMENTATION_PLAN.md` | NO | 과거 구현 계획 | 현재 코드·freeze | historical |
| `repositioning/TEAM_POSITIONING.md` | NO | 과거 발표 포지셔닝 | 최종 데모·Q&A | historical |

## 읽기 원칙

1. 제품·제출 사실은 `CANONICAL` 문서를 우선한다.
2. 계산·adapter 계약은 `ARCHITECTURE`의 해당 Stage 문서를 확인한다.
3. 테스트 수와 Git 상태는 과거 보고서가 아니라 현재 명령 결과를 사용한다.
4. `HISTORICAL_AND_ARCHIVE_CANDIDATE`는 자동 이동·삭제하지 않는다.
5. 외부 URL의 최신성은 이 인덱스가 보증하지 않는다.
