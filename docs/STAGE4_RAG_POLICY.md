# Stage 4 Official Source Policy

## OFFLINE_KB

`knowledge_base/official_products.json`을 lexical ranking합니다. 각 record에는 기관,
분류, 요약, 자격 상태, 공식 URL, 확인일, 근거 요약이 있습니다. URL이 allowlist를
통과하지 않으면 load 단계에서 제거합니다.

## OFFICIAL_WEB_SEARCH

기본 OFF이며 API 키와 `ENABLE_OFFICIAL_WEB_SEARCH=true`가 필요합니다. Responses API
`web_search`의 `allowed_domains` 필터와 반환 source를 모두 검사합니다. 공식 사용법:
[Web search tool](https://developers.openai.com/api/docs/guides/tools-web-search).

기본 allowlist:

- kbstar.com, kbfg.com
- ksure.or.kr
- kosmes.or.kr
- bizinfo.go.kr
- kodit.co.kr
- kibo.or.kr

결과는 `.cache/official_search/`에 질의·거래방향·모델·allowlist hash로 cache하며
Git에서 제외합니다. cache envelope에는 timezone 포함 `cached_at`을 기록하고 기본
24시간 TTL을 적용합니다. `OFFICIAL_SEARCH_CACHE_TTL_HOURS=0` 이하는 cache를
비활성화합니다. cache hit에서도 query, 거래방향, 현재 allowlist, HTTPS 규칙을 다시
검증하며 timestamp가 없거나 미래이거나 만료된 cache는 사용하지 않습니다.
web search가 실패하면 `WorkflowOrchestrator`가 offline 공식 KB로 전환하고
`fallback_used=True`를 기록합니다.

## 표현 규칙

- 자격, 승인, 금리, 한도는 확인되지 않으면 `unknown`
- URL·제목·확인일·핵심 근거가 없는 결과는 제외 또는 warning
- 민간 블로그·광고·allowlist lookalike 도메인 거부
- HTTPS가 아닌 URL 거부
- “후보”, “상담 필요”, “기관 확인 필요” 사용
- 대상 고객, 주요 조건, 필요 서류, 전략 연결 이유, 확인 상태, 제한사항 구조화
- 공식 근거 후보가 없으면 빈 candidates를 유지하고 LLM의 상품 생성 차단

offline KB의 예시는 한국무역보험공사, KB국민은행, 중소벤처기업진흥공단, 기업마당의
공식 페이지를 근거로 하며 상품 조건의 최신성은 상담 시 다시 확인해야 합니다.
