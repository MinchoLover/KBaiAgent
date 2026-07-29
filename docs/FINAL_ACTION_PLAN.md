# KBaiAgent 제출 직전 최종 실행 계획

기준일: 2026-07-29 KST

코드 상태: 상담 Top 3·handoff 구현 완료, API-free 456 tests PASS

기능 동결 원칙: 새 금융 계산·상품·eligibility·Live 호출 금지

## 1. 종합 판단

현재 로컬 공모전 MVP의 제출 blocker였던 수출 유동성 상담 누락과 위험 기반
상담 Top 3 부재는 해결됐다. `amount_due`는 승인된 제품 계약상 Stage 2 분석 대상
예정 결제 노출액으로 유지하고, 실제 현재 미수·미지급잔액은 입금·지급 이력 없이는
`UNKNOWN`으로 구분한다.

이제 제출 전 우선순위는 기능 추가가 아니라 다음 세 가지다.

1. Golden Top 3를 한 화면에서 안정적으로 시연
2. “검토 순서/예정 노출/버퍼 부족”의 안전 경계를 발표자가 정확히 말함
3. 영상·슬라이드·Git·불변 지문을 한 번에 재현

## 2. 지금 즉시 할 일

| 순서 | 작업 | 완료 기준 | 예상 |
|---:|---|---|---:|
| 1 | 전체 품질 gate 최종 실행 | compile, 456 unittest, verify, pip check, 격리 regression PASS | 30분 |
| 2 | Golden 불변성 확인 | PDF SHA, Baseline 지문, 보호 파일 SHA 시작값 일치 | 10분 |
| 3 | 상담 화면 캡처 | Top 3·USD 20,000 UNKNOWN·2m/0/0·CTA 한 화면 | 30분 |
| 4 | 3분 발표 리허설 | 숫자·용어 오류 0, 3분 10초 이내 | 1시간 |
| 5 | offline 영상 녹화 | 네트워크·Live 없이 완주, 음성·글자 판독 가능 | 1시간 |

## 3. 제출 전 해야 할 일

### 3.1 제출 패키지 사실 확인

- branch와 제출 commit SHA 기록
- Golden SHA-256
  `5330a1a572488005f7b02cccfc7150fbaa8b38c84bb9290da1e0c6e1c3a0a91c`
- `python scripts/verify.py` 결과 저장
- 전체 테스트 수 456 확인
- regression은 원본 report를 덮어쓰지 않도록 임시 `git archive`에서 실행
- 보호 untracked 3개가 commit에 없는지 확인
- `.env`, 실제 업로드, API key, raw response가 staged되지 않았는지 확인
- 실제 push는 사용자가 별도 지시하기 전 금지

### 3.2 Golden 상담 숫자 암기

| 항목 | 정확한 값 |
|---|---|
| 분석 대상 예정 수취액 | USD 100,000 |
| 실제 현재 미수잔액 | UNKNOWN |
| 선지급 예정 | USD 20,000, 실제 입금 여부 UNKNOWN |
| 잔금 예정 | USD 80,000, 2026-08-20 |
| 결제조건 | Open Account / T/T |
| trade review | ELEVATED_REVIEW |
| 기준 원화 수취 | 140,000,000원 |
| -5% 원화 수취 | 133,000,000원 |
| 기준 대비 감소 | 7,000,000원 |
| 허용손실 | 5,000,000원 |
| -5% ending cash | 8,000,000원 |
| 목표 buffer | 10,000,000원 |
| buffer shortfall | 2,000,000원 |
| cash deficit | 0원 |
| payment/post-credit deficit | 0원 |

### 3.3 Golden 상담 Top 3

1. 수출대금 회수 보호 상담
2. 환율 관리 상담
3. 운영자금 버퍼·수출대금 회수시점 상담

발표자는 반드시 다음 문장을 포함한다.

> 상담 순위는 현재 거래에서 먼저 확인할 검토 순서이며, 상품 승인·보험 인수·
> 대출 심사 결과가 아닙니다.

## 4. 기능 동결 후 할 일

- README와 최종 네 보고서의 commit SHA·test count만 최종 갱신
- 화면 캡처 파일명과 슬라이드 번호 고정
- 영상 재생 환경·폰트·해상도 확인
- `docs/DEMO_SCRIPT_KO.md`와 실제 클릭 순서 대조
- `docs/JUDGE_QA_KO.md`를 팀원 모두 1회 소리 내어 답변
- 제출 zip을 별도 임시 위치에 풀어 README 명령과 링크 확인

기능 동결 뒤 app 구조, 금융 rule, prompt/schema, official candidate data를
수정하지 않는다.

## 5. 발표자료 작업

권장 7장 구성:

1. **문제** — 환율 전망보다 특정 계약의 현금·회수·상담 행동이 단절됨
2. **사용자 흐름** — 문서 → evidence → 확인 → stress → cash → 상담
3. **AI 경계** — 구조화·설명은 AI, 숫자·priority·critic은 결정론
4. **Golden 숫자** — USD 100k, KRW 7m, buffer 2m, deficits 0
5. **상담 Top 3** — 회수 보호 → 환율 → 유동성, 각 이유·서류·질문
6. **안전·검증** — fail-closed, UNKNOWN, 456 tests, one Golden Live 범위
7. **KB handoff와 한계** — JSON/Markdown, 공식 후보, 실제 예약·RM 연동 없음

슬라이드별 금지 표현:

- “AI가 최적 상품을 추천합니다”
- “USD 100,000 미수금”
- “2,000,000원 대출이 필요합니다”
- “BR 국가신용등급 4”
- “상담이 RM에게 전송됐습니다”
- “모든 문서 정확도 100%”

## 6. 3분 데모 리허설

| 시간 | 화면 | 말할 내용 |
|---|---|---|
| 0:00~0:20 | 문제 | “환율 숫자를 특정 계약의 현금과 상담 행동으로 바꿉니다.” |
| 0:20~0:45 | Golden 문서/evidence | 합성문서, source-grounded quote, 사용자 확인 gate |
| 0:45~1:15 | Stage 2 | 140m → 133m, 감소 7m, ending cash 8m |
| 1:15~1:35 | 안전 구분 | buffer 2m vs cash/payment deficit 0 |
| 1:35~2:20 | Top 3 | 회수 보호, 환율, 유동성의 숫자·부족정보·목표 |
| 2:20~2:40 | handoff | 같은 JSON의 Markdown, 공식 후보와 질문 |
| 2:40~3:00 | 검증·한계 | 456 tests, 제한된 Golden Live 1건, RM 연동 없음 |

실패 주입 리허설:

1. OpenAI key 없음 → fixture extraction/결정론 report
2. Stage 1 HTTP 실패 → file/mock/manual stress와 경고
3. evidence 부족 → Stage 2 차단
4. 공식 후보 0건 → 상품 생성 없이 빈 상태
5. report AI/critic 실패 → 같은 packet의 deterministic report

## 7. 영상 백업

- 기본 영상: Golden API-free path, 3분 이내
- 안전 영상: scan fail-closed, 60초
- 정적 백업: Top 3 카드, evidence, Stage 2 숫자, handoff Markdown 캡처
- 터미널 백업: Golden SHA, unittest 456, verify PASS
- 영상에 API key·환경변수·로컬 사용자 경로·실제 문서가 보이지 않게 확인

## 8. 최종 Git 정리

커밋 전:

```bash
git status --short
git diff --check
git diff --cached --name-only
git diff --cached
```

확인 항목:

- 보호 파일 3개 미포함
- Golden PDF·expected data 미포함
- Baseline prediction/report 미포함
- `.env`·secret 미포함
- 문서 commit에는 code 파일 미포함
- logical commit 메시지와 실제 diff 일치
- push하지 않음

## 9. 치명적 문제

### 제출 로컬 데모

현재 확인된 미해결 코드 P0는 없다. 다음 두 과거 P0는 해결됐다.

- `LIQUIDITY_BUFFER_RISK`의 수출 상담 연결
- 위험 기반 Top 3·numeric rationale·UNKNOWN·handoff·Stage 5 결속

### 실제 고객 운영

| 문제 | 영향 | 제출 처리 |
|---|---|---|
| 인증·tenant·동의·보존/삭제 없음 | 고객문서·packet 접근통제 불가 | 운영 완료 주장 금지 |
| malware scan·격리 렌더링 없음 | 악성 업로드 대응 불충분 | 합성문서 로컬 데모만 |
| 실제 예약·RM API 없음 | 업무 closure 수동 | 다운로드 handoff까지만 주장 |

## 10. 보통 문제

| 문제 | 영향 | 제출 전 대응 |
|---|---|---|
| `app.py` 대형 단일 파일 | UI 회귀면 큼 | 리팩터링 금지, AppTest 유지 |
| `* 2.py` 중복 파일 | canonical 혼동 | 제출 후 정리, 현재 import 경로 확인 |
| CI·coverage·lint/type gate 없음 | 로컬 검증 의존 | 터미널 증거와 verify 결과 제출 |
| official web→shortlist category gap | live web 빈 후보 가능 | offline 검증 후보 사용, 과장 금지 |
| 실제 사용자성 테스트 없음 | 카드 이해도 증거 부족 | 팀 리허설과 화면 캡처, 한계 공개 |
| 실제 고객문서 benchmark 없음 | 일반화 불가 | 합성 범위만 주장 |

## 11. 개선 제안

### 제출 전

- Top 3 화면 캡처와 3분 offline 영상
- 발표 슬라이드에서 `scheduled exposure`, `UNKNOWN`, `review order` 고정
- 팀원별 Q&A 역할과 fallback 클릭 순서 리허설

### 제출 후

- 기업 담당자·RM 각 3~5명 usability test
- 인증·tenant·동의·보존/삭제·malware scan 설계
- 승인된 KB 예약/RM adapter 계약
- 실제 적격성 엔진은 KB 정책·최신성·설명 가능성이 확보된 뒤 별도 개발
- 실제 고객문서는 허가·비식별·보존정책을 갖춘 독립 benchmark로만 평가

## 12. 공모전 100점 평가

| 평가 영역 | 배점 | 현재 | 근거 |
|---|---:|---:|---|
| 문제 정의와 고객가치 | 10 | 9 | 계약→현금→상담 문제 명확 |
| KB AI Challenge 적합성 | 10 | 9 | 기업금융 상담 handoff, 실제 내부 연동 없음 |
| 전체 아키텍처 | 10 | 8 | AI/결정론 경계 명확, Streamlit monolith |
| AI 활용 적절성 | 10 | 8 | 구조화·renderer에 제한, 실제 고객 검증 부족 |
| 금융 계산·도메인 | 10 | 8 | Decimal·지표 분리, 실제 quote/계좌 없음 |
| evidence·안전성 | 10 | 9 | source gate·UNKNOWN·critic, scan OCR 미지원 |
| 테스트·재현성 | 10 | 10 | 456 tests·verify·regression·지문 |
| 상담·KB 업무 연결 | 15 | 12 | Top 3/handoff 완성, RM/예약 없음 |
| UI·데모 전달력 | 10 | 7 | 카드 위계, 실사용성·영상 증거 부족 |
| 제출 완성도 | 5 | 4 | 문서·대본 준비, 최종 영상/실제 deck 확인 필요 |
| **합계** | **100** | **84** | **본상 경쟁력 있음** |

P0/P1 상담 구현 전 감사 기준은 74/100, 통과 가능 수준이었다. 현재 84/100으로
상승했지만 실제 고객 검증·은행 내부 closure 없이 “대상 경쟁력 있음”을
확정해서는 안 된다.

### 대상 가능성 평가

**판정: 본상 경쟁력 있음. 대상 가능성은 있으나 현재 증거로 단정 불가.**

대상을 결정할 변수는 코드 기능 수가 아니다. 심사에서 “기업 담당자가 이 packet으로
실제 KB 상담을 더 빨리 시작할 수 있는가”를 3분 안에 설득하고, 실제 예약·RM
연동이 없다는 경계를 정직하게 방어하는지가 중요하다.

## 13. 심사위원 관점 약점

1. 한 건 Golden Live와 합성 8건 외 실제 고객분포 증거가 없다.
2. 스캔문서는 독립 OCR이 없어 안전하게 차단하지만 자동화 완성도는 낮다.
3. one-page packet 뒤 실제 KB 예약·RM·심사 workflow가 없다.
4. 공식 후보는 최신 실시간 자격·가격·한도가 아니라 출처 확인 snapshot이다.
5. Stage 3은 실제 quote가 없는 계산상 비교안이다.
6. 로컬 Streamlit MVP라 auth·tenant·운영 보안이 없다.
7. 긴 `app.py`, CI·coverage 부재가 엔지니어링 성숙도를 낮춘다.
8. 상담 priority는 공개 rule이지만 KB 공식 routing policy는 아니다.

## 14. 경쟁작 대비 부족한 점

| 경쟁 축 | 부족한 점 | 발표 방어 |
|---|---|---|
| end-to-end 금융 업무 | 예약·RM·신청 없음 | 정확히 packet 다운로드까지만 주장 |
| 데이터/모델 증거 | 실고객 benchmark 없음 | fail-closed와 제한 범위를 강점으로 전환 |
| 실행 가능 상품 | 실시간 quote·eligibility 없음 | 공식 후보와 승인 판단 분리 |
| 운영성 | 인증·DB·관측성 없음 | 공모전 로컬 MVP와 운영 roadmap 분리 |
| 사용자 검증 | usability 연구 없음 | Golden 과업 데모와 후속 검증 계획 |
| 시각 완성도 | 실제 deck·영상 최종 확인 필요 | 7장/3분 구조와 정적 fallback |

차별점은 다음 네 가지다.

- 미검증 AI 값은 금융 계산으로 보내지 않음
- buffer shortfall, cash deficit, payment deficit를 혼동하지 않음
- 국가 원자료를 합산 신용등급으로 만들지 않음
- 위험 기반 Top 3와 공식 후보 eligibility를 분리함

## 15. 발표에서 방어해야 할 질문

### Q1. 왜 USD 100,000이지 잔금 USD 80,000이 아닌가?

USD 100,000은 계약상 두 예정 회차의 Stage 2 분석 대상 노출이다. 실제 선지급
입금 여부는 `UNKNOWN`이며 현재 미수잔액이라고 하지 않는다. 실제 입금이 확인되면
상담 missing item을 갱신하고 운영에서는 이행액을 반영해야 한다.

### Q2. 상담 1순위는 AI 추천인가?

아니다. 기존 finding으로 생성된 topic을 공개된 사전식 rule과 category tie-break로
정렬한다. LLM과 product score는 rank를 바꾸지 않는다.

### Q3. 2,000,000원은 필요 대출금인가?

아니다. 목표 buffer 부족이며 cash deficit와 payment/post-credit deficit는 모두
0원이다. 최신 자금계획·회수일·실제 한도 확인이 상담 목표다.

### Q4. 공식 후보는 가입 가능 상품인가?

아니다. 출처와 상담 category가 맞는 최대 3개 후보다. eligibility는 `UNKNOWN`,
approval은 `CONSULTATION_REQUIRED`다.

### Q5. KB에 실제 연결됐나?

현재는 JSON/Markdown handoff 다운로드와 영업점·기업금융·외환 상담 준비까지다.
예약·RM 전송·신청·내부심사는 구현하지 않았다.

### Q6. Golden Live는 성공했나?

최초 v1은 값이 맞아도 evidence 오류로 차단됐다. recovery 이후 승인된 제한된
합성문서 1건은 `validation_pass=true`, 확인 후 `stage2_allowed=true`였다.
이번 작업에서 Live를 재호출하지 않았고 전체 정확도로 일반화하지 않는다.

### Q7. BR 4는 국가신용등급인가?

아니다. OECD 공식 원자료의 raw classification이고 World Bank·WTO와 합산하지
않는다. KB 내부 신용등급·부도확률도 아니다.

### Q8. Stage 3 후보는 최적 헤지인가?

아니다. 공개된 비용·위험 가정에서 만든 계산상 비교안이다. 실제 환율·수수료·
한도·회계·세무와 실행 가능성은 상담에서 확인한다.

### Q9. UI·Markdown·보고서 숫자가 다르면?

모두 같은 `ConsultationPacket` JSON에서 파생한다. LLM draft가 rank·숫자를
바꾸면 critic이 거부하고 deterministic fallback을 사용한다.

### Q10. 실제 고객에게 바로 배포 가능한가?

아니다. 인증·tenant·동의·보존/삭제·malware scan·운영 모니터링과 KB 내부 계약이
필요하다. 현재는 합성문서를 사용하는 로컬 공모전 MVP다.

## 16. 하지 말아야 할 작업

- extraction prompt/schema, evidence validator, 국가 canonicalization 변경
- Stage 1~5 금융 계산·threshold 변경
- 새로운 상품·eligibility·승인 예측 추가
- 국가 신호를 헤지·현금·결제 숫자에 합산
- 제출 직전 `app.py` 대규모 리팩터링
- Golden·Baseline 재생성 또는 기대값 완화
- Live API 재실행으로 표본 수를 급히 늘리기
- 실제 고객문서 사용
- 미승인 RM/예약 URL 추측
- Git push

## 17. 내일 가장 먼저 할 세 가지

1. Golden Top 3 화면과 one-page handoff를 3분 offline 영상으로 녹화한다.
2. 팀 전체가 Q1~Q10을 실제 숫자로 답하고, “review order/UNKNOWN/no RM
   integration” 문구를 통일한다.
3. 제출 직전 Golden·Baseline·보호 파일 지문, 456 tests와 verify를 다시 확인하고
   제출 commit SHA를 고정한다.
