# 관세청 양국 무역통계 공식 fixture

이 디렉터리는 Golden 한국 판매자→브라질 구매자 수출 거래가 외부 API 없이도
재현되도록 관세청 수출입무역통계의 공식 공개 조회 결과를 보존한다. 통계는 거래의
시장 맥락만 제공하며 환율·현금흐름·헤지·상담 순위를 변경하지 않는다.

## Provenance

- 공식 서비스: 관세청 수출입무역통계
- 공개 조회 화면: <https://tradedata.go.kr/cts/index.do>
- OpenAPI 문서: <https://www.data.go.kr/data/15100475/openapi.do>
- 조회 범위: 한국 기준 상대국 `BR`, 국가 전체, 월별 `2024-07`~`2026-06`
- 수집일: `2026-08-01T22:55:18+09:00`
- 공개 조회 응답 단위: 천 USD
- 정규화: 쉼표 제거 후 `Decimal(value) * 1000`; 결측월 생성 금지

`raw/kr_br_country_2024-07_2026-06.json`은 공식 공개 응답의 TOTAL record와
24개 월 record에서 식별·통계 원문 필드와 문자열을 값 변경 없이 기록한 raw
record asset이다. HTTP 세션 정보와 화면 전용 부가 필드는 저장하지 않았다.
`snapshot_kr_br_country_v1.json`은 이를 USD 단위의 strict schema로 정규화한
snapshot이다.

## Integrity

- raw SHA-256:
  `16fcfc5222aab3e9b58dc3481cd130c411dbbcb4b103f994a1b42d872edb9cb5`
- normalized canonical SHA-256:
  `3e3120223e00013fcfbe9168bb794be21834c3c329b58d618fa84c09308e6b5b`
- snapshot version: `2026.08.01-kr-br-country-v1`

공개 화면의 월별 금액은 천 달러 단위 반올림 값이므로 월별 합계와 공식 TOTAL의
차이는 최대 USD 1,000까지만 허용한다. 각 월에서는 저장된 수지와
`수출-수입`의 차이도 같은 반올림 허용범위를 넘으면 검증에 실패한다.

```bash
python scripts/verify_trade_statistics_fixture.py
```

갱신 시 기존 파일을 자동 덮어쓰지 않는다. 공식 원자료를 다시 조회해 새 version의
raw asset과 normalized snapshot을 만들고, hash와 월별/TOTAL 결합 검증을 모두
통과시킨 뒤 registry에 구조적 키 `(reporter, partner, hs_code, version)`로 추가한다.
