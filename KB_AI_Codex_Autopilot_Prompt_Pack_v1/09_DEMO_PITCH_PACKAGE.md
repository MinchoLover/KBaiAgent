# 공모전 데모·발표 패키지 프롬프트

현재 작동하는 앱을 기반으로 심사위원이 3분 안에 가치를 이해할 수 있는 데모 패키지를 만들어라. 기능을 새로 과도하게 추가하지 말고 데모 안정성과 이야기 흐름을 우선한다.

대표 데모:

- 한국 판매자·브라질 구매자의 합성 수출계약
- USD 100,000 예정 수취 노출
- USD 20,000 선지급 예정의 실제 입금 여부 `UNKNOWN`
- USD 80,000 Open Account/T/T 잔금
- 환율 -5%에서 수취 감소 7,000,000원
- 목표 buffer 부족 2,000,000원, cash/payment deficit 0원
- 상담 Top 3: 회수 보호 → 환율 관리 → 운영자금 버퍼

3분 이야기:

```text
0:00 문제 — 기업은 환율 전망보다 자기 현금이 버티는지 모른다
0:25 문서 업로드 — AI가 금액·통화·결제일과 근거 추출
0:55 사용자 확인 — AI 오독을 그대로 계산하지 않음
1:10 Stage 1 시나리오 연결
1:25 Stage 2 — 수취 감소·잔고·buffer/deficit 분리
1:50 상담 Top 3 — 숫자·부족정보·기대 결정·다음 행동
2:25 공식 후보 — 출처·검증일·eligibility UNKNOWN
2:40 one-page handoff — 같은 JSON의 Markdown
2:55 실제 예약·RM 연동 없음과 인간 검토
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
