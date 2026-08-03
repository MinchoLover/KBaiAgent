# 제출 기능 동결 기준

동결 기준 시점: 2026-08-03, `feature/submission-benchmark-evidence`, 시작 HEAD
`c98ac4946c084eb37429822bf80fab3422036b2b`, 제출 검증 707 tests PASS.

## 동결된 기능 범위

- 합성 문서 추출, 원문 대조와 사용자 거래 확정
- 환율 방향·중심·범위·horizon 표시와 고정 스트레스 현금흐름
- 저장된 뉴스 시장 배경과 정상 empty state
- 거래위험·국가환경·무역통계의 분리된 참고 맥락
- 공식 catalogue 16개, 금융 Top 3, 적격 overflow, deferred, auxiliary 분리
- `OfficialCandidateInputProfile`의 명시적 조건 우선과 상충 입력 차단
- 상담 우선순위, `ConsultationPacket`, Stage5 critic·결정론 fallback
- transaction/profile/Packet/report 결속과 stale 다운로드 차단
- 4개 사용자 탭과 1440×900·390×844 레이아웃

## 동결 이후 수정 허용

다음 P0 또는 제출 사실 오류만 최소 범위로 수정한다.

- 잘못된 금융 숫자나 의미
- 조건과 다른 금융후보, 비결정론 순서, auxiliary의 금융 Top 3 진입
- 거래 변경 뒤 stale 후보·Packet·보고서·다운로드 노출
- 주요 화면 크래시 또는 Golden 데모 완주 실패
- 개인정보·API key·문서 원문·내부 debug 정보 노출
- README·기술설명서·PPT·영상의 구현 사실 또는 숫자 불일치

수정할 때는 재현 테스트를 먼저 추가하고 해당 계약의 기대값을 완화하지 않는다.

## 동결 이후 수정 금지

- 새 상품, catalogue ID 또는 상품 점수
- 새 API·뉴스 crawler·web search
- 새 탭, 대규모 CSS 또는 정보구조 개편
- Stage1 모델, Stage2 계산, Stage3 헤지 규칙 변경
- 새 LLM 모델·DB·로그인·인증·RM 전송·예약·신청 기능
- Golden·Baseline·snapshot 재생성
- 공모전 제출에 필요하지 않은 로드맵 기능 구현

## 최종 검증 절차

1. `git status --short`와 staged 상태를 확인한다.
2. Golden·Baseline·국가환경·무역통계 보호 SHA를 대조한다.
3. live flag를 끈 상태에서 Demo A·D·E를 AppTest 또는 브라우저로 확인한다.
4. `PYTHONPYCACHEPREFIX=/tmp/kbaiagent-final python scripts/verify.py`를 실행한다.
5. `git diff --check`를 실행한다.
6. catalogue 16개, Golden 후보 순서, 금융후보 최대 3개를 다시 확인한다.
7. PPT·영상·README·기술설명서의 숫자를 `DEMO_SCENARIO_MATRIX.md`와 대조한다.

## 최종 commit 전 확인사항

- 승인된 변경 파일만 stage한다.
- `.env`, 실제 업로드, cache, pycache와 live 응답이 포함되지 않았는지 확인한다.
- commit diff에서 secret·원문·내부 운영 주소를 검색한다.
- 최종 verify와 보호 SHA 결과를 기록한다.
- commit과 push는 별도의 명시적 승인 후 수행한다.
