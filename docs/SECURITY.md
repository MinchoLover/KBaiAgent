# Security

## 적용된 통제

- `.env`, Streamlit secrets, 실제 업로드와 live prediction 출력 Git 제외
- 설정 객체에서 API key repr 제외, 오류 메시지에 key·원문 응답 미포함
- PDF/PNG/JPEG 확장자·MIME·magic bytes·크기·PDF 페이지 검증
- 실제 문서는 메모리 처리하며 dataset이나 trace에 자동 저장하지 않음
- prompt injection 문구는 문서 데이터로만 취급하고 validator warning
- 추출 결과는 Pydantic·결정론 규칙·사용자 확인 뒤에만 계산 전달
- Stage 1 HTTP timeout/retry/응답 크기/content type/redirect/remote host 제한
- 공식 상품 검색은 HTTPS 공식 도메인 allowlist와 기준일·출처 필수
- LLM report 입력에서 문서 `source_text`와 confirmation `original_values` 제외
- trace는 case/status/time/provider/fallback만 저장

## 남은 운영 위험

- 인증·tenant별 데이터 분리·권한 관리 미구현
- 중앙 감사로그와 보존/삭제 정책 미구현
- malware scanner·sandboxed PDF rendering 미구현
- production egress proxy와 DNS rebinding 방어 미구현
- Streamlit 세션 종료 전 사용자가 내려받은 보고서의 로컬 보관 통제는 운영 필요

공개 배포 전 위 항목과 TLS, secret manager, rate limit, dependency/CI scan을
추가해야 합니다. 자세한 기존 정책은
[`SECURITY_PRIVACY.md`](SECURITY_PRIVACY.md)를 봅니다.
