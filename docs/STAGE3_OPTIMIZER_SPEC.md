# Stage 3 Optimizer Specification

Stage 3은 주문·자문 엔진이 아니라 명시된 가정 아래 검토 후보를 탐색하는
결정론 모듈입니다.

## 변수

```text
forward_ratio + staged_conversion_ratio + unhedged_ratio = 1
```

기본 5%p grid이며 10%p도 선택할 수 있습니다. 기존 헤지는 Stage 2에서 이미
open exposure에서 제외됩니다.

## 가정 계약

`Stage3Assumptions`는 forward effective rate, forward/staged fee bps,
staged residual-risk factor, staged dates, risk·liquidity·concentration weight,
최대 forward 비율과 최소 거래 비율을 결과 JSON에 그대로 공개합니다. 실제 견적이
없으면 `SIMULATED_CANDIDATE`입니다.

## 제약

- 비율 합 100%
- 신규 forward 최대 비율
- 기존+신규 hedge 총액 100% 이하
- q90 불리 시나리오 손실한도
- 고정 ±10% 불리 시나리오 존재와 지급 가능성
- 최소 운영자금
- 대출한도 반영 후 실제 부족 0
- 선택적 최소 거래 비율

결제일이 21거래일 밖이면 q90 결과는 `null`이며 고정 ±10% 제약으로만
결제기간을 검증합니다.

## 목적과 출력

헤지 비용 + 잔여 불리 손실 + 유동성 부족 penalty + 집중도 penalty를
프로필별로 평가해 `STABILITY_FIRST`, `BALANCED`, `COST_FIRST`를 최대 3개
반환합니다. 각 후보에는 q90 손실, 고정 ±10% 손실, 최저 현금잔고, 신용 후
부족, 비용 가정과 제약 결과가 포함됩니다.

제약을 만족하는 해가 없으면 후보를 강제로 만들지 않고
`NO_FEASIBLE_CANDIDATE`와 실패 코드를 반환합니다.
