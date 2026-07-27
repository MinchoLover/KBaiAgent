# Repository Audit

감사 기준일: 2026-07-27 KST
기준 브랜치: `feature/reposition-trade-consultation`
기준 커밋: `e011428`
Stage 1 기준 저장소: `../kb_macro_ai` `main` `b5168e4`

## 기준선

| 항목 | 실제 상태 |
|---|---|
| 언어·런타임 | Python 3.9.6 |
| UI | 단일 Streamlit 앱 `app.py` |
| 데이터 계약 | Pydantic 2 strict model |
| 금융 계산 | `src/stage2/`, `Decimal`, 날짜별 ledger |
| 워크플로 | `src/workflow/` 상태·gate·trace |
| 문서 추출 | OpenAI structured output와 offline fixture |
| Stage 1 기존 경계 | 절대 환율 시나리오 JSON/REST adapter |
| Stage 3 | 결정론 grid 탐색 프로토타입 |
| Stage 4 | 공식 URL allowlist + 검증된 local snapshot |
| Stage 5 | LLM 설명 + critic + 결정론 fallback |
| 데이터베이스·Docker | 사용하지 않음 |
| 기준 검증 | `.venv/bin/python scripts/verify.py` PASS, 184 tests PASS |

사용자 제공 `latest_forecast.json`, `JSON_README.md`,
`team_model_report_3page.docx`는
`src/integration_assets/stage1/`에서 확인했다. 실제 sibling Stage 1 서비스도
`GET /api/forecast`, `GET /health`를 제공하는 것을 코드로 대조했다.

## 발견 사항

| 심각도 | 문제 | 근거 | 영향 | 수정 방향 | 상태 |
|---|---|---|---|---|---|
| CRITICAL | Stage 1 웹 출력은 상대 수익률 분위수인데 기존 adapter는 절대 환율 시나리오만 받음 | `src/stage1/adapter.py`, Stage 1 `web_forecast_v1.py` | 원본 JSON을 바로 계산에 넣을 수 없고 임의 환율 변환 위험 | 별도 web forecast provider·normalizer·scenario builder | 수정 완료 |
| CRITICAL | Stage 1 JSON에 spot rate가 없음 | 제공 `latest_forecast.json` | 절대 결제액을 계산할 기준환율이 없으며 임의 추정 위험 | 독립 `SpotRateProvider`, 수동 확인·fixture·공식 provider | 수정 완료 |
| CRITICAL | 기존 target-date 불일치는 경고 후 같은 환율을 그대로 적용 | `src/stage1/normalizer.py`, `src/stage2/engine.py` | 21거래일 모델을 90일 거래에 외삽할 수 있음 | web forecast 경로에서 model scenario를 계산에서 제외 | 수정 완료 |
| HIGH | `probability_calibrated=false` 방향 점수용 전용 DTO·정책이 없음 | 제공 JSON, 기존 `ScenarioPoint.probability` | 점수를 실제 발생확률 또는 기대손실 가중치로 오용할 수 있음 | score를 시장 문맥 전용으로 정규화하고 scenario probability는 null | 수정 완료 |
| HIGH | Stage 1 HTTP/file/mock 선택과 표시된 fallback이 없음 | 기존 adapter는 legacy JSON/REST만 지원 | 로컬 API 장애·오프라인 데모의 상태를 구분하기 어려움 | provider port와 `FALLBACK_USED` 결과 추가 | 수정 완료 |
| HIGH | Stage 1 품질 필드·뉴스 오류·연구용 상태가 downstream에 보존되지 않음 | 제공 JSON `data_quality`, `news_market_context` | 오래되거나 부분 fallback된 분석을 정상처럼 보일 수 있음 | freshness·quality warning과 정성 context 보존 | 수정 완료 |
| MEDIUM | Python 파일과 문서에 ` 2` 이름의 폐기 후보가 남아 있음 | `src/demo 2.py`, `src/stage5/* 2.py`, `docs/PROJECT_BRIEF 2.md` | 유지보수자가 canonical 파일을 혼동 | 이번 통합에서는 삭제하지 않고 canonical 경로만 문서화 | 미수정 |
| MEDIUM | `app.py`가 3천 줄 이상인 단일 화면 모듈임 | `app.py` | UI 수정 충돌 위험 | 대규모 UI 분리는 P2 | P2 |
| MEDIUM | CI·Docker가 없음 | 저장소 파일 검사 | 다른 환경의 재현성이 수동 검증에 의존 | 한 명령 `scripts/verify.py`를 강화; CI는 P2 | P2 |
| LOW | 실제 OpenAI·공식 환율·공식 웹 검색은 자격증명 없이 live 검증할 수 없음 | `.env.example` | 외부 장애 경계는 mock으로만 검증 | fixture/fetcher test와 설정 문서, live smoke 분리 | 문서화 완료 |

## 보안·개인정보 감사

- 실제 API token 패턴은 추적 파일과 작업 파일에서 발견되지 않았다.
- `.env`, `.venv`, 실제 업로드, live prediction은 `.gitignore` 대상이다.
- 사용자 제공 Stage 1 fixture에는 공개 시장·뉴스 정보만 있으며 기업 문서는 없다.
- 문서 원문과 금액 payload는 workflow trace에 기록하지 않는 기존 정책을 유지한다.
- Stage 1 HTTP 소비는 브라우저가 아니라 서버 측 adapter에서 수행한다.
- sibling Stage 1 서버의 `Access-Control-Allow-Origin: *`는 메인 앱 통합에 필요하지
  않으며 운영 공개 시 최소 origin으로 제한하도록 변경 요청에 기록한다.

## 수정 금지·보존 경계

- Stage 1 모델 코드는 메인 저장소에 복사하지 않는다.
- 기존 `Stage1ScenarioSet` JSON/REST 계약과 기존 184개 테스트를 보존한다.
- Stage 2 금융 계산은 새 시나리오의 검증된 절대 환율만 받는다.
- uncalibrated direction score와 뉴스는 어떤 금액도 바꾸지 않는다.
- 사용자 확인 전 downstream 계산을 계속 차단한다.

## 수정 후 확인

- Stage 1 HTTP/file/mock, 공식·수동·fixture Spot, q scenario와 horizon 차단 구현
- 수입 v36 상승·수출 v34 하락 방향 테스트 구현
- 보고서에서 raw evidence 제거, q90·미보정 점수·horizon·뉴스 오용 critic 구현
- 기본 5%p Stage 3 제약 탐색과 `NO_FEASIBLE_CANDIDATE` 구현
- `python scripts/verify.py`를 최종 release gate로 유지
