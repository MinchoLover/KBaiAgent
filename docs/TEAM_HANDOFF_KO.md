# 팀 인수인계

## 팀원 A — 문서 인테이크와 화면

- 담당: `app.py`, `src/document_intake/`, `src/ui/`
- 완료조건: 문서/샘플 → evidence → 거래방향·통화·금액·결제일 확인 gate
- 변경 금지: `Stage2Input`, `ConfirmationRecord` 필드는 합의 없이 변경하지 않음
- 테스트: `python -m unittest tests.test_document_intake tests.test_workflow -v`
- 연결: 확인된 거래 fingerprint를 팀원 C의 Stage 2에 전달

## 팀원 B — Stage 1과 환율 데이터

- 담당: `src/stage1/`, `src/application/market_integration_service.py`,
  `src/integration_assets/stage1/`
- 완료조건: HTTP/file/mock, spot provenance, q 시나리오와 horizon 경고
- 변경 금지: 팀 `kb_macro_ai` raw JSON path, `NormalizedStage1Forecast`
- 테스트: `python -m unittest tests.test_stage1_web_integration -v`
- 연결: Stage 2에는 `NormalizedScenarioSet`만 전달, 뉴스는 숫자에 미반영

## 팀원 C — 계산·후속 의사결정

- 담당: `src/stage2/`~`src/stage5/`, `src/consultation/`,
  `src/workflow/`, 통합 테스트
- 완료조건: Decimal ledger, 위험 코드, 결정론 상담 Top 3, canonical handoff,
  제약 후보, 공식근거, verified report
- 변경 금지: `ConfirmedTrade`, scenario quote convention
- 테스트: `python scripts/verify.py`
- 연결: 팀원 A의 confirmed fingerprint, 팀원 B의 scenario set을 결합

## 공용 계약과 브랜치

`schemas.py`, `src/domain/`, Stage 1 raw mapping, Stage 2 입력·출력은 세 명 합의
없이 변경하지 않습니다. 각 기능 브랜치는 담당 디렉터리 중심으로 만들고, 공용
계약 변경 PR을 먼저 병합한 뒤 구현 PR을 rebase합니다.

## 팀에 쉽게 설명할 문장

“Stage 1 팀원은 앞으로 한 달의 환율 경로가 어느 정도 흔들릴 수 있는지 계산하고,
메인 앱은 그 결과를 우리 회사 계약금액과 현금 일정에 대입합니다. AI가 돈을
계산하는 게 아니라 문서를 읽고 시장 문맥을 설명하며, 실제 금액은 Decimal 코드가
계산합니다. 마지막에는 기존 위험 finding이 회수 보호·환율·유동성의 검토 순서를
결정하고, 같은 JSON에서 숫자·부족정보·질문·서류가 있는 KB 상담 handoff를
만듭니다. 상품·승인·실제 RM 전송은 확정하지 않습니다.”
