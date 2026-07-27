# Dataset and Evaluations

## 구조

```text
dataset/
  documents/                 # 실제 업로드 자동 저장 금지
  labels/                    # TradeDocumentExtraction 정답
  predictions/fixture/       # API 없는 evaluator 자체 검증용
  manifest.jsonl
  synthetic/
    simple_invoice/
    payment_terms/
    installment_contract/
    adversarial/
```

16건의 가상 합성 문서와 기존 샘플 원본 참조 1건이 있습니다. 회사명은 모두 가상이고
합성 문서 상단에 `TEST DOCUMENT - NO LEGAL EFFECT`가 있습니다. balance due,
Net 30/60/90, 명시 due, 분할결제, due 누락, 혼합 날짜, 다중통화, 수입·수출,
JPY 100단위, 흐린 이미지, prompt injection, due 충돌을 포함합니다.
당사자 이름과 국가는 같은 실제 원문을 재사용할 수 있지만
`seller_name`/`seller_country`/`buyer_name`/`buyer_country` 각각의 정확한 evidence
항목으로 정답에 기록합니다.

manifest의 `split=test`는 평가 전용이고 fine-tuning에서 영구 제외됩니다.
`human_approved=false`인 가상 생성 정답도 승인 전에는 학습 후보가 아닙니다.

문서 이미지를 바꾸지 않고 정답 JSON 계약만 재생성할 때는 다음을 사용합니다.

```bash
python scripts/generate_synthetic_dataset.py --json-only
```

## 평가

```bash
python scripts/evaluate_extraction.py --mode offline
python scripts/evaluate_extraction.py --mode live --max-cases 2
```

offline은 저장 prediction과 label을 비교합니다. live는 실제 문서를 모델로 추출해
`predictions/`에 사용량 metadata와 함께 저장한 뒤 같은 evaluator를 실행합니다.
live 파일은 모델 원출력 `raw_extraction`과 결정론 보정 후 `extraction`을 함께
보존해 실패 원인을 분리합니다. 문서 원문 자체는 저장하지 않습니다.

지표:

- field exact / normalized match
- currency, amount exact, amount tolerance, date accuracy
- required field completion, hallucination rate
- evidence coverage, human review recall, document pass rate
- latency, tokens, 선택적 추정 API cost

문서 PASS:

1. currency 정확
2. amount_due 정확
3. 필수 발행/계약일과 결제일 정확
4. critical field hallucination 없음
5. validation CRITICAL 없음

정보가 실제 문서에 없는 정답 abstention이나 의도된 충돌은 필드 exact가 맞아도 문서
PASS가 아닐 수 있습니다. 이는 안전한 자동 전달 기준입니다.

## Regression

```bash
python scripts/run_regression.py --update-baseline  # 승인된 변경에서만
python scripts/run_regression.py
```

핵심 필드가 1%p 이상 하락, hallucination 상승, document PASS 하락 중 하나라도 있으면
실패하며 회귀 case를 출력합니다. baseline 갱신은 자동이 아니라 명시 옵션입니다.
기본 fixture 회귀는 evaluator·schema·validator의 결정론적 회귀를 검사합니다.
프롬프트 자체의 모델 품질 회귀는 같은 고정 test split에서 생성한 승인된 live prediction
snapshot과 live baseline을 별도로 보존해 비교해야 합니다.

## Few-shot과 fine-tuning

`prompts/few_shot_examples.json`은 요청 시 참고하는 정답 예시이며 fine-tuning이
아닙니다. `scripts/export_finetuning_candidates.py`도 job을 실행하지 않습니다.
train split, 사용자 확인, 모든 필수 evidence, 결정론 PASS, 사람 승인을 모두 만족한
사례만 후보 JSONL로 변환하고 나머지는 제외 사유를 기록합니다.
