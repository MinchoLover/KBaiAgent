# Validation Report

검증일: 2026-07-28 KST
환경: macOS, Python 3.9.6, Streamlit 1.50.0, Pydantic 2.13.4

## 최종 결과

| 검증 | 명령 | 결과 |
| --- | --- | --- |
| 한 명령 release gate | `python scripts/verify.py` | PASS |
| compile | `PYTHONPYCACHEPREFIX=/tmp/kbaiagent_compile_cache python -m compileall ...` | PASS |
| 전체 unit/integration/E2E | `python -m unittest discover -s tests -v` | 273/273 PASS |
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
