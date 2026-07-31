# Spot Rate Provider Setup

Stage 1의 return 분위수를 절대환율로 바꾸려면 별도 `SpotQuote`가 필요합니다.

## 우선순위

1. 한국수출입은행 공식 reference provider
2. 사용자가 확인한 수동 입력
3. demo fixture
4. 모두 없으면 분석 차단

`SPOT_RATE_PROVIDER=auto`가 위 순서를 사용합니다. `manual`, `koreaexim`,
`fixture`를 명시하면 선택한 provider 정책을 따릅니다.

## 한국수출입은행

```dotenv
SPOT_RATE_PROVIDER=koreaexim
KOREAEXIM_KEY=
```

코드는 한국수출입은행 공개 환율 API의 `deal_bas_r`를 읽고 최근 영업일을
탐색합니다. 키·원문 응답을 로그에 남기지 않습니다. `JPY(100)` 같은 고시단위는
내부 `KRW_PER_1_JPY`로 나눠 정규화합니다.

## 수동 확인

```dotenv
SPOT_RATE_PROVIDER=manual
MANUAL_USDKRW_RATE=1400
```

UI의 “사용자 확인” 체크가 없으면 `ManualSpotRateProvider`가 계산을 차단합니다.
입력 시각과 `USER_CONFIRMED_MANUAL` provenance가 결과에 남습니다.

## Fixture

`DEMO_MODE=true`, `SPOT_RATE_PROVIDER=fixture`에서 USD/KRW 1400 공개 fixture를
사용합니다. 이 값은 실시간 환율이 아니며 운영 분석에 사용할 수 없습니다.

## 지원 통화

Spot provider와 Stage 2는 다른 통화를 받을 수 있지만 Stage 1 모델은 현재
USD/KRW만 지원합니다. 다른 통화는 사용자 확인 spot과 고정 스트레스만 허용합니다.
