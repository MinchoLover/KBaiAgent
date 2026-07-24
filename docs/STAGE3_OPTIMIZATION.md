# Stage 3 Strategy Candidate Search

이 단계는 최종 자문이 아니라 입력 가정 아래 비교 가능한 후보를 생성합니다.

## 탐색 공간

- forward ratio
- staged conversion ratio
- unhedged ratio
- 세 비율 합계 정확히 1
- 5% 또는 10% grid

## 목적 함수

환율 손실, 최소 운영자금 부족, 데모 hedge 비용, 손실한도 위반 penalty, 안정성 선호를
합칩니다. 확률이 유효하면 probability-weighted mode, 아니면 worst-case robust
mode입니다.

데모 비용 가정은 open exposure의 BASE 원화가치에 대해 forward 0.15%, staged
conversion 0.05%이며 실제 견적이 아닙니다. 이미 자연상계·기존 hedge·다른 현금흐름은
신규 hedge 비용 기준에 다시 포함하지 않습니다. staged conversion의 잔여 위험을
미헤지의 50%로 근사합니다.

## 출력

점수가 낮은 상위 3개 후보에 비율, 최악 손실, 가능한 경우 예상 손실, 비용 가정,
보유외화 반영 비율, 추정 buffer 부족과 liquidity impact, 손실한도 초과 여부,
제약 충족 여부, 선택 이유, 한계, 필요한 상품 유형을 기록합니다. 후보 비율과 점수는
`optimizer.py`, 자연어 선택 이유는 `explanations.py`가 담당합니다.
실제 은행 quote, 신용한도, 회계·세무·중도해지 조건은 별도 상담이 필요합니다.
