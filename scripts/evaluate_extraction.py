#!/usr/bin/env python3
import argparse
import hashlib
import json
import mimetypes
import platform
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Tuple

from dotenv import load_dotenv


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
BENCHMARK_FIELD_NAMES = [
    "currency",
    "amount_due",
    "explicit_due_date",
    "derived_due_date",
    "trade_type",
    "company_role",
    "seller_country",
    "buyer_country",
    "document_type",
]
AMOUNT_FIELDS = {"grand_total", "amount_due"}
DATE_FIELDS = {
    "issue_date",
    "contract_date",
    "shipment_date",
    "explicit_due_date",
    "derived_due_date",
}
ABSTENTION_FIELDS = [
    "currency",
    "grand_total",
    "amount_due",
    "issue_date",
    "contract_date",
    "shipment_date",
    "explicit_due_date",
    "derived_due_date",
]
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
LIVE_FIXTURE_PATHS = (
    ROOT / "dataset" / "predictions" / "fixture",
    ROOT / "dataset" / "country_validation" / "predictions" / "fixture",
)
PROMPT_CONTRACT_PATHS = (
    ROOT / "prompt.py",
    ROOT / "src" / "document_intake" / "prompt_builder.py",
    ROOT / "prompts" / "system_prompt.md",
    ROOT / "prompts" / "extraction_rules.md",
    ROOT / "prompts" / "adversarial_rules.md",
    ROOT / "prompts" / "few_shot_examples.json",
    ROOT / "prompts" / "prompt_version.json",
)
EVALUATOR_VERSION = "2.0"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _prompt_contract_hash() -> str:
    digest = hashlib.sha256()
    for path in PROMPT_CONTRACT_PATHS:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _git_state() -> Tuple[str, bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=str(ROOT),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN", True


def _relative_to_root(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return "OUTSIDE_REPOSITORY"


def _validate_run_id(run_id: Optional[str]) -> str:
    if not run_id or not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(
            "live 모드는 영문자·숫자·점·밑줄·하이픈으로 된 "
            "--run-id가 필요합니다."
        )
    return run_id


def _selected_rows(
    manifest_rows: List[Dict[str, Any]],
    case_ids: Optional[List[str]],
    max_cases: Optional[int],
) -> List[Dict[str, Any]]:
    if max_cases is not None and max_cases <= 0:
        raise ValueError("--max-cases는 양수여야 합니다.")
    requested = set(case_ids or [])
    known = {str(row["case_id"]) for row in manifest_rows}
    missing = sorted(requested - known)
    if missing:
        raise ValueError(
            "manifest에 없는 case_id: {}".format(", ".join(missing))
        )
    selected = [
        row
        for row in manifest_rows
        if not requested or row["case_id"] in requested
    ]
    if max_cases is not None:
        selected = selected[:max_cases]
    if not selected:
        raise ValueError("평가할 사례가 없습니다.")
    return selected


def _validate_synthetic_live_rows(
    manifest_rows: List[Dict[str, Any]],
) -> None:
    for row in manifest_rows:
        case_id = str(row["case_id"])
        if row.get("synthetic_document") is not True:
            raise ValueError(
                "{}: synthetic_document=true가 아니므로 live 실행을 "
                "차단했습니다.".format(case_id)
            )
        if row.get("real_customer_document") is not False:
            raise ValueError(
                "{}: real_customer_document=false가 아니므로 live 실행을 "
                "차단했습니다.".format(case_id)
            )
        if row.get("split") != "test":
            raise ValueError(
                "{}: live benchmark는 격리된 test split만 허용합니다.".format(
                    case_id
                )
            )
        if row.get("fine_tuning_eligible") is not False:
            raise ValueError(
                "{}: 파인튜닝 후보 제외가 확인되지 않았습니다.".format(case_id)
            )
        document_path = _safe_path(str(row["document_path"]))
        country_root = (
            ROOT / "dataset" / "country_validation" / "documents"
        ).resolve()
        if country_root not in document_path.parents:
            raise ValueError(
                "{}: 승인된 합성 검증 문서 경로가 아닙니다.".format(case_id)
            )


def _live_run_directories(
    predictions_root: Path,
    reports_root: Path,
    run_id: str,
) -> Tuple[Path, Path]:
    resolved_predictions = predictions_root.resolve()
    for fixture_path in LIVE_FIXTURE_PATHS:
        if resolved_predictions == fixture_path.resolve():
            raise ValueError(
                "live prediction은 fixture 디렉터리에 저장할 수 없습니다."
            )
    predictions_dir = resolved_predictions / run_id
    reports_dir = reports_root.resolve() / run_id
    if predictions_dir.exists() or reports_dir.exists():
        raise FileExistsError(
            "run_id={} 결과가 이미 존재합니다. baseline을 덮어쓰지 말고 "
            "새 --run-id를 사용하세요.".format(run_id)
        )
    return predictions_dir, reports_dir


def _base_run_metadata(
    *,
    manifest_path: Path,
    manifest_rows: List[Dict[str, Any]],
    selected_rows: List[Dict[str, Any]],
    predictions_dir: Path,
    reports_dir: Path,
    settings: Settings,
    run_id: str,
    baseline_version: Optional[str],
) -> Dict[str, Any]:
    git_commit, git_dirty = _git_state()
    return {
        "schema_version": EVALUATOR_VERSION,
        "evaluation_mode": "LIVE",
        "run_id": run_id,
        "baseline_version": baseline_version,
        "status": "RUNNING",
        "started_at": datetime.now().astimezone().isoformat(),
        "completed_at": None,
        "timezone": str(datetime.now().astimezone().tzinfo),
        "git_commit_sha": git_commit,
        "git_worktree_dirty": git_dirty,
        "python_version": platform.python_version(),
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_sha256": _sha256_file(Path(__file__).resolve()),
        "extraction_prompt_version": _load_prompt_version(),
        "extraction_prompt_sha256": _prompt_contract_hash(),
        "requested_model": settings.openai_model,
        "fallback_model": settings.openai_fallback_model,
        "models_used": [],
        "manifest_path": _relative_to_root(manifest_path),
        "manifest_sha256": _sha256_file(manifest_path),
        "manifest_case_count": len(manifest_rows),
        "selected_case_count": len(selected_rows),
        "executed_case_count": 0,
        "successful_case_count": 0,
        "failed_case_count": 0,
        "timeout_case_count": 0,
        "selected_case_ids": [row["case_id"] for row in selected_rows],
        "predictions_dir": _relative_to_root(predictions_dir),
        "reports_dir": _relative_to_root(reports_dir),
        "synthetic_dataset": True,
        "real_customer_documents": False,
        "statistical_generalization_allowed": False,
        "model_accuracy_claim_allowed": True,
        "api_key_configured": bool(settings.openai_api_key),
        "api_key_value_recorded": False,
        "raw_prompt_recorded": False,
        "raw_document_recorded": False,
        "raw_api_payload_recorded": False,
        "raw_model_response_recorded": False,
        "interrupted": False,
    }


def _load_prompt_version() -> str:
    path = ROOT / "prompts" / "prompt_version.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "UNKNOWN"
    return str(payload.get("version") or "UNKNOWN")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _replace_json(path: Path, payload: Dict[str, Any]) -> None:
    temporary = path.with_name("{}.tmp".format(path.name))
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


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


def _load_prediction(
    path: Path,
) -> Tuple[Optional[TradeDocumentExtraction], Dict[str, Any], Optional[str]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):
        return None, {}, "invalid_prediction_file"
    if not isinstance(data, dict):
        return None, {}, "invalid_prediction_file"
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        return None, {}, "invalid_prediction_file"
    status = str(metadata.get("status") or "SUCCESS").upper()
    if status != "SUCCESS":
        error_type = str(metadata.get("error_type") or status).lower()
        if error_type == "timeout":
            return None, metadata, "timeout"
        return None, metadata, "api_error"
    extraction_data = data.get("extraction", data)
    try:
        extraction = TradeDocumentExtraction.model_validate(extraction_data)
    except (TypeError, ValueError):
        return None, metadata, "invalid_prediction_file"
    return extraction, metadata, None


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


def _has_advance_payment(extraction: TradeDocumentExtraction) -> bool:
    text = " ".join(
        [
            extraction.payment_terms or "",
            *[
                item.condition or ""
                for item in extraction.installments
            ],
        ]
    ).lower()
    return any(
        marker in text
        for marker in ("advance", "upfront", "선지급", "선급")
    )


def _installment_amounts(
    extraction: TradeDocumentExtraction,
) -> Dict[int, Optional[Decimal]]:
    return {
        item.sequence: _decimal(item.amount)
        for item in extraction.installments
    }


def _installment_sum_matches(
    extraction: TradeDocumentExtraction,
) -> bool:
    if not extraction.installments:
        return False
    amounts = [
        _decimal(item.amount)
        for item in extraction.installments
    ]
    amount_due = _decimal(extraction.amount_due)
    if amount_due is None or any(item is None for item in amounts):
        return False
    return sum(
        (item for item in amounts if item is not None),
        Decimal("0"),
    ) == amount_due


def _evidence_link_consistent(
    extraction: TradeDocumentExtraction,
    field: str,
) -> bool:
    if field == "document_notice":
        return True
    if field == "installments":
        return bool(extraction.installments)
    if not hasattr(extraction, field):
        return False
    return getattr(extraction, field) is not None


def _case_dimensions(
    row: Dict[str, Any],
    label: TradeDocumentExtraction,
) -> Dict[str, str]:
    suffix = Path(str(row.get("document_path") or "")).suffix.lower()
    document_format = {
        ".pdf": "PDF",
        ".jpg": "JPG",
        ".jpeg": "JPG",
        ".png": "PNG",
    }.get(suffix, "OTHER")
    if label.explicit_due_date:
        due_date_type = "EXPLICIT_DATE"
    elif label.derived_due_date:
        due_date_type = "DERIVED_DATE"
    elif label.installments:
        due_date_type = "INSTALLMENT_OR_EVENT_DATE"
    else:
        due_date_type = "UNRESOLVED_EVENT_DATE"
    return {
        "document_format": document_format,
        "counterparty_country": str(
            row.get("counterparty_country") or "UNKNOWN"
        ),
        "trade_type": str(row.get("trade_type") or label.trade_type),
        "expected_validation_status": str(
            row.get("expected_validation_status") or "UNKNOWN"
        ),
        "due_date_type": due_date_type,
        "currency_presence": (
            "EXPLICIT_CURRENCY"
            if label.currency is not None
            else "MISSING_CURRENCY"
        ),
    }


def _build_breakdowns(
    case_results: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    breakdowns: Dict[str, Dict[str, Any]] = {}
    for dimension in (
        "document_format",
        "counterparty_country",
        "trade_type",
        "expected_validation_status",
        "due_date_type",
        "currency_presence",
    ):
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for result in case_results.values():
            grouped[result["dimensions"][dimension]].append(result)
        dimension_result: Dict[str, Any] = {}
        for value, items in sorted(grouped.items()):
            field_accuracy = {}
            for field in BENCHMARK_FIELD_NAMES:
                field_accuracy[field] = _ratio(
                    sum(
                        1
                        for item in items
                        if item.get("benchmark_fields", {}).get(field)
                    ),
                    len(items),
                )
            dimension_result[value] = {
                "case_count": len(items),
                "successful_prediction_count": sum(
                    1 for item in items if item.get("prediction_succeeded")
                ),
                "document_pass_count": sum(
                    1 for item in items if item.get("passed")
                ),
                "document_pass_rate": _ratio(
                    sum(1 for item in items if item.get("passed")),
                    len(items),
                ),
                "benchmark_field_accuracy": field_accuracy,
            }
        breakdowns[dimension] = dimension_result
    return breakdowns


def _safe_live_error_type(exc: Exception) -> str:
    name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    if "timeout" in name or "timeout" in message or "시간이 초과" in message:
        return "TIMEOUT"
    return "API_ERROR"


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
    evaluation_mode: str = "FIXTURE",
    run_metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not amount_tolerance.is_finite() or amount_tolerance < 0:
        raise ValueError("amount_tolerance는 0 이상의 유한한 값이어야 합니다.")
    normalized_mode = evaluation_mode.strip().upper()
    if normalized_mode not in {"FIXTURE", "LIVE"}:
        raise ValueError("evaluation_mode는 FIXTURE 또는 LIVE여야 합니다.")
    field_counts: DefaultDict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "exact": 0, "normalized": 0}
    )
    benchmark_field_counts: DefaultDict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "correct": 0}
    )
    currency_total = currency_correct = 0
    amount_total = amount_exact = amount_tolerance_correct = 0
    date_total = date_correct = 0
    required_total = required_completed = 0
    hallucination_total = hallucination_count = 0
    evidence_total = evidence_covered = 0
    evidence_link_total = evidence_link_consistent = 0
    confirmed_without_evidence = 0
    confirmed_without_source_text = 0
    image_evidence_total = image_evidence_safely_blocked = 0
    review_positive = review_true_positive = 0
    review_identification_total = review_identification_correct = 0
    blocked_total = blocked_correct = 0
    abstention_total = abstention_correct = 0
    unsupported_currency_guesses = 0
    unsupported_date_guesses = 0
    unsupported_amount_guesses = 0
    false_positive_fields = 0
    installment_amount_total = installment_amount_correct = 0
    installment_sum_total = installment_sum_correct = 0
    advance_total = advance_correct = 0
    event_due_total = event_due_preserved = 0
    unknown_due_total = unknown_due_abstained = 0
    document_passes = 0
    failure_cases: List[Dict[str, Any]] = []
    case_results: Dict[str, Any] = {}
    latencies: List[Decimal] = []
    costs: List[Decimal] = []
    input_tokens = output_tokens = 0
    successful_predictions = failed_predictions = timeout_predictions = 0
    models_used: List[str] = []
    per_case_operations: Dict[str, Any] = {}

    for row in manifest_rows:
        case_id = row["case_id"]
        label, unused_label_meta = _load_extraction(
            _safe_path(row["label_path"])
        )
        del unused_label_meta
        dimensions = _case_dimensions(row, label)
        for field in BENCHMARK_FIELD_NAMES:
            benchmark_field_counts[field]["total"] += 1
        prediction_path = predictions_dir / "{}.json".format(case_id)
        prediction_error: Optional[str] = None
        prediction: Optional[TradeDocumentExtraction] = None
        metadata: Dict[str, Any] = {}
        if not prediction_path.exists():
            prediction_error = "missing_prediction_file"
        else:
            prediction, metadata, prediction_error = _load_prediction(
                prediction_path
            )

        latency = _decimal(metadata.get("latency_seconds"))
        if latency is not None:
            latencies.append(latency)
        cost = _decimal(metadata.get("estimated_api_cost"))
        if cost is not None:
            costs.append(cost)
        input_tokens += int(metadata.get("input_tokens") or 0)
        output_tokens += int(metadata.get("output_tokens") or 0)
        model = str(metadata.get("model") or "").strip()
        if model and model not in models_used:
            models_used.append(model)
        operation_status = (
            "SUCCESS"
            if prediction_error is None and prediction is not None
            else (
                "TIMEOUT"
                if prediction_error == "timeout"
                else "FAILED"
            )
        )
        per_case_operations[case_id] = {
            "status": operation_status,
            "latency_seconds": (
                str(latency) if latency is not None else None
            ),
            "input_tokens": metadata.get("input_tokens"),
            "output_tokens": metadata.get("output_tokens"),
            "total_tokens": metadata.get("total_tokens"),
            "estimated_api_cost": metadata.get("estimated_api_cost"),
            "cost_status": (
                "KNOWN"
                if metadata.get("estimated_api_cost") is not None
                else "UNKNOWN"
            ),
            "model": model or None,
            "error_type": metadata.get("error_type"),
        }

        if prediction_error or prediction is None:
            failed_predictions += 1
            if prediction_error == "timeout":
                timeout_predictions += 1
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
            for field in ABSTENTION_FIELDS:
                if getattr(label, field) is None:
                    abstention_total += 1
            expected_installments = _installment_amounts(label)
            installment_amount_total += len(expected_installments)
            if label.installments:
                installment_sum_total += 1
            advance_total += 1
            if (
                virtual_due_date(label) is None
                and (
                    row.get("category") in {
                        "event_based_terms",
                        "mixed_split_terms",
                    }
                    or label.installments
                )
            ):
                event_due_total += 1
            if virtual_due_date(label) is None:
                unknown_due_total += 1
            if label.needs_human_review:
                review_positive += 1
            review_identification_total += 1
            if row.get("expected_validation_status") == "BLOCKED":
                blocked_total += 1
            if normalized_mode == "LIVE":
                image_evidence_total += 1
            case_results[case_id] = {
                "passed": False,
                "core_fields": {},
                "benchmark_fields": {
                    field: False for field in BENCHMARK_FIELD_NAMES
                },
                "validation_critical_codes": [
                    (
                        "MISSING_PREDICTION"
                        if prediction_error == "missing_prediction_file"
                        else (
                            "LIVE_TIMEOUT"
                            if prediction_error == "timeout"
                            else (
                                "LIVE_API_ERROR"
                                if prediction_error == "api_error"
                                else "INVALID_PREDICTION"
                            )
                        )
                    )
                ],
                "prediction_succeeded": False,
                "operation_status": operation_status,
                "dimensions": dimensions,
            }
            continue

        successful_predictions += 1

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
                    false_positive_fields += 1
                    if field == "currency":
                        unsupported_currency_guesses += 1
                    elif field in DATE_FIELDS:
                        unsupported_date_guesses += 1
                    elif field in AMOUNT_FIELDS:
                        unsupported_amount_guesses += 1

        benchmark_matches: Dict[str, bool] = {}
        for field in BENCHMARK_FIELD_NAMES:
            matches = normalize_field(
                field,
                label_dict[field],
            ) == normalize_field(
                field,
                prediction_dict[field],
            )
            benchmark_matches[field] = matches
            if matches:
                benchmark_field_counts[field]["correct"] += 1

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

        for field in ABSTENTION_FIELDS:
            if getattr(label, field) is None:
                abstention_total += 1
                if getattr(prediction, field) is None:
                    abstention_correct += 1

        for item in prediction.evidence:
            evidence_link_total += 1
            if (
                item.source_text.strip()
                and _evidence_link_consistent(prediction, item.field)
            ):
                evidence_link_consistent += 1

        for field in (
            "currency",
            "amount_due",
            "explicit_due_date",
            "derived_due_date",
            "trade_type",
            "seller_country",
            "buyer_country",
        ):
            if getattr(prediction, field) is None:
                continue
            matching_evidence = [
                item
                for item in prediction.evidence
                if item.field == field and item.extraction_type != "INFERRED"
            ]
            if field == "trade_type":
                matching_evidence = [
                    item
                    for item in prediction.evidence
                    if item.field
                    in {
                        "seller_name",
                        "seller_country",
                        "buyer_name",
                        "buyer_country",
                    }
                    and item.extraction_type != "INFERRED"
                ]
            if not matching_evidence:
                confirmed_without_evidence += 1
            if not any(item.source_text.strip() for item in matching_evidence):
                confirmed_without_source_text += 1

        expected_installments = _installment_amounts(label)
        actual_installments = _installment_amounts(prediction)
        for sequence, expected_amount in expected_installments.items():
            installment_amount_total += 1
            if expected_amount == actual_installments.get(sequence):
                installment_amount_correct += 1
        if label.installments:
            installment_sum_total += 1
            if _installment_sum_matches(prediction):
                installment_sum_correct += 1

        advance_total += 1
        if _has_advance_payment(label) == _has_advance_payment(prediction):
            advance_correct += 1

        is_event_case = (
            virtual_due_date(label) is None
            and (
                row.get("category")
                in {"event_based_terms", "mixed_split_terms"}
                or label.installments
            )
        )
        if is_event_case:
            event_due_total += 1
            if virtual_due_date(prediction) is None:
                event_due_preserved += 1
        if virtual_due_date(label) is None:
            unknown_due_total += 1
            if virtual_due_date(prediction) is None:
                unknown_due_abstained += 1

        if label.needs_human_review:
            review_positive += 1
            if prediction.needs_human_review:
                review_true_positive += 1
        review_identification_total += 1
        if label.needs_human_review == prediction.needs_human_review:
            review_identification_correct += 1

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
        expected_blocked = row.get("expected_validation_status") == "BLOCKED"
        if expected_blocked:
            blocked_total += 1
            predicted_blocked = bool(
                critical_codes
                or prediction.missing_required_fields
            )
            if predicted_blocked:
                blocked_correct += 1

        if normalized_mode == "LIVE":
            image_evidence_total += 1
            validation_codes = {
                str(item)
                for item in metadata.get("validation_issue_codes", [])
            }
            safely_blocked = (
                metadata.get("stage2_allowed") is False
                and bool(
                    {
                        "OCR_REQUIRED",
                        "EVIDENCE_UNVERIFIABLE",
                    }.intersection(validation_codes)
                )
            )
            if safely_blocked:
                image_evidence_safely_blocked += 1

        case_results[case_id] = {
            "passed": passed,
            "core_fields": core_match,
            "benchmark_fields": benchmark_matches,
            "validation_critical_codes": critical_codes,
            "prediction_succeeded": True,
            "operation_status": operation_status,
            "dimensions": dimensions,
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
    benchmark_field_accuracy = {
        field: _ratio(values["correct"], values["total"])
        for field, values in sorted(benchmark_field_counts.items())
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
    total_cost = (
        str(sum(costs, Decimal("0")))
        if costs and len(costs) == successful_predictions
        else None
    )
    operational_metrics = {
        "success_count": successful_predictions,
        "failed_count": failed_predictions,
        "timeout_count": timeout_predictions,
        "per_case": per_case_operations,
        "average_latency_seconds": average_latency,
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "estimated_total_api_cost": total_cost,
        "estimated_api_cost_status": (
            "KNOWN" if total_cost is not None else "UNKNOWN"
        ),
        "models_used": models_used,
    }
    payment_term_metrics = {
        "installment_amount_accuracy": _ratio(
            installment_amount_correct,
            installment_amount_total,
        ),
        "installment_amount_count": installment_amount_total,
        "installment_total_consistency_accuracy": _ratio(
            installment_sum_correct,
            installment_sum_total,
        ),
        "installment_case_count": installment_sum_total,
        "advance_payment_identification_accuracy": _ratio(
            advance_correct,
            advance_total,
        ),
        "event_based_condition_preservation_accuracy": _ratio(
            event_due_preserved,
            event_due_total,
        ),
        "event_based_case_count": event_due_total,
        "unknown_due_date_abstention_accuracy": _ratio(
            unknown_due_abstained,
            unknown_due_total,
        ),
        "unknown_due_date_case_count": unknown_due_total,
    }
    safety_metrics = {
        "unsupported_currency_guess_count": unsupported_currency_guesses,
        "unsupported_date_guess_count": unsupported_date_guesses,
        "unsupported_amount_guess_count": unsupported_amount_guesses,
        "false_positive_field_count": false_positive_fields,
        "abstention_accuracy": _ratio(
            abstention_correct,
            abstention_total,
        ),
        "abstention_field_count": abstention_total,
        "human_review_identification_accuracy": _ratio(
            review_identification_correct,
            review_identification_total,
        ),
        "user_confirmation_required_case_count": review_positive,
        "user_confirmation_required_identified_count": review_true_positive,
        "blocked_case_accuracy": _ratio(blocked_correct, blocked_total),
        "blocked_case_count": blocked_total,
    }
    evidence_metrics = {
        "core_field_evidence_coverage": _ratio(
            evidence_covered,
            evidence_total,
        ),
        "evidence_field_link_consistency": _ratio(
            evidence_link_consistent,
            evidence_link_total,
        ),
        "confirmed_value_without_evidence_count": (
            confirmed_without_evidence
        ),
        "confirmed_value_without_source_text_count": (
            confirmed_without_source_text
        ),
        "image_evidence_safety_accuracy": _ratio(
            image_evidence_safely_blocked,
            image_evidence_total,
        ),
        "image_evidence_case_count": image_evidence_total,
        "image_evidence_interpretation": (
            "Independent OCR verification is unavailable; safe blocking "
            "requires OCR_REQUIRED or EVIDENCE_UNVERIFIABLE."
            if normalized_mode == "LIVE"
            else "NOT_APPLICABLE_TO_FIXTURE_PIPELINE_VALIDATION"
        ),
    }
    summary: Dict[str, Any] = {
        "schema_version": EVALUATOR_VERSION,
        "evaluation_mode": normalized_mode,
        "model_accuracy_claim_allowed": normalized_mode == "LIVE",
        "purpose": (
            "EVALUATOR_PIPELINE_VALIDATION"
            if normalized_mode == "FIXTURE"
            else "SYNTHETIC_LIVE_MODEL_BASELINE"
        ),
        "synthetic_dataset": all(
            row.get("synthetic_document") is True
            for row in manifest_rows
        ),
        "real_customer_documents": False,
        "statistical_generalization_allowed": False,
        "cases_in_manifest": len(manifest_rows),
        "cases_evaluated": evaluated_count,
        "executed_case_count": evaluated_count,
        "failed_case_count": failed_predictions,
        "exact_match_accuracy_per_field": exact_per_field,
        "normalized_match_accuracy_per_field": normalized_per_field,
        "benchmark_field_accuracy": benchmark_field_accuracy,
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
        # This metric is a fixture-level claim check only. It must never be
        # presented as proof that a quote exists in an uploaded document;
        # source-grounded verification happens in the Stage 0 intake path.
        "evidence_claim_coverage": _ratio(
            evidence_covered,
            evidence_total,
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
        "payment_term_metrics": payment_term_metrics,
        "safety_metrics": safety_metrics,
        "evidence_metrics": evidence_metrics,
        "operational_metrics": operational_metrics,
        "case_results": case_results,
        "breakdowns": _build_breakdowns(case_results),
    }
    if normalized_mode == "LIVE":
        summary["model_name"] = (
            (run_metadata or {}).get("requested_model")
            or (models_used[0] if len(models_used) == 1 else None)
        )
        summary["run_id"] = (run_metadata or {}).get("run_id")
    if run_metadata is not None:
        summary["run_metadata"] = run_metadata
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
    run_id: str,
    case_ids: Optional[List[str]] = None,
    max_cases: Optional[int] = None,
    input_cost_per_million: Optional[Decimal] = None,
    output_cost_per_million: Optional[Decimal] = None,
) -> List[Dict[str, Any]]:
    if not settings.live_extraction_ready:
        raise RuntimeError(
            "live 모드는 OPENAI_API_KEY와 "
            "ENABLE_LIVE_DOCUMENT_EXTRACTION=true가 필요합니다."
        )
    _validate_run_id(run_id)
    if max_cases is None or max_cases <= 0:
        raise ValueError("live 모드는 양수 --max-cases가 반드시 필요합니다.")
    selected = _selected_rows(manifest_rows, case_ids, max_cases)
    _validate_synthetic_live_rows(selected)
    resolved_predictions = predictions_dir.resolve()
    for fixture_path in LIVE_FIXTURE_PATHS:
        if resolved_predictions == fixture_path.resolve():
            raise ValueError(
                "live prediction은 fixture 디렉터리에 저장할 수 없습니다."
            )
    if predictions_dir.exists():
        if any(predictions_dir.iterdir()):
            raise FileExistsError(
                "live prediction 디렉터리가 비어 있지 않아 실행을 차단했습니다."
            )
    else:
        predictions_dir.mkdir(parents=True, exist_ok=False)
    outcomes: List[Dict[str, Any]] = []

    for row in selected:
        case_id = str(row["case_id"])
        prediction_path = predictions_dir / "{}.json".format(case_id)
        if prediction_path.exists():
            raise FileExistsError(
                "{} 결과가 이미 있어 덮어쓰기를 차단했습니다.".format(case_id)
            )
        document_path = _safe_path(row["document_path"])
        mime_type = mimetypes.guess_type(document_path.name)[0]
        label, unused_metadata = _load_extraction(
            _safe_path(row["label_path"])
        )
        del unused_metadata
        started = time.monotonic()
        try:
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
            issue_codes = sorted(
                {item.code for item in run.validation.issues}
            )
            metadata = {
                "evaluation_mode": "LIVE",
                "status": "SUCCESS",
                "run_id": run_id,
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
                "validation_pass": run.validation.validation_pass,
                "stage2_allowed": run.validation.stage2_allowed,
                "validation_issue_codes": issue_codes,
                "synthetic_dataset": True,
                "real_customer_documents": False,
                "statistical_generalization_allowed": False,
                "raw_model_response_recorded": False,
            }
            _write_json(
                prediction_path,
                {
                    "extraction": run.extraction.model_dump(),
                    "metadata": metadata,
                },
            )
            outcomes.append(
                {
                    "case_id": case_id,
                    "status": "SUCCESS",
                    "latency_seconds": metadata["latency_seconds"],
                    "input_tokens": run.usage.input_tokens,
                    "output_tokens": run.usage.output_tokens,
                    "total_tokens": run.usage.total_tokens,
                    "estimated_api_cost": cost,
                    "model": run.usage.model,
                    "error_type": None,
                }
            )
        except Exception as exc:
            error_type = _safe_live_error_type(exc)
            latency = str(time.monotonic() - started)
            metadata = {
                "evaluation_mode": "LIVE",
                "status": error_type,
                "error_type": error_type,
                "safe_error_code": (
                    "DOCUMENT_EXTRACTION_TIMEOUT"
                    if error_type == "TIMEOUT"
                    else "DOCUMENT_EXTRACTION_FAILED"
                ),
                "run_id": run_id,
                "model": settings.openai_model,
                "latency_seconds": latency,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "attempts": None,
                "estimated_api_cost": None,
                "synthetic_dataset": True,
                "real_customer_documents": False,
                "statistical_generalization_allowed": False,
                "raw_model_response_recorded": False,
            }
            _write_json(prediction_path, {"metadata": metadata})
            outcomes.append(
                {
                    "case_id": case_id,
                    "status": error_type,
                    "latency_seconds": latency,
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "estimated_api_cost": None,
                    "model": settings.openai_model,
                    "error_type": error_type,
                }
            )
    return outcomes


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

    operation = summary["operational_metrics"]
    safety = summary["safety_metrics"]
    evidence = summary["evidence_metrics"]
    payment = summary["payment_term_metrics"]
    cost_display = (
        operation["estimated_total_api_cost"]
        if operation["estimated_api_cost_status"] == "KNOWN"
        else "UNKNOWN"
    )
    lines = [
        "# Extraction Evaluation Report",
        "",
        "- Evaluation mode: {}".format(summary["evaluation_mode"]),
        "- Purpose: {}".format(summary["purpose"]),
        "- Synthetic dataset: {}".format(
            str(summary["synthetic_dataset"]).lower()
        ),
        "- Real customer documents: false",
        "- Statistical generalization allowed: false",
        "- Cases evaluated: {}".format(summary["cases_evaluated"]),
        "- Successful API/prediction records: {}".format(
            operation["success_count"]
        ),
        "- Failed API/prediction records: {}".format(
            operation["failed_count"]
        ),
        "- Timeout records: {}".format(operation["timeout_count"]),
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
        "- Evidence claim coverage (not source verification): {:.2%}".format(
            summary["evidence_claim_coverage"]
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
        "- Total input tokens: {}".format(summary["total_input_tokens"]),
        "- Total output tokens: {}".format(summary["total_output_tokens"]),
        "- Estimated total API cost: {}".format(cost_display),
        "",
        "## Benchmark fields",
        "",
    ]
    for field in BENCHMARK_FIELD_NAMES:
        lines.append(
            "- {}: {:.2%}".format(
                field,
                summary["benchmark_field_accuracy"][field],
            )
        )
    lines.extend(
        [
            "",
            "## Payment terms and abstention",
            "",
            "- Installment amount accuracy: {:.2%}".format(
                payment["installment_amount_accuracy"]
            ),
            "- Installment total consistency: {:.2%}".format(
                payment["installment_total_consistency_accuracy"]
            ),
            "- Advance payment identification: {:.2%}".format(
                payment["advance_payment_identification_accuracy"]
            ),
            "- Event-based due-date preservation: {:.2%}".format(
                payment["event_based_condition_preservation_accuracy"]
            ),
            "- Unknown due-date abstention: {:.2%}".format(
                payment["unknown_due_date_abstention_accuracy"]
            ),
            "- Unsupported currency guesses: {}".format(
                safety["unsupported_currency_guess_count"]
            ),
            "- Unsupported date guesses: {}".format(
                safety["unsupported_date_guess_count"]
            ),
            "- Unsupported amount guesses: {}".format(
                safety["unsupported_amount_guess_count"]
            ),
            "- False-positive fields: {}".format(
                safety["false_positive_field_count"]
            ),
            "- General abstention accuracy: {:.2%}".format(
                safety["abstention_accuracy"]
            ),
            "- Human-review identification: {:.2%}".format(
                safety["human_review_identification_accuracy"]
            ),
            "- Blocked-case accuracy: {:.2%}".format(
                safety["blocked_case_accuracy"]
            ),
            "",
            "## Evidence",
            "",
            "- Core field evidence coverage: {:.2%}".format(
                evidence["core_field_evidence_coverage"]
            ),
            "- Evidence field-link consistency: {:.2%}".format(
                evidence["evidence_field_link_consistency"]
            ),
            "- Confirmed values without evidence: {}".format(
                evidence["confirmed_value_without_evidence_count"]
            ),
            "- Confirmed values without source_text: {}".format(
                evidence["confirmed_value_without_source_text_count"]
            ),
            "- Image evidence safety accuracy: {:.2%}".format(
                evidence["image_evidence_safety_accuracy"]
            ),
            "",
            "## Interpretation",
            "",
        ]
    )
    if summary["evaluation_mode"] == "FIXTURE":
        lines.extend(
            [
                "Fixture predictions validate the evaluator pipeline only. "
                "They do not measure live model or OCR accuracy and must not "
                "be presented as an AI accuracy result.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "This is a live model result on a limited synthetic validation "
                "set. It is not evidence of real-customer-document accuracy and "
                "must not be generalized beyond the executed cases.",
                "",
            ]
        )
    lines.extend(
        [
            "The Stage 0 intake path independently verifies text-PDF quotes "
            "against source pages. Image/scanned documents do not have an "
            "independently verified OCR layer and require field-level human "
            "confirmation.",
            "",
            "Source-incomplete or intentionally conflicting documents can "
            "correctly fail the document PASS rule even when extraction "
            "matches the label.",
            "",
            "## Failure count",
            "",
            "- {} field/document failures".format(len(failure_cases)),
        ]
    )
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
    evaluation_mode: str = "FIXTURE",
    run_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rows = load_manifest(manifest_path)
    summary, failures = evaluate_records(
        manifest_rows=rows,
        predictions_dir=predictions_dir,
        amount_tolerance=amount_tolerance,
        evaluation_mode=evaluation_mode,
        run_metadata=run_metadata,
    )
    write_reports(
        summary=summary,
        failure_cases=failures,
        reports_dir=reports_dir,
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fixture evaluator 또는 승인된 합성문서 guarded live benchmark"
        )
    )
    parser.add_argument("--mode", choices=["offline", "live"], required=True)
    parser.add_argument(
        "--manifest",
        default="dataset/manifest.jsonl",
    )
    parser.add_argument("--predictions-dir")
    parser.add_argument("--reports-dir")
    parser.add_argument("--amount-tolerance", default="0.01")
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--baseline-version")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="안전조건과 출력 경로만 확인하고 API를 호출하지 않습니다.",
    )
    parser.add_argument("--input-cost-per-million")
    parser.add_argument("--output-cost-per-million")
    args = parser.parse_args()

    try:
        manifest_path = _safe_path(args.manifest)
        rows = load_manifest(manifest_path)
        amount_tolerance = Decimal(args.amount_tolerance)
        if (
            not amount_tolerance.is_finite()
            or amount_tolerance < Decimal("0")
        ):
            raise ValueError(
                "--amount-tolerance는 0 이상의 유한한 값이어야 합니다."
            )
        input_cost = (
            Decimal(args.input_cost_per_million)
            if args.input_cost_per_million
            else None
        )
        output_cost = (
            Decimal(args.output_cost_per_million)
            if args.output_cost_per_million
            else None
        )
        for value in (input_cost, output_cost):
            if value is not None and (
                not value.is_finite() or value < Decimal("0")
            ):
                raise ValueError("token 단가는 0 이상의 유한한 값이어야 합니다.")
    except (InvalidOperation, OSError, UnicodeError, ValueError) as exc:
        print("ERROR: {}".format(exc))
        return 2

    if args.mode == "offline":
        if args.confirm_live or args.run_id or args.prepare_only:
            print("ERROR: live 전용 옵션은 --mode offline에서 사용할 수 없습니다.")
            return 2
        try:
            selected_rows = _selected_rows(
                rows,
                args.case_id,
                args.max_cases,
            )
            predictions_dir = (
                _safe_path(args.predictions_dir)
                if args.predictions_dir
                else ROOT / "dataset" / "predictions" / "fixture"
            )
            reports_dir = (
                _safe_path(args.reports_dir)
                if args.reports_dir
                else ROOT / "reports"
            )
            summary, failures = evaluate_records(
                manifest_rows=selected_rows,
                predictions_dir=predictions_dir,
                amount_tolerance=amount_tolerance,
                evaluation_mode="FIXTURE",
            )
            write_reports(
                summary=summary,
                failure_cases=failures,
                reports_dir=reports_dir,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            print("ERROR: {}".format(exc))
            return 2
        print(
            "evaluated={} pass_rate={:.2%} hallucination_rate={:.2%}".format(
                summary["cases_evaluated"],
                summary["document_pass_rate"],
                summary["hallucination_rate"],
            )
        )
        return 0

    if not args.confirm_live:
        print(
            "ERROR: live API 호출에는 --confirm-live가 필요합니다. "
            "API 호출은 실행되지 않았습니다."
        )
        return 2
    if args.max_cases is None or args.max_cases <= 0:
        print(
            "ERROR: live API 호출에는 양수 --max-cases가 필요합니다. "
            "API 호출은 실행되지 않았습니다."
        )
        return 2
    try:
        run_id = _validate_run_id(args.run_id)
        selected_rows = _selected_rows(rows, args.case_id, args.max_cases)
        _validate_synthetic_live_rows(selected_rows)
        predictions_root = (
            _safe_path(args.predictions_dir)
            if args.predictions_dir
            else (
                ROOT
                / "dataset"
                / "country_validation"
                / "predictions"
                / "live"
            )
        )
        reports_root = (
            _safe_path(args.reports_dir)
            if args.reports_dir
            else ROOT / "reports" / "country_validation_live"
        )
        predictions_dir, reports_dir = _live_run_directories(
            predictions_root,
            reports_root,
            run_id,
        )
    except (FileExistsError, OSError, UnicodeError, ValueError) as exc:
        print("ERROR: {}".format(exc))
        return 2

    load_dotenv(dotenv_path=ROOT / ".env", override=False)
    settings = Settings.from_env()
    print("LIVE BENCHMARK PREFLIGHT")
    print(
        "- OPENAI_API_KEY configured: {} (value not displayed)".format(
            str(bool(settings.openai_api_key)).lower()
        )
    )
    print("- model: {}".format(settings.openai_model))
    print("- manifest: {}".format(_relative_to_root(manifest_path)))
    print("- selected case count: {}".format(len(selected_rows)))
    print("- run_id: {}".format(run_id))
    print("- predictions: {}".format(_relative_to_root(predictions_dir)))
    print("- reports: {}".format(_relative_to_root(reports_dir)))
    if not settings.live_extraction_ready:
        print(
            "READY_FOR_AUTHORIZED_LIVE_RUN: OPENAI_API_KEY 또는 "
            "ENABLE_LIVE_DOCUMENT_EXTRACTION 설정을 확인하세요. "
            "API 호출은 실행되지 않았습니다."
        )
        return 2
    if args.prepare_only:
        print(
            "READY_FOR_AUTHORIZED_LIVE_RUN: 준비 점검만 완료했으며 "
            "API 호출은 실행되지 않았습니다."
        )
        return 0

    metadata = _base_run_metadata(
        manifest_path=manifest_path,
        manifest_rows=rows,
        selected_rows=selected_rows,
        predictions_dir=predictions_dir,
        reports_dir=reports_dir,
        settings=settings,
        run_id=run_id,
        baseline_version=args.baseline_version,
    )
    metadata_path = reports_dir / "run_metadata.json"
    try:
        _write_json(metadata_path, metadata)
        outcomes = run_live_predictions(
            manifest_rows=selected_rows,
            predictions_dir=predictions_dir,
            settings=settings,
            run_id=run_id,
            max_cases=args.max_cases,
            input_cost_per_million=input_cost,
            output_cost_per_million=output_cost,
        )
    except KeyboardInterrupt:
        metadata["status"] = "INTERRUPTED"
        metadata["interrupted"] = True
        metadata["completed_at"] = datetime.now().astimezone().isoformat()
        _replace_json(metadata_path, metadata)
        print("INTERRUPTED: 완료되지 않은 run으로 기록했습니다.")
        return 130
    except Exception:
        metadata["status"] = "FAILED"
        metadata["completed_at"] = datetime.now().astimezone().isoformat()
        _replace_json(metadata_path, metadata)
        print(
            "ERROR: live benchmark 실행 준비 또는 결과 저장에 실패했습니다. "
            "비밀값과 원문은 출력하지 않았습니다."
        )
        return 1

    successful_count = sum(
        1 for item in outcomes if item["status"] == "SUCCESS"
    )
    failed_count = len(outcomes) - successful_count
    timeout_count = sum(
        1 for item in outcomes if item["status"] == "TIMEOUT"
    )
    metadata["completed_at"] = datetime.now().astimezone().isoformat()
    metadata["executed_case_count"] = len(outcomes)
    metadata["successful_case_count"] = successful_count
    metadata["failed_case_count"] = failed_count
    metadata["timeout_case_count"] = timeout_count
    metadata["models_used"] = sorted(
        {
            str(item["model"])
            for item in outcomes
            if item.get("model")
        }
    )
    metadata["status"] = (
        "COMPLETED"
        if failed_count == 0
        else "COMPLETED_WITH_FAILURES"
    )
    summary, failures = evaluate_records(
        manifest_rows=selected_rows,
        predictions_dir=predictions_dir,
        amount_tolerance=amount_tolerance,
        evaluation_mode="LIVE",
        run_metadata=metadata,
    )
    write_reports(
        summary=summary,
        failure_cases=failures,
        reports_dir=reports_dir,
    )
    _replace_json(metadata_path, metadata)
    print(
        "evaluated={} success={} failed={} timeout={} "
        "pass_rate={:.2%} hallucination_rate={:.2%}".format(
            summary["cases_evaluated"],
            successful_count,
            failed_count,
            timeout_count,
            summary["document_pass_rate"],
            summary["hallucination_rate"],
        )
    )
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
