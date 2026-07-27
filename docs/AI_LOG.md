# AI Use Log

## 2026-07-27 Stage 0 exact evidence integrity

Codex와 병렬 에이전트가 공유된 실패 화면의 `MISSING_CORE_EVIDENCE`를 추적했습니다.
프롬프트와 few-shot은 값이 있는 당사자·통화·금액·날짜·지급조건마다 정확한 field의
실제 원문 evidence를 요구하도록 맞췄고, `INFERRED`는 coverage에서 제외했습니다.
텍스트 PDF는 메모리 안에서 페이지 원문을 대조해 안전하게 당사자 evidence를 연결하며,
이미지형 PDF에서 누락이 남으면 `OCR_REQUIRED`를 표시합니다. 사용자가 값을 수정하면
이전 값의 evidence를 폐기하고 전체 검증을 다시 실행합니다.

실제 합성 `demo_net90_contract.pdf` 호출에서 값과 `(CA)` 인용이 존재하는데도
캐나다 코드 매칭표 누락 때문에 `buyer_country`만 차단되는 결정론 버그를 확인했습니다.
지원 국가 별칭과 대문자 ISO 토큰 판정을 보강한 뒤 같은 문서를 한 번 재호출해
`SALES_CONTRACT`, `validation_pass=true`를 확인했습니다. 문서 원문·업로드 bytes·
비밀값은 로그나 dataset에 저장하지 않았고, 별도 evidence 재추출 LLM 호출도
추가하지 않았습니다. 최종 API-free 전체 264개 테스트와 release gate가
통과했습니다.

## 2026-07-27 Stage 0 normalization and confirmation hardening

Codex가 문서 추출값을 계산 전에 정규화하는 경계를 추가했습니다. 자연어 국가 별칭은
검증 전에 ISO alpha-2로 바꾸고 raw 값과 변경 이력을 보존하며, 알 수 없는 별칭은
임의 추정하지 않습니다. 거래 방향은 정규화된 회사 역할과 양 당사자 국가로
결정론적으로 판정합니다.

통화 evidence는 기존 금액 evidence의 실제 원문에 같은 ISO 코드가 있을 때만
연결합니다. 날짜 placeholder는 null로 정리하고 Contract/Invoice Date 기준
calendar/business Net N 산술은 Python이 수행합니다. Streamlit 수정 후 전체 검증을
다시 실행하고 다섯 핵심값을 확인하기 전 Stage 2를 차단합니다. API-free 매매계약
fixture를 포함한 당시 전체 240개 테스트가 통과했습니다.

## 2026-07-27 Stage 1 integration and decision-flow hardening

Codex가 sibling `kb_macro_ai`의 `krw_forecast_web_v1` 계약을 읽기 전용으로
검증하고, 메인 저장소에 HTTP/file/mock provider, 별도 Spot provider,
21거래일 model-path/고정 스트레스 builder를 추가했습니다. v25 미보정 방향 점수는
시장 문맥으로만 보존하고 수입 v36 상승·수출 v34 하락 분위수를 서로 다른 불리
방향으로 연결했습니다. 90일 결제는 `HORIZON_MISMATCH`로 모델 환율 계산을
차단합니다.

Stage 2는 유리한 시나리오의 음수 손실을 0으로 분리하고 signed impact를 별도
보존합니다. Stage 3은 비용 가정과 q90·±10%·운영자금·신용 제약을 공개하는
안정성/균형/비용 후보와 infeasible 결과를 만듭니다. 보고서 LLM 입력에서 문서
원문 evidence를 제거하고 q90·미보정 점수·horizon·뉴스 오용 critic을 추가했습니다.
당시 API-free 전체 219개 테스트와 실제 Streamlit health, 실행 중인 sibling Stage 1
HTTP 응답 파싱을 검증했습니다.

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

## 2026-07-24 Stage 2 completion hardening

Codex가 사용자 확인 뒤 거래금액·통화·결제일이 바뀌어도 기존 gate 상태만으로 계산이
실행될 수 있던 경계를 보강했습니다. 문서 SHA, 회사 국가, 거래 방향·통화와 회차별
금액·결제일을 canonical fingerprint로 묶고 오케스트레이터가 확인 기록을 결정론적으로
재검증한 뒤 Stage 2 입력의 fingerprint와 실제 필드를 모두 대조합니다.

분할결제 수입에서 보유외화 배분 뒤 남은 회차별 금액에만 동일통화 흐름을 배분하도록
수정했고, 배분하지 못한 값은 고정 warning code로 공개합니다. 금액·날짜 입력 계약,
과도한 spread, 과거 현금흐름, 회차 sequence를 엄격히 검증하고 작은 aggregate hedge
fee의 비례 반올림이 음수가 되지 않도록 보강했습니다.

## 2026-07-24 Company finance UX redesign

Codex가 P0 사용자를 수출입 중소기업 재무·자금 담당자로 명확히 고정하고 Streamlit
표시 계층을 재설계했습니다. Stage 번호 중심 탭을 거래 확인, 환율 가정, 현금 영향,
대응 전략, 상담 상품, 상담 리포트의 업무 언어로 바꾸고, 현금 방어선 판정·최대
추가부담·최저 잔고·자금 부족을 결과 상단에 배치했습니다.

기존 계산, 확인 gate, Stage 1 adapter와 Stage 2/3 결과 계약은 변경하지 않았습니다.
JSON 다운로드, validator 상세, provider/fallback, critic과 workflow trace는 삭제하지
않고 접힌 고급 영역으로 이동했습니다. 헤지 조합은 금융 자문이 아닌 검토 순위로,
공식 상품은 자격·승인 미확정 상담 후보로 계속 표시합니다.

Streamlit AppTest의 전체 오프라인 데모와 금융 표시 formatter 테스트를 추가했습니다.
실제 Chrome headless 렌더링에서 1600px 전략 카드·현금 결과 화면과 820px 지표
재배치를 확인했으며, 폼 primary button의 최종 계산 스타일도 브라우저 computed
style로 확인했습니다.

## 2026-07-24 KB AI Challenge repositioning

Codex가 기존 Stage 2 금융 엔진과 Stage 1 JSON/REST 계약을 유지하면서 수출입 금융
의사결정 지원 수직 슬라이스를 구현했습니다. 거래 방향 사용자 확인,
`src/consultation/`의 결정론 위험 분류·상담 매핑, 버전형 JSON·Markdown 상담 패킷,
수입·수출 API-free 대표 데모와 Streamlit 결과 흐름을 추가했습니다.

위험 판정과 상담 패킷 숫자에는 LLM을 사용하지 않았습니다. 상담 후보는 공식 상품
추천이 아니라 일반 상담 범주이며 모두 은행 검토와 사람 판단을 요구합니다. 수입
대표 사례의 최소 운영자금 부족 600,000원과 지급 부족 0원을 분리하고, 수출 대표
사례에서 환율 하락에 따른 `FX_RECEIPT_RISK`를 검증했습니다.

실제 OpenAI API, 외부 Stage 1 endpoint, 상품 web search, Git push와 배포는 수행하지
않았습니다. 전체 기능은 로컬 fixture, 수동/고정 스트레스, 결정론 계산·패킷으로
외부 서비스 없이 재현했습니다.
