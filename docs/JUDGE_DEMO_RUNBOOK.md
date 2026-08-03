# KBaiAgent 심사위원 실행 안내서

## 1. 프로젝트와 실행 방식

KBaiAgent는 합성 수출계약을 확인하고 환율 전망, 현금흐름 위험, 금융지원 상담
후보와 상담 준비서 PDF까지 연결하는 Python 3.9+ Streamlit 애플리케이션입니다.
DB와 Docker는 필요하지 않습니다.

심사용 실행은 두 경로를 분리합니다.

- **Golden Demo**: 저장소의 합성 계약서와 검증된 고정 데이터로 실행합니다.
  API 키와 네트워크가 없어도 완주할 수 있습니다.
- **실제 API 연동 확인**: 허가된 합성 문서에 OpenAI 문서 추출을 사용하거나,
  일반 거래에서 관세청·한국수출입은행 adapter를 선택적으로 확인합니다.
  Golden 고정 수치에는 이 응답을 섞지 않습니다.

## 2. 검증 환경과 필수 프로그램

- Python 3.9 이상
- 의존성 설치를 위한 인터넷 연결
- 최신 Chrome, Edge 또는 Safari
- macOS/Linux 또는 Windows PowerShell

프로젝트는 macOS의 Python 가상환경과 Streamlit에서 검증합니다. Windows에서는
아래 PowerShell 명령을 사용합니다.

## 3. 압축파일 준비

제출 ZIP을 **압축 풀기**로 해제하고 `app.py`가 있는 `KBaiAgent` 폴더로 이동합니다.
Git clone은 필요하지 않습니다.

macOS/Linux:

```bash
cd KBaiAgent
./run_mac.command
```

Windows에서는 `run_windows.bat`를 더블클릭하거나 다음 명령을 사용합니다.

```powershell
cd KBaiAgent
.\run_windows.bat
```

실행파일은 `.env`가 없을 때 안전한 Golden 설정을 자동으로 준비합니다. 기존
`.env`가 있으면 덮어쓰지 않습니다.

수동 실행을 원하는 경우:

macOS/Linux:

```bash
cp judge-demo.env.example .env
```

Windows PowerShell:

```powershell
Copy-Item judge-demo.env.example .env
```

실제 API 연동이 승인되어 비공개 `judge-demo.env`를 별도로 받은 경우에만 해당 파일을
`.env`로 복사합니다. `.env`와 실제 `judge-demo.env`를 화면 공유, 보고서, 이슈 또는
Git에 올리지 마세요.

## 4. 의존성 설치와 실행

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

브라우저가 자동으로 열리지 않으면 다음 주소로 접속합니다.

```text
http://localhost:8501
```

## 5. Golden Demo 실행 절차

1. 홈에서 **3분 데모 시작하기**를 누릅니다.
2. 등록된 브라질 Golden 합성 계약서를 확인하고
   **문서 분석하고 거래정보 채우기**를 누릅니다.
3. 원문 근거 카드에서 거래정보를 확인한 뒤 **거래 기본정보 확정**을 누릅니다.
4. 대금 회수조건과 회사 자금의 자동 입력값을 확인하고
   **환율·자금 위험 계산하기**를 누릅니다.
5. **거래 확정하고 분석 시작**으로 환율 전망·위험 화면을 엽니다.
6. 전망, 거래 금액 영향, 현금흐름 위험과 고정 스트레스 시나리오를 확인한 뒤
   **금융지원 추천으로 계속**을 누릅니다.
7. 금융지원 추천의 현재 후보를 확인하고 **상담 준비로 계속**을 누릅니다.
8. 상담 준비·보고서 화면에서 **상담 준비서 PDF 다운로드**를 누릅니다.

환경이나 화면 상태에 따라 이미 완료된 단계의 버튼은 비활성화되거나 결과가 바로
표시될 수 있습니다. 숫자·국가·날짜를 새로 입력할 필요는 없습니다. 확인되지 않은
사실은 `확인 필요`로 유지됩니다.

## 6. 정상 실행 시 확인할 값

Golden 계약의 고정 사실은 다음과 같습니다.

| 항목 | 값 |
| --- | --- |
| 거래 | 대한민국 판매자 → 브라질 구매자, 수출 |
| 통화·계약금액 | USD 100,000 |
| 선지급 예정·잔금 예정 | USD 20,000 · USD 80,000 |
| 계약일·선적일·잔금일 | 2026-07-29 · 2026-08-05 · 2026-08-20 |
| 결제조건 | 외상거래(Open Account) / 전신송금(T/T) |
| Incoterm | FOB Busan, Incoterms 2020 |

고정 스트레스 검증값은 기준환율 1,400원, 환율 5% 하락 시 1,330원, 기준
수취액 140,000,000원, 스트레스 수취액 133,000,000원, 감소액 7,000,000원,
스트레스 후 현금 8,000,000원, 최소 운영자금 대비 부족액 2,000,000원,
실제 현금 적자 0원, 대출한도 반영 후 부족액 0원입니다.

시장 모델의 중심환율과 범위는 참고정보이며 위 고정 스트레스 금액과 같은 값으로
해석하지 않습니다.

## 7. 상담 준비서 PDF

상담 준비·보고서 화면의 **상담 준비서 PDF 다운로드** 버튼을 사용합니다. PDF가
열리지 않으면 OS의 한글 Unicode 폰트가 있는지 확인합니다. 필요할 때만
`KBAI_CONSULTATION_PDF_FONT`에 사용 권한이 있는 폰트의 절대경로를 설정합니다.
키·내부 hash·개발자 trace는 PDF에 포함되지 않습니다.

## 8. 실제 API와 fallback 확인

Golden Demo는 재현성을 위해 다음 자료를 사용합니다.

- 문서 추출: 등록된 합성문서의 검증된 extraction
- Stage 1: `src/integration_assets/stage1/latest_forecast.json`
- 기준환율: Golden fixture 1,400원
- 무역통계: 검증된 관세청 공식 원자료 snapshot

따라서 Golden Demo가 성공했다고 해서 live API 호출 성공을 의미하지 않습니다.
실제 연동은 다음처럼 별도로 확인합니다.

- `OPENAI_API_KEY`가 있으면 **내 거래문서 분석하기**에서 허가된 합성 문서를
  분석할 수 있습니다.
- `CUSTOMS_TRADE_API_KEY`가 있으면 일반 업로드 거래의 거래국 통계를 관세청
  adapter가 조회합니다. Golden 거래는 항상 검증된 snapshot을 사용합니다.
- `KOREAEXIM_KEY`를 넣고 `SPOT_RATE_PROVIDER=koreaexim`으로 전달한 팩에서는
  한국수출입은행 환율 adapter를 사용할 수 있습니다.
- 팀 Stage 1 HTTP 서버는 이 저장소에 포함되지 않습니다. 별도 서버가 준비된
  경우에만 `STAGE1_PROVIDER=http`과 `STAGE1_BASE_URL`을 사용합니다. 연결 실패 시
  기존 file fallback 계약이 적용되며 출처가 실제 연결처럼 표시되지 않습니다.

비밀값을 출력하지 않는 준비상태 점검:

```bash
.venv/bin/python scripts/check_integration_readiness.py
```

Windows:

```powershell
.venv\Scripts\python.exe scripts/check_integration_readiness.py
```

사용자 화면에는 `연결된 환율 전망`, `검증된 전망 자료`, `공식 API 조회`,
`검증된 저장자료 사용`처럼 출처 의미를 표시합니다. 내부 provider ID나 원문 JSON은
presentation 모드에서 숨깁니다.

## 9. 종료 방법

Streamlit을 실행한 터미널에서 `Ctrl+C`를 누릅니다. 심사가 끝나면 저장소의 `.env`,
압축 해제한 `judge-demo.env`와 다운로드한 민감 자료를 삭제하고 심사용 임시 키를
각 발급기관에서 폐기합니다.

## 10. 자주 발생하는 오류

| 증상 | 원인과 조치 |
| --- | --- |
| `ModuleNotFoundError` | 시스템 Python이 아니라 `.venv` Python으로 실행합니다. |
| `streamlit` 명령을 찾지 못함 | 의존성 설치를 다시 실행하고 `python -m streamlit run app.py`를 사용합니다. |
| OpenAI 연결 준비 안 됨 | `OPENAI_API_KEY` 앞뒤 공백과 빈 값을 확인합니다. Golden은 키 없이 계속할 수 있습니다. |
| 관세청 키 필요 안내 | 일반 업로드의 live 통계에만 필요합니다. Golden 계산은 계속됩니다. |
| Stage 1 HTTP 연결 실패 | 별도 팀 서버가 없으면 `STAGE1_PROVIDER=file`을 유지합니다. |
| PDF 한글 폰트 오류 | OS 한글 폰트를 설치하거나 허가된 폰트 경로를 `KBAI_CONSULTATION_PDF_FONT`에 지정합니다. |
| 포트 8501 사용 중 | 기존 Streamlit을 종료하거나 `--server.port 8502`를 추가합니다. |

## 11. 실제 환경변수 요약

아래 표는 심사 팩에 직접 관련된 변수만 요약합니다. 전체 안전 템플릿은
`.env.example`입니다.

| 변수명 | 사용 위치 | Golden 필수 | 비밀 | 용도 |
| --- | --- | ---: | ---: | --- |
| `APP_ENV` | `src/config.py`, `app.py` | 예 | 아니오 | presentation UI 선택 |
| `DEMO_MODE` | `src/config.py`, provider | 예 | 아니오 | 등록 샘플과 fixture 경로 허용 |
| `OPENAI_API_KEY` | 문서 추출·설명 서비스 | 아니오 | 예 | 실제 문서 추출·선택적 설명 |
| `OPEN_AI_API_KEY` | `src/config.py` | 아니오 | 예 | 기존 호환용 OpenAI 키 별칭 |
| `STAGE1_PROVIDER` | Stage 1 forecast adapter | 예 | 아니오 | `http`, `file`, `mock` 선택 |
| `STAGE1_BASE_URL` | Stage 1 HTTP adapter | 아니오 | 아니오 | 별도 팀 서버 주소 |
| `STAGE1_FORECAST_FILE` | Stage 1 file adapter | 예 | 아니오 | 검증된 forecast JSON |
| `SPOT_RATE_PROVIDER` | spot provider | 예 | 아니오 | Golden `fixture`, 선택적 live provider |
| `KOREAEXIM_KEY` | 한국수출입은행 spot provider | 아니오 | 예 | live 기준환율 조회 |
| `CUSTOMS_TRADE_API_KEY` | 관세청 provider | 아니오 | 예 | 일반 거래 live 무역통계 조회 |
| `TRADE_STATISTICS_PROVIDER` | 무역통계 service | 예 | 아니오 | Golden fixture와 일반 live 분기 |
| `KBAI_CONSULTATION_PDF_FONT` | PDF renderer | 아니오 | 아니오 | 선택적 한글 폰트 경로 |

`ECOS_KEY`와 `CREDIT_KEY`는 현재 `Settings`가 읽지만 Golden 의사결정 경로의
active provider에는 연결되지 않으므로 심사 팩에 넣지 않습니다.
