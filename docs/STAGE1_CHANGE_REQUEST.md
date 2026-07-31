# Stage 1 Change Request

현재 JSON과 endpoint는 메인 앱 통합에 충분하여 Stage 1 원본 코드 변경은
필수는 아닙니다. 운영 전 다음 최소 개선을 팀원 저장소에 요청합니다.

1. `/health`와 `/api/forecast`의 CORS `*`를 배포 origin allowlist로 제한
2. JSON schema version 변경 시 changelog와 호환 기간 제공
3. 생성 결과를 atomic write해 부분 JSON 노출 방지
4. health에 model bundle version과 latest market date를 구조화해 제공
5. 뉴스 오류와 가격모델 오류 상태를 HTTP health에서도 분리

메인 앱은 이 변경을 기다리지 않고 현재 계약을 검증하며, 변경 전까지
file/mock fallback을 명시적으로 표시합니다.
