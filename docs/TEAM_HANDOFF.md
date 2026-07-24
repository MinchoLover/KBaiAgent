# Team Handoff

## Stage 1 담당자

`docs/STAGE1_CONTRACT.md` schema를 그대로 제공하세요. 핵심은
`KRW_PER_1_FC`, rate unit, timezone 포함 as_of, target_date, 정확히 한 base입니다.
확률은 모두 제공하고 합이 1이거나 전부 생략하세요.

샘플: `samples/stage1_scenarios.json`

운영 REST 연동에는 `STAGE1_ALLOWED_HOSTS` exact hostname을 설정하세요. 기본값은
HTTPS/public IP만 허용합니다. 로컬 개발에서만
`STAGE1_ALLOW_PRIVATE_ENDPOINTS=true`를 사용합니다.

## 문서 AI 담당자

prompt는 `prompts/`에서만 수정하고 `prompt_version.json`을 올립니다. 수정 후:

```bash
python scripts/evaluate_extraction.py --mode live --max-cases 2
python scripts/run_regression.py
```

baseline 갱신은 회귀가 아니라 정답/평가 기준의 승인된 변경일 때만 합니다.

## 금융 엔진 담당자

`src/domain/stage2_models.py` 입력/출력을 먼저 변경하고 Decimal을 유지하세요.
비율·현금흐름 공식 변경 시 `docs/STAGE2_CALCULATION_SPEC.md`와 방향성 테스트를 함께
수정합니다. LLM report에 계산을 추가하지 않습니다.

## UI 담당자

`src/ui/`와 `app.py`는 domain model 조립과 표시만 담당합니다. 업로드/역할이 바뀔 때
state invalidation, 확인 gate, 상태 badge를 유지하세요.

## 릴리스 담당자

```bash
python scripts/generate_demo_outputs.py
python scripts/evaluate_extraction.py --mode offline
python scripts/run_regression.py
python scripts/verify.py
```

API 키가 있으면 `python scripts/live_smoke_test.py samples/sample_invoice.png` 한 건만
호출하고 비용·모델·날짜를 validation report에 기록합니다.
