# Codex 계속 실행 프롬프트

아직 완료가 아니다. 지금까지의 대화 설명을 반복하지 말고 현재 저장소 상태와 마지막 명령 결과부터 확인하라.

다음 순서로 즉시 계속하라.

1. `git status`와 변경 파일 확인
2. 미완성 TODO, placeholder, `pass`, `NotImplementedError`, 임시 mock-only 경로 검색
3. `python -m compileall .`
4. 전체 테스트 실행
5. `python scripts/evaluate_extraction.py --mode offline`
6. `python scripts/verify.py`
7. 실패의 첫 root cause부터 수정
8. 동일 오류를 방지하는 테스트 추가
9. 다시 전체 검사

다음 상태가 모두 될 때까지 계획만 말하고 멈추지 마라.

- API 키 없는 sample mode end-to-end PASS
- 사용자 확인 전 Stage 2 차단 PASS
- 수입·수출 Stage 2 테스트 PASS
- Stage 1 manual/external adapter PASS
- 문서 추출 offline evaluation PASS
- `.env`와 secret leakage 검사 PASS
- README 명령과 실제 명령 일치
- `docs/VALIDATION_REPORT.md` 최신화

현재 환경에서 실제 API 키가 없어 live test만 못 한다면, mock으로 API request payload와 parsing 경로를 검증하고 `live_smoke_test.py`를 남겨라. 그 외의 실패를 API 키 부재 탓으로 돌리지 말라.

마지막에는 실행한 명령과 실제 PASS/FAIL 수치를 보고하라.
