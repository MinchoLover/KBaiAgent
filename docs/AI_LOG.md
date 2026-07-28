# AI Use Log

## 2026-07-29 P1-A guarded Live benchmark evidence

Codex가 기존 evaluator를 교체하지 않고 Live 실행에 양수 `--max-cases`,
`--confirm-live`, 고유 `--run-id`, 합성 test-only manifest 검증과 immutable
run 디렉터리를 추가했습니다. 사례별 API 오류·timeout을 안전한 실패로 격리하고
Git·Python·evaluator·prompt·manifest hash, model, 시간, 성공·실패·token을 raw
prompt·문서·API response 없이 기록합니다. Fixture prediction에는
`evaluation_mode=FIXTURE`, `model_accuracy_claim_allowed=false`,
`purpose=EVALUATOR_PIPELINE_VALIDATION`을 명시했습니다.

mock 기반 신규 11개 테스트를 포함한 API-free 전체 394개 테스트, country fixture
8건 평가, 기존 regression과 `scripts/verify.py`가 통과한 뒤 사용자가 승인한 합성
문서 2건만 `gpt-4o-mini`로 호출했습니다. API/구조화 응답은 2건 성공,
실패·timeout 0건, 평균 latency 9.46초, input/output token 77,623/1,254였습니다.
공식 단가를 입력하지 않아 비용은 `UNKNOWN`입니다.

통화·금액·분할금액·날짜는 두 사례에서 일치했지만 국가 ISO 정규화와 거래방향은
실패했습니다. 독립 OCR text layer가 없어 accepted evidence는 0%였고 두 사례 모두
`OCR_REQUIRED`·사용자 확인 gate로 계산 전달을 차단했습니다. Baseline을 지우거나
국가 별칭·prompt를 즉시 수정하지 않았습니다. 전체 8건은 두 번째 승인 전 실행하지
않았고 Live raw artifact, API key, `.env`, 실제 고객문서와 Git push는 범위에서
제외했습니다.

## 2026-07-29 US/Brazil synthetic document validation set

Codex가 기존 17건 manifest와 regression baseline을 유지한 채 미국·브라질 합성
무역문서 8건을 별도 데이터셋으로 생성했습니다. PDF 4건은 텍스트 레이어가 없는
스캔형이고 JPG 4건은 고정 seed의 원근·그림자·압축 효과를 사용합니다. 문서에는
가상 회사명과 법적 효력 없음 경고만 있으며 실제 주소·계좌·식별번호·로고·서명·
도장을 넣지 않았습니다.

`TradeDocumentExtraction` label, 문자 단위 렌더링 원문 evidence, fixture
prediction, manifest와 전용 테스트를 코드로 생성했습니다. Net 60만 기존 Python
정책으로 파생하고 B/L date·final acceptance·통화·가려진 결제일은 추측하지
않았습니다. 이미지 label evidence는 평가용 ground truth일 뿐 production OCR의
자동 검증으로 사용하지 않습니다.

fixture offline 평가는 evaluator 파이프라인 검증용으로만 실행했습니다. 실제
OpenAI/OCR/외부 API 호출, live prediction, baseline 갱신, 파인튜닝 포함, Git
commit·push는 수행하지 않았습니다. 초기 시각 검수에서 사진 원근 좌표 순서 때문에
문서가 회전한 결함을 발견해 수정하고 8건을 다시 열어 확인했습니다.

## 2026-07-29 Trade-risk final report grounding

Codex가 기존 Stage 5 생성·critic·1회 수정·결정론 fallback 구조를 유지하면서
상담 패킷을 확장 보고서의 추가 근거로 연결했습니다. 패킷이 있으면 거래·결제 위험,
금융 대응과 공식 후보는 `consultation.*` 경로만 사용하며, Stage 4 원시 후보의
이름·기관·URL은 LLM 입력에서 제거했습니다. 화면과 보고서의 공식 후보는 같은
shortlist 최대 3개입니다.

critic은 shortlist 밖 Stage 4 인용, 공식 후보명·기관명·URL 변조, 이용 자격·승인
확정, 근거 없는 거래위험·대응, 공식 심사등급·부도확률 표현, 결제위험에 따른
환헤지 비율 변경을 거부합니다. 수입·수출 fixture, 빈 shortlist, LLM mock과
결정론 fallback을 API-free 테스트로 검증했습니다. 문서 원문·비밀값은 보고서
bundle이나 trace에 추가하지 않았고 실제 OpenAI 보고서 호출·외부 메시지·배포·
Git push는 수행하지 않았습니다.

## 2026-07-28 P0 source-grounded evidence gate

Codex가 Stage 0의 evidence 존재 여부만 보던 검증을 원문 기반 검증으로 강화했습니다.
텍스트 PDF에서는 모델 인용문이 실제 페이지에 있는지 확인하고, 당사자·국가·통화·금액·
날짜·지급조건이 현재 canonical 값과 일치할 때만 evidence로 유지합니다. 잘못된 금액·
결제일 인용, 원문에 없는 당사자 인용은 `EVIDENCE_VALUE_MISMATCH` 또는
`EVIDENCE_NOT_IN_SOURCE`로 차단합니다. 이미지·스캔 문서는 독립 텍스트가 없으므로
`EVIDENCE_UNVERIFIABLE`과 `OCR_REQUIRED` 상태에서 field-level 사용자 확인 전에는
Stage 2로 전달하지 않습니다. 원문·업로드 bytes·비밀값은 로그나 dataset에 추가하지
않았습니다.

금액·결제일 위조 인용, 원문 부재 당사자, textless image, 실제 페이지 번호 복구,
명시적 사용자 override를 회귀 테스트로 추가했고 `python scripts/verify.py` 274개
테스트가 통과했습니다.

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
대표 사례의 최소 운영자금 부족 2,600,000원과 지급 부족 0원을 분리하고, 수출 대표
사례에서 환율 하락에 따른 `FX_RECEIPT_RISK`를 검증했습니다.

실제 OpenAI API, 외부 Stage 1 endpoint, 상품 web search, Git push와 배포는 수행하지
않았습니다. 전체 기능은 로컬 fixture, 수동/고정 스트레스, 결정론 계산·패킷으로
외부 서비스 없이 재현했습니다.

## 2026-07-28 Four-step UI simplification

Codex가 기존 Stage 0~5 함수, Stage 1 adapter, Stage 2/3 금융 계산과 confirmation
gate를 유지하면서 Streamlit 정보 구조를 네 개의 사용자 업무 단계로 통합했습니다.
어두운 운영 대시보드 테마는 밝은 B2B 금융 화면으로 바꾸고, 큰 hero와 복수 진행표를
간결한 헤더·네 단계 진행표로 축소했습니다.

문서 검토는 핵심 거래정보와 추가 문서정보를 분리하고 내부 evidence code 대신
필드별 확인 행동을 먼저 표시합니다. 환율 provider, 모델·뉴스 근거, 추가 자금정보,
시나리오 표, JSON과 trace는 삭제하지 않고 접힌 상세 영역으로 이동했습니다. 대응
후보는 `검토 순위`를 제거하고 안정성·균형·비용 관점의 계산상 비교안으로 표시하며,
상담자료는 사람이 읽는 Markdown 다운로드를 우선합니다.

Streamlit AppTest로 수입·수출 원클릭 데모, 네 탭, 사용자 수정 후 confirmation 무효화와
쉬운 evidence 안내를 검증했습니다. 실제 금융 숫자와 JSON/REST 계약은 변경하지
않았습니다.

## 2026-07-29 T4 country and trade environment review

Codex가 OECD, World Bank, WTO의 공개 1차 공식 자료를 사람이 검토할 수 있는
versioned offline snapshot으로 정리했습니다. snapshot에는 미국·브라질의 필요한
공개 원값, 기준일·관측기간, 공식 URL, 제한적 해석과 한계만 저장했으며 전체
페이지·PDF 응답, 문서 원문, 기업정보, 비밀값은 저장하지 않았습니다. runtime과
테스트는 외부 API를 호출하지 않습니다.

국가환경 엔진은 사용자 확인된 거래 상대국과 거래·결제조건만 입력받습니다.
OECD 지급·이전, World Bank 거시환경, WTO 무역·시장접근을 별도 축으로 보존하고
숫자 점수·가중치·국가 신용등급·부도확률을 만들지 않습니다. 미국 미분류는
`HIGH_INCOME_OECD_UNCLASSIFIED`와 raw null로, 브라질은 OECD 공식 원값 `4`와
보호수단 검토 행동 신호로 보존했습니다.

기존 `ConsultationPacket`, workflow auxiliary step, T5 topic, T7 critic·결정론
fallback과 Streamlit에 optional 연결했습니다. Stage 1 환율, Stage 2 Decimal
현금흐름, Stage 3 헤지 후보, runtime Stage 4 공식 검색과 상품 자격·승인은
변경하지 않았습니다. critic은 브라질 원값의 자체등급화, 미국 미분류의
LOW·0 변환, 세 축 합산점수, 공식 source 변조, 국가 신호에 따른 환헤지·현금흐름
변경과 승인 주장을 차단합니다.

API-free 전체 383개 테스트와 8건 country validation fixture 평가를 실행했습니다.
초기 집중 실행에서 안전 고지가 같은 줄의 잘못된 국가등급 주장을 가리는 critic
경계가 드러나 affirmative 오표현을 별도로 거부하도록 수정한 뒤 재검증했습니다.
OpenAI API, 외부 LLM, runtime 공식자료 API, live 문서 평가, 배포와 Git push는
실행하지 않았습니다.
