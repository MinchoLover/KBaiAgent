# Country environment offline snapshot

`snapshot_v1.json`은 T4 국가·무역환경 검토의 공개 공식 원값만 보존하는
versioned offline snapshot이다. runtime과 테스트는 외부 네트워크를 호출하지
않는다.

- snapshot version: `2026.07.29-v1`
- snapshot ID: `country-environment-2026-07-29`
- canonical SHA-256:
  `095c5e38a88403449214ba899e05d07831f1b2a44932f2ebe2beaa65045fb757`
- 지원 국가: `BR`, `US`
- OECD 기준일: `2026-06-26`
- World Bank 게시·갱신 기준일: `2026-07-13`
- WTO 관세 관측연도: `2025`
- 검증일: `2026-07-29`

공식 URL, 관측기간, 원값, 단위, 제한적 해석과 한계는 각 source record에
함께 저장한다. 전체 PDF·웹페이지 또는 응답 payload는 저장하지 않는다.

## 공식 source

- OECD: [Country Risk Classifications, 2026-06-26](https://www.oecd.org/content/dam/oecd/en/topics/policy-sub-issues/country-risk-classification/cre-crc-current-english.pdf)
- World Bank: [BR GDP API](https://api.worldbank.org/v2/country/BR/indicator/NY.GDP.MKTP.KD.ZG?format=json&date=2020:2026&per_page=100),
  [US GDP API](https://api.worldbank.org/v2/country/US/indicator/NY.GDP.MKTP.KD.ZG?format=json&date=2020:2026&per_page=100)
  및 같은 공식 API 정의의 CPI·경상수지 지표
- WTO BR: [trade profile](https://ttd.wto.org/en/profiles/brazil/),
  [member page](https://www.wto.org/english/thewto_e/countries_e/brazil_e.htm),
  [2022 TPR](https://www.wto.org/english/tratop_e/tpr_e/tp532_crc_e.htm)
- WTO US: [trade profile](https://ttd.wto.org/en/profiles/united-states-of-america),
  [member page](https://www.wto.org/english/thewto_e/countries_e/usa_e.htm),
  [2022 TPR](https://www.wto.org/english/tratop_e/tpr_e/tp534_crc_e.htm)

World Bank는 지표별 실제 관측연도를 저장한다. BR 세 지표와 US GDP·경상수지는
2025, US CPI 최신 비결측치는 2024다. WTO membership 기간은
`1995-01-01 to 2026-07-29`, MFN 관세는 2025, TPR은 2022다.

## 재현과 검증

loader는 strict Pydantic schema, snapshot version, 공식 HTTPS host allowlist,
국가·source axis·World Bank indicator 완전성, OECD 핵심값과 canonical
SHA-256 hash를 검증한다. source record 순서와 무관하게 ID 순으로 정렬한
canonical JSON에서 hash를 계산한다. 하나라도 맞지 않으면 분석 서비스는
`INSUFFICIENT_INFORMATION`으로 fail closed한다.

갱신 시에는 다음을 모두 수행한다.

1. OECD·World Bank·WTO 1차 공식 출처에서 원값과 자료기간을 사람이 확인한다.
2. 기존 파일을 자동 덮어쓰지 않고 새 snapshot version 후보를 별도 검토한다.
3. 서로 다른 관측연도와 null을 그대로 보존한다.
4. canonical hash를 다시 계산하고 snapshot·assessment·integration 테스트를
   실행한다.
5. `python scripts/verify.py`에 해당하는 저장소 Python 3.9 환경 검증을
   통과한 뒤에만 commit한다.
