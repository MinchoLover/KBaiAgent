# Stage 2 Calculation Specification

모든 금융 숫자는 `Decimal`이며 결과 JSON은 decimal 문자열입니다.

## 확정 거래 바인딩과 입력 계약

오케스트레이션 경로의 Stage 2는 단순히 `user_confirmed=true`를 신뢰하지 않습니다.
`ConfirmationRecord`의 회사 국가와 확인값으로 Stage 0 검증을 다시 실행하고, 다음
필드를 canonical JSON으로 만든 뒤 SHA-256 fingerprint를 계산합니다.

- 문서 원본 SHA-256
- 거래 방향과 통화
- 각 결제 이벤트의 연속 sequence, 외화금액, 결제일

`Stage2Input.confirmed_trade_sha256`와 위 fingerprint가 같아야 하며, fingerprint가
같더라도 모든 결제 이벤트를 확인 기록과 다시 대조합니다. 금액·통화·결제일·회차 중
하나라도 다르면 `confirmed_trade_binding` 단계에서 `FAILED`가 되고 계산 runner를
호출하지 않습니다. 성공 결과에도 같은 fingerprint를 복사해 Stage 0 확인 거래부터
Stage 2 결과까지 추적할 수 있게 합니다. 직접 `run_stage2`를 호출하는 독립 계산
테스트에서는 fingerprint를 생략할 수 있지만 사용자 워크플로에서는 필수입니다.

엔진에 들어가는 숫자는 기호·쉼표·공백·지수 표기 없는 decimal 문자열이어야 합니다.
UI의 천 단위 쉼표는 application service에서 먼저 제거합니다. 날짜는 정확한
`YYYY-MM-DD`, 거래 회차는 1부터 연속, 한 실행의 거래 방향과 통화는 각각 하나여야
합니다. 결제일·원화 현금흐름·동일통화 흐름은 `as_of_date`보다 빠를 수 없고 은행
spread는 `10000` bps 미만이어야 합니다.

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

분할결제 수입은 보유외화를 먼저 회차 순서대로 capped allocation한 뒤 각 회차의 남은
금액만 동일통화 유입의 cap으로 사용합니다. 한 회차에서 쓰고 남은 양만 다음 회차로
전달합니다. 기존 hedge는 서명된 별도 계약으로 보고 전체 거래금액 안에서 독립
allocation하며, aggregate hedge fee는 회차별 hedge 배분 비율로 나눠 총 한 번만
반영합니다. 아주 작은 수수료도 반올림 잔여가 음수가 되지 않으며 배분 합계는 입력
수수료와 같습니다.

거래금액을 초과한 보유외화나 결제일·잔여노출 조건에 맞지 않아 배분하지 못한
동일통화 흐름은 조용히 버리지 않고 고정 warning code로 입력에 보존한 뒤 사용자용
경고 문구로 변환합니다.

## 환율과 거래 현금

```text
import customer rate = reference rate × (1 + spread_bps / 10000)
export customer rate = reference rate × (1 - spread_bps / 10000)

import outflow = open exposure × buy rate
               + hedge amount × locked rate + hedge fee + bank fee
export inflow  = open exposure × sell rate + hedge amount × locked rate
export outflow = hedge fee + bank fee
```

`bank_fee`는 UI 표기와 같이 결제 이벤트별 고정 수수료입니다.

방향을 보존하는 값은 수입이면 `scenario total outflow - BASE outflow`, 수출이면
`BASE inflow - scenario total inflow`이며 `signed_impact_vs_base`에 저장합니다.
금융 위험 지표 `loss_vs_base`는 `max(0, signed impact)`입니다. 따라서 유리한
시나리오를 음수 손실로 표시하지 않습니다. 수입은 환율 상승, 수출은 환율 하락이
불리합니다.

## 날짜별 ledger

```text
balance = previous balance + KRW inflow - KRW outflow + FX KRW flow
buffer_shortfall = max(minimum_buffer - balance, 0)
cash_deficit = max(-balance, 0)
post_credit_shortfall = max(-(balance + credit_limit), 0)
```

세 부족 개념을 혼용하지 않습니다. 각 scenario에 전체 날짜 ledger, 종료·최저 잔고,
최초 buffer 부족일, 최초 실제 현금 적자일, 최대 buffer 부족, 현금 적자, 신용 후
부족을 저장합니다.
시작 시점에 이미 최소 운영자금보다 낮으면 최초 buffer 부족일은 `as_of`입니다.
모든 ledger entry와 Stage 2 결과는 `CALCULATION` 상태로 표시하고, 적용 환율의 성격은
별도 `scenario_kind`의 `STRESS` 또는 `FORECAST`로 보존합니다.

## 복합 스트레스

- REVENUE inflow: 금액 감소와 날짜 지연
- COST outflow: 금액 증가
- 위 회사 스트레스와 Stage 1 환율 scenario 조합

확률이 완전하고 합이 유효할 때만 expected adverse loss와 shortage probability를
계산합니다. 그렇지 않으면 해당 필드는 `null`입니다.

Stage 1 계약은 target date 하나를 제공하므로 분할결제일이 여러 개면 같은 scenario
set을 각 결제일에 대체 적용하고 결제일별 warning을 남깁니다.

새 Stage 1 web forecast는 21거래일 안의 결제에만 모델 분위수 시나리오를 Stage 2에
전달합니다. 결제일이 범위 밖이면 `HORIZON_MISMATCH`를 남기고 ±3/5/10% 고정
스트레스만 계산합니다. 각 `ScenarioResult`에는 source kind, horizon, warning과
숫자 source path가 포함됩니다.
