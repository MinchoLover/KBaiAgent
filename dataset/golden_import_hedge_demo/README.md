# Golden 단일 USD 수입 지급 헤지 데모

이 디렉터리는 KBaiAgent의 실제 업로드 경로와 외부 헤지 참고 어댑터를
검증하기 위한 합성·비법적 문서 1건이다.

## 고정 시나리오

| 항목 | 값 |
| --- | --- |
| 문서 | `golden_import_payable_contract.pdf` |
| PDF SHA-256 | `fbd4c4dbdf0f92d459e19acf2af4a1e2ee3cd0916f43576290d54b040662550b` |
| 회사 역할·국가 | `BUYER` / `KR` |
| 판매자·구매자 국가 | `US` / `KR` |
| 거래 방향 | `IMPORT` |
| 통화·예정 지급액 | `USD` / `100000.00` |
| 지급일 | `2026-08-27` |
| 분할결제 | 없음 · 단일 지급 |
| 결제용 보유 USD | `10000.00` |
| 기존 선물환 | `0.00` |
| 외부 헤지 순노출 | `90000.00` |

PDF는 2페이지 텍스트 레이어를 가지며 모든 페이지에
`SYNTHETIC SAMPLE - NOT LEGALLY BINDING`이 표시된다. 실제 주소, 연락처,
계좌, 등록번호, 로고, 서명과 도장은 없다.

## 파일 역할

- `golden_import_payable_contract.pdf`: 사용자가 Streamlit에 직접 첨부할 문서
- `expected_extraction.json`: API-free 파이프라인 검증용 예상 구조화 값과
  정확한 페이지별 evidence
- `demo_inputs.json`: 계약서 밖에서 사용자가 확인해야 하는 회사 현금,
  보유외화, 외부 모델 제약과 주장 경계

Expected extraction은 모델 정확도 정답 발표용이 아니다. API-free 테스트에서
업로드 안전검사, 텍스트 evidence, 확인 gate, Stage 2/3와 외부 어댑터 결속을
재현하는 fixture다. 실제 문서 추출 성능을 확인하려면 별도 승인된 Live 추출을
실행해야 한다.

## 결정론 생성과 API-free 검증

```bash
python scripts/generate_golden_import_hedge_demo.py
python scripts/verify_golden_import_hedge_flow.py
python -m unittest tests.test_golden_import_hedge_demo -v
```

일상 검증에서는 고정 PDF를 다시 생성할 필요가 없다. 생성기를 실행했다면
전후 SHA-256이 위 값과 같은지 확인한다.

기본 검증 명령은 OpenAI, 환율 API, 외부 네트워크와 `kb_macro_ai` 실행을
사용하지 않는다. 실제 PDF bytes를 upload guard와 text extractor에 통과시킨
후 expected fixture를 모델 출력의 test double로 명시적으로 사용한다.

## Streamlit 직접 첨부 순서

1. `python -m streamlit run app.py`로 앱을 연다.
2. `거래문서 등록하기`를 누른다.
3. `실제 문서 분석`, `구매자 · BUYER`, 회사 국가 `KR`을 선택한다.
4. `golden_import_payable_contract.pdf`를 첨부한다.
5. `문서 분석하고 거래정보 채우기`를 누른다.
6. `IMPORT / USD / 100000.00 / 2026-08-27 / 단일 지급`과 원문 evidence를
   대조하고 다섯 핵심 확인 항목을 체크해 거래를 확정한다.
7. 금융 리스크 분석에서 기준일 `2026-07-29`, 현재 원화 현금
   `140000000`, 최소 운영자금 `10000000`, 신용한도 `0`, 보유 USD
   `10000`, 허용 환손실 `5000000`, 기존 헤지 `0`을 입력한다.
8. 환율·자금 위험을 계산하고 기존 Stage 3의 세 계산상 비교안을 확인한다.
9. `외부 환헤지 조합 참고 결과`에서 별도 제약조건과 목업 견적 사용을
   확인한 뒤 외부 모델 실행 또는 고정 파일 검증 버튼을 누른다.
10. 외부 결과가 `REFERENCE_ONLY / MOCK`, 후보 3개이고 Stage 4·상담
    리포트에는 전달되지 않는지 확인한다.

실제 문서 분석 5단계는 OpenAI 추출 설정이 있어야 한다. 이 디렉터리의
API-free 테스트 통과를 Live 추출 성공으로 표현하면 안 된다. 고정
`kb_macro_ai` local CLI 설정과 정확한 클릭 순서는
`docs/KB_MACRO_HEDGE_REFERENCE_RUNBOOK.md`를 따른다.
