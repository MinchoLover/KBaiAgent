#!/usr/bin/env python3
import argparse
import json
import mimetypes
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas import TradeDocumentExtraction  # noqa: E402
from src.config import Settings  # noqa: E402
from src.document_intake.extractor import (  # noqa: E402
    extract_trade_document_with_metadata,
)
from validators import (  # noqa: E402
    calculate_net_due_date,
    validate_extraction,
)


FIELD_NAMES = [
    "document_type",
    "document_number",
    "seller_name",
    "seller_country",
    "buyer_name",
    "buyer_country",
    "company_role",
    "trade_type",
    "currency",
    "grand_total",
    "amount_due",
    "issue_date",
    "contract_date",
    "shipment_date",
    "explicit_due_date",
    "derived_due_date",
    "payment_terms",
    "incoterm",
    "installments",
    "evidence",
    "warnings",
    "missing_required_fields",
    "needs_human_review",
]
AMOUNT_FIELDS = {"grand_total", "amount_due"}
DATE_FIELDS = {
    "issue_date",
    "contract_date",
    "shipment_date",
    "explicit_due_date",
    "derived_due_date",
}


def _safe_path(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    if ROOT != path and ROOT not in path.parents:
        raise ValueError("manifest path가 저장소 밖을 가리킵니다.")
    return path


def load_manifest(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not row.get("case_id"):
                raise ValueError(
                    "manifest {}행에 case_id가 없습니다.".format(line_number)
                )
            rows.append(row)
    return rows


def _load_extraction(path: Path) -> Tuple[TradeDocumentExtraction, Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    metadata: Dict[str, Any] = {}
    if isinstance(data, dict) and "extraction" in data:
        metadata = data.get("metadata", {})
        data = data["extraction"]
    return TradeDocumentExtraction.model_validate(data), metadata


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _normalize_text(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, list):
        return [_normalize_text(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _normalize_text(item)
            for key, item in sorted(value.items())
        }
    return " ".join(str(value).strip().lower().split())


def normalize_field(field: str, value: Any) -> Any:
    if field in AMOUNT_FIELDS:
        return _decimal(value)
    if field == "currency" and value is not None:
        return str(value).strip().upper()
    if field in DATE_FIELDS and value is not None:
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError:
            return str(value)
    return _normalize_text(value)


def virtual_due_date(extraction: TradeDocumentExtraction) -> Optional[str]:
    if extraction.explicit_due_date:
        return extraction.explicit_due_date
    if extraction.derived_due_date:
        return extraction.derived_due_date
    base_date = (
        extraction.contract_date or extraction.issue_date
        if extraction.document_type == "SALES_CONTRACT"
        else extraction.issue_date or extraction.contract_date
    )
    calculated = calculate_net_due_date(base_date, extraction.payment_terms)
    if calculated:
        return calculated
    installment_dates = [
        item.due_date
        for item in extraction.installments
        if item.due_date
    ]
    if installment_dates and len(installment_dates) == len(
        extraction.installments
    ):
        return "|".join(installment_dates)
    return None


def required_date(extraction: TradeDocumentExtraction) -> Optional[str]:
    if extraction.document_type == "SALES_CONTRACT":
        return extraction.contract_date or extraction.issue_date
    return extraction.issue_date or extraction.contract_date


def core_values(extraction: TradeDocumentExtraction) -> Dict[str, Any]:
    return {
        "currency": normalize_field("currency", extraction.currency),
        "amount_due": _decimal(extraction.amount_due),
        "required_date": required_date(extraction),
        "due_date": virtual_due_date(extraction),
        "trade_type": extraction.trade_type,
    }


def _evidence_covered(
    extraction: TradeDocumentExtraction,
    field: str,
) -> bool:
    fields = {
        item.field
        for item in extraction.evidence
        if (
            item.source_text.strip()
            and item.extraction_type != "INFERRED"
        )
    }
    if field == "required_date":
        return "issue_date" in fields or "contract_date" in fields
    if field == "due_date":
        return bool(
            {"explicit_due_date", "payment_terms", "installments"}.intersection(
                fields
            )
        )
    if field == "trade_type":
        return {
            "seller_name",
            "seller_country",
            "buyer_name",
            "buyer_country",
        }.issubset(fields)
    return field in fields


def _cause_and_suggestion(
    field: str,
    expected: Any,
    actual: Any,
) -> Tuple[str, str]:
    if expected is None and actual is not None:
        return (
            "hallucination_or_conflict_resolution_error",
            "문서에 없는 값을 null로 유지하고 충돌 시 human review로 보낸다.",
        )
    if expected is not None and actual is None:
        return (
            "omission_or_ocr_failure",
            "해당 라벨의 evidence 예시와 OCR 품질 fixture를 프롬프트 평가에 추가한다.",
        )
    if field in AMOUNT_FIELDS or field == "amount_due":
        return (
            "amount_selection_or_normalization_error",
            "Balance Due 우선순위와 decimal 문자열 정규화를 회귀 테스트한다.",
        )
    if field in DATE_FIELDS or field in {"required_date", "due_date"}:
        return (
            "date_role_or_derivation_error",
            "날짜 라벨 구분과 Net N 결정론 계산을 점검한다.",
        )
    if field == "currency":
        return (
            "currency_ambiguity_error",
            "다중 통화 충돌 규칙과 통화 evidence를 강화한다.",
        )
    return (
        "field_extraction_mismatch",
        "해당 필드의 실패 사례를 few-shot 또는 검증 규칙에 추가한다.",
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def _document_pass(
    *,
    label: TradeDocumentExtraction,
    prediction: TradeDocumentExtraction,
    company_country: str,
) -> Tuple[bool, Dict[str, bool], List[str]]:
    expected = core_values(label)
    actual = core_values(prediction)
    core_match = {
        field: expected[field] == actual[field]
        for field in expected
    }
    expected_complete = all(value is not None for value in expected.values())
    critical_hallucination = any(
        expected[field] is None and actual[field] is not None
        for field in expected
    )
    validation = validate_extraction(
        prediction,
        company_role=label.company_role,
        company_country=company_country,
    )
    critical_codes = [
        issue.code
        for issue in validation.issues
        if issue.severity == "CRITICAL"
    ]
    passed = (
        expected_complete
        and all(core_match.values())
        and not critical_hallucination
        and not critical_codes
    )
    return passed, core_match, critical_codes


def evaluate_records(
    *,
    manifest_rows: List[Dict[str, Any]],
    predictions_dir: Path,
    amount_tolerance: Decimal = Decimal("0.01"),
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not amount_tolerance.is_finite() or amount_tolerance < 0:
        raise ValueError("amount_tolerance는 0 이상의 유한한 값이어야 합니다.")
    field_counts: DefaultDict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "exact": 0, "normalized": 0}
    )
    currency_total = currency_correct = 0
    amount_total = amount_exact = amount_tolerance_correct = 0
    date_total = date_correct = 0
    required_total = required_completed = 0
    hallucination_total = hallucination_count = 0
    evidence_total = evidence_covered = 0
    review_positive = review_true_positive = 0
    document_passes = 0
    failure_cases: List[Dict[str, Any]] = []
    case_results: Dict[str, Any] = {}
    latencies: List[Decimal] = []
    costs: List[Decimal] = []
    input_tokens = output_tokens = 0

    for row in manifest_rows:
        case_id = row["case_id"]
        label, unused_label_meta = _load_extraction(
            _safe_path(row["label_path"])
        )
        del unused_label_meta
        prediction_path = predictions_dir / "{}.json".format(case_id)
        prediction_error: Optional[str] = None
        prediction: Optional[TradeDocumentExtraction] = None
        metadata: Dict[str, Any] = {}
        if not prediction_path.exists():
            prediction_error = "missing_prediction_file"
        else:
            try:
                prediction, metadata = _load_extraction(prediction_path)
            except (
                OSError,
                UnicodeError,
                json.JSONDecodeError,
                TypeError,
                ValueError,
            ):
                prediction_error = "invalid_prediction_file"

        if prediction_error or prediction is None:
            failure_cases.append(
                {
                    "case_id": case_id,
                    "field": "__prediction__",
                    "expected": "prediction JSON",
                    "actual": None,
                    "cause": prediction_error,
                    "suggestion": (
                        "해당 case_id의 schema-valid prediction을 생성한다."
                    ),
                }
            )
            label_dict = label.model_dump()
            for field in FIELD_NAMES:
                field_counts[field]["total"] += 1
                if label_dict[field] is None:
                    hallucination_total += 1
            currency_total += 1
            if _decimal(label.amount_due) is not None:
                amount_total += 1
            for expected_date in (
                required_date(label),
                virtual_due_date(label),
            ):
                if expected_date is not None:
                    date_total += 1
            for expected_value in core_values(label).values():
                if expected_value is not None:
                    required_total += 1
                    evidence_total += 1
            if label.needs_human_review:
                review_positive += 1
            case_results[case_id] = {
                "passed": False,
                "core_fields": {},
                "validation_critical_codes": [
                    (
                        "MISSING_PREDICTION"
                        if prediction_error == "missing_prediction_file"
                        else "INVALID_PREDICTION"
                    )
                ],
            }
            continue

        latency = _decimal(metadata.get("latency_seconds"))
        if latency is not None:
            latencies.append(latency)
        cost = _decimal(metadata.get("estimated_api_cost"))
        if cost is not None:
            costs.append(cost)
        input_tokens += int(metadata.get("input_tokens") or 0)
        output_tokens += int(metadata.get("output_tokens") or 0)

        label_dict = label.model_dump()
        prediction_dict = prediction.model_dump()
        for field in FIELD_NAMES:
            expected_value = label_dict[field]
            actual_value = prediction_dict[field]
            field_counts[field]["total"] += 1
            if expected_value == actual_value:
                field_counts[field]["exact"] += 1
            if normalize_field(field, expected_value) == normalize_field(
                field,
                actual_value,
            ):
                field_counts[field]["normalized"] += 1
            if expected_value != actual_value:
                cause, suggestion = _cause_and_suggestion(
                    field,
                    expected_value,
                    actual_value,
                )
                failure_cases.append(
                    {
                        "case_id": case_id,
                        "field": field,
                        "expected": expected_value,
                        "actual": actual_value,
                        "cause": cause,
                        "suggestion": suggestion,
                    }
                )

            if expected_value is None:
                hallucination_total += 1
                if actual_value is not None:
                    hallucination_count += 1

        currency_total += 1
        if normalize_field("currency", label.currency) == normalize_field(
            "currency",
            prediction.currency,
        ):
            currency_correct += 1

        expected_amount = _decimal(label.amount_due)
        actual_amount = _decimal(prediction.amount_due)
        if expected_amount is not None:
            amount_total += 1
            if expected_amount == actual_amount:
                amount_exact += 1
            if (
                actual_amount is not None
                and abs(expected_amount - actual_amount) <= amount_tolerance
            ):
                amount_tolerance_correct += 1

        for expected_date, actual_date in (
            (required_date(label), required_date(prediction)),
            (virtual_due_date(label), virtual_due_date(prediction)),
        ):
            if expected_date is not None:
                date_total += 1
                if expected_date == actual_date:
                    date_correct += 1

        expected_core = core_values(label)
        actual_core = core_values(prediction)
        for field, expected_value in expected_core.items():
            if expected_value is not None:
                required_total += 1
                if actual_core[field] is not None:
                    required_completed += 1
                evidence_total += 1
                if _evidence_covered(prediction, field):
                    evidence_covered += 1

        if label.needs_human_review:
            review_positive += 1
            if prediction.needs_human_review:
                review_true_positive += 1

        passed, core_match, critical_codes = _document_pass(
            label=label,
            prediction=prediction,
            company_country=row.get("company_country", "KR"),
        )
        if passed:
            document_passes += 1
        else:
            if all(core_match.values()) and not critical_codes:
                cause = "source_missing_required_data"
                suggestion = (
                    "정확한 abstention으로 기록하고 사용자 보완 입력을 요구한다."
                )
            elif critical_codes:
                cause = "critical_validation_failure"
                suggestion = (
                    "CRITICAL 검증 오류를 해소하기 전 자동 전달을 차단한다."
                )
            else:
                cause = "critical_field_mismatch"
                suggestion = "핵심 필드 실패를 prompt regression에 추가한다."
            failure_cases.append(
                {
                    "case_id": case_id,
                    "field": "__document_pass__",
                    "expected": True,
                    "actual": False,
                    "cause": cause,
                    "suggestion": suggestion,
                    "validation_critical_codes": critical_codes,
                }
            )
        case_results[case_id] = {
            "passed": passed,
            "core_fields": core_match,
            "validation_critical_codes": critical_codes,
        }

    evaluated_count = len(case_results)
    exact_per_field = {
        field: _ratio(values["exact"], values["total"])
        for field, values in sorted(field_counts.items())
    }
    normalized_per_field = {
        field: _ratio(values["normalized"], values["total"])
        for field, values in sorted(field_counts.items())
    }
    core_field_accuracy = {
        field: _ratio(
            sum(
                1
                for result in case_results.values()
                if result.get("core_fields", {}).get(field)
            ),
            evaluated_count,
        )
        for field in (
            "currency",
            "amount_due",
            "required_date",
            "due_date",
            "trade_type",
        )
    }
    average_latency = (
        str(sum(latencies, Decimal("0")) / Decimal(len(latencies)))
        if latencies
        else None
    )
    average_cost = (
        str(sum(costs, Decimal("0")) / Decimal(len(costs)))
        if costs
        else None
    )
    summary: Dict[str, Any] = {
        "schema_version": "1.0",
        "cases_in_manifest": len(manifest_rows),
        "cases_evaluated": evaluated_count,
        "exact_match_accuracy_per_field": exact_per_field,
        "normalized_match_accuracy_per_field": normalized_per_field,
        "currency_accuracy": _ratio(currency_correct, currency_total),
        "amount_exact_accuracy": _ratio(amount_exact, amount_total),
        "amount_tolerance_accuracy": _ratio(
            amount_tolerance_correct,
            amount_total,
        ),
        "amount_tolerance": str(amount_tolerance),
        "date_exact_accuracy": _ratio(date_correct, date_total),
        "required_field_completion_rate": _ratio(
            required_completed,
            required_total,
        ),
        "hallucination_rate": _ratio(
            hallucination_count,
            hallucination_total,
        ),
        "evidence_coverage": _ratio(evidence_covered, evidence_total),
        "human_review_recall": _ratio(
            review_true_positive,
            review_positive,
        ),
        "document_pass_rate": _ratio(
            document_passes,
            evaluated_count,
        ),
        "average_latency_seconds": average_latency,
        "average_estimated_api_cost_per_document": average_cost,
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "core_field_accuracy": core_field_accuracy,
        "case_results": case_results,
    }
    return summary, failure_cases


def _estimated_cost(
    *,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    input_cost_per_million: Optional[Decimal],
    output_cost_per_million: Optional[Decimal],
) -> Optional[str]:
    if (
        input_tokens is None
        or output_tokens is None
        or input_cost_per_million is None
        or output_cost_per_million is None
    ):
        return None
    cost = (
        Decimal(input_tokens) / Decimal("1000000")
        * input_cost_per_million
        + Decimal(output_tokens) / Decimal("1000000")
        * output_cost_per_million
    )
    return format(cost, "f")


def run_live_predictions(
    *,
    manifest_rows: List[Dict[str, Any]],
    predictions_dir: Path,
    settings: Settings,
    case_ids: Optional[List[str]] = None,
    max_cases: Optional[int] = None,
    input_cost_per_million: Optional[Decimal] = None,
    output_cost_per_million: Optional[Decimal] = None,
) -> None:
    if not settings.live_extraction_ready:
        raise RuntimeError(
            "live 모드는 OPENAI_API_KEY와 "
            "ENABLE_LIVE_DOCUMENT_EXTRACTION=true가 필요합니다."
        )
    selected = [
        row
        for row in manifest_rows
        if not case_ids or row["case_id"] in case_ids
    ]
    if max_cases is not None:
        selected = selected[:max_cases]
    predictions_dir.mkdir(parents=True, exist_ok=True)

    for row in selected:
        document_path = _safe_path(row["document_path"])
        mime_type = mimetypes.guess_type(document_path.name)[0]
        label, unused_metadata = _load_extraction(
            _safe_path(row["label_path"])
        )
        del unused_metadata
        run = extract_trade_document_with_metadata(
            file_bytes=document_path.read_bytes(),
            filename=document_path.name,
            mime_type=mime_type,
            company_role=label.company_role,
            company_country=row.get("company_country", "KR"),
            settings=settings,
        )
        cost = _estimated_cost(
            input_tokens=run.usage.input_tokens,
            output_tokens=run.usage.output_tokens,
            input_cost_per_million=input_cost_per_million,
            output_cost_per_million=output_cost_per_million,
        )
        prediction = {
            "raw_extraction": run.raw_extraction.model_dump(),
            "extraction": run.extraction.model_dump(),
            "metadata": {
                "mode": "live",
                "model": run.usage.model,
                "prompt_version": run.usage.prompt_version,
                "request_id": run.usage.request_id,
                "latency_seconds": str(run.usage.latency_seconds),
                "input_tokens": run.usage.input_tokens,
                "output_tokens": run.usage.output_tokens,
                "total_tokens": run.usage.total_tokens,
                "attempts": run.usage.attempts,
                "estimated_api_cost": cost,
                "source_sha256": run.upload.sha256,
            },
        }
        with (
            predictions_dir / "{}.json".format(row["case_id"])
        ).open("w", encoding="utf-8") as handle:
            json.dump(prediction, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def write_reports(
    *,
    summary: Dict[str, Any],
    failure_cases: List[Dict[str, Any]],
    reports_dir: Path,
) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    with (reports_dir / "eval_summary.json").open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    with (reports_dir / "failure_cases.jsonl").open(
        "w",
        encoding="utf-8",
    ) as handle:
        for item in failure_cases:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    lines = [
        "# Extraction Evaluation Report",
        "",
        "- Cases evaluated: {}".format(summary["cases_evaluated"]),
        "- Currency accuracy: {:.2%}".format(summary["currency_accuracy"]),
        "- Amount exact accuracy: {:.2%}".format(
            summary["amount_exact_accuracy"]
        ),
        "- Amount tolerance accuracy: {:.2%}".format(
            summary["amount_tolerance_accuracy"]
        ),
        "- Date exact accuracy: {:.2%}".format(
            summary["date_exact_accuracy"]
        ),
        "- Required field completion: {:.2%}".format(
            summary["required_field_completion_rate"]
        ),
        "- Hallucination rate: {:.2%}".format(
            summary["hallucination_rate"]
        ),
        "- Evidence coverage: {:.2%}".format(
            summary["evidence_coverage"]
        ),
        "- Human review recall: {:.2%}".format(
            summary["human_review_recall"]
        ),
        "- Document pass rate: {:.2%}".format(
            summary["document_pass_rate"]
        ),
        "- Average latency (seconds): {}".format(
            summary["average_latency_seconds"]
        ),
        "- Average estimated API cost/document: {}".format(
            summary["average_estimated_api_cost_per_document"]
        ),
        "",
        "## Interpretation",
        "",
        "Fixture predictions validate the evaluation pipeline; they do not measure "
        "live model quality. Run `--mode live` on the same manifest for a real "
        "baseline. Source-incomplete or intentionally conflicting documents can "
        "correctly fail the document PASS rule even when extraction exactly "
        "matches the label.",
        "",
        "## Failure count",
        "",
        "- {} field/document failures".format(len(failure_cases)),
    ]
    (reports_dir / "eval_report.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def evaluate(
    *,
    manifest_path: Path,
    predictions_dir: Path,
    reports_dir: Path,
    amount_tolerance: Decimal = Decimal("0.01"),
) -> Dict[str, Any]:
    rows = load_manifest(manifest_path)
    summary, failures = evaluate_records(
        manifest_rows=rows,
        predictions_dir=predictions_dir,
        amount_tolerance=amount_tolerance,
    )
    write_reports(
        summary=summary,
        failure_cases=failures,
        reports_dir=reports_dir,
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["offline", "live"], required=True)
    parser.add_argument(
        "--manifest",
        default="dataset/manifest.jsonl",
    )
    parser.add_argument("--predictions-dir")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--amount-tolerance", default="0.01")
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--input-cost-per-million")
    parser.add_argument("--output-cost-per-million")
    args = parser.parse_args()

    manifest_path = _safe_path(args.manifest)
    if args.predictions_dir:
        predictions_dir = _safe_path(args.predictions_dir)
    elif args.mode == "offline":
        predictions_dir = ROOT / "dataset" / "predictions" / "fixture"
    else:
        predictions_dir = ROOT / "predictions"
    reports_dir = _safe_path(args.reports_dir)
    rows = load_manifest(manifest_path)

    if args.mode == "live":
        print(
            "LIVE MODE: 실제 API 호출과 비용이 발생할 수 있습니다. "
            "--max-cases로 호출 수를 제한할 수 있습니다."
        )
        run_live_predictions(
            manifest_rows=rows,
            predictions_dir=predictions_dir,
            settings=Settings.from_env(),
            case_ids=args.case_id,
            max_cases=args.max_cases,
            input_cost_per_million=(
                Decimal(args.input_cost_per_million)
                if args.input_cost_per_million
                else None
            ),
            output_cost_per_million=(
                Decimal(args.output_cost_per_million)
                if args.output_cost_per_million
                else None
            ),
        )

    selected_rows = [
        row
        for row in rows
        if not args.case_id or row["case_id"] in args.case_id
    ]
    if args.max_cases is not None:
        selected_rows = selected_rows[: args.max_cases]
    summary, failures = evaluate_records(
        manifest_rows=selected_rows,
        predictions_dir=predictions_dir,
        amount_tolerance=Decimal(args.amount_tolerance),
    )
    write_reports(
        summary=summary,
        failure_cases=failures,
        reports_dir=reports_dir,
    )
    print(
        "evaluated={} pass_rate={:.2%} hallucination_rate={:.2%}".format(
            summary["cases_evaluated"],
            summary["document_pass_rate"],
            summary["hallucination_rate"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
