# Stage 3 환헤지 전략 후보 엔진 프롬프트

현재 Stage 2 결과를 입력으로 받아 검토 가능한 헤지 전략 후보를 생성하는 Stage 3를 구현하라.

중요:

- 금융 자문이나 최종 상품 추천으로 단정하지 않는다.
- 상품의 실제 견적이 없으면 비용을 가정값으로 명확히 표시한다.
- “최적”이라는 표현은 주어진 목적함수와 가정 안에서만 사용한다.

전략 변수:

- forward ratio
- staged conversion ratio
- unhedged ratio
- 합계 1.0
- grid step 기본 0.05

입력:

- Stage 2 scenario results
- valid scenario probabilities 여부
- acceptable loss
- minimum cash buffer
- risk aversion
- forward estimated spread/cost
- staged conversion transaction cost
- minimum/maximum hedge policy

목적함수:

- expected adverse loss 또는 worst-case adverse loss
- tail/cash shortfall penalty
- hedge cost
- constraint violation penalty
- excessive hedge penalty

후보별 계산을 결정론적으로 수행하고 상위 3개를 반환한다.

출력:

- candidate id
- ratios
- objective score and components
- expected/worst loss
- maximum buffer shortfall
- cost assumption
- constraints satisfied
- required product types
- explanation facts
- warnings

테스트:

- ratios sum 1
- 0~1 범위
- 동일 입력 재현성
- probability 없는 robust mode
- impossible constraints
- zero exposure
- fully naturally hedged
- import/export 방향

UI에서 상위 후보를 비교 카드와 표로 보여주고, Stage 4 query intent를 생성하라. 전체 테스트와 verify를 통과시켜라.
