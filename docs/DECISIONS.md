# Engineering Decisions

## 1. Evaluation before fine-tuning

정답·few-shot·규칙·지표를 먼저 만들었습니다. 파인튜닝은 prompt와 validator로 해결되지
않는 반복 오류가 live baseline에서 확인될 때만 별도 검토합니다.

## 2. Strict model output, deterministic trust

Responses API structured parse로 syntax/schema를 강제하되 semantic truth는 믿지 않습니다.
evidence와 충돌 규칙을 일반 코드가 판정하고 사람이 핵심 세 필드를 확인합니다.

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
