# Repository Audit

감사일: 2026-07-23, 환경: macOS / Python 3.9.6.

## CRITICAL

| 발견 | 위험 | 조치 |
|---|---|---|
| 기존 UI가 단일 submit으로 추출값을 Stage 2 JSON에 전달 | 금액·통화·결제일 오인식이 금융 계산에 직접 유입 | 세 필드 독립 확인, CRITICAL/HIGH PASS, 확인 기록을 모두 요구하는 gate 구현 |
| 사용자 역할·업로드가 바뀌어도 기존 session 결과가 남을 수 있음 | 서로 다른 문서 계산 결과 혼합 | file bytes/role/country/mode signature 기반 전체 state invalidation 구현 |

## HIGH

| 발견 | 위험 | 조치 |
|---|---|---|
| 스키마가 당사자 국가, installments, evidence 상세, review 상태를 충분히 표현하지 못함 | 계약/분할/근거 평가 불가 | strict Pydantic v2 전체 schema와 JSON 계약 추가 |
| validator가 금액·다중통화·날짜충돌·evidence를 검사하지 않음 | 환각·충돌 자동 통과 | 결정론 validator와 severity issue code 구현 |
| 업로드가 브라우저 MIME과 크기만 신뢰 | 위장·손상·과대 파일 처리 | extension/MIME/magic/실제 parse/page 교차검사 구현 |
| API 오류가 raw exception으로 노출될 수 있음 | secret·문서정보 유출 가능 | 일반화된 오류와 redaction 구현 |
| Python float 중심 계산 가능성 | 금융 반올림·재현성 오류 | Stage 1~3 계산을 Decimal 문자열 계약으로 구현 |
| 기존 헤지 처리 규칙 없음 | open exposure와 총 현금결제 혼동 | 헤지는 노출에서 차감하되 계약 현금흐름에 유지 |
| 분할결제별 계산에서 자연상계 잔여량과 일괄 hedge fee를 독립 재사용할 수 있음 | 총 상계·수수료가 회차 수만큼 왜곡 | 날짜 적격 capped allocation과 수수료 비례 배분 구현 |
| PDF 미리보기가 Streamlit 기본 설치만으로 런타임 실패 | 데모 중 PDF 업로드 화면 중단 | 호환되는 `streamlit-pdf==1.0.8`을 고정하고 AppTest로 검증 |

## MEDIUM

| 발견 | 위험 | 조치 |
|---|---|---|
| prompt가 코드에 결합되고 version/few-shot 관리 없음 | 변경 추적·회귀 분석 불가 | `prompts/` 5개 파일과 version loader 추가 |
| 정답셋·평가·회귀 체계 없음 | 모델 품질과 실패 원인 측정 불가 | 16 synthetic + 1 sample, offline/live evaluator, regression gate 추가 |
| Stage 1 팀 계약이 없음 | 단위·통화·날짜 오류 | JSON/REST adapter와 정규화, fallback 추가 |
| 상품 출처 정책 없음 | 비공식 광고/환각 후보 | 공식 KB, URL allowlist, optional web search 추가 |
| 보고서가 계산값을 바꿀 수 있음 | 숫자 환각 | critic, 1회 revision, deterministic fallback 추가 |
| 테스트 3개만 존재하고 새 schema와 불일치 | 핵심 위험 회귀 미탐지 | 133개 기준선과 후속 보강 후 158개 API-free 테스트 |
| 보고서 숫자가 존재하는 임의 JSON path만 인용해도 통과 가능 | 잘못된 근거 연결 | 각 숫자가 같은 줄의 실제 JSON path 값에 포함되는지 critic이 검증 |
| REST/web 응답 크기·cache 정책이 느슨함 | 과대 응답·오래된 allowlist 결과 재사용 | Stage 1 1MB 제한, cache key에 모델·도메인 포함, cache hit 재검증 |

## LOW

| 발견 | 위험 | 조치 |
|---|---|---|
| README가 WEBP/10MB/Commercial Invoice 중심이라고 기재했으나 목표와 불일치 | 실행·데모 혼선 | 실제 PDF/PNG/JPEG, 15MB/20페이지, Stage 0~5 명령으로 갱신 |
| 모델 기본값이 여러 곳에 노출 | 설정 drift | `src/config.py` 단일 환경변수 source로 통합 |
| 의존성이 넓은 range | 재현성 저하 | 검증 환경 버전으로 requirements pin |
| Git 저장소가 아님 | branch/commit 이력 생성 불가 | 파일 변경 목록과 validation report로 인계; Git 파괴 작업 없음 |

## 잔여 감사 항목

실제 OpenAI 문서 추출과 공식 web search는 키가 없어 실행하지 않았습니다. 운영 인증,
malware scanner, 중앙 감사로그, 실제 문서 보존정책은 MVP 범위 밖이며
`docs/LIMITATIONS.md`에 남겼습니다.
