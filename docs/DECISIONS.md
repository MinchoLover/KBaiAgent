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
