# Validation Report

검증일: 2026-07-28 KST
환경: macOS, Python 3.9.6, Streamlit 1.50.0, Pydantic 2.13.4

## 최종 결과

| 검증 | 명령 | 결과 |
| --- | --- | --- |
| 한 명령 release gate | `python scripts/verify.py` | PASS |
| compile | `PYTHONPYCACHEPREFIX=/tmp/kbaiagent_compile_cache python -m compileall ...` | PASS |
| 전체 unit/integration/E2E | `python -m unittest discover -s tests -v` | 320/320 PASS |
| 거래·결제 위험·상담·공식 후보 연결 P0 | `python -m unittest tests.test_consultation tests.test_trade_settlement_risk tests.test_official_candidate_service tests.test_ui_evidence_state -v` | 58/58 PASS |
| Stage 0 source-grounded evidence | 금액·결제일 불일치, 원문 부재·반대 당사자, quantity 오인, textless live image, page recovery, confirmation recheck, override 회귀 | 9/9 PASS |
| dependency | `python -m pip check` | PASS |
| extraction fixture 평가 | `python scripts/evaluate_extraction.py --mode offline` | 17건, pass 82.35%, hallucination 0% |
| Stage 0 live 합성 PDF | `scripts/live_smoke_test.py samples/demo_net90_contract.pdf --company-role SELLER` | PASS, `SALES_CONTRACT`, 10.14초 |
| regression | `python scripts/run_regression.py` | PASS |
| Streamlit AppTest | 전체 unittest 내 실행 | PASS |
| Streamlit 실제 health | `curl ...:8502/_stcore/health` | HTTP 200, `ok` |
| Import fixture E2E | `scripts/run_decision_demo.py --company-role BUYER` | PASS |
| Export fixture E2E | `scripts/run_decision_demo.py --company-role SELLER` | PASS |
| sibling Stage 1 actual HTTP | `127.0.0.1:8765` health/forecast + main adapter | `HTTP OK`, fallback 없음 |

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

- 허가된 실제 고객 문서군 OpenAI 추출 benchmark
- 실제 OpenAI LLM 보고서 생성
- 한국수출입은행 live 호출: 자격증명 없음
- 공식 web 상품 검색 live: 기본 비활성, 자격증명 없음
- Windows launcher: 현재 macOS 환경에서 미검증

위 항목은 구현 완료나 live 품질 검증으로 표시하지 않습니다.
