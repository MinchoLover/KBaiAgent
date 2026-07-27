# START HERE

## 1. API key 없는 검증과 데모

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/verify.py
python scripts/run_decision_demo.py --company-role BUYER --format summary
python scripts/run_decision_demo.py --company-role SELLER --format summary
python -m streamlit run app.py
```

브라우저에서 `http://localhost:8501`을 열고 샘플 거래를 실행합니다. 기본 CLI
데모는 팀 Stage 1 forecast fixture, USD/KRW 1,400 fixture spot, 고정 스트레스를
사용합니다. 둘 다 실시간 값이 아님을 결과에 표시합니다.

## 2. 팀 Stage 1 HTTP 연결

별도 `kb_macro_ai` 저장소에서:

```bash
KRW_ENABLE_OPENAI_NEWS=1 zsh scripts/run_web_forecast.sh
zsh scripts/serve_web_forecast.sh
```

메인 저장소:

```bash
cp .env.example .env
```

`.env`:

```dotenv
STAGE1_PROVIDER=http
STAGE1_BASE_URL=http://127.0.0.1:8765
SPOT_RATE_PROVIDER=manual
MANUAL_USDKRW_RATE=1400
```

수동 환율은 UI에서 사용자가 확인해야 합니다. 한국수출입은행 key가 있으면
`SPOT_RATE_PROVIDER=koreaexim`을 사용할 수 있습니다.

## 3. 제공 파일

다음 파일은 `src/integration_assets/stage1/`에 있습니다.

```text
latest_forecast.json
JSON_README.md
team_model_report_3page.docx
```

없을 경우 동일 경로에 팀원 산출물을 넣으세요. 코드는 mock fixture가 없으면
완료로 간주하지 않으며 `python scripts/verify.py`가 실패합니다.

## 4. 실제 문서 AI

```dotenv
OPENAI_API_KEY=
ENABLE_DOCUMENT_AI=true
```

실제 회사 문서는 전송 정책과 허가를 먼저 확인합니다. 키가 없거나 호출이
실패해도 샘플 인테이크·Stage 1 fixture·결정론 계산·템플릿 보고서는 동작합니다.

구조와 안전 한계는
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/STAGE1_INTEGRATION.md`](docs/STAGE1_INTEGRATION.md),
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md)를 확인하세요.
