# KBaiAgent 3분 발표자료 원고

형식: 7장 Markdown source

데모: API-free Golden 수출계약

주장 경계: 실제 예약·RM 전송·상품 승인·실고객 검증 없음

## Slide 1 — 환율 전망이 아니라 내 계약의 다음 행동

화면:

- 수출계약 한 장
- “USD 100,000 예정 수취”
- “어떤 위험을 먼저 KB와 상담할 것인가?”

발표:

> 중소기업 재무 담당자는 환율 전망보다 이 계약이 원화 현금, 회수와 다음 상담에
> 어떤 영향을 주는지 알아야 합니다. KBaiAgent는 확인된 계약정보를 현금 숫자와
> 위험 기반 상담 행동으로 연결합니다.

방어:

- 실제 현재 미수잔액이 아니라 분석 대상 예정 수취 노출액
- 실제 입금 이력 없으면 `UNKNOWN`

## Slide 2 — AI 입력을 그대로 돈 계산에 넣지 않는다

화면:

```text
문서 업로드
→ AI 구조화
→ 원문 evidence 대조
→ 국가 canonicalization
→ 사용자 확인
→ Decimal 계산
```

발표:

> AI는 비정형 문서를 구조화하지만, 원문 quote와 사용자 확인을 통과하기 전에는
> 금융 계산에 들어가지 않습니다. 텍스트가 없는 scan은 독립 검증 근거가 없어
> fail closed합니다.

근거:

- `src/document_intake/`
- `validators.py`
- `tests/test_source_evidence_recovery.py`
- `tests/test_workflow.py`

## Slide 3 — Golden 계약을 원화 현금으로 변환

화면:

| 값 | 결과 |
|---|---:|
| 예정 수취 노출 | USD 100,000 |
| 기준 수취 | 140,000,000원 |
| -5% 수취 | 133,000,000원 |
| 기준 대비 감소 | 7,000,000원 |
| -5% ending cash | 8,000,000원 |
| 목표 buffer | 10,000,000원 |
| buffer shortfall | 2,000,000원 |
| cash deficit | 0원 |
| payment/post-credit deficit | 0원 |

발표:

> 환율 하락 시 원화 수취는 700만원 줄고 목표 운영자금 버퍼는 200만원
> 부족합니다. 그러나 현금 적자와 지급부족은 모두 0원입니다. 버퍼 부족을
> 지급불능이나 필요 대출금으로 바꾸지 않습니다.

근거:

- `tests/test_consultation_priority.py::test_golden_numeric_rationale_uses_existing_results`

## Slide 4 — 위험 기반 상담 Top 3

화면:

1. 수출대금 회수 보호
2. 환율 관리
3. 운영자금 버퍼·수출대금 회수시점

발표:

> 이 순서는 AI 추천이나 승인등급이 아닙니다. 기존 risk finding과 공개된 category
> tie-break의 결정론적 검토 순서입니다. 같은 topic을 다른 순서로 입력해도 같은
> rank와 fingerprint가 나옵니다.

카드 한 줄:

- 1순위: USD 80,000 Open Account/T/T 잔금, 보호수단 없음, 실제 USD 20,000
  입금 `UNKNOWN`
- 2순위: USD 100,000 열린 예정 노출, 손실 7,000,000원 > 허용손실
  5,000,000원
- 3순위: ending cash 8,000,000원, buffer shortfall 2,000,000원,
  두 deficit 0원

근거:

- `src/consultation/prioritization.py`
- `tests/test_consultation_priority.py`

## Slide 5 — 상품 목록이 아니라 상담 준비

화면:

```text
각 Top 3
├─ 숫자와 source path
├─ 아직 확인할 정보
├─ 준비자료
├─ 은행 질문
├─ 상담에서 기대하는 결정
├─ 다음 행동
└─ 공식 후보 최대 3
```

발표:

> 공식 후보는 출처와 연결 이유를 보여주지만 eligibility는 UNKNOWN,
> approval은 CONSULTATION_REQUIRED입니다. 후보가 없으면 새 상품을 만들지
> 않습니다. 사용자는 계약서·인보이스·선적서류·입금내역과 자금계획을 준비해
> 사람 상담을 요청합니다.

금지:

- 가입하세요
- 대출받으세요
- 승인될 것입니다
- 최적 상품입니다

## Slide 6 — 같은 JSON에서 화면·다운로드·보고서

화면:

```text
ConsultationPacket JSON
├─ Streamlit Top 3
├─ one-page Markdown handoff
└─ Stage 5 report / deterministic fallback
```

발표:

> UI, Markdown과 최종 보고서는 같은 JSON의 rank와 숫자를 사용합니다. AI는
> 선택적 renderer일 뿐 순서와 numeric rationale를 바꾸지 못합니다. critic은
> 승인등급, 지급불능, 실제 미수, 최적 추천, RM 전송 완료 같은 과장을 거부합니다.

경계:

- 다운로드는 상담 준비자료 생성
- 실제 예약·RM 전송·신청·내부심사 연동 없음

## Slide 7 — 검증과 정확한 현재 수준

화면:

- API-free tests: 456/456 PASS
- `scripts/verify.py`: PASS
- regression: 임시 Git archive에서 PASS
- Golden PDF SHA-256 불변
- Live: recovery 이후 제한된 합성 Golden 1건 성공

발표:

> 최초 Golden Live는 값이 맞아도 evidence 오류로 차단됐고, recovery 이후 승인된
> 한 건에서 validation pass와 사용자 확인 후 Stage 2 허용을 확인했습니다.
> 전체 문서 정확도나 실제 고객환경 성능으로 일반화하지 않습니다. 현재 완성 범위는
> 위험 기반 KB 상담 준비와 handoff packet이며, 실제 운영 연동은 다음 단계입니다.

마지막 문장:

> KBaiAgent는 AI가 금융결정을 대신하는 서비스가 아니라, 확인된 사실과 결정론
> 숫자로 기업과 KB가 더 정확한 상담을 시작하게 하는 서비스입니다.

## 발표자 체크리스트

- [ ] USD 100,000을 실제 미수잔액이라고 하지 않음
- [ ] USD 20,000 실제 입금 상태를 `UNKNOWN`으로 말함
- [ ] 2,000,000원과 cash/payment deficit 0원을 함께 말함
- [ ] 상담 순위를 검토 순서라고 설명
- [ ] 공식 후보의 eligibility·approval을 확정하지 않음
- [ ] OECD raw 4를 국가신용등급이라고 하지 않음
- [ ] Stage 3을 최적 추천이라고 하지 않음
- [ ] Markdown을 RM 전송 완료라고 하지 않음
- [ ] Golden Live를 제한된 합성문서 1건으로만 설명
- [ ] 실제 고객·운영 배포 완료를 주장하지 않음
