# Stage 5 Report Policy

## Pipeline

```text
confirmed Stage 0 + Stage 1 + Stage 2 + Stage 3 + Stage 4
→ explainer LLM
→ deterministic critic
→ PASS
→ 실패 시 1회 수정
→ 재실패 또는 API 실패 시 deterministic fallback
```

API 키가 없으면 처음부터 fallback 보고서를 생성합니다.
Stage 4 공식 근거 후보가 비어 있어도 LLM을 호출하지 않고 fallback합니다. 이 정책은
상품명·기관명을 자연어로 임의 생성할 가능성을 호출 경계에서 차단합니다.

## 허용

- 계산 JSON의 값을 이해하기 쉬운 한국어로 설명
- 위험 원인과 다음 행동 정리
- 공식 후보를 URL과 함께 정리
- 핵심 숫자에 `[source: JSON.path]` 표시

## 금지

- 숫자 재계산·수정·새 숫자 생성
- 확률이 없는데 확률 표현
- STRESS를 예측이라고 표현
- 승인·수익·손실회피 보장

critic은 각 숫자가 같은 줄에 표시된 유효한 JSON path의 실제 값과 연결되는지,
시나리오 표현, 무근거 확률, 보장 문구, 필수 섹션, Stage 4 상품 근거를 검사합니다.
결과는 score, numeric consistency, evidence quality, recommendation consistency,
prohibited claims, missing sections, revision instructions로 구조화됩니다. 수정 지시는
실제 재작성 prompt에 전달되며 `revision_count`는 최대 1입니다.

fallback은 같은 source bundle을
template에 직접 넣고 Stage 3 후보 세 건과 Stage 4 출처를 모두 추적하므로 LLM이 계산
결과를 바꿀 수 없습니다.
