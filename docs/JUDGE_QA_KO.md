# 심사위원 예상 Q&A

## 1. 왜 Live 평가의 validation pass가 0/8인가요?

8건 모두 API 구조화 응답 자체는 성공했습니다. 그러나 입력이 텍스트 레이어 없는
이미지형 PDF 또는 JPG라 모델 인용을 독립 원문으로 자동 검증할 수 없었습니다.
`OCR_REQUIRED`, `EVIDENCE_UNVERIFIABLE`, `MISSING_CORE_EVIDENCE` 정책으로 사람이
확인하기 전 전부 fail closed한 결과입니다.

## 2. Evidence coverage 0%는 OCR 정확도 0%라는 뜻인가요?

아닙니다. “자동 수용할 수 있는 독립 검증 evidence가 0%”라는 뜻입니다. Vision
모델의 인용이 맞을 수 있어도 같은 모델 출력만으로 진위를 증명하지 않습니다.
OCR 문자 정확도는 별도 ground truth OCR 평가가 있어야 말할 수 있습니다.

## 3. 왜 Stage 2도 0/8인가요?

Stage 2는 API 성공 여부가 아니라 evidence 검증과 통화·금액·결제일·거래방향의
사용자 확인을 요구합니다. 그 gate를 통과하지 못한 스캔형 8건을 금융 계산으로
전달하지 않은 것이 의도된 안전 동작입니다.

## 4. GPT-4o mini 추출 정확도가 100%라고 주장할 수 있나요?

없습니다. 제한된 합성 8건에서 V2의 benchmark 필드가 모두 맞은 항목이 있지만,
contract date 하루 오류가 있고 evidence gate는 통과하지 못했습니다. Fixture
100%는 label과 동일한 prediction으로 evaluator를 검증한 수치일 뿐 모델 정확도가
아닙니다.

## 5. V1/V2 개선이 모델 변경 때문이 아닌지 어떻게 확인했나요?

두 run은 모두 `gpt-4o-mini`, 같은 합성 8건, evaluator
`ac0aa62a...8542e89`, prompt `39693763...403eef5`, manifest
`be472519...ce0792`, 같은 schema와 안전 정책을 사용했습니다. 의도된 코드 차이는
commit `9bdffd9`의 국가 canonicalization입니다.

## 6. 어떤 V1/V2 개선만 canonicalization 효과로 보나요?

`seller_country` 4/8→8/8, `buyer_country` 3/8→8/8과 정규화 국가에서
결정론적으로 파생한 `trade_type` 2/8→8/8만 직접 효과로 봅니다. 금액·통화·날짜와
분할결제는 사례별로 불변이었습니다.

## 7. 왜 document_type 7/8→8/8은 효과라고 하지 않나요?

국가 정규화 코드는 document type을 바꾸지 않습니다. 두 baseline은 별도 LLM
호출이므로 이 차이와 전체 document match, token, latency, 법인명 표현은 재호출
변동일 수 있습니다. 인과관계를 과장하지 않습니다.

## 8. 국가위험 결과는 공식 국가신용등급인가요?

아닙니다. OECD 지급·이전 원자료, World Bank 거시 관측, WTO 무역·시장접근 정보를
축별로 보존하고 거래조건과 함께 상담 검토 우선도를 냅니다. 국가·기업 신용등급,
부도확률이나 은행 내부 심사등급이 아닙니다.

## 9. 왜 국가위험이 환헤지 비율을 바꾸지 않나요?

공개 국가 원자료를 자체 가중치로 환헤지 계산에 넣으면 검증되지 않은 금융 판단이
됩니다. T4는 보험·보증·신용장·결제조건 상담 순서에만 반영하며 Stage 1 환율,
Stage 2 현금흐름, Stage 3 헤지 후보는 같은 입력에서 동일합니다.

## 10. Fixture와 Live 평가는 무엇이 다른가요?

Fixture는 저장된 label/prediction으로 JSON 로딩, 정규화, 지표와 보고서 회귀를
검증합니다. Live는 실제 모델 호출의 구조화 출력, latency와 token을 측정합니다.
Metadata·디렉터리·주장 범위를 분리하고 fixture 수치를 모델 성능으로 쓰지 않습니다.

## 11. 합성 8건을 실제 고객문서에 일반화할 수 있나요?

없습니다. 미국·브라질, 수입·수출, PDF·JPG, 통화 누락과 사건 기준 조건을 재현한
제한된 QA 세트입니다. 실제 언어·레이아웃·촬영 품질·기업 분포를 대표하지 않습니다.

## 12. 실제 API 비용은 얼마인가요?

Cached input token 수를 수집하지 않아 실제 청구 비용은 `UNKNOWN`입니다. V2의
310,495 input·4,660 output token에 캐시 미적용 단가를 적용한 USD 0.04937025는
사후 상한 추정일 뿐 실제 비용이 아닙니다.

## 13. 왜 cached token이 UNKNOWN인가요?

현재 baseline adapter metadata가 input/output 총량은 보존하지만 cached input
세부량은 보존하지 않습니다. Baseline hash를 바꾸지 않기 위해 실행 뒤 evaluator를
수정하지 않았고 비용을 억지로 확정하지 않았습니다.

## 14. 남은 contract date 하루 오류는 어떻게 처리하나요?

`us_import_split_scan_001`에서 정답 2026-08-05를 2026-08-06으로 추출했습니다.
Baseline을 지우거나 label을 낮추지 않았습니다. 운영 흐름에서는 날짜 evidence와
사용자 확인 전 계산을 차단하며 prompt·추출 개선은 별도 비교 실험으로 다룹니다.

## 15. 모델이 금액이나 날짜를 잘못 읽으면 계산까지 전달되나요?

바로 전달되지 않습니다. Pydantic schema, 금액·날짜·분할합계 규칙, source quote와
페이지 원문 대조, 회사역할·거래방향 판정, 사용자 개별 확인을 모두 거쳐야 합니다.
사용자가 값을 바꾸면 이전 evidence와 확인 fingerprint를 폐기하고 다시 검증합니다.

## 16. Golden 계약서는 Live 정확도 증거인가요?

단일 문서 정확도를 일반화할 수 없습니다. Golden Live v1은 핵심값이 expected와
일치했지만 amount/due-date evidence 검증에서 차단됐습니다. 이는 값이 맞아도
근거가 틀리면 금융 계산에 보내지 않는 정책을 보여줍니다. 결정론 recovery 수정은
API-free 검증만 완료했으며, 수정 후 별도 승인 Live 재실행 전에는 end-to-end
성공을 주장하지 않습니다.

## 17. 왜 Golden 계약서와 스캔 평가문서를 분리했나요?

Golden은 메인 성공 흐름과 사람이 읽을 수 있는 evidence를 보여줍니다. 스캔형
8건은 독립 검증 근거가 없을 때 자동 계산을 막는 안전성을 보여줍니다. 한 문서에
성공성과 fail-closed 검증을 억지로 섞지 않습니다.

## 18. 실제 고객문서와 개인정보는 어떻게 보호했나요?

실제 고객문서를 사용하지 않았습니다. Golden과 benchmark는 가상 당사자와 합성
금액만 사용하고 주소·전화·이메일·계좌·등록번호·로고·서명·도장을 넣지 않았습니다.
API key, Authorization header, 전체 prompt·payload·raw response도 제출 파일에
저장하지 않았습니다.

## 19. 금융상품 추천과 승인 판단을 어떻게 구분하나요?

현재 출력은 공식 출처가 연결된 상담 후보 최대 3개와 확인 질문입니다. 가격, 한도,
자격, 보험 인수, 대출 승인과 주문을 확정하지 않고 `UNKNOWN`·`상담 필요`로
남깁니다. 최종 결정은 KB 담당자의 공식 심사 영역입니다.

## 20. 환율모델의 방향점수와 q90은 확률인가요?

아닙니다. `probability_calibrated=false`인 방향점수는 시장 문맥이고 q90은
경로위험 분위수입니다. 기대손실 확률가중치로 사용하지 않으며 결제일이 21거래일
범위 밖이면 모델 값을 계산에서 제외합니다.

## 21. Golden 결제일은 Stage 1 지원 범위 안인가요?

네. fixture 예측일은 2026-07-27, 21거래일 종료일은 2026-08-25이고 Golden 잔금일은
2026-08-20입니다. `test_due_date_is_inside_current_stage1_horizon`이 이 경계를
API-free로 검증합니다.

## 22. 실제 배포 전에 무엇이 더 필요한가요?

사용자 인증과 tenant별 권한·데이터 분리, TLS와 secret manager, 악성파일 검사,
sandboxed PDF rendering, 동의·보존·삭제 정책, 중앙 감사로그, rate limit,
production egress allowlist, 실제 견적·심사 시스템 계약과 운영 모니터링이
필요합니다. 현재 로컬 Streamlit MVP가 이를 구현했다고 주장하지 않습니다.
