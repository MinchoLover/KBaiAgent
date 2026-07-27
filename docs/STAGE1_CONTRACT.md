# Stage 1 Integration Contract

팀원의 환율 분석 모델은 이 저장소에서 재구현하지 않습니다.

현재 팀 `kb_macro_ai`의 `krw_forecast_web_v1` 계약과 HTTP/file/mock 연결은
[`STAGE1_INTEGRATION.md`](STAGE1_INTEGRATION.md)와
[`STAGE1_JSON_MAPPING.md`](STAGE1_JSON_MAPPING.md)가 canonical입니다.
아래 `schema_version=1.0` 계약은 기존 일반 시나리오 JSON과의 하위 호환 경로입니다.

## MANUAL_STRESS

기준 환율에 `-10%, -5%, -3%, 0%, +3%, +5%, +10%`를 적용합니다. 결과 kind는
항상 `STRESS`이고 확률은 없습니다. UI와 보고서에서 예측이라고 부르지 않습니다.

## EXTERNAL_STAGE1

JSON 업로드 또는 GET REST endpoint를 지원합니다.

```json
{
  "schema_version": "1.0",
  "currency": "USD",
  "quote_convention": "KRW_PER_1_FC",
  "rate_unit_foreign_currency": "1",
  "as_of": "2026-07-23T09:00:00+09:00",
  "target_date": "2026-10-21",
  "kind": "FORECAST",
  "scenarios": [
    {"name": "LOW", "rate": "1330", "is_base": false, "probability": "0.20"},
    {"name": "BASE", "rate": "1400", "is_base": true, "probability": "0.60"},
    {"name": "HIGH", "rate": "1515", "is_base": false, "probability": "0.20"}
  ]
}
```

## 검증과 정규화

- Stage 0 currency와 일치
- `as_of` timezone 포함 ISO datetime
- target date ISO 날짜; 불일치는 적용 규칙과 warning으로 공개
- base 정확히 하나, name 중복 금지
- 모든 rate와 rate unit은 양수
- `KRW_PER_1_FC`로 통일
- 100 JPY 등의 환율은 rate를 unit으로 나눠 1통화 단위로 정규화
- probability가 전부 있으면 각 값 0~1, 합 1 ± 0.0001
- 일부 또는 전부 없으면 확률 지표 금지

endpoint는 `STAGE1_TIMEOUT_SECONDS` 내에 응답해야 합니다. network, JSON, schema,
validation 실패 시 `MANUAL_FALLBACK`으로 명시해 수동 스트레스를 생성합니다.

## REST outbound 보안

JSON payload 계약은 변경하지 않고 HTTP 경계만 검증합니다.

- 기본값은 HTTPS와 DNS가 확인된 public IP만 허용
- URL userinfo, fragment, redirect 거부
- loopback, private, link-local, multicast, reserved, unspecified IP 거부
- DNS가 여러 IP를 반환하면 하나라도 non-public인 경우 거부
- `STAGE1_ALLOWED_HOSTS`가 있으면 exact hostname만 허용
- 차단 또는 network 실패는 원문·URL을 로그에 쓰지 않고 `MANUAL_FALLBACK`

운영 예시:

```dotenv
STAGE1_ALLOWED_HOSTS=stage1.example.com
STAGE1_ALLOW_PRIVATE_ENDPOINTS=false
```

로컬 개발 endpoint가 필요한 경우에만 다음처럼 명시적으로 완화합니다.

```dotenv
STAGE1_ALLOWED_HOSTS=localhost
STAGE1_ALLOW_PRIVATE_ENDPOINTS=true
```

사설 endpoint 허용은 개발 전용이며 공개 배포에서는 사용하지 않습니다.
