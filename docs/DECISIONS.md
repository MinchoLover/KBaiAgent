# Engineering Decisions

## 1. Evaluation before fine-tuning

정답·few-shot·규칙·지표를 먼저 만들었습니다. 파인튜닝은 prompt와 validator로 해결되지
않는 반복 오류가 live baseline에서 확인될 때만 별도 검토합니다.

## 2. Strict model output, deterministic trust

Responses API structured parse로 syntax/schema를 강제하되 semantic truth는 믿지 않습니다.
evidence와 충돌 규칙을 일반 코드가 판정하고 사람이 회사 역할·거래 방향·통화·금액·
결제일 다섯 필드를 확인합니다.

## 3. One canonical quote

내부 환율은 항상 KRW per 1 foreign currency입니다. 원천의 100 JPY 표시 등은 adapter가
정규화해 금융 엔진에 단위 분기를 남기지 않습니다.

## 4. Exposure and cash are separate

자연상계·기존 헤지 후 open exposure와 실제 결제/수취 cashflow를 별도 계산합니다.
기존 헤지는 risk에서 빠져도 cash contract이므로 ledger에 유지합니다.

## 5. Safe degradation

API key 없음은 오류가 아니라 demo + manual stress + offline KB + deterministic report
정상 경로입니다. 외부 Stage 1 실패도 표시된 manual fallback으로 이어집니다.

## 6. Official candidates, not recommendations

Stage 4는 allowlist 공식 URL만 사용하고 자격·승인·가격은 unknown으로 둡니다.
Stage 3/4 문구는 후보와 상담 필요를 유지합니다.

## 7. Orchestrator over Stage rewrites

기존 Stage 0~5 함수와 Pydantic 계약은 이미 테스트되어 있으므로 재구현하지 않습니다.
공통 `WorkflowState`와 `StageResult`로 감싸 순서·gate·fallback·trace만 한 곳에서
관리합니다. Stage 1 팀 JSON/REST adapter와 Stage 2 계산 결과를 그대로 보존하는
점진적 경계입니다.

## 8. Trace metadata, not payload logging

실행 trace에는 case ID, Stage, 시간, provider, fallback, 안전한 근거 참조와 경고만
기록합니다. 문서 원문, evidence source text, 확인 금액, 업로드 bytes, API key는
기록하지 않습니다. 디버깅 상세보다 금융·문서 데이터 최소화를 우선합니다.

## 9. Stage 1 contract preservation with outbound policy

팀의 Stage 1 JSON/REST payload schema는 변경하지 않습니다. 대신 URL 요청 경계에서
HTTPS, public IP, userinfo·fragment·redirect 금지와 선택적 exact host allowlist를
검사합니다. 로컬 개발 호환성은 기본 완화가 아니라
`STAGE1_ALLOW_PRIVATE_ENDPOINTS=true`의 명시적 opt-in으로 유지합니다. DNS rebinding을
완전히 제거하려면 production egress proxy가 필요하다는 한계는 남깁니다.

## 10. Time-bounded official search cache

공식 검색 cache의 file mtime이나 상품 설명만으로 최신성을 추정하지 않습니다.
timezone 포함 `cached_at`, schema version, query·거래방향 binding을 가진 envelope를
저장하고 기본 24시간 TTL을 적용합니다. timestamp가 없거나 미래·만료 상태면 live
검색을 다시 시도하고, 실패하면 기존 orchestrator의 offline 공식 KB fallback을
사용합니다.

## 11. Company finance user first, advisor report second

Context: 기존 화면은 Stage 번호, JSON, provider, grid, validator와 workflow trace를
업무 입력과 같은 위계에 노출해 기업 담당자용 화면인지 상담자·운영자용 화면인지
불명확했습니다.

Alternatives considered: 은행·보험기관 상담자용 case management UI로 전환하거나,
기업 담당자와 상담자 화면을 동시에 제공하는 방안을 검토했습니다.

Decision: P0 사용자는 수출입 중소기업의 재무·자금 담당자로 고정합니다. 앱은 거래문서
확인에서 현금 영향과 대응 후보 비교까지의 self-service 흐름을 제공하고, 상담자는
Stage 5 리포트를 전달받는 downstream 이해관계자로 둡니다. JSON, validator,
provider/fallback과 trace는 접힌 고급 영역에 유지합니다.

Rationale: 현재 입력 모델은 회사 현금, 운영자금, 대출한도, 보유외화처럼 기업 내부
정보를 중심으로 하며, 인증·고객목록·상담 메모·quote workflow 같은 상담자용 제품
요건은 MVP에 없습니다.

Trade-off: 운영·심사 데모에서 기술 상태를 한눈에 보기는 어려워졌지만, 모든 감사
데이터는 제거하지 않고 고급 영역에서 계속 확인할 수 있습니다.

Revisit condition: 거래은행용 다중 고객 case management, 역할별 권한과 상담 이력
요구가 P0가 될 때 별도 advisor view를 설계합니다.

## 12. Risk codes before consultation copy

위험 설명과 금융 대응을 LLM이 자유생성하지 않습니다. Stage 2 결과의 손실, 최소
운영자금 부족, 현금 적자, 대출한도 반영 후 부족과 정보 누락을
`src/consultation/risk_classifier.py`가 고정 코드와 근거값으로 분류합니다.
상담 범주는 거래 방향과 위험 코드의 명시적 mapping에서만 생성합니다.

이 선택은 표현의 다양성보다 재현성과 잘못된 금융 판단 방지를 우선합니다. 규칙에
없는 실제 KB 상품이나 적격성은 생성하지 않고 은행 검토 필요 상태로 남깁니다.

## 13. Deterministic consultation packet as the P0 report

P0의 필수 산출물은 Stage 3 헤지 grid나 Stage 4 상품 검색을 완료해야만 열리는 기존
확장 보고서가 아니라, Stage 2 직후 생성되는 JSON·Markdown 상담 패킷입니다. 패킷은
금융 숫자를 Stage 2 결과에서 직접 복사하고 계산 버전, 입력 hash, 환율 기준시각,
시나리오 ID, 원문 문서 hash와 사용자 확인 필드를 포함합니다.

LLM 보고서는 선택적 설명 계층으로 유지합니다. LLM 장애 또는 Stage 3/4 미실행이
핵심 상담 준비 흐름을 막지 않습니다.

## 14. Buffer risk is not payment failure

`maximum_buffer_shortfall`은 기업이 스스로 정한 최소 운영자금 방어선 미달이고,
`post_credit_shortfall`은 현금과 입력한 대출한도 반영 후에도 남는 자금 부족입니다.
상담 패킷에서는 후자를 `payment_gap_krw`로 명명합니다. 현재 수입 대표 사례는
확정 유입 40,000,000원과 비용 45,000,000원을 반영해 전자가 2,600,000원이고
후자가 0원이므로 지급불능으로 분류하지 않습니다.

## 15. Stage 1 web forecast and legacy scenarios coexist

Context: 기존 Stage 1 계약은 절대 환율 배열이지만 `kb_macro_ai`의
`krw_forecast_web_v1`은 spot이 없는 21거래일 상대 경로위험과 방향 score를
제공합니다.

Decision: 기존 `Stage1ScenarioSet` adapter를 제거하거나 바꾸지 않습니다. 새
HTTP/file/mock provider가 원본 forecast를 별도 DTO로 검증하고, 독립 spot provider와
`ScenarioBuilder`가 검증된 절대 환율을 만들어 기존 Stage 2 경계로 전달합니다.

Trade-off: Stage 1 표현 DTO와 계산용 scenario DTO가 둘 다 존재하지만, 모델 문맥과
금융 숫자의 신뢰 경계를 코드로 분리할 수 있습니다.

Revisit condition: Stage 1이 안정적인 공식 absolute-rate contract를 제공하고 양 팀이
공용 schema version을 합의한 경우 adapter 중복을 줄일 수 있습니다.

## 16. Direction scores never become cash-flow probabilities

`probability_calibrated=false`인 v25 up/down 값은 `score`와
`MARKET_CONTEXT_ONLY`로 저장합니다. Stage 2 scenario의 `probability`는 null이고
expected loss·buffer probability 같은 확률 가중 지표를 만들지 않습니다. v36/v34
quantile도 발생확률이 아니라 예측분포의 경로위험 분위수로 표시합니다.

## 17. Horizon mismatch removes model rates from calculation

21거래일 종료일을 prediction date에서 평일 기준으로 계산합니다. 최종 결제일이 그
범위를 넘으면 model quantile rate는 시장 문맥에만 남기고 Stage 2 계산용 set에는
BASE와 ±3/5/10 고정 스트레스만 포함합니다. 기존의 경고 후 대체 적용은 legacy
adapter 호환용으로만 남기며 새 web integration 경로에서는 사용하지 않습니다.

## 18. Separate spot provenance

Stage 1 상대수익률에 기준환율을 임의로 보충하지 않습니다. 공식 KoreaExim adapter,
사용자 확인 수동 입력, 표시된 demo fixture 순서로 `SpotQuote`를 만들며 source,
as-of, quote convention, 확인 여부를 함께 보존합니다. live 모드에서 셋 다 없으면
분석을 차단합니다.

## 19. Normalize before validating document semantics

자연어 국가명, 날짜 placeholder, 화면용 금액 문자열을 곧바로 ISO/date/Decimal
검증기에 넣지 않습니다. 독립 normalizer가 raw 값을 audit에 남긴 뒤 내부 계약으로
정규화하고, 실제 source text를 재사용할 수 있는 경우에만 evidence를 보완한 다음
trade type을 판정합니다.

사용자 지정 IMPORT/EXPORT는 자동판정보다 우선하지만 자동 결과와 다르면 경고를
남깁니다. 자동판정과 사용자 지정의 출처를 confirmation record에 보존해 이후
Stage 2 재검증도 같은 결과를 재현합니다. 확인되지 않은 국가 별칭이나 원문 없는
currency evidence는 추정하지 않습니다.

## 20. Exact evidence repair stays deterministic

Context: 이미지형 합성 계약서에서 당사자 값과 원문 인용이 이미 반환됐는데도
`buyer_country=CA`가 `MISSING_CORE_EVIDENCE`로 차단됐습니다. 처음에는 누락 field만
다시 읽는 두 번째 LLM 호출도 검토했습니다.

Decision: 각 핵심값에는 정확히 같은 field의 비추론 evidence를 요구하고, 이름·국가가
한 줄에 있으면 현재 값과 당사자 방향을 일반 코드로 대조해 evidence를 연결합니다.
지원 데이터의 국가 별칭과 대문자 ISO 독립 토큰을 판정하되, 일반 단어와 충돌할 수
있는 소문자 2글자 매칭은 하지 않습니다. 검증 실패를 감추기 위한 두 번째 LLM 호출은
추가하지 않습니다.

Rationale: 이번 실패는 모델 누락이 아니라 validator의 캐나다 코드 판정 누락이었고,
결정론 규칙 수정만으로 동일 live 문서가 PASS했습니다. 추가 호출 없이 비용과 새로운
환각 표면을 줄이고, 실제 evidence가 없을 때는 계속 fail closed 상태를 유지합니다.

Revisit condition: 허가된 live baseline에서 실제 원문 인용 누락이 반복되고, 독립 OCR
대조를 포함한 evidence-only 보정의 이득이 측정될 때 별도 설계합니다.

## 21. Four user tasks over six internal Stages

Context: 기존 Streamlit은 내부 Stage 0~5를 여섯 탭과 별도 일곱 단계 진행표로
노출했습니다. 화면 캡처에서는 사용자 확인 항목과 validator code, 긴 데이터 표가
동시에 보여 비전공자가 현재 행동을 파악하기 어려웠습니다.

Decision: 내부 함수와 workflow state는 그대로 유지하면서 사용자 내비게이션을
`문서 확인`, `위험 진단`, `대응안 비교`, `상담자료` 네 업무 단계로 통합합니다.
Stage 1/2와 Stage 3/4는 각각 같은 사용자 탭에 순서대로 표시합니다. 기본 화면은
핵심 결과와 다음 행동을 우선하고 provider, 원본 JSON, 계산표와 trace는 접힌
상세 영역에 둡니다.

Rationale: 금융 계산 경계를 바꾸지 않고도 사용자의 의사결정 순서와 내부 구현
구조를 분리할 수 있습니다. evidence 확인과 사람 confirmation은 숨기지 않고 문서
단계의 필수 행동으로 유지합니다.

Trade-off: 한 사용자 탭에 두 내부 Stage가 연결되므로 소스의 `with stageN_tab`
구조는 당분간 남습니다. 대회 프로토타입 이후 화면 모듈을 독립 함수로 분리할 때
내부 이름을 정리할 수 있습니다.

Revisit condition: 다중 사용자 case 관리나 역할별 화면이 P0가 되면 Streamlit 탭이
아닌 page router와 별도 상담자 화면을 검토합니다.

## 22. Settlement risk is a separate confirmed, deterministic assessment

Context: 기존 Stage 1은 환율 경로위험, Stage 2는 현금·유동성, Stage 3은 가정 기반
환헤지 후보를 담당합니다. 신규 거래처, 수입 선지급, 수출 사후송금, 신용장·보험·
보증 여부를 이 계산에 섞으면 서로 다른 위험의 대응수단이 혼동됩니다. 또한
`has_insurance=false` 같은 기본값은 “없다고 확인”과 “정보 없음”을 구분하지
못합니다.

Decision: 번호가 붙은 새 Stage를 만들지 않고 consultation 보조 분석으로
`TradeSettlementRiskInput`과 독립 confirmation fingerprint를 둡니다.
`advance_payment_ratio`의 저장 단위는 0~1 `Decimal` 문자열이고 화면에서만
0~100%로 변환합니다. 일부 선지급 후 잔액 조건을 표현하기 위해
`balance_payment_method`를 사용하며 신용장 여부 boolean은 추가하지 않습니다.
보호수단은 `UNKNOWN`, `NONE_CONFIRMED`, `DETAILS_PROVIDED`와 종류·현재 거래
적용범위로 나눕니다. 문서 근거가 있는 결제조건만 prefill하고 사용자가 확인한
snapshot만 규칙 엔진에 전달합니다.

수입은 `IMPORT_PREPAYMENT_PERFORMANCE_RISK`, 수출은
`EXPORT_RECEIVABLE_COLLECTION_RISK` 규칙표를 따로 사용합니다. 출력은 임의의
0~100 점수 대신 `STANDARD_REVIEW`, `ELEVATED_REVIEW`, `HIGH_REVIEW`,
`UNKNOWN` 검토 우선도와 규칙별 근거를 제공합니다. 수출 90일은 공식 등급 경계가
아닌 공개된 MVP 장기조건 추가 검토 기준입니다. 적용범위가 확인되지 않은 보호수단은
위험을 낮추지 않으며, 확인된 보호수단도 최대 한 단계만 낮춥니다. 신용장은 발행은행,
확인 여부, 서류조건을 평가하지 않으므로 그 존재만으로 위험 제거로 처리하지 않습니다.

Boundary: 이 평가는 환율 시나리오, 원화 cash ledger, 헤지 후보 또는 상품 승인·
보험 인수 가능성을 변경하지 않습니다. 결제·회수 입력 변경은 기존 Stage 1~3 결과를
보존하고 이 평가와 이를 참조할 수 있는 후속 공동 산출물만 무효화합니다. 문서 확인
값이 바뀌면 거래 fingerprint가 달라지므로 기존 평가를 폐기합니다.

Trade-off: 국가·은행·거래처 신용 데이터가 없는 MVP이므로 부도확률이나 신용등급을
제공하지 못하지만, 설문 점수 대신 문서 조건·사용자 확인·결정론 근거의 경계를
감사할 수 있습니다.

Revisit condition: T4 국가·무역환경 위험 또는 T5~T7 금융 대응·보고서 연결을
구현할 때도 이 우선도를 환율 위험과 합산하지 않고 별도 축으로 유지합니다. 90일
기준과 규칙 강도는 전문가 검토 및 사례 데이터로 검증된 뒤 version을 올려 변경합니다.

## 23. Trade-risk responses reuse consultation topics, not product selection

Context: T2·T3는 결제·회수 위험의 원인과 검토 우선도까지 제공하지만 사용자가
은행에 어떤 기능을 문의하고 어떤 서류를 준비할지는 연결하지 않았습니다. 반대로
현재 정보만으로 특정 상품, 가입 가능성, 한도나 승인 결과를 만들면 근거 범위를
넘습니다.

Decision: 새 추천 엔진이나 Stage를 만들지 않고 기존 `ConsultationTopic` 계약의
필요정보·준비서류·질문 구조를 재사용합니다. `TradeRiskReviewNeed`를 다음 상담
범주로 결정론 매핑합니다.

- 수입 선지급 보호 검토 → `IMPORT_ADVANCE_PAYMENT_PROTECTION`
- 수출채권 회수 보호 검토 → `EXPORT_RECEIVABLE_PROTECTION`
- 신용장 상세 검토 → `DOCUMENTARY_CREDIT_TERMS_REVIEW`
- 불명확한 지급조건 → `PAYMENT_TERMS_REVIEW`
- `UNKNOWN` 정보 → `TRADE_RISK_INFORMATION_REVIEW`

각 topic에는 근거가 된 trade-risk factor code와 review need를 별도 필드로 저장합니다.
상담 패킷에는 `TradeSettlementRiskAssessment`와 그 input fingerprint를 포함해
거래조건이 바뀌면 packet hash도 달라지게 합니다. Markdown에는 한국어 위험 유형,
우선도, 원인, 질문과 준비서류를 표시하고 내부 category는 JSON 감사정보로만
유지합니다.

Rationale: 기존 환율·유동성 상담 흐름과 결제·회수 대응을 한 자료에서 볼 수 있지만
환율위험은 환헤지, 유동성위험은 결제자금, 결제·회수위험은 보증·보험·신용장 조건
검토로 계속 분리됩니다. 모든 topic은 generic consultation category이며 사람과
거래은행 심사를 최종 판단으로 유지합니다.

Trade-off: 공식 상품명이나 신청 자격을 즉시 보여주지 않지만, 근거 없는 추천을
피하고 이후 T6 공식 출처 후보 연결에 사용할 안정적인 기능 단위를 확보합니다.

Revisit condition: T6에서 공식 후보를 연결할 때도 topic과 공식 source record를
분리하고, source가 없거나 오래됐으면 후보를 생성하지 않습니다.

## 24. Official retrieval and the user-facing shortlist are separate

Context: 기존 Stage 4 검색은 공식 KB 또는 허용된 공식 웹 출처에서 관련 문서를
넓게 찾는 retrieval 계층이며 최대 8건을 반환합니다. 이를 그대로 사용자에게
보여주면 현재 상담 필요 항목과 직접 관계없는 제도까지 섞이고, 기존 JSON·샘플
계약의 후보 수를 바꾸면 Stage 4 회귀 범위가 불필요하게 커집니다.

Decision: `Stage4Result`는 기존 retrieval 계약으로 유지하고, application 계층에서
`OfficialCandidateShortlist`를 별도로 만듭니다. T5의 `ConsultationTopic.category`와
공식 KB의 `ProductRecord.category`를 공개된 결정론 테이블로 연결하고, 공식 HTTPS
allowlist·거래방향·검증상태를 다시 확인한 후보만 최대 3개 표시합니다. 각 후보에는
연결된 상담 범주를 저장하고 상담 패킷 hash에는 product ID, 공식 URL, 자료 확인일과
매칭 범주를 포함합니다.

수입 선지급 보호는 K-SURE `수입보험(수입자용)`, 수출채권 보호는 K-SURE
`단기수출보험` 공식 제도 snapshot과 직접 연결합니다. 두 항목 모두
`eligibility=unknown`, `approval_status=consultation_required`를 유지하며 대상
물품·거래·기업, 보험료, 한도와 인수 여부를 확정하지 않습니다. 현재 상담 범주와
직접 맞는 공식 후보가 없으면 빈 shortlist와 미매칭 범주를 반환하고 상품을 만들지
않습니다.

Rationale: 사용자에게는 근거 있는 소수 후보만 보이면서도 기존 Stage 4 검색과
Stage 5 보고서 계약을 보존할 수 있습니다. 환율·유동성·결제위험 계산은 shortlist
때문에 변경되지 않고, 후보는 계산 결과가 아니라 상담 준비용 공식 정보입니다.

Trade-off: 공식 snapshot은 자료 확인일 이후 조건 변경을 자동 반영하지 않으며,
실시간 이용 가능성을 보장하지 않습니다. 공식 웹 검색이 활성화되더라도 shortlist
정책과 사람 확인 경계는 동일합니다.

Revisit condition: T7 최종 보고서 통합 시에도 raw retrieval 목록이 아니라 이
shortlist만 사용자용 보고서에 전달하고, 공식 출처의 갱신 주기·만료 정책을 별도
운영 기준으로 정합니다.

## 25. The consultation packet is authoritative for the final report

Context: T6 이후 기본 상담 패킷과 Streamlit 후보 화면은 최대 3개 shortlist를
사용하지만, 기존 Stage 5 확장 보고서는 Stage 4의 원시 검색 후보 최대 8건을 직접
LLM과 template에 전달했습니다. 이 상태에서는 같은 case에서 화면·상담 패킷·확장
보고서의 상품 수가 다르고, 거래·결제 위험과 대응 근거도 확장 보고서에서
누락됩니다.

Decision: 기존 Stage 0~4 bundle과 Stage 5 생성·critic·1회 수정·fallback 구조는
유지하고 `ConsultationPacket`을 선택적 추가 입력으로 전달합니다. 패킷이 있으면
거래·결제 위험, 상담 항목과 공식 후보는 `consultation.*` 경로만 사용자용 근거로
사용합니다. Stage 4는 mode·query·원시 후보 수 등 retrieval audit metadata만
보고서 bundle에 남기고 원시 후보 이름·기관·URL은 제거합니다. 상품 섹션은
`consultation.official_candidate_shortlist.candidates`의 최대 3개만 인용합니다.

critic은 다음을 추가로 거부합니다.

- 패킷이 있는데 `stage4.candidates`를 상품 근거로 사용
- 공식 후보와 다른 상품명·기관명·URL
- shortlist가 비었는데 상품을 생성
- 상품 이용 자격이나 승인 가능성 확정
- 근거 없는 거래·결제 위험 또는 금융 대응
- 검토 우선도를 공식 심사등급·부도확률·보험 인수판단으로 표현
- 결제·회수 위험 때문에 환헤지 비율을 직접 변경

Rationale: 보고서가 T2~T6의 결정론적 근거를 그대로 이어받고, LLM은 숫자·위험·
상품을 새로 선택하지 않는 설명 계층으로만 남습니다. 상담 패킷이 없는 기존 호출은
Stage 4 legacy 계약으로 계속 동작해 하위 호환성을 유지합니다.

Trade-off: Stage 4 원시 후보를 보고서 JSON에서 직접 감사할 수는 없지만 workflow의
Stage 4 결과와 trace에는 그대로 남습니다. 보고서에는 사용자가 실제로 보게 되는
shortlist만 보존하는 편이 오해 가능성이 낮습니다.

Revisit condition: 별도 case 저장소를 도입하면 report가 참조한 packet hash와 Stage 4
retrieval artifact ID를 영속적으로 연결하고, 보고서 재생성 이력을 case audit으로
관리합니다.

## 26. Country validation documents stay isolated from the regression baseline

Context: 미국·브라질 거래의 스캔·사진 문서와 의도적 누락 사례를 검증해야 하지만,
기존 16개 합성 문서와 샘플 1건의 manifest·fixture·regression baseline에 합치면
기존 품질 수치가 데이터 구성 변경 때문에 달라집니다. 이미지 label의
`source_text`를 production OCR이 검증한 evidence로 오해할 위험도 있습니다.

Decision: `dataset/country_validation`에 문서 8건, label, fixture prediction,
manifest를 별도로 둡니다. 모두 test split이고 사람 승인·사용자 확인·파인튜닝
자격을 false로 고정합니다. PDF는 텍스트 레이어가 없는 실제 이미지형 PDF로 만들고
사진에는 제한적인 원근·그림자·압축을 적용합니다. label evidence는 렌더링 원문과
일치하는 평가용 ground truth로만 사용하며 Stage 0의 `OCR_REQUIRED`와 필드별 사용자
확인 정책을 약화하지 않습니다.

Rationale: 기존 회귀 지표를 보존하면서도 Balance Due, 분할결제, 사건 기준 날짜,
통화 누락과 국소 가림을 독립적으로 반복 평가할 수 있습니다. 고정 seed와 고정 PDF
metadata로 재생성 결과도 byte 단위로 비교할 수 있습니다.

Trade-off: fixture prediction은 label 복사이므로 evaluator 파이프라인만 검증하며
실제 모델·OCR 정확도를 측정하지 않습니다. 사건 기준일·통화·결제일이 안전하게
비어 있는 사례는 exact match여도 자동 문서 PASS가 아닐 수 있습니다.

Revisit condition: 사용자가 실제 API 비용을 명시적으로 허가하면 최대 2건부터
`predictions/live`와 별도 live 보고서로 측정합니다. 승인된 익명 문서가 생겨도
기존 test split이나 baseline은 자동 갱신하지 않습니다.

## 27. Country signals are separate review context, not a country rating

Context: T4는 미국·브라질 거래에서 OECD 지급·이전, World Bank 거시환경,
WTO 무역·시장접근 원자료를 상담자료에 연결해야 합니다. 세 자료는 정의·기준일·
관측기간이 다르므로 하나의 숫자나 국가등급으로 합치면 공식 원자료보다 강한
주장을 만들게 됩니다. 특히 OECD의 브라질 원값 `4`와 고소득 OECD 회원국인
미국의 미분류 상태를 자체 등급이나 `0·LOW`로 바꾸면 안 됩니다.

Decision: `src/integration_assets/country_environment/snapshot_v1.json`의
versioned offline snapshot을 strict schema·version·canonical SHA-256 hash로
검증합니다. 세 축은 `CountryTradeEnvironmentAssessment` 안에서 분리하고,
`STANDARD_REVIEW`, `ELEVATED_REVIEW`, `HIGH_REVIEW`,
`INSUFFICIENT_INFORMATION`만 거래 검토 우선순위로 사용합니다. 이 우선순위는
보험·보증·신용장·결제조건 상담 순서를 설명할 뿐 국가 신용등급·부도확률·은행
승인 판단이 아닙니다.

T4는 사용자 확인된 거래 상대국과 기존 거래·결제조건만 입력받는 auxiliary
workflow입니다. fingerprint에는 canonical 거래조건, 국가, snapshot
version/hash, rule version, source record ID를 포함합니다. 변경 시 T4,
`ConsultationPacket`, T7 보고서만 다시 만들고 Stage 1 환율, Stage 2 현금흐름,
Stage 3 헤지 후보, 기존 runtime Stage 4와 상품 eligibility·approval은 유지합니다.
World Bank·WTO 원값은 context-only이며 OECD와 합산하거나 환헤지 비율에
반영하지 않습니다.

Rationale: 외부 API·LLM 없이 같은 입력에 같은 결과를 재현하고, 공식 자료의
관측시점과 한계를 그대로 노출하면서 기존 계산·상품 계약을 보존할 수 있습니다.
packet이 T4를 포함하지 않으면 optional 필드가 직렬화되지 않아 기존 JSON과 hash
계약도 유지됩니다.

Trade-off: committed snapshot 검증일 이후 공식 자료 변경을 자동 반영하지 않고,
US·BR 외 국가는 `INSUFFICIENT_INFORMATION`으로 처리합니다. 개별 품목 관세,
통관조건, 보험 인수와 은행 승인은 별도 사람 상담이 필요합니다.

Revisit condition: 공식 원자료를 사람이 재검증해 새 snapshot version과 hash를
승인하거나 지원 국가를 확장할 명시적 범위가 생길 때 rule version·경계 테스트와
함께 재검토합니다.

## 28. Live benchmark runs are guarded, immutable evidence artifacts

Context: 기존 evaluator는 offline/live를 모두 지원했지만 `--mode live`만으로 전체
manifest를 호출할 수 있었고 기존 prediction을 덮어쓸 수 있었습니다. 한 사례의 API
오류가 전체 실행을 중단했으며 Git SHA, evaluator·prompt·manifest hash와 실행
상태를 묶는 run metadata도 없었습니다.

Decision: 기존 evaluator를 유지하면서 Live에 양수 `--max-cases`,
`--confirm-live`, 고유 `--run-id`를 모두 요구합니다. manifest는
`synthetic_document=true`, `real_customer_document=false`, test split,
파인튜닝 제외와 승인된 합성문서 경로를 fail closed로 검사합니다. prediction과
report는 `<root>/<run-id>`에 새로 만들고 기존 run은 덮어쓰지 않습니다. API 오류와
timeout은 원문·예외 메시지를 저장하지 않는 안전한 사례 실패 record로 남기고 다음
사례를 계속 평가합니다.

Run metadata는 호출 전에 `RUNNING`으로 먼저 쓰고 Git HEAD·dirty 여부, Python,
evaluator·prompt·manifest hash, model, 대상 건수와 시간대를 기록한 뒤
`COMPLETED`, `COMPLETED_WITH_FAILURES`, `INTERRUPTED`로 갱신합니다. API key,
전체 prompt·문서·payload·raw response는 저장하지 않습니다. Fixture에는
`model_accuracy_claim_allowed=false`와
`purpose=EVALUATOR_PIPELINE_VALIDATION`을 명시합니다.

Rationale: baseline 실패를 지우거나 성공처럼 합치지 않고, 코드·prompt·데이터
버전을 재현 가능한 최소 metadata로 고정할 수 있습니다. Live raw artifact는 Git에서
제외하되 합성 정답·fixture·manifest와 집계 근거 문서는 계속 추적합니다.

Trade-off: 실패 run을 같은 ID로 resume하지 못하고 새 ID로 재실행해야 합니다.
표본 8건과 독립 OCR 부재 때문에 Live 결과도 실제 고객문서 성능으로 일반화할 수
없습니다.

Revisit condition: 승인된 운영 benchmark 저장소와 접근통제·보존정책이 생기면
immutable artifact ID, 중앙 cost ledger와 승인 audit을 별도 서비스로 이동합니다.
