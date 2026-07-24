# 정답 데이터셋

`manifest.jsonl`이 문서, 정답 label, 난이도, split, 사람 승인 상태를 연결한다.
`documents/`는 실제 사용자가 제공한 문서를 자동 복사하는 위치가 아니다. 기존 저장소
샘플은 `samples/...` 원본 경로를 manifest에서 직접 참조한다.

`synthetic/`에는 완전히 가상인 문서가 있으며 모든 문서 상단에
`TEST DOCUMENT - NO LEGAL EFFECT`가 표시된다. 생성 명령:

```bash
python scripts/generate_synthetic_dataset.py
```

`labels/`는 `TradeDocumentExtraction`과 동일한 스키마다. `predictions/fixture/`는
API 키 없이 평가 파이프라인을 검증하기 위한 완전 일치 예측 fixture다. 이는 실제 모델
성능을 의미하지 않는다.

split 규칙:

- `test`: 평가 전용이며 fine-tuning 후보에서 항상 제외
- `train`: 사람 확인·승인·검증 PASS를 모두 만족할 때만 후보 가능
- `demo`: 화면 데모 전용

현재 항목은 자동 생성된 가상 정답이므로 `human_approved=false`다. 사람이 문서와 정답을
검수하기 전에는 fine-tuning 후보가 될 수 없다.
