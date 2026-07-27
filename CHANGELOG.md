# Changelog

## 2026-07-28

- 텍스트 PDF의 핵심 evidence를 실제 페이지 존재와 현재 당사자·통화·금액·날짜·지급조건 값으로 결정론 검증
- 금액·결제일 불일치, 원문 부재·반대 당사자 인용, 수량을 금액으로 오인하는 evidence를 Stage 2 전 차단
- 올바른 인용이 다른 페이지에 있으면 page 번호를 정정하고, 이미지·스캔 문서는 독립 텍스트 원문 없이 field-level 사용자 override 전 차단
- 수정·최종 confirmation 단계에서도 현재 live 업로드의 원문 텍스트를 다시 대조
- fixture evaluator의 evidence coverage를 source verification이 아닌 evidence claim coverage로 명시

## 2026-07-27

- 핵심값별 정확한 비추론 evidence 계약과 few-shot 자체 감사 추가
- 합성 label·fixture prediction의 당사자 국가 evidence 계약과 JSON-only 재생성 추가
- 텍스트 PDF의 메모리 내 당사자 evidence 대조 및 이미지형 PDF `OCR_REQUIRED` 추가
- 당사자 이름·국가의 stale/opposite evidence 차단과 사용자 수정 시 evidence 폐기
- CA/AU/FR/NL/NO/TW 국가 별칭 및 대문자 ISO evidence 판정 보강
- live smoke가 validation 실패를 성공으로 표시하던 종료 코드 수정
- 국가 자연어 별칭의 ISO alpha-2 정규화와 raw/normalized audit 추가
- 정규화 후 회사 역할·당사자 국가 기반 IMPORT/EXPORT 자동판정 및 사용자 override 추가
- 실제 금액 원문의 ISO 통화 코드만 재사용하는 currency evidence 후처리 추가
- 날짜 placeholder null 처리와 Contract/Invoice 기준 calendar/business Net N 검증 추가
- Streamlit 수정 후 전체 재검증, 5필드 확인, evidence 사용자 대조 override 추가
- KBFX 매매계약 fixture의 Stage 0 → Stage 2 회귀 테스트 추가
- sibling `kb_macro_ai`용 `krw_forecast_web_v1` HTTP/file/mock adapter 추가
- 독립 Spot provider와 KoreaExim·사용자 확인 수동값·fixture provenance 추가
- v36 수입 상승, v34 수출 하락 경로위험과 ±3/5/10% stress builder 추가
- 21거래일 밖 결제의 `HORIZON_MISMATCH`와 모델 환율 계산 차단
- Stage 2 signed impact/비음수 loss, 최초 실제 현금 적자와 source path 보강
- Stage 3 안정성·균형·비용 후보, q90/±10%/유동성 제약과 infeasible 상태 추가
- 보고서 입력 최소화와 q90·미보정 점수·horizon·뉴스 정책 critic 추가
- 수입·수출 Stage 1 fixture E2E, 실제 sibling HTTP, Streamlit health 검증
- API-free 테스트 264개와 통합 문서·환경설정 갱신

## 2026-07-23

- Stage 0 strict extraction schema, prompt files, evidence-based validator, confirmation gate 추가
- PDF/이미지 Responses API adapter와 안전한 업로드 검사 추가
- 16건 합성 문서, labels, manifest, offline/live 평가 및 regression 도구 추가
- Stage 1 manual/external adapter 및 1통화 단위 정규화 추가
- Stage 2 Decimal 기반 exposure, 시나리오, ledger, 복합 스트레스 엔진 추가
- Stage 3 grid 후보, Stage 4 공식 offline KB/web allowlist, Stage 5 critic/fallback 추가
- 단일 Streamlit Stage 0~5 UI, JSON/Markdown 다운로드, 실행 스크립트 추가
- 분할결제 자연상계·헤지 수수료 배분, 복합 Net 조건 abstention, 국가 evidence 규칙 강화
- Streamlit 상태 무효화와 확인 audit snapshot, PDF 미리보기 의존성 고정
- 보고서의 숫자-JSON path 연관 검증과 Stage 3 전체 후보 추적성 강화
- evaluator 결손/손상 prediction 격리, live raw/validated extraction 동시 기록
- 133개 API-free 테스트와 통합 verify 추가
