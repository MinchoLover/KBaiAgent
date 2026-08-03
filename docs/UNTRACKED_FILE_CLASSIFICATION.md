# Untracked 파일 최종 분류

감사일: 2026-08-03

`git ls-files --others --exclude-standard` 기준 실제 untracked 파일은 51개다.
ignored `.env`, `.venv`, cache와 local-only `.vscode/settings.json`은 이 합계와
분리한다. 어떤 파일도 삭제·이동·stage하지 않았다.

| 최종 분류 | 개수 |
| --- | ---: |
| SUBMIT_NOW | 18 |
| SUBMIT_AFTER_REVIEW | 30 |
| ACTIVE_WORK_KEEP_UNTRACKED | 0 |
| HISTORICAL_KEEP_UNTRACKED | 3 |
| LOCAL_ONLY_EXCLUDE | 0 |
| GENERATED_EXCLUDE | 0 |
| DUPLICATE_REVIEW | 0 |
| SECRET_SENSITIVE_EXCLUDE | 0 |
| NEEDS_HUMAN_DECISION | 0 |
| **합계** | **51** |

`SUBMIT_AFTER_REVIEW`는 목적이 불명확하다는 뜻이 아니다. 현재 runtime과 테스트에
필요하지만, 여러 선행 회차가 누적된 dirty tree이므로 파일별 diff 또는 내용을
사람이 확인한 뒤 명시적으로 stage해야 한다는 뜻이다.

| 경로 | 크기 | 종류 | 최종 분류 | 제출 이유 | 참조 여부 | staging 권고 | 사람 확인 |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| `KBaiAgent_ACCOUNT_HANDOFF.md` | 24,029B | 내부 문서 | HISTORICAL_KEEP_UNTRACKED | 제출 산출물 아님 | runtime 없음 | stage 금지 | 보존 여부 YES |
| `PROJECT_DIRECTION.md` | 1,772B | 내부 문서 | HISTORICAL_KEEP_UNTRACKED | 개발 방향 메모 | runtime 없음 | stage 금지 | 보존 여부 YES |
| `dataset/country_validation/documents/us_export_net60_text_009.pdf` | 2,842B | 합성 PDF | SUBMIT_AFTER_REVIEW | non-Golden 회귀 자산 | manifest·test | 내용 확인 후 stage | YES |
| `dataset/country_validation/labels/us_export_net60_text_009.json` | 3,235B | label | SUBMIT_AFTER_REVIEW | 합성 PDF 정답 계약 | manifest·test | diff 확인 후 stage | YES |
| `docs/DEMO_SCENARIO_MATRIX.md` | 3,138B | canonical 문서 | SUBMIT_NOW | Demo A~E 사실 계약 | INDEX·demo script | 명시적 stage | NO |
| `docs/FEATURE_MAPPING.md` | 3,757B | architecture 문서 | SUBMIT_NOW | 구현 기능 대응 | INDEX | 명시적 stage | NO |
| `docs/FINAL_DEMO_SCRIPT.md` | 5,518B | canonical 문서 | SUBMIT_NOW | 최종 데모 동선 | AGENTS·INDEX | 명시적 stage | NO |
| `docs/FINAL_DIFF_REVIEW.md` | 12,105B | 감사 문서 | SUBMIT_AFTER_REVIEW | 전체 diff 검토 지원 | AGENTS·INDEX | 내용 갱신 확인 후 stage | YES |
| `docs/INDEX.md` | 7,701B | 문서 인덱스 | SUBMIT_NOW | canonical 탐색 경계 | AGENTS | 명시적 stage | NO |
| `docs/KB_AI_CHALLENGE_TECHNICAL_DESCRIPTION_KO.md` | 29,880B | canonical 문서 | SUBMIT_NOW | 기술설명서 원본 | AGENTS·INDEX | 명시적 stage | NO |
| `docs/LARGE_AND_TEMP_FILE_AUDIT.md` | 2,281B | 감사 문서 | SUBMIT_AFTER_REVIEW | 제출 제외 근거 | INDEX | 최신 상태 확인 후 stage | YES |
| `docs/PPT_CHECK_STATUS.md` | 2,149B | 감사 문서 | SUBMIT_AFTER_REVIEW | PPT 수동 반영 상태 | INDEX·PPT notes | PPT 상태 확인 후 stage | YES |
| `docs/PROPOSED_STAGING_PLAN.md` | 8,304B | 감사 문서 | SUBMIT_AFTER_REVIEW | 명시적 staging 경계 | AGENTS·INDEX | 최종 계획 확인 후 stage | YES |
| `docs/REPOSITORY_MAP.md` | 6,213B | 저장소 맵 | SUBMIT_NOW | 기능별 핵심 경로 | AGENTS·INDEX | 명시적 stage | NO |
| `docs/SCREENSHOT_MANIFEST.md` | 1,946B | canonical 문서 | SUBMIT_NOW | UI evidence 계약 | AGENTS·INDEX | 명시적 stage | NO |
| `docs/SECRET_AUDIT_REPORT.md` | 3,063B | 감사 문서 | SUBMIT_AFTER_REVIEW | REDACTED 보안 감사 | INDEX | 값 미포함 재확인 후 stage | YES |
| `docs/SUBMISSION_CHECKLIST.md` | 2,610B | canonical 문서 | SUBMIT_NOW | 제출 수동 점검 | AGENTS·INDEX | 명시적 stage | NO |
| `docs/SUBMISSION_FREEZE.md` | 2,845B | canonical 문서 | SUBMIT_NOW | feature freeze 계약 | AGENTS·INDEX | 명시적 stage | NO |
| `docs/SUBMISSION_PPT_UPDATE_NOTES.md` | 3,504B | 제출 문서 | SUBMIT_NOW | PPT 교체 사실 계약 | INDEX | 명시적 stage | NO |
| `docs/T4_COUNTRY_ENVIRONMENT_IMPLEMENTATION_PROMPT.md` | 35,747B | 내부 prompt | HISTORICAL_KEEP_UNTRACKED | 선행 구현 지시서 | runtime 없음 | stage 금지 | 보존 여부 YES |
| `docs/UNTRACKED_FILE_CLASSIFICATION.md` | 현재 파일 | 감사 문서 | SUBMIT_AFTER_REVIEW | 51개 분류 manifest | INDEX | 합계 재확인 후 stage | YES |
| `docs/evidence/ui/demo_a_consultation_report_1440.png` | 241,421B | UI PNG | SUBMIT_NOW | Golden 상담 화면 | screenshot manifest | 명시적 stage | NO |
| `docs/evidence/ui/demo_a_finance_candidates_1440.png` | 332,092B | UI PNG | SUBMIT_NOW | Golden Top3 화면 | screenshot manifest | 명시적 stage | NO |
| `docs/evidence/ui/demo_a_fx_forecast_news_1440.png` | 231,634B | UI PNG | SUBMIT_NOW | 환율·뉴스 화면 | screenshot manifest | 명시적 stage | NO |
| `docs/evidence/ui/demo_a_trade_analysis_1440.png` | 177,299B | UI PNG | SUBMIT_NOW | Golden 거래 화면 | screenshot manifest | 명시적 stage | NO |
| `docs/evidence/ui/demo_d_dynamic_candidates_1440.png` | 336,081B | UI PNG | SUBMIT_NOW | 동적 정책금융 화면 | screenshot manifest | 명시적 stage | NO |
| `docs/evidence/ui/demo_e_conflict_validation_1440.png` | 201,537B | UI PNG | SUBMIT_NOW | 모순 입력 차단 화면 | screenshot manifest | 명시적 stage | NO |
| `docs/evidence/ui/demo_mobile_candidates_390.png` | 88,682B | UI PNG | SUBMIT_NOW | 모바일 후보 화면 | screenshot manifest | 명시적 stage | NO |
| `docs/evidence/ui/demo_mobile_fx_forecast_390.png` | 55,008B | UI PNG | SUBMIT_NOW | 모바일 환율 화면 | screenshot manifest | 명시적 stage | NO |
| `prompts/country_economic_interpretation.md` | 1,438B | prompt | SUBMIT_AFTER_REVIEW | 구조화 해석 계약 | source·test | diff 확인 후 stage | YES |
| `prompts/trade_statistics_interpretation.md` | 1,237B | prompt | SUBMIT_AFTER_REVIEW | 구조화 해석 계약 | source·test | diff 확인 후 stage | YES |
| `src/application/country_economic_interpretation_service.py` | 5,234B | Python | SUBMIT_AFTER_REVIEW | 국가환경 설명 fallback | runtime·test | diff 확인 후 stage | YES |
| `src/application/trade_statistics_interpretation_service.py` | 5,689B | Python | SUBMIT_AFTER_REVIEW | 무역통계 설명 fallback | runtime·test | diff 확인 후 stage | YES |
| `src/consultation/review_area.py` | 16,266B | Python | SUBMIT_AFTER_REVIEW | review area projection | runtime·test | diff 확인 후 stage | YES |
| `src/country_environment/interpretation_fallback.py` | 4,734B | Python | SUBMIT_AFTER_REVIEW | 결정론 설명 | runtime·test | diff 확인 후 stage | YES |
| `src/country_environment/interpretation_input.py` | 8,626B | Python | SUBMIT_AFTER_REVIEW | canonical 입력 registry | runtime·test | diff 확인 후 stage | YES |
| `src/country_environment/interpretation_validator.py` | 5,163B | Python | SUBMIT_AFTER_REVIEW | AI 설명 검증 | runtime·test | diff 확인 후 stage | YES |
| `src/domain/country_economic_interpretation_models.py` | 3,386B | Python | SUBMIT_AFTER_REVIEW | optional schema | runtime·test | diff 확인 후 stage | YES |
| `src/domain/trade_statistics_interpretation_models.py` | 3,252B | Python | SUBMIT_AFTER_REVIEW | optional schema | runtime·test | diff 확인 후 stage | YES |
| `src/stage5/grounding.py` | 10,597B | Python | SUBMIT_AFTER_REVIEW | canonical source registry | runtime·test | diff 확인 후 stage | YES |
| `src/trade_statistics/interpretation_fallback.py` | 1,226B | Python | SUBMIT_AFTER_REVIEW | 결정론 설명 | runtime·test | diff 확인 후 stage | YES |
| `src/trade_statistics/interpretation_input.py` | 7,118B | Python | SUBMIT_AFTER_REVIEW | 해석 입력 registry | runtime·test | diff 확인 후 stage | YES |
| `src/trade_statistics/interpretation_validator.py` | 5,426B | Python | SUBMIT_AFTER_REVIEW | 해석 검증 | runtime·test | diff 확인 후 stage | YES |
| `src/ui/user_views.py` | 6,478B | Python | SUBMIT_AFTER_REVIEW | 환율·뉴스 view model | runtime·test | diff 확인 후 stage | YES |
| `tests/test_consultation_review_area.py` | 13,486B | test | SUBMIT_AFTER_REVIEW | review area 회귀 | verify | diff 확인 후 stage | YES |
| `tests/test_country_economic_interpretation.py` | 16,139B | test | SUBMIT_AFTER_REVIEW | 국가 설명 회귀 | verify | diff 확인 후 stage | YES |
| `tests/test_official_candidate_input_profile.py` | 53,364B | test | SUBMIT_AFTER_REVIEW | profile·stale 회귀 | verify | diff 확인 후 stage | YES |
| `tests/test_stage5_grounding.py` | 7,038B | test | SUBMIT_AFTER_REVIEW | grounding 회귀 | verify | diff 확인 후 stage | YES |
| `tests/test_submission_demo_acceptance.py` | 10,653B | test | SUBMIT_AFTER_REVIEW | Demo A~E 수용성 | verify | diff 확인 후 stage | YES |
| `tests/test_trade_statistics_interpretation.py` | 12,278B | test | SUBMIT_AFTER_REVIEW | 통계 해석 회귀 | verify | diff 확인 후 stage | YES |
| `tests/test_user_centered_ui.py` | 4,672B | test | SUBMIT_AFTER_REVIEW | UI projection 회귀 | verify | diff 확인 후 stage | YES |

## Git이 무시하는 로컬 항목

아래 항목은 위 51개 합계에 포함되지 않는다.

| 경로 | 최종 분류 | Git 상태 | 조치 |
| --- | --- | --- | --- |
| `.env` | SECRET_SENSITIVE_EXCLUDE | ignored·untracked | 내용 미열람, 제출·stage 금지 |
| `.vscode/settings.json` | LOCAL_ONLY_EXCLUDE | `.git/info/exclude`로 ignored | local-only 유지 |
| `.venv/` | LOCAL_ONLY_EXCLUDE | ignored | 이동·삭제하지 않음 |
| `__pycache__/`, `.pytest_cache/` 등 | GENERATED_EXCLUDE | ignored | 제출 제외, 자동 삭제하지 않음 |

tracked historical copy 후보 4개는 현재 modified 목록에 없으며 자동 삭제·이동하지
않는다. 패키지 포함 여부는 사람이 별도로 결정한다.
