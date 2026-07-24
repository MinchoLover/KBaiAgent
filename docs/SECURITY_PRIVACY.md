# Security and Privacy

## 파일 경계

- 허용 확장자와 MIME: PDF, PNG, JPEG
- 기본 15MB, PDF 20페이지
- extension, claimed MIME, magic bytes 교차 검증
- Pillow image verify 및 strict PDF parse
- archive, 암호화·손상·빈 PDF, 위장 파일 차단
- 파일명에서 경로와 특수문자 제거

실제 파일은 메모리 bytes로 처리하며 dataset에 자동 복사하지 않습니다. API에 base64로
직접 전달하므로 장기 OpenAI file object를 만들지 않습니다.

## 비밀과 로그

API 키는 `.env` 또는 서버 환경변수에서만 읽습니다. 설정 객체 repr에도 키를 노출하지
않습니다. 오류 메시지는 원문/API response dump 대신 일반화된 안내를 사용합니다.
로그가 필요하면 request id, SHA-256, status, latency만 저장하고 원문 전체는 저장하지
않습니다. redaction 함수는 API key와 bearer token 패턴을 제거합니다.

## Prompt injection

시스템 프롬프트는 첨부 문서를 신뢰하지 않는 데이터로 정의합니다. “ignore previous
instructions”, “system prompt” 같은 문구는 evidence 텍스트로만 처리하고 실행하지
않습니다. validator가 해당 패턴을 warning으로 올립니다. 모델 출력은 strict schema와
deterministic rule을 통과해야 합니다.

## 공식 검색

웹 검색은 기본 OFF, 공식 도메인 allowlist를 tool filter와 결과 URL 양쪽에서
검사합니다. host suffix 검사는 `ksure.or.kr.evil.example` 같은 lookalike를 거부합니다.
민간 블로그와 광고를 근거로 사용하지 않습니다. cache는 timezone 포함 생성시각,
기본 24시간 TTL, query·거래방향·allowlist를 재검증합니다.

## Stage 1 outbound

REST endpoint는 기본적으로 HTTPS와 public IP만 허용합니다. URL userinfo·fragment와
redirect를 거부하고, DNS 결과에 사설·loopback·link-local·예약 IP가 하나라도 있으면
요청하지 않습니다. 운영에서는 `STAGE1_ALLOWED_HOSTS` exact allowlist를 함께
사용합니다. 사설 endpoint 허용 설정은 로컬 개발에서만 사용합니다.

## 운영 권고

- 문서 전송 전 회사 개인정보·국외이전 정책 확인
- 실제 문서 보존기간과 접근권한을 별도 운영 정책으로 정의
- 공용 PC에서는 `.env`, cache, 다운로드 보고서를 세션 후 삭제
- production에는 인증, 전송구간 보호, 감사로그 저장소, malware scanner를 추가
