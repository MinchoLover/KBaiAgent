# KB AI Challenge P0 구현 계획

## 1. 제품과 사용자

- 제품: 수출입 금융 의사결정 지원 에이전트
- 한 줄 목적: 수출입 거래의 환율 위험을 실제 현금 문제로 변환하고 필요한 KB 상담을
  준비한다.
- 주 사용자: 수출입 중소기업 재무·자금 담당자
- 보조 사용자: 사용자에게 공유받은 패킷을 검토하는 KB 상담 담당자

## 2. 하나의 주 사용자 여정

1. 샘플 또는 실제 거래문서를 불러와 핵심 거래값과 거래 방향을 확인한다.
2. 회사 현금·외화·대출한도와 환율 스트레스를 입력해 Stage 2 계산을 실행한다.
3. 결정론 엔진이 위험 코드와 근거를 만들고 규칙 기반 상담 대응을 연결한다.
4. 사용자가 JSON·Markdown KB 상담 준비 패킷과 보고서를 내려받는다.

## 3. P0 범위

P0 기능을 네 개의 제품 역량으로 묶습니다.

1. 확인된 수입·수출 거래 인테이크
2. 기존 Stage 2 계산 및 구조화 위험 분류
3. 위험 기반 일반 금융상담 대응과 KB 상담 패킷
4. 외부 API 없는 수입·수출 E2E 데모, 화면, 테스트, 문서

## 4. 명시적 비목표

- 실시간 뉴스 감성분석 및 환율 예측 모델
- 은행 내부 API, 자동 대출 적격성, 자동 상품 추천
- 환헤지 주문 및 금융 거래 실행
- 새로운 웹 프레임워크, 데이터베이스, 인증·권한 인프라
- 공식 출처가 없는 KB 상품명·금리·한도 생성

## 5. 구현 순서

| 순서 | 작업 | 재사용할 기존 코드 | 수정 파일 | 완료조건 | 검증 명령 |
| -: | --- | --- | --- | --- | --- |
| 1 | 변경 전 기준선·범위 기록 | Git, `scripts/verify.py` | `docs/repositioning/CURRENT_STATE.md`, `IMPLEMENTATION_PLAN.md` | 실제 Git/테스트 결과가 문서에 기록됨 | `git diff --check` |
| 2 | 거래 방향 사용자 확인 추가 | `ConfirmationState`, confirmation gate | `schemas.py`, `src/document_intake/confirmation.py`, `app.py`, 관련 테스트 | 통화·금액·결제일·거래 방향 네 항목 없이는 Stage 2가 열리지 않음 | `python -m unittest tests.test_schemas_validators tests.test_workflow -v` |
| 3 | 구조화 위험 분류 | `Stage2Result`, `Decimal` 유틸 | `src/domain/consultation_models.py`, `src/consultation/risk_classifier.py` | 수입/수출 FX, 손실한도, buffer, 음수현금, payment gap, timing, 정보누락 코드와 근거 출력 | 신규 단위 테스트 |
| 4 | 규칙 기반 상담 대응 | risk codes, 거래 유형 | `src/consultation/response_mapping.py` | 일반 상담 범주만 반환하고 중복 제거·사람 검토 표시 | 신규 단위 테스트 |
| 5 | 상담 패킷 JSON·Markdown | confirmation fingerprint, Stage 1/2 JSON | `src/consultation/packet.py`, domain models | 버전·입력 hash·확정필드·질문·서류·고지문과 계산 숫자 일치 | 신규 패킷 테스트 |
| 6 | 수입·수출 오프라인 사례 | `sample_extraction`, orchestrator, Stage 2 | `src/application/demo_service.py`, `src/demo.py` | 두 사례가 계산부터 상담 패킷까지 API 없이 완료 | 신규 E2E 테스트 |
| 7 | Streamlit 결과 재포지셔닝 | 기존 CSS/컴포넌트/Stage 2 결과 | `app.py`, 필요 시 `src/ui/components.py` | 위험 원인·상담 대응·패킷 다운로드가 동일 흐름에 보임 | Streamlit bare-mode 테스트 |
| 8 | 회귀·문서·발표 자료 | 기존 README·검증 스크립트 | `README.md`, `TEAM_POSITIONING.md`, `FINAL_REPORT.md`, 관련 docs | 구현·미구현·테스트 수가 실제 결과와 일치 | `python scripts/verify.py` |

## 6. 공용 계약 변경 원칙

- `Stage2Input`, `Stage2Result`, Stage 1 JSON/REST adapter 계약은 변경하지 않습니다.
- `ConfirmationState`에는 하위 호환 기본값을 둔 `trade_type_confirmed`를 추가하되,
  저장소 내부의 모든 확정 경로는 명시적으로 값을 전달합니다.
- 새 위험·상담·패킷 모델은 기존 `StrictModel`을 재사용합니다.
- 모든 금액은 decimal 문자열이며 계산은 `Decimal`만 사용합니다.
- 공용 DTO 변경은 세 팀원이 합의하고 샘플 JSON·테스트·문서를 함께 갱신해야 합니다.

## 7. 수용 테스트

| 여정 | Given | When | Then |
| --- | --- | --- | --- |
| 수입 성공 | USD 100,000, 보유 USD 20,000, 환율 1,400/+5%, 현금 130,000,000원 | 오프라인 E2E 실행 | open USD 80,000, 기준 112,000,000원, +5% 117,600,000원, 추가비용 5,600,000원 및 buffer 위험 |
| 수출 성공 | USD 수출대금과 하락 스트레스 | 계산·분류·패킷 실행 | 환율 하락 시 원화 수취 감소와 `FX_RECEIPT_RISK` |
| 확인 실패 | 거래 방향 확인이 false | Stage 2 진입 | `WAITING_FOR_USER`, 계산 runner 미호출 |
| payment gap 구분 | 결제 후 현금은 음수이고 신용한도로도 보전 불가 | 위험 분류 | buffer 위험과 별도로 `PAYMENT_CAPACITY_RISK` |
| 외부 서비스 실패 | API 키와 Stage 1 endpoint 없음 | 전체 데모 | fixture, 수동 스트레스, 일반 상담 범주, 결정론 패킷으로 완료 |

## 8. 데모 경로

1. 수입 또는 수출 샘플을 선택하고 네 핵심값을 확인한다.
2. 회사 현금과 보유 외화를 입력하고 스트레스 시나리오를 실행한다.
3. 열린 환노출, 추가 비용/수취 감소, 현금 방어선과 실제 지급 부족을 확인한다.
4. 위험 원인과 검토할 금융 대응을 확인한다.
5. KB 상담 준비 패킷 JSON·Markdown을 내려받는다.
