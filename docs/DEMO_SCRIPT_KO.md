# Golden 수출계약 메인 데모 스크립트

## 데모 자산과 주장 경계

메인 문서는
`dataset/golden_demo/golden_export_contract.pdf`입니다. 한국 합성 판매자가 브라질
합성 구매자에게 USD 100,000의 장비를 수출하고 20% 선지급·80% T/T 잔금을 받는
2페이지 영문 텍스트 레이어 계약서입니다.

최초 Golden Live v1은 핵심값이 맞았지만 amount/due-date evidence 검증에서
차단됐습니다. 이 실패는 역사적 baseline으로 보존합니다. 이후 결정론
source-grounded recovery가 적용된 승인된 Golden Live 1건에서
`validation_pass=true`, 사용자 확인 후 `stage2_allowed=true`를 확인했습니다.
이번 제출 점검에서는 Live API를 다시 호출하지 않습니다. 무대에서는 API-free
fixture를 기본 경로로 사용하고, Live 성공은 “제한된 합성문서 한 건”으로만
설명합니다.

## 발표 전 API-free 확인

```bash
shasum -a 256 dataset/golden_demo/golden_export_contract.pdf
python -m unittest tests.test_golden_trade_demo -v
python scripts/run_decision_demo.py --company-role SELLER --format summary
python scripts/verify.py
APP_ENV=presentation python -m streamlit run app.py
```

Golden PDF의 기대 SHA-256은
`5330a1a572488005f7b02cccfc7150fbaa8b38c84bb9290da1e0c6e1c3a0a91c`입니다.
발표 직전에는 생성기로 덮어쓰지 않고 이 지문과 테스트로 무결성을 확인합니다.

## 발표 모드 실행

발표 직전에는 저장소 루트에서 다음과 같이 실행합니다.

```bash
APP_ENV=presentation python -m streamlit run app.py
```

발표 모드는 첫 화면과 사이드바의 미국·수입 API-free 샘플 실행 버튼을 숨기고
`샘플 수출 거래로 체험하기`만 주 CTA로 표시합니다. 또한 발표자가 아래
업로드 영역으로 바로 이동해도 미국 fixture가 선택되지 않도록 문서 등록 모드로
고정합니다. 이 환경변수는 UI 진입 경로만 바꾸며 Golden 결과를 자동 주입하거나,
금융 계산·상담 순위·ConsultationPacket·문서 추출 provider를 변경하지 않습니다.
기본 개발 모드는 `APP_ENV=development`이거나 `APP_ENV`를 지정하지 않은
상태이며 기존 샘플 버튼과 데모 모드 선택이 그대로 표시됩니다.

앱 첫 화면의 `샘플 수출 거래로 체험하기`는 실제 고객정보가 없는 브라질 Golden
fixture를 문서 등록 상태로 불러와 정식 서비스 여정을 시작합니다. 발표에서는
브라질 Golden 단일 사례만 사용합니다. 개발 모드의 고급 설정에 남겨 둔 미국 수출 샘플은
회귀 확인용 보조 경로이며, 미국 샘플의 국가·일정·상담 결과를 브라질 Golden
결과처럼 설명하지 않습니다.

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
| 분석 대상 예정 수취액 (`amount_due`) | USD 100,000 |
| 실제 현재 미수잔액 | `UNKNOWN` · 계약서만으로 입금 이력 확인 불가 |
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

발표자는 `amount_due`를 현재 미수금이라고 부르지 않고 다음 문구를 그대로
설명합니다.

> 현재 분석은 계약서에 명시된 예정 결제액을 기준으로 합니다.
> 실제 입금·지급 이력을 반영한 현재 미수·미지급 잔액은 별도 확인이 필요합니다.

## 실제 화면 순서

| 단계 | 클릭·입력 | 강조할 결과 | 발표자 한 문장 | 실패 시 fallback |
| --- | --- | --- | --- | --- |
| 1. Golden 계약서 업로드 | 첫 화면 `샘플 수출 거래로 체험하기`; 등록된 Golden 문서를 확인하고 `문서 분석하고 거래정보 채우기` | 2페이지 텍스트 PDF와 합성·법적 효력 없음 표시 | “실제 고객정보가 없는 합성 계약서 한 장으로 시작합니다.” | PDF와 `expected_extraction.json`을 나란히 보여주고 수정 후 Live가 미검증임을 밝힘 |
| 2. 텍스트 evidence 확인 | `1 거래 확인`의 `상세 거래정보`에서 원문 근거를 펼치기 | 각 exact quote의 page 1/2 연결 | “텍스트 레이어의 짧은 인용이 실제 페이지에 있는지 일반 코드가 대조합니다.” | `python -m unittest tests.test_source_evidence_recovery -v` 결과 제시 |
| 3. 핵심 거래값 사용자 확인 | `KR/BR`, `EXPORT`, `USD`, `100000.00`, `2026-08-20` 확인 후 확인 버튼 | `분석 대상 예정 수취액 USD 100,000`; 실제 미수잔액 `UNKNOWN` | “계약서의 예정 결제액을 기준으로 분석하며 실제 입금이력을 반영한 현재 미수잔액은 별도 확인이 필요합니다.” | `expected_extraction.json`과 Golden consultation fixture 결과를 제시하고 미국 샘플로 전환하지 않음 |
| 4. 거래·회수 조건 확인 | `2 금융 분석` → 거래처 `기존`, 선지급 `비율 확인 20%`, 잔금 `Open Account`, 기간 22일, 보호수단 `없음 확인` | `EXPORT_RECEIVABLE_COLLECTION_RISK`, `ELEVATED_REVIEW` | “기존 거래처라도 Open Account이고 적용 가능한 보호수단이 없으면 회수보호 상담을 추가 검토합니다.” | `demo_inputs.json`과 Golden domain test 결과 제시 |
| 5. 환율 시장 문맥 확인 | 같은 탭의 환율 상세 펼치기 | 하락 0.712·상승 0.288, q90 하락 3.6%, `보정확률 아님` | “방향점수와 q90은 실제 발생확률이 아니며 뉴스도 금융 숫자를 바꾸지 않습니다.” | Stage 1 fixture JSON의 hash·고정 값을 표시 |
| 6. 원화 현금 영향 확인 | 현금 20,000,000; 버퍼 10,000,000; 한도 0; 운영비 145,000,000 입력 후 계산 | 기준 수취 140,000,000원; -5% 수취 133,000,000원; 감소 7,000,000원; 결제 후 8,000,000원; 버퍼 부족 2,000,000원; 지급부족 0원 | “환율 하락 손실, 운영자금 버퍼 부족, 지급불능을 서로 다른 숫자로 분리합니다.” | `test_demo_finance_inputs_produce_meaningful_existing_stage2_result` 결과 제시 |
| 7. 환헤지 비교안 확인 | `3 상담 준비` 아래 선택 분석의 안정성·균형·비용 후보 열기 | 후보별 비율·비용 가정·최저 현금, 최대 3개 | “이 값은 실제 견적이나 자동 추천이 아니라 동일 입력의 계산상 비교안입니다.” | Golden API-free 계산 테스트 결과를 제시하고 다른 국가 fixture를 섞지 않음 |
| 8. 국가·무역환경 확인 | 브라질 국가환경 섹션과 공식 근거 펼치기 | OECD raw 4, World Bank·WTO 별도 축, 국가환경 `STANDARD_REVIEW`; 별도 거래·회수 위험 `ELEVATED_REVIEW` | “세 공식 축을 국가 신용점수로 합치지 않고 이 거래에서 확인할 상담 순서만 제시합니다.” | versioned offline snapshot과 T4 테스트 결과 제시 |
| 9. 상담 Top 3 확인 | `2 금융 분석`의 핵심 결과 바로 아래 카드 확인 | 1순위 회수 보호 → 2순위 환율 → 3순위 운영자금 버퍼; 각 카드의 숫자·부족정보·기대 결정·다음 행동 | “이 순서는 AI 추천이나 승인등급이 아니라 기존 위험 finding의 결정론적 검토 순서입니다.” | `tests.test_consultation_priority`와 JSON packet 출력 제시 |
| 10. 실제 입금 상태 경계 확인 | 1순위 카드의 `USD 20,000 선지급 실제 입금 여부 UNKNOWN` 확인 | 부족정보 첫 항목과 보호수단 현황에 UNKNOWN 표시 | “계약상 예정 노출액은 10만 달러지만 실제 선지급 입금 여부는 계약서만으로 확정하지 않습니다.” | Golden packet Markdown에서 동일 항목 표시 |
| 11. 공식 상담 후보 확인 | Top 3 카드의 `준비자료·질문·공식 후보` 펼치기 | 공식 URL·검증일·연결 이유, eligibility UNKNOWN, approval CONSULTATION_REQUIRED | “공식 출처와 상담범주가 맞는 후보만 연결하고 가입 가능성은 확정하지 않습니다.” | offline KB snapshot을 사용하고 후보가 없으면 빈 상태 유지 |
| 12. 한 페이지 handoff 확인 | `4 결과 다운로드` → `상담 준비서 다운로드` | 거래·회차·보호수단·Top 3·준비자료·질문·공식후보·trace가 같은 JSON에서 파생 | “다운로드는 상담 준비자료이며 예약·RM 전송·신청 완료가 아닙니다.” | 결정론 Markdown handoff와 Stage 5 fallback 표시 |

## Golden 발표 숫자

Golden 수동 입력과 기존 계산식의 API-free test 결과입니다.

- 분석 대상 예정 수취액: USD 100,000
- 실제 현재 미수잔액: `UNKNOWN`
- 기준환율: 1,400원
- 기준 원화 수취: 140,000,000원
- 환율 -5%: 1,330원
- -5% 원화 수취: 133,000,000원
- 기준 대비 수취 감소: 7,000,000원
- 운영비 반영 후 현금: 8,000,000원
- 최소 버퍼 부족: 2,000,000원
- 현금 적자·신용 후 지급부족: 0원
- 상담 1순위: 수출대금 회수 보호 상담
- 상담 2순위: 환율 관리 상담
- 상담 3순위: 운영자금 버퍼·수출대금 회수시점 상담
- USD 20,000 선지급 실제 입금 여부: `UNKNOWN`

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
먼저 검토할 상담 세 가지, 숫자 근거, 부족정보와 준비사항을 같은 화면과 handoff
문서에 정리합니다. 실제 예약·RM 전송·상품 승인은 사람이 이어서 수행합니다.”
