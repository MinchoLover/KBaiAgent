# Assumptions and Limitations

## Stage 1 시장모델과 환율

- 모델 지원 범위는 USD/KRW 한 통화쌍과 21거래일입니다.
- v25 방향 점수는 보정된 발생확률이 아니며 기대손실 가중치로 사용하지 않습니다.
- v36/v34 q90은 90% 발생확률이 아니라 모델 예측분포의 상위 경로위험 분위수입니다.
- 정확한 미래 환율을 예측하지 않으며 Stage 1 JSON에 없는 spot을 추정하지 않습니다.
- 결제일이 horizon 밖이면 모델 시나리오는 초기 21거래일 시장 문맥일 뿐이고,
  결제기간 숫자는 고정 스트레스로만 계산합니다.
- 뉴스는 설명용이며 방향 점수·분위수·손실 숫자를 변경하지 않습니다.
- 모델과 제공 fixture는 연구·대회용입니다.
- fixture spot 1,400원은 실시간 환율이 아닙니다. 운영 시 공식 reference 또는
  사용자가 확인한 수동 환율이 필요합니다.

## 문서 AI

- 합성 데이터 중심이며 실제 OCR 품질·언어·레이아웃 분포의 live baseline은 API 키가
  있어야 측정할 수 있습니다.
- 텍스트 PDF는 모델 인용문이 실제 페이지에 존재하는지와 당사자·통화·금액·날짜·
  지급조건 값이 일치하는지를 결정론적으로 검사합니다. 이미지형 PDF는 로컬 `pypdf`
  텍스트 레이어가 비어 있고 독립 OCR 엔진은 아직 없습니다. 따라서 vision이 반환한
  evidence는 자동 검증하지 않고 `EVIDENCE_UNVERIFIABLE`, `MISSING_CORE_EVIDENCE`,
  `OCR_REQUIRED`로 계산 전달을 차단합니다. 사용자가 원문을 직접 대조한 field-level
  override만 허용합니다.
- 손글씨, 암호화 PDF, 스캔 20페이지 초과, 표가 매우 복잡한 계약서는 P0 범위 밖입니다.
- 회사 역할은 사용자가 선택하며 회사 국가와 문서 당사자 국가가 다르면 review로
  보냅니다. 동일 국가 간 거래나 삼각무역의 import/export 법적 판정은 지원하지 않습니다.
- 분할조건이 날짜가 아닌 “선적 후 N일”처럼 이벤트 의존적이면 날짜를 추측하지 않습니다.
- `EOM`, 선적·검수·인수 기준 등 복합 지급조건은 단순 Net N로 산술하지 않고 사람
  검토로 보냅니다.

## 금융 계산

- KRW per 1 foreign currency quote만 내부 표준으로 사용합니다.
- 은행 spread는 단일 bps, bank fee는 exposure별 고정액으로 단순화했습니다.
- 기존 hedge의 mark-to-market, margin, 조기해지, rollover, 회계·세무는 계산하지
  않습니다.
- natural hedge eligibility는 입력된 날짜·통화·방향만 사용하며 실제 확정 가능성을
  판단하지 않습니다.
- 원화 cashflow는 일 단위이고 intraday 순서는 없습니다.
- 복합 스트레스는 매출 감소·지연, 비용 증가의 단순 선형 변환입니다.
- UI는 동일 통화 예정흐름을 방향별 합계 한 건으로 빠르게 입력하는 데 최적화되어
  있습니다. 엔진과 JSON 계약은 여러 날짜 흐름을 지원하지만 복잡한 일정은 JSON 연동이
  더 적합합니다.
- Stage 1은 target date 하나만 제공하므로 분할결제일이 여러 개면 같은 환율 scenario
  set을 각 회차에 대체 적용하고 경고합니다. 회차별 term structure는 지원하지 않습니다.
- 확정 거래 SHA-256은 한 workflow 안에서 오래되거나 바뀐 입력을 차단하는 무결성
  fingerprint이며 전자서명이나 사용자 인증을 대신하지 않습니다.

## 전략·상품

- Stage 3 비용률, forward effective rate와 staged risk factor는 공개된
  `assumptions_contract` 아래의 시뮬레이션 가정이며 실제 최적화·주문·투자 자문이
  아닙니다.
- Stage 4 offline KB는 2026-07-23 확인 snapshot이며 자격·금리·한도·신청기간 최신성을
  보장하지 않습니다.
- official web search도 URL과 설명 후보만 제공하며 승인 가능성을 판정하지 않습니다.
- 금융상품 가입·대출심사·보험인수·헤지 계약 가능성을 보장하지 않습니다.
- official web search cache는 기본 24시간 TTL과 allowlist·모델·질의·거래방향을
  재검증합니다. TTL 안의 자료도 상품 조건 최신성을 보장하지 않으므로 확인일과 공식
  페이지를 사람이 다시 확인해야 합니다.

## 보고서

- critic은 숫자가 같은 줄의 유효한 JSON path 값과 연결되는지와 정책 표현을 강하게
  검사하지만 자연어의 모든 의미 오류를 증명하지는 못합니다.
- API가 없거나 Stage 4 공식 후보가 비었거나 critic이 재실패하면 안전한 template
  보고서로 fallback합니다.

## 운영

- 단일 로컬 Streamlit 앱이며 사용자 인증, 권한 분리, 중앙 DB, malware scan,
  production observability는 없습니다.
- workflow trace는 session state의 실행 메타데이터이며 중앙 감사로그나 영구
  event store가 아닙니다. 문서 원문과 금융 payload는 의도적으로 포함하지 않습니다.
- `app.py`는 금융 계산을 직접 수행하지 않지만 탭별 form과 렌더링을 한 파일에 유지해
  길이가 큽니다. view 함수 분리는 후속 UI 리팩터링 범위입니다.
- macOS Python 3.9.6에서 검증했습니다. Windows launcher는 제공했지만 이 환경에서
  직접 실행 검증하지 못했습니다.
- 실제 OpenAI 호출과 공식 web search는 API 키가 없어 실행하지 않았습니다.
- Stage 1 REST endpoint는 HTTPS/public IP, redirect 금지, 선택적 exact host
  allowlist를 적용합니다. DNS 검증과 실제 연결 사이 rebinding 위험을 더 줄이려면
  production egress proxy 또는 방화벽 allowlist가 추가로 필요합니다.
- fixture 기반 regression은 evaluator·schema·결정론 코드 회귀를 검출하지만 프롬프트
  변경이 실제 모델에 미치는 영향은 측정하지 못합니다. 승인된 live prediction snapshot을
  별도 baseline으로 보존해 비교해야 합니다.
