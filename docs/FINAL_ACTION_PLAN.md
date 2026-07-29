# KBaiAgent 제출 직전 최종 실행 계획

## 1. 실행 원칙

제출 전 목표는 기능 수를 늘리는 것이 아니라 이미 계산된 결과를 금융적으로
일관되고 상담 가능한 형태로 만드는 것이다.

1. P0는 숨기거나 문구로 덮지 않고 코드 계약과 테스트를 함께 고친다.
2. P1은 기존 risk finding·packet·official shortlist를 재사용한다.
3. 새로운 금융 계산, 임계값, 상품, eligibility rule은 추가하지 않는다.
4. Golden·Baseline은 immutable fixture로 취급한다.
5. 모든 코드 변경은 논리 단위 commit과 전체 API-free gate를 가진다.
6. Live API는 별도 승인·고유 run ID·합성문서·비용 상한이 있을 때만 실행한다.
7. 실제 고객문서는 사용하지 않는다.

## 2. 지금 즉시 할 일

### 2.1 P0-1 금융 입력 계약 확정

결정해야 할 질문은 하나다.

> `amount_due`가 문서가 말하는 실제 Balance Due인가, 아직 이행 여부를 확인하지
> 못한 예정 회차의 분석 노출인가?

현재 schema/prompt와 Decision 29가 서로 다른 답을 낸다. 먼저 제품·금융 owner가
다음 문서유형별 표를 승인해야 한다.

| 문서 유형 | 우선 source | 이미 지급/수취 표시 | 이행정보 없음 | 실제 outstanding |
|---|---|---|---|---|
| Invoice | 명시 Balance/Amount Due | paid를 반영한 balance | 명시 due 우선 | 문서 명시 범위 |
| Sales Contract | 명시된 예정 회차 | 완료 회차만 근거 있을 때 제외 | 예정 회차 합계 또는 별도 필드 결정 필요 | 별도 UNKNOWN 가능 |
| Purchase Order | 명시 결제/총액 조건 | 이행정보가 있으면 별도 검토 | 주문 총액 사용 조건 승인 필요 | 보통 UNKNOWN |

승인 뒤 하나의 commit에서 schema, extraction rule, validator, evidence recovery,
fixture, UI copy, README, Decision Log를 맞춘다. 일부 계층만 바꾸면 안 된다.

권장 commit:

```text
fix: align scheduled exposure amount contract
```

필수 gate:

```bash
python -m unittest tests.test_schemas_validators -v
python -m unittest tests.test_source_evidence_recovery -v
python -m unittest tests.test_golden_trade_demo -v
python scripts/run_regression.py
python scripts/verify.py
```

### 2.2 P0-2 수출 유동성 상담 연결

기존 `LIQUIDITY_BUFFER_RISK`를 수출에서도 상담 행동으로 연결한다. 새 대출 rule이나
승인 판단은 만들지 않는다.

최소 acceptance criteria:

- Golden -5% 2,000,000원 buffer shortfall가 “운영자금 버퍼 확인” topic의 숫자
  이유에 나타난다.
- `cash_deficit=0`, `post_credit_deficit=0`을 “지급불능”으로 표현하지 않는다.
- 실제 가용한도·대출 승인·필요 조달액은 UNKNOWN/은행 확인이다.
- 수입 `IMPORT_SETTLEMENT_FINANCE` 결과는 변하지 않는다.

권장 commit:

```text
fix: map export liquidity risk to consultation action
```

필수 gate:

```bash
python -m unittest tests.test_consultation -v
python -m unittest tests.test_stage5_decision_report -v
python -m unittest tests.test_ui_evidence_state -v
python scripts/verify.py
```

### 2.3 Golden split end-to-end test

Golden의 USD 20,000/80,000 회차를 그대로 사용해 Stage 1 target policy와 Stage 2
substitution warning을 검증한다. 현행 test처럼 USD 100,000 단일 잔금 노출로
축약하지 않는다.

먼저 정책을 결정한다.

- 첫 회차 target 하나를 모든 회차에 대체 적용하고 경고를 유지할지
- 마지막 회차를 대표 target으로 택할지
- 회차별 scenario set을 별도로 만들지

제출 직전에는 계산식을 넓히기보다 현행 “첫 회차 + 대체 적용 경고”를 정확히
테스트·설명하는 선택이 회귀 위험이 가장 낮다.

권장 commit:

```text
test: cover golden split schedule end to end
```

## 3. 제출 전 해야 할 일

### P1 우선순위

| 순서 | 작업 | 완료 조건 | 예상 |
|---:|---|---|---|
| 1 | 상담 1·2·3 view-model | 동일 입력 동일 순서, 이유 공개 | 1~2일 |
| 2 | topic별 숫자 결속 | USD/KRW, loss, threshold, buffer가 원 source path와 일치 | 1일 |
| 3 | 실제 입금이력 UNKNOWN | Golden 부족정보 첫 항목 | 0.5일 |
| 4 | expected decision·next action | 승인 아닌 상담 목표 문구 | 1일 |
| 5 | one-page handoff | 역할·회차·top3·서류·질문·fingerprint | 1~2일 |
| 6 | web search category 통합 | mocked web result → grounded shortlist | 1~2일 |
| 7 | 공식 source/KB CTA | 최신 출처와 사람 상담 경로 명시 | 0.5일 |
| 8 | 실제 slide deck | 3분 흐름·숫자·한계·backup | 1일 |

권장 논리 commit:

```text
feat: prioritize grounded consultation actions
feat: add consultation handoff summary
fix: preserve official categories in web shortlist
test: bind golden consultation evidence end to end
docs: add submission deck and rehearsal package
```

한 commit에 금융 계약, UI, web search, 발표자료를 섞지 않는다.

## 4. 기능 동결 후 할 일

기능 동결 시점부터는 다음만 허용한다.

- 문구 오탈자·링크 수정
- deterministic artifact SHA 확인
- API-free test·demo 반복
- screenshot·영상·발표자료 업데이트
- BLOCKER가 아닌 새 아이디어는 backlog 이동

동결 checklist:

```text
[ ] branch/HEAD 기록
[ ] git status에 의도한 파일만 존재
[ ] Golden SHA 일치
[ ] Baseline directory fingerprint 일치
[ ] protected untracked 3개 SHA 일치
[ ] compile PASS
[ ] 436+ unittest PASS
[ ] regression PASS
[ ] verify PASS
[ ] pip check PASS
[ ] git diff --check PASS
[ ] secret scan PASS
[ ] local link scan PASS
[ ] import/export demo PASS
[ ] Streamlit health ok
[ ] Golden packet top3와 숫자 대본 일치
```

## 5. 발표자료 작업

현재 저장소에는 `.pptx`, `.ppt`, `.key`가 없다. Markdown demo script와 judge Q&A만
있으므로 실제 발표산출물은 미완성이다.

### 권장 7장 구성

1. **문제**: 환율이 아니라 거래별 현금·상담 결정의 문제.
2. **한 장 흐름**: 문서 → evidence/확인 → stress → cash → 상담 packet.
3. **안전 경계**: AI 추출과 deterministic 계산 분리, scan fail-closed.
4. **Golden 숫자**: USD 100k, -5% 7m 감소, buffer 2m 부족.
5. **상담 top3**: 회수보호 → 환율관리 → 운영자금, 각각 서류·질문.
6. **공식 후보와 한계**: 최대 3, 출처, eligibility UNKNOWN.
7. **검증·요청**: 436 tests, Live 범위, KB handoff 확장.

### 각 장의 금지 표현

- “모든 문서를 정확히 읽습니다”
- “OCR 정확도 100%”
- “AI가 최적 상품/헤지를 추천합니다”
- “대출·보험 승인을 예측합니다”
- “BR 국가 신용등급 4”
- “USD 100,000 실제 미수 확정”
- “Golden Live end-to-end 성공”

## 6. 데모 리허설

### 6.1 3분 기본 경로

| 시간 | 행동 | 한 문장 |
|---:|---|---|
| 0:00~0:20 | 문제·사용자 | “계약 금액을 기업 현금과 은행 질문으로 바꿉니다.” |
| 0:20~0:45 | Golden 문서·evidence | “AI 값도 원문과 사람 확인 전 계산하지 않습니다.” |
| 0:45~1:15 | -5% 현금 영향 | “7백만원 수취 감소와 2백만원 buffer 부족을 분리합니다.” |
| 1:15~1:40 | 회수 위험·국가환경 | “Open Account 보호 검토와 국가 원자료를 섞지 않습니다.” |
| 1:40~2:20 | 상담 top3·공식 후보 | “상품 승인이 아니라 먼저 준비할 서류와 질문입니다.” |
| 2:20~2:45 | packet 다운로드 | “같은 숫자와 fingerprint를 상담자에게 넘깁니다.” |
| 2:45~3:00 | 검증·한계 | “436 API-free tests, Live와 실고객 범위는 제한적입니다.” |

### 6.2 리허설에서 반드시 구분할 값

- `amount_due`: 승인된 최종 계약 표현을 사용
- 실제 USD 20,000 입금 여부: `UNKNOWN`
- 거래·회수 priority: `ELEVATED_REVIEW`
- Golden 국가환경 priority: `STANDARD_REVIEW`
- BR OECD: raw 4, 자체 국가등급 아님
- -5% buffer shortfall: 2,000,000원
- cash/payment deficit: 0원
- Stage 3: 계산상 비교안, 실제 추천 아님
- shortlist: 상담 후보, 자격·승인 unknown

### 6.3 실패 주입 리허설

1. API key 없음 → deterministic demo/report.
2. textless scan → evidence 차단 화면.
3. Stage 1 HTTP 없음 → fixture/manual stress warning.
4. official candidate 없음 → 빈 상태, 상품 생성 금지.
5. report AI 실패 → deterministic report.

각 실패를 “장애”가 아니라 “공개된 안전 fallback”으로 설명하되, Live 성공인 것처럼
포장하지 않는다.

## 7. 영상 백업

제출 전 다음 두 영상을 별도로 만든다.

1. **3분 정규 영상**: Golden API-free path, top3 상담, packet download.
2. **60초 fail-closed 영상**: scan에서 Stage 2 차단, deterministic fallback.

영상과 함께 보관할 정적 backup:

- Golden PDF 첫·둘째 페이지 screenshot
- exact evidence 4개 screenshot
- -5% Stage 2 결과 screenshot
- 상담 top3 한 화면
- 공식 후보와 disclaimer
- packet Markdown 첫 페이지
- 436/436, verify, regression terminal 결과
- branch·commit·Golden SHA 표

영상에 실제 API key, `.env`, 전체 prompt, 로컬 사용자 경로, 고객정보를 노출하지
않는다.

## 8. 최종 Git 정리

각 commit 전:

```bash
git status --short
git diff --check
git diff --stat
git diff
git diff --cached --name-only
git diff --cached
```

검사 항목:

- 보호 untracked 3개 제외
- Golden PDF 제외
- Baseline prediction/report 제외
- `.env`, key, token 제외
- 예상하지 않은 code/generated file 제외
- commit message가 실제 변경 한 가지를 표현

마지막 제출 tag/commit을 만든 뒤에는 push 전에 별도 사용자 승인을 받는다. 본 감사
작업에서는 push하지 않는다.

## 9. 선택적 작업

제출에 여유가 있을 때만 한다.

- canonical 문서 index와 오래된 audit의 “historical” banner
- ` 2` 중복 파일 제거
- `app.py`의 상담 rendering만 작은 component로 추출
- CI에서 Python 3.9 compile/unittest/verify
- coverage report와 critical path branch 기준
- official source 갱신 runbook의 owner·주기·expiry
- presentation screenshot 자동화

이 작업들은 P0/P1과 deck보다 먼저 하면 안 된다.

## 10. 하지 말아야 할 작업

- 새 금융상품을 많이 추가
- 새로운 국가·통화·42/63일 모델 확장
- 금융 위험 임계값 또는 ranking 변경
- 자동 eligibility·승인·보험인수 추정
- 실제 주문·대출신청을 급하게 연결
- extraction prompt/schema를 한쪽만 임시 수정
- Golden PDF 재생성으로 문제를 덮기
- Baseline 덮어쓰기 또는 기대값 완화
- 대규모 `app.py` 리팩터링
- 실제 고객문서 Live 테스트
- 실패한 Golden Live를 성공으로 편집
- 국가 raw 값으로 자체 점수 만들기
- API key를 발표 PC·영상·로그에 노출
- release gate 없이 여러 기능을 한 commit에 묶기

## 11. 치명적 문제

| 문제 | 제출 영향 | 해소 조건 |
|---|---|---|
| `amount_due` 의미 충돌 | 금융 입력의 신뢰성 질문에 방어 불가 | 승인된 계약과 전 계층 테스트 일치 |
| 수출 liquidity 상담 누락 | 핵심 “위험→행동” 약속 단절 | Golden 2m가 상담 action과 packet에 연결 |

두 문제는 P0다. 현재 감사에서는 이전 범위 제한에 따라 코드 수정 대신 재현·patch
계획만 기록했다.

## 12. 보통 문제

- official web result가 shortlist와 category match되지 않음
- Golden split target과 단일노출 테스트 불일치
- 실제 payment history UNKNOWN이 missing gap에 없음
- 상담 priority·expected decision·actual KB CTA 없음
- 다른 내용의 duplicate ` 2` 파일
- 실제 presentation deck 없음
- prompt pack의 역사 `.env.example`에 현재 앱이 읽지 않는 키가 남음
- auth/tenant/AV/retention/central audit 없음
- CI·coverage·lint gate 없음

## 13. 개선 제안

가장 효과가 큰 순서:

1. 금융 입력 계약 일치
2. export liquidity mapping
3. top3 + 숫자 이유 + 부족정보
4. one-page KB handoff
5. official web integration test/fix
6. Golden split end-to-end
7. 실제 deck·영상·rehearsal
8. 운영 보안·RM 연동은 제출 후

## 14. 대상 가능성 평가

| 상태 | 점수 | 판정 |
|---|---:|---|
| 현재 코드 | 74/100 | 통과 가능 수준 |
| 상담 P0/P1·deck·검증 후 예상 | 86/100 | 본상 경쟁력 가능 |
| 대상 가능성 | 확정 불가 | 실고객 검증·KB 업무연동·상담 closure 부족 |

대상을 노릴 수 없다는 뜻이 아니라, 현재 증거로 “대상 경쟁력 있음”을 단정하면
과장이라는 뜻이다. 심사에서 architecture 안전성보다 사용자 행동 완결성을 더
강하게 본다면 현행 상담 gap의 감점이 크다.

## 15. 심사위원 관점 약점과 방어 질문

### Q1. 왜 `amount_due` 뜻이 코드와 발표에서 다릅니까?

현재는 실제 blocker다. 제출 전 하나의 계약으로 정렬해야 하며, 해결 전에는 “현재
미수”라고 말하지 않는다. 계약서 기반 예정 노출과 입금이력 기반 actual outstanding을
구분하는 것이 patch의 핵심이다.

### Q2. Golden Live가 성공했습니까?

아니다. 한 건의 API 응답에서 핵심값은 맞았지만 amount/date evidence 오류로 Stage 2가
차단됐다. recovery는 API-free로 검증했으며 수정 후 Live는 미실행이다.

### Q3. 스캔문서 정확도는 얼마입니까?

운영 정확도는 UNKNOWN이다. 합성 scan 8건에서 API 호출은 성공했지만 독립 OCR
evidence가 없어 Stage 2를 0/8 모두 차단했다. 이것은 OCR 정확도 0%가 아니라 자동
수용 evidence 0%다.

### Q4. 왜 상담이 다섯 개나 나오고 무엇을 먼저 합니까?

현행 topic은 category 생성 순서이고 priority가 아니다. 제출 전 기존 위험을 top3
view-model로 정리해야 한다. Golden 권장 순서는 회수보호, 환율관리, 운영자금이다.

### Q5. 2백만원 부족이면 대출이 필요합니까?

시스템은 그렇게 판단하지 않는다. 2백만원은 사용자 입력 목표 buffer 기준 부족이며
현금 적자와 신용 후 지급 부족은 0원이다. 최신 자금계획과 실제 한도를 상담에서
확인해야 한다.

### Q6. BR 4는 국가 신용등급입니까?

아니다. OECD 공식 원자료 classification 4이며 지급·이전 보호 검토 신호로만 쓴다.
World Bank·WTO와 합산하거나 환헤지 비율·승인에 사용하지 않는다.

### Q7. 헤지 100%가 추천입니까?

아니다. 기본 fee 가정과 제약 아래 grid가 만든 `SIMULATED_CANDIDATE`다. 실제
forward rate, 한도, 담보, 회계·세무는 은행 확인이 필요하다.

### Q8. 공식 후보는 가입 가능한 상품입니까?

아니다. official source와 상담 category가 연결된 최대 3개 후보이며 eligibility는
`unknown`, approval은 `consultation_required`다.

### Q9. KB와 실제 연결됩니까?

현재는 Markdown/JSON handoff packet 다운로드까지다. 예약·RM·내부심사 API는
미구현이며 후속 범위다.

### Q10. AI가 꼭 필요한 이유는 무엇입니까?

문서마다 다른 비정형 표현을 strict schema 후보로 바꾸고 계산 결과를 사람이 읽는
설명으로 만드는 데 사용한다. 금융 계산·위험·우선도·후보 제한은 결정론 코드로
남겨 AI의 불확실성을 통제한다.

### Q11. 왜 product web search를 기본으로 쓰지 않습니까?

offline verified KB가 재현 가능하고 안전하기 때문이다. 선택적 web 경로는 현재
category 통합 결함이 있어 fix와 end-to-end test 전 제출 주경로로 쓰면 안 된다.

### Q12. 실제 고객에게 바로 쓸 수 있습니까?

아니다. 공모전 MVP다. 실제 운영에는 고객 동의, auth, tenant, AV, 보존·삭제,
secret manager, rate limit, 중앙 audit, KB 내부 계약과 실제 문서 benchmark가
필요하다.

## 16. 경쟁작 대비 부족한 점

| 경쟁 축 | 현재 부족 | 발표/개선 대응 |
|---|---|---|
| end-to-end 업무완결 | 실제 예약·RM·승인 없음 | packet까지 정확히 주장, roadmap 제시 |
| 데이터 근거 | 합성 중심 | 범위·fail-closed를 투명하게 제시 |
| 상담 UX | top3·CTA 없음 | P1 view-model 우선 |
| 상품 실행성 | 조건·가격·자격 실시간 아님 | official source·unknown 유지 |
| 운영성 | auth/tenant/observability 없음 | 공모전/운영 경계 명시 |
| 발표 deliverable | deck·영상 없음 | 7장 deck와 backup 영상 |
| 모델 차별화 | Stage1 외부 팀 모델 의존 | adapter 계약·금융결정 연결을 차별점으로 설명 |

## 17. 내일 가장 먼저 할 세 가지

1. 금융 owner와 `amount_due` 문서유형별 계약을 30분 안에 확정하고 ADR·테스트 표를
   만든다.
2. 수출 liquidity mapping과 Golden split end-to-end 테스트를 별도 commit으로
   구현·검증한다.
3. 현행 계산만 사용한 Golden 상담 top3 한 화면과 7장 발표 deck을 만든다.

이 세 가지가 끝나기 전 새 상품·새 국가·예약 연동을 시작하지 않는다.
