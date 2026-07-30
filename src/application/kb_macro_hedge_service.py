import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import Settings
from src.domain.kb_macro_hedge_models import (
    KbMacroHedgeCandidate,
    KbMacroHedgeExecutionConstraints,
    KbMacroHedgeProvenance,
    KbMacroHedgeReferenceResult,
    KbMacroHedgeRequest,
    KbMacroHedgeValidation,
    KbMacroHedgeValidationCheck,
)
from src.domain.stage2_models import Stage2Input, Stage2Result


FORECAST_SCHEMA_VERSION = "krw_forecast_web_v1"
HEDGE_SCHEMA_VERSION = "krw_hedge_recommendation_v1"
SUPPORTED_PROVIDER_COMMIT_SHA = (
    "7d3efa41cdc8bbb8da61b6b0c6108bdf55713e3e"
)
KNOWN_INSTRUMENTS = {"forward", "vanilla_usd_call"}
KNOWN_STRATEGIES = {
    "forward_only",
    "forward_and_call_option",
    "call_option_only",
    "unhedged",
}
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{40}$")


@dataclass(frozen=True)
class _LoadedArtifact:
    data: Dict[str, Any]
    filename: str
    sha256: str


@dataclass(frozen=True)
class _LoadedPinnedFile:
    path: Path
    raw: bytes
    sha256: str


class _Checks:
    def __init__(self) -> None:
        self.items: List[KbMacroHedgeValidationCheck] = []
        self.warnings: List[str] = []

    def add(
        self,
        check: str,
        passed: bool,
        field: Optional[str],
        detail: str,
    ) -> None:
        self.items.append(
            KbMacroHedgeValidationCheck(
                check=check,
                passed=passed,
                field=field,
                detail=detail,
            )
        )

    def warn(self, warning: str) -> None:
        if warning not in self.warnings:
            self.warnings.append(warning)

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.items)

    def model(self) -> KbMacroHedgeValidation:
        return KbMacroHedgeValidation(
            passed=self.passed,
            checks=self.items,
            failed_checks=[
                item.check for item in self.items if not item.passed
            ],
            warnings=self.warnings,
        )


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value, "f")


def _parse_decimal(
    value: Any,
    *,
    field: str,
    checks: _Checks,
) -> Optional[Decimal]:
    if isinstance(value, bool) or value is None:
        checks.add(
            "DECIMAL_VALUE",
            False,
            field,
            "숫자 필드가 없거나 boolean입니다.",
        )
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        checks.add(
            "DECIMAL_VALUE",
            False,
            field,
            "Decimal(str(value))로 해석할 수 없습니다.",
        )
        return None
    if not parsed.is_finite():
        checks.add(
            "DECIMAL_VALUE",
            False,
            field,
            "유한한 Decimal 값이 아닙니다.",
        )
        return None
    return parsed


def _require_dict(
    parent: Dict[str, Any],
    field: str,
    checks: _Checks,
) -> Optional[Dict[str, Any]]:
    value = parent.get(field)
    if not isinstance(value, dict):
        checks.add(
            "RAW_CONTRACT_REQUIRED_FIELD",
            False,
            field,
            "필수 object가 없습니다.",
        )
        return None
    return value


def _require_list(
    parent: Dict[str, Any],
    field: str,
    checks: _Checks,
) -> Optional[List[Any]]:
    value = parent.get(field)
    if not isinstance(value, list):
        checks.add(
            "RAW_CONTRACT_REQUIRED_FIELD",
            False,
            field,
            "필수 array가 없습니다.",
        )
        return None
    return value


def _safe_path(
    *,
    path_text: str,
    allowed_root_text: str,
) -> Tuple[Optional[Path], Optional[str]]:
    if not allowed_root_text:
        return None, "허용 디렉터리가 설정되지 않았습니다."
    root = Path(allowed_root_text).expanduser().resolve()
    configured = Path(path_text).expanduser()
    if not configured.is_absolute():
        configured = root / configured
    resolved = configured.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None, "파일이 설정된 허용 디렉터리 밖에 있습니다."
    return resolved, None


def _load_artifact(
    *,
    path_text: str,
    allowed_root_text: str,
    maximum_bytes: int,
) -> Tuple[Optional[_LoadedArtifact], Optional[str]]:
    path, path_error = _safe_path(
        path_text=path_text,
        allowed_root_text=allowed_root_text,
    )
    if path_error is not None or path is None:
        return None, path_error
    if maximum_bytes <= 0:
        return None, "최대 파일 크기는 양수여야 합니다."
    try:
        stat = path.stat()
    except OSError:
        return None, "설정된 파일을 찾을 수 없습니다."
    if not path.is_file():
        return None, "설정된 경로가 일반 파일이 아닙니다."
    if stat.st_size > maximum_bytes:
        return None, "설정된 최대 파일 크기를 초과했습니다."
    try:
        raw = path.read_bytes()
    except OSError:
        return None, "설정된 파일을 읽을 수 없습니다."
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "UTF-8 JSON 파일이 아닙니다."
    if not isinstance(parsed, dict):
        return None, "JSON 최상위 값은 object여야 합니다."
    return (
        _LoadedArtifact(
            data=parsed,
            filename=path.name,
            sha256=hashlib.sha256(raw).hexdigest(),
        ),
        None,
    )


def _load_pinned_file(
    *,
    path_text: str,
    allowed_root_text: str,
    maximum_bytes: int,
) -> Tuple[Optional[_LoadedPinnedFile], Optional[str]]:
    path, path_error = _safe_path(
        path_text=path_text,
        allowed_root_text=allowed_root_text,
    )
    if path_error is not None or path is None:
        return None, path_error
    if maximum_bytes <= 0:
        return None, "최대 파일 크기는 양수여야 합니다."
    try:
        stat = path.stat()
    except OSError:
        return None, "설정된 파일을 찾을 수 없습니다."
    if not path.is_file():
        return None, "설정된 경로가 일반 파일이 아닙니다."
    if stat.st_size > maximum_bytes:
        return None, "설정된 최대 파일 크기를 초과했습니다."
    try:
        raw = path.read_bytes()
    except OSError:
        return None, "설정된 파일을 읽을 수 없습니다."
    return (
        _LoadedPinnedFile(
            path=path,
            raw=raw,
            sha256=hashlib.sha256(raw).hexdigest(),
        ),
        None,
    )


def _matches_expected_sha256(
    loaded: _LoadedPinnedFile,
    expected_sha256: str,
) -> bool:
    return (
        bool(SHA256_PATTERN.fullmatch(expected_sha256))
        and loaded.sha256 == expected_sha256
    )


def _status_result(
    *,
    status: str,
    provider_mode: str,
    check: str,
    detail: str,
    warning: Optional[str] = None,
) -> KbMacroHedgeReferenceResult:
    checks = _Checks()
    checks.add(check, False, None, detail)
    if warning is not None:
        checks.warn(warning)
    return KbMacroHedgeReferenceResult(
        status=status,
        provider_mode=provider_mode,
        pricing_status="UNKNOWN",
        validation=checks.model(),
        warnings=checks.warnings,
    )


def _current_trade_values(
    stage2_input: Stage2Input,
    *,
    provider_mode: str = "file",
) -> Tuple[
    Optional[Dict[str, Any]],
    Optional[KbMacroHedgeReferenceResult],
]:
    mode = provider_mode
    if len(stage2_input.exposures) != 1:
        return None, _status_result(
            status="UNSUPPORTED_EXPOSURE",
            provider_mode=mode,
            check="SINGLE_EXPOSURE",
            detail="외부 v1은 정확히 한 건의 거래만 지원합니다.",
        )
    exposure = stage2_input.exposures[0]
    if exposure.trade_type != "IMPORT":
        return None, _status_result(
            status="UNSUPPORTED_EXPOSURE",
            provider_mode=mode,
            check="USD_PAYABLE_ONLY",
            detail="수출·수취 거래는 외부 v1 지원 범위가 아닙니다.",
        )
    if exposure.currency.upper() != "USD":
        return None, _status_result(
            status="UNSUPPORTED_EXPOSURE",
            provider_mode=mode,
            check="USD_ONLY",
            detail="외부 v1은 USD 지급 노출만 지원합니다.",
        )
    if exposure.same_currency_flows:
        return None, _status_result(
            status="UNSUPPORTED_EXPOSURE",
            provider_mode=mode,
            check="NO_SAME_CURRENCY_FLOWS",
            detail="같은 통화 자연상계 흐름은 외부 v1에 매핑하지 않습니다.",
        )
    try:
        amount = Decimal(exposure.foreign_amount)
        cash = Decimal(exposure.usable_fx_balance)
        forward = Decimal(
            exposure.existing_hedge.amount
            if exposure.existing_hedge is not None
            else "0"
        )
        date.fromisoformat(exposure.settlement_date)
    except (InvalidOperation, ValueError):
        return None, _status_result(
            status="UNSUPPORTED_EXPOSURE",
            provider_mode=mode,
            check="VALID_EXPOSURE_VALUES",
            detail="금액 또는 단일 지급일을 확정할 수 없습니다.",
        )
    if not all(value.is_finite() for value in (amount, cash, forward)):
        return None, _status_result(
            status="UNSUPPORTED_EXPOSURE",
            provider_mode=mode,
            check="FINITE_EXPOSURE_VALUES",
            detail="금액은 유한한 Decimal이어야 합니다.",
        )
    if amount <= 0 or cash < 0 or forward < 0:
        return None, _status_result(
            status="UNSUPPORTED_EXPOSURE",
            provider_mode=mode,
            check="NONNEGATIVE_EXPOSURE_VALUES",
            detail="지급액은 양수이고 보유 USD와 기존 선물환은 0 이상이어야 합니다.",
        )
    if cash + forward > amount:
        return None, _status_result(
            status="UNSUPPORTED_EXPOSURE",
            provider_mode=mode,
            check="NO_OVER_OFFSET",
            detail="보유 USD와 기존 선물환 합이 지급액을 초과합니다.",
        )
    if stage2_input.confirmed_trade_sha256 is None:
        return None, _status_result(
            status="VALIDATION_FAILED",
            provider_mode=mode,
            check="SOURCE_TRADE_SHA",
            detail="확정 거래 SHA-256이 없습니다.",
        )
    return (
        {
            "amount": amount,
            "cash": cash,
            "forward": forward,
            "net": amount - cash - forward,
            "payment_date": exposure.settlement_date,
            "source_trade_sha256": (
                stage2_input.confirmed_trade_sha256
            ),
        },
        None,
    )


def _request_hash(request: KbMacroHedgeRequest) -> str:
    payload = json.dumps(
        request.model_dump(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_user_constraints(
    company: Dict[str, Any],
    checks: _Checks,
) -> Optional[Dict[str, Any]]:
    decimal_fields = (
        "payment_certainty",
        "maximum_acceptable_cost_krw",
        "maximum_budget_exceedance_probability",
        "maximum_total_hedge_ratio",
        "option_premium_budget_krw",
    )
    parsed: Dict[str, Any] = {}
    for field in decimal_fields:
        parsed[field] = _parse_decimal(
            company.get(field),
            field="company_exposure.{}".format(field),
            checks=checks,
        )
    risk_tolerance = company.get("risk_tolerance")
    risk_ok = risk_tolerance in {"low", "medium", "high"}
    checks.add(
        "RISK_TOLERANCE",
        risk_ok,
        "company_exposure.risk_tolerance",
        (
            "low, medium, high 중 하나입니다."
            if risk_ok
            else "지원하는 위험성향 값이 아닙니다."
        ),
    )
    allowed = company.get("allowed_instruments")
    allowed_ok = (
        isinstance(allowed, list)
        and bool(allowed)
        and all(item in KNOWN_INSTRUMENTS for item in allowed)
    )
    checks.add(
        "ALLOWED_INSTRUMENTS",
        allowed_ok,
        "company_exposure.allowed_instruments",
        (
            "알려진 상품만 포함합니다."
            if allowed_ok
            else "비어 있거나 알려지지 않은 상품이 포함되어 있습니다."
        ),
    )
    if any(parsed[field] is None for field in decimal_fields):
        return None
    certainty = parsed["payment_certainty"]
    maximum_probability = parsed[
        "maximum_budget_exceedance_probability"
    ]
    maximum_ratio = parsed["maximum_total_hedge_ratio"]
    maximum_cost = parsed["maximum_acceptable_cost_krw"]
    premium_budget = parsed["option_premium_budget_krw"]
    ranges_ok = (
        Decimal("0") <= certainty <= Decimal("1")
        and Decimal("0") <= maximum_probability <= Decimal("1")
        and Decimal("0") <= maximum_ratio <= Decimal("1")
        and maximum_cost > 0
        and premium_budget >= 0
    )
    checks.add(
        "USER_CONSTRAINT_RANGES",
        ranges_ok,
        "company_exposure",
        (
            "사용자 제약의 범위가 유효합니다."
            if ranges_ok
            else "사용자 제약의 허용 범위를 벗어났습니다."
        ),
    )
    if not risk_ok or not allowed_ok or not ranges_ok:
        return None
    parsed["risk_tolerance"] = risk_tolerance
    parsed["allowed_instruments"] = allowed
    return parsed


def evaluate_kb_macro_hedge_reference(
    *,
    settings: Settings,
    stage2_input: Optional[Stage2Input] = None,
    stage2_result: Optional[Stage2Result] = None,
    binding_mode: str = "UPSTREAM_FIXTURE_SELF_TEST",
    fixture_constraints_confirmed: bool = False,
    constraints_source: str = "UPSTREAM_FILE_CONFIRMED_BY_USER",
) -> Optional[KbMacroHedgeReferenceResult]:
    """Validate a read-only kb_macro_ai file result.

    The normalized result never replaces Stage 3 and is never forwarded to
    Stage 4 or Stage 5.
    """

    if not getattr(settings, "enable_kb_macro_hedge_reference", False):
        return None
    mode = settings.kb_macro_hedge_mode
    if mode == "off":
        return None
    if mode not in {"fixture", "file"}:
        return _status_result(
            status="UPSTREAM_UNAVAILABLE",
            provider_mode="off",
            check="PROVIDER_MODE",
            detail="provider mode는 off, fixture, file 중 하나여야 합니다.",
        )
    current_values: Optional[Dict[str, Any]] = None
    if binding_mode == "CURRENT_CONFIRMED_TRADE":
        if stage2_input is None:
            return _status_result(
                status="UNSUPPORTED_EXPOSURE",
                provider_mode=mode,
                check="CURRENT_STAGE2_INPUT",
                detail="현재 확정 거래의 Stage 2 입력이 없습니다.",
            )
        current_values, unsupported = _current_trade_values(
            stage2_input,
            provider_mode=mode,
        )
        if unsupported is not None:
            return unsupported.model_copy(
                update={"provider_mode": mode}
            )
    elif binding_mode != "UPSTREAM_FIXTURE_SELF_TEST":
        return _status_result(
            status="VALIDATION_FAILED",
            provider_mode=mode,
            check="BINDING_MODE",
            detail="지원하지 않는 거래 결속 검증 방식입니다.",
        )

    forecast, forecast_error = _load_artifact(
        path_text=settings.kb_macro_forecast_file,
        allowed_root_text=settings.kb_macro_hedge_allowed_root,
        maximum_bytes=settings.kb_macro_max_file_bytes,
    )
    hedge, hedge_error = _load_artifact(
        path_text=settings.kb_macro_hedge_file,
        allowed_root_text=settings.kb_macro_hedge_allowed_root,
        maximum_bytes=settings.kb_macro_max_file_bytes,
    )
    if forecast_error is not None or hedge_error is not None:
        return _status_result(
            status="UPSTREAM_UNAVAILABLE",
            provider_mode=mode,
            check="PROVIDER_FILES_AVAILABLE",
            detail="forecast 또는 hedge JSON을 안전하게 읽지 못했습니다.",
            warning="INTERNAL_STAGE3_FALLBACK_REMAINS_ACTIVE",
        )
    if forecast is None or hedge is None:
        return _status_result(
            status="UPSTREAM_UNAVAILABLE",
            provider_mode=mode,
            check="PROVIDER_FILES_AVAILABLE",
            detail="forecast 또는 hedge JSON이 없습니다.",
        )

    checks = _Checks()
    for warning in (
        "UPSTREAM_JSON_SCHEMAS_NOT_PROVIDED",
        "UPSTREAM_CONTRACT_MANIFEST_NOT_PROVIDED",
        "PRODUCER_COMMIT_NOT_EMBEDDED_IN_RESPONSE",
        "REQUEST_AND_FORECAST_HASHES_NOT_EMBEDDED_IN_RESPONSE",
        "UPSTREAM_RAW_NUMBERS_ORIGINATED_AS_FLOAT",
        "NOT_CONNECTED_TO_STAGE4_OR_STAGE5",
    ):
        checks.warn(warning)
    if binding_mode == "UPSTREAM_FIXTURE_SELF_TEST":
        checks.warn("CURRENT_TRADE_BINDING_NOT_CHECKED")

    commit_sha = settings.kb_macro_expected_provider_commit_sha
    commit_ok = (
        bool(COMMIT_PATTERN.fullmatch(commit_sha))
        and commit_sha == SUPPORTED_PROVIDER_COMMIT_SHA
    )
    checks.add(
        "PINNED_PRODUCER_COMMIT",
        commit_ok,
        "settings.kb_macro_expected_provider_commit_sha",
        (
            "운영자가 40자리 producer commit을 고정했습니다."
            if commit_ok
            else "검토·허용된 producer commit과 정확히 일치해야 합니다."
        ),
    )
    expected_forecast_sha = (
        settings.kb_macro_expected_forecast_sha256
    )
    expected_hedge_sha = settings.kb_macro_expected_hedge_sha256
    forecast_sha_ok = (
        bool(SHA256_PATTERN.fullmatch(expected_forecast_sha))
        and forecast.sha256 == expected_forecast_sha
    )
    hedge_sha_ok = (
        bool(SHA256_PATTERN.fullmatch(expected_hedge_sha))
        and hedge.sha256 == expected_hedge_sha
    )
    checks.add(
        "FORECAST_SHA256",
        forecast_sha_ok,
        "forecast_sha256",
        (
            "고정 forecast SHA-256과 일치합니다."
            if forecast_sha_ok
            else "고정 forecast SHA-256이 없거나 파일과 다릅니다."
        ),
    )
    checks.add(
        "HEDGE_SHA256",
        hedge_sha_ok,
        "hedge_sha256",
        (
            "고정 hedge SHA-256과 일치합니다."
            if hedge_sha_ok
            else "고정 hedge SHA-256이 없거나 파일과 다릅니다."
        ),
    )

    forecast_schema = forecast.data.get("schema_version")
    hedge_schema = hedge.data.get("schema_version")
    checks.add(
        "FORECAST_SCHEMA_VERSION",
        forecast_schema == FORECAST_SCHEMA_VERSION,
        "forecast.schema_version",
        "forecast schema exact match를 확인했습니다.",
    )
    checks.add(
        "HEDGE_SCHEMA_VERSION",
        hedge_schema == HEDGE_SCHEMA_VERSION,
        "hedge.schema_version",
        "hedge schema exact match를 확인했습니다.",
    )
    forecast_horizon = _require_dict(
        forecast.data,
        "horizon",
        checks,
    )
    forecast_reference = _require_dict(
        hedge.data,
        "forecast_json_reference",
        checks,
    )
    company = _require_dict(
        hedge.data,
        "company_exposure",
        checks,
    )
    calculation = _require_dict(
        hedge.data,
        "exposure_calculation",
        checks,
    )
    alignment = _require_dict(
        hedge.data,
        "horizon_alignment",
        checks,
    )
    pricing = _require_dict(
        hedge.data,
        "pricing_snapshot",
        checks,
    )
    verification = _require_dict(
        hedge.data,
        "verification",
        checks,
    )
    candidates_raw = _require_list(
        hedge.data,
        "recommended_hedge_combinations",
        checks,
    )
    required_blocks = (
        forecast_horizon,
        forecast_reference,
        company,
        calculation,
        alignment,
        pricing,
        verification,
        candidates_raw,
    )
    if any(value is None for value in required_blocks):
        return KbMacroHedgeReferenceResult(
            status="VALIDATION_FAILED",
            provider_mode=mode,
            pricing_status="UNKNOWN",
            validation=checks.model(),
            warnings=checks.warnings,
        )
    assert forecast_horizon is not None
    assert forecast_reference is not None
    assert company is not None
    assert calculation is not None
    assert alignment is not None
    assert pricing is not None
    assert verification is not None
    assert candidates_raw is not None

    prediction_date = forecast.data.get("prediction_date")
    horizon_days = forecast_horizon.get("trading_days")
    reference_match = (
        forecast_reference.get("schema_version")
        == FORECAST_SCHEMA_VERSION
        and forecast_reference.get("prediction_date")
        == prediction_date
        and forecast_reference.get("horizon_trading_days")
        == horizon_days
    )
    checks.add(
        "FORECAST_REFERENCE_MATCH",
        reference_match,
        "forecast_json_reference",
        (
            "forecast와 hedge의 버전·기준일·기간이 일치합니다."
            if reference_match
            else "forecast와 hedge의 버전·기준일·기간이 다릅니다."
        ),
    )
    date_ok = isinstance(prediction_date, str)
    try:
        if not date_ok:
            raise ValueError
        date.fromisoformat(prediction_date)
    except ValueError:
        date_ok = False
    horizon_ok = (
        isinstance(horizon_days, int)
        and not isinstance(horizon_days, bool)
        and horizon_days > 0
    )
    checks.add(
        "FORECAST_DATE_AND_HORIZON",
        date_ok and horizon_ok,
        "forecast",
        "prediction date와 양의 trading-day horizon을 확인했습니다.",
    )
    within_horizon = alignment.get("within_three_trading_days")
    if within_horizon is not True:
        checks.warn("PAYMENT_DATE_OUTSIDE_THREE_TRADING_DAYS")

    constraints = _validate_user_constraints(company, checks)
    checks.add(
        "EXPLICIT_FIXTURE_CONSTRAINT_CONFIRMATION",
        fixture_constraints_confirmed,
        "fixture_constraints_confirmed",
        (
            "외부 파일의 목업 제약조건을 참고 검증에 사용하도록 확인했습니다."
            if fixture_constraints_confirmed
            else "목업 제약조건을 사용한다는 명시적 확인이 필요합니다."
        ),
    )

    amount = _parse_decimal(
        company.get("amount_usd"),
        field="company_exposure.amount_usd",
        checks=checks,
    )
    cash = _parse_decimal(
        company.get("existing_usd_cash"),
        field="company_exposure.existing_usd_cash",
        checks=checks,
    )
    forward = _parse_decimal(
        company.get("existing_forward_usd"),
        field="company_exposure.existing_forward_usd",
        checks=checks,
    )
    payment_date = company.get("payment_date")
    company_values_ok = (
        company.get("exposure_type") == "usd_payable"
        and amount is not None
        and amount > 0
        and cash is not None
        and cash >= 0
        and forward is not None
        and forward >= 0
        and cash + forward <= amount
        and isinstance(payment_date, str)
    )
    try:
        if not isinstance(payment_date, str):
            raise ValueError
        date.fromisoformat(payment_date)
    except ValueError:
        company_values_ok = False
    checks.add(
        "SUPPORTED_COMPANY_EXPOSURE",
        company_values_ok,
        "company_exposure",
        (
            "단일 USD 지급 fixture 입력이 유효합니다."
            if company_values_ok
            else "USD 지급 fixture 입력이 유효하지 않습니다."
        ),
    )
    if amount is None or cash is None or forward is None:
        company_values_ok = False
        net = None
    else:
        net = amount - cash - forward

    if binding_mode == "CURRENT_CONFIRMED_TRADE":
        assert current_values is not None
        echo_match = (
            company_values_ok
            and amount == current_values["amount"]
            and cash == current_values["cash"]
            and forward == current_values["forward"]
            and payment_date == current_values["payment_date"]
        )
        checks.add(
            "CURRENT_TRADE_ECHO_MATCH",
            echo_match,
            "company_exposure",
            (
                "현재 확정 거래와 외부 response echo가 일치합니다."
                if echo_match
                else "현재 확정 거래와 외부 response echo가 다릅니다."
            ),
        )
        if stage2_result is not None and net is not None:
            stage2_open = _parse_decimal(
                stage2_result.open_exposure,
                field="stage2_result.open_exposure",
                checks=checks,
            )
            stage2_match = (
                stage2_result.trade_type == "IMPORT"
                and stage2_result.currency.upper() == "USD"
                and stage2_open == net
            )
            checks.add(
                "STAGE2_NET_EXPOSURE_MATCH",
                stage2_match,
                "stage2_result.open_exposure",
                (
                    "Stage 2 open exposure와 외부 순노출이 일치합니다."
                    if stage2_match
                    else "Stage 2 open exposure와 외부 순노출이 다릅니다."
                ),
            )
        source_trade_sha256 = current_values[
            "source_trade_sha256"
        ]
    else:
        source_trade_sha256 = None

    calc_gross = _parse_decimal(
        calculation.get("gross_exposure_usd"),
        field="exposure_calculation.gross_exposure_usd",
        checks=checks,
    )
    calc_cash = _parse_decimal(
        calculation.get("natural_hedge_usd"),
        field="exposure_calculation.natural_hedge_usd",
        checks=checks,
    )
    calc_forward = _parse_decimal(
        calculation.get("existing_forward_usd"),
        field="exposure_calculation.existing_forward_usd",
        checks=checks,
    )
    calc_net = _parse_decimal(
        calculation.get("net_exposure_usd"),
        field="exposure_calculation.net_exposure_usd",
        checks=checks,
    )
    net_match = (
        net is not None
        and calc_gross == amount
        and calc_cash == cash
        and calc_forward == forward
        and calc_net == net
        and net >= 0
    )
    checks.add(
        "NET_EXPOSURE_CALCULATION",
        net_match,
        "exposure_calculation",
        (
            "gross-cash-forward 순노출 계산이 일치합니다."
            if net_match
            else "순노출 계산 또는 입력 echo가 일치하지 않습니다."
        ),
    )

    quotes_are_mock = pricing.get("quotes_are_mock")
    pricing_flag_ok = isinstance(quotes_are_mock, bool)
    checks.add(
        "PRICING_STATUS_PRESENT",
        pricing_flag_ok,
        "pricing_snapshot.quotes_are_mock",
        (
            "목업/실제 가격 상태가 명시되어 있습니다."
            if pricing_flag_ok
            else "가격 상태 boolean이 없습니다."
        ),
    )
    pricing_status = (
        "MOCK"
        if quotes_are_mock is True
        else ("ACTUAL" if quotes_are_mock is False else "UNKNOWN")
    )
    if quotes_are_mock is True:
        checks.warn("MOCK_QUOTES")
    elif quotes_are_mock is False:
        checks.warn("ACTUAL_QUOTE_PROVENANCE_NOT_VERIFIED")

    normalized_candidates: List[KbMacroHedgeCandidate] = []
    count_ok = len(candidates_raw) == 3
    checks.add(
        "EXACTLY_THREE_CANDIDATES",
        count_ok,
        "recommended_hedge_combinations",
        (
            "후보가 정확히 3개입니다."
            if count_ok
            else "후보 개수가 정확히 3개가 아닙니다."
        ),
    )
    candidate_valid = count_ok and net is not None
    ranks: List[int] = []
    objectives: List[Decimal] = []
    option_quotes = pricing.get("option_quotes")
    option_ids = set()
    if isinstance(option_quotes, list):
        option_ids = {
            item.get("option_id")
            for item in option_quotes
            if isinstance(item, dict)
            and isinstance(item.get("option_id"), str)
        }
    for index, raw_candidate in enumerate(candidates_raw):
        prefix = "recommended_hedge_combinations[{}]".format(index)
        if not isinstance(raw_candidate, dict):
            checks.add(
                "CANDIDATE_STRUCTURE",
                False,
                prefix,
                "후보가 object가 아닙니다.",
            )
            candidate_valid = False
            continue
        rank = raw_candidate.get("rank")
        strategy = raw_candidate.get("strategy_type")
        rank_ok = (
            isinstance(rank, int)
            and not isinstance(rank, bool)
            and rank in {1, 2, 3}
        )
        strategy_ok = strategy in KNOWN_STRATEGIES
        if rank_ok:
            ranks.append(rank)
        else:
            candidate_valid = False
        if not strategy_ok:
            candidate_valid = False
        forward_ratio = _parse_decimal(
            raw_candidate.get("forward_ratio"),
            field="{}.forward_ratio".format(prefix),
            checks=checks,
        )
        option_ratio = _parse_decimal(
            raw_candidate.get("option_ratio"),
            field="{}.option_ratio".format(prefix),
            checks=checks,
        )
        unhedged_ratio = _parse_decimal(
            raw_candidate.get("unhedged_ratio"),
            field="{}.unhedged_ratio".format(prefix),
            checks=checks,
        )
        notional = _require_dict(
            raw_candidate,
            "notional_usd",
            checks,
        )
        scenario = _require_dict(
            raw_candidate,
            "scenario_metrics",
            checks,
        )
        objective = _require_dict(
            raw_candidate,
            "objective_components_krw",
            checks,
        )
        if notional is None or scenario is None or objective is None:
            candidate_valid = False
            continue
        forward_notional = _parse_decimal(
            notional.get("forward"),
            field="{}.notional_usd.forward".format(prefix),
            checks=checks,
        )
        option_notional = _parse_decimal(
            notional.get("call_option"),
            field="{}.notional_usd.call_option".format(prefix),
            checks=checks,
        )
        unhedged_notional = _parse_decimal(
            notional.get("unhedged"),
            field="{}.notional_usd.unhedged".format(prefix),
            checks=checks,
        )
        option_premium = _parse_decimal(
            raw_candidate.get("option_premium_krw"),
            field="{}.option_premium_krw".format(prefix),
            checks=checks,
        )
        expected_cost = _parse_decimal(
            scenario.get("expected_cost_krw"),
            field="{}.scenario_metrics.expected_cost_krw".format(
                prefix
            ),
            checks=checks,
        )
        cvar_cost = _parse_decimal(
            scenario.get("cvar_95_cost_krw"),
            field="{}.scenario_metrics.cvar_95_cost_krw".format(
                prefix
            ),
            checks=checks,
        )
        objective_score = _parse_decimal(
            objective.get("total_objective_score"),
            field=(
                "{}.objective_components_krw."
                "total_objective_score".format(prefix)
            ),
            checks=checks,
        )
        parsed_values = (
            forward_ratio,
            option_ratio,
            unhedged_ratio,
            forward_notional,
            option_notional,
            unhedged_notional,
            option_premium,
            expected_cost,
            cvar_cost,
            objective_score,
        )
        if any(value is None for value in parsed_values):
            candidate_valid = False
            continue
        assert forward_ratio is not None
        assert option_ratio is not None
        assert unhedged_ratio is not None
        assert forward_notional is not None
        assert option_notional is not None
        assert unhedged_notional is not None
        assert option_premium is not None
        assert expected_cost is not None
        assert cvar_cost is not None
        assert objective_score is not None
        ratio_ok = (
            all(
                Decimal("0") <= value <= Decimal("1")
                for value in (
                    forward_ratio,
                    option_ratio,
                    unhedged_ratio,
                )
            )
            and (
                forward_ratio + option_ratio + unhedged_ratio
                == Decimal("1")
            )
        )
        notional_ok = (
            net is not None
            and all(
                Decimal("0") <= value <= net
                for value in (
                    forward_notional,
                    option_notional,
                    unhedged_notional,
                )
            )
            and (
                forward_notional
                + option_notional
                + unhedged_notional
                == net
            )
        )
        ratio_notional_ok = (
            net is not None
            and forward_notional == net * forward_ratio
            and option_notional == net * option_ratio
            and unhedged_notional == net * unhedged_ratio
        )
        option = raw_candidate.get("option")
        option_id = (
            option.get("option_id")
            if isinstance(option, dict)
            else None
        )
        option_ok = (
            (
                option_ratio == 0
                and option_notional == 0
                and option is None
            )
            or (
                option_ratio > 0
                and "vanilla_usd_call"
                in (
                    constraints["allowed_instruments"]
                    if constraints is not None
                    else []
                )
                and isinstance(option_id, str)
                and option_id in option_ids
            )
        )
        forward_ok = (
            forward_ratio == 0
            or (
                constraints is not None
                and "forward" in constraints["allowed_instruments"]
            )
        )
        checks.add(
            "CANDIDATE_{}_RATIOS".format(index + 1),
            ratio_ok,
            prefix,
            "후보 비율 범위와 합계를 확인했습니다.",
        )
        checks.add(
            "CANDIDATE_{}_NOTIONALS".format(index + 1),
            notional_ok and ratio_notional_ok,
            prefix,
            "후보 notional 범위·합계·비율 일치를 확인했습니다.",
        )
        checks.add(
            "CANDIDATE_{}_INSTRUMENTS".format(index + 1),
            strategy_ok and option_ok and forward_ok,
            prefix,
            "알려진 전략과 옵션 quote만 사용했습니다.",
        )
        if not (
            rank_ok
            and strategy_ok
            and ratio_ok
            and notional_ok
            and ratio_notional_ok
            and option_ok
            and forward_ok
        ):
            candidate_valid = False
            continue
        objectives.append(objective_score)
        normalized_candidates.append(
            KbMacroHedgeCandidate(
                rank=rank,
                strategy_type=strategy,
                forward_ratio=_decimal_text(forward_ratio),
                call_option_ratio=_decimal_text(option_ratio),
                unhedged_ratio=_decimal_text(unhedged_ratio),
                forward_notional_usd=_decimal_text(
                    forward_notional
                ),
                call_option_notional_usd=_decimal_text(
                    option_notional
                ),
                unhedged_notional_usd=_decimal_text(
                    unhedged_notional
                ),
                option_id=option_id,
                option_premium_krw=_decimal_text(option_premium),
                expected_cost_krw=_decimal_text(expected_cost),
                cvar_95_cost_krw=_decimal_text(cvar_cost),
                objective_score_krw=_decimal_text(
                    objective_score
                ),
            )
        )
    rank_order_ok = sorted(ranks) == [1, 2, 3] and len(set(ranks)) == 3
    objective_order_ok = (
        len(objectives) == 3
        and objectives == sorted(objectives)
    )
    checks.add(
        "RANKS_EXACT_AND_UNIQUE",
        rank_order_ok,
        "recommended_hedge_combinations.rank",
        "rank가 1, 2, 3이며 중복되지 않습니다.",
    )
    checks.add(
        "OBJECTIVE_SCORE_ORDER",
        objective_order_ok,
        "recommended_hedge_combinations",
        "objective score가 rank 순서대로 오름차순입니다.",
    )
    if not rank_order_ok or not objective_order_ok:
        candidate_valid = False

    finite_certificate = _require_dict(
        verification,
        "finite_grid_optimality_certificate",
        checks,
    )
    constraint_certificate = _require_dict(
        verification,
        "constraints",
        checks,
    )
    certificate_ok = (
        finite_certificate is not None
        and constraint_certificate is not None
        and finite_certificate.get("enumeration_complete") is True
        and finite_certificate.get(
            "top3_are_lowest_objective_scores"
        )
        is True
        and constraint_certificate.get("no_over_hedging") is True
        and constraint_certificate.get(
            "option_premium_within_budget"
        )
        is True
        and constraint_certificate.get("ratios_sum_to_one") is True
    )
    checks.add(
        "CERTIFICATE_REQUIRED_BOOLEANS",
        certificate_ok,
        "verification",
        (
            "필수 certificate boolean이 모두 true입니다."
            if certificate_ok
            else "필수 certificate boolean이 없거나 false입니다."
        ),
    )
    prototype_notice = hedge.data.get("prototype_notice")
    notice_ok = (
        isinstance(prototype_notice, str)
        and bool(prototype_notice.strip())
    )
    checks.add(
        "PROTOTYPE_NOTICE",
        notice_ok,
        "prototype_notice",
        (
            "prototype 고지가 있습니다."
            if notice_ok
            else "prototype 고지가 없습니다."
        ),
    )
    if notice_ok:
        checks.warn("PROTOTYPE_ONLY")

    if (
        company_values_ok
        and constraints is not None
        and net is not None
        and isinstance(payment_date, str)
    ):
        request_seed = {
            "binding_mode": binding_mode,
            "source_trade_sha256": source_trade_sha256,
            "amount_usd": _decimal_text(amount),
            "payment_date": payment_date,
            "existing_usd_cash": _decimal_text(cash),
            "existing_forward_usd": _decimal_text(forward),
            "forecast_sha256": forecast.sha256,
            "producer_commit_sha": commit_sha,
            "payment_certainty": _decimal_text(
                constraints["payment_certainty"]
            ),
            "maximum_acceptable_cost_krw": _decimal_text(
                constraints["maximum_acceptable_cost_krw"]
            ),
            "maximum_budget_exceedance_probability": _decimal_text(
                constraints[
                    "maximum_budget_exceedance_probability"
                ]
            ),
            "risk_tolerance": constraints["risk_tolerance"],
            "maximum_total_hedge_ratio": _decimal_text(
                constraints["maximum_total_hedge_ratio"]
            ),
            "option_premium_budget_krw": _decimal_text(
                constraints["option_premium_budget_krw"]
            ),
            "allowed_instruments": constraints[
                "allowed_instruments"
            ],
            "constraints_source": constraints_source,
        }
        seed_hash = hashlib.sha256(
            json.dumps(
                request_seed,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        request = KbMacroHedgeRequest(
            request_id="kbm-{}".format(seed_hash[:16]),
            binding_mode=binding_mode,
            source_trade_sha256=source_trade_sha256,
            amount_usd=_decimal_text(amount),
            payment_date=payment_date,
            existing_usd_cash=_decimal_text(cash),
            existing_forward_usd=_decimal_text(forward),
            net_exposure_usd=_decimal_text(net),
            payment_certainty=_decimal_text(
                constraints["payment_certainty"]
            ),
            maximum_acceptable_cost_krw=_decimal_text(
                constraints["maximum_acceptable_cost_krw"]
            ),
            maximum_budget_exceedance_probability=_decimal_text(
                constraints[
                    "maximum_budget_exceedance_probability"
                ]
            ),
            risk_tolerance=constraints["risk_tolerance"],
            maximum_total_hedge_ratio=_decimal_text(
                constraints["maximum_total_hedge_ratio"]
            ),
            option_premium_budget_krw=_decimal_text(
                constraints["option_premium_budget_krw"]
            ),
            allowed_instruments=constraints[
                "allowed_instruments"
            ],
            constraints_source=constraints_source,
        )
        request_sha256 = _request_hash(request)
    else:
        request = None
        request_sha256 = "0" * 64

    provenance: Optional[KbMacroHedgeProvenance]
    if (
        commit_ok
        and date_ok
        and horizon_ok
        and request is not None
    ):
        provenance = KbMacroHedgeProvenance(
            producer_commit_sha=commit_sha,
            request_sha256=request_sha256,
            forecast_sha256=forecast.sha256,
            hedge_sha256=hedge.sha256,
            forecast_schema_version=str(forecast_schema),
            hedge_schema_version=str(hedge_schema),
            prediction_date=str(prediction_date),
            horizon_trading_days=int(horizon_days),
            forecast_filename=forecast.filename,
            hedge_filename=hedge.filename,
        )
    else:
        provenance = None

    if not checks.passed or not candidate_valid:
        normalized_candidates = []
        status = "VALIDATION_FAILED"
    elif pricing_status == "MOCK":
        status = "REFERENCE_ONLY"
    else:
        # The upstream repository does not publish formal JSON Schemas or an
        # embedded producer commit/manifest yet. Do not promote the provisional
        # file contract to READY even if a future file says quotes are actual.
        status = "REFERENCE_ONLY"
        checks.warn("FORMAL_UPSTREAM_CONTRACT_REQUIRED_FOR_READY")
    return KbMacroHedgeReferenceResult(
        status=status,
        provider_mode=mode,
        pricing_status=pricing_status,
        request=request,
        provenance=provenance,
        validation=checks.model(),
        candidates=normalized_candidates,
        warnings=checks.warnings,
    )


def _local_cli_failure(
    *,
    check: str,
    detail: str,
    status: str = "UPSTREAM_UNAVAILABLE",
) -> KbMacroHedgeReferenceResult:
    return _status_result(
        status=status,
        provider_mode="local_cli",
        check=check,
        detail=detail,
        warning="INTERNAL_STAGE3_FALLBACK_REMAINS_ACTIVE",
    )


def _run_pinned_git_check(
    *,
    repo_root: Path,
    expected_commit_sha: str,
    command_runner: Any,
    timeout_seconds: float,
    maximum_output_bytes: int,
) -> Optional[KbMacroHedgeReferenceResult]:
    if (
        not COMMIT_PATTERN.fullmatch(expected_commit_sha)
        or expected_commit_sha != SUPPORTED_PROVIDER_COMMIT_SHA
    ):
        return _local_cli_failure(
            check="PRODUCER_COMMIT_PIN",
            detail="지원하는 kb_macro_ai producer commit이 고정되지 않았습니다.",
            status="VALIDATION_FAILED",
        )
    commands = (
        (
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            expected_commit_sha,
            "PRODUCER_COMMIT_CHECKOUT",
        ),
        (
            [
                "git",
                "-C",
                str(repo_root),
                "status",
                "--porcelain",
                "--untracked-files=no",
            ],
            "",
            "PRODUCER_TRACKED_WORKTREE_CLEAN",
        ),
    )
    for command, expected_output, check in commands:
        try:
            completed = command_runner(
                command,
                cwd=str(repo_root),
                env={
                    "PATH": os.environ.get(
                        "PATH",
                        "/usr/local/bin:/usr/bin:/bin",
                    )
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return _local_cli_failure(
                check=check,
                detail="kb_macro_ai 저장소 무결성을 확인하지 못했습니다.",
            )
        stdout = completed.stdout or b""
        stderr = completed.stderr or b""
        if isinstance(stdout, str):
            stdout = stdout.encode("utf-8", errors="replace")
        if isinstance(stderr, str):
            stderr = stderr.encode("utf-8", errors="replace")
        if (
            completed.returncode != 0
            or len(stdout) > maximum_output_bytes
            or len(stderr) > maximum_output_bytes
        ):
            return _local_cli_failure(
                check=check,
                detail="kb_macro_ai 저장소 무결성 명령이 안전하게 완료되지 않았습니다.",
            )
        actual_output = stdout.decode(
            "utf-8",
            errors="replace",
        ).strip()
        if actual_output != expected_output:
            return _local_cli_failure(
                check=check,
                detail=(
                    "producer checkout이 고정 commit과 다르거나 "
                    "추적 파일 변경이 있습니다."
                ),
                status="VALIDATION_FAILED",
            )
    return None


def run_kb_macro_hedge_for_confirmed_trade(
    *,
    settings: Settings,
    stage2_input: Optional[Stage2Input],
    stage2_result: Optional[Stage2Result],
    constraints: KbMacroHedgeExecutionConstraints,
    constraints_confirmed: bool,
    command_runner: Any = subprocess.run,
) -> Optional[KbMacroHedgeReferenceResult]:
    """Run the pinned upstream CLI in an isolated temporary workspace.

    Only normalized, revalidated reference data leaves this function. The
    generated company request and raw upstream response are deleted with the
    temporary directory.
    """

    if not getattr(settings, "enable_kb_macro_hedge_reference", False):
        return None
    if getattr(settings, "kb_macro_hedge_mode", "off") != "local_cli":
        return _local_cli_failure(
            check="PROVIDER_MODE",
            detail="현재 거래 실행에는 local_cli provider mode가 필요합니다.",
        )
    if stage2_input is None or stage2_result is None:
        return _local_cli_failure(
            check="CURRENT_STAGE2_RESULT",
            detail="확정 거래의 Stage 2 계산을 먼저 완료해야 합니다.",
            status="UNSUPPORTED_EXPOSURE",
        )
    current_values, unsupported = _current_trade_values(
        stage2_input,
        provider_mode="local_cli",
    )
    if unsupported is not None:
        return unsupported
    assert current_values is not None
    if not constraints_confirmed:
        return _local_cli_failure(
            check="EXPLICIT_USER_CONSTRAINT_CONFIRMATION",
            detail=(
                "외부 모델 제약조건과 목업 견적 사용을 사용자가 "
                "명시적으로 확인해야 합니다."
            ),
            status="VALIDATION_FAILED",
        )
    constraint_checks = _Checks()
    parsed_constraints = _validate_user_constraints(
        constraints.model_dump(),
        constraint_checks,
    )
    if parsed_constraints is None or not constraint_checks.passed:
        return KbMacroHedgeReferenceResult(
            status="VALIDATION_FAILED",
            provider_mode="local_cli",
            pricing_status="UNKNOWN",
            validation=constraint_checks.model(),
            warnings=constraint_checks.warnings,
        )

    allowed_root_text = getattr(
        settings,
        "kb_macro_hedge_allowed_root",
        "",
    )
    if not allowed_root_text:
        return _local_cli_failure(
            check="PROVIDER_ROOT",
            detail="kb_macro_ai 저장소 허용 경로가 설정되지 않았습니다.",
        )
    repo_root = Path(allowed_root_text).expanduser().resolve()
    if not repo_root.is_dir():
        return _local_cli_failure(
            check="PROVIDER_ROOT",
            detail="설정된 kb_macro_ai 저장소 경로를 찾을 수 없습니다.",
        )
    timeout_seconds = getattr(
        settings,
        "kb_macro_cli_timeout_seconds",
        30.0,
    )
    maximum_output_bytes = getattr(
        settings,
        "kb_macro_cli_max_output_bytes",
        64 * 1024,
    )
    if timeout_seconds <= 0 or maximum_output_bytes <= 0:
        return _local_cli_failure(
            check="CLI_RESOURCE_LIMITS",
            detail="CLI timeout과 출력 크기 제한은 양수여야 합니다.",
            status="VALIDATION_FAILED",
        )
    git_failure = _run_pinned_git_check(
        repo_root=repo_root,
        expected_commit_sha=getattr(
            settings,
            "kb_macro_expected_provider_commit_sha",
            "",
        ),
        command_runner=command_runner,
        timeout_seconds=timeout_seconds,
        maximum_output_bytes=maximum_output_bytes,
    )
    if git_failure is not None:
        return git_failure

    maximum_file_bytes = getattr(
        settings,
        "kb_macro_max_file_bytes",
        1024 * 1024,
    )
    pinned_specs = (
        (
            "forecast",
            getattr(settings, "kb_macro_forecast_file", ""),
            getattr(
                settings,
                "kb_macro_expected_forecast_sha256",
                "",
            ),
        ),
        (
            "model_config",
            getattr(settings, "kb_macro_model_config_file", ""),
            getattr(
                settings,
                "kb_macro_expected_model_config_sha256",
                "",
            ),
        ),
        (
            "market_history",
            getattr(settings, "kb_macro_market_history_file", ""),
            getattr(
                settings,
                "kb_macro_expected_market_history_sha256",
                "",
            ),
        ),
        (
            "quote_template",
            getattr(settings, "kb_macro_quote_template_file", ""),
            getattr(
                settings,
                "kb_macro_expected_quote_template_sha256",
                "",
            ),
        ),
    )
    loaded_files: Dict[str, _LoadedPinnedFile] = {}
    for name, path_text, expected_sha256 in pinned_specs:
        loaded, load_error = _load_pinned_file(
            path_text=path_text,
            allowed_root_text=str(repo_root),
            maximum_bytes=maximum_file_bytes,
        )
        if load_error is not None or loaded is None:
            return _local_cli_failure(
                check="PINNED_{}_AVAILABLE".format(name.upper()),
                detail="고정된 kb_macro_ai 입력 파일을 안전하게 읽지 못했습니다.",
            )
        if not _matches_expected_sha256(loaded, expected_sha256):
            return _local_cli_failure(
                check="PINNED_{}_SHA256".format(name.upper()),
                detail="고정된 kb_macro_ai 입력 파일 SHA-256이 다릅니다.",
                status="VALIDATION_FAILED",
            )
        loaded_files[name] = loaded

    try:
        model_config = json.loads(
            loaded_files["model_config"].raw.decode("utf-8")
        )
        quote_template = json.loads(
            loaded_files["quote_template"].raw.decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _local_cli_failure(
            check="PINNED_JSON_FORMAT",
            detail="고정된 model config 또는 quote template이 UTF-8 JSON이 아닙니다.",
            status="VALIDATION_FAILED",
        )
    if (
        not isinstance(model_config, dict)
        or model_config.get("schema_version") != HEDGE_SCHEMA_VERSION
        or not isinstance(quote_template, dict)
        or not isinstance(
            quote_template.get("mock_hedge_quotes"),
            dict,
        )
    ):
        return _local_cli_failure(
            check="PINNED_MODEL_CONTRACT",
            detail="고정된 model config 또는 목업 견적 계약이 올바르지 않습니다.",
            status="VALIDATION_FAILED",
        )

    cli_python = repo_root / ".venv" / "bin" / "python"
    cli_module = (
        repo_root
        / "src"
        / "krw_forecast"
        / "hedge_recommendation_v1_cli.py"
    )
    if (
        not cli_python.exists()
        or not os.access(str(cli_python), os.X_OK)
        or not cli_module.is_file()
    ):
        return _local_cli_failure(
            check="PINNED_CLI_AVAILABLE",
            detail="kb_macro_ai의 Python 3.11 CLI 실행환경을 찾을 수 없습니다.",
        )

    normalized_constraints = {
        key: (
            value
            if not isinstance(value, Decimal)
            else _decimal_text(value)
        )
        for key, value in parsed_constraints.items()
    }
    request_seed = {
        "source_trade_sha256": current_values[
            "source_trade_sha256"
        ],
        "amount_usd": _decimal_text(current_values["amount"]),
        "payment_date": current_values["payment_date"],
        "existing_usd_cash": _decimal_text(current_values["cash"]),
        "existing_forward_usd": _decimal_text(
            current_values["forward"]
        ),
        "constraints": normalized_constraints,
        "forecast_sha256": loaded_files["forecast"].sha256,
    }
    request_seed_sha = hashlib.sha256(
        json.dumps(
            request_seed,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    company_input = {
        "company_id": "KB_AGENT_REDACTED",
        "exposure_id": "kbm-{}".format(request_seed_sha[:16]),
        "exposure_type": "usd_payable",
        "amount_usd": _decimal_text(current_values["amount"]),
        "payment_date": current_values["payment_date"],
        "existing_usd_cash": _decimal_text(current_values["cash"]),
        "existing_forward_usd": _decimal_text(
            current_values["forward"]
        ),
        "payment_certainty": normalized_constraints[
            "payment_certainty"
        ],
        "maximum_acceptable_cost_krw": normalized_constraints[
            "maximum_acceptable_cost_krw"
        ],
        "maximum_budget_exceedance_probability": (
            normalized_constraints[
                "maximum_budget_exceedance_probability"
            ]
        ),
        "risk_tolerance": normalized_constraints["risk_tolerance"],
        "maximum_total_hedge_ratio": normalized_constraints[
            "maximum_total_hedge_ratio"
        ],
        "option_premium_budget_krw": normalized_constraints[
            "option_premium_budget_krw"
        ],
        "allowed_instruments": normalized_constraints[
            "allowed_instruments"
        ],
        "mock_hedge_quotes": quote_template["mock_hedge_quotes"],
        "prototype_notice": (
            "KBaiAgent가 사용자 확인 거래에 적용한 대회용 목업 견적이며 "
            "실제 거래조건이 아니다."
        ),
    }

    with tempfile.TemporaryDirectory(
        prefix="kbai-kbmacro-"
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        forecast_path = temporary_root / "forecast.json"
        company_path = temporary_root / "company_input.json"
        config_path = temporary_root / "model_config.json"
        output_path = temporary_root / "hedge_result.json"
        shutil.copyfile(
            loaded_files["forecast"].path,
            forecast_path,
        )
        runtime_config = dict(model_config)
        runtime_config.update(
            {
                "forecast_path": str(forecast_path),
                "market_history_path": str(
                    loaded_files["market_history"].path
                ),
                "company_input_path": str(company_path),
                "output_path": str(output_path),
            }
        )
        company_path.write_text(
            json.dumps(
                company_input,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        config_path.write_text(
            json.dumps(
                runtime_config,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        company_path.chmod(0o600)
        config_path.chmod(0o600)
        try:
            completed = command_runner(
                [
                    str(cli_python),
                    "-m",
                    "krw_forecast.hedge_recommendation_v1_cli",
                    "--config",
                    str(config_path),
                ],
                cwd=str(temporary_root),
                env={
                    "PATH": os.environ.get(
                        "PATH",
                        "/usr/local/bin:/usr/bin:/bin",
                    ),
                    "PYTHONPATH": str(repo_root / "src"),
                    "PYTHONUNBUFFERED": "1",
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _local_cli_failure(
                check="PINNED_CLI_TIMEOUT",
                detail="kb_macro_ai 계산이 설정된 제한시간을 초과했습니다.",
            )
        except (OSError, subprocess.SubprocessError):
            return _local_cli_failure(
                check="PINNED_CLI_EXECUTION",
                detail="kb_macro_ai 계산을 안전하게 실행하지 못했습니다.",
            )
        stdout = completed.stdout or b""
        stderr = completed.stderr or b""
        if isinstance(stdout, str):
            stdout = stdout.encode("utf-8", errors="replace")
        if isinstance(stderr, str):
            stderr = stderr.encode("utf-8", errors="replace")
        if (
            completed.returncode != 0
            or len(stdout) > maximum_output_bytes
            or len(stderr) > maximum_output_bytes
        ):
            return _local_cli_failure(
                check="PINNED_CLI_EXECUTION",
                detail=(
                    "kb_macro_ai 계산이 실패했거나 안전한 출력 크기를 "
                    "초과했습니다."
                ),
            )
        if not output_path.is_file():
            return _local_cli_failure(
                check="PINNED_CLI_OUTPUT",
                detail="kb_macro_ai 계산 결과 파일이 생성되지 않았습니다.",
            )
        try:
            output_raw = output_path.read_bytes()
        except OSError:
            return _local_cli_failure(
                check="PINNED_CLI_OUTPUT",
                detail="kb_macro_ai 계산 결과 파일을 읽지 못했습니다.",
            )
        if len(output_raw) > maximum_file_bytes:
            return _local_cli_failure(
                check="PINNED_CLI_OUTPUT_SIZE",
                detail="kb_macro_ai 계산 결과가 최대 파일 크기를 초과했습니다.",
            )
        output_sha256 = hashlib.sha256(output_raw).hexdigest()
        runtime_settings = replace(
            settings,
            kb_macro_hedge_mode="file",
            kb_macro_hedge_allowed_root=str(temporary_root),
            kb_macro_forecast_file=forecast_path.name,
            kb_macro_hedge_file=output_path.name,
            kb_macro_expected_forecast_sha256=(
                loaded_files["forecast"].sha256
            ),
            kb_macro_expected_hedge_sha256=output_sha256,
        )
        result = evaluate_kb_macro_hedge_reference(
            settings=runtime_settings,
            stage2_input=stage2_input,
            stage2_result=stage2_result,
            binding_mode="CURRENT_CONFIRMED_TRADE",
            fixture_constraints_confirmed=True,
            constraints_source="USER_CONFIRMED_UI",
        )
        if result is None:
            return _local_cli_failure(
                check="NORMALIZED_RESULT",
                detail="kb_macro_ai 정규화 결과가 생성되지 않았습니다.",
            )
        warnings = list(
            dict.fromkeys(
                result.warnings
                + [
                    "PINNED_LOCAL_CLI_EXECUTION",
                    "TEMPORARY_RAW_OUTPUT_DELETED",
                ]
            )
        )
        validation = result.validation.model_copy(
            update={"warnings": warnings}
        )
        provenance = result.provenance
        if provenance is not None:
            provenance = provenance.model_copy(
                update={
                    "model_config_sha256": loaded_files[
                        "model_config"
                    ].sha256,
                    "market_history_sha256": loaded_files[
                        "market_history"
                    ].sha256,
                    "quote_template_sha256": loaded_files[
                        "quote_template"
                    ].sha256,
                    "execution_method": "PINNED_LOCAL_CLI",
                }
            )
        return result.model_copy(
            update={
                "provider_mode": "local_cli",
                "provenance": provenance,
                "validation": validation,
                "warnings": warnings,
            }
        )
