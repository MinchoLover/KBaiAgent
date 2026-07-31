# Integration Readiness 운영 점검

## 목적

발표자와 운영자가 환율 예측 경로와 `kb_macro_ai` 외부 헤지 참고 경로를 한 번에
점검하는 API-free 상태 화면이다. 점검 결과는 금융 입력이나 Stage 1~5 결과를
수정하지 않는다.

```text
Settings
├─ Stage 1 provider health + normalized forecast quality
├─ Spot provider 설정/실제 사용 source
└─ kb_macro_ai flag/mode
   ├─ producer commit + tracked worktree
   ├─ pinned input SHA-256
   ├─ 현재 확정 거래 지원 여부
   └─ 선택적 synthetic local_cli E2E
        └─ 기존 strict response validator
```

출력 계약은
`src/domain/integration_readiness_models.py`, 조립은
`src/application/integration_readiness_service.py`, CLI는
`scripts/check_integration_readiness.py`에 있다.

## Streamlit에서 확인

사이드바의 `Integration Readiness`를 열고 `연동 상태 점검`을 누른다.

- Stage 1: configured provider, endpoint 종류, health, 실제 source, prediction date,
  market-data date, freshness, provider fallback, upstream partial fallback
- Spot: provider, 설정 source, 현재 분석에서 실제 사용한 source가 있으면 그 값,
  자격증명 설정 여부
- `kb_macro_ai`: feature flag, mode, producer commit, 입력 파일 SHA-256,
  현재 확정 거래의 지원 여부

버튼은 Stage 1 health/forecast만 읽는다. 한국수출입은행 환율 API,
OpenAI, `kb_macro_ai` 모델은 실행하지 않는다. 자격증명은 `설정됨/미설정`만
표시하고 값은 상태 모델에 넣지 않는다.

## CLI 기본 점검

```bash
python scripts/check_integration_readiness.py
```

머신 판독용 strict JSON:

```bash
python scripts/check_integration_readiness.py --json
```

Stage 1 provider까지 호출하지 않는 설정 전용 점검:

```bash
python scripts/check_integration_readiness.py --passive-stage1
```

종료 코드는 `READY`/`DEGRADED`이면 `0`, `BLOCKED`/`DISABLED`이면 `2`다.
`DEGRADED`는 fallback, stale, upstream partial fallback, research-only 또는
fixture/manual 확인 같은 공개된 주의사항이 있다는 뜻이다.

## 단일 USD 수입 지급 local_cli E2E

먼저
[KB_MACRO_HEDGE_REFERENCE_RUNBOOK.md](KB_MACRO_HEDGE_REFERENCE_RUNBOOK.md)의
고정 commit과 forecast/model-config/market-history/quote-template SHA 환경변수를
설정한다. 그 뒤 다음을 실행한다.

```bash
python scripts/check_integration_readiness.py --run-local-cli-e2e
```

E2E fixture는 다음 값으로 고정된다.

| 항목 | 값 |
| --- | --- |
| 거래 | 단일 `IMPORT` |
| 통화 | `USD` |
| 계약상 예정 지급액 | `100000` |
| 지급일 | `2026-08-27` |
| 지급에 사용할 보유 USD | `10000` |
| 기존 선물환 | `0` |
| 순노출 | `90000` |

같은 거래조건을 가진 실제 텍스트 레이어 합성계약과 직접 첨부 순서는
[Golden 단일 USD 수입 지급 헤지 데모](../dataset/golden_import_hedge_demo/README.md)와
[외부 헤지 실행 안내](KB_MACRO_HEDGE_REFERENCE_RUNBOOK.md)에 있다. 다음 명령은
실제 PDF bytes부터 API-free로 같은 결속을 검증한다.

```bash
python scripts/verify_golden_import_hedge_flow.py
```

이 명령은 expected extraction fixture를 명시적으로 사용하므로 Live 모델 정확도
주장에는 사용할 수 없다.

실행은 기존 `run_kb_macro_hedge_for_confirmed_trade`를 그대로 호출한다. 따라서
feature flag, `local_cli` mode, exact producer commit, clean tracked worktree,
허용 경로, 네 입력 SHA, CLI timeout/출력 크기, 사용자 제약, 응답 수학과
certificate gate를 우회하지 않는다.

성공 기준:

- `result_status=REFERENCE_ONLY` 또는 `READY`
- 현재 목업 견적에서는 `pricing_status=MOCK`,
  `result_status=REFERENCE_ONLY`
- validation PASS
- 후보 3개, rank `1,2,3`
- `TEMPORARY_RAW_OUTPUT_DELETED`

회사 입력과 raw upstream 결과는 권한 제한 임시 디렉터리에서만 존재하고 종료 시
삭제된다. CLI 환경에는 API key를 전달하지 않는다.

## 상태 해석

- `READY`: 해당 연결과 무결성 점검 완료
- `DEGRADED`: fallback/fixture/research-only/현재 거래 지원 밖 등 공개된 제한 존재
- `BLOCKED`: provider, commit, SHA, 파일, 자격증명 또는 mode 설정 실패
- `DISABLED`: `ENABLE_KB_MACRO_HEDGE_REFERENCE=false`; 기존 Stage 3만 사용
- `NOT_CHECKED`: 능동 health 또는 현재 확정 거래가 아직 없음

외부 헤지의 `READY`는 실제 상품 가격·가입 승인·실행 권고가 아니다. 목업 가격이면
항상 `REFERENCE_ONLY`이고, 기존 Stage 3·Stage 4·ConsultationPacket·Stage 5와
분리된다. 수출, 수취, 비USD, 분할결제와 복수거래는 provider 실행 전에
`UNSUPPORTED_EXPOSURE`로 차단된다.

## 2026-07-31 실제 local_cli 증거

고정 producer `7d3efa41cdc8bbb8da61b6b0c6108bdf55713e3e`와 runbook의 네
SHA를 사용해 실행했다.

```text
Stage 1 health: OK
Stage 1 source: HTTP
forecast freshness: PASS
provider fallback: false
upstream partial fallback: true
Spot configuration: koreaexim credential configured
Spot API call by readiness check: false
kb_macro_ai commit/SHA/clean checkout/CLI: PASS
synthetic local_cli E2E: PASS
result: REFERENCE_ONLY / MOCK
validation: PASS
candidates/ranks: 3 / 1,2,3
temporary raw output: deleted
overall: DEGRADED
```

전체 상태가 `DEGRADED`인 이유는 연결 실패가 아니라 Stage 1 원본의
`partial_fallback_used=true`와 `research_only=true`를 숨기지 않았기 때문이다.
