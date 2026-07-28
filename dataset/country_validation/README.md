# 미국·브라질 합성 무역문서 검증 세트

실제 개인정보·기업정보·계좌·식별번호·로고·서명·도장을 사용하지 않은 평가 전용
문서 8건입니다. 모든 회사명은 `Synthetic`, `Test`, `Fictional`, `Sandbox` 중
하나를 포함하며 문서 상단에 법적 효력이 없다는 영문·한글 경고가 있습니다.
브라질 문서에는 포르투갈어 경고도 있습니다.

이 세트는 기존 `dataset/manifest.jsonl` 17건과 회귀 기준선을 변경하지 않도록
별도 manifest로 격리했습니다. 8건 모두 `split=test`,
`human_approved=false`, `user_confirmed=false`,
`fine_tuning_eligible=false`이며 파인튜닝 후보에서 영구 제외됩니다.

## 사례

| ID | 국가·방향 | 형식 | 핵심 검증점 | 예상 상태 |
| --- | --- | --- | --- | --- |
| `us_import_split_scan_001` | 미국 수입 | 이미지형 PDF | 30/70 분할결제 합계 | 조건부 검토 |
| `br_import_advance_photo_002` | 브라질 수입 | JPG 사진 | 20% 선지급과 80% 잔금 | 조건부 검토 |
| `us_export_net60_scan_003` | 미국 수출 | 이미지형 PDF | 명시 due 없이 Net 60 결정론 파생 | 조건부 검토 |
| `br_export_bl_event_photo_004` | 브라질 수출 | JPG 사진 | B/L date 부재, 사건 기준일 미계산 | 조건부 검토 |
| `us_import_balance_scan_005` | 미국 수입 | 이미지형 PDF | Grand Total이 아닌 Balance Due 선택 | 조건부 검토 |
| `br_export_mixed_split_scan_006` | 브라질 수출 | 이미지형 PDF | 두 번째 분할일 미확정 | 차단 |
| `us_import_missing_currency_photo_007` | 미국 수입 | JPG 사진 | 숫자만 있고 통화 누락 | 차단 |
| `br_export_occluded_due_photo_008` | 브라질 수출 | JPG 사진 | 금액은 판독, 결제일만 가림 | 차단 |

`expected_validation_status`는 시나리오 설계 상태입니다. 4번은 문서 자체가 잘못된
것이 아니라 B/L date를 사람이 보완하면 진행 가능한 조건부 사례입니다. 다만 현재
evaluator의 자동 문서 PASS는 모든 핵심값이 완성되어야 하므로 4번도 자동 PASS에는
포함되지 않습니다.

## 구조

```text
dataset/country_validation/
  documents/                  # PDF 4건, JPG 4건
  labels/                     # TradeDocumentExtraction 정답
  predictions/fixture/        # 평가 파이프라인 자체 검증용
  manifest.jsonl
  README.md
```

PDF 4건은 텍스트 레이어가 없는 단일 페이지 스캔 PDF입니다. label의
`FieldEvidence.source_text`는 생성 원문과 문자 단위로 맞춘 합성 ground truth이지,
production OCR이 자동 검증했다는 뜻이 아닙니다. 현재 Stage 0 정책대로 이미지·스캔
문서는 `OCR_REQUIRED` 또는 필드별 사용자 확인 없이 계산 단계로 전달하면 안 됩니다.

## 재생성

고정 seed와 고정 PDF metadata를 사용하므로 같은 코드·Pillow 버전에서 같은 입력은
동일한 파일 바이트를 만듭니다.

```bash
python scripts/generate_country_validation_dataset.py
python scripts/generate_country_validation_dataset.py --json-only
```

첫 명령은 문서·label·fixture·manifest를 모두 재생성하고, 두 번째 명령은 문서
이미지를 유지한 채 JSON과 manifest만 재생성합니다.

## API 없는 평가

```bash
python scripts/evaluate_extraction.py \
  --mode offline \
  --manifest dataset/country_validation/manifest.jsonl \
  --predictions-dir dataset/country_validation/predictions/fixture \
  --reports-dir reports/country_validation
```

fixture prediction은 label과 같은 값으로 evaluator의 로딩·정규화·지표·보고서
파이프라인만 검사합니다. 현재 결과의 필드 일치율 100%는 모델 정확도 주장이
아닙니다. 안전하게 비워 둔 4·6·7·8번 때문에 자동 문서 PASS는 4/8입니다.

## 향후 허가된 live 평가

아래 명령은 실제 API 호출과 비용이 발생할 수 있습니다. 사용자가 명시적으로
허가한 경우에만 실행하고, fixture 결과와 별도 디렉터리에 저장합니다.

```bash
python scripts/evaluate_extraction.py \
  --mode live \
  --manifest dataset/country_validation/manifest.jsonl \
  --predictions-dir dataset/country_validation/predictions/live \
  --reports-dir reports/country_validation_live \
  --max-cases 2
```

이 데이터셋 생성 작업에서는 live 평가를 실행하지 않았습니다.
