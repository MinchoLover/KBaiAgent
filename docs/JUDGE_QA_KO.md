# 심사위원 예상 Q&A

## 왜 바로 파인튜닝하지 않았나요?

현재 오류가 OCR, prompt, schema, validation 중 어디서 나는지 baseline 없이 알 수
없기 때문입니다. 16개 adversarial 포함 정답 문서와 자동 지표·회귀 gate를 먼저
만들었습니다.

## AI 금액이 틀리면 회사 현금 계산도 틀리지 않나요?

통화·금액·결제일은 사용자 개별 확인과 CRITICAL/HIGH validator PASS 전에는 Stage 2로
전달되지 않습니다. 원본값·수정값·확인시각·파일 hash도 기록합니다.

## 모델 confidence는 쓰나요?

쓰지 않습니다. evidence 존재, explicit 여부, 통화·날짜·금액 충돌, 필수값 누락을
일반 코드가 검사해 review 상태를 다시 계산합니다.

## 팀원의 환율 예측과 어떻게 연결하나요?

`docs/STAGE1_CONTRACT.md` JSON을 파일 또는 REST로 받습니다. currency, target date,
base, quote unit, probability를 검증하고 오류 시 수동 스트레스로 fallback합니다.

## 환율 리스크와 현금부족은 어떻게 구분하나요?

환율 손실은 BASE 시나리오 대비 불리한 원화 차이입니다. liquidity는 날짜별 ledger의
minimum buffer shortfall, negative cash deficit, credit 반영 후 shortfall을 별도
필드로 냅니다.

## 추천 상품이 광고나 환각이면요?

offline KB와 web 모두 공식 도메인 allowlist를 사용하고 URL·확인일 없는 후보를
배제합니다. 자격·승인·금리·한도는 `unknown`, `상담 필요`로 남깁니다.

## 보고서가 숫자를 바꾸면요?

explainer 뒤 critic이 source JSON에 없는 숫자와 무근거 확률을 검사합니다. 한 번
수정 후에도 실패하면 LLM을 버리고 source JSON을 직접 넣는 template 보고서를 냅니다.

## 현재 정확도 100%인가요?

아닙니다. offline 100% 필드 점수는 label과 동일한 fixture로 evaluator를 검증한
수치입니다. 실제 모델 정확도는 live mode baseline으로 별도 측정해야 합니다.
