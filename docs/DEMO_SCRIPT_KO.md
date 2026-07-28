# Golden 수출계약 메인 데모 스크립트

## 데모 자산과 주장 경계

메인 문서는
`dataset/golden_demo/golden_export_contract.pdf`입니다. 한국 합성 판매자가 브라질
합성 구매자에게 USD 100,000의 장비를 수출하고 20% 선지급·80% T/T 잔금을 받는
2페이지 영문 텍스트 레이어 계약서입니다.

이 PDF의 Golden Live v1은 핵심값이 맞았지만 amount/due-date evidence 검증에서
차단됐습니다. 결정론 recovery 수정은 API-free 테스트만 통과했으므로 실제 문서
분석을 메인 무대에서 사용하기 전에 수정 commit으로 별도 승인 Live 재검증이
필요합니다. 재검증 결과가 없거나 호출이 불안정하면 아래 fallback을 사용하며
모델 end-to-end 성공 데모라고 말하지 않습니다.

## 발표 전 API-free 확인

```bash
python scripts/generate_golden_trade_demo.py
python -m unittest tests.test_golden_trade_demo -v
python scripts/run_decision_demo.py --company-role SELLER --format summary
python scripts/verify.py
python -m streamlit run app.py
```

Expected data와 수동 입력은 다음 두 파일을 옆 화면에 준비합니다.

- `dataset/golden_demo/expected_extraction.json`
- `dataset/golden_demo/demo_inputs.json`

Country validation의 스캔형 8건은 메인 성공 데모에 사용하지 않습니다. 해당 문서는
안전 차단 설명에서만 사용합니다.

## 메인 입력값

### 계약서에서 확인하는 값

| 항목 | 값 |
| --- | --- |
| 문서유형 | `SALES_CONTRACT` |
| 판매자 | Hanbit Precision Co., Ltd. |
| 판매자 국가 | `Republic of Korea (KR)` → `KR` |
| 구매자 | Aurora Comercio de Equipamentos Ltda. |
| 구매자 국가 | `Brazil (BR)` → `BR` |
| 우리 회사 역할·거래방향 | `SELLER` · `EXPORT` |
| 통화·총액 | USD · 100,000 |
| 계약일·선적일 | 2026-07-29 · 2026-08-05 |
| 결제구조 | USD 20,000 선지급 + USD 80,000 잔금 |
| 잔금 결제일 | 2026-08-20 |
| 결제방식 | Open Account · T/T |
| Incoterm | FOB Busan, Incoterms 2020 |
| 신용장·독립 지급보증 | 불필요 · 미제공 |

### 사용자가 별도로 확인하는 값

| 화면 입력 | 값 |
| --- | --- |
| 거래처 관계 | `EXISTING` |
| 선지급 | 비율 확인 · 20% |
| 잔여대금 방식 | `OPEN_ACCOUNT` |
| 결제기간 기준·일수 | 확정일 간격 · 22일 |
| 보호수단 | `NONE_CONFIRMED` |
| 수출신용보험 | NO |
| 기존 헤지 | NONE |
| 현재 원화현금 | 20,000,000원 |
| 최소 현금 버퍼 | 10,000,000원 |
| 신용한도 | 0원 |
| 허용 환손실 | 5,000,000원 |
| 결제일 확정 운영비 | 145,000,000원 유출 |
| 기준환율 | fixture USD/KRW 1,400원 |

보험, 거래처 관계, 보유외화·현금·신용한도와 기존 헤지는 계약서가 알려주는 값이
아니므로 반드시 사용자 입력이라고 설명합니다.

## 실제 화면 순서

| 단계 | 클릭·입력 | 강조할 결과 | 발표자 한 문장 | 실패 시 fallback |
| --- | --- | --- | --- | --- |
| 1. Golden 계약서 업로드 | 사이드바 `데모 및 연결 설정` → `실제 문서 분석`; 역할 `판매자 · SELLER`; 회사국가 `KR`; Golden PDF 업로드; `문서 분석하고 거래정보 채우기` | 2페이지 텍스트 PDF와 합성·법적 효력 없음 표시 | “실제 고객정보가 없는 합성 계약서 한 장으로 시작합니다.” | PDF와 `expected_extraction.json`을 나란히 보여주고 수정 후 Live가 미검증임을 밝힘 |
| 2. 텍스트 evidence 확인 | `1 문서 확인`에서 판매자·구매자·금액·결제일의 원문 근거 펼치기 | 각 exact quote의 page 1/2 연결 | “텍스트 레이어의 짧은 인용이 실제 페이지에 있는지 일반 코드가 대조합니다.” | `python -m unittest tests.test_source_evidence_recovery -v` 결과 제시 |
| 3. 핵심 거래값 사용자 확인 | `KR/BR`, `EXPORT`, `USD`, `100000.00`, `2026-08-20` 확인 후 확인 버튼 | `Republic of Korea (KR)→KR`, `Brazil (BR)→BR`, `EXPORT` | “AI 값은 evidence와 규칙 검증 뒤에도 사람이 확인해야 계산으로 넘어갑니다.” | expected data를 읽어 설명하고 앱의 `수출기업 대표 데모`로 계산 화면 전환 |
| 4. 거래·회수 조건 확인 | `2 위험 진단` → 거래처 `기존`, 선지급 `비율 확인 20%`, 잔금 `Open Account`, 기간 22일, 보호수단 `없음 확인` | `EXPORT_RECEIVABLE_COLLECTION_RISK`, `ELEVATED_REVIEW` | “기존 거래처라도 Open Account이고 적용 가능한 보호수단이 없으면 회수보호 상담을 추가 검토합니다.” | `demo_inputs.json`과 Golden domain test 결과 제시 |
| 5. 환율 시장 문맥 확인 | 같은 탭의 환율 상세 펼치기 | 하락 0.712·상승 0.288, q90 하락 3.6%, `보정확률 아님` | “방향점수와 q90은 실제 발생확률이 아니며 뉴스도 금융 숫자를 바꾸지 않습니다.” | Stage 1 fixture JSON의 hash·고정 값을 표시 |
| 6. 원화 현금 영향 확인 | 현금 20,000,000; 버퍼 10,000,000; 한도 0; 운영비 145,000,000 입력 후 계산 | 기준 수취 140,000,000원; -5% 수취 133,000,000원; 감소 7,000,000원; 결제 후 8,000,000원; 버퍼 부족 2,000,000원; 지급부족 0원 | “환율 하락 손실, 운영자금 버퍼 부족, 지급불능을 서로 다른 숫자로 분리합니다.” | `test_demo_finance_inputs_produce_meaningful_existing_stage2_result` 결과 제시 |
| 7. 환헤지 비교안 확인 | `3 대응안 비교`의 안정성·균형·비용 후보 열기 | 후보별 비율·비용 가정·최저 현금, 최대 3개 | “이 값은 실제 견적이나 자동 추천이 아니라 동일 입력의 계산상 비교안입니다.” | `수출기업 대표 데모`의 결정론 Stage 3 결과 사용 |
| 8. 국가·무역환경 확인 | 브라질 국가환경 섹션과 공식 근거 펼치기 | OECD raw 4, World Bank·WTO 별도 축, `HIGH_REVIEW` 거래 검토 우선도 | “세 공식 축을 국가 신용점수로 합치지 않고 이 거래에서 확인할 상담 순서만 제시합니다.” | versioned offline snapshot과 T4 테스트 결과 제시 |
| 9. 공식 상담 후보 확인 | 같은 탭의 공식 후보 최대 3개 확인 | 공식 URL·검증일·상담 필요, 승인·가격은 UNKNOWN | “공식 출처와 상담범주가 맞는 후보만 연결하고 가입 가능성은 확정하지 않습니다.” | offline KB snapshot을 사용하고 후보가 없으면 빈 상태 유지 |
| 10. 최종 상담자료 확인 | `4 상담자료` → Markdown 미리보기·다운로드 | 거래·환율·현금·회수위험·국가 근거와 은행 질문 | “AI가 승인 결론을 내리는 것이 아니라 KB 상담을 시작할 근거와 준비사항을 만듭니다.” | 결정론 report fallback을 다운로드 |

## Golden 발표 숫자

Golden 수동 입력과 기존 계산식의 API-free test 결과입니다.

- 열린 수출노출: USD 100,000
- 기준환율: 1,400원
- 기준 원화 수취: 140,000,000원
- 환율 -5%: 1,330원
- -5% 원화 수취: 133,000,000원
- 기준 대비 수취 감소: 7,000,000원
- 운영비 반영 후 현금: 8,000,000원
- 최소 버퍼 부족: 2,000,000원
- 현금 적자·신용 후 지급부족: 0원

잔금일 2026-08-20은 Stage 1 fixture의 예측일 2026-07-27부터 21거래일 종료일
2026-08-25 이내입니다. 이 Golden 사례에서는 model path와 고정 스트레스를 함께
계산할 수 있습니다. q90을 확률로 말하지 않습니다.

## 보조 안전성 데모

Country validation 스캔형 PDF/JPG 8건의 Baseline v2를 한 장으로 보여주고 다음만
말합니다.

> 독립 검증할 수 없는 스캔문서는 AI 결과를 자동으로 금융계산에 전달하지 않고
> 사용자 확인을 요구합니다.

API 성공 8/8과 validation·Stage 2 허용 0/8을 혼동하지 않습니다. Evidence
coverage 0%는 OCR 정확도 0%가 아닙니다.

## 마무리

“KBaiAgent는 환율을 맞혀 자동 거래하는 서비스가 아닙니다. 계약서의 확인된
결제정보와 시장 위험 구간을 원화 현금흐름으로 연결하고, 기업과 KB 담당자가
상담해야 할 위험·근거·준비사항을 같은 화면에 정리합니다.”
