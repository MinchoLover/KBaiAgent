# Stage 5 설명 가능한 보고서 Agent 프롬프트

Stage 0~4의 구조화 결과를 최종 상담 준비 보고서로 변환하라.

구성:

- Report Explainer
- Independent Critic
- Deterministic fallback renderer

Explainer는 숫자를 계산하지 않고 주어진 JSON만 설명한다. 모든 핵심 수치에 source JSON path를 연결한다.

Critic 검사:

- 숫자 일치
- 수입/수출 손실 방향
- 스트레스와 예측 구분
- probability 없는 확률 표현 금지
- 운영자금 부족과 지급불능 구분
- Stage 3 후보를 확정 권고로 과장하지 않음
- 상품 출처와 기준일 존재
- 인간 검토 문구

실패하면 최대 1회 수정 요청 후, 다시 실패하면 deterministic Markdown 보고서를 사용한다.

보고서:

1. 거래 요약
2. 문서 추출 근거와 사용자 확인
3. 환율 분석/시나리오 설명
4. 현금흐름 영향 표
5. 핵심 위험과 경보
6. 헤지 후보 비교
7. 상품·제도 후보와 공식 출처
8. 상담 전 준비정보
9. 상담 질문
10. 가정·한계·면책

출력:

- Markdown
- JSON
- 화면 렌더링
- 가능한 환경이면 PDF export, 불가능하면 Markdown/HTML을 안정적으로 제공

LLM 없이도 deterministic fallback 보고서가 완전해야 한다. 숫자 환각을 유발하는 적대적 테스트를 추가하라.
