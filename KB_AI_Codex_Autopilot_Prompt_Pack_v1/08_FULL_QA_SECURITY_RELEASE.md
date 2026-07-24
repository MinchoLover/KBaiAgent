# 전체 QA·보안·릴리스 프롬프트

현재 기능 개발은 끝났다고 가정하지 말고 릴리스 후보로 엄격하게 감사하라.

1. 코드베이스 전체 구조와 dead code 감사
2. Python 3.9 clean venv 설치
3. compileall
4. 전체 unit/integration/offline e2e
5. prompt/data regression
6. sample imports/exports
7. secret scan
8. upload security tests
9. temp file cleanup tests
10. README commands copy-paste 검증
11. macOS/Windows launch scripts 검토
12. 오류 메시지와 사용자 복구 경로
13. 성능과 API 비용 계측 포인트
14. 금융 표현과 면책 검토
15. 공식 출처 보존 여부

치명도 분류:

- CRITICAL: 숫자 오류, secret 노출, 잘못된 Stage 2 전달, 사용자 확인 우회
- HIGH: 수입/수출 방향 오류, 파일 미삭제, 출처 없는 상품
- MEDIUM: UI 상태 손실, 경고 누락, 회귀테스트 부족
- LOW: 문서/스타일

모든 CRITICAL/HIGH를 해결하고 테스트를 추가하라. MEDIUM은 가능한 만큼 해결하고 남은 항목을 backlog로 명시하라.

릴리스 산출물:

- `RELEASE_CHECKLIST.md`
- `docs/VALIDATION_REPORT.md`
- `docs/SECURITY_PRIVACY.md`
- `CHANGELOG.md`
- `.env.example`
- `requirements.txt`
- `SHA256SUMS.txt` 또는 package manifest
- clean ZIP 생성 스크립트

마지막에 실제 명령 출력과 PASS 수치를 기록하라. 테스트를 생략하고 문서상 PASS라고 쓰지 말라.
