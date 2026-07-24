# AI Use Log

## 2026-07-23

Codex가 저장소 감사, schema와 prompt 분리, deterministic validators, Stage 1~5 모듈,
합성 dataset, evaluation scripts, tests, Streamlit UI, 문서를 구현했습니다.

OpenAI 연동 방식은 공식 문서의 다음 항목을 확인했습니다.

- Responses API Pydantic parse / Structured Outputs:
  https://developers.openai.com/api/docs/guides/structured-outputs
- base64 PDF `input_file`:
  https://developers.openai.com/api/docs/guides/file-inputs
- image `input_image`:
  https://developers.openai.com/api/docs/guides/images-vision
- official domain-filtered web search:
  https://developers.openai.com/api/docs/guides/tools-web-search

공식 상품 KB는 한국무역보험공사, KB국민은행, 중소벤처기업진흥공단, 기업마당의
공식 URL만 사용했습니다. AI가 상품 자격·승인·가격을 확정하지 않도록 unknown과
상담 필요 정책을 적용했습니다.

실제 OpenAI API 호출, fine-tuning job, 외부 메시지·배포·Git push는 실행하지
않았습니다. API 키가 없어서 live 경로는 mock adapter와 compile/import로 검증했습니다.

## 2026-07-23 Workflow refactoring

Codex가 기존 Stage 계산과 adapter 계약을 유지하면서 `src/workflow/`의 typed state,
공통 result, confirmation gate, fallback policy, payload-free trace를 추가했습니다.
offline demo와 Streamlit은 같은 orchestrator를 사용하고, UI의 Stage 2 입력 배분은
application service로 이동했습니다.

critic 피드백이 정확히 한 번의 재작성 호출에 전달되는지, 재실패/API 실패 시
결정론 report로 전환되는지, 공식 상품 결과가 비면 LLM이 상품을 만들지 못하는지
mock/API-free 테스트로 검증했습니다. 실제 외부 API, Git push, 배포는 수행하지
않았습니다.

## 2026-07-24 Outbound and cache hardening

Codex가 Stage 1 JSON/REST payload 계약을 유지한 채 REST URL에 HTTPS/public IP,
userinfo·fragment·redirect 금지, DNS/IP 범위 검사와 선택적 exact host allowlist를
추가했습니다. 로컬 개발 endpoint는 명시적 설정으로만 허용합니다.

공식 web search cache에는 timezone 포함 생성시각, schema version, query·거래방향
binding과 기본 24시간 TTL을 추가했습니다. fresh cache hit, stale refresh, private
endpoint 차단, 로컬 opt-in을 API-free 테스트로 검증했습니다. 실제 외부 endpoint나
OpenAI web search 호출은 수행하지 않았습니다.
