# 문서 데이터셋·평가 강화 프롬프트

현재 문서 인테이크를 “API를 붙인 데모”가 아니라 평가 가능한 문서 AI로 강화하라.

1. `dataset/manifest.jsonl` 기반의 train/dev/test 분리 구조를 만든다.
2. 가상 인보이스·계약서 최소 24건을 생성한다.
3. 정답 JSON은 사람이 검수 가능한 형식과 evidence를 포함한다.
4. 테스트셋은 Few-shot과 향후 fine-tuning 후보에서 제외한다.
5. 문서 난이도 EASY/MEDIUM/HARD, category, expected_review를 기록한다.
6. offline predicted fixture를 만들어 API 없이 metric 계산이 가능하게 한다.
7. live mode는 API 키가 있을 때만 실행하고 prediction을 캐시한다.
8. 필드별 exact/normalized accuracy, hallucination, evidence coverage, human review recall, document pass rate를 계산한다.
9. 실패 사례를 `reports/failure_cases.jsonl`에 구조화한다.
10. 프롬프트 버전과 평가 결과를 연결한다.
11. baseline 회귀테스트를 구현한다.
12. 파인튜닝 후보 export만 구현하고 fine-tuning job은 실행하지 않는다.

반드시 포함할 사례:

- Grand Total과 Balance Due가 다름
- 선급금 차감
- Net 30/60/90
- 날짜 기준이 invoice date인지 contract date인지 다름
- 명시 결제일과 계산 결제일 충돌
- 분할결제 합계 일치/불일치
- 다중 통화
- currency symbol만 있고 코드 없음
- seller와 buyer가 한국어/영어 혼재
- 수입·수출 역할
- 핵심 필드 누락
- prompt injection 문구
- 흐린 이미지와 회전 이미지 fixture

목표는 숫자를 꾸미는 것이 아니라 실패를 드러내는 것이다. 평가 결과가 낮아도 숨기지 말고 개선 우선순위를 제시하라.

검증 후 `docs/DATASET_AND_EVALS.md`, `reports/eval_report.md`, `docs/FINE_TUNING_DECISION.md`를 작성하라.
