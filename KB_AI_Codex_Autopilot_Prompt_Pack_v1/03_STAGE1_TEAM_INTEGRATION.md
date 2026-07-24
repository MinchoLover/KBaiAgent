# Stage 1 팀원 결과 통합 프롬프트

너는 통합 책임자다. 팀원이 만든 Stage 1 환율 분석 결과를 현재 Stage 0/2 앱에 연결하라. Stage 1의 예측 알고리즘을 수정하거나 재구현하지 말고 **adapter와 contract test**만 담당하라.

진행:

1. 현재 Stage 1 샘플 JSON/endpoint 문서를 찾는다.
2. 현재 Stage 2의 scenario schema와 비교해 차이를 표로 정리한다.
3. `src/stage1/adapter.py` 또는 기존 대응 모듈에서 양쪽 형식을 분리한다.
4. 팀원 원본 응답을 보존하고 내부 canonical schema로 정규화한다.
5. quote convention, currency, target date, base scenario, probability, timezone, JPY unit을 검증한다.
6. endpoint timeout/retry/fallback을 구현한다.
7. Stage 1 실패 시 앱이 manual stress mode로 안전하게 전환되도록 한다.
8. raw payload와 normalized payload를 UI에서 개발자 모드로 확인할 수 있게 한다. secret은 가린다.
9. contract tests와 golden fixtures를 작성한다.
10. `docs/STAGE1_CONTRACT.md`와 팀 전달용 예제 JSON을 갱신한다.

Canonical schema는 최소 다음을 포함한다.

```json
{
  "schema_version": "1.0",
  "source": "STAGE1_EXTERNAL",
  "kind": "FORECAST",
  "currency": "USD",
  "quote_convention": "KRW_PER_1_FC",
  "rate_unit_foreign_currency": "1",
  "as_of": "2026-07-23T09:00:00+09:00",
  "target_date": "2026-10-21",
  "scenarios": [
    {"name":"LOW","rate":"1330","is_base":false,"probability":"0.20"},
    {"name":"BASE","rate":"1400","is_base":true,"probability":"0.60"},
    {"name":"HIGH","rate":"1515","is_base":false,"probability":"0.20"}
  ],
  "warnings": []
}
```

완료 조건:

- 팀원 샘플 fixture 통과
- malformed response 안전 실패
- probability incomplete 시 확률 지표 차단
- manual fallback 동작
- Stage 2 계산 코드는 Stage 1 구현 세부를 모름
- 전체 테스트와 verify PASS
