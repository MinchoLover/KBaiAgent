# 공모전 데모·발표 패키지 프롬프트

현재 작동하는 앱을 기반으로 심사위원이 3분 안에 가치를 이해할 수 있는 데모 패키지를 만들어라. 기능을 새로 과도하게 추가하지 말고 데모 안정성과 이야기 흐름을 우선한다.

대표 데모:

- 한국 수입 중소기업
- USD 100,000 지급 예정
- 보유 USD 20,000
- 현재 현금, 매출 입금, 비용 지급
- 환율 +5%에서 추가 비용과 안전잔고 부족 발생

3분 이야기:

```text
0:00 문제 — 기업은 환율 전망보다 자기 현금이 버티는지 모른다
0:25 문서 업로드 — AI가 금액·통화·결제일과 근거 추출
0:55 사용자 확인 — AI 오독을 그대로 계산하지 않음
1:10 Stage 1 시나리오 연결
1:25 Stage 2 — 추가 비용·잔고·부족 시점 계산
1:55 Stage 3 — 제약을 충족하는 전략 후보 비교
2:20 Stage 4 — 공식 상품·제도 근거
2:40 Stage 5 — KB 상담 준비 보고서
2:55 한계와 인간 검토
```

생성할 파일:

- `docs/DEMO_SCRIPT_KO.md`
- `docs/PITCH_3MIN_KO.md`
- `docs/JUDGE_QA_KO.md`
- `docs/FAILSAFE_DEMO.md`
- `samples/demo_import.json`
- `samples/demo_stage1.json`
- `outputs/demo_expected.json`
- screenshot checklist
- 1페이지 architecture Mermaid
- 팀원별 발표 역할

Failsafe:

- API 장애 → sample extraction
- Stage 1 endpoint 장애 → bundled Stage 1 fixture
- web search 장애 → offline KB
- LLM report 장애 → deterministic report

데모 전용 버튼 하나로 대표 사례를 불러오고, reset 버튼을 제공하라. 발표 숫자는 테스트 expected output과 자동 비교해 틀리지 않게 하라.
