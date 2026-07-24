# Stage 2 Calculation Specification

모든 금융 숫자는 `Decimal`이며 결과 JSON은 decimal 문자열입니다.

## Exposure

```text
held_fx_used = min(trade_amount, eligible usable balance)
same_currency_offset = min(trade_amount - held_fx_used,
                           eligible same-currency flows)
natural_offset = held_fx_used + same_currency_offset
open_exposure = max(trade_amount - natural_offset - hedged_amount, 0)
```

수입은 결제일까지 들어오는 동일 통화 유입과 보유외화를 자연상계합니다. 수출
receivable은 보유외화를 자동 상계하지 않고 결제일까지 예정된 동일 통화 지출만
상계 후보로 봅니다. 결제일 뒤의 흐름과 다른 통화는 제외합니다. 보유외화 사용량은
실제 거래금액을 넘지 않으며, 보유외화와 기타 동일통화 상계를 결과에서 분리해
Stage 3의 보유외화 비율이 다른 자연상계 흐름을 포함하지 않게 합니다.

기존 헤지는 open exposure에서 제외하지만 계약된 외화금액·약정환율·수수료를 실제
KRW cashflow에 유지합니다. 자연상계 후 노출보다 큰 헤지는 삭제하지 않고 over-hedge
warning을 냅니다.

분할결제는 전체 거래에 사용할 수 있는 자연상계·기존 hedge를 회차 순서대로 capped
allocation합니다. 한 회차에서 쓰고 남은 양만 다음 회차로 전달하며, aggregate hedge
fee는 회차별 hedge 배분 비율로 나눠 총 한 번만 반영합니다.

## 환율과 거래 현금

```text
import customer rate = reference rate × (1 + spread_bps / 10000)
export customer rate = reference rate × (1 - spread_bps / 10000)

import outflow = open exposure × buy rate
               + hedge amount × locked rate + hedge fee + bank fee
export inflow  = open exposure × sell rate + hedge amount × locked rate
export outflow = hedge fee + bank fee
```

기준 손실은 수입이면 `scenario total outflow - BASE outflow`, 수출이면
`BASE inflow - scenario total inflow`입니다. 따라서 수입은 환율 상승, 수출은 환율
하락이 불리합니다. 비교 기준 이름을 결과에 저장합니다.

## 날짜별 ledger

```text
balance = previous balance + KRW inflow - KRW outflow + FX KRW flow
buffer_shortfall = max(minimum_buffer - balance, 0)
cash_deficit = max(-balance, 0)
post_credit_shortfall = max(-(balance + credit_limit), 0)
```

세 부족 개념을 혼용하지 않습니다. 각 scenario에 전체 날짜 ledger, 종료·최저 잔고,
최초 buffer 부족일, 최대 buffer 부족, 현금 적자, 신용 후 부족을 저장합니다.
시작 시점에 이미 최소 운영자금보다 낮으면 최초 buffer 부족일은 `as_of`입니다.
모든 ledger entry와 Stage 2 결과는 `CALCULATION` 상태로 표시하고, 적용 환율의 성격은
별도 `scenario_kind`의 `STRESS` 또는 `FORECAST`로 보존합니다.

## 복합 스트레스

- REVENUE inflow: 금액 감소와 날짜 지연
- COST outflow: 금액 증가
- 위 회사 스트레스와 Stage 1 환율 scenario 조합

확률이 완전하고 합이 유효할 때만 expected adverse loss와 shortage probability를
계산합니다. 그렇지 않으면 해당 필드는 `null`입니다.
