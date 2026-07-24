# 환율·현금흐름 리스크 검토 보고서

## 1. 거래 요약

- 거래 방향: IMPORT [source: stage2.trade_type]
- 거래 통화: USD [source: stage2.currency]
- 거래 외화금액: 100000.00 [source: stage2.total_foreign_amount]
- 결제 확인값: 2026-10-18 [source: stage0.confirmation.confirmed_values.settlement_date]

## 2. 데이터 출처와 사용자 확인 여부

문서 파일 `sample_invoice.png`의 fingerprint를 기록했습니다. [source: stage0.confirmation.source_filename]
통화·금액·결제일 확인과 확인시각이 기록되었습니다. [source: stage0.confirmation.checks]

## 3. 환율 시나리오 성격

수동 환율 값은 예측이 아니라 스트레스 가정입니다. 적용 규칙: Stage 1 target_date가 거래 settlement_date와 일치하여 직접 적용 [source: stage1.kind] [source: stage1.application_rule]

## 4. 현금흐름 영향

- BASE 필요/수취 원화: 126239000.00 [source: stage2.base_required_or_proceeds_krw]
- 최악 손실 시나리오: STRESS_+10.00PCT [source: stage2.scenario_results]
- BASE 대비 손실: 12618900.00 [source: stage2.scenario_results]
- 결제 후 잔고: 71142100.00 [source: stage2.scenario_results]

## 5. 위험 경보

- 최초 최소운영자금 부족일: 없음 [source: stage2.scenario_results]
- 최대 최소운영자금 부족액: 0.00 [source: stage2.scenario_results]
- 대출한도 반영 후 부족액: 0.00 [source: stage2.scenario_results]

## 6. 전략 후보

- 후보 1: 선물환 1 · 분할환전 0 · 미헤지 0 · 최악손실 189000.00 · 비용가정 189000.00 · 제약 충족. 선물환 비중으로 최악 환율 손실을 제한; 입력된 손실·유동성 제약을 계산상 충족 [source: stage3.candidates.0]
- 후보 2: 선물환 0.9 · 분할환전 0.1 · 미헤지 0 · 최악손실 807345.00 · 비용가정 176400.00 · 제약 충족. 선물환 비중으로 최악 환율 손실을 제한; 분할환전 비중으로 시점 집중을 완화; 입력된 손실·유동성 제약을 계산상 충족 [source: stage3.candidates.1]
- 후보 3: 선물환 0.8 · 분할환전 0.2 · 미헤지 0 · 최악손실 1425690.00 · 비용가정 163800.00 · 제약 충족. 선물환 비중으로 최악 환율 손실을 제한; 분할환전 비중으로 시점 집중을 완화; 입력된 손실·유동성 제약을 계산상 충족 [source: stage3.candidates.2]

위 후보는 확정 자문이 아니라 입력 가정 아래 계산된 검토안입니다.
[source: stage3.status]

## 7. 금융상품·제도 후보와 출처

- 신시장진출지원자금 등 정책자금 확인 — 중소벤처기업진흥공단 ([공식 출처](https://kdoctor.kosmes.or.kr/support/policy.do)); 자격·승인 조건은 상담 필요 [source: stage4.candidates.0]
- 옵션형 환변동보험 검토 — 한국무역보험공사 ([공식 출처](https://ksure.or.kr/rh-kr/cntnts/i-264/web.do)); 자격·승인 조건은 상담 필요 [source: stage4.candidates.1]
- 은행 선물환·외환스왑 상담 — KB국민은행 ([공식 출처](https://fx.kbstar.com/quics?page=C110657)); 자격·승인 조건은 상담 필요 [source: stage4.candidates.2]
- 환변동보험 검토 — 한국무역보험공사 ([공식 출처](https://www.ksure.or.kr/rh-fx/cntnts/i-513/web.do)); 자격·승인 조건은 상담 필요 [source: stage4.candidates.3]
- 수출입기업 외화예금 상담 — KB국민은행 ([공식 출처](https://img2.kbstar.com/obj/ocommon/kb20210405.pdf)); 자격·승인 조건은 상담 필요 [source: stage4.candidates.4]

## 8. 필요한 추가 정보

- 실제 은행 스프레드·수수료와 선물환 견적
- 기관별 최신 자격·한도·신청기간
- 확정된 원화 입출금 일정과 기존 헤지 계약서

## 9. 은행 상담 시 질문 목록

- 결제일과 통화 기준으로 가능한 선물환 한도와 전체 비용은 무엇인가?
- 중도 변경·조기결제·over-hedge 발생 시 조건은 무엇인가?
- 외화예금 및 환변동보험과 조합할 때 중복 노출은 없는가?

## 10. 가정·한계·면책

본 결과는 제공된 입력의 결정론적 계산과 공식자료 후보 정리이며 금융자문·승인·보장을
의미하지 않습니다. 실제 거래 전 은행·보험기관·전문가 확인이 필요합니다.
