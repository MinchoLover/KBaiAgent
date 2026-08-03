# 대용량·임시파일 감사

감사일: 2026-08-03

## 추적·표준 비추적 파일

감사 문서 생성 전 기준 추적 361개와 비추적 실제 파일 43개, 총 404개를 측정했다.
감사 Markdown 6개를 추가한 뒤 추적 361개와 비추적 49개, 총 410개를 다시 측정했다.

| 기준 | 파일 수 |
| --- | ---: |
| 5MB 이상 | 0 |
| 20MB 이상 | 0 |
| 50MB 이상 | 0 |
| 100MB 이상 | 0 |

가장 큰 추적 파일은 `app.py` 약 353KB이고, 가장 큰 비추적 파일은
`demo_d_dynamic_candidates_1440.png` 약 328KB다. UI 캡처는 서로 다른 화면이며
중복 이미지로 판정하지 않았다.

## Git에서 무시되는 로컬 항목

| 경로 | 크기·상태 | 추적 | 제출 필요 | 권고 |
| --- | --- | --- | --- | --- |
| `.venv/` | 약 315MB | NO | NO | EXCLUDE, 100MB 이상 로컬 의존성 |
| `.env` | 민감 설정 존재 | NO | NO | EXCLUDE, 절대 압축하지 않음 |
| `__pycache__/` | `.pyc` 존재 | NO | NO | EXCLUDE |
| `tests/__pycache__/` | `.pyc` 존재 | NO | NO | EXCLUDE |
| `.streamlit/` | `config.toml`은 추적 파일 | YES | 실행 설정 | config만 포함, runtime cache로 확대하지 않음 |

표준 추적·비추적 목록에서 `.zip`, `.tar`, `.7z`, log, notebook, `.DS_Store`, raw API
response, raw LLM response 또는 browser profile은 발견되지 않았다.

## 이름상 legacy duplicate 후보

아래 파일은 대용량은 아니지만 초기 커밋부터 존재하는 별도 사본이며 현재 canonical
모듈과 동일하지 않다. 이번 회차에서는 삭제·수정하지 않는다.

| 경로 | 크기 | 추적 | 현재 판단 | 권고 |
| --- | ---: | --- | --- | --- |
| `src/stage5/report_agent 2.py` | 4,530B | YES | canonical `report_agent.py`와 비동일 | 패키지 제외 또는 삭제 여부 사람 결정 |
| `src/stage5/critic 2.py` | 4,284B | YES | legacy duplicate 후보 | 사람 결정 |
| `src/demo 2.py` | 3,987B | YES | legacy duplicate 후보 | 사람 결정 |
| `docs/PROJECT_BRIEF 2.md` | 1,486B | YES | legacy 문서 후보 | 사람 결정 |

이 항목들은 현재 수정 diff에는 없고 기존 이력의 일부다. 저장소 링크 자체를 제출하면
노출되므로 최종 사람 diff·패키지 manifest 검토가 필요하다.
