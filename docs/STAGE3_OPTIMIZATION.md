# Stage 3 Strategy Candidate Search

현재 사양은 [`STAGE3_OPTIMIZER_SPEC.md`](STAGE3_OPTIMIZER_SPEC.md)를 기준으로
합니다.

기존 `forward/staged/unhedged` grid 구조를 유지하면서 기본 간격을 5%p로 하고,
q90·고정 ±10%·최소 운영자금·신용 후 실제 부족·최대 forward 비율을 제약으로
검사합니다. 결과는 안정성·균형·비용 우선의 `SIMULATED_CANDIDATE`이며 실제
금융상품 가격이나 확정 자문이 아닙니다. 해가 없으면
`NO_FEASIBLE_CANDIDATE`를 반환합니다.
