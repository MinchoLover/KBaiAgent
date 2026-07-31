# 필드 추출 규칙

1. `document_type`은 COMMERCIAL_INVOICE, SALES_CONTRACT, PURCHASE_ORDER,
   UNKNOWN 중 하나다.
2. invoice number, contract number, PO number는 `document_number`에 넣는다.
3. seller/buyer 이름과 국가는 문서에서 명시된 경우에만 추출한다.
4. `company_role`은 요청 컨텍스트의 BUYER 또는 SELLER를 그대로 사용한다.
5. `trade_type`은 역할만으로 정하지 않는다. 사용자 회사 국가가 BUYER 국가와
   일치하고 SELLER 국가가 다른 국가로 명시된 경우 IMPORT, 사용자 회사 국가가
   SELLER 국가와 일치하고 BUYER 국가가 다른 국가로 명시된 경우 EXPORT다.
   당사자 국가가 없거나 같거나 충돌하면 UNKNOWN이다. 국가와 거래방향을 확정할
   때는 판매자·구매자 국가가 보이는 원문을 evidence로 남긴다.
6. subtotal, tax, grand total, paid amount, balance due를 구분한다.
7. `amount_due`는 Balance Due 또는 Amount Due처럼 실제 미지급·미수 금액을
   우선한다. 그런 필드가 없으면 문서가 총액 전액 지급임을 명확히 표현한 경우에만
   grand total과 같게 둘 수 있다.
8. 여러 통화가 거래 후보로 등장하고 어느 통화가 최종 거래 통화인지 명확하지 않으면
   currency와 관련 금액은 null로 두고 warnings에 충돌을 기록한다.
9. `explicit_due_date`에는 결제일이 날짜로 직접 쓰인 경우만 넣는다.
   Net N으로 계산한 날짜를 넣지 않는다.
10. `derived_due_date`는 항상 null로 반환한다. Net 30/60/90 등은 원문 의미를
    유지해 `payment_terms`에 넣고 날짜 계산은 Python 검증기에 맡긴다.
    EOM, after shipment, acceptance 기준처럼 기준 사건이 추가된 조건은 단순 Net N로
    바꾸지 않는다.
11. invoice date, contract date, shipment date, due date를 서로 바꾸지 않는다.
12. 분할결제는 각 installment에 sequence, amount, currency, due_date, condition을 넣는다.
13. 핵심 필드마다 짧고 국소적인 원문을 evidence에 남긴다. 특히
    `seller_name`, `seller_country`, `buyer_name`, `buyer_country`, `currency`,
    `amount_due`, `issue_date`, `explicit_due_date`, `contract_date`,
    `payment_terms`, `installments` 값이 존재하면 각각의 **정확히 같은 field
    이름**으로 evidence를 반드시 반환한다. 반환 직전에 위 비어 있지 않은 핵심
    필드마다 `INFERRED`가 아닌 evidence 항목이 하나 이상 있는지 체크한다.
    판매자·구매자 이름에는 `Legal Name`, `Seller`, `Buyer` 등이 포함된 실제 원문,
    국가에는 해당 당사자의 `Country` 실제 원문을 사용한다. 통화와 금액이 같은
    문구에 있으면 동일한 실제 원문을 각 field의 evidence로 사용할 수 있다.
    여러 필드를 하나의 `party` 같은 임의 field로 합치지 않는다. 문서에 없는
    문구를 evidence로 만들지 않는다.
14. `extraction_type`은 문서 직접 표기 EXPLICIT, 코드로 계산할 값 DERIVED,
    문맥 추론 INFERRED 중 하나다. 핵심 금액·통화·날짜에 INFERRED를 남발하지 않는다.
15. `confidence_reason`은 숫자 확률이 아니라 어떤 라벨/문구가 근거인지 설명한다.
16. `missing_required_fields`와 `needs_human_review`는 초기 판단을 반환하되,
    애플리케이션의 결정론 검증기가 최종 값을 다시 계산한다.
