# Secret·개인정보 Read-only 감사

감사일: 2026-08-03

## 결과 요약

| 항목 | 결과 |
| --- | ---: |
| 추적 파일 검사 | 361개 |
| 비추적 실제 파일 검사 | 49개 |
| credential 변수명·참조 출현 | 추적 171건 / 비추적 21건 |
| 고신뢰 실제 credential 의심 | 0건 |
| private key block | 0건 |
| 추적 `.env*` | 0개 |
| 표준 비추적 `.env*` | 0개 |
| Git에서 무시되는 로컬 `.env` | 1개, **제출 제외 필수** |
| 로컬 `.env`의 비어 있지 않은 민감 설정 | 2개, 값 미출력 |
| notebook·log·PEM/key 파일 | 0개 |
| 값이 보고서에 포함됐는가 | NO |

로컬 `.env`는 `.gitignore`로 무시되고 있으나 실제 파일은 존재한다. 내용과 key 값은
출력하지 않았고, 비어 있지 않은 민감 설정의 개수만 확인했다. 제출 압축과 화면 녹화,
터미널 출력에서 이 파일을 반드시 제외해야 한다.

## 휴리스틱 재검토

초기 URL/query credential 휴리스틱이 아래 8개 위치를 표시했다. 각 행을 값 없이
구문 형태로 재검토한 결과 모두 하드코딩 문자열이 아니라 `api_key=[REDACTED]` 형태의
심볼 전달이었다.

| 범위 | 경로 | 행 | 재검토 결과 |
| --- | --- | ---: | --- |
| TRACKED | `src/document_intake/extractor.py` | 131 | SYMBOL_REFERENCE |
| TRACKED | `src/document_intake/openai_adapter.py` | 102 | SYMBOL_REFERENCE |
| TRACKED | `src/stage1/spot_rate.py` | 296 | SYMBOL_REFERENCE |
| TRACKED | `src/stage4/official_search.py` | 253 | SYMBOL_REFERENCE |
| TRACKED | `src/stage5/report_agent 2.py` | 63 | SYMBOL_REFERENCE, legacy duplicate 검토 필요 |
| TRACKED | `src/stage5/report_agent.py` | 166 | SYMBOL_REFERENCE |
| UNTRACKED | `src/application/country_economic_interpretation_service.py` | 105 | SYMBOL_REFERENCE |
| UNTRACKED | `src/application/trade_statistics_interpretation_service.py` | 115 | SYMBOL_REFERENCE |

검사한 고신뢰 형태는 OpenAI·AWS·GitHub·Google token, JWT, literal Bearer token,
private key block과 credential query literal이다. 변수명 검색 결과는 구현 계약의 존재를
보여줄 뿐 실제 secret 유출 건수로 계산하지 않았다.

## 개인정보·문서 확인

- UI 캡처 8개를 시각 검수했으며 합성 거래 외 개인정보·이메일·계좌·API key를
  발견하지 않았다.
- 신규 비추적 PDF `us_export_net60_text_009.pdf`는 synthetic label·manifest와
  dataset 회귀 테스트에 결속된 비식별 검증 자산이다.
- 실제 고객 업로드, raw OpenAI 응답, raw 관세청 응답 또는 shell history 파일은
  추적·표준 비추적 목록에서 발견되지 않았다.
- 최종 PPT와 영상은 존재하지 않아 그 안의 개인정보·알림·secret은 검수하지 못했다.

## 수동 확인 필요

- 최종 패키지 구성 시 `.env` 제외를 다시 검사한다.
- PPT와 영상이 추가되면 시각·음성 전체를 별도로 검수한다.
- 실제 secret 문자열을 검색어·로그·보고서에 출력하지 않는다.
