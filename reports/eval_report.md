# Extraction Evaluation Report

- Cases evaluated: 17
- Currency accuracy: 100.00%
- Amount exact accuracy: 100.00%
- Amount tolerance accuracy: 100.00%
- Date exact accuracy: 100.00%
- Required field completion: 100.00%
- Hallucination rate: 0.00%
- Evidence coverage: 100.00%
- Human review recall: 100.00%
- Document pass rate: 82.35%
- Average latency (seconds): 0
- Average estimated API cost/document: 0

## Interpretation

Fixture predictions validate the evaluation pipeline; they do not measure live model quality. Run `--mode live` on the same manifest for a real baseline. Source-incomplete or intentionally conflicting documents can correctly fail the document PASS rule even when extraction exactly matches the label.

## Failure count

- 3 field/document failures
