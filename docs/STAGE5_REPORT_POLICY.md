# Stage 5 Report Policy

## Pipeline

```text
confirmed Stage 0 + Stage 1 + Stage 2 + Stage 3 + Stage 4
                    + 선택적 ConsultationPacket
→ explainer LLM
→ deterministic critic
→ PASS
→ 실패 시 1회 수정
→ 재실패 또는 API 실패 시 deterministic fallback
```

API 키가 없으면 처음부터 fallback 보고서를 생성합니다.
Stage 4 공식 근거 후보가 비어 있어도 LLM을 호출하지 않고 fallback합니다. 이 정책은
상품명·기관명을 자연어로 임의 생성할 가능성을 호출 경계에서 차단합니다.

`ConsultationPacket`이 전달되면 이 패킷이 거래·결제 위험, 금융 대응과 사용자용
공식 후보의 권위 있는 근거입니다.

- 거래·결제 위험: `consultation.trade_settlement_risk`
- 상담 Top 3: `consultation.consultation_priorities`
- 기타 확인사항: `consultation.other_consultation_topics`
- 공식 후보: `consultation.official_candidate_shortlist.candidates`

이때 Stage 4 원시 검색 후보의 이름·기관·URL은 LLM bundle에서 제거하고 검색 mode,
query, 원시 후보 수와 warning만 audit metadata로 유지합니다. 보고서 상품 후보는
shortlist의 최대 3개만 사용할 수 있습니다. 패킷이나 shortlist가 없으면 원시
Stage 4 후보로 보충하지 않습니다.

## 허용

- 계산 JSON의 값을 이해하기 쉬운 한국어로 설명
- 위험 원인과 다음 행동 정리
- 공식 후보를 URL과 함께 정리
- 확인된 거래·결제 위험과 검토 우선도를 별도 축으로 설명
- 구조화된 금융 대응·질문을 상담 항목으로 정리
- Top 3의 rank·title·priority reason·numeric rationale·부족정보·기대 결정·
  다음 행동을 packet 순서 그대로 설명
- 핵심 숫자에 `[source: JSON.path]` 표시

## 금지

- 숫자 재계산·수정·새 숫자 생성
- 확률이 없는데 확률 표현
- STRESS를 예측이라고 표현
- 승인·수익·손실회피 보장
- 거래·결제 위험을 공식 심사등급·부도확률·보험 인수판단으로 표현
- 결제·회수 위험을 이유로 환헤지 비율을 직접 변경
- shortlist 밖 Stage 4 원시 검색 후보를 사용자용 후보로 표시
- 공식 후보명·기관명·URL 또는 자격을 근거와 다르게 표현
- 상담 검토 순위를 승인·보험 인수·대출 심사 등급으로 표현
- `buffer_shortfall`을 지급불능·부도·필요 대출금으로 표현
- 예정 결제 노출액을 실제 현재 미수·미지급잔액으로 표현
- Stage 3 계산상 후보를 최적 추천·실행 지시로 표현
- Markdown 다운로드를 실제 예약·RM 전송·신청·내부심사 완료로 표현

critic은 각 숫자가 같은 줄에 표시된 유효한 JSON path의 실제 값과 연결되는지,
시나리오 표현, 무근거 확률, 보장 문구, 필수 섹션, Stage 4 상품 근거를 검사합니다.
패킷이 있으면 거래·결제 위험과 금융 대응의 `consultation.*` 근거, 위험 유형·
상담 Top 3의 rank·제목·숫자·expected decision·next action 일치,
shortlist 상품명·기관명·URL 일치와 예정노출·버퍼·RM handoff 책임 경계도
추가 검사합니다.
결과는 score, numeric consistency, evidence quality, recommendation consistency,
prohibited claims, missing sections, revision instructions로 구조화됩니다. 수정 지시는
실제 재작성 prompt에 전달되며 `revision_count`는 최대 1입니다.

fallback은 같은 source bundle을 template에 직접 넣고 Stage 3 후보 세 건과
ConsultationPacket의 Top 3·숫자·부족정보·기대 결정·다음 행동·공식 shortlist를
추적하므로 LLM이 순서, 계산 결과나 상품 범위를 바꿀 수 없습니다. 패킷이 없는
legacy 호출은 기존 Stage 4 근거 계약을 유지합니다.
