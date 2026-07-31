# Stage 0 Document Intake

## 지원 입력

- Commercial Invoice, International Sales Contract, Purchase Order
- PDF, PNG, JPG/JPEG
- 기본 15MB, PDF 20페이지; env로 낮추거나 높일 수 있음

업로드는 확장자, browser MIME, magic bytes, 실제 Pillow/PDF parse 결과가 모두
일치해야 합니다. 암호화·손상 PDF와 archive는 거부합니다.

## 추출 계약

`TradeDocumentExtraction`은 문서 유형·번호, 당사자와 국가, 사용자 회사 역할,
결정론적으로 정한 수입/수출 방향, 통화, `grand_total`, `amount_due`, 서로 구분된
날짜, 지급조건, Incoterm, 분할결제, evidence, warnings, 누락 필드, review 상태를
포함합니다.

- 금액: 기호·쉼표 없는 양수 decimal 문자열 또는 `null`
- 날짜: `YYYY-MM-DD` 또는 `null`
- 없는 값: 추측하지 않고 `null`
- `derived_due_date`: 모델은 `null`; Python만 계산
- 모델의 confidence 숫자는 사용하지 않음

evidence는 field, 1부터 시작하는 page, 짧은 source_text, `EXPLICIT/DERIVED/INFERRED`,
confidence_reason을 가집니다.

### 금액 Domain 계약

- `grand_total`: 문서에 명시된 계약 또는 청구 총액
- `amount_due`: Stage 2 분석에 투입되는 계약상 미결제 예정 노출액
- Invoice: 명시된 `Balance Due` 또는 `Amount Due`가 우선하며
  `grand_total`보다 작을 수 있음
- SALES_CONTRACT: 지급 완료 정보가 없으면 완료 여부가 확인되지 않은 예정
  installment의 합계를 사용하며 `sum(installments) == amount_due`
- Purchase Order: 명시 amount due가 없으면 order total과 amount_due가 같은
  경우에만 총액 문맥을 사용할 수 있음

Golden 계약서는 USD 20,000 선지급과 USD 80,000 잔금의 실제 이행 여부를 알려주지
않으므로 `amount_due=USD 100,000`을 유지합니다. 실제 입금·지급 이력을 반영한
현재 미수·미지급 잔액은 별도 `actual_outstanding_balance` 개념이며 이 문서만으로
확인할 수 없어 `UNKNOWN`입니다. 신규 Domain 필드는 만들지 않고 내부 JSON
`amount_due` 이름을 유지합니다. 문서가 일부 이행 사실을 표시하지만 어느 회차가
완료됐는지 모호한 경우에는 금액을 임의 선택하지 않고 사람 검토로 보냅니다.

화면에서는 수출 `amount_due`를 `분석 대상 예정 수취액`, 수입 `amount_due`를
`분석 대상 예정 지급액`으로 표시하고 다음 경고를 제공합니다.

> 계약서에 명시된 예정 결제액을 기준으로 분석합니다.
> 실제 입금·지급 이력이 확인되면 이미 이행된 금액을 제외해야 합니다.

문서 모델은 국가를 자연어로 반환할 수 있습니다. 검증 전에
`src/document_intake/normalization.py`가 판매자·구매자·사용자 회사 국가를 같은
별칭 규칙으로 ISO alpha-2에 정규화합니다. 원래 모델값은 confirmation 원본 snapshot과
`normalization_audit.raw_value`에 유지합니다. 확인되지 않은 별칭은 임의 코드로
바꾸지 않고 원문을 유지한 채 `UNKNOWN_COUNTRY_ALIAS`를 표시합니다.

통화 evidence가 별도로 없더라도 금액 evidence의 실제 `source_text`에 같은 ISO
통화 코드가 명시되어 있으면 그 원문과 페이지를 그대로 재사용해 currency evidence를
연결합니다. 값만 보고 source text를 만들지는 않습니다.

판매자·구매자의 이름과 국가는 `seller_name`, `seller_country`, `buyer_name`,
`buyer_country` 각각의 정확한 field evidence가 필요합니다. 모델이 당사자 한 줄에
이름과 국가를 함께 반환한 경우에도 실제 인용문 안에서 현재 값이 확인될 때만 정확한
field로 연결합니다. 상대 당사자 이름·라벨이 섞인 인용문은 국가 evidence로 인정하지
않습니다. `CA`처럼 ISO 코드가 직접 적힌 경우에는 대문자 독립 토큰으로 확인하고,
`Canada` 같은 확인된 별칭도 같은 ISO 코드로 정규화합니다. `No` 같은 일반 단어가
노르웨이 코드 `NO`로 오인되지 않도록 대소문자를 잃은 2글자 토큰은 사용하지 않습니다.

텍스트 레이어가 있는 PDF는 `pypdf`로 메모리 안에서 페이지 텍스트만 읽습니다. 모델
인용문이 실제 페이지에 있어야 하며, 인용문은 현재 당사자·국가·통화·금액·날짜·지급
조건 값을 의미적으로 뒷받침해야 합니다. 통화는 ISO 코드, 금액은 `Decimal`, 날짜는
`date`로 대조합니다. 페이지가 틀렸지만 다른 실제 페이지에서 인용문을 찾으면 그
페이지로 정정합니다. 인용문이 없거나 값이 다르면 canonical extraction에서 제거하고
`EVIDENCE_NOT_IN_SOURCE` 또는 `EVIDENCE_VALUE_MISMATCH`로 Stage 2를 막습니다.

`amount_due` 또는 `explicit_due_date` 모델 evidence가 폐기되더라도 텍스트 PDF의
실제 원문 줄에서 문서유형에 맞는 후보가 하나로 확정되면 결정론적으로 복구할 수
있습니다. 금액은 통화·문맥·`Decimal` 값과 installment aggregate를 함께 검사하고,
날짜는 `Payment Due Date`, `Settlement Date`, `on or before`,
`no later than`, `payment shall be made by` 같은 지급 문맥에서 실제 날짜 표현을
`date`로 파싱합니다. Source quote에는 `2026-08-20` 같은 canonical 값을 새로
만들지 않고 `20 August 2026`처럼 PDF에 있는 원문을 그대로 보존합니다.

같은 강도의 후보가 둘 이상이거나 같은 금액이 계약 총액·잔금 등 여러 의미로
등장하거나 지급일과 계약일·선적일을 구분할 수 없으면
`EVIDENCE_RECOVERY_AMBIGUOUS`로 fail closed합니다. Recovery audit에는 실제 page,
canonical parsed value, `UNIQUE_SEMANTIC_TEXT_LINE` method와 기존 모델 evidence
폐기 사유를 남깁니다. 이 경로는 문자열 유사도를 사용하지 않습니다.

파일이나 원문은 저장·로그하지 않습니다. 이미지·스캔 PDF는 독립 텍스트 레이어가
없으므로 모든 핵심 evidence를 `EVIDENCE_UNVERIFIABLE`로 취급하고
`OCR_REQUIRED`를 표시합니다. 사용자가 문서 미리보기와 직접 대조한 필드만 confirmation
override로 열 수 있으며, 자동 evidence로 승격하지 않습니다.

## Responses API

`src/document_intake/openai_adapter.py`만 SDK 세부를 압니다. 이미지는 `input_image`,
PDF는 base64 `input_file`, 응답은 Pydantic `text_format`으로 파싱합니다. `store=false`
이고 정상 응답도 validator를 통과해야 합니다. 기본 모델 1회 + 재시도 1회 후 다른
fallback 모델을 한 번 시도합니다.

## 결정론 검증

순서는 raw extraction → placeholder/문자열 정리 → 국가 정규화 → 금액·날짜
정규화 → evidence 보완 → 원문·값 기반 evidence 검증 → trade type 자동판정 → 필수값
→ 논리 검증 → 사용자 확인 gate → Stage 2 계약 생성으로 고정합니다.

- ISO 형태 통화와 모든 양수 금액
- Balance Due와 Grand Total 관계
- 분할 합계와 amount_due
- 날짜 형식·순서와 Net N
- Contract/Invoice Date 기준 calendar/business day Net 조건은 일반 코드로 계산
- shipment, delivery, EOM 등 지원하지 않는 복합 Net 조건은 임의 산술하지 않고 review
- 명시 due와 계산 due 충돌
- 사용자 역할·당사자 국가 evidence와 거래 방향
- evidence에서 여러 통화 및 prompt injection 문구
- 핵심값 evidence의 원문 존재·현재 값 일치·필수값 누락

CRITICAL/HIGH가 있거나 핵심값이 없으면 `validation_pass=false`입니다. 모델의
`needs_human_review`를 믿지 않고 위 규칙으로 다시 계산합니다.

사용자가 추출값을 고치면 이전 값에 붙어 있던 모델 evidence를 제거한 뒤 전체
결정론 검증을 다시 실행합니다. 새 값에 과거 인용을 재사용하지 않으며, 사용자가
원문을 직접 대조한 경우에만 confirmation override로 별도 기록합니다.

## 확인 gate

사용자는 추출 필드를 수정하고 다음 다섯 항목을 각각 체크합니다.

- company role
- trade type
- currency
- amount_due
- settlement date

확인 기록에는 전체 원본 추출 snapshot, 전체 수정 snapshot, 확인시각, 파일명,
SHA-256 fingerprint, 자동판정/사용자 override 출처가 남습니다. 단일 결제는 실제
확인 날짜가 필요하고, 분할결제는 회차별 due date를 한 묶음으로 확인할 수 있습니다.
AI evidence가 없거나 원문·값 대조에 실패한 경우에는 사용자가 원문에서 직접 대조한
필드만 override로 별도 기록할 수 있으며 AI evidence가 존재한 것처럼 기록하지
않습니다. 다섯 확인과 validation PASS가 모두 충족되기 전에는 Stage 2 입력을 만들 수
없습니다.

`tests/fixtures/kbfx_sales_contract_extraction.json`은
`United States → US`, `Republic of Korea → KR`, `BUYER → IMPORT`,
`YYYY-MM-DD → null`, 계약일 2026-07-27 기준 Net 90 calendar days
`2026-10-25`를 API 없이 회귀 검증합니다. 실제
`KBFX_sample_international_sales_contract.pdf` 파일은 현재 저장소에서 미확인입니다.
