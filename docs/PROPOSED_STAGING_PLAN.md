# 제안 Staging 계획

기준일: 2026-08-03

이 문서는 계획만 제공한다. 실제 `git add`, commit, push는 수행하지 않았다.
모든 경로는 파일별 diff를 확인한 뒤 명시적으로 stage하며 `git add .`와
`git add app.py src tests` 같은 광범위한 staging은 사용하지 않는다.

## 1. Runtime and financial workflow

아래 파일은 현재 Demo A~E와 runtime에 연결된다. Stage1~3 계산 파일은 포함되지
않지만, catalogue·후보·Packet·Stage5·상태 경계가 누적 변경됐으므로 전부 사람의
diff 확인 후 stage한다.

| 파일 | 변경 목적 | Golden 영향 | hunk 검토 |
| --- | --- | --- | --- |
| `app.py` | 4탭 UI·조건 입력·one-click 갱신 | 값 불변 | **필수** |
| `env.template` | optional flag 예시 | 없음 | secret 없음 확인 |
| `knowledge_base/official_products.json` | catalogue metadata·신호 | Top3 회귀 PASS | **필수** |
| `src/application/consultation_service.py` | review area·후보 Packet 연결 | 순서 회귀 PASS | **필수** |
| `src/application/demo_service.py` | demo reset | 값 불변 | YES |
| `src/application/official_candidate_service.py` | explicit 우선·overflow·auxiliary | Top3 회귀 PASS | **필수** |
| `src/config.py` | debug·optional 해석 flag | 없음 | YES |
| `src/consultation/packet.py` | profile·후보·해석 binding | Packet 수치 PASS | **필수** |
| `src/domain/consultation_models.py` | optional 상담 모델 | 역호환 PASS | YES |
| `src/domain/product_models.py` | catalogue/profile/판정 모델 | Top3 회귀 PASS | **필수** |
| `src/domain/report_models.py` | Stage5 구조화 설명 모델 | 숫자 불변 | YES |
| `src/stage4/local_kb.py` | active catalogue 검증 | 16개 PASS | **필수** |
| `src/stage5/critic.py` | grounding·숫자·순위 차단 | critic PASS | **필수** |
| `src/stage5/deterministic_fallback.py` | canonical fallback | Golden 수치 PASS | **필수** |
| `src/stage5/report_agent.py` | 구조화 설명·fallback | 수치·순위 PASS | **필수** |
| `src/ui/layout.py` | 4개 사용자 탭 | 없음 | YES |
| `src/ui/state.py` | 좁은 invalidation | stale 회귀 PASS | **필수** |
| `src/ui/theme.py` | 반응형 presentation | 없음 | YES |
| `src/workflow/orchestrator.py` | optional 해석·후보 흐름 | 단계 회귀 PASS | **필수** |
| `src/workflow/state.py` | authoritative profile·binding | stale 회귀 PASS | **필수** |
| `prompts/country_economic_interpretation.md` | 구조화 해석 계약 | 금융 계산 없음 | YES |
| `prompts/trade_statistics_interpretation.md` | 구조화 해석 계약 | 금융 계산 없음 | YES |
| `src/application/country_economic_interpretation_service.py` | 국가환경 설명 fallback | 우선순위 불변 | YES |
| `src/application/trade_statistics_interpretation_service.py` | 무역통계 설명 fallback | 후보 불변 | YES |
| `src/consultation/review_area.py` | review area/supporting projection | 순서 회귀 PASS | **필수** |
| `src/country_environment/interpretation_fallback.py` | 결정론 설명 | 없음 | YES |
| `src/country_environment/interpretation_input.py` | canonical 입력 registry | 없음 | YES |
| `src/country_environment/interpretation_validator.py` | AI 설명 검증 | 없음 | YES |
| `src/domain/country_economic_interpretation_models.py` | optional schema | 역호환 PASS | YES |
| `src/domain/trade_statistics_interpretation_models.py` | optional schema | 역호환 PASS | YES |
| `src/stage5/grounding.py` | canonical source registry | critic PASS | **필수** |
| `src/trade_statistics/interpretation_fallback.py` | 결정론 설명 | 없음 | YES |
| `src/trade_statistics/interpretation_input.py` | 해석 입력 registry | 없음 | YES |
| `src/trade_statistics/interpretation_validator.py` | 해석 검증 | 없음 | YES |
| `src/ui/user_views.py` | 환율·뉴스 view model | Stage1 값만 표시 | YES |

## 2. Tests and verification

테스트 기대값 완화 여부를 확인한 뒤 runtime 그룹과 함께 stage한다.

### Tracked modified tests

- `tests/golden_consultation_fixture.py`
- `tests/test_completed_streamlit_service_journey.py`
- `tests/test_consultation_priority.py`
- `tests/test_country_validation_dataset.py`
- `tests/test_golden_transaction_e2e.py`
- `tests/test_integration_readiness.py`
- `tests/test_kb_macro_hedge_reference.py`
- `tests/test_live_benchmark.py`
- `tests/test_official_candidate_service.py`
- `tests/test_stage3_4_5.py`
- `tests/test_stage5_decision_report.py`
- `tests/test_trade_statistics.py`
- `tests/test_ui_evidence_state.py`

### Untracked tests

- `tests/test_consultation_review_area.py`
- `tests/test_country_economic_interpretation.py`
- `tests/test_official_candidate_input_profile.py`
- `tests/test_stage5_grounding.py`
- `tests/test_submission_demo_acceptance.py`
- `tests/test_trade_statistics_interpretation.py`
- `tests/test_user_centered_ui.py`

### Verification scripts and synthetic assets

- `scripts/generate_country_validation_dataset.py`
- `scripts/verify_golden_user_flow.py`
- `dataset/country_validation/README.md`
- `dataset/country_validation/manifest.jsonl`
- `dataset/country_validation/documents/us_export_net60_text_009.pdf`
- `dataset/country_validation/labels/us_export_net60_text_009.json`

검토 포인트: 삭제된 assertion이 더 강한 새 계약으로 대체됐는지, 합성 PDF·label이
Golden이나 실제 업로드로 오인되지 않는지 확인한다.

## 3. Canonical documentation

다음 문서는 숫자·후보·브라우저 검증 범위를 최종 확인한 뒤 문서 커밋으로 분리한다.

- `README.md`
- `docs/FEATURE_MAPPING.md`
- `docs/KB_AI_CHALLENGE_TECHNICAL_DESCRIPTION_KO.md`
- `docs/DEMO_SCENARIO_MATRIX.md`
- `docs/FINAL_DEMO_SCRIPT.md`
- `docs/SCREENSHOT_MANIFEST.md`
- `docs/SUBMISSION_CHECKLIST.md`
- `docs/SUBMISSION_FREEZE.md`
- `docs/SUBMISSION_PPT_UPDATE_NOTES.md`

## 4. Evidence and submission assets

manifest와 연결된 아래 PNG만 evidence 그룹에 포함한다.

- `docs/evidence/ui/demo_a_trade_analysis_1440.png`
- `docs/evidence/ui/demo_a_fx_forecast_news_1440.png`
- `docs/evidence/ui/demo_a_finance_candidates_1440.png`
- `docs/evidence/ui/demo_a_consultation_report_1440.png`
- `docs/evidence/ui/demo_d_dynamic_candidates_1440.png`
- `docs/evidence/ui/demo_e_conflict_validation_1440.png`
- `docs/evidence/ui/demo_mobile_fx_forecast_390.png`
- `docs/evidence/ui/demo_mobile_candidates_390.png`

현재 repository에서 확인되지 않은 산출물은 stage 계획에 넣지 않는다.

- 최종 PPTX: MISSING
- 기술설명서 PDF 또는 요구 형식: MISSING
- 5~7분 데모 영상: MISSING
- 제출 후보 압축: 미생성

## 5. Repository hygiene

runtime과 분리된 hygiene 커밋 후보이며, 각각 내용을 확인한 뒤 stage한다.

- `.gitignore`
- `AGENTS.md`
- `docs/INDEX.md`
- `docs/REPOSITORY_MAP.md`
- `docs/UNTRACKED_FILE_CLASSIFICATION.md`
- `docs/FINAL_DIFF_REVIEW.md`
- `docs/LARGE_AND_TEMP_FILE_AUDIT.md`
- `docs/PPT_CHECK_STATUS.md`
- `docs/SECRET_AUDIT_REPORT.md`
- `docs/PROPOSED_STAGING_PLAN.md`

`.vscode/settings.json`은 `.git/info/exclude`로 숨긴 local-only 설정이므로 이 그룹에
포함하지 않는다. `.git/info/exclude`도 Git commit 대상이 아니다.

## 6. Do not stage

### Historical·personal material

- `KBaiAgent_ACCOUNT_HANDOFF.md`
- `PROJECT_DIRECTION.md`
- `docs/T4_COUNTRY_ENVIRONMENT_IMPLEMENTATION_PROMPT.md`

### Local·secret·generated

- `.env`
- `.vscode/settings.json`
- `.venv/`
- `__pycache__/`
- `.pytest_cache/`
- `.mypy_cache/`
- `.ruff_cache/`
- browser/Chrome profile
- Playwright report와 test output

### Tracked historical copies — 현재 diff 대상 아님

- `src/demo 2.py`
- `src/stage5/critic 2.py`
- `src/stage5/report_agent 2.py`
- `docs/PROJECT_BRIEF 2.md`

네 파일은 이미 HEAD에 추적돼 있고 현재 modified가 아니다. 이번 최종 commit에서
정리하지 않으며 제출 패키지 포함 여부만 사람이 별도로 결정한다.

## 승인 후 순서

1. 각 그룹의 파일별 diff 검토
2. runtime과 test dependency를 함께 확인
3. 명시적 파일 경로 또는 `git add -p` 사용
4. staged diff만 다시 검토
5. `python scripts/verify.py` 재실행
6. 사용자 승인 후 commit
7. 사용자 승인 후 push
