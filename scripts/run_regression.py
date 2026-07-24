#!/usr/bin/env python3
import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_extraction import evaluate  # noqa: E402


CORE_FIELDS = [
    "currency",
    "amount_due",
    "required_date",
    "due_date",
    "trade_type",
]


def _load(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _baseline_payload(summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "core_field_accuracy": summary["core_field_accuracy"],
        "hallucination_rate": summary["hallucination_rate"],
        "document_pass_rate": summary["document_pass_rate"],
        "case_results": summary["case_results"],
    }


def compare_metrics(
    baseline: Dict[str, Any],
    current: Dict[str, Any],
) -> List[str]:
    failures: List[str] = []
    for field in CORE_FIELDS:
        baseline_value = Decimal(
            str(baseline["core_field_accuracy"].get(field, 0))
        )
        current_value = Decimal(
            str(current["core_field_accuracy"].get(field, 0))
        )
        if baseline_value - current_value >= Decimal("0.01"):
            failures.append(
                "{} accuracy가 {:.2%}에서 {:.2%}로 1%p 이상 하락".format(
                    field,
                    baseline_value,
                    current_value,
                )
            )

    baseline_hallucination = Decimal(str(baseline["hallucination_rate"]))
    current_hallucination = Decimal(str(current["hallucination_rate"]))
    if current_hallucination > baseline_hallucination:
        failures.append(
            "hallucination rate가 {:.2%}에서 {:.2%}로 상승".format(
                baseline_hallucination,
                current_hallucination,
            )
        )

    baseline_pass = Decimal(str(baseline["document_pass_rate"]))
    current_pass = Decimal(str(current["document_pass_rate"]))
    if current_pass < baseline_pass:
        failures.append(
            "document pass rate가 {:.2%}에서 {:.2%}로 하락".format(
                baseline_pass,
                current_pass,
            )
        )

    baseline_cases = baseline.get("case_results", {})
    current_cases = current.get("case_results", {})
    for case_id, old_result in baseline_cases.items():
        new_result = current_cases.get(case_id, {})
        if old_result.get("passed") and not new_result.get("passed"):
            failures.append("{} 문서 PASS가 회귀".format(case_id))
        for field, old_match in old_result.get("core_fields", {}).items():
            if old_match and not new_result.get("core_fields", {}).get(field):
                failures.append(
                    "{}의 {} 핵심 필드가 회귀".format(case_id, field)
                )
    return list(dict.fromkeys(failures))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        default="reports/baseline_metrics.json",
    )
    parser.add_argument(
        "--current-summary",
        default="reports/eval_summary.json",
    )
    parser.add_argument(
        "--predictions-dir",
        default="dataset/predictions/fixture",
    )
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    summary_path = ROOT / args.current_summary
    current = evaluate(
        manifest_path=ROOT / "dataset" / "manifest.jsonl",
        predictions_dir=ROOT / args.predictions_dir,
        reports_dir=ROOT / "reports",
    )
    if summary_path != ROOT / "reports" / "eval_summary.json":
        current = _load(summary_path)

    baseline_path = ROOT / args.baseline
    if args.update_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        with baseline_path.open("w", encoding="utf-8") as handle:
            json.dump(
                _baseline_payload(current),
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")
        print("baseline updated: {}".format(baseline_path))
        return 0

    if not baseline_path.exists():
        print(
            "baseline이 없습니다. 먼저 --update-baseline을 명시적으로 실행하세요."
        )
        return 2
    failures = compare_metrics(_load(baseline_path), current)
    if failures:
        print("REGRESSION FAILED")
        for failure in failures:
            print("- {}".format(failure))
        return 1
    print("REGRESSION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
