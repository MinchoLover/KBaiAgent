# KB AI Challenge 재포지셔닝 변경 전 기준 상태

기록 시각 기준 저장소는 수출입 문서 확인, 환율 스트레스, `Decimal` 현금흐름
계산, 헤지 후보, 공식자료 후보, 보고서를 하나의 Streamlit 흐름으로 연결합니다.
다만 구조화된 위험 코드와 위험 기반 상담 대응, 독립적인 KB 상담 준비 패킷은 아직
없습니다. 이 문서는 README의 주장보다 실제 코드와 실행 결과를 우선해 기록합니다.

## 1. Git 및 런타임 기준선

- 원격 저장소: `https://github.com/MinchoLover/KBaiAgent.git`
- 변경 전 브랜치: `main`
- 변경 전 커밋: `68448292c34e97c9df53e69220df34fc31813d59`
- 최근 커밋:
  - `6844829 feat: redesign copilot for finance users`
  - `cc45b23 feat: 2 stage 리팩토링`
  - `e2e05bd feat: initial commit`
- 변경 전 작업 트리: clean
- 구현 브랜치: `feature/reposition-trade-consultation`
- Python: `3.9.6`
- Streamlit: `1.50.0`
- 의존성 검사: `python -m pip check` 통과
- 데이터베이스: 미구현, `st.session_state`만 사용
- Docker: 미구현 및 불필요
- 별도 HTTP API 서버: 미구현

## 2. 실행 구조

- 통합 실행 진입점: `app.py`
- 실행 명령: `python -m streamlit run app.py`
- macOS 보조 실행: `run_mac.command`
- Windows 보조 실행: `run_windows.bat`
- 프론트엔드: `app.py`, `src/ui/`
- 애플리케이션 서비스: `src/application/`
- 문서 추출: `src/document_intake/`
- 환율 시나리오: `src/stage1/`
- 결정론 계산 엔진: `src/stage2/`
- 헤지 후보 프로토타입: `src/stage3/`
- 공식자료 후보: `src/stage4/`, `knowledge_base/official_products.json`
- 설명 보고서: `src/stage5/`
- 상태 기반 실행 제어: `src/workflow/`
- 테스트: `tests/`
- 샘플: `samples/`, `dataset/synthetic/`, `dataset/labels/`

## 3. 환경변수와 외부 의존성

로컬 `.env.example`에는 다음 계약이 있으나 `.gitignore`의 `.env.*` 규칙으로 현재
Git 추적 대상은 아닙니다. 실제 키 값은 확인하거나 출력하지 않았습니다.

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_FALLBACK_MODEL`
- `OPENAI_REPORT_MODEL`
- `OPENAI_RAG_MODEL`
- `DEMO_MODE`
- `ENABLE_LIVE_DOCUMENT_EXTRACTION`
- `ENABLE_OFFICIAL_WEB_SEARCH`
- `STAGE1_MODE`
- `STAGE1_BASE_URL`
- `STAGE1_ALLOW_PRIVATE_ENDPOINTS`
- `STAGE1_ALLOWED_HOSTS`
- `MAX_UPLOAD_MB`
- `MAX_PDF_PAGES`
- `STAGE1_TIMEOUT_SECONDS`
- `OPENAI_TIMEOUT_SECONDS`
- `OFFICIAL_SEARCH_CACHE_TTL_HOURS`
- `OFFICIAL_DOMAINS`

외부 서비스는 OpenAI 문서 구조화, 선택적 OpenAI 공식 도메인 웹 검색, 선택적
Stage 1 JSON/REST 입력입니다. 세 서비스가 모두 없어도 `전체 오프라인 데모 실행`,
수동 스트레스, 오프라인 공식 KB, 결정론 보고서가 동작합니다.

## 4. 기능별 실제 상태

| 영역 | 실제 파일 | 현재 상태 | 재사용 가능성 | P0 수정 필요 |
| --- | --- | --- | --- | --- |
| 거래정보 입력 | `app.py`, `sample_data.py` | 샘플 fixture와 실제 문서 업로드가 동작. 빈 수동 거래 생성기는 없음 | 높음 | 수입·수출 대표 샘플을 명시적으로 제공 |
| 문서 추출 | `src/document_intake/openai_adapter.py`, `schemas.py` | OpenAI Responses Structured Outputs 사용. API 없는 로컬 OCR은 없음 | 높음 | 없음. API 실패 시 샘플 경로 유지 |
| 사용자 확인 | `src/document_intake/confirmation.py`, `validators.py`, `app.py` | 통화·금액·결제일 확인과 fingerprint gate 존재. 거래 방향은 결정론 파생되지만 별도 확인 상태 없음 | 높음 | 거래 방향 확인 상태 추가 |
| 환율 시나리오 | `src/stage1/` | 기준 및 ±3/5/10% 수동 스트레스, 외부 JSON/REST, 실패 fallback 구현 | 높음 | 대표 데모는 spread/fee 0으로 계산 정의를 명확히 함 |
| 환노출 계산 | `src/stage2/exposure.py` | 보유 외화, 동일통화 흐름, 기존 헤지를 분리해 계산 | 매우 높음 | 재작성하지 않음 |
| 현금흐름 계산 | `src/stage2/engine.py`, `cashflow.py` | 날짜별 잔고, buffer shortfall, cash deficit, post-credit shortfall 구현 | 매우 높음 | 패킷에서 `payment_gap` 명칭으로 명확히 매핑 |
| 위험 분류 | `app.py::_risk_summary` | 화면용 단일 문구만 존재. 구조화 risk code/evidence 없음 | 낮음 | 결정론 분류 모델과 엔진 추가 |
| 금융 대응 후보 | `src/stage3/`, `src/stage4/` | 헤지 grid 및 공식상품 후보는 있으나 risk code 기반 상담 범주 매핑은 없음 | 중간 | 규칙 기반 일반 상담 범주 추가 |
| 상담 패킷 | 미구현 | Stage 5 source bundle은 있으나 별도 schema/version/hash/상담질문 패킷이 아님 | 없음 | JSON·Markdown 패킷 추가 |
| 보고서 | `src/stage5/` | LLM 설명 + critic + 1회 재작성 + 결정론 fallback 구현 | 높음 | 상담 패킷을 사용자 화면과 다운로드에 연결 |
| 테스트 | `tests/`, `scripts/verify.py` | 변경 전 `unittest` 175개 통과, 오프라인 E2E 1개 존재 | 높음 | 위험·매핑·패킷 및 수출 E2E 보강 |

## 5. 변경 전 테스트 결과

| 실행 명령 | 결과 | 오류 메시지 | 직접 원인 | 근본 원인 | 수정 필요 여부 |
| --- | --- | --- | --- | --- | --- |
| `python -m compileall -q -x '(^|/)(\.venv|\.git|__pycache__)(/|$)' .` | 성공 | 없음 | 해당 없음 | 해당 없음 | 없음 |
| `python -m unittest discover -s tests -v` | 성공, 175/175 | 없음 | 해당 없음 | 해당 없음 | 없음 |
| `pytest -q` | 실패, 미실행 | `command not found: pytest` | 실행 파일 미설치 | 저장소 표준 러너가 `unittest`이고 `pytest`가 `requirements.txt`에 없음 | P0에서는 새 프레임워크를 추가하지 않음 |
| `python scripts/evaluate_extraction.py --mode offline` | 성공 | 없음 | 17건 평가, 문서 pass rate 82.35%, hallucination 0% | fixture 기반 계약 평가이며 실제 LLM 품질 평가는 아님 | live 품질은 외부 자격증명 필요 |
| `python scripts/run_regression.py` | 성공 | 없음 | 해당 없음 | 해당 없음 | 없음 |
| `python scripts/verify.py` | 성공 | 없음 | compile + 175 tests + 계약 검사 통과 | 해당 없음 | 변경 후 재실행 |

## 6. 변경 전 핵심 판단

1. Stage 2 계산 엔진은 P0에서 재작성할 이유가 없습니다. 이미 `Decimal`, 날짜순
   ledger, 수입·수출 위험 방향, 자연상계, 기존 헤지, 신용한도를 검증합니다.
2. 제품이 환율 계산기로 보이는 직접 원인은 계산 뒤에 구조화된 위험 원인과
   은행 상담용 산출물이 없기 때문입니다.
3. Stage 3의 비용률과 잔여위험계수는 명시적인 데모 가정이므로 “최적”으로 표현할 수
   없습니다. 새 상담 흐름에서는 확정 추천이 아니라 참고 대응 후보로만 유지합니다.
4. 현재 `post_credit_shortfall`은 대출한도 반영 후 음수 현금의 최대 부족액입니다.
   상담 패킷에서는 이를 `payment_gap_krw`로 명시해 최소 운영자금 부족과 구분합니다.
5. P0는 새 프레임워크나 데이터베이스가 아니라 기존 오케스트레이터 뒤에 작은
   결정론 서비스 계층을 연결하는 방식이 가장 안전합니다.
