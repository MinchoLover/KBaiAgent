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
수치입니다. fixture는 JSON 로딩·정규화·지표·보고서 회귀를 확인하지만 OpenAI가
이미지에서 값을 찾는 능력을 측정하지 않습니다. 실제 모델 결과는 별도 Live run
ID와 합성 사례 수를 함께 공개해야 합니다.

## Live 검증을 몇 건 수행했나요?

합성문서 2건을 `gpt-4o-mini`로 실행했고 API/구조화 응답은 2건 성공, 실패·timeout은
0건이었습니다. 통화·금액·분할 금액·날짜는 2건에서 맞았지만 국가 canonicalization과
거래방향은 실패했고, 독립 OCR evidence가 없어 둘 다 사용자 확인 전 계산을
차단했습니다. 전체 8건은 아직 실행하지 않았으며 별도 승인이 필요합니다. 정확한
필드·latency·token과 한계는 `docs/LIVE_BENCHMARK_RESULTS.md`에 있습니다.

## 왜 실제 고객문서를 사용하지 않았나요?

동의, 목적 제한, 보존·삭제, 접근권한과 비밀관리 통제가 없는 대회 개발 환경에서
실제 거래문서를 외부 API나 저장소에 보내는 것은 부적절하기 때문입니다. 회사명·
계좌·주소·식별번호·서명·도장을 쓰지 않은 명시적 합성 문서만 사용했습니다.

## 합성 문서 8건으로 무엇까지 말할 수 있나요?

미국·브라질, 수입·수출, PDF·JPG, 명시·사건 기준 날짜, 통화 누락과 차단 사례를
같은 evaluator에서 재현했다고 말할 수 있습니다. 표본이 8건뿐이고 실제 언어·
레이아웃·촬영 품질 분포를 대표하지 않으므로 전체 무역문서 정확도나 운영 성능으로
일반화할 수 없습니다.

## 스캔 PDF의 OCR evidence는 독립 검증됐나요?

아닙니다. 현재 별도 OCR 엔진이나 독립 OCR ground truth verifier가 없습니다.
이미지형 PDF와 사진에서 vision 모델이 반환한 `source_text`는 스스로를 증명하지
못하므로 `OCR_REQUIRED`·`EVIDENCE_UNVERIFIABLE` 상태와 field별 사용자 확인을
요구합니다. 합성 label의 source text는 평가 정답이지 production OCR 인증이
아닙니다.

## 왜 UNKNOWN이나 null을 유지하나요?

통화, 사건 기준일, 가려진 결제일을 임의 보정하면 뒤의 원화 금액과 현금계획이
그럴듯하지만 잘못된 숫자가 됩니다. 정보가 없다는 사실을 별도 위험으로 표시하고
사용자에게 보완을 요청하는 것이 자동 추측보다 안전합니다.

## 모델이 잘못 추출하면 계산으로 전달되나요?

바로 전달되지 않습니다. 통화·금액·결제일·거래방향·회사역할은 evidence,
Pydantic, 결정론 규칙과 사용자 개별 확인을 통과해야 합니다. 이미지 문서는
독립 원문 검증이 없으므로 field-level 확인 전 Stage 2가 차단됩니다. 사용자가 값을
수정하면 기존 evidence와 확인 fingerprint를 폐기하고 다시 검증합니다.

## 왜 국가 위험을 하나의 점수로 합치지 않았나요?

OECD 지급·이전 분류, World Bank 거시 관측치, WTO 회원·시장접근 정보는 의미와
기준시점이 다릅니다. 임의 가중합은 공식기관이 제공하지 않은 자체 신용점수처럼
보일 수 있어 세 축과 원값·기간·한계를 분리합니다. 미국 OECD 미분류를 `LOW`로
바꾸지 않고 브라질 raw class `4`도 자체 등급명으로 바꾸지 않습니다.

## 금융기관 공식 심사등급과 무엇이 다른가요?

현재 결과는 공개 snapshot과 거래조건을 이용한 상담 검토 우선도입니다. 거래처
재무, 담보, 내부 신용정책, 발행은행, 보험 약관과 심사 데이터를 사용하지 않으므로
국가·기업 신용등급, 부도확률, 대출 승인 또는 보험 인수판정이 아닙니다.

## 실제 배포 전에 어떤 보안이 더 필요한가요?

사용자 인증과 tenant별 권한·데이터 분리, TLS와 secret manager, 악성파일 검사와
sandboxed PDF rendering, 저장·삭제 정책과 고객 동의, 중앙 감사로그, rate limit,
의존성·CI scan, production egress allowlist와 모니터링이 필요합니다. 현재 로컬
Streamlit MVP가 이를 구현했다고 주장하지 않습니다.
