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

1. `문서 확인`에서 PDF/이미지 또는 가상 데모를 열고 핵심 거래값을 원문과 대조한다.
2. `위험 진단`에서 거래처·결제·보호조건을 확인하고, 환율 범위와 회사 자금 방어선을
   입력해 결제·회수 검토 우선도와 추가 부담·지급 부족을 각각 계산한다.
3. `대응안 비교`에서 안정성·균형·비용 관점의 계산상 후보와 선택적 공식 정보를
   비교한다.
4. `상담자료`에서 은행에 확인할 질문과 준비서류가 포함된 Markdown 보고서를 받는다.

## Definition of done

A user can:

- 네 개의 업무 단계만 보고 전체 오프라인 데모를 완주할 수 있다.
- 확인 전 계산이 차단되고, Stage 1 HTTP 실패 시 표시된 file/mock fallback 결과를
  받을 수 있다.
- 21거래일 밖 결제에는 모델 분위수 환율을 적용하지 않고 고정 스트레스만 계산한다.
- 핵심 거래값, 불리한 경우 추가 부담, 최저 현금잔고와 신용 후 부족을 먼저 확인한다.
- 수입 선지급·계약이행 위험과 수출대금 회수 위험을 구분하고, 정보가 없으면
  `UNKNOWN` 상태와 확인할 항목을 받는다.
- 결제·회수 위험에 맞는 상담 범주, 확인 질문과 준비서류를 보고서에서 받되 특정
  상품 가입이나 승인 결과로 오해하지 않는다.
- 상담 범주와 직접 연결되고 공식 출처가 확인된 후보만 최대 3개 받으며, 매칭이
  없으면 상품을 임의 생성하지 않은 빈 상태를 확인한다.
- 내부 오류 code, JSON, provider와 workflow trace는 접힌 개발·감사용 영역에서만
  확인한다.
- 대응 후보가 금융 추천이 아니라 가정 기반 비교안임을 이해할 수 있다.
- 각 Stage 상태, provider, fallback, 경고, critic 및 재작성 횟수를 trace에서 확인할 수 있다.

The team can verify:

- Streamlit 없이 오케스트레이터만 실행해 Stage 0~5 결과를 얻는다.
- 같은 금융 입력은 같은 Stage 2/3 계산 결과를 만들고 전체 API-free suite가 통과한다.
- Stage 1 REST가 내부 주소를 호출하지 않고, 공식 검색 cache가 TTL을 넘으면 재검색한다.

## P0 scope

1. 기존 여섯 Stage 탭과 일곱 단계 표시를 네 개의 사용자 업무 단계로 통합한다.
2. 문서 확인에서 핵심 필드와 추가 문서정보를 분리하고 validation code를 쉬운
   행동 문구로 바꾼다.
3. 환율 근거·추가 자금·계산표는 접고 위험 상태와 핵심 금액 네 개를 먼저 표시한다.
4. 대응 후보의 순위 표현을 제거하고 사람이 읽는 상담자료 다운로드를 우선한다.
5. 사용자 확인된 거래처·선지급·잔여대금·보호수단으로 결제·회수 검토 우선도를
   결정론적으로 표시하되 숫자 신용점수나 자동 승인 판단은 만들지 않는다.
6. 확인된 상담 범주를 공식 source record와 결정론적으로 연결하고 사용자에게는
   직접 맞는 후보만 최대 3개 표시한다.

## Non-goals

- Stage 1 팀의 예측 모델 또는 JSON/REST 계약 재구현
- Stage 2/3의 환노출·ledger·후보 점수 계산식 변경
- 자동 금융 자문·상품 승인 판단 또는 실제 은행 견적 연결
- production 인증·중앙 로그·배포 구조 추가

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
| Primary success | 확인된 가상 거래와 offline 설정 | 대표 데모를 실행 | 네 업무 단계에 계산 결과와 상담자료가 표시된다 |
| Navigation | 초기 앱 | 화면을 연다 | 문서 확인·위험 진단·대응안 비교·상담자료 네 탭만 표시된다 |
| Information hierarchy | 위험 계산 완료 | 결과를 본다 | 핵심 금액 네 개가 상세 계산표보다 먼저 표시된다 |
| Import settlement risk | 신규 수입 거래처, 30% 선지급, 보호수단 없음 확인 | 거래조건을 확인 | 수입 선지급·계약이행 `우선 검토 필요`와 구체적 근거가 표시된다 |
| Export collection risk | 신규 수출 거래처, Open Account 90일, 보호수단 없음 확인 | 거래조건을 확인 | 수출대금 회수 `우선 검토 필요`와 구체적 근거가 표시된다 |
| Unknown protection | 보호수단 정보가 없음 | 거래조건을 확인 | 없음으로 간주하거나 감경하지 않고 `정보 확인 필요`로 표시된다 |
| Risk boundary | 결제·회수 우선도가 높음 | 결과를 저장 | Stage 2 현금 또는 Stage 3 환헤지 비율을 직접 변경하지 않는다 |
| Financial response mapping | 확인된 수입 선지급 또는 수출채권 회수 위험 | 상담자료를 생성 | 거래방향에 맞는 보호기능·질문·준비서류가 생성되고 특정 상품 승인 결과는 만들지 않는다 |
| Official candidate shortlist | 보호기능 상담 범주와 공식 Stage 4 검색 결과 | 공식 정보 연결 | 공식 출처·거래방향·범주가 모두 맞는 후보만 최대 3개 표시하고 자격·승인을 확정하지 않는다 |
| No grounded official candidate | 상담 범주와 직접 맞는 공식 record 없음 | 공식 정보 연결 | 빈 후보와 미매칭 사유를 표시하고 상품을 생성하지 않는다 |
| Packet binding | 거래·보호조건 confirmation이 변경됨 | 상담자료를 다시 생성 | trade-risk fingerprint가 packet hash에 반영되고 이전 자료와 구분된다 |
| Plain-language validation | 원문 근거 불일치 | 문서 검토 화면을 본다 | 내부 code 대신 필드명과 확인 행동이 표시된다 |
| Validation failure | 필수 필드 또는 사용자 확인 누락 | downstream 실행 요청 | `WAITING_FOR_USER`이며 Cashflow가 실행되지 않는다 |
| External Stage 1 failure | 외부 adapter 오류 | 워크플로 실행 | ±3/5/10 수동 stress로 `FALLBACK`하고 경고를 남긴다 |
| Stage 1 web success | 제공 web JSON과 확인된 spot | 21일 이내 수입/수출 거래 분석 | 수입은 v36 up, 수출은 v34 down 분위수를 사용한다 |
| Horizon mismatch | 결제일이 21거래일 이후 | 모델 JSON을 연결 | 모델 값은 문맥으로만 보존하고 금액은 고정 stress로만 계산한다 |
| Uncalibrated direction | `probability_calibrated=false` | 보고서·Stage 2 생성 | 기대손실 확률가중치와 실제확률 문구가 생성되지 않는다 |
| Unsafe Stage 1 endpoint | 사설·loopback·metadata IP | REST 실행 요청 | network 호출 없이 차단하고 수동 stress로 전환한다 |
| Stale official cache | TTL을 넘긴 cache | 공식 web 검색 | cache를 사용하지 않고 live 검색을 시도한다 |
| Empty product state | 공식 근거 후보 없음 | 보고서 생성 | 임의 상품을 만들지 않고 빈 후보 상태를 명시한다 |
| Report failure | API/critic 재검수 실패 | 보고서 Stage 실행 | 최대 1회 재작성 후 결정론 fallback으로 종료한다 |

## Demo flow

1. `python -m streamlit run app.py`를 실행한다.
2. 첫 화면 또는 사이드바 설정에서 `수입기업 대표 데모`를 불러온다.
3. 문서 확인 → 위험 진단 → 대응안 비교 → 상담자료 네 화면을 순서대로 확인한다.
4. 필요할 때만 개발·감사용 실행 기록에서 provider, fallback과 critic을 확인한다.

## Assumptions to record

- 외부 시장 데이터가 없으면 수동 스트레스는 예측이 아닌 fallback 시나리오다.
- Stage 3 비용률·위험계수와 offline KB는 데모 가정/snapshot이며 실제 견적이 아니다.
- 계산 검증과 Git commit/push는 분리하며, 원격 반영은 명시적으로 요청된 범위에서만
  수행한다.
