# Agent Workflow

현재 구현은 자유롭게 대화하는 멀티에이전트가 아니라 typed state와 gate가 있는
단일 오케스트레이터입니다.

| 사용자 의미 상태 | 실제 StageResult/필드 | 사람 확인 |
| --- | --- | --- |
| `UPLOADED` | intake 시작 | 아니오 |
| `EXTRACTED` | `state.extracted_trade` | 아니오 |
| `HUMAN_CONFIRMED` | `user_confirmed=true` | 필수 |
| `FORECAST_LOADED` | `market_integration.forecast_load` | fallback 공개 |
| `SPOT_CONFIRMED` | `market_integration.spot_quote` | 수동값은 필수 |
| `RISK_CALCULATED` | `cashflow.data` | 결정론 |
| `HEDGE_CANDIDATES_GENERATED` | `hedge.data` | 후보만 |
| `PRODUCTS_RETRIEVED` | `product_search.data` | 적격성 미확정 |
| `REPORT_VERIFIED` | `critic_result.passed` | critic |
| `READY_FOR_HUMAN_REVIEW` | `final_status=SUCCEEDED` | 최종 판단 |

`StageResult`는 status, schema data, 오류·경고, evidence path, 시작·종료시각,
duration, provider, retry와 fallback 여부를 보관합니다. Trace에는 문서 원문,
확인 금융 payload, 비밀값을 넣지 않습니다.

한 단계가 실패하면 뒤 단계를 실행하지 않습니다. 확인이 부족하면
`WAITING_FOR_USER`, 안전한 provider가 없으면 `FAILED`, 외부 기능을 명시적으로
대체하면 `FALLBACK`입니다.

현재 Streamlit 단일 앱이므로 요청된 REST endpoint는 다음 서비스 함수와
오케스트레이터 메서드로 대응합니다.

| 논리 도구 | 함수 |
| --- | --- |
| extract trade | `extract_trade_document_with_metadata` |
| confirm fields | `create_confirmation_record` |
| load forecast | `Stage1ForecastService.load` |
| spot quote | `resolve_spot_quote` |
| build scenarios | `build_fx_scenarios` |
| calculate risk | `run_stage2` |
| optimize hedge | `generate_strategy_candidates` |
| retrieve products | `search_offline_kb` / `search_official_web` |
| compose/verify report | `generate_report` / `critique_report` |
| run all | `WorkflowOrchestrator.run` |
