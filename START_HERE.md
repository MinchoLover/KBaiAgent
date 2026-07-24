# START HERE

가장 빠른 공모전 데모 방법:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

앱 왼쪽의 `전체 오프라인 데모 실행`을 누르면 API 키 없이 Stage 0~5 결과가 생성됩니다.
각 탭에서 문서 근거, 확인 gate, 스트레스 시나리오, 현금잔고, 후보 전략, 공식 출처,
보고서의 JSON path를 순서대로 설명하면 됩니다.

실제 문서는 `.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`만 채운 뒤
`실제 API 모드`를 선택합니다. 팀 Stage 1 endpoint가 없으면
`MANUAL_STRESS`, 웹 검색이 꺼져 있으면 `OFFLINE_KB`가 정상 기본 경로입니다.
Stage 1 REST 운영 연결은 `.env`의 `STAGE1_ALLOWED_HOSTS`에 exact hostname을
설정하세요. localhost 연결은 개발 환경에서만 별도로 허용합니다.

릴리스 전 한 번에 확인:

```bash
python scripts/verify.py
```

운영 전에는 [docs/SECURITY_PRIVACY.md](docs/SECURITY_PRIVACY.md)와
[docs/LIMITATIONS.md](docs/LIMITATIONS.md)를 읽으세요.
