#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.demo import run_offline_demo  # noqa: E402


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            _jsonable(value),
            handle,
            ensure_ascii=False,
            indent=2,
        )
        handle.write("\n")


def main() -> int:
    result = run_offline_demo()
    _write_json(
        ROOT / "samples" / "sample_extraction.json",
        result["extraction"],
    )
    _write_json(
        ROOT / "samples" / "stage1_scenarios.json",
        result["stage1"],
    )
    _write_json(
        ROOT / "samples" / "company_cashflow.json",
        result["stage2_input"],
    )
    _write_json(
        ROOT / "samples" / "expected_stage2.json",
        result["stage2"],
    )
    _write_json(
        ROOT / "samples" / "expected_stage3.json",
        result["stage3"],
    )
    _write_json(
        ROOT / "samples" / "expected_stage4.json",
        result["stage4"],
    )
    _write_json(
        ROOT / "samples" / "expected_report.json",
        result["report"],
    )
    report_path = ROOT / "samples" / "expected_report.md"
    with report_path.open("w", encoding="utf-8") as handle:
        handle.write(result["report"].markdown.rstrip() + "\n")
    print("demo outputs generated in samples/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
