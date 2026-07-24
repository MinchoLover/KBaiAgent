#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prompt import build_system_prompt, get_prompt_version  # noqa: E402
from schemas import ConfirmationState, TradeDocumentExtraction  # noqa: E402
from scripts.evaluate_extraction import (  # noqa: E402
    load_manifest,
    virtual_due_date,
)
from validators import (  # noqa: E402
    derive_due_date,
    required_evidence_gaps,
    validate_extraction,
)


def _load_label(row: Dict[str, Any]) -> TradeDocumentExtraction:
    with (ROOT / row["label_path"]).open("r", encoding="utf-8") as handle:
        return TradeDocumentExtraction.model_validate(json.load(handle))


def classify_candidate(
    row: Dict[str, Any],
    label: TradeDocumentExtraction,
) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    if row.get("split") != "train":
        reasons.append("split_is_not_train")
    if row.get("split") == "test":
        reasons.append("test_split_must_never_be_training_data")
    if not row.get("user_confirmed"):
        reasons.append("user_confirmation_missing")
    if not row.get("human_approved"):
        reasons.append("human_approval_missing")

    due_date = virtual_due_date(label)
    confirmations = ConfirmationState(
        currency_confirmed=True,
        amount_due_confirmed=True,
        due_date_confirmed=True,
        confirmed_due_date=(
            due_date if due_date and "|" not in due_date else None
        ),
        confirmed_by="manifest-human-review",
        confirmed_at="manifest-recorded",
    )
    validation = validate_extraction(
        label,
        company_role=label.company_role,
        company_country=row.get("company_country", "KR"),
        confirmations=confirmations,
    )
    if not validation.validation_pass:
        reasons.append("deterministic_validation_not_pass")
    raw_due, raw_source = derive_due_date(
        label.explicit_due_date,
        label.issue_date,
        label.payment_terms,
        contract_date=label.contract_date,
        document_type=label.document_type,
    )
    del raw_due
    if raw_source == "MISSING" and label.installments:
        raw_source = "INSTALLMENTS"
    evidence_gaps = required_evidence_gaps(label, raw_source)
    if evidence_gaps:
        reasons.append(
            "missing_required_evidence:{}".format(",".join(evidence_gaps))
        )
    return not reasons, reasons


def export_candidates(
    *,
    manifest_path: Path,
    candidate_path: Path,
    excluded_path: Path,
) -> Tuple[int, int]:
    rows = load_manifest(manifest_path)
    candidates: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    system_prompt = build_system_prompt()

    for row in rows:
        label = _load_label(row)
        included, reasons = classify_candidate(row, label)
        if included:
            candidates.append(
                {
                    "case_id": row["case_id"],
                    "document_path": row["document_path"],
                    "prompt_version": get_prompt_version(),
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": (
                                "첨부 거래 문서를 구조화하라. 로컬 문서 참조: "
                                + row["document_path"]
                            ),
                        },
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                label.model_dump(),
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        },
                    ],
                }
            )
        else:
            excluded.append(
                {
                    "case_id": row["case_id"],
                    "document_path": row["document_path"],
                    "reasons": reasons,
                }
            )

    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    with candidate_path.open("w", encoding="utf-8") as handle:
        for item in candidates:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    with excluded_path.open("w", encoding="utf-8") as handle:
        for item in excluded:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return len(candidates), len(excluded)


def main() -> int:
    included, excluded = export_candidates(
        manifest_path=ROOT / "dataset" / "manifest.jsonl",
        candidate_path=ROOT / "artifacts" / "fine_tuning_candidate.jsonl",
        excluded_path=ROOT / "artifacts" / "fine_tuning_excluded.jsonl",
    )
    print("included={} excluded={}".format(included, excluded))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
