# Baseline v1 Follow-up Tickets

이 문서는 `baseline-v1-full-20260729-0404-kst`에서 확인됐지만 국가
canonicalization 커밋에 포함하지 않는 합성문서 추출 실패를 기록합니다.
Baseline v1 산출물은 수정하거나 덮어쓰지 않습니다.

## P1-B-DATE-001 — Contract date 하루 차이

- 사례: `us_import_split_scan_001`
- 정답: `2026-08-05`
- Baseline v1 결과: `2026-08-06`
- 범위: 날짜 역할 구분 또는 vision 판독 원인 조사
- 이번 커밋: 원인 기록만 수행하며 날짜·prompt·추출 로직은 수정하지 않음

## P1-B-DOC-002 — Document type UNKNOWN

- 사례: `br_export_bl_event_photo_004`
- 정답: `SALES_CONTRACT`
- Baseline v1 결과: `UNKNOWN`
- 범위: 문서유형 판독 실패 원인 조사
- 이번 커밋: 원인 기록만 수행하며 schema·prompt·validator는 수정하지 않음

## P1-B-NAME-003 — 법인명 접미사 차이

- 사례: `br_export_occluded_due_photo_008`
- 정답 접미사: `Ltda.`
- Baseline v1 결과 접미사: `Ltd.`
- 범위: 법인명 원문 보존과 suffix 판독 원인 조사
- 이번 커밋: 원인 기록만 수행하며 회사명 정규화는 추가하지 않음

## 분리 원칙

각 항목은 국가 alias 개선과 별도 티켓·별도 논리 커밋으로 처리합니다. 테스트셋을
prompt 튜닝이나 파인튜닝 데이터로 사용하지 않으며, 개선 전후 Live 비교는 별도
승인을 받은 새 run ID로만 수행합니다.
