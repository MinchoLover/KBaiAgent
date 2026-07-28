# Validation Report

검증일: 2026-07-29 KST
환경: macOS, Python 3.9.6, Streamlit 1.50.0, Pydantic 2.13.4

## 최종 결과

| 검증 | 명령 | 결과 |
| --- | --- | --- |
| 한 명령 release gate | `python scripts/verify.py` | PASS |
| compile | `PYTHONPYCACHEPREFIX=/tmp/invoice_intake_pycache .venv/bin/python -m compileall -q app.py src scripts tests` | PASS |
| 전체 unit/integration/E2E | `python -m unittest discover -s tests -v` | 436/436 PASS |
| Golden text-layer 계약서 | `python -m unittest tests.test_golden_trade_demo -v` | 14/14 PASS |
| Text-PDF amount/date evidence recovery | `python -m unittest tests.test_source_evidence_recovery -v` | 18/18 PASS |
| T4 snapshot·engine·workflow·T7·UI P0 | `.venv/bin/python -m unittest tests.test_country_environment tests.test_country_environment_integration tests.test_stage5_decision_report tests.test_ui_evidence_state -v` | 60/60 PASS |
| 거래·결제 위험·상담·공식 후보 연결 P0 | `.venv/bin/python -m unittest tests.test_consultation tests.test_trade_settlement_risk tests.test_official_candidate_service tests.test_ui_evidence_state -v` | 62/62 PASS |
| T7 통합 보고서·critic | 전체 unittest 내 실행 | 34/34 PASS |
| Stage 0 source-grounded evidence | 금액·결제일 불일치, 원문 부재·반대 당사자, quantity 오인, textless live image, page recovery, confirmation recheck, override 회귀 | 9/9 PASS |
| dependency | `python -m pip check` | PASS |
| extraction fixture 평가 | `python scripts/evaluate_extraction.py --mode offline` | 17건, pass 82.35%, hallucination 0% |
| 미국·브라질 별도 fixture 평가 | `python scripts/evaluate_extraction.py --mode offline --manifest dataset/country_validation/manifest.jsonl ...` | 8건, fixture field match 100%, 안전 누락 포함 document pass 50%, hallucination 0% |
| 미국·브라질 guarded Live smoke | `python scripts/evaluate_extraction.py --mode live ... --max-cases 2 --confirm-live --run-id ...` | API 성공 2, 실패·timeout 0, 자동 document pass 0/2 |
| country validation 전용 | `python -m unittest tests.test_country_validation_dataset -v` | 12/12 PASS |
| Stage 0 live 합성 PDF | `scripts/live_smoke_test.py samples/demo_net90_contract.pdf --company-role SELLER` | PASS, `SALES_CONTRACT`, 10.14초 |
| regression | `python scripts/run_regression.py` | PASS |
| Streamlit amount_due 방향별 라벨·경고 | `python -m unittest tests.test_ui_evidence_state -v` | 11/11 PASS |
| Streamlit 실제 health | `curl ...:8502/_stcore/health` | HTTP 200, `ok` |
| Import fixture E2E | `scripts/run_decision_demo.py --company-role BUYER` | PASS |
| Export fixture E2E | `scripts/run_decision_demo.py --company-role SELLER` | PASS |
| sibling Stage 1 actual HTTP | `127.0.0.1:8765` health/forecast + main adapter | `HTTP OK`, fallback 없음 |

## T4 국가·무역환경 검증

`2026.07.29-v1` offline snapshot
(`country-environment-2026-07-29`, hash
`095c5e38a88403449214ba899e05d07831f1b2a44932f2ebe2beaa65045fb757`)
을 외부 네트워크 없이 strict 역직렬화했습니다. schema·version·hash 변조,
누락 provenance, 비공식 URL과 lookalike host, 중복 source ID, 국가 불일치,
float·과학표기 소수를 모두 fail closed하는 테스트가 통과했습니다.

동일한 `SELLER / EXPORT / USD / EXISTING / Open Account 90일 /
NONE_CONFIRMED` 입력에서 국가만 변경했습니다.

```text
US: OECD HIGH_INCOME_OECD_UNCLASSIFIED / raw null
    review priority ELEVATED_REVIEW
BR: OECD CLASSIFIED / raw 4
    action PAYMENT_TRANSFER_PROTECTION_REVIEW_REQUIRED
    review priority HIGH_REVIEW
```

우선순위는 국가 신용등급이 아닌 보험·보증·신용장·결제조건 상담 순서입니다.
World Bank는 US 물가의 최신 비결측 관측연도 `2024`와 GDP·경상수지 `2025`를
같은 시점으로 표현하지 않았고, WTO 회원·MFN·TPR 원값도 지급불능 위험으로
변환하지 않았습니다.

`CountryEnvironmentIntegrationTests`는 국가 변경 전후 Stage 1, Stage 2,
Stage 3, runtime Stage 4와 상품 eligibility·approval이 완전히 동일함을
검증했습니다. T4 auxiliary step은 국가 assessment와 안전한 source ID trace만
갱신하고 packet·report를 무효화합니다. legacy packet에서는 T4 필드가
직렬화되지 않고, T4가 있으면 assessment fingerprint가 packet hash에
결속됩니다.

T7 결정론 fallback은 세 축, 공식 URL, 자료기간, 원값 해석과 한계를 분리해
출력합니다. critic 테스트는 브라질 원값 `4`의 자체등급화, 미국 미분류의
`LOW·0·안전` 변환, 0~100 합산, source URL·원값 변조, 국가 신호에 따른
환헤지·Stage 2 현금흐름 변경, 상품 승인 주장을 거부했습니다. Streamlit
AppTest는 정상 US 상태와 지원하지 않는 국가의 `정보 부족` 상태를 모두
렌더링했습니다.

공식 source 확인에만 공개 1차 자료를 사용했고 runtime·테스트에서는 OECD,
World Bank, WTO API나 OpenAI API를 호출하지 않았습니다.

## 미국·브라질 합성 문서 검증

기존 17건 manifest와 regression baseline을 변경하지 않고
`dataset/country_validation`에 미국 4건·브라질 4건을 별도로 생성했습니다.
수입·수출은 각각 4건이며 PDF 4건은 텍스트 레이어가 없는 이미지형, JPG 4건은
사진형입니다.

```text
fixture cases: 8
currency accuracy: 100%
amount exact accuracy: 100%
date exact accuracy: 100%
evidence claim coverage: 100%
hallucination rate: 0%
document pass: 4/8
```

fixture는 label 복사로 evaluator 동작만 검증하므로 위 일치율은 실제 OCR·모델
정확도 주장이 아닙니다. 자동 문서 PASS에서 제외된 4건은 B/L 사건 기준일 부재,
두 번째 분할결제일 부재, 통화 누락, 가려진 결제일 사례입니다. 4번 B/L 사례는
사람이 기준일을 보완할 수 있는 조건부 검토이고, 6·7·8번은 manifest상 의도적
차단 사례입니다.

시각 검수에서 8건의 경고문, 당사자, 국가, 금액·통화와 의도한 가림 범위를 직접
확인했습니다. 최초 생성 사진의 원근 좌표 순서 오류로 90도 회전하던 결함은
수정 후 전건 재생성·재검수했습니다. 반복 생성 byte hash, upload guard, 이미지형
PDF 무텍스트, 정답 schema/evidence, 분할합계, fine-tuning 영구 제외도 자동
테스트로 확인했습니다. 데이터셋 생성 당시에는 OpenAI Live 평가를 실행하지
않았고, 이후 승인된 P1-A Baseline v1/v2에서 별도 immutable run으로 8건씩
실행했습니다.

## P1-A guarded Live Baseline v1/v2

사용자가 승인한 합성 country validation test split 8건을 Baseline v1과 v2로 각각
실행했습니다. 두 run 모두 `gpt-4o-mini` API/structured output 8건 성공,
실패·timeout 0건이었습니다.

| 검증 | Baseline v1 | Baseline v2 |
| --- | ---: | ---: |
| run ID | `baseline-v1-full-20260729-0404-kst` | `baseline-v2-full-20260729-0443-kst` |
| seller_country | 4/8 | 8/8 |
| buyer_country | 3/8 | 8/8 |
| trade_type | 2/8 | 8/8 |
| currency·amount_due·explicit/derived due date | 각 8/8 | 각 8/8 |
| installment 금액·합계 | 6/6·3/3 | 6/6·3/3 |
| event condition·unknown due abstention | 2/2·3/3 | 2/2·3/3 |
| 전체 abstention·hallucination | 30/30·0 | 30/30·0 |
| validation PASS·Stage 2 allowed | 0/8·0/8 | 0/8·0/8 |
| accepted evidence coverage | 0% | 0% |

Model, evaluator, prompt, manifest, extraction schema, evidence·confirmation
policy와 timeout 정책은 동결했습니다. V1/V2의 의도된 차이는 국가 canonicalization
commit `9bdffd9`뿐입니다. seller/buyer 국가와 그 결과인 trade type 개선만 직접
효과로 기록합니다. `document_type` 7/8 → 8/8, 전체 document match 1/8 → 3/8,
token·latency와 법인명 표현 변화는 LLM 재호출 변동 가능성이 있어 인과 효과로
주장하지 않습니다.

8건 모두 이미지형 PDF 또는 JPG이고 독립적으로 검증 가능한 텍스트 레이어가
없습니다. 모델 인용을 자동 수용하지 않아 `OCR_REQUIRED`,
`EVIDENCE_UNVERIFIABLE`, `MISSING_CORE_EVIDENCE`와 사용자 확인 gate로 전부
Stage 2 전달을 차단했습니다. Evidence coverage 0%는 OCR 정확도 0%가 아니라
“독립 검증되어 자동 수용된 evidence 없음”입니다.

금액·통화·모든 날짜·payment terms·installments는 국가 정규화 전후 사례별로
동일했습니다. 통화 누락과 사건 기준일은 추측하지 않았습니다. 남은 명확한 오류는
`us_import_split_scan_001` contract date가 label보다 하루 늦은 1건입니다.

V2 input/output token은 310,495/4,660이고 평균 latency는 8.836초입니다. cached
input token을 수집하지 않아 실제 비용은 `UNKNOWN`이며, 비캐시 가정 사후 상한
USD 0.04937025를 실제 청구액으로 표현하지 않습니다.

원본 Run ID, 전체 hash, 직접 비교, 보안 경계와 주장 한계는
`docs/LIVE_BENCHMARK_RESULTS.md`와 sanitized
`docs/evidence/country_benchmark_v1_v2_summary.json`에 기록했습니다. Raw response,
전체 prompt·payload·문서와 API key는 제출 문서에 저장하지 않았습니다.

## Golden text-layer 무역계약 데모

`scripts/generate_golden_trade_demo.py`가 2페이지 영문 합성 수출계약 PDF,
`TradeDocumentExtraction` expected data와 계약 밖 사용자 입력을 결정론적으로
생성합니다.

```text
document: dataset/golden_demo/golden_export_contract.pdf
seller/buyer: Republic of Korea (KR) / Brazil (BR)
normalized countries: KR / BR
trade type: EXPORT
currency/amount: USD / 100000.00
installments: 20000.00 + 80000.00 = 100000.00
contract/shipment/balance due: 2026-07-29 / 2026-08-05 / 2026-08-20
text layer: 2/2 pages
expected evidence: 16 exact quotes on declared pages
```

모든 페이지에 `SYNTHETIC SAMPLE - NOT LEGALLY BINDING`을 넣고 실제 주소·계좌·
등록번호·로고·서명·도장을 넣지 않았습니다. 신용장·보증은 현재 extraction schema에
임의 필드를 추가하지 않고 별도 document fact에 보존했습니다. 거래처 관계,
신용보험, 헤지, 현금과 신용한도는 계약서 사실이 아니라 사용자 입력으로 분리했습니다.

Golden 전용 14개 API-free 테스트는 다음을 검증했습니다.

- 반복 생성 PDF/JSON byte hash 동일
- pypdf strict parsing과 비어 있지 않은 텍스트 레이어
- 모든 evidence quote의 실제 페이지 존재
- raw 국가 표현·normalized 값·normalization method 보존
- KR/BR에서 EXPORT 결정론 판정
- 통화·금액·날짜·분할합계 불변
- 사용자 확인 후 `validation_pass=true`, `stage2_allowed=true`
- 기존 trade-risk domain에서 `ELEVATED_REVIEW`
- 현재 Stage 1 fixture의 21거래일 종료일 2026-08-25 안에 잔금일 존재
- 기존 Stage 2 계산으로 기준 수취 140,000,000원, -5% 수취 133,000,000원,
  수취 감소 7,000,000원, buffer shortfall 2,000,000원

Golden 자료 생성 시점의 Expected data와 14/14 결과는 모델 정확도가 아니라
API-free 성공 경로 검증입니다.

### Golden 1건 Live evidence 실패와 API-free 복구 검증

이후 별도 승인된 `gpt-4o-mini` 단일 Live 호출에서 핵심 값과 installment 합계는
정답과 일치했지만 다음 evidence 오류로 안전하게 차단됐습니다.

```text
EVIDENCE_VALUE_MISMATCH: amount_due
EVIDENCE_NOT_IN_SOURCE: explicit_due_date
validation_pass: false
stage2_allowed: false
```

`amount_due`는 분할결제 합계 USD 100,000과 같은 계약상 미결제 예정 노출액인데
모델 evidence가 canonical 금액을 뒷받침하지 못했습니다. 결제일 값
`2026-08-20`은 맞지만 모델
quote가 PDF의 실제 `20 August 2026` 표현과 일치하지 않았습니다. 단순 사용자
확인으로 두 오류를 제거하지 않았고, USD 80,000 잔금 조항을 계약상 미결제 예정
노출액 USD 100,000의 evidence로 사용하지 않습니다.

수정된 API-free 경로는 먼저 잘못된 모델 evidence를 같은 사유로 폐기한 뒤 실제
텍스트 레이어에서 다음 원문을 복구합니다.

```text
page 1: The total Contract Price is one hundred thousand United States dollars (USD 100,000).
page 2: The remaining eighty percent (80%), equal to USD 80,000, shall be paid by T/T remittance on or before 20 August 2026 (Payment Due Date).
```

금액은 `Decimal("100000.00")`, 날짜는 `date(2026, 8, 20)`과 대조하며 canonical
값을 source quote로 만들지 않습니다. 다른 의미의 동일 금액, 복수의 강한 지급일,
통화 충돌, 값 불일치와 textless 문서는 계속 차단합니다. 신규
`tests.test_source_evidence_recovery` 18개가 이 정책과 Golden Live-like 실패
재현 후 사용자 확인 경로를 API 없이 검증합니다.

이 결과는 코드 수정 후 API-free 검증입니다. 수정된 코드로 Golden Live를 다시
실행하기 전에는 end-to-end 추출 성공으로 주장하지 않습니다.

## Stage 0 매매계약 회귀

`tests/fixtures/kbfx_sales_contract_extraction.json`을 외부 API 없이 실행했습니다.

```text
seller_country: United States -> US
buyer_country: Republic of Korea -> KR
company_role: BUYER
trade_type: UNKNOWN -> IMPORT
issue_date: YYYY-MM-DD -> null
contract_date + Net 90 calendar days: 2026-10-25
currency evidence: amount_due 실제 원문 "USD 100,000.00"에서 연결
확인 전 Stage 2: 차단
5필드 확인 후 Stage 2: IMPORT / USD / 100000.00 / 2026-10-25
```

기존 `COMPANY_COUNTRY_ROLE_MISMATCH`, `INVALID_PARTY_COUNTRY`,
`MISSING_REQUIRED_FIELD trade_type`, `MISSING_CORE_EVIDENCE currency`는 이
fixture에서 재현되지 않습니다.

저장소의 이미지형 합성 `samples/demo_net90_contract.pdf`를 실제 문서 추출 API로
검증했습니다. 첫 재현에서 모델은 `buyer_country=CA`와 `(CA)` 원문을 반환했지만
validator의 국가 evidence 별칭표에 캐나다가 없어
`MISSING_CORE_EVIDENCE:buyer_country`로 오판했습니다. 지원 국가 별칭과 대문자 ISO
독립 토큰 판정을 보강한 뒤 같은 문서가 다음처럼 통과했습니다.

```text
PASS document_type=SALES_CONTRACT validation_pass=True
latency_seconds=10.1423285
```

이는 합성 문서 한 건의 smoke test이며 실제 고객 문서군의 OCR·추출 정확도
benchmark를 뜻하지 않습니다.

## Stage 1 검증

저장소 fixture:

```text
direction: USD_KRW_DOWN
up/down score: 0.288 / 0.712
calibrated probability: false
maximum rise q50/q75/q90: 0.015 / 0.026 / 0.035
maximum fall q50/q75/q90: 0.010 / 0.021 / 0.036
```

실행 중이던 sibling HTTP 서버의 2026-07-27 출력도 메인 Python adapter로 직접
파싱했습니다.

```text
provider health: HTTP OK
direction: USD_KRW_DOWN
up/down score: 0.041 / 0.959
calibrated probability: false
maximum rise q50/q75/q90: 0.014 / 0.022 / 0.035
maximum fall q50/q75/q90: 0.011 / 0.025 / 0.041
```

실제 출력은 새로 생성되면 fixture와 달라질 수 있습니다. 두 결과 모두 방향 점수를
발생확률로 사용하지 않았고, 뉴스는 숫자 계산에 미반영했습니다.

자동 테스트 범위:

- raw schema mismatch, q 순서, path return 상한, score 합
- stale market data, partial fallback, failed series, news query degraded
- HTTP success/timeout/invalid JSON, response/fallback provenance
- file/mock mode, remote URL/host 제한
- 수동 spot 확인 gate, KoreaExim parsing, JPY(100) 정규화
- 정확한 model/fixed rate, horizon mismatch
- 수입 v36 상승·수출 v34 하락 방향

## 대표 수입 결과

```text
수입대금: USD 100,000
결제용 보유외화: USD 20,000
열린 노출: USD 80,000
기준환율: 1,400
기준 필요액: 112,000,000원
+5% 환율: 1,470
+5% 필요액: 117,600,000원
추가비용: 5,600,000원
현재현금/유입/비용: 130,000,000 / 40,000,000 / 45,000,000원
결제 후 현금: 7,400,000원
운영자금 부족: 2,600,000원
대출한도 후 지급부족: 0원
```

`LIQUIDITY_BUFFER_RISK`이며 `PAYMENT_CAPACITY_RISK`가 아님을 검증했습니다.

## 대표 수출 결과

USD 100,000 수취 거래에서 기준 수취액 140,000,000원, -5% 스트레스 수취액
133,000,000원, 원화 수취 감소 7,000,000원을 검증했습니다.
`FX_RECEIPT_RISK`가 발생하고 수입 `FX_COST_RISK`와 구분됩니다.

두 대표 사례는 90일 결제이므로 Stage 1 모델 분위수가 계산에서 제외되고
`HORIZON_MISMATCH`가 보고서까지 전달됩니다.

## 거래·결제 위험 검증

수입 선지급·계약이행 위험과 수출대금 회수 위험을 기존 환율·유동성 계산과 분리해
검증했습니다.

```text
수입 데모: 신규 거래처 + 30% 선지급 + 보호수단 없음
결과: IMPORT_PREPAYMENT_PERFORMANCE_RISK / HIGH_REVIEW

수출 데모: 신규 거래처 + Open Account 90일 + 보호수단 없음
결과: EXPORT_RECEIVABLE_COLLECTION_RISK / HIGH_REVIEW
```

자동 테스트 범위:

- 선지급 비율 0~1 Decimal 문자열 계약과 화면 % 단위 분리
- 미확인 선지급과 확인된 0% 구분, 범위·과학표기·float 거부
- 전액 선지급과 잔여대금 결제방식·기간의 교차 검증
- `UNKNOWN`, `NONE_CONFIRMED`, 보호수단 상세 상태 구분
- 수입용 보증과 수출보험·지급보증의 거래방향별 적용 제한
- 적용범위 미확인 보호수단의 감경 금지와 확인된 보호수단의 제한적 감경
- Open Account, D/P, D/A, 종류 미확인 추심, 신용장 조건의 구분
- 사건 기준 결제조건을 임의의 일수로 변환하지 않음
- 89일과 공개된 MVP 90일 장기조건 검토 경계
- confirmation fingerprint 결정성 및 변조 거부
- 문서 변경 시 위험 snapshot 폐기, 위험조건 변경 시 Stage 1~3 결과 보존
- 수입·수출 대표 데모와 Streamlit 렌더링
- 수입 선지급 위험 → 선지급 보호수단 상담·질문·준비서류 매핑
- 수출 회수 위험 → 수출채권 보호 상담·질문·준비서류 매핑
- 신용장 존재를 위험 제거로 처리하지 않고 상세조건 검토로 연결
- `UNKNOWN`을 별도 정보 확인 topic과 packet 미확인 정보로 연결
- 거래위험 fingerprint 변경 시 상담 packet input hash 변경
- 상담자료에 한국어 위험 유형·우선도·근거와 공식등급이 아니라는 고지 포함
- 거래위험이 없는 기존 packet·topic 직렬화에는 신규 optional 필드를 출력하지 않음

이 결과는 숫자 신용점수, 부도확률, 공식 심사등급이 아닙니다. 국가위험, 거래처
재무정보, 신용장 발행은행·확인 여부·서류불일치, 보험 약관·보증 범위는 이번 P0에서
평가하지 않았습니다.

## 공식 출처 후보 연결 검증

기존 Stage 4 검색 결과와 별도로 사용자용 공식 후보 shortlist를 최대 3개로
제한했습니다.

```text
수입 데모 첫 후보:
K-SURE 수입보험(수입자용)
연결 범주: IMPORT_ADVANCE_PAYMENT_PROTECTION
공식 자료 확인일: 2026-07-29

수출 데모 첫 후보:
K-SURE 단기수출보험
연결 범주: EXPORT_RECEIVABLE_PROTECTION
공식 자료 확인일: 2026-07-29
```

자동 테스트 범위:

- 상담 범주 기반 검색어와 후보 순서의 결정성
- 공식 HTTPS allowlist, 거래방향과 검증상태 재확인
- 수입 선지급 보호와 수출채권 보호의 방향별 공식 제도 연결
- shortlist 모델과 서비스 모두 최대 3개 제한
- 직접 매칭이 없을 때 빈 결과·미매칭 범주 반환, 상품 생성 금지
- 비공식 URL 후보 제거
- 모든 후보의 자격 `unknown`, 승인 `consultation_required` 유지
- 후보 product ID·공식 URL·자료 확인일·매칭 범주의 상담 packet hash 반영
- Streamlit 기본 화면과 상담 패킷에는 shortlist만 표시

K-SURE 공식 페이지는 제도의 위험보호 구조를 확인하는 근거이며, 현재 거래의
대상 여부·인수·책임금액·보험료를 확정하는 근거로 사용하지 않았습니다.

## Stage 3·보고서 검증

- 5%p grid와 비율 합 1
- 안정성·균형·비용 우선 후보
- q90와 고정 ±10% 손실, 최저 현금, 대출 후 부족
- 비용·위험계수·최대 forward 가정 공개
- 제약 해가 없으면 `NO_FEASIBLE_CANDIDATE`
- 보고서 JSON에서 문서 `source_text`와 confirmation 원본값 제외
- 보고서 숫자·JSON path 일치
- q90 확률 오용, 미보정 방향 점수 확률 오용, horizon 외삽, 뉴스 숫자 반영,
  비공식 상품 근거를 critic이 차단
- 상담 패킷이 있으면 거래·결제 위험·금융 대응·공식 후보를
  `consultation.*` 근거로만 인용
- Stage 4 원시 후보명·기관·URL은 최종 보고서 LLM bundle에서 제외
- 수입 선지급·계약이행 위험과 수출대금 회수 위험을 방향별로 최종 보고서에 표시
- shortlist 최대 3개만 표시하고 빈 shortlist에서는 LLM 상품 생성 호출을 차단
- shortlist 밖 Stage 4 인용, 상품명·기관명·URL 변조, 자격·승인 확정을 critic이 차단
- 거래위험 우선도와 금융 대응 제목을 인용한 구조화 값과 다르게 쓰는 경우 차단
- 공식 심사등급·부도확률·보험 인수판단 주장과 결제위험→환헤지 비율 변경을 차단
- LLM API 없음/실패/critic 재실패 시 결정론 template

## 실패와 해결 기록

### macOS compile cache

```text
실행 명령: python -m compileall .
결과: 실패
오류 메시지: sandbox 밖 Python cache 경로 PermissionError
직접 원인: 기본 pycache가 허용되지 않은 macOS cache 경로를 사용
근본 원인: 실행 sandbox 파일쓰기 제한
수정 필요 여부: 코드 수정 불필요
해결: PYTHONPYCACHEPREFIX=/tmp/kbaiagent_compile_cache로 재실행 PASS
```

### Streamlit port bind

```text
실행 명령: python -m streamlit run app.py --server.port 8502
결과: sandbox 안에서 PermissionError
직접 원인: local port bind 권한 제한
해결: 승인된 로컬 실행으로 재시도, health `ok`
```

### Stage 1 server start

```text
실행 명령: zsh scripts/serve_web_forecast.sh
결과: Address already in use
직접 원인: 127.0.0.1:8765에 팀 서버가 이미 실행 중
해결: 기존 사용자 프로세스를 종료하지 않고 health와 forecast를 읽어 통합 검증
```

### 최초 최종 gate

```text
실행 명령: python scripts/verify.py
결과: unit test는 PASS, README 문서 링크 2개 누락으로 gate 실패
해결: STAGE1_INTEGRATION·SPOT_PROVIDER_SETUP 링크 추가 후 재실행 PASS
```

## 미실행

- 미국·브라질 합성 세트 전체 8건 Live baseline: 두 번째 승인 필요
- 허가된 실제 고객 문서군 OpenAI 추출 benchmark
- 실제 OpenAI LLM 보고서 생성
- 한국수출입은행 live 호출: 자격증명 없음
- 공식 web 상품 검색 live: 기본 비활성, 자격증명 없음
- Windows launcher: 현재 macOS 환경에서 미검증

위 항목은 구현 완료나 live 품질 검증으로 표시하지 않습니다.
