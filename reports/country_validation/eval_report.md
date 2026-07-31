# Extraction Evaluation Report

- Evaluation mode: FIXTURE
- Purpose: EVALUATOR_PIPELINE_VALIDATION
- Synthetic dataset: true
- Real customer documents: false
- Statistical generalization allowed: false
- Cases evaluated: 8
- Successful API/prediction records: 8
- Failed API/prediction records: 0
- Timeout records: 0
- Currency accuracy: 100.00%
- Amount exact accuracy: 100.00%
- Amount tolerance accuracy: 100.00%
- Date exact accuracy: 100.00%
- Required field completion: 100.00%
- Hallucination rate: 0.00%
- Evidence claim coverage (not source verification): 100.00%
- Human review recall: 100.00%
- Document pass rate: 50.00%
- Average latency (seconds): 0
- Total input tokens: 0
- Total output tokens: 0
- Estimated total API cost: 0

## Benchmark fields

- currency: 100.00%
- amount_due: 100.00%
- explicit_due_date: 100.00%
- derived_due_date: 100.00%
- trade_type: 100.00%
- company_role: 100.00%
- seller_country: 100.00%
- buyer_country: 100.00%
- document_type: 100.00%

## Payment terms and abstention

- Installment amount accuracy: 100.00%
- Installment total consistency: 100.00%
- Advance payment identification: 100.00%
- Event-based due-date preservation: 100.00%
- Unknown due-date abstention: 100.00%
- Unsupported currency guesses: 0
- Unsupported date guesses: 0
- Unsupported amount guesses: 0
- False-positive fields: 0
- General abstention accuracy: 100.00%
- Human-review identification: 100.00%
- Blocked-case accuracy: 100.00%

## Evidence

- Core field evidence coverage: 100.00%
- Evidence field-link consistency: 100.00%
- Confirmed values without evidence: 0
- Confirmed values without source_text: 0
- Image evidence safety accuracy: 0.00%

## Interpretation

Fixture predictions validate the evaluator pipeline only. They do not measure live model or OCR accuracy and must not be presented as an AI accuracy result.

The Stage 0 intake path independently verifies text-PDF quotes against source pages. Image/scanned documents do not have an independently verified OCR layer and require field-level human confirmation.

Source-incomplete or intentionally conflicting documents can correctly fail the document PASS rule even when extraction matches the label.

## Failure count

- 4 field/document failures
