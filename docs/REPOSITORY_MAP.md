# KBaiAgent Repository Map

기준일: 2026-08-03

전체 tree를 반복 탐색하지 않고 작업에 필요한 핵심 경로를 찾기 위한 안내다.
구체적인 금융·검증 계약은 코드와 해당 Stage 문서를 기준으로 한다.

## Runtime path

```text
문서 업로드
  app.py
  → src/security/upload_guard.py
  → src/document_intake/extractor.py
  → src/document_intake/normalization.py
  → src/document_intake/source_evidence.py

사용자 확인·거래 확정
  → src/document_intake/confirmation.py
  → src/domain/confirmed_transaction_models.py
  → src/workflow/state.py

환율 전망·현물환율
  → src/application/market_integration_service.py
  → src/stage1/

현금흐름
  → src/application/stage2_input_service.py
  → src/stage2/engine.py

헤지 비교
  → src/stage3/optimizer.py

공식 금융지원
  → src/application/official_candidate_service.py
  → src/stage4/local_kb.py
  → knowledge_base/official_products.json

상담 패킷
  → src/application/consultation_service.py
  → src/consultation/packet.py

보고서
  → src/stage5/report_agent.py
  → src/stage5/critic.py
  → src/stage5/deterministic_fallback.py

UI·다운로드
  → app.py
  → src/ui/layout.py
  → src/ui/state.py
  → src/ui/theme.py
  → src/ui/user_views.py
```

전체 상태 전이는 `src/workflow/orchestrator.py`와
`src/workflow/state.py`가 authoritative하다.

## Feature to file mapping

| 기능 | 먼저 볼 파일 | 함께 볼 파일 |
| --- | --- | --- |
| 문서 추출 | `src/document_intake/extractor.py` | `openai_adapter.py`, `prompt_builder.py`, `document_models.py` |
| 원문 근거 | `src/document_intake/source_evidence.py` | `normalization.py`, `validators.py` |
| 사용자 확인 | `src/document_intake/confirmation.py` | `confirmed_transaction_models.py`, `app.py` |
| 환율 전망 | `src/application/market_integration_service.py` | `src/stage1/`, `stage1_web_models.py` |
| 현물환율 | `src/stage1/spot_rate.py` | `src/config.py` |
| 현금흐름 | `src/stage2/engine.py` | `exposure.py`, `cashflow.py`, `scenarios.py` |
| 헤지 | `src/stage3/optimizer.py` | `constraints.py`, `explanations.py` |
| 금융상품 | `src/application/official_candidate_service.py` | `product_models.py`, `stage4/local_kb.py` |
| catalogue | `knowledge_base/official_products.json` | `tests/test_official_candidate_service.py` |
| 국가환경 | `src/application/country_environment_service.py` | `src/country_environment/`, integration snapshot |
| 무역통계 | `src/application/trade_statistics_service.py` | `src/trade_statistics/`, integration snapshot/raw |
| 상담 우선순위 | `src/consultation/prioritization.py` | `review_area.py`, `risk_classifier.py` |
| ConsultationPacket | `src/consultation/packet.py` | `consultation_models.py` |
| Stage5 grounding | `src/stage5/grounding.py` | `critic.py`, `report_agent.py` |
| fallback 보고서 | `src/stage5/deterministic_fallback.py` | `report_models.py` |
| workflow state | `src/workflow/state.py` | `orchestrator.py`, `gates.py` |
| UI 상태 | `src/ui/state.py` | `app.py` |
| UI 스타일 | `src/ui/theme.py` | `layout.py`, `user_views.py` |
| 업로드 보안 | `src/security/upload_guard.py` | `redaction.py` |
| 환경 설정 | `src/config.py` | `env.template` |

## Protected paths

다음 경로는 명시적 요청 없이 수정·재생성하지 않는다.

- `dataset/golden_demo/`
- `dataset/golden_import_hedge_demo/`
- `knowledge_base/official_products.json`
- `reports/baseline_metrics.json`
- `src/integration_assets/country_environment/snapshot_v1.json`
- `src/integration_assets/trade_statistics/snapshot_kr_br_country_v1.json`
- `src/integration_assets/trade_statistics/raw/`
- Golden expected extraction과 demo inputs
- `docs/evidence/ui/`의 제출 캡처

## Test entry points

| 목적 | 명령·파일 |
| --- | --- |
| 전체 검증 | `python scripts/verify.py` |
| whitespace | `git diff --check` |
| Golden 수출 흐름 | `scripts/verify_golden_user_flow.py` |
| Golden 수입 흐름 | `scripts/verify_golden_import_hedge_flow.py` |
| Demo A~E | `tests/test_submission_demo_acceptance.py` |
| completed journey | `tests/test_completed_streamlit_service_journey.py` |
| Stage1 | `tests/test_stage1.py`, `test_stage1_web_integration.py` |
| Stage2 | `tests/test_stage2.py` |
| Stage3~5 | `tests/test_stage3_4_5.py`, `test_stage5_decision_report.py` |
| 금융후보 | `tests/test_official_candidate_service.py`, `test_official_candidate_input_profile.py` |
| stale binding | `test_official_candidate_input_profile.py`, `test_workflow.py` |
| UI | `test_ui_evidence_state.py`, `test_user_centered_ui.py` |

## Submission documents

일반 제출 작업은 다음 문서만 먼저 읽는다.

- `README.md`
- `docs/KB_AI_CHALLENGE_TECHNICAL_DESCRIPTION_KO.md`
- `docs/FINAL_DEMO_SCRIPT.md`
- `docs/SUBMISSION_CHECKLIST.md`
- `docs/SUBMISSION_FREEZE.md`
- `docs/DEMO_SCENARIO_MATRIX.md`
- `docs/SCREENSHOT_MANIFEST.md`
- `docs/FINAL_DIFF_REVIEW.md`
- `docs/PROPOSED_STAGING_PLAN.md`

문서의 전체 분류는 `docs/INDEX.md`를 따른다.

## Paths normally not needed

- `.venv/`, `venv/`
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`
- browser·Chrome profile, Playwright report와 test output
- `reports/country_validation_live/`의 과거 live run
- `dataset/**/predictions/live/`
- `docs/evidence/ui/` 이미지의 binary bytes
- `KB_AI_Codex_Autopilot_Prompt_Pack_v1/`
- `docs/repositioning/`과 과거 audit·handoff 문서
- `src/demo 2.py`, `src/stage5/critic 2.py`,
  `src/stage5/report_agent 2.py`, `docs/PROJECT_BRIEF 2.md`

위 경로는 삭제 대상이라는 뜻이 아니다. 사용자가 명시하거나 특정 회귀·감사에
필요한 경우 경로를 직접 지정해 읽는다.

## app.py boundary

`app.py`는 현재 큰 Streamlit composition root다. 이미 view model, layout, state,
theme 일부가 `src/ui/`로 분리됐지만 거래 확인, 금융 입력, 추천 질문과 결과 renderer가
남아 있다. 제출 직전 분할은 widget key·session state·invalidation 회귀 위험이 커서
`PRE_SUBMISSION_REFACTOR_NOT_RECOMMENDED`다. 분리는 공모전 이후 별도 회차에서 한다.
