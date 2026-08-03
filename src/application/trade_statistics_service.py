import hashlib
import json
from datetime import date
from typing import Any, Dict, Optional

from pydantic import ValidationError

from src.config import Settings
from src.domain.confirmed_transaction_models import (
    ConfirmedTransactionSnapshot,
)
from src.domain.trade_statistics_models import (
    TradeStatisticsErrorCode,
    TradeStatisticsRequest,
    TradeStatisticsResult,
)
from src.trade_statistics.analysis import summarize_trade_statistics
from src.trade_statistics.fixture import (
    TRADE_STATISTICS_FIXTURE_VERSION,
    TradeStatisticsFixtureError,
    load_trade_statistics_fixture,
)
from src.trade_statistics.periods import (
    korea_today,
    latest_complete_month,
    shift_month,
)
from src.trade_statistics.provider import (
    CustomsOpenApiProvider,
    TradeStatisticsProviderError,
    Transport,
)


class TradeStatisticsRequestError(ValueError):
    def __init__(
        self,
        code: TradeStatisticsErrorCode,
        user_message: str,
    ) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


def _partner_country(
    transaction: ConfirmedTransactionSnapshot,
) -> str:
    value = (
        transaction.buyer_country
        if transaction.trade_type == "EXPORT"
        else transaction.seller_country
    )
    if not value:
        raise TradeStatisticsRequestError(
            "MISSING_PARTNER_COUNTRY",
            "거래 상대국을 확인해야 무역통계를 조회할 수 있습니다.",
        )
    return value


def trade_statistics_request_fingerprint(
    request: TradeStatisticsRequest,
) -> str:
    canonical = {
        "reporter_country": request.reporter_country,
        "partner_country": request.partner_country,
        "trade_direction": request.trade_direction,
        "hs_code": request.hs_code,
        "hs_level": request.hs_level,
        "period_start": request.period_start,
        "period_end": request.period_end,
        "provider": request.provider,
        "source_preference": request.source_preference,
        "snapshot_version": request.snapshot_version,
        "confirmed_transaction_fingerprint": (
            request.confirmed_transaction_fingerprint
        ),
    }
    serialized = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_trade_statistics_request(
    *,
    confirmed_transaction: ConfirmedTransactionSnapshot,
    source_preference: str,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    hs_code: Optional[str] = None,
    hs_code_confirmed: bool = False,
    snapshot_version: str = TRADE_STATISTICS_FIXTURE_VERSION,
    as_of: Optional[date] = None,
) -> TradeStatisticsRequest:
    if not confirmed_transaction.input_fingerprint:
        raise TradeStatisticsRequestError(
            "VALIDATION_FAILED",
            "확정 거래 fingerprint를 확인할 수 없습니다.",
        )
    normalized_source = source_preference.strip().upper()
    if normalized_source not in {"LIVE", "OFFICIAL_FIXTURE"}:
        raise TradeStatisticsRequestError(
            "VALIDATION_FAILED",
            "지원하지 않는 무역통계 provider 설정입니다.",
        )
    if normalized_source == "OFFICIAL_FIXTURE":
        default_start = "2024-07"
        default_end = "2026-06"
        effective_snapshot_version: Optional[str] = snapshot_version
    else:
        effective_as_of = as_of or korea_today()
        default_end = latest_complete_month(effective_as_of)
        if effective_as_of.day < 15:
            default_end = shift_month(default_end, -1)
        default_start = shift_month(default_end, -23)
        effective_snapshot_version = None
    if hs_code is None and hs_code_confirmed:
        raise TradeStatisticsRequestError(
            "MISSING_HS_CODE",
            "품목별 통계를 사용하려면 HS Code를 확인하세요. 국가 전체 "
            "통계는 계속 확인할 수 있습니다.",
        )
    try:
        return TradeStatisticsRequest(
            reporter_country=confirmed_transaction.company_country,
            partner_country=_partner_country(confirmed_transaction),
            trade_direction=confirmed_transaction.trade_type,
            period_start=period_start or default_start,
            period_end=period_end or default_end,
            hs_code=hs_code,
            hs_level=len(hs_code) if hs_code is not None else None,
            hs_code_confirmed=hs_code_confirmed,
            source_preference=normalized_source,
            snapshot_version=effective_snapshot_version,
            confirmed_transaction_fingerprint=(
                confirmed_transaction.input_fingerprint
            ),
        )
    except ValidationError as exc:
        text = str(exc)
        if "HS Code" in text or "HS level" in text:
            code: TradeStatisticsErrorCode = "INVALID_HS_CODE"
            message = (
                "HS Code는 확인된 숫자 2·4·6·10자리만 사용할 수 "
                "있습니다."
            )
        elif "관측기간" in text or "시작월" in text:
            code = "INVALID_PERIOD"
            message = "무역통계 조회기간을 확인해 주세요."
        elif "국가" in text:
            code = "INVALID_COUNTRY_CODE"
            message = "거래 국가코드는 ISO alpha-2 형식으로 확인해 주세요."
        else:
            code = "VALIDATION_FAILED"
            message = "무역통계 조회 입력을 확인해 주세요."
        raise TradeStatisticsRequestError(code, message) from exc


def _unavailable_status(code: TradeStatisticsErrorCode) -> str:
    if code == "MISSING_API_KEY":
        return "MISSING_API_KEY"
    if code == "NO_DATA":
        return "NO_DATA"
    if code == "FIXTURE_NOT_AVAILABLE":
        return "FIXTURE_NOT_AVAILABLE"
    if code == "UNSUPPORTED_COUNTRY":
        return "UNSUPPORTED_COUNTRY"
    if code == "STALE_DATA":
        return "STALE_DATA"
    if code in {"UPSTREAM_TIMEOUT", "UPSTREAM_ERROR"}:
        return "UPSTREAM_UNAVAILABLE"
    return "VALIDATION_FAILED"


def retrieve_trade_statistics(
    request: TradeStatisticsRequest,
    *,
    settings: Optional[Settings] = None,
    transport: Optional[Transport] = None,
) -> TradeStatisticsResult:
    fingerprint = trade_statistics_request_fingerprint(request)
    effective_settings = settings or Settings.from_env()
    try:
        if request.reporter_country != "KR":
            raise TradeStatisticsProviderError(
                "UNSUPPORTED_COUNTRY",
                "현재 공식 관세청 provider는 한국 기준 거래만 "
                "지원합니다.",
            )
        if request.source_preference == "OFFICIAL_FIXTURE":
            snapshot = load_trade_statistics_fixture(request)
        else:
            provider_kwargs: Dict[str, Any] = {
                "api_key": effective_settings.customs_trade_api_key,
                "timeout_seconds": (
                    effective_settings.trade_statistics_timeout_seconds
                ),
            }
            if transport is not None:
                provider_kwargs["transport"] = transport
            snapshot = CustomsOpenApiProvider(**provider_kwargs).fetch(
                request
            )
        summary = summarize_trade_statistics(request, snapshot)
        user_message = summary.user_summary
        return TradeStatisticsResult(
            status=snapshot.provider_status,
            request=request,
            request_fingerprint=fingerprint,
            snapshot=snapshot,
            summary=summary,
            user_message=user_message,
            warnings=list(snapshot.warnings),
            missing_information=list(summary.missing_information),
        )
    except TradeStatisticsFixtureError as exc:
        code: TradeStatisticsErrorCode = "FIXTURE_NOT_AVAILABLE"
        message = (
            "현재 거래 범위의 검증된 공식 통계 fixture를 사용할 수 "
            "없습니다. 현재 거래 계산에는 영향을 주지 않습니다."
        )
        if "hash" in str(exc) or "검증" in str(exc):
            code = "VALIDATION_FAILED"
            message = (
                "공식 무역통계 fixture 검증에 실패했습니다. 검증되지 "
                "않은 값은 표시하지 않습니다."
            )
        return TradeStatisticsResult(
            status=_unavailable_status(code),
            request=request,
            request_fingerprint=fingerprint,
            error_code=code,
            user_message=message,
            warnings=[message],
            missing_information=[],
        )
    except TradeStatisticsProviderError as exc:
        return TradeStatisticsResult(
            status=_unavailable_status(exc.code),
            request=request,
            request_fingerprint=fingerprint,
            error_code=exc.code,
            user_message=exc.user_message,
            warnings=[exc.user_message],
            missing_information=[],
        )
    except (ValidationError, ValueError) as exc:
        message = (
            "공식 무역통계 검증에 실패했습니다. 검증되지 않은 값은 "
            "표시하지 않습니다."
        )
        return TradeStatisticsResult(
            status="VALIDATION_FAILED",
            request=request,
            request_fingerprint=fingerprint,
            error_code="VALIDATION_FAILED",
            user_message=message,
            warnings=[message],
            missing_information=[],
        )


def trade_statistics_trace(
    result: TradeStatisticsResult,
) -> Dict[str, Any]:
    trace: Dict[str, Any] = {
        "status": result.status,
        "error_code": result.error_code,
        "request_fingerprint": result.request_fingerprint,
        "reporter_country": result.request.reporter_country,
        "partner_country": result.request.partner_country,
        "trade_direction": result.request.trade_direction,
        "scope": result.request.scope,
        "hs_code": result.request.hs_code,
        "period_start": result.request.period_start,
        "period_end": result.request.period_end,
        "provider": result.request.provider,
        "source_preference": result.request.source_preference,
        "snapshot_version": result.request.snapshot_version,
    }
    if result.snapshot is not None:
        trace.update(
            {
                "snapshot_id": result.snapshot.snapshot_id,
                "source_name": result.snapshot.source_name,
                "source_as_of": result.snapshot.source_as_of,
                "raw_sha256": result.snapshot.raw_sha256,
                "normalized_sha256": result.snapshot.normalized_sha256,
            }
        )
    return trace
