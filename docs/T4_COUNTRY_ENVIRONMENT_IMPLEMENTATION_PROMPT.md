
# KBaiAgent T4 국가·무역환경 위험 — Codex Sol xhigh 구현 프롬프트

> 새 Codex 세션의 작업 폴더를 현재 KBaiAgent 저장소 루트로 설정한 뒤,
> 이 문서에서 아래 역할 선언부터 마지막 지시까지 전체를 붙여 넣는다.

너는 KBaiAgent 프로젝트의 수출입금융 전문가이자 금융 AI 아키텍트,
Python·Pydantic·Streamlit 수석 개발자, 금융 시스템 감사·QA 책임자다.

이번 작업에서는 계획만 작성하지 말고 T4 국가·무역환경 위험 기능을
구현·테스트·문서화·별도 커밋까지 완료하라.

---

## 0. 대상 저장소와 확인된 기준 상태

대상 저장소:

현재 KBaiAgent 저장소 루트

작업 시작 기준 커밋:

- T6 공식 후보 shortlist:
  `b6716e2 feat: shortlist grounded official candidates`
- T7 최종 보고서 연결:
  `92c3adf feat: ground final report in consultation evidence`
- 미국·브라질 합성 검증문서:
  `6ad75ad test: add country trade document validation set`

현재 확인된 기존 기능:

- Stage 0 무역문서 추출·evidence·사용자 확인
- Stage 1 환율 모델 JSON/REST adapter
- Stage 2 Decimal 기반 현금흐름·유동성 계산
- Stage 3 환헤지 후보 시뮬레이션
- 기존 runtime Stage 4 공식 금융상품 검색
- Stage 5 보고서·critic·결정론 fallback
- T2·T3 거래·결제 위험 진단
- T5 위험→금융상담 대응 매핑
- T6 공식 후보 shortlist 최대 3개
- T7 ConsultationPacket 기반 최종 보고서

중요:

이번 T4는 backlog 티켓 이름이다. 기존 runtime Stage 4 공식 상품검색과
혼동하지 마라. 새 Stage 번호를 추가하거나 기존 Stage 4를 교체하지 마라.

---

## 1. 이번 작업의 단일 목표

기존 T1~T3, T5~T7을 재구현하지 않고 T4 국가·무역환경 위험 기능만
구현한다.

대상 국가는 다음 두 곳으로 제한한다.

- United States, US
- Brazil, BR

기능 목표:

1. OECD 지급·이전 위험 관련 공식 신호
2. World Bank 거시환경 공식 신호
3. WTO 무역·시장접근 공식 신호

위 세 축을 서로 분리된 결정론적 분석으로 제공한다.

국가 신호는 다음 용도로만 사용한다.

- 보험 검토 우선순위
- 보증 검토 우선순위
- 신용장·결제조건 검토 우선순위
- ConsultationPacket 설명
- T7 최종 보고서 설명

국가 신호는 다음을 변경하면 안 된다.

- Stage 1 환율 방향·분위수
- Stage 2 환노출·현금흐름·유동성 계산
- Stage 3 환헤지 비율·후보·목적함수
- 금융상품 자격·승인·한도·가격
- 거래처 부도확률
- 은행 공식 심사등급

---

## 2. 작업 시작 전 안전 감사

코드를 수정하기 전에 반드시 다음을 수행한다.

1. `AGENTS.md` 전체 확인
2. `git status` 확인
3. 현재 브랜치와 HEAD 확인
4. 다음 커밋이 현재 HEAD의 조상인지 확인
   - `b6716e2`
   - `92c3adf`
   - `6ad75ad`
5. 기존 미커밋·미추적 파일 확인
6. 전체 `src/`, `tests/`, `docs/`, `dataset/`, `reports/` 구조 확인
7. 관련 Domain 모델과 service 위치 확인
8. `ConsultationPacket` 계약 확인
9. 거래·결제 위험 input·assessment·fingerprint 확인
10. T5 상담 topic 매핑 확인
11. T6 공식 shortlist 연결 확인
12. T7 보고서 bundle·critic·fallback 확인
13. `WorkflowState`·`StageResult`·trace·session state invalidation 확인
14. 기존 snapshot·integration asset의 버전 관리 방식 확인
15. Python 및 Pydantic 버전 확인

현재 다음 파일이 미추적 상태라면 사용자 소유 파일이다.

- `PROJECT_DIRECTION.md`
- `docs/FEATURE_MAPPING.md`
- `docs/T4_COUNTRY_ENVIRONMENT_IMPLEMENTATION_PROMPT.md`

위 두 파일은 다음 행동을 금지한다.

- 수정
- 삭제
- 이동
- staging
- commit
- 내용 덮어쓰기

다른 tracked 변경이 존재하거나 현재 HEAD가 `6ad75ad`를 포함하지 않으면
임의로 reset·stash·checkout하지 말고 작업을 중단해 상태를 보고하라.

감사가 정상이라면 현재 HEAD에서 다음 전용 브랜치를 만든다.

`feature/t4-country-risk`

이미 같은 브랜치가 존재하면 덮어쓰지 말고 상태를 확인한 뒤 안전하게
사용한다.

금지 명령:

- `git reset --hard`
- `git checkout --`
- 사용자 파일을 포함한 광범위한 `git add`
- `git clean`
- 강제 push

---

## 3. 절대적인 금융·데이터 원칙

1. OECD, World Bank, WTO를 하나의 0~100 점수로 합치지 마라.
2. 가중평균, 합산점수, 신용점수, 부도확률을 만들지 마라.
3. 국가 신용등급을 만들지 마라.
4. LOW / MEDIUM / HIGH 국가등급을 만들지 마라.
5. OECD 원자료 분류를 KBaiAgent 자체 등급처럼 표현하지 마라.
6. UNKNOWN·미분류·자료 없음과 낮은 위험을 구분하라.
7. 자료가 없으면 0, LOW, 안전으로 변환하지 마라.
8. 공식 출처에 없는 값을 추측하거나 보간하지 마라.
9. 서로 다른 관측연도 값을 같은 시점 자료처럼 표현하지 마라.
10. 국가 신호로 환헤지 비율을 조정하지 마라.
11. 국가 신호로 상품 승인·가입 가능성을 판단하지 마라.
12. LLM이 신호, 임계값, 우선순위를 생성하게 하지 마라.
13. 같은 snapshot과 입력은 항상 같은 결과를 내야 한다.
14. 모든 결정론 규칙과 기여 원인을 공개하라.
15. 정보 부족은 명시적인 결과로 처리하라.

최종 우선순위 enum은 다음 네 개만 사용한다.

- `STANDARD_REVIEW`
- `ELEVATED_REVIEW`
- `HIGH_REVIEW`
- `INSUFFICIENT_INFORMATION`

이 값은 국가등급이 아니라 다음 의미의 거래 검토 우선순위다.

- `STANDARD_REVIEW`
  - 통상적인 거래·결제 검토 절차가 필요함
  - 낮은 국가위험이나 안전을 의미하지 않음
- `ELEVATED_REVIEW`
  - 보험·보증·신용장·결제조건을 추가 검토해야 함
- `HIGH_REVIEW`
  - 거래 실행 전 지급·회수 보호수단과 조건을 우선적으로 검토해야 함
- `INSUFFICIENT_INFORMATION`
  - 공식 자료가 없거나 snapshot이 손상·불완전·상충하여
    결정론적 검토 우선순위를 정할 수 없음

---

## 4. 공식 출처 정책

공식 자료를 조사할 때는 반드시 1차 공식 출처만 사용한다.

허용 출처 예시:

- OECD
  - `oecd.org` 하위 공식 페이지·공식 문서
- World Bank
  - `worldbank.org`
  - `data.worldbank.org`
  - `api.worldbank.org`
- WTO
  - `wto.org`
  - `stats.wto.org`

검색 결과 snippet, 블로그, 언론 기사, 민간 위험평가 사이트, Wikipedia,
임의 요약문은 snapshot 근거로 사용하지 마라.

공식 페이지가 접근되지 않거나 원값을 검증할 수 없으면 추측하지 마라.

다음 OECD 핵심값은 반드시 공식 출처로 재확인한다.

- OECD snapshot 기준일: `2026-06-26`
- Brazil raw classification: `4`
- United States: `HIGH_INCOME_OECD_UNCLASSIFIED`

공식 출처가 위 값과 충돌하면 임의로 다른 값으로 구현하지 말고
충돌한 공식 URL·표기·날짜를 보고하고 작업을 중단하라.

OECD 기준일 `2026-06-26`을 World Bank와 WTO 자료에도 억지로 적용하지
마라.

World Bank와 WTO는 각 지표별로 다음을 별도 저장한다.

- 실제 관측연도 또는 자료기간
- 공식 게시·갱신 기준일
- snapshot에서 검증한 날짜

---

## 5. Versioned offline snapshot

API key와 runtime 인터넷 연결이 없어도 동일하게 재현되는
versioned offline snapshot을 구현한다.

실제 저장소 패턴을 감사한 뒤 자연스러운 위치를 선택하되,
구조 확인 전에 파일 경로를 단정하지 마라.

snapshot에는 최소 다음이 있어야 한다.

- `schema_version`
- `snapshot_version`
- `snapshot_id`
- `supported_countries`
- `generated_or_curated_at`
- source records
- source별 공식 URL
- source별 공식 문서 제목
- source별 자료 기준일
- source별 관측연도·자료기간
- 원값
- 단위
- 원값에 대한 제한적 해석
- 한계
- 검증 상태
- 변경·재현을 위한 snapshot hash

모든 source record는 최소 다음 정보를 제공한다.

- `source_record_id`
- `source_name`
- `source_axis`
- `country`
- `official_url`
- `source_title`
- `as_of_date`
- `observation_period`
- `raw_value`
- `raw_unit`
- `interpretation`
- `limitations`
- `verification_status`

`source_axis`는 최소 다음 세 축을 분리한다.

- `OECD_PAYMENT_TRANSFER`
- `WORLD_BANK_MACRO_ENVIRONMENT`
- `WTO_TRADE_MARKET_ACCESS`

규칙:

1. 원값을 문자열·정수 계약에 맞게 보존한다.
2. 소수 데이터는 float 대신 Decimal 호환 문자열을 사용한다.
3. 날짜는 `YYYY-MM-DD` 또는 명시적인 연도·기간 문자열을 사용한다.
4. JSON extra field를 허용하지 않는다.
5. snapshot version이 다르거나 hash가 맞지 않으면 fail closed한다.
6. 지원하지 않는 국가는 값을 추측하지 않는다.
7. runtime에 외부 API를 호출하지 않는다.
8. 테스트에서 네트워크를 호출하지 않는다.
9. snapshot 생성 시각을 매 실행 시 현재 시각으로 바꾸지 않는다.
10. 같은 snapshot은 byte 또는 canonical hash가 동일해야 한다.
11. 전체 공식 PDF나 웹페이지를 저장하지 말고 필요한 공개 사실과 URL만
    보존한다.
12. refresh 도구가 꼭 필요하지 않다면 새 fetch framework를 만들지 마라.
13. refresh 도구를 만들더라도 committed snapshot을 자동 덮어쓰지 마라.

---

## 6. OECD 처리 규칙

### Brazil

- `raw_classification`은 정수 `4`로 저장한다.
- 원본 체계가 OECD 0~7 분류임을 metadata에 기록한다.
- 화면 제목이나 보고서에서 다음처럼 쓰지 마라.
  - 브라질 위험등급 4
  - KBaiAgent 국가등급 4
  - 국가 신용등급 4
  - HIGH 국가

허용 표현 예시:

- OECD 공식 원자료 분류: 4
- 지급·이전 위험 관련 보험·보증 검토 신호
- 본 값은 OECD 공식 원값이며 KBaiAgent 자체 국가등급이 아님

### United States

- `raw_classification`은 `null`로 저장한다.
- `0`으로 저장하지 마라.
- `LOW`로 저장하지 마라.
- `STANDARD` 국가등급으로 변환하지 마라.
- 상태를 정확히 다음 값으로 보존한다.

`HIGH_INCOME_OECD_UNCLASSIFIED`

허용 표현 예시:

- 고소득 OECD 회원국 미분류
- OECD 원자료상 분류번호 없음
- 미분류는 0 또는 낮은 위험을 의미하지 않음

미국의 미분류 상태는 정보 부족 오류와도 구분한다.

즉 다음 세 상태는 서로 달라야 한다.

- `CLASSIFIED`
- `HIGH_INCOME_OECD_UNCLASSIFIED`
- `DATA_UNAVAILABLE`

OECD raw 4를 자체 국가등급으로 변환해서는 안 되지만, 거래 검토에서는
다음의 결정론적 행동 신호로 사용할 수 있다.

`PAYMENT_TRANSFER_PROTECTION_REVIEW_REQUIRED`

이는 국가 신용등급이 아니라 보험·보증·신용장·결제조건 추가 검토
필요성을 뜻한다.

미국 미분류 상태는 위험을 낮추는 감경 신호로 사용하지 않는다.

---

## 7. World Bank 거시환경 축

World Bank는 거시환경 관측 자료로만 사용한다.

최소 검토 후보 지표:

- GDP growth annual %
  - indicator 예시: `NY.GDP.MKTP.KD.ZG`
- Inflation, consumer prices annual %
  - indicator 예시: `FP.CPI.TOTL.ZG`
- Current account balance % of GDP
  - indicator 예시: `BN.CAB.XOKA.GD.ZS`

실제 구현 전 다음을 확인한다.

1. 두 국가 모두 같은 공식 정의의 지표인지
2. 각 국가의 최신 공식 관측연도가 무엇인지
3. 단위가 동일한지
4. 값이 null이거나 revision 대상인지
5. 동일 연도 비교가 가능한지

지표가 없으면 다른 민간 지표로 대체하지 마라.
서로 다른 관측연도라면 그대로 표시하고 비교 한계를 기록한다.

World Bank 값으로 다음을 만들지 마라.

- 거시위험 73점
- 국가 안정성 점수
- 부도확률
- 공식 신용등급
- 환율 예측값
- 환헤지 비율

프로젝트에서 사전 승인된 공식 임계값이 없다면 GDP·물가·경상수지
숫자만 보고 임의의 위험 임계값을 만들지 마라.

초기 v1에서는 다음을 우선한다.

- 원값 보존
- 관측연도 표시
- 방향·변동성에 대한 제한적 설명
- 결제기간과 보호수단을 재확인할 상담 질문
- 오래되거나 누락된 자료 경고

수치 임계값을 도입해야 한다면 반드시 다음을 모두 만족한다.

- 코드 상수 또는 versioned rule table
- 도입 근거
- 공식 기준이 아니라는 명시
- 경계값 테스트
- 변경 시 rule version 증가

---

## 8. WTO 무역·시장접근 축

WTO는 무역·시장접근 환경으로만 사용한다.

검토 후보:

- WTO membership status
- 최신 공식 trade profile 또는 tariff profile
- 최신 공식 MFN applied tariff 자료
- 최신 공식 Trade Policy Review 관련 기준일
- 두 국가에서 동일한 정의로 비교 가능한 시장접근 원값

규칙:

1. WTO 자료를 국가 신용위험으로 해석하지 마라.
2. WTO tariff 원값을 지급불능 위험으로 변환하지 마라.
3. 서로 다른 상품군·연도·정의를 직접 비교하지 마라.
4. 값이 없으면 null과 한계를 저장한다.
5. 공식 WTO URL과 자료기간을 저장한다.
6. 시장접근 신호는 다음 상담 행동으로만 연결한다.
   - 계약조건 재확인
   - 통관·관세·시장접근 조건 확인
   - 거래은행 또는 무역전문가 상담
7. 특정 금융상품 승인이나 추천순위를 만들지 마라.

---

## 9. 동일 조건 비교 시나리오

미국과 브라질은 국가 외의 모든 조건을 동일하게 비교한다.

대표 비교 조건:

- 한국 기업: `SELLER`
- 거래 방향: `EXPORT`
- `counterparty_country`: US 또는 BR만 변경
- `currency`: `USD`
- `payment_method`: `OPEN_ACCOUNT`
- payment term: 90 calendar days
- counterparty relationship: `EXISTING`
- credit insurance: `NONE_CONFIRMED`
- guarantee: `NONE_CONFIRMED`
- letter of credit: 적용 없음
- 사용자 확인 완료
- 동일한 금액
- 동일한 현금흐름
- 동일한 환율 시나리오
- 동일한 기존 헤지

실제 enum과 필드명은 저장소 Domain 계약을 먼저 확인한 뒤 맞춘다.
새 boolean 필드를 중복 추가하지 마라.

두 fixture는 counterparty country와 그에 따른 공식 snapshot record
외에는 canonical 입력이 동일해야 한다.

비교 결과에서 다음을 검증한다.

### United States

- OECD status: `HIGH_INCOME_OECD_UNCLASSIFIED`
- raw classification: `null`
- 0 또는 LOW로 변환되지 않음
- OECD 미분류를 위험감경으로 사용하지 않음
- 대표 거래조건 때문에 최소 `ELEVATED_REVIEW`
- 국가등급으로 표시하지 않음

### Brazil

- OECD raw classification: `4`
- 자체 국가등급 필드 없음
- `PAYMENT_TRANSFER_PROTECTION_REVIEW_REQUIRED` 발생
- 동일한 90일 Open Account·무보호 거래조건과 결합해 대표 fixture는
  `HIGH_REVIEW`
- 보험·보증·신용장·결제조건 우선 검토로 연결

위 예상 결과는 국가 신용등급이 아니라 동일 거래의 상담·검토
우선순위 차이다.

---

## 10. Domain 모델

실제 저장소 naming과 module boundary를 확인한 뒤 최소 모델을 구현한다.

필요 개념 예시:

- `CountryTradeEnvironmentInput`
- `OfficialSourceReference`
- `OecdPaymentTransferSignal`
- `WorldBankMacroEnvironmentSignal`
- `WtoTradeMarketAccessSignal`
- `CountryTradeEnvironmentAssessment`
- `CountryEnvironmentReviewNeed`
- `CountryReviewPriority`
- `SnapshotMetadata`

모델 이름은 기존 패턴에 맞게 조정할 수 있다.

`CountryTradeEnvironmentAssessment`에는 최소 다음이 있어야 한다.

- country
- trade_type
- review_priority
- OECD 지급·이전 신호
- World Bank 거시환경 신호
- WTO 무역·시장접근 신호
- review_needs
- reasons
- warnings
- assumptions
- limitations
- official_source_references
- snapshot_version
- rule_version
- input_fingerprint

T4 subtree에는 다음 필드를 두지 마라.

- `score`
- `composite_score`
- `credit_score`
- `default_probability`
- `country_rating`
- `internal_country_grade`

Python 3.9 호환 규칙:

- `Optional`
- `List`
- `Dict`

를 사용하고 `X | None` 문법에 의존하지 마라.

금융·경제 소수 값은 Decimal 문자열로 저장한다.
날짜는 `date`/`datetime` 또는 ISO 문자열을 기존 계약에 맞춰 사용한다.
Pydantic extra field는 금지한다.

---

## 11. 결정론적 우선순위 규칙

0~100 점수 없이 공개된 rule table로만 판단한다.

우선순위는 낮추는 방향으로 사용하지 않는다.
국가 신호가 기존 거래·결제 위험을 감경하면 안 된다.

v1 기본 규칙:

1. snapshot schema/hash가 잘못됨
   - `INSUFFICIENT_INFORMATION`
2. 국가 record가 없음
   - `INSUFFICIENT_INFORMATION`
3. 핵심 공식 source provenance가 없음
   - `INSUFFICIENT_INFORMATION`
4. `HIGH_INCOME_OECD_UNCLASSIFIED`
   - 0 또는 LOW로 변환하지 않음
   - 위험감경 없음
   - 미분류 상태와 한계를 이유에 추가
5. Brazil OECD raw classification 4
   - 자체 국가등급으로 변환하지 않음
   - `PAYMENT_TRANSFER_PROTECTION_REVIEW_REQUIRED` 추가
6. 90일 Open Account + 무보험·무보증
   - 최소 `ELEVATED_REVIEW`
7. 위 거래조건에
   `PAYMENT_TRANSFER_PROTECTION_REVIEW_REQUIRED`가 추가됨
   - `HIGH_REVIEW`
8. World Bank·WTO 신호는 각 축의 이유와 상담 질문을 추가
   - 숫자 점수나 가중치로 OECD와 합산 금지
9. 공식 source가 제공하는 직접적인 categorical warning을 쓰려면
   raw category와 출처를 그대로 보존
   - 자체 국가등급으로 재명명 금지
10. 신호가 없거나 중립처럼 보인다는 이유로 기존 거래 검토
    우선순위를 낮추지 않음

모든 rule은 다음 정보를 결과에 남긴다.

- rule code
- source axis
- observed raw value 또는 status
- 발생한 review need
- 우선순위에 미친 방향
- 사람이 읽는 이유

숨겨진 가중치나 숫자 impact를 사용하지 마라.

---

## 12. 기존 시스템 연결

새 runtime Stage 번호를 추가하지 마라.

실제 구조를 비교한 뒤 다음 중 가장 작은 변경을 선택한다.

- 독립 country environment domain/service
- consultation application service의 보조 분석
- workflow의 별도 auxiliary step
- 기존 trade-risk 후속 보조 분석

선택 이유를 설계 문서에 기록한다.

반드시 지킬 연결 경계:

1. 사용자 확인된 국가·거래조건만 입력으로 사용
2. 문서 모델이 국가를 추측한 상태에서는 실행하지 않음
3. T4 결과 변경 시 무효화 범위
   - T4 assessment
   - ConsultationPacket
   - T7 최종 보고서
4. T4 결과 변경 시 유지할 범위
   - Stage 1 결과
   - Stage 2 결과
   - Stage 3 결과
   - 기존 거래·결제 위험 원본 assessment
5. fingerprint에 포함
   - canonical 거래조건
   - counterparty country
   - snapshot version
   - snapshot hash
   - rule version
   - 사용된 source record IDs
6. fingerprint에 포함하지 말 것
   - 화면 표시문구
   - runtime 현재시각
   - 문서 원문 전체
   - API key
   - 민감 payload
7. trace에는 다음 정도만 기록
   - country
   - snapshot ID
   - rule version
   - review priority
   - source record IDs
   - warning code
8. trace에 전체 snapshot raw payload를 남기지 마라.

---

## 13. ConsultationPacket과 T5 연결

기존 `ConsultationPacket`에 선택적 필드로 연결한다.

기존 packet에 T4가 없는 경우:

- 기존 JSON 구조 유지
- 불필요한 null 필드 출력 금지
- 기존 packet hash·테스트 유지
- 기존 샘플 역직렬화 유지

T4가 있는 경우 다음을 포함한다.

- country assessment
- review priority
- 세 축의 분리된 이유
- official source references
- review needs
- snapshot version
- input fingerprint

`CountryEnvironmentReviewNeed`는 다음과 같은 상담 행동에만 연결한다.

- `PAYMENT_TRANSFER_PROTECTION_REVIEW`
- `CREDIT_INSURANCE_REVIEW`
- `GUARANTEE_REVIEW`
- `DOCUMENTARY_CREDIT_TERMS_REVIEW`
- `PAYMENT_TERMS_REVIEW`
- `MACRO_ENVIRONMENT_MONITORING`
- `TRADE_MARKET_ACCESS_REVIEW`
- `INFORMATION_COMPLETENESS_REVIEW`

실제 기존 category가 있으면 재사용한다.
중복 enum을 만들지 마라.

T4는 상담 topic의 검토 우선순위와 질문을 보강할 수 있지만 다음을
하면 안 된다.

- 특정 상품 강제 선택
- 공식 후보 shortlist 점수화
- 후보 eligibility 변경
- `approval_status` 변경
- 후보 수 3개 제한 변경
- 비공식 상품 생성

T6 shortlist는 기존 공식 source matching 정책을 그대로 유지한다.

---

## 14. T7 최종 보고서 연결

기존 Stage 5 생성·critic·1회 수정·결정론 fallback 구조를 유지한다.

`ConsultationPacket`에 T4가 있으면 보고서에 다음을 추가한다.

- 거래국
- 거래 검토 우선순위
- OECD 지급·이전 신호
- World Bank 거시환경 신호
- WTO 무역·시장접근 신호
- 공식 URL
- 자료 기준일·관측연도
- 원값의 제한적 해석
- 한계
- 은행·보험·보증·신용장·결제조건 상담 질문

보고서에서 허용하는 표현:

- 브라질 OECD 공식 원자료 분류는 4입니다.
- 이는 KBaiAgent 자체 국가 신용등급이 아닙니다.
- 미국은 고소득 OECD 회원국 미분류 상태입니다.
- 미분류를 0이나 낮은 위험으로 해석하지 않았습니다.
- 거래 검토 우선순위는 동일한 거래조건과 공식 신호를 바탕으로 한
  상담 순서입니다.

critic은 최소 다음을 거부한다.

1. OECD raw 4를 KBaiAgent 국가등급으로 표현
2. 미국 미분류를 LOW·0·안전으로 표현
3. OECD·World Bank·WTO를 0~100으로 합산
4. 국가 신용등급·부도확률 주장
5. snapshot과 다른 원값·날짜·URL 생성
6. 비공식 URL 인용
7. 국가 신호로 환헤지 비율 변경
8. 국가 신호로 Stage 2 현금흐름 변경
9. 상품 가입·승인·보험 인수 가능성 확정
10. 서로 다른 관측연도를 같은 시점처럼 표현
11. shortlist 밖 상품 생성
12. 원자료 미분류와 정보 부족 혼동

LLM이 없거나 critic이 재실패하면 같은 T4 구조화 근거를 사용하는
결정론 fallback 보고서를 생성한다.

---

## 15. 최소 UI

UI 전면 개편은 금지한다.

기존 위험 진단 또는 상담자료 흐름에서 T4 결과를 최소 표시한다.

상단에 표시:

- 거래국
- 거래 검토 우선순위
- 국가 신용등급이 아니라는 고지
- 상담 시 먼저 확인할 항목 최대 3개

분리된 세 축:

1. 지급·이전 환경 — OECD
2. 거시환경 — World Bank
3. 무역·시장접근 — WTO

각 축에 표시:

- source 이름
- 원값 또는 status
- 자료 기준일·관측연도
- 짧은 해석
- 한계
- 공식 URL

브라질 OECD 4는 headline badge로 표시하지 마라.
상세 근거 안에서 다음처럼 표시한다.

> OECD 공식 원자료 분류: 4
>
> 자체 국가등급 아님

미국은 다음처럼 표시한다.

> 고소득 OECD 회원국 미분류
>
> 0 또는 낮은 위험으로 변환하지 않음

내부 JSON, fingerprint, snapshot hash, trace는 기본 사용자 화면이 아니라
접힌 감사 영역에 둔다.

---

## 16. 보안·감사

1. OpenAI API를 호출하지 마라.
2. 외부 LLM을 호출하지 마라.
3. 테스트에서 인터넷을 호출하지 마라.
4. runtime 국가분석에서 인터넷을 호출하지 마라.
5. API key를 읽거나 출력하지 마라.
6. `.env` 내용을 출력하지 마라.
7. 공식 source 조사 시 비밀키 없는 공개 공식 자료만 사용한다.
8. snapshot에 개인정보·기업정보를 저장하지 마라.
9. 전체 원문 웹페이지나 PDF를 로그에 저장하지 마라.
10. 공식 source의 짧은 공개 사실과 URL만 기록한다.
11. trace에 전체 source payload를 기록하지 마라.
12. 기존 보안·redaction 테스트를 약화하지 마라.

---

## 17. 필수 테스트

기존 테스트 기대값을 낮추거나 삭제하지 마라.
regression baseline을 갱신하지 마라.

### P0 — 구현 승인 전 필수

1. snapshot schema 역직렬화
2. snapshot version 검증
3. snapshot canonical hash 결정성
4. snapshot 변조 시 fail closed
5. 공식 HTTPS URL만 허용
6. source별 official URL 존재
7. source별 기준일 또는 관측기간 존재
8. source별 raw value/status 존재
9. source별 interpretation 존재
10. source별 limitations 존재
11. OECD 기준일이 정확히 `2026-06-26`
12. Brazil raw classification이 정확히 `4`
13. Brazil raw 4가 자체 country rating으로 직렬화되지 않음
14. US raw classification이 `null`
15. US status가 `HIGH_INCOME_OECD_UNCLASSIFIED`
16. US가 LOW 또는 0으로 변환되지 않음
17. 미분류와 `DATA_UNAVAILABLE` 구분
18. OECD·World Bank·WTO 결과가 별도 축
19. T4 subtree에 `score`/`composite_score`/`credit_score` 없음
20. 하나의 숫자 점수로 합쳐지지 않음
21. 같은 입력은 같은 priority·reason·fingerprint
22. 지원하지 않는 국가는 `INSUFFICIENT_INFORMATION`
23. snapshot 누락은 `INSUFFICIENT_INFORMATION`
24. source provenance 누락은 fail closed
25. 미국·브라질 대표 입력이 country 외에는 동일
26. 두 입력 모두 USD
27. 두 입력 모두 EXPORT
28. 두 입력 모두 Open Account 90일
29. 두 입력 모두 기존 거래처
30. 두 입력 모두 무보험·무보증
31. 미국 fixture가 `ELEVATED_REVIEW`
32. 브라질 fixture가 `HIGH_REVIEW`
33. 브라질 결과에
    `PAYMENT_TRANSFER_PROTECTION_REVIEW_REQUIRED` 존재
34. 미국 미분류가 감경 요인으로 사용되지 않음
35. 국가 신호 적용 전후 Stage 2 결과 완전 동일
36. 국가 신호 적용 전후 Stage 3 후보·비율 완전 동일
37. 국가 신호 변경이 Stage 1~3 결과를 무효화하지 않음
38. 국가 신호 변경이 T4·packet·report만 무효화
39. T4 fingerprint에 snapshot version/hash 포함
40. trace에 전체 source payload·비밀값 없음
41. 기존 `ConsultationPacket`에 T4가 없으면 legacy 직렬화 유지
42. T4가 있으면 packet hash에 assessment binding 반영
43. T4 review need가 상담 topic으로 결정론 매핑
44. 국가 신호가 상품 eligibility·approval을 변경하지 않음
45. shortlist 최대 3개 유지
46. 매칭 source가 없을 때 상품 생성 금지
47. T7 보고서에 세 축이 분리되어 표시
48. T7 보고서에 공식 URL·자료기간·한계 표시
49. critic이 Brazil 4 자체등급 표현 거부
50. critic이 US LOW/0 표현 거부
51. critic이 0~100 합산점수 거부
52. critic이 국가 신호→환헤지 비율 변경 거부
53. critic이 국가 신호→현금흐름 변경 거부
54. critic이 상품 승인 주장 거부
55. fallback 보고서에도 동일 정책 적용
56. 최소 UI 렌더링 테스트
57. 정보 부족 UI 상태
58. 기존 US/BR 합성문서 8건 유지
59. 기존 전체 345개 테스트 회귀 통과
60. fine-tuning test split 제외 유지

### P1 — 이번 작업에서 권장

- World Bank 지표별 null·관측연도 차이
- WTO 서로 다른 자료연도 경고
- snapshot unsupported version
- 중복 `source_record_id`
- source country 불일치
- URL allowlist lookalike 차단
- Decimal 과학표기·float 거부
- source 순서가 달라도 canonical hash 결정성
- packet fingerprint 변조 거부
- US/BR 비교 Markdown snapshot test

---

## 18. 테스트 실행 명령

저장소에 맞는지 먼저 확인한 뒤 최소 다음을 실행한다.

```bash
PYTHONPYCACHEPREFIX=/tmp/invoice_intake_pycache \
python -m compileall -q app.py src scripts tests

python -m unittest discover -s tests -v

python scripts/evaluate_extraction.py \
  --mode offline \
  --manifest dataset/country_validation/manifest.jsonl \
  --predictions-dir dataset/country_validation/predictions/fixture \
  --reports-dir reports/country_validation

python scripts/verify.py
```

country-risk 신규 테스트 모듈을 별도로 실행한다.

필요하다면 기존 결정 데모도 API-free로 실행한다.

테스트 실패 시 반드시 보고한다.

- 실패 명령
- 실패 테스트
- 실제 오류
- 직접 원인
- 수정 여부
- 남은 문제

실행하지 않은 테스트를 PASS라고 쓰지 마라.
실패 테스트를 삭제하거나 기대값을 낮추지 마라.

---

## 19. 문서화

실제 저장소 명명 규칙에 맞춰 다음을 문서화한다.

1. T4 국가·무역환경 설계 문서
   - 목적
   - 비목표
   - 세 축 분리
   - snapshot schema
   - 공식 source table
   - raw value
   - 자료 기준일
   - 규칙표
   - priority 의미
   - 한계
   - 갱신 절차
2. snapshot README
   - snapshot version
   - 지원 국가
   - 공식 URL
   - source별 자료기간
   - 재현 방법
   - runtime network 미사용
   - 갱신 시 검증 절차
3. `docs/DECISIONS.md`
   - 국가 신용등급 대신 거래 검토 우선순위
   - 세 신호 비합산
   - 기존 Stage 2·3 불변
   - versioned offline snapshot
4. `docs/VALIDATION_REPORT.md`
   - 신규 테스트
   - US/BR 동일조건 비교
   - Stage 2·3 불변 검증
   - 실제 테스트 결과
   - live API 미사용
5. `docs/PROGRESS.md`
6. `docs/AI_LOG.md`
7. 필요한 경우 tracked P0 backlog 문서

다음 사용자 파일은 문서화 대상으로 사용하지 마라.

- `PROJECT_DIRECTION.md`
- `docs/FEATURE_MAPPING.md`
- `docs/T4_COUNTRY_ENVIRONMENT_IMPLEMENTATION_PROMPT.md`

기존 문서의 테스트 개수는 실제 최종 실행 결과와 일치하도록 갱신한다.

---

## 20. 과잉 구현 금지

이번 작업에서 하지 말 것:

- Stage 1 환율 모델 변경
- Stage 2 계산 변경
- Stage 3 optimizer 변경
- 기존 runtime Stage 4 교체
- T5 전체 재작성
- T6 shortlist 재작성
- T7 보고서 구조 전면 재작성
- 국가 신용평가 모델
- 머신러닝 학습
- LLM 기반 국가분석
- 0~100 국가점수
- 부도확률
- 은행 내부등급 모사
- 실시간 뉴스 수집
- 범용 국가 데이터 플랫폼
- 데이터베이스·Redis·Celery 도입
- 신규 OCR
- 신규 web framework
- OpenAI API 호출
- World Bank·OECD·WTO runtime API 의존
- 미국·브라질 외 국가 확장
- 정책자금 신규 추천
- 금융상품 승인 예측
- regression baseline 갱신
- 기존 test split의 fine-tuning 포함
- Git push
- 사용자 파일 commit

---

## 21. 구현 순서

### Phase 0 — 저장소 감사와 브랜치

목표:

- 변경 범위와 기존 extension point 확인
- 사용자 파일 보호
- 전용 branch 생성

완료 기준:

- 관련 모델·서비스·테스트 위치 확인
- `6ad75ad` 기준 확인
- `feature/t4-country-risk` branch

중단 조건:

- tracked 미커밋 변경
- 기준 커밋 누락
- 사용자 변경과 충돌

### Phase 1 — 공식 출처와 데이터 계약

목표:

- OECD·World Bank·WTO 공식 원값 검증
- snapshot schema와 rule matrix 확정

완료 기준:

- US/BR source table 작성
- OECD `2026-06-26`·Brazil `4`·US unclassified 확인
- 각 URL·자료기간·한계 확인
- 두 대표 fixture 예상 결과 문서화

중단 조건:

- 핵심 OECD 공식값 충돌
- 공식 URL 확인 불가
- 원값 추측이 필요한 상황

### Phase 2 — Versioned snapshot·Domain

목표:

- strict schema
- offline snapshot
- loader·validator·hash

완료 기준:

- API 없이 로드
- canonical hash 결정성
- 변조 fail closed
- US/BR raw 상태 보존

### Phase 3 — 결정론 엔진

목표:

- 세 축 분리
- 공개 rule table
- 거래 검토 우선순위

완료 기준:

- US `ELEVATED_REVIEW`
- BR `HIGH_REVIEW`
- score 없음
- 근거·source·한계 포함

### Phase 4 — ConsultationPacket·Workflow 연결

목표:

- optional backward-compatible integration
- 정확한 invalidation 범위

완료 기준:

- legacy packet 유지
- T4 packet binding
- Stage 1~3 결과 보존
- 상담 topic만 보강

### Phase 5 — T7 보고서·최소 UI

목표:

- 구조화 근거 표시
- critic/fallback 정책
- 최소 사용자 카드

완료 기준:

- 세 축 분리 표시
- 공식 URL·기간·한계 표시
- 잘못된 국가등급 표현 critic 차단
- UI 전면 개편 없음

### Phase 6 — 테스트·문서화

목표:

- 신규·전체 회귀
- 감사 가능한 문서

완료 기준:

- 신규 P0 테스트 통과
- 기존 전체 테스트 통과
- verify PASS
- baseline 미변경
- 문서 수치 일치

### Phase 7 — 선택적 커밋

모든 필수 테스트 통과 후 T4 파일만 staging한다.

반드시 staging에서 제외:

- `PROJECT_DIRECTION.md`
- `docs/FEATURE_MAPPING.md`
- `docs/T4_COUNTRY_ENVIRONMENT_IMPLEMENTATION_PROMPT.md`

commit 전 확인:

- `git status`
- `git diff --cached --stat`
- `git diff --cached --check`
- 사용자 파일 staged 0건
- 비밀값 없음
- Stage 2·3 계산 변경 없음
- regression baseline 변경 없음

커밋 메시지:

`feat: add versioned country environment review`

Git push는 하지 마라.

---

## 22. Definition of Done

다음 조건을 모두 만족해야 완료다.

1. T4만 구현됨
2. 기존 T1~T3, T5~T7 재구현 없음
3. runtime Stage 4 유지
4. US·BR만 지원
5. OECD 기준일 `2026-06-26`
6. Brazil raw classification `4` 보존
7. Brazil 4를 자체 국가등급으로 표현하지 않음
8. US `HIGH_INCOME_OECD_UNCLASSIFIED` 보존
9. US를 LOW·0으로 변환하지 않음
10. OECD·World Bank·WTO 세 축 분리
11. 0~100 합산점수 없음
12. 국가 신용등급·부도확률 없음
13. 공식 URL·자료기간·원값·해석·한계 저장
14. versioned offline snapshot 구현
15. runtime API·인터넷 없이 재현
16. 같은 snapshot·입력에 동일 결과
17. US/BR 동일 거래조건 fixture
18. US `ELEVATED_REVIEW`
19. BR `HIGH_REVIEW`
20. 우선순위가 국가등급이 아님을 명시
21. Stage 2 결과 불변
22. Stage 3 후보·비율 불변
23. 상담 우선순위에만 반영
24. 상품 eligibility·approval 불변
25. `ConsultationPacket` optional 호환
26. T7 보고서와 critic·fallback 연결
27. 최소 UI 표시
28. 기존 JSON·sample 하위 호환
29. 신규·기존 테스트 실제 통과
30. verify PASS
31. 기존 regression baseline 미변경
32. test split fine-tuning 제외 유지
33. 사용자 미추적 파일 보존
34. 별도 T4 commit 완료
35. Git push 미실행

---

## 23. 최종 보고 형식

완료 후 반드시 다음 순서로 보고한다.

1. 저장소 감사 결과
2. 시작 branch·HEAD·git status
3. 기존 T6·T7 보존 확인
4. 공식 source 표
   - source
   - country
   - official URL
   - 기준일·관측기간
   - raw value/status
   - 한계
5. offline snapshot version과 hash
6. Domain 모델
7. OECD 처리
   - Brazil raw 4
   - US unclassified
8. World Bank 처리
9. WTO 처리
10. 공개된 priority rule table
11. US/BR 동일조건 비교 결과
12. ConsultationPacket 연결
13. T7 보고서·critic 연결
14. Stage 2·3 불변 증거
15. 변경 파일 목록
16. 신규 테스트 목록
17. 실제 실행 명령과 결과
18. 실패·미실행 테스트
19. 알려진 한계
20. 사용자 파일 보호 결과
21. 최종 commit hash
22. Git push를 하지 않았다는 사실

각 주장에는 실제 파일 경로와 테스트 이름을 연결한다.

계획만 작성하고 종료하지 마라.
저장소 감사부터 구현·테스트·문서화·별도 커밋까지 완료하라.
