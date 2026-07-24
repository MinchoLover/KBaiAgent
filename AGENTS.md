# Repository Working Agreement

- Python 3.9 호환을 유지하고 타입은 `Optional`, `List`, `Dict`를 사용한다.
- 금융 계산은 `Decimal`, 날짜는 `date`/`datetime`을 사용한다.
- LLM 출력은 사용자 확인과 결정론 검증 전 계산에 전달하지 않는다.
- 문서 원문, 비밀값, 실제 업로드를 로그·dataset에 자동 저장하지 않는다.
- Stage 1 팀 모델을 재구현하지 않고 JSON/REST adapter 계약을 유지한다.
- 테스트셋은 파인튜닝 후보에서 항상 제외한다.
- 변경 후 `python scripts/verify.py`를 실행한다.
