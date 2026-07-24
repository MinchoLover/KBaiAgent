# KB AI Codex Autopilot Prompt Pack

이 팩은 현재 저장소를 Codex가 직접 감사하고, **문서 인테이크(0단계) + 현금흐름 리스크 엔진(2단계) + 나머지 단계의 연결 가능한 MVP**로 완성하게 만드는 복붙용 프롬프트 모음이다.

## 가장 빠른 사용법

1. 개발할 저장소를 Codex로 연다.
2. 가능하면 현재 코드를 Git에 커밋하거나 폴더를 복사해 백업한다.
3. `00_ONE_CLICK_MASTER_PROMPT.md`의 전체 내용을 Codex에 붙여 넣는다.
4. Codex가 중간에 멈추면 `01_CONTINUE_UNTIL_GREEN.md`를 붙여 넣는다.
5. 특정 기능을 별도로 강화할 때 나머지 번호 프롬프트를 사용한다.
6. 최종 검수는 `08_FULL_QA_SECURITY_RELEASE.md`, 발표 준비는 `09_DEMO_PITCH_PACKAGE.md`를 사용한다.

## 중요한 원칙

- 이 프로젝트의 “학습”은 우선 **정답 데이터셋 + Few-shot + 자동 평가 + 실패사례 개선**을 의미한다.
- 파인튜닝은 충분한 사람 검수 데이터와 반복 실패가 확인되기 전에는 실행하지 않는다.
- LLM은 문서를 읽고 설명하지만, 금액·날짜·손실 계산은 결정론적 Python 코드가 수행한다.
- API 키가 없을 때도 샘플 모드와 자동 테스트가 돌아가야 한다.
- API 키를 `.env`에 넣으면 실제 PDF·PNG·JPG 문서를 분석할 수 있어야 한다.
- 팀원이 담당한 1단계 환율 예측은 침범하지 않고, JSON 어댑터와 수동 시나리오 fallback만 구현한다.

## 추천 실행 순서

```text
00 마스터 프롬프트
→ 01 계속 실행 프롬프트(필요할 때 반복)
→ 실제 API 키로 smoke test
→ 03 팀원의 Stage 1 출력 연결
→ 08 전체 QA·보안·릴리스
→ 09 데모·발표 패키지
```

## 프롬프트 파일 안내

- `00_ONE_CLICK_MASTER_PROMPT.md`: 현재 저장소를 한 번에 완성하는 메인 프롬프트
- `01_CONTINUE_UNTIL_GREEN.md`: Codex가 계획만 말하거나 중간에 멈췄을 때
- `02_FIX_ANY_ERROR.md`: 실행 오류를 자동 조사·수정할 때
- `03_STAGE1_TEAM_INTEGRATION.md`: 팀원의 1단계 결과와 연결할 때
- `04_DOCUMENT_DATASET_EVALS.md`: 문서 정답 데이터와 평가체계를 강화할 때
- `05_STAGE3_OPTIMIZER.md`: 환헤지 비율 제안 모듈을 강화할 때
- `06_STAGE4_OFFICIAL_RAG.md`: 공식 자료만 사용하는 금융상품 검색을 구축할 때
- `07_STAGE5_REPORT_AGENT.md`: 설명 가능한 최종 보고서 에이전트를 구축할 때
- `08_FULL_QA_SECURITY_RELEASE.md`: 전체 검수·보안·릴리스
- `09_DEMO_PITCH_PACKAGE.md`: 3분 데모와 발표자료용 산출물
- `10_MAINTENANCE_AUTOPILOT.md`: 이후 유지보수와 치명적 오류 탐지
- `AGENTS.md`: 저장소 루트에 둘 Codex 상시 규칙
- `.env.example`: 최종 애플리케이션 환경변수 예시
