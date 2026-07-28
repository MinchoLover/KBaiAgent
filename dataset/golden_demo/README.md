# Golden Trade Demo

`golden_export_contract.pdf`는 KBaiAgent 메인 성공 데모를 위한 2페이지 영문 합성
매매계약서입니다. 이미지형 country validation benchmark와 달리 실제 PDF 텍스트
레이어가 있어 field evidence를 페이지별로 결정론 검증할 수 있습니다.

## 파일

- `golden_export_contract.pdf`: 합성·법적 효력 없음 표시가 모든 페이지에 있는
  한국 판매자/브라질 구매자 USD 100,000 수출계약
- `expected_extraction.json`: 기존 `TradeDocumentExtraction` schema로 검증되는
  expected data와 짧은 exact evidence quote
- `demo_inputs.json`: 계약서 밖에서 사람이 확인해야 하는 거래처 관계·보험·헤지·
  기업 자금 입력, 국가 정규화 audit 기대값과 Stage 1 horizon 확인

`letter_of_credit`와 `guarantee`는 현재 extraction schema 필드가 아니므로
`expected_extraction.json`에 임의 필드를 추가하지 않았습니다. 해당 계약 문구와
상태는 `demo_inputs.json`의 `document_facts_outside_extraction_schema`에
분리했습니다.

## 재생성

```bash
python scripts/generate_golden_trade_demo.py
```

생성기는 고정 PDF object 순서, built-in Helvetica font와 고정 metadata를 사용합니다.
같은 코드에서는 byte-identical PDF와 JSON을 생성합니다.

## 주장 경계

Expected data는 API-free Golden fixture 및 evaluator/evidence pipeline 검증용입니다.
Live extraction이 아니며 모델 정확도 주장에 사용할 수 없습니다. Golden PDF의
실제 OpenAI 추출은 별도 승인과 새 immutable Run ID가 필요한 후속 작업입니다.
