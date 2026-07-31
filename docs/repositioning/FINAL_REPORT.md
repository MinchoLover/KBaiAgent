# KB AI Challenge MVP 재포지셔닝 최종 보고서

> 2026-07-27 통합 보강: 팀 `kb_macro_ai`의 실제
> `krw_forecast_web_v1`을 HTTP/file/mock adapter로 연결하고 별도 Spot provider,
> 21거래일 horizon gate, 수입 v36/수출 v34 scenario, 제약형 Stage 3와 시장정책
> report critic을 추가했습니다. 2026-07-29 P1-A 기준 API-free 394개가 PASS했고,
> 미국·브라질 합성문서 Live smoke 2건을 별도 run으로 실행했습니다. 실제
> 고객문서 품질이나 OCR 일반 성능은 검증하지 않았습니다. 최신 실행·제한은
> `docs/VALIDATION_REPORT.md`, `docs/STAGE1_INTEGRATION.md`,
> `docs/LIMITATIONS.md`, `docs/LIVE_BENCHMARK_RESULTS.md`가 우선합니다.
> 아래 1~6절의 커밋·기준선 설명은 이전
> 재포지셔닝 작업 당시 기록입니다.

## 1. 기준 브랜치와 커밋

- 변경 전 브랜치: `main`
- 변경 전 커밋: `68448292c34e97c9df53e69220df34fc31813d59`
- 구현 브랜치: `feature/reposition-trade-consultation`
- 기준선 문서 커밋: `aef75fa`
- 결정론 위험·상담 흐름 커밋: `3a360c6`
- Streamlit 상담 패킷 UI 커밋: `1d3a252`
- 원격 저장소: `https://github.com/MinchoLover/KBaiAgent.git`

변경 전 작업 트리는 clean이었고, `main`에서 동일 목적 브랜치가 없는 것을 확인한 뒤
기능 브랜치를 만들었습니다.

## 2. 변경 전 실행 상태

변경 전에도 Python 3.9·Streamlit 앱, 문서 추출, 사용자 확인, Stage 1 시나리오,
`Decimal` Stage 2 계산, Stage 3 헤지 grid, Stage 4 공식자료 후보와 Stage 5
fallback 보고서가 연결되어 있었습니다. API 없이 175개 `unittest`가 통과했고
`python scripts/verify.py`도 통과했습니다.

부족했던 핵심은 다음 세 가지였습니다.

1. 거래 방향은 계산 전에 별도 사용자 확인 상태가 없었습니다.
2. Stage 2 뒤에 구조화된 위험 코드와 위험 근거가 없었습니다.
3. 위험을 일반 금융상담 범주, 질문·서류와 연결하는 독립 상담 패킷이 없었습니다.

따라서 계산 엔진을 재작성하지 않고 기존 결과 뒤에 작은 결정론 서비스 계층을
추가하는 방식을 선택했습니다. 자세한 기준선은
`docs/repositioning/CURRENT_STATE.md`에 있습니다.

## 3. 최종 제품 포지셔닝

> 수출입 계약서 또는 거래정보를 구조화하고, 환율 변화가 기업의 실제 결제액과
> 운영자금에 미치는 영향을 결정론적으로 계산한 뒤, 검토할 외환·무역금융 대응과
> KB 상담 준비사항을 생성하는 수출입 금융 의사결정 지원 에이전트

주 사용자는 수출입 기업 재무·자금 담당자이고, KB 담당자는 기업이 공유한 상담
패킷을 검토하는 후속 사용자입니다. 실제 은행 직원용 다중 고객 관리 화면은
미구현이므로 구현된 것처럼 설명하지 않습니다.

## 4. 재사용한 기존 기능

- `schemas.py`, `src/document_intake/`: OpenAI Structured Outputs 문서 추출과 evidence
- `src/document_intake/confirmation.py`, `src/workflow/gates.py`: 사용자 확인 gate
- `src/stage1/`: 수동 스트레스, 외부 JSON/REST adapter, 단위 정규화와 fallback
- `src/stage2/`: 보유 외화·자연상계·기존 헤지·날짜별 현금흐름 `Decimal` 계산
- `src/stage3/`: 공개된 가정 기반 헤지 조합 프로토타입
- `src/stage4/`: 공식 출처 allowlist와 오프라인 스냅샷
- `src/stage5/`: LLM 설명, critic, 1회 수정과 결정론 fallback
- `src/workflow/`: Stage 순서, 실패 상태와 payload 없는 trace
- 기존 Streamlit CSS, 입력 컴포넌트, 다운로드와 AppTest

Stage 1 팀 계약과 Stage 2 공개 입력·결과 DTO는 변경하지 않았습니다.

## 5. 새로 구현한 기능

- 거래 방향을 포함한 네 핵심 필드 사용자 확인
- `FX_COST_RISK`, `FX_RECEIPT_RISK`, `LOSS_LIMIT_EXCEEDED`,
  `LIQUIDITY_BUFFER_RISK`, `NEGATIVE_CASH_RISK`,
  `PAYMENT_CAPACITY_RISK`, `TIMING_MISMATCH_RISK`,
  `DOCUMENT_INFORMATION_GAP` 결정론 분류
- 각 위험의 trigger, threshold, scenario ID와 explanation data
- 위험 코드·수입/수출 방향 기반 일반 상담 범주와 중복 제거
- `REQUIRES_BANK_REVIEW`, `human_review_required=true` 안전 상태
- 계산 버전·입력 hash·환율 기준시각·시나리오·문서 hash·사용자 확인 필드가 있는
  JSON·Markdown KB 상담 패킷
- 수입·수출 API-free 대표 데모와 CLI
- Stage 2 직후 위험 원인, 금융 대응 후보와 상담 패킷까지 열리는 Streamlit 흐름
- 원클릭 데모 입력값과 표시된 계산 입력의 일치
- Stage 3·4를 하지 않아도 기본 상담 패킷을 받을 수 있는 최종 탭

## 6. 변경 파일 목록

### 기준선·계획

- `docs/repositioning/CURRENT_STATE.md`
- `docs/repositioning/IMPLEMENTATION_PLAN.md`

### 공용 확인 계약

- `schemas.py`
- `validators.py`
- `src/document_intake/confirmation.py`
- `src/workflow/gates.py`

### 위험·상담·패킷

- `src/domain/consultation_models.py`
- `src/consultation/__init__.py`
- `src/consultation/risk_classifier.py`
- `src/consultation/response_mapping.py`
- `src/consultation/packet.py`
- `src/application/consultation_service.py`

### 데모·UI·검증

- `src/application/demo_service.py`
- `src/demo.py`, 기존 호환 파일 `src/demo 2.py`
- `scripts/run_decision_demo.py`
- `app.py`
- `src/ui/components.py`
- `src/ui/state.py`
- `scripts/verify.py`
- `tests/test_consultation.py`
- `tests/test_schemas_validators.py`
- `tests/test_security_eval_demo.py`

### 문서

- `README.md`
- `docs/PROGRESS.md`
- `docs/DECISIONS.md`
- `docs/AI_LOG.md`
- `docs/repositioning/TEAM_POSITIONING.md`
- `docs/repositioning/FINAL_REPORT.md`

## 7. 대표 수입기업 실행 결과

실행 명령:

```bash
python scripts/run_decision_demo.py --company-role BUYER --format summary
```

| 항목 | 결과 |
| --- | ---: |
| 총 수입대금 | USD 100,000.00 |
| 결제에 사용할 보유외화 | USD 20,000.00 |
| 열린 환노출 | USD 80,000.00 |
| 기준환율 | 1,400 KRW/USD |
| 기준 원화 필요액 | 112,000,000.00원 |
| +5% 스트레스 환율 | 1,470 KRW/USD |
| 스트레스 원화 필요액 | 117,600,000.00원 |
| 기준 대비 추가 비용 | 5,600,000.00원 |
| 확정 유입 40,000,000원·비용 45,000,000원 반영 후 현금 | 7,400,000.00원 |
| 최소 운영자금 부족 | 2,600,000.00원 |
| 대출한도 반영 후 지급 부족 | 0.00원 |

위험 코드는 `FX_COST_RISK`, `LOSS_LIMIT_EXCEEDED`,
`LIQUIDITY_BUFFER_RISK`입니다. `PAYMENT_CAPACITY_RISK`는 발생하지 않습니다.
대응 후보는 환율 관리 상담, 보유 외화 활용 검토, 수입 결제자금 상담입니다.

## 8. 대표 수출기업 실행 결과

실행 명령:

```bash
python scripts/run_decision_demo.py --company-role SELLER --format summary
```

| 항목 | 결과 |
| --- | ---: |
| 총 수출대금·열린 환노출 | USD 100,000.00 |
| 기준환율 | 1,400 KRW/USD |
| 기준 원화 수취액 | 140,000,000.00원 |
| -5% 스트레스 환율 | 1,330 KRW/USD |
| 스트레스 원화 수취액 | 133,000,000.00원 |
| 기준 대비 원화 수취 감소 | 7,000,000.00원 |
| 예정 비용 반영 후 현금 | 8,000,000.00원 |
| 최소 운영자금 부족 | 2,000,000.00원 |
| 대출한도 반영 후 부족 | 0.00원 |

위험 코드는 `FX_RECEIPT_RISK`, `LOSS_LIMIT_EXCEEDED`,
`LIQUIDITY_BUFFER_RISK`입니다. 수입의 비용 증가와 반대 방향임을 독립 테스트로
고정했습니다.

## 9. 테스트 명령과 실제 결과

| 검증 | 실행 명령 | 실제 결과 |
| --- | --- | --- |
| Python compile | `PYTHONPYCACHEPREFIX=/private/tmp/kbai-pycache .venv/bin/python -m compileall -q -x '(^|/)(\.venv|\.git|__pycache__)(/|$)' .` | 성공 |
| 전체 단위·통합·UI | `.venv/bin/python -m unittest discover -s tests -v` | 274개 성공, 0개 실패 |
| 오프라인 추출 계약 | `.venv/bin/python scripts/evaluate_extraction.py --mode offline` | 17건, pass rate 82.35%, hallucination 0.00% |
| 회귀 기준 | `.venv/bin/python scripts/run_regression.py` | 성공 |
| 의존성 | `.venv/bin/python -m pip check` | broken requirement 없음 |
| Streamlit E2E | 전체 suite의 `AppTest` | 수입·수출 원클릭 모두 예외 0 |
| 실제 서버 health | Streamlit 8502 실행 후 `curl .../_stcore/health` | `ok` |
| 저장소 검증 | `.venv/bin/python scripts/verify.py` | 최종 실행 결과: 성공 |

오프라인 추출의 82.35%는 fixture·label 계약 평가이며 실제 LLM 품질 점수로 주장하지
않습니다. 합성 PDF 한 건의 OpenAI live smoke test는 통과했지만, 실제 고객 문서군의
OCR·추출 정확도 benchmark는 아직 수행하지 않았습니다.

실패 기록 1:

```text
실행 명령:
python -m compileall -q -x ... .
결과:
실패 후 대체 명령 성공
오류 메시지:
macOS Python pycache 경로 PermissionError
직접 원인:
기본 PYTHONPYCACHEPREFIX가 샌드박스 밖 ~/Library/Caches를 가리킴
근본 원인:
관리형 실행 환경의 파일쓰기 제한이며 소스 문법 오류가 아님
수정 필요 여부:
아니오. 검증 명령에 /private/tmp pycache 경로를 명시해 성공
```

실패 기록 2:

```text
실행 명령:
.venv/bin/python -m streamlit run app.py --server.headless true --server.port 8502
결과:
샌드박스 내부 실패, 허용된 로컬 실행에서 성공
오류 메시지:
PermissionError: socket bind operation not permitted
직접 원인:
샌드박스가 로컬 포트 바인딩을 차단
근본 원인:
실행 환경 권한 제한이며 앱 시작 오류가 아님
수정 필요 여부:
아니오. 동일 명령으로 서버 기동 후 health endpoint `ok` 확인
```

`pytest -q`는 저장소 의존성에 pytest가 없어 변경 전 기준선에서 실행 불가였습니다.
새 테스트 프레임워크를 추가하지 않고 기존 `unittest`를 유지했습니다.

## 10. 오프라인 fallback

다음 구성은 OpenAI, 환율 API, Stage 1 서버 없이 동작합니다.

- 가상 수입·수출 문서 fixture와 사용자 확인 완료 상태
- 고정 기준 1,400원 및 수입 +5%·수출 -5% 스트레스
- 기존 Stage 2 `Decimal` 계산
- 결정론 위험 코드와 상담 mapping
- JSON·Markdown 상담 패킷
- 오프라인 공식자료 스냅샷과 결정론 확장 보고서

오프라인 실행 명령:

```bash
python scripts/run_decision_demo.py --company-role BUYER --format summary
python scripts/run_decision_demo.py --company-role SELLER --format summary
python -m streamlit run app.py
```

## 11. 현재 완성된 E2E 흐름

```text
가상 또는 실제 거래문서
→ AI 구조화 또는 fixture
→ 회사 역할·거래 방향·통화·금액·결제일 사용자 확인
→ 수동/외부 환율 시나리오 정규화
→ 기업 현금·외화·헤지·예정 입출금
→ Stage 2 환노출·날짜별 현금흐름
→ 결정론 위험 코드·근거
→ 규칙 기반 일반 상담 범주
→ JSON·Markdown KB 상담 준비 패킷
→ 선택: 헤지 시뮬레이션·공식자료·확장 설명 보고서
```

Streamlit과 CLI가 같은 `run_decision_support_demo` 및 서비스 계층을 사용합니다.

## 12. 남은 P0 문제

API-free 제출 데모를 막는 확인된 P0 문제는 없습니다.

다만 실제 고객문서 OpenAI 품질은 미확인이고, 합성문서 2건 smoke를 실제 기업
문서 품질로 일반화할 수 없습니다. 이 상태를 “완료”로 과장하지 않고
`제한된 합성 검증`·`추가 승인 필요`로 표시합니다. 공용 기업 현금 필드의
`KNOWN/UNKNOWN/USER_ESTIMATE` 상태는 권장 모델이지만 현재 DTO에는 미구현이며,
P1에서 하위 호환 방식으로 추가해야 합니다.

## 13. P1 개선사항

1. 승인된 가상/비식별 실제 문서로 live 추출 정확도와 비용·지연 baseline 수립
2. 현금·한도·헤지 입력의 `KNOWN`, `UNKNOWN`, `USER_ESTIMATE` 상태
3. 은행 담당자가 패킷을 읽는 별도 read-only advisor view
4. Stage 3의 가상 비용률을 실제 견적 adapter와 분리하고 프로토타입 배지 강화
5. 공식자료 snapshot의 정기 갱신·만료 운영 절차
6. GitHub Actions에서 Python 3.9 검증과 secret scan 자동화

## 14. 미구현 기능

- 환율 예측 모델, 뉴스 감성분석과 확률 시나리오 생성
- KB 내부 상품·고객·한도·심사 API
- 상품 적격성, 대출 승인, 헤지 실행과 자동 주문
- 운영용 인증·권한, 다중 기업 데이터 분리, 상담 이력 DB
- 운영용 악성파일 검사, 작업 queue, 관측성, 클라우드 배포
- PDF 상담 패킷

위 기능은 현재 발표에서 동작한다고 주장하지 않습니다.

## 15. 금융 안전성 검토

- 금융 숫자는 Stage 2 `Decimal` 코드만 계산합니다.
- 수입 환율 상승과 수출 환율 하락의 위험 방향을 각각 검증했습니다.
- 보유 외화, 동일통화 흐름, 기존 헤지를 열린 노출에서 분리 반영합니다.
- `buffer_shortfall`, 현금 적자, `payment_gap`을 독립 표시합니다.
- 음수 거래금액, 비양수·비유한 환율, 통화 불일치와 잘못된 날짜를 차단하는 기존
  테스트를 유지합니다.
- 스트레스 시나리오를 예측 확률로 표시하지 않습니다.
- 상담 mapping은 상품 가입·승인·최적 비율을 확정하지 않습니다.
- 공식 근거 없는 상품명을 생성하지 않습니다.
- 상담 패킷 숫자는 Stage 2 결과에서 직접 가져오며 LLM이 재생성하지 않습니다.
- 문서 원문·API 키·금융 payload를 workflow trace에 기록하지 않습니다.

## 16. 팀 회의에서 설명할 핵심 문장

“우리가 새 환율 예측기를 만든 게 아니라, 기존의 검증된 계산 엔진 앞에는 문서 확인을,
뒤에는 위험 원인과 상담 준비를 붙였습니다. 그래서 환율 숫자를 원화로 바꾸는 데서
끝나지 않고, 이 기업이 운영자금 기준을 지키는지와 KB에 무엇을 물어볼지를 한 흐름에서
보여줍니다. 숫자는 모두 일반 코드가 계산하고 AI는 문서 이해와 설명만 맡습니다.”

## 17. 3분 데모 실행 순서

1. `수입기업 대표 데모`를 클릭하고 가상 데이터임을 먼저 밝힙니다.
2. `문서 확인`에서 방향·USD 100,000·결제일을 사람이 확인한 상태를 보여줍니다.
3. `위험 진단`의 계산 근거에서 1,400원과 +5% 1,470원이 예측이 아닌
   스트레스임을 설명합니다.
4. 열린 노출 USD 80,000, 기준 1억 1,200만 원, 추가 비용 560만 원을 보여줍니다.
5. 결제 후 현금 740만 원, 운영자금 부족 260만 원, 지급 부족 0원을 비교합니다.
6. 운영자금 방어선 미달 근거와 `대응안 비교`의 세 관점을 보여줍니다.
7. `상담자료`에서 질문·서류를 보여주고 Markdown을 내려받습니다. 계산 버전과
   입력 hash는 개발·연동용 데이터에서 확인합니다.
8. 마지막 10초에 수출 데모를 눌러 환율 하락 시 수취 감소 700만 원과
   사용자용 위험 설명을 보여줍니다.
