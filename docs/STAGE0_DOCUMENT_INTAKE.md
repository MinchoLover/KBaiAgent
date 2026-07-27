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

문서 모델은 국가를 자연어로 반환할 수 있습니다. 검증 전에
`src/document_intake/normalization.py`가 판매자·구매자·사용자 회사 국가를 같은
별칭 규칙으로 ISO alpha-2에 정규화합니다. 원래 모델값은 confirmation 원본 snapshot과
`normalization_audit.raw_value`에 유지합니다. 확인되지 않은 별칭은 임의 코드로
바꾸지 않고 원문을 유지한 채 `UNKNOWN_COUNTRY_ALIAS`를 표시합니다.

통화 evidence가 별도로 없더라도 금액 evidence의 실제 `source_text`에 같은 ISO
통화 코드가 명시되어 있으면 그 원문과 페이지를 그대로 재사용해 currency evidence를
연결합니다. 값만 보고 source text를 만들지는 않습니다.

## Responses API

`src/document_intake/openai_adapter.py`만 SDK 세부를 압니다. 이미지는 `input_image`,
PDF는 base64 `input_file`, 응답은 Pydantic `text_format`으로 파싱합니다. `store=false`
이고 정상 응답도 validator를 통과해야 합니다. 기본 모델 1회 + 재시도 1회 후 다른
fallback 모델을 한 번 시도합니다.

## 결정론 검증

순서는 raw extraction → placeholder/문자열 정리 → 국가 정규화 → 금액·날짜
정규화 → evidence 후처리 → trade type 자동판정 → 필수값 → 논리 검증 → 사용자
확인 gate → Stage 2 계약 생성으로 고정합니다.

- ISO 형태 통화와 모든 양수 금액
- Balance Due와 Grand Total 관계
- 분할 합계와 amount_due
- 날짜 형식·순서와 Net N
- Contract/Invoice Date 기준 calendar/business day Net 조건은 일반 코드로 계산
- shipment, delivery, EOM 등 지원하지 않는 복합 Net 조건은 임의 산술하지 않고 review
- 명시 due와 계산 due 충돌
- 사용자 역할·당사자 국가 evidence와 거래 방향
- evidence에서 여러 통화 및 prompt injection 문구
- 핵심값 evidence와 필수값 누락

CRITICAL/HIGH가 있거나 핵심값이 없으면 `validation_pass=false`입니다. 모델의
`needs_human_review`를 믿지 않고 위 규칙으로 다시 계산합니다.

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
AI evidence가 없을 때는 사용자가 원문에서 직접 대조한 필드만 override로 별도
기록할 수 있으며 AI evidence가 존재한 것처럼 기록하지 않습니다. 다섯 확인과
validation PASS가 모두 충족되기 전에는 Stage 2 입력을 만들 수 없습니다.

`tests/fixtures/kbfx_sales_contract_extraction.json`은
`United States → US`, `Republic of Korea → KR`, `BUYER → IMPORT`,
`YYYY-MM-DD → null`, 계약일 2026-07-27 기준 Net 90 calendar days
`2026-10-25`를 API 없이 회귀 검증합니다. 실제
`KBFX_sample_international_sales_contract.pdf` 파일은 현재 저장소에서 미확인입니다.
