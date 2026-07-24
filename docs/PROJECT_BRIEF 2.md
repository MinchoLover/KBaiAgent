# Project Brief

## Problem

수출입 기업이 문서에서 거래금액·통화·결제일을 수작업으로 옮기고 환율 시나리오와
현금계획을 별도로 계산하면서 추출 오류, 단위 오류, 유동성 위험을 놓칠 수 있습니다.

## Users

- P0: 수출입 중소기업 재무·자금 담당자
- P1: 거래은행·보험기관 상담 전에 자료를 정리하는 팀
- 운영자: 문서 AI prompt/evaluation과 팀 Stage 1 연결 담당자

## MVP Outcome

문서 근거와 확인 기록을 가진 거래 입력을 만들고, 같은 입력에 같은 환율·현금흐름
결과와 안전한 후보 보고서를 로컬 한 앱에서 생성합니다.

## P0 Acceptance

- PDF/PNG/JPEG 안전 업로드와 demo/live 추출
- strict schema, evidence, deterministic validation, human confirmation gate
- manual/external Stage 1
- Decimal Stage 2와 날짜별 ledger
- Streamlit 결과·차트·JSON/Markdown 다운로드
- API 없는 tests/verify/end-to-end

## P1 Acceptance

- 16건 이상 dataset, eval, regression, fine-tuning candidate export
- Stage 3 top-3 candidates
- Stage 4 offline official KB
- Stage 5 critic and deterministic fallback

## P2

- allowlist official web search와 cache 구현은 포함했으나 live 미검증
- CI/Docker/production auth는 후속

## Non-goals

- 팀원의 FX forecast model 재구현
- fine-tuning job 자동 실행
- 금융상품 승인 또는 최종 자문
- 확률 없는 데이터에서 예상값 생성
