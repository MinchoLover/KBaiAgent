# KBaiAgent 계정 이전용 작업 이관 문서

작성일: 2026-08-02 (Asia/Seoul)
저장소: 현재 KBaiAgent 저장소 루트

## 0. 범위와 한계

이 문서는 새 계정에서 KBaiAgent 작업을 안전하게 이어가기 위한 기술 이관 문서다.

- 대화 전체의 완전한 원문 transcript는 아니다.
- 이전 대화 일부는 시스템에서 요약·압축되어 원문 그대로 다시 읽을 수 없다.
- 숨겨진 시스템·개발자 지침과 내부 추론은 포함하지 않는다.
- 현재 보존된 사용자 요구사항, 구현 상태, Git 상태, 테스트 증거와 주의사항을 최대한 충실하게 재구성했다.
- 정확한 원문 대화는 기존 계정의 데이터 내보내기 또는 대화 저장 기능으로 별도 확보해야 한다.

## 1. 프로젝트 목적

KBaiAgent는 중소기업·개인사업자의 수출입 거래문서를 분석해 다음을 지원하는 금융 의사결정 보조 서비스다.

- 거래문서 추출과 사용자 확인
- canonical confirmed transaction 생성
- 환율 변동에 따른 원화 수취·지급 영향
- 기업 현금흐름 및 운영자금 영향
- 거래국 경제환경과 양국 무역통계
- 결제·대금 회수 위험
- 상담 우선순위 Top 3
- 공식 금융지원 후보 최대 3개
- 상담 준비서, 통합 보고서와 JSON 다운로드

금융 계산은 결정론적 코드가 담당한다. LLM은 문서 추출 또는 검증된 결과의 제한된 설명에만 사용하며 승인·심사·가입 결과를 확정하지 않는다.

## 2. 저장소 작업 규칙

사용자가 제공한 `AGENTS.md` 규칙:

- Python 3.9 호환을 유지하고 타입은 `Optional`, `List`, `Dict`를 사용한다.
- 금융 계산은 `Decimal`, 날짜는 `date`/`datetime`을 사용한다.
- LLM 출력은 사용자 확인과 결정론 검증 전 계산에 전달하지 않는다.
- 문서 원문, 비밀값, 실제 업로드를 로그·dataset에 자동 저장하지 않는다.
- Stage 1 팀 모델을 재구현하지 않고 JSON/REST adapter 계약을 유지한다.
- 테스트셋은 파인튜닝 후보에서 항상 제외한다.
- 변경 후 `python scripts/verify.py`를 실행한다.

반복 지정된 Git 안전 규칙:

- 기존 staged, unstaged, untracked 변경을 삭제하거나 되돌리지 않는다.
- `git reset`, `git restore`, `git clean`, `git stash`, rebase를 사용하지 않는다.
- 현재 HEAD가 과거 기준보다 앞서 있으면 과거 HEAD로 돌아가지 않는다.
- 기존 커밋을 amend하지 않는다.
- 사용자 승인 없는 commit과 모든 Git push를 수행하지 않는다.

## 3. 핵심 도메인 불변조건

1. 계약상 선지급 조건과 실제 선지급 입금 상태는 별도 개념이다.
2. `amount_due`는 계약상 지급예정 노출액이며 실제 현재 미수금 확정값이 아니다.
3. USD 100,000은 계약상 예정 수취 노출액이다.
4. USD 80,000은 잔금 회차이며 전체 `amount_due`를 대체하지 않는다.
5. USD 20,000이 이미 입금됐다고 추측하지 않는다. 실제 입금 상태는 `UNKNOWN`이다.
6. 국가 경제지표는 거래처 부도확률이나 지급불능 확률이 아니다.
7. 국가 경제지표와 무역통계는 환율 계산, 헤지 비율, 현금흐름 계산을 변경하지 않는다.
8. 상담 Top 3와 공식 금융지원 후보 최대 3개는 서로 다른 결과다.
9. q90 등의 분위수와 방향 score를 실제 발생확률로 표현하지 않는다.
10. 상품 자격·승인·한도·금리·보험료를 확정하지 않는다.
11. Golden, Baseline과 Stage 1~3 금융 계산식의 의미를 임의로 바꾸지 않는다.
12. 기존 Stage 3 헤지 계산과 외부 `kb_macro_ai` 연동은 별개다.
13. 브라질을 단순히 안전국가 또는 위험국가로 단정하지 않는다.

## 4. Golden 거래와 금융값

| 항목 | 값 |
|---|---|
| company_role | `SELLER` |
| trade_direction | `EXPORT` |
| seller_country | `KR` |
| buyer_country | `BR` |
| currency | `USD` |
| contract_date | `2026-07-29` |
| shipment_date | `2026-08-05` |
| due_date | `2026-08-20` |
| contract total | `USD 100,000` |
| amount_due | `USD 100,000` |
| installment 1 | `USD 20,000` |
| installment 2 | `USD 80,000` |
| 선지급 실제 입금 여부 | `UNKNOWN` |
| 결제조건 | Open Account / T/T |
| 신용장·보험·보증 | 없음 |

날짜 invariant:

- 거래 확인, Stage 1 target, Stage 2 settlement/receipt, ConsultationPacket, Stage 5 JSON/Markdown/download 모두 `2026-08-20`을 사용한다.
- `contract_date=2026-07-29`를 결제일로 사용하면 안 된다.

금융값:

| 항목 | 값 |
|---|---:|
| 기준 원화 수취액 | 140,000,000원 |
| 환율 -5% 원화 수취액 | 133,000,000원 |
| 원화 수취 감소 | 7,000,000원 |
| 스트레스 후 예상 현금 | 8,000,000원 |
| 최소 유지 운영자금 | 10,000,000원 |
| 운영자금 부족 | 2,000,000원 |
| 현금 적자 | 0원 |
| 지급 또는 post-credit 부족 | 0원 |

상담 Top 3 고정 순서:

1. 수출대금 회수 보호 상담
2. 환율 관리 상담
3. 운영자금 버퍼·수출대금 회수시점 상담

기대 공식 후보, global unique 최대 3개:

- 한국무역보험공사 단기수출보험 검토
- KB국민은행 은행 선물환·외환스왑 상담
- 한국무역보험공사 환변동보험 검토

Stage 3가 `NO_FEASIBLE_CANDIDATE`일 때 사용자 문구:

> 현재 입력된 조건에서는 제시할 수 있는 헤지 비교안이 없습니다.

## 5. 대화와 작업 요청 연혁

### 5.1 최종 릴리스 안정화

단순 테스트 보고가 아니라 실제 UI·UX와 금융분석 전체 흐름을 실행하고, 릴리스 차단 문제를 production code에서 직접 수정하며 검증이 통과할 때까지 반복하라는 요청이었다.

범위에는 Git 상태 보존, 3분 데모와 실제 문서 흐름, Golden 계약값, 금융값, Top 3, 공식 후보, stale state, 오류 상태, 다운로드 payload, Chrome 데스크톱/모바일, 접근성·보안·성능, clean worktree와 전체 자동 검증이 포함됐다.

중간에 사용자는 남은 토큰과 진행률을 여러 차례 물었고 하던 작업을 마무리해 달라고 요청했다.

### 5.2 거래 확인 화면 UI

거래문서 분석 완료 후 거래 확인 화면만 정리했다.

- 거래 요약 우선
- 데스크톱 60~65% / 35~40% 2열
- 오른쪽에 핵심값 확인과 금융분석 CTA
- 모바일은 요약→확인→CTA→상세→원문→보조기능
- 중복 자동검증 안내 제거
- 완료 후 재분석 기능을 보조 위계로 낮춤
- 추출·검증·확정·금융 로직 불변

관련 커밋: `091b807 fix: simplify transaction confirmation layout`

### 5.3 API 연결과 자동 당사자 매칭

사용자는 API 미연결 이유를 물은 뒤 연결을 요청했다. 첨부 화면에서 Golden 문서가 `BUYER`, `UNKNOWN` 등으로 잘못 확인되는 문제를 보여주며 수정 없이 올바르게 추출할 방법을 요청했다.

검증된 문서 당사자와 회사 국가를 사용한 자동 당사자 매칭을 구현했다.

관련 커밋: `aefed83 fix: auto-match verified transaction parties`

### 5.4 금융 분석 UI

최종 사용자 흐름을 다음으로 정리했다.

1. 대금 회수 조건 확인
2. 회사 자금 입력
3. 환율·자금 위험 계산
4. 분석 핵심 결과
5. 상담 준비로 계속
6. 분석 근거와 상세정보

모델 분위수, raw provider, warning code, 뉴스 상세와 기술 metadata는 기본 화면에서 접었다. 계산 공식과 callback은 변경하지 않았다.

관련 커밋: `68fb51b fix: streamline financial analysis input and result flow`

### 5.5 공식 무역통계 production 기능

확정 거래의 회사 국가, 상대국, 방향과 선택적으로 확인된 HS Code로 공식 수출입 통계를 조회·검증·요약하는 독립 기능을 구현했다.

- 관세청 OpenAPI adapter
- live provider와 API-free 공식 fixture
- 공식 raw asset과 normalized snapshot
- schema/version/hash 검증
- 월별 수출·수입·무역수지
- 최근 12개월과 직전 12개월 집계 및 YoY
- 결측월·중복월·0 분모 처리
- HS 2·4·6·10단위 조건부 지원
- UI 차트, ConsultationPacket, Stage 5 연결
- stale state 및 금융 경계 테스트

관련 커밋:

- `f7c4e7b feat: add official bilateral trade statistics`
- `bc3daaf test: verify official trade statistics boundaries`
- `c98ac49 fix: make verification reproducible from clean checkout`

### 5.6 1회차 저장소 조사

코드를 변경하지 않고 entrypoint, navigation, extraction, canonical transaction, Stage 1~3, 국가환경, 무역통계, 결제위험, Top 3, 공식 후보, LLM, state, packet/report와 테스트를 읽기 전용으로 조사하는 단계였다.

향후 목표 탭은 거래 분석, 거래 위험, 상담 전략, 금융지원·보고서의 4개다.

### 5.7 2회차 국가 경제지표 AI 해석

검증된 `CountryTradeEnvironmentAssessment` 위에 GDP 성장률, CPI, 경상수지/GDP, OECD 분류를 쉬운 한국어로 설명하는 presentation 계층을 추가했다.

- 기존 `assessment.py` 판단과 `review_priority` 유지
- AI는 숫자·날짜·출처를 재작성하지 않음
- 국가위험점수, 부도확률, 환율전망, 상품추천 금지
- 결정론 validator와 fallback
- UI, packet, Stage 5 동일 결과
- fingerprint로 stale 결과 방지
- 실제 OpenAI 호출 없이 fake client 테스트

이 변경은 아직 commit되지 않은 정상 선행 작업이다.

### 5.8 3회차 무역통계 한 줄 해석

이미 검증된 관세청 통계를 재사용해 국가 전체 기준 네 지표와 제한된 한 줄 설명을 추가했다.

네 지표:

1. 최근 12개월 한국의 상대국 수출액
2. 최근 12개월 한국의 상대국 수입액
3. 최근 12개월 무역수지
4. 직전 12개월 대비 수출 증감률

AI는 `summary`와 `limitation` 한 문장씩만 생성한다. 숫자, 통화, 날짜, URL, Markdown, 위험판단, 환율예측, 상품추천, 순위·점수는 validator가 차단한다. AI 실패 시 deterministic fallback한다.

이 변경도 아직 commit되지 않았다.

### 5.9 계정 이전

사용자는 새로운 계정으로 이전하기 위해 대화 내용을 Markdown으로 요청했다. 완전한 원문 transcript는 컨텍스트 압축 때문에 불가능하다고 안내했고 이 이관 문서 작성에 동의했다.

## 6. 현재 Git 상태

- Branch: `feature/submission-benchmark-evidence`
- HEAD: `c98ac4946c084eb37429822bf80fab3422036b2b`
- 원격 대비: 8커밋 앞섬
- 최근 커밋: `c98ac49 fix: make verification reproducible from clean checkout`

최근 커밋:

```text
c98ac49 fix: make verification reproducible from clean checkout
bc3daaf test: verify official trade statistics boundaries
f7c4e7b feat: add official bilateral trade statistics
68fb51b fix: streamline financial analysis input and result flow
aefed83 fix: auto-match verified transaction parties
091b807 fix: simplify transaction confirmation layout
2406a57 test: cover final release candidate journeys
d49d06b fix: stabilize final financial analysis journeys
b165190 test: verify demo-first workflow navigation
d2bf444 fix: clarify api-free sample entry
b47ff5f feat: implement demo-first KB financial risk workspace
60d57a2 test: cover demo-first golden service journey
```

현재 tracked modified 파일:

```text
app.py
env.template
src/application/consultation_service.py
src/config.py
src/consultation/packet.py
src/domain/consultation_models.py
src/stage5/critic.py
src/stage5/deterministic_fallback.py
src/stage5/report_agent.py
src/ui/state.py
tests/golden_consultation_fixture.py
tests/test_completed_streamlit_service_journey.py
tests/test_golden_transaction_e2e.py
tests/test_trade_statistics.py
```

보호 대상 untracked 파일:

```text
PROJECT_DIRECTION.md
docs/FEATURE_MAPPING.md
docs/T4_COUNTRY_ENVIRONMENT_IMPLEMENTATION_PROMPT.md
```

절대 수정·삭제·이동하지 않는다.

2회차 untracked 파일:

```text
prompts/country_economic_interpretation.md
src/application/country_economic_interpretation_service.py
src/country_environment/interpretation_fallback.py
src/country_environment/interpretation_input.py
src/country_environment/interpretation_validator.py
src/domain/country_economic_interpretation_models.py
tests/test_country_economic_interpretation.py
```

3회차 untracked 파일:

```text
prompts/trade_statistics_interpretation.md
src/application/trade_statistics_interpretation_service.py
src/domain/trade_statistics_interpretation_models.py
src/trade_statistics/interpretation_fallback.py
src/trade_statistics/interpretation_input.py
src/trade_statistics/interpretation_validator.py
tests/test_trade_statistics_interpretation.py
```

이 문서 `KBaiAgent_ACCOUNT_HANDOFF.md`도 생성 후 untracked 파일이다.

## 7. 2회차 구현 구조

```text
verified CountryTradeEnvironmentAssessment
+ confirmed transaction context
→ deterministic interpretation input
→ optional OpenAI structured output
→ deterministic validator
→ validated AI result or deterministic fallback
→ UI / ConsultationPacket / Stage5 shared result
```

주요 특성:

- GDP, CPI, current account, OECD indicator allowlist
- prompt/schema/model/transaction/assessment fingerprint
- 숫자·상품·기관·순위·점수·금지판정 validator
- AI disabled, key 없음, call/parse/validation 실패 fallback
- `ENABLE_COUNTRY_ECONOMIC_INTERPRETATION=false`
- top-level Streamlit session state가 authoritative
- packet optional field와 report critic grounding
- 기존 국가환경 수치·기간·단위·출처는 deterministic renderer 사용

변경하지 않은 영역: `src/country_environment/assessment.py`, BR/US snapshot, `review_priority`, Stage 1~3, Top 3, 공식 후보.

## 8. 3회차 구현 구조

```text
verified TradeStatisticsResult (COUNTRY_TOTAL)
+ confirmed transaction fingerprint
→ deterministic direction projection
→ optional OpenAI structured output
→ deterministic validator
→ validated AI result or fallback
→ UI / ConsultationPacket / Stage5 shared result
```

수출 증감 enum: `INCREASED`, `DECREASED`, `UNCHANGED`, `UNAVAILABLE`
무역수지 enum: `SURPLUS`, `DEFICIT`, `BALANCED`, `UNAVAILABLE`

출력 계약:

```json
{
  "summary": "숫자 없는 한국어 한 문장",
  "limitation": "양국 전체 교역 참고정보의 한계를 담은 한 문장"
}
```

Golden fallback summary:

> 최근 양국 교역 자료에서 한국의 상대국 수출은 이전 비교기간보다 증가했습니다.

공통 limitation:

> 이 정보는 양국 전체 교역 흐름에 관한 참고자료이며 개별 거래처의 신용도나 대금 회수 가능성을 의미하지 않습니다.

기본 UI 순서:

1. 국가 전체 핵심 네 지표
2. 관측기간, 최근 집계기간, 직전 비교기간과 공식 출처
3. 검증된 한 줄 해석
4. 한계 문구
5. 접힌 월별 상세 추이
6. 접힌 HS 조회와 기술정보

기본 flag: `ENABLE_TRADE_STATISTICS_INTERPRETATION=false`
authoritative state: `trade_statistics_interpretation_result`

HS 기능은 유지했다. 현재 해석은 `COUNTRY_TOTAL`에만 연결해 HS 품목 결과에 국가 전체용 설명을 잘못 붙이지 않는다.

## 9. 공식 무역통계 Golden 값

- Source: `KOREA_CUSTOMS_SERVICE`
- Status: `OFFICIAL_FIXTURE`
- Scope: `COUNTRY_TOTAL`
- Snapshot version: `2026.08.01-kr-br-country-v1`
- 전체 관측기간: `2024-07~2026-06`
- 최근 집계기간: `2025-07~2026-06`
- 직전 비교기간: `2024-07~2025-06`

| 항목 | 결정론 원본 | 화면 표시 |
|---|---:|---:|
| 최근 12개월 수출 | 8,282,425,000 USD | USD 8,282,425,000 |
| 최근 12개월 수입 | 6,154,122,000 USD | USD 6,154,122,000 |
| 최근 12개월 수지 | 2,128,302,000 USD | USD 2,128,302,000 |
| 수출 YoY | 56.36383442142403103102139311% | +56.4% |
| 수입 YoY | -16.67620750760378846303822258% | -16.7% |

통계는 수출 FOB, 수입 CIF, 금액 USD 기준이다. 정정·취하에 따라 과거 값이 변경될 수 있다.

## 10. AI 출력 안전 경계

두 interpretation validator는 다음을 차단한다.

- 아라비아 숫자, 퍼센트, 통화, 날짜, URL
- Markdown, HTML, 표, 제목
- 입력에 없는 지표와 중복 지표
- 안전국가·위험국가 단정
- 거래처 신용도, 부도, 지급불능, 회수 가능성 판단
- 환율 예측, 헤지 비율
- 보험·대출·보증·정책자금 추천 또는 가입 지시
- 기관명·상품명, 순위·점수·종합등급
- 자격·승인 확정
- 교역 증감과 거래 안전성의 인과관계 확정

검증 실패 시 재작성 루프 없이 즉시 deterministic fallback한다.

## 11. Packet와 Stage 5

추가된 optional packet field:

- `country_economic_interpretation`
- `trade_statistics_interpretation`

역호환 원칙:

- 필드가 없어도 기존 packet과 보고서가 동작한다.
- 화면이나 보고서에서 해석을 다시 생성하지 않는다.
- Stage 5는 packet의 검증 완료 문구를 그대로 사용한다.
- report LLM은 재작성·요약·수정 또는 새 숫자·판정을 추가할 수 없다.
- critic은 누락·변조와 존재하지 않는 source path를 차단한다.

## 12. 검증 증거

집중 테스트:

```text
python -m unittest tests.test_trade_statistics_interpretation -v
Ran 10 tests
OK
```

관련 무역통계, 국가해석, consultation, Stage 5, Golden 회귀 120 tests PASS.

Golden Streamlit AppTest에서 확인한 내용:

- 한국–브라질 국가 전체 교역
- 네 핵심 지표와 +56.4%
- fallback summary와 limitation
- packet `trade_statistics_interpretation`
- 월별 상세 차트 expander
- HS Code 미확인 안내
- 기존 금융값과 버튼 action 유지

공식 fixture verifier:

```text
python scripts/verify_trade_statistics_fixture.py
verified=true
month_count=24
```

마지막 전체 검증:

```text
python scripts/verify.py
Ran 619 tests
OK
VERIFY PASSED
```

추가 결과:

- `python -m compileall app.py src`: exit 0
- `git diff --check`: exit 0
- live OpenAI, 관세청, World Bank, OECD, WTO 호출 없음
- fixture, snapshot, baseline regeneration 없음

## 13. 보호 해시

| 파일 | SHA-256 |
|---|---|
| `PROJECT_DIRECTION.md` | `4739d0db7087cdd61e20f5c444114ba661f46972b655528bac5307bc042f8e63` |
| `docs/FEATURE_MAPPING.md` | `e0e6ae03a3d40614da8a739e6f641bcaaa0bd66a4f53808a0c71449986c33a08` |
| `docs/T4_COUNTRY_ENVIRONMENT_IMPLEMENTATION_PROMPT.md` | `5a3b28721722367e49f1737406059546dc8116ede064f9b343857d78869836d3` |
| Golden PDF | `5330a1a572488005f7b02cccfc7150fbaa8b38c84bb9290da1e0c6e1c3a0a91c` |
| Golden expected | `3df4f925bbc34687f60f9bc822deafdb637e460f7269364a210d1a805a7292c3` |
| Baseline | `e839d8ecb8fa6203ef1204d313b839dae28358b34aec03c0e8d30b1328c451c0` |
| Country snapshot | `f4175a0e53dd84d3ea564f2289637ee0a10196dc85f5880bda52da5b061feb37` |
| Trade raw | `16fcfc5222aab3e9b58dc3481cd130c411dbbcb4b103f994a1b42d872edb9cb5` |
| Trade snapshot file | `a0fabc7fc26c9a90d2ee3f69e597d75e2a8a5089a899dee751d17467bb3f838f` |

Normalized canonical hash: `3e3120223e00013fcfbe9168bb794be21834c3c329b58d618fa84c09308e6b5b`

## 14. 명시적 수정 금지 영역

- `src/stage1/*`, `src/stage2/*`, `src/stage3/*`
- `src/domain/stage2_models.py`
- `src/application/stage2_input_service.py`
- `src/country_environment/assessment.py`
- 국가환경 및 무역통계 raw/snapshot
- 관세청 adapter response contract와 Decimal 집계
- Golden dataset/PDF/expected 값
- `reports/baseline_metrics.json`
- 상담 Top 3 규칙과 `CATEGORY_PRIORITY_RULES`
- 공식 상품 catalogue와 shortlist 정책
- `kb_macro_ai` adapter
- amount_due, confirmed transaction, due date 의미
- 금융 공식, stress 값, 공식 후보 최대 3개 정책

실제 버그가 의심되면 몰래 변경하지 말고 근거·영향·수정 전후를 먼저 보고한다.

## 15. 미검증과 남은 위험

- 실제 OpenAI live 품질은 검증하지 않았다.
- 실제 관세청 live keyed 응답은 이번 해석 회차에서 호출하지 않았다.
- 마지막 회차는 Streamlit AppTest까지 수행했으나 실제 Chrome 육안 검수는 하지 않았다.
- 전체 4개 탭 UI 개편은 아직 구현하지 않았다.
- HS 품목별 one-line interpretation은 의도적으로 구현하지 않았다.
- 2회차와 3회차 변경은 아직 commit되지 않았다.

## 16. 향후 4개 탭 구조

1. 거래 분석: 업로드, 확인·수정, 환율·현금흐름
2. 거래 위험: 국가 경제환경, 무역통계, 결제·회수 조건
3. 상담 전략: 규칙 기반 Top 3와 근거
4. 금융지원·보고서: 공식 후보 최대 3개와 다운로드

UI 개편 시 계산 로직을 재작성하지 말고 기존 renderer와 결과 객체를 조합하는 방식이 우선이다.

## 17. 새 계정에서 먼저 할 점검

```bash
git branch --show-current
git rev-parse HEAD
git status --short
git status
git log --oneline --decorate --graph -25
git diff --stat
git diff
git diff --cached --stat
git diff --cached
git ls-files --others --exclude-standard
```

확인사항:

- branch가 `feature/submission-benchmark-evidence`인지
- HEAD가 `c98ac4946...`와 같거나 더 최신인지
- 2회차와 3회차 변경이 그대로 있는지
- 보호 대상 세 파일과 공식 asset 해시가 같은지
- 기존 작업을 지우는 Git 명령을 실행하지 않았는지

## 18. 새 계정용 재개 프롬프트

```text
현재 열려 있는 KBaiAgent 저장소 작업을 이어서 수행해라.

먼저 저장소 루트의 KBaiAgent_ACCOUNT_HANDOFF.md와 AGENTS.md를
완전히 읽고 실제 저장소 상태와 대조해라.

중요:
- 현재 working tree에는 정상적인 2회차 국가 경제지표 AI 해석과
  3회차 무역통계 한 줄 해석 변경이 commit되지 않은 상태로 존재한다.
- 이를 reset, restore, stash, clean, checkout, rebase로 지우지 않는다.
- PROJECT_DIRECTION.md, docs/FEATURE_MAPPING.md,
  docs/T4_COUNTRY_ENVIRONMENT_IMPLEMENTATION_PROMPT.md를 수정·삭제·이동하지 않는다.
- Golden PDF, expected fixture, Baseline, 국가환경 snapshot,
  무역통계 raw/snapshot과 금융 계산을 변경하지 않는다.
- 외부 live API를 임의로 호출하지 않는다.
- commit과 push는 사용자의 명시적 요청 전까지 수행하지 않는다.

현재 기준:
- branch feature/submission-benchmark-evidence
- 기준 HEAD c98ac4946c084eb37429822bf80fab3422036b2b
- 마지막 전체 verify 619/619 PASS
- 무역통계 fixture verifier PASS
- Golden 네 지표와 금융값은 handoff 문서 값을 유지한다.

새 작업 전 handoff 내용과 실제 상태가 일치하는지 읽기 전용으로 확인하고,
불일치가 있으면 추측하지 말고 보고해라.
```

## 19. 최종 요약

그대로 재사용할 수 있는 것:

- canonical confirmed transaction과 Stage 1~5
- 거래 확인/금융 분석 UI, 자동 당사자 매칭
- 공식 국가환경 assessment와 해석 계층
- 관세청 무역통계 provider/fixture/summary와 한 줄 해석 계층
- ConsultationPacket, Stage 5 grounding/critic
- Golden AppTest와 전체 619개 검증

아직 할 수 있는 것:

- 실제 OpenAI와 관세청 live 확인
- 실제 브라우저 데스크톱/모바일 육안 검수
- 4개 탭 UI 개편
- 후속 상담 규칙과 공식 후보 작업
- 사용자 승인 시 2회차·3회차 변경의 논리적 commit

가장 위험한 통합 지점:

- canonical transaction 변경과 downstream stale state
- AI 설명이 결정론 값 또는 금융 판단을 오염시키는 경로
- 국가환경/무역통계가 Stage 1~3 또는 Top 3에 영향을 주는 경로
- UI와 packet/report가 서로 다른 결과를 재계산하는 경로
- 보호 대상 untracked 파일이나 공식 snapshot을 잘못 정리하는 작업

---

이 문서를 생성하면서 기존 tracked/untracked 파일을 삭제·복구·초기화하지 않았고 commit과 push를 수행하지 않았다.
