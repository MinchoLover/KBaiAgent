# MVP Delivery Brief

## Product

- Name: 수출입 환율·현금흐름 리스크 Copilot
- One-sentence purpose: 무역문서 추출, 시장 시나리오, 결정론적 현금흐름 계산,
  헤지·공식상품 후보, 검증된 보고서를 사람 확인 게이트가 있는 상태 기반 워크플로로
  연결한다.
- Target user: 수출입 중소기업의 재무·자금 담당자
- Core problem: 문서 추출값과 환율 가정, 현금계획, 헤지 검토가 분리되어 있어 입력
  오류와 유동성 위험을 놓치고 계산·추천 근거를 추적하기 어렵다.

## Primary journey

1. 사용자가 PDF/이미지 무역문서를 안전하게 업로드하거나 가상 데모 문서를 연다.
2. 추출된 통화·금액·결제일과 원문 근거를 검토하고 명시적으로 확인한다.
3. 워크플로가 구조화된 환율 시나리오를 받아 `Decimal` 현금흐름과 헤지 후보를
   결정론적으로 계산하고, 공식 출처가 있는 상품 후보만 연결한다.
4. 보고서 생성 결과를 독립 critic이 검사하고, 필요하면 한 번만 재작성한 뒤 안전한
   결정론 보고서까지 포함한 최종 상태와 trace를 보여준다.

## Definition of done

A user can:

- 기존 Streamlit 버튼 흐름과 전체 오프라인 데모를 그대로 사용할 수 있다.
- 확인 전 계산이 차단되고, 외부 Stage/API 실패 시 표시된 fallback 결과를 받을 수 있다.
- 기업 재무 담당자 관점의 업무 용어로 거래 확인, 환율 가정, 현금 영향, 대응 전략,
  상담 후보와 리포트 흐름을 이해할 수 있다.
- JSON, validator code, provider와 workflow trace는 필요할 때만 고급 영역에서 확인할
  수 있다.
- 각 Stage 상태, provider, fallback, 경고, critic 및 재작성 횟수를 trace에서 확인할 수 있다.

The team can verify:

- Streamlit 없이 오케스트레이터만 실행해 Stage 0~5 결과를 얻는다.
- 같은 금융 입력은 같은 Stage 2/3 계산 결과를 만들고 전체 API-free suite가 통과한다.
- Stage 1 REST가 내부 주소를 호출하지 않고, 공식 검색 cache가 TTL을 넘으면 재검색한다.

## P0 scope

1. 기존 Stage 모델 위에 `WorkflowState`, 공통 `StageResult`, 안전한 trace를 도입한다.
2. 확인 게이트와 Stage 순서, 실패·fallback·종료 조건을 오케스트레이터로 이동한다.
3. 보고서 critic 결과·1회 재작성·fallback 사유를 구조화하고 상품 근거 경계를 강화한다.
4. 오프라인 데모와 Streamlit을 같은 오케스트레이션 경로에 연결하고 문서·테스트를 갱신한다.

## Non-goals

- Stage 1 팀의 예측 모델 또는 JSON/REST 계약 재구현
- 완전 자율형 멀티에이전트, 자동 금융 자문·상품 승인 판단
- Stage 2 계산식이나 Stage 3 grid 점수의 변경
- 실제 OpenAI 호출, 실제 공식 웹 검색, 배포·인증·중앙 로그 구축

## Constraints

- Deadline/session goal: 기존 동작을 보존하는 점진적 리팩터링
- Required stack: Python 3.9, Pydantic 2, Streamlit, 표준 `unittest`
- Existing repository constraints: `Optional`/`List`/`Dict`, 금융 `Decimal`,
  날짜 `date`/`datetime`, Stage 1 adapter 계약 유지
- External services: OpenAI 및 Stage 1 REST는 선택 사항이며 API key 없이 완주해야 한다.
- Security/privacy constraints: 문서 원문, 업로드 bytes, API key, 개인정보를 trace·로그·
  dataset에 자동 저장하지 않는다.

## Acceptance tests

| Journey | Given | When | Then |
|---|---|---|---|
| Primary success | 확인된 가상 거래와 offline 설정 | 오케스트레이터를 실행 | Stage 0~5, 최종 보고서, 안전한 trace가 생성된다 |
| Validation failure | 필수 필드 또는 사용자 확인 누락 | downstream 실행 요청 | `WAITING_FOR_USER`이며 Cashflow가 실행되지 않는다 |
| External Stage 1 failure | 외부 adapter 오류 | 워크플로 실행 | ±3/5/10 수동 stress로 `FALLBACK`하고 경고를 남긴다 |
| Unsafe Stage 1 endpoint | 사설·loopback·metadata IP | REST 실행 요청 | network 호출 없이 차단하고 수동 stress로 전환한다 |
| Stale official cache | TTL을 넘긴 cache | 공식 web 검색 | cache를 사용하지 않고 live 검색을 시도한다 |
| Empty product state | 공식 근거 후보 없음 | 보고서 생성 | 임의 상품을 만들지 않고 빈 후보 상태를 명시한다 |
| Report failure | API/critic 재검수 실패 | 보고서 Stage 실행 | 최대 1회 재작성 후 결정론 fallback으로 종료한다 |

## Demo flow

1. `python -m streamlit run app.py`를 실행한다.
2. 사이드바의 `전체 오프라인 데모 실행`을 누른다.
3. Stage 2 시나리오, Stage 3 후보, Stage 4 공식 출처, Stage 5 보고서를 확인한다.
4. 실행 trace expander에서 case ID, Stage 순서, fallback 및 critic 상태를 확인한다.

## Assumptions to record

- 외부 시장 데이터가 없으면 수동 스트레스는 예측이 아닌 fallback 시나리오다.
- Stage 3 비용률·위험계수와 offline KB는 데모 가정/snapshot이며 실제 견적이 아니다.
- 계산 검증과 Git commit/push는 분리하며, 원격 반영은 명시적으로 요청된 범위에서만
  수행한다.
