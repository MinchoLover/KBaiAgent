import hashlib
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple
from urllib.parse import urlsplit

from src.application.kb_macro_hedge_service import (
    SUPPORTED_PROVIDER_COMMIT_SHA,
    inspect_kb_macro_exposure_support,
    run_kb_macro_hedge_for_confirmed_trade,
)
from src.application.market_integration_service import (
    build_stage1_forecast_service,
)
from src.config import Settings
from src.domain.integration_readiness_models import (
    IntegrationReadinessCheck,
    IntegrationReadinessReport,
    KbMacroAssetReadiness,
    KbMacroExposureReadiness,
    KbMacroIntegrationReadiness,
    KbMacroLocalCliE2EReadiness,
    SpotIntegrationReadiness,
    Stage1IntegrationReadiness,
)
from src.domain.kb_macro_hedge_models import (
    KbMacroHedgeExecutionConstraints,
)
from src.domain.stage1_models import ScenarioPoint, Stage1ScenarioSet
from src.domain.stage1_web_models import MarketIntegrationResult
from src.domain.stage2_models import ExposureInput, Stage2Input, Stage2Result
from src.stage1.forecast_provider import Stage1ForecastService
from src.stage1.normalizer import normalize_stage1_scenarios
from src.stage2.engine import run_stage2


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{40}$")
SUPPORTED_KB_MACRO_MODES = {"off", "fixture", "file", "local_cli"}


def _checked_at(now: Optional[datetime]) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.isoformat()


def _stage1_endpoint_kind(settings: Settings) -> str:
    provider = settings.stage1_provider.strip().lower()
    if provider == "file":
        return "LOCAL_FILE"
    if provider == "mock":
        return "BUILT_IN_FIXTURE"
    if provider != "http":
        return "INVALID_PROVIDER"
    parsed = urlsplit(settings.stage1_base_url)
    if parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return "LOCAL_HTTP"
    return "REMOTE_HTTPS" if parsed.scheme == "https" else "REMOTE_HTTP"


def _stage1_readiness(
    *,
    settings: Settings,
    active_check: bool,
    now: Optional[datetime],
    forecast_service: Optional[Stage1ForecastService],
) -> Stage1IntegrationReadiness:
    provider = settings.stage1_provider.strip().lower()
    endpoint_kind = _stage1_endpoint_kind(settings)
    if not active_check:
        return Stage1IntegrationReadiness(
            status="NOT_CHECKED",
            configured_provider=provider,
            endpoint_kind=endpoint_kind,
            checks=[
                IntegrationReadinessCheck(
                    check="STAGE1_ACTIVE_CHECK",
                    status="NOT_CHECKED",
                    summary="Stage 1 health와 forecast를 아직 읽지 않았습니다.",
                    action="연동 상태 점검을 실행하세요.",
                )
            ],
        )
    try:
        service = forecast_service or build_stage1_forecast_service(
            settings
        )
        loaded = service.load(provider, now=now)
    except Exception as exc:
        error_code = getattr(exc, "code", type(exc).__name__)
        return Stage1IntegrationReadiness(
            status="BLOCKED",
            configured_provider=provider,
            endpoint_kind=endpoint_kind,
            error_code=str(error_code),
            warnings=[
                "Stage 1 provider와 표시된 fallback을 사용할 수 없습니다."
            ],
            checks=[
                IntegrationReadinessCheck(
                    check="STAGE1_FORECAST_LOAD",
                    status="BLOCKED",
                    summary="Stage 1 forecast를 검증해 읽지 못했습니다.",
                    action="provider health, 파일 경로와 fallback을 확인하세요.",
                )
            ],
        )

    forecast = loaded.forecast
    health = loaded.provider_health
    degraded = bool(
        loaded.fallback_used
        or health.status != "OK"
        or forecast.quality.stale_market_data
        or forecast.quality.partial_fallback_used
        or forecast.quality.research_only
    )
    status = "DEGRADED" if degraded else "READY"
    checks = [
        IntegrationReadinessCheck(
            check="STAGE1_PROVIDER_HEALTH",
            status=("READY" if health.status == "OK" else "DEGRADED"),
            summary=(
                "configured provider health={}".format(health.status)
            ),
            action=(
                None
                if health.status == "OK"
                else "configured provider를 복구하고 fallback 표시를 확인하세요."
            ),
        ),
        IntegrationReadinessCheck(
            check="STAGE1_FORECAST_FRESHNESS",
            status=(
                "DEGRADED"
                if forecast.quality.stale_market_data
                else "READY"
            ),
            summary=(
                "시장 데이터가 stale 상태입니다."
                if forecast.quality.stale_market_data
                else "설정된 freshness 검증을 통과했습니다."
            ),
        ),
        IntegrationReadinessCheck(
            check="STAGE1_FALLBACK_DISCLOSURE",
            status=("DEGRADED" if loaded.fallback_used else "READY"),
            summary=(
                "표시된 {} source를 사용했습니다.".format(loaded.source)
            ),
        ),
        IntegrationReadinessCheck(
            check="STAGE1_RESEARCH_SCOPE",
            status=(
                "DEGRADED"
                if forecast.quality.research_only
                else "READY"
            ),
            summary=(
                "연구·대회용 forecast이며 운영 확정값이 아닙니다."
                if forecast.quality.research_only
                else "운영 범위 표기가 research-only가 아닙니다."
            ),
        ),
    ]
    return Stage1IntegrationReadiness(
        status=status,
        configured_provider=provider,
        endpoint_kind=endpoint_kind,
        active_source=loaded.source,
        health_status=health.status,
        reachable=health.reachable,
        forecast_available=health.forecast_available,
        fallback_used=loaded.fallback_used,
        schema_version=forecast.schema_version,
        raw_schema_version=forecast.source.raw_schema_version,
        prediction_date=forecast.source.prediction_date,
        generated_at=forecast.source.generated_at,
        market_data_latest_date=(
            forecast.quality.market_data_latest_date
        ),
        forecast_fresh=not forecast.quality.stale_market_data,
        partial_fallback_used=(
            forecast.quality.partial_fallback_used
        ),
        research_only=forecast.quality.research_only,
        error_code=health.error_code,
        warnings=list(
            dict.fromkeys(loaded.warnings + health.warnings)
        ),
        checks=checks,
    )


def _spot_readiness(
    *,
    settings: Settings,
    market_integration: Optional[MarketIntegrationResult],
) -> SpotIntegrationReadiness:
    provider = settings.spot_rate_provider.strip().lower()
    credential_configured = bool(settings.koreaexim_key)
    manual_configured = bool(
        settings.manual_usdkrw_rate
        and settings.manual_usdkrw_rate.strip()
    )
    if market_integration is not None:
        quote = market_integration.spot_quote
        fixture = quote.rate_type == "TEST_FIXTURE"
        return SpotIntegrationReadiness(
            status="DEGRADED" if fixture else "READY",
            configured_provider=provider,
            configured_source=provider.upper(),
            active_source=quote.source,
            credential_configured=credential_configured,
            manual_rate_configured=manual_configured,
            requires_transaction_confirmation=(
                quote.rate_type == "USER_CONFIRMED_MANUAL"
                and not quote.user_confirmed
            ),
            external_call_performed=False,
            warnings=(
                ["현재 활성 환율은 테스트 fixture이며 실시간 환율이 아닙니다."]
                if fixture
                else []
            ),
        )
    if provider == "koreaexim":
        return SpotIntegrationReadiness(
            status="READY" if credential_configured else "BLOCKED",
            configured_provider=provider,
            configured_source="KOREAEXIM_DEAL_BASE_RATE",
            credential_configured=credential_configured,
            manual_rate_configured=manual_configured,
            external_call_performed=False,
            warnings=(
                []
                if credential_configured
                else ["한국수출입은행 API 자격증명이 설정되지 않았습니다."]
            ),
        )
    if provider == "manual":
        return SpotIntegrationReadiness(
            status="DEGRADED",
            configured_provider=provider,
            configured_source="USER_CONFIRMED_MANUAL",
            credential_configured=credential_configured,
            manual_rate_configured=manual_configured,
            requires_transaction_confirmation=True,
            external_call_performed=False,
            warnings=[
                (
                    "수동 환율은 거래마다 사용자 확인이 필요합니다."
                    if manual_configured
                    else "수동 환율을 거래 화면에서 입력하고 확인해야 합니다."
                )
            ],
        )
    if provider == "fixture":
        return SpotIntegrationReadiness(
            status="DEGRADED" if settings.demo_mode else "BLOCKED",
            configured_provider=provider,
            configured_source="TEST_FIXTURE_NOT_LIVE_RATE",
            credential_configured=credential_configured,
            manual_rate_configured=manual_configured,
            external_call_performed=False,
            warnings=["fixture 환율은 발표·테스트 전용입니다."],
        )
    if provider == "auto":
        if credential_configured:
            status = "READY"
            source = "KOREAEXIM_WITH_DISCLOSED_FALLBACK"
            warnings: List[str] = []
        elif manual_configured:
            status = "DEGRADED"
            source = "USER_CONFIRMED_MANUAL"
            warnings = ["수동 환율의 거래별 사용자 확인이 필요합니다."]
        elif settings.demo_mode:
            status = "DEGRADED"
            source = "TEST_FIXTURE_NOT_LIVE_RATE"
            warnings = ["공식·수동 환율이 없어 demo fixture 후보만 있습니다."]
        else:
            status = "BLOCKED"
            source = "UNAVAILABLE"
            warnings = ["사용 가능한 환율 출처가 설정되지 않았습니다."]
        return SpotIntegrationReadiness(
            status=status,
            configured_provider=provider,
            configured_source=source,
            credential_configured=credential_configured,
            manual_rate_configured=manual_configured,
            requires_transaction_confirmation=manual_configured,
            external_call_performed=False,
            warnings=warnings,
        )
    return SpotIntegrationReadiness(
        status="BLOCKED",
        configured_provider=provider,
        configured_source="INVALID_PROVIDER",
        credential_configured=credential_configured,
        manual_rate_configured=manual_configured,
        external_call_performed=False,
        warnings=["지원하지 않는 SPOT_RATE_PROVIDER입니다."],
    )


def _safe_asset_path(
    *,
    root: Path,
    path_text: str,
) -> Optional[Path]:
    if not path_text:
        return None
    configured = Path(path_text).expanduser()
    candidate = (
        configured.resolve()
        if configured.is_absolute()
        else (root / configured).resolve()
    )
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _file_sha256(path: Path, maximum_bytes: int) -> Optional[str]:
    try:
        if (
            not path.is_file()
            or maximum_bytes <= 0
            or path.stat().st_size > maximum_bytes
        ):
            return None
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _asset_readiness(
    *,
    root: Optional[Path],
    asset: str,
    path_text: str,
    expected_sha256: str,
    maximum_bytes: int,
) -> KbMacroAssetReadiness:
    expected = (
        expected_sha256
        if SHA256_PATTERN.fullmatch(expected_sha256)
        else None
    )
    path = (
        _safe_asset_path(root=root, path_text=path_text)
        if root is not None
        else None
    )
    actual = (
        _file_sha256(path, maximum_bytes)
        if path is not None
        else None
    )
    return KbMacroAssetReadiness(
        asset=asset,
        configured=bool(path_text and expected is not None),
        available=actual is not None,
        expected_sha256=expected,
        actual_sha256=actual,
        sha256_matches=(
            actual == expected
            if actual is not None and expected is not None
            else None
        ),
    )


def _git_checkout_status(
    *,
    root: Path,
    command_runner: Any,
    timeout_seconds: float,
) -> Tuple[Optional[str], Optional[bool], Optional[str]]:
    commands = (
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain",
            "--untracked-files=no",
        ],
    )
    outputs: List[str] = []
    try:
        for command in commands:
            completed = command_runner(
                command,
                cwd=str(root),
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
            if completed.returncode != 0:
                return None, None, "GIT_COMMAND_FAILED"
            stdout = completed.stdout or b""
            if isinstance(stdout, bytes):
                output = stdout.decode(
                    "utf-8",
                    errors="replace",
                ).strip()
            else:
                output = str(stdout).strip()
            outputs.append(output)
    except (OSError, subprocess.SubprocessError):
        return None, None, "GIT_COMMAND_FAILED"
    commit = outputs[0] if COMMIT_PATTERN.fullmatch(outputs[0]) else None
    return commit, outputs[1] == "", None


def _exposure_readiness(
    stage2_input: Optional[Stage2Input],
) -> KbMacroExposureReadiness:
    if stage2_input is None:
        return KbMacroExposureReadiness(
            status="NOT_CHECKED",
            supported=None,
            failed_checks=["CURRENT_STAGE2_INPUT"],
            detail="확정 Stage 2 거래가 생기면 지원 여부를 점검합니다.",
        )
    validation = inspect_kb_macro_exposure_support(stage2_input)
    failed = list(validation.failed_checks)
    detail = (
        "단일 USD 수입 지급 지원 범위입니다."
        if validation.passed
        else next(
            (
                item.detail
                for item in validation.checks
                if not item.passed
            ),
            "현재 거래는 외부 헤지 v1 지원 범위가 아닙니다.",
        )
    )
    return KbMacroExposureReadiness(
        status="READY" if validation.passed else "DEGRADED",
        supported=validation.passed,
        failed_checks=failed,
        detail=detail,
    )


def build_single_usd_import_readiness_fixture(
) -> Tuple[Stage2Input, Stage2Result]:
    source_sha256 = hashlib.sha256(
        b"kbaiagent-integration-readiness-single-usd-import-v1"
    ).hexdigest()
    stage2_input = Stage2Input(
        confirmed_trade_sha256=source_sha256,
        as_of_date="2026-07-29",
        exposures=[
            ExposureInput(
                sequence=1,
                trade_type="IMPORT",
                currency="USD",
                foreign_amount="100000",
                settlement_date="2026-08-27",
                usable_fx_balance="10000",
                same_currency_flows=[],
            )
        ],
        current_krw_cash="200000000",
        minimum_cash_buffer="50000000",
        credit_limit="0",
        acceptable_fx_loss="10000000",
        krw_cashflows=[],
        bank_spread_bps="0",
        bank_fee="0",
    )
    scenarios = normalize_stage1_scenarios(
        Stage1ScenarioSet(
            currency="USD",
            rate_unit_foreign_currency="1",
            as_of="2026-07-29T09:00:00+09:00",
            target_date="2026-08-27",
            kind="STRESS",
            scenarios=[
                ScenarioPoint(
                    name="BASE",
                    rate="1400",
                    is_base=True,
                ),
                ScenarioPoint(
                    name="STRESS_+10PCT",
                    rate="1540",
                    is_base=False,
                ),
            ],
        )
    )
    return stage2_input, run_stage2(stage2_input, scenarios)


def _local_cli_e2e(
    *,
    settings: Settings,
    command_runner: Any,
) -> KbMacroLocalCliE2EReadiness:
    if (
        not settings.enable_kb_macro_hedge_reference
        or settings.kb_macro_hedge_mode != "local_cli"
    ):
        return KbMacroLocalCliE2EReadiness(
            status="BLOCKED",
            executed=False,
            failed_checks=["LOCAL_CLI_NOT_ENABLED"],
            warnings=[
                "feature flag와 local_cli mode를 명시해야 E2E를 실행합니다."
            ],
        )
    stage2_input, stage2_result = (
        build_single_usd_import_readiness_fixture()
    )
    constraints = KbMacroHedgeExecutionConstraints(
        payment_certainty="1.0",
        maximum_acceptable_cost_krw="135000000",
        maximum_budget_exceedance_probability="0.15",
        risk_tolerance="medium",
        maximum_total_hedge_ratio="1.0",
        option_premium_budget_krw="1500000",
        allowed_instruments=["forward", "vanilla_usd_call"],
    )
    result = run_kb_macro_hedge_for_confirmed_trade(
        settings=settings,
        stage2_input=stage2_input,
        stage2_result=stage2_result,
        constraints=constraints,
        constraints_confirmed=True,
        command_runner=command_runner,
    )
    if result is None:
        return KbMacroLocalCliE2EReadiness(
            status="BLOCKED",
            executed=False,
            failed_checks=["NO_REFERENCE_RESULT"],
        )
    passed = bool(
        result.status in {"READY", "REFERENCE_ONLY"}
        and result.validation.passed
        and len(result.candidates) == 3
        and [item.rank for item in result.candidates] == [1, 2, 3]
    )
    provenance = result.provenance
    return KbMacroLocalCliE2EReadiness(
        status="READY" if passed else "BLOCKED",
        executed=True,
        provider_mode=result.provider_mode,
        result_status=result.status,
        pricing_status=result.pricing_status,
        validation_passed=result.validation.passed,
        candidate_count=len(result.candidates),
        candidate_ranks=[item.rank for item in result.candidates],
        producer_commit_sha=(
            provenance.producer_commit_sha
            if provenance is not None
            else None
        ),
        forecast_sha256=(
            provenance.forecast_sha256
            if provenance is not None
            else None
        ),
        temporary_raw_output_deleted=(
            "TEMPORARY_RAW_OUTPUT_DELETED" in result.warnings
        ),
        failed_checks=list(result.validation.failed_checks),
        warnings=list(result.warnings),
    )


def _kb_macro_readiness(
    *,
    settings: Settings,
    stage2_input: Optional[Stage2Input],
    run_local_cli_e2e: bool,
    command_runner: Any,
) -> KbMacroIntegrationReadiness:
    enabled = settings.enable_kb_macro_hedge_reference
    mode = settings.kb_macro_hedge_mode.strip().lower()
    root_text = settings.kb_macro_hedge_allowed_root
    root = (
        Path(root_text).expanduser().resolve()
        if root_text
        else None
    )
    root_available = bool(root is not None and root.is_dir())
    expected_commit = (
        settings.kb_macro_expected_provider_commit_sha
        if COMMIT_PATTERN.fullmatch(
            settings.kb_macro_expected_provider_commit_sha
        )
        else None
    )
    actual_commit: Optional[str] = None
    tracked_clean: Optional[bool] = None
    git_error: Optional[str] = None
    cli_available: Optional[bool] = None
    if mode == "local_cli" and root is not None and root_available:
        actual_commit, tracked_clean, git_error = _git_checkout_status(
            root=root,
            command_runner=command_runner,
            timeout_seconds=settings.kb_macro_cli_timeout_seconds,
        )
        cli_available = bool(
            (root / ".venv" / "bin" / "python").is_file()
            and os.access(
                str(root / ".venv" / "bin" / "python"),
                os.X_OK,
            )
            and (
                root
                / "src"
                / "krw_forecast"
                / "hedge_recommendation_v1_cli.py"
            ).is_file()
        )
    asset_specs: List[Tuple[str, str, str]]
    if mode == "local_cli":
        asset_specs = [
            (
                "forecast",
                settings.kb_macro_forecast_file,
                settings.kb_macro_expected_forecast_sha256,
            ),
            (
                "model_config",
                settings.kb_macro_model_config_file,
                settings.kb_macro_expected_model_config_sha256,
            ),
            (
                "market_history",
                settings.kb_macro_market_history_file,
                settings.kb_macro_expected_market_history_sha256,
            ),
            (
                "quote_template",
                settings.kb_macro_quote_template_file,
                settings.kb_macro_expected_quote_template_sha256,
            ),
        ]
    elif mode in {"fixture", "file"}:
        asset_specs = [
            (
                "forecast",
                settings.kb_macro_forecast_file,
                settings.kb_macro_expected_forecast_sha256,
            ),
            (
                "hedge_response",
                settings.kb_macro_hedge_file,
                settings.kb_macro_expected_hedge_sha256,
            ),
        ]
    else:
        asset_specs = []
    assets = [
        _asset_readiness(
            root=root if root_available else None,
            asset=name,
            path_text=path_text,
            expected_sha256=expected_sha,
            maximum_bytes=settings.kb_macro_max_file_bytes,
        )
        for name, path_text, expected_sha in asset_specs
    ]
    commit_matches = (
        actual_commit == expected_commit
        if actual_commit is not None and expected_commit is not None
        else None
    )
    expected_commit_supported = (
        expected_commit == SUPPORTED_PROVIDER_COMMIT_SHA
    )
    integrity_ready = bool(
        root_available
        and expected_commit_supported
        and all(
            item.available and item.sha256_matches is True
            for item in assets
        )
    )
    if mode == "local_cli":
        integrity_ready = bool(
            integrity_ready
            and commit_matches is True
            and tracked_clean is True
            and cli_available is True
            and git_error is None
        )
    exposure = _exposure_readiness(stage2_input)
    e2e = (
        _local_cli_e2e(
            settings=settings,
            command_runner=command_runner,
        )
        if run_local_cli_e2e
        else None
    )
    checks: List[IntegrationReadinessCheck] = []
    if mode not in SUPPORTED_KB_MACRO_MODES:
        checks.append(
            IntegrationReadinessCheck(
                check="KB_MACRO_MODE",
                status="BLOCKED",
                summary="지원하지 않는 provider mode입니다.",
            )
        )
    else:
        checks.append(
            IntegrationReadinessCheck(
                check="KB_MACRO_FEATURE_FLAG",
                status="READY" if enabled else "DISABLED",
                summary=(
                    "외부 참고 기능이 켜져 있습니다."
                    if enabled
                    else "기본 안전값 off입니다."
                ),
            )
        )
    if mode != "off":
        checks.extend(
            [
                IntegrationReadinessCheck(
                    check="KB_MACRO_PROVIDER_ROOT",
                    status="READY" if root_available else "BLOCKED",
                    summary=(
                        "허용 provider 디렉터리를 확인했습니다."
                        if root_available
                        else "허용 provider 디렉터리를 확인할 수 없습니다."
                    ),
                ),
                IntegrationReadinessCheck(
                    check="KB_MACRO_PRODUCER_COMMIT",
                    status=(
                        "READY"
                        if expected_commit_supported
                        and (
                            mode != "local_cli"
                            or commit_matches is True
                        )
                        else "BLOCKED"
                    ),
                    summary="producer commit pin을 대조했습니다.",
                ),
                IntegrationReadinessCheck(
                    check="KB_MACRO_ASSET_SHA256",
                    status=(
                        "READY"
                        if assets
                        and all(
                            item.sha256_matches is True
                            for item in assets
                        )
                        else "BLOCKED"
                    ),
                    summary="고정 입력 자산 SHA-256을 대조했습니다.",
                ),
            ]
        )
    if not enabled:
        status = "DISABLED"
    elif mode == "off" or mode not in SUPPORTED_KB_MACRO_MODES:
        status = "BLOCKED"
    elif not integrity_ready:
        status = "BLOCKED"
    elif e2e is not None and e2e.status == "BLOCKED":
        status = "BLOCKED"
    elif exposure.status == "DEGRADED":
        status = "DEGRADED"
    else:
        status = "READY"
    warnings: List[str] = []
    if not enabled:
        warnings.append(
            "feature flag off에서는 기존 Stage 3만 사용합니다."
        )
    if mode in {"fixture", "file", "local_cli"}:
        warnings.append(
            "외부 결과는 단일 USD 수입 지급 참고 전용이며 Stage 3를 대체하지 않습니다."
        )
    if git_error is not None:
        warnings.append("producer Git 상태를 안전하게 확인하지 못했습니다.")
    if expected_commit is None and mode != "off":
        warnings.append("유효한 producer commit SHA가 설정되지 않았습니다.")
    return KbMacroIntegrationReadiness(
        status=status,
        feature_enabled=enabled,
        configured_mode=mode,
        provider_root_configured=bool(root_text),
        provider_root_available=root_available,
        expected_producer_commit_sha=expected_commit,
        actual_producer_commit_sha=actual_commit,
        producer_commit_matches=commit_matches,
        tracked_worktree_clean=tracked_clean,
        cli_available=cli_available,
        assets=assets,
        exposure=exposure,
        local_cli_e2e=e2e,
        warnings=warnings,
        checks=checks,
    )


def _overall_status(
    *,
    stage1: Stage1IntegrationReadiness,
    spot: SpotIntegrationReadiness,
    kb_macro: KbMacroIntegrationReadiness,
) -> str:
    statuses = (stage1.status, spot.status, kb_macro.status)
    if "BLOCKED" in statuses:
        return "BLOCKED"
    if kb_macro.status == "DISABLED":
        return "DISABLED"
    if "DEGRADED" in statuses or "NOT_CHECKED" in statuses:
        return "DEGRADED"
    return "READY"


def build_integration_readiness_report(
    *,
    settings: Settings,
    stage2_input: Optional[Stage2Input] = None,
    market_integration: Optional[MarketIntegrationResult] = None,
    active_stage1_check: bool = True,
    run_local_cli_e2e: bool = False,
    now: Optional[datetime] = None,
    forecast_service: Optional[Stage1ForecastService] = None,
    command_runner: Any = subprocess.run,
) -> IntegrationReadinessReport:
    """Build a sanitized operational view without changing financial state."""

    stage1 = _stage1_readiness(
        settings=settings,
        active_check=active_stage1_check,
        now=now,
        forecast_service=forecast_service,
    )
    spot = _spot_readiness(
        settings=settings,
        market_integration=market_integration,
    )
    kb_macro = _kb_macro_readiness(
        settings=settings,
        stage2_input=stage2_input,
        run_local_cli_e2e=run_local_cli_e2e,
        command_runner=command_runner,
    )
    status = _overall_status(
        stage1=stage1,
        spot=spot,
        kb_macro=kb_macro,
    )
    return IntegrationReadinessReport(
        status=status,
        checked_at=_checked_at(now),
        stage1=stage1,
        spot=spot,
        kb_macro_hedge=kb_macro,
        checks=[
            IntegrationReadinessCheck(
                check="NO_SECRET_VALUE_EXPOSURE",
                status="READY",
                summary=(
                    "자격증명은 설정 여부만 표시하고 값은 report에 포함하지 않습니다."
                ),
            ),
            IntegrationReadinessCheck(
                check="FINANCIAL_CALCULATION_BOUNDARY",
                status="READY",
                summary=(
                    "점검 결과는 Stage 1~5 계산과 외부 헤지 안전 gate를 변경하지 않습니다."
                ),
            ),
        ],
    )
