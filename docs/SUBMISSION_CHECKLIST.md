# 공모전 제출 체크리스트

기준일: 2026-08-03. 체크 표시는 현재 작업트리에서 확인한 항목만 의미한다.

## 코드와 검증

- [x] branch와 HEAD 기록
- [x] 기존 미커밋 선행 작업 보존
- [x] Golden profile 없는 Top 3 순서 확인
- [x] Demo A~E 결정론 시나리오 테스트
- [x] catalogue 16개 및 금융 shortlist 최대 3개 확인
- [x] stale transaction/profile/Packet/report 차단 확인
- [x] production UI 내부 식별자·hash·critic 기본 미노출 회귀
- [x] 1440×900 및 390×844 브라우저 smoke와 캡처
- [x] `python scripts/verify.py`: 707 tests PASS
- [x] `git diff --check`
- [ ] 최종 커밋 직전 위 검증을 다시 실행

## 환경변수와 보안

- [x] 데모는 합성 문서만 사용
- [x] 화면·캡처·문서에 API key 값 없음
- [x] OpenAI·관세청·공식 web search 없이 Golden 완주 가능
- [ ] 발표 노트북에서 live 관련 flag를 끄고 file/manual 데모 설정 확인
- [ ] `.env` 파일이 제출 압축·화면 녹화·Git diff에 포함되지 않았는지 최종 확인
- [ ] 터미널 기록에 secret query 또는 key가 없는지 최종 확인

## 데모와 캡처

- [x] 거래 분석 캡처
- [x] 환율 전망·시장 배경 캡처
- [x] Golden 금융후보 캡처
- [x] 상담 준비·보고서 캡처
- [x] Demo D 동적 후보 캡처
- [x] Demo E 모순 차단 캡처
- [x] 모바일 환율·금융후보 캡처
- [ ] 발표용 모니터 배율과 브라우저 확대 100% 확인
- [ ] 5~7분 데모 영상 녹화 및 재생 확인

## 제출 문서

- [x] README 최종 4탭·뉴스·추천 계약 반영
- [x] 기술설명서 숫자와 구현 범위 정렬
- [x] `FINAL_DEMO_SCRIPT.md`
- [x] `DEMO_SCENARIO_MATRIX.md`
- [x] `SCREENSHOT_MANIFEST.md`
- [x] `SUBMISSION_PPT_UPDATE_NOTES.md`
- [x] `SUBMISSION_FREEZE.md`
- [ ] PPT 슬라이드 6·9·10·11·12 실제 교체
- [ ] PPT와 영상의 Golden 숫자를 화면·보고서와 대조

## Git과 제출물

- [x] 이 회차 commit/push 없음
- [x] staged 변경 없음
- [ ] 최종 리뷰 승인 후 단일 범위의 commit 계획 확정
- [ ] 제출 저장소 또는 압축파일에 `.env`, 실제 업로드, cache, pycache 제외
- [ ] 제출 파일명을 공모전 규정과 일치시킴
- [ ] 압축파일을 새 디렉터리에 풀어 README 실행 절차 재검증

권장 제출 압축 내용:

- 애플리케이션 소스와 `requirements.txt`
- README와 기술설명서
- Golden 합성 데모 자산
- 제출용 스크립트·체크리스트·PPT 교체 노트
- 필요 시 개인정보가 없는 UI evidence
