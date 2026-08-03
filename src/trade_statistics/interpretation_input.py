import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

from src.config import Settings
from src.domain.trade_statistics_interpretation_models import (
    TradeBalanceDirection,
    TradeExportChangeDirection,
    TradeStatisticsInterpretationInput,
)
from src.domain.trade_statistics_models import TradeStatisticsResult
from src.trade_statistics.periods import shift_month


TRADE_STATISTICS_INTERPRETATION_SCHEMA_VERSION = "1.0"
TRADE_STATISTICS_INTERPRETATION_PROMPT_VERSION = "trade-statistics-ko-1.0"
ZERO_HASH = "0" * 64
COUNTRY_NAMES = {
    "BR": "브라질",
    "US": "미국",
}


def _fingerprint(payload: Dict[str, object]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def trade_statistics_interpretation_model_fingerprint(
    settings: Settings,
) -> str:
    return _fingerprint(
        {
            "model": settings.openai_model,
            "timeout_seconds": str(settings.openai_timeout_seconds),
            "feature_enabled": (
                settings.enable_trade_statistics_interpretation
            ),
            "schema_version": (
                TRADE_STATISTICS_INTERPRETATION_SCHEMA_VERSION
            ),
            "prompt_version": (
                TRADE_STATISTICS_INTERPRETATION_PROMPT_VERSION
            ),
        }
    )


def trade_statistics_result_fingerprint(
    result: TradeStatisticsResult,
) -> str:
    return _fingerprint(
        {
            "request_fingerprint": result.request_fingerprint,
            "status": result.status,
            "error_code": result.error_code,
            "snapshot_version": (
                result.snapshot.snapshot_version
                if result.snapshot is not None
                else None
            ),
            "normalized_sha256": (
                result.snapshot.normalized_sha256
                if result.snapshot is not None
                else None
            ),
            "summary": (
                result.summary.model_dump()
                if result.summary is not None
                else None
            ),
        }
    )


def _decimal_direction(
    value: Optional[str],
    *,
    positive: str,
    negative: str,
    zero: str,
    unavailable: str,
) -> str:
    if value is None:
        return unavailable
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return unavailable
    if parsed > 0:
        return positive
    if parsed < 0:
        return negative
    return zero


def _export_direction(
    result: TradeStatisticsResult,
) -> TradeExportChangeDirection:
    summary = result.summary
    if (
        summary is None
        or summary.export_comparison_status != "AVAILABLE"
    ):
        return "UNAVAILABLE"
    return _decimal_direction(
        summary.export_yoy_pct,
        positive="INCREASED",
        negative="DECREASED",
        zero="UNCHANGED",
        unavailable="UNAVAILABLE",
    )


def _balance_direction(
    result: TradeStatisticsResult,
) -> TradeBalanceDirection:
    value = (
        result.summary.latest_12m_balance_usd
        if result.summary is not None
        else None
    )
    return _decimal_direction(
        value,
        positive="SURPLUS",
        negative="DEFICIT",
        zero="BALANCED",
        unavailable="UNAVAILABLE",
    )


def build_trade_statistics_interpretation_input(
    *,
    result: TradeStatisticsResult,
    settings: Settings,
) -> TradeStatisticsInterpretationInput:
    if result.request.scope != "COUNTRY_TOTAL":
        raise ValueError(
            "국가 전체 무역통계 결과만 기본 해석에 연결할 수 있습니다."
        )
    summary = result.summary
    snapshot = result.snapshot
    if summary is not None:
        latest_end = summary.latest_period
        latest_start = shift_month(latest_end, -11)
        comparison_end = shift_month(latest_start, -1)
        comparison_start = shift_month(comparison_end, -11)
        observation_period = "{}~{}".format(latest_start, latest_end)
        comparison_period: Optional[str] = "{}~{}".format(
            comparison_start,
            comparison_end,
        )
    else:
        observation_period = "{}~{}".format(
            result.request.period_start,
            result.request.period_end,
        )
        comparison_period = None
    source_reference = (
        summary.source_refs[0]
        if summary is not None and summary.source_refs
        else None
    )
    result_fingerprint = trade_statistics_result_fingerprint(result)
    normalized_fingerprint = (
        snapshot.normalized_sha256 if snapshot is not None else ZERO_HASH
    )
    model_fingerprint = trade_statistics_interpretation_model_fingerprint(
        settings
    )
    canonical: Dict[str, object] = {
        "schema_version": TRADE_STATISTICS_INTERPRETATION_SCHEMA_VERSION,
        "prompt_version": TRADE_STATISTICS_INTERPRETATION_PROMPT_VERSION,
        "reporting_country_code": result.request.reporter_country,
        "partner_country_code": result.request.partner_country,
        "partner_country_name": COUNTRY_NAMES.get(
            result.request.partner_country,
            result.request.partner_country,
        ),
        "trade_direction": result.request.trade_direction,
        "observation_period": observation_period,
        "comparison_period": comparison_period,
        "latest_12m_export_value": (
            summary.latest_12m_export_usd if summary is not None else None
        ),
        "latest_12m_import_value": (
            summary.latest_12m_import_usd if summary is not None else None
        ),
        "latest_12m_trade_balance": (
            summary.latest_12m_balance_usd if summary is not None else None
        ),
        "previous_12m_export_value": (
            summary.previous_12m_export_usd if summary is not None else None
        ),
        "export_change_rate": (
            summary.export_yoy_pct if summary is not None else None
        ),
        "export_change_direction": _export_direction(result),
        "trade_balance_direction": _balance_direction(result),
        "data_source_type": result.status,
        "source_reference": (
            source_reference.model_dump()
            if source_reference is not None
            else None
        ),
        "snapshot_version": (
            snapshot.snapshot_version if snapshot is not None else None
        ),
        "source_as_of": (
            snapshot.source_as_of if snapshot is not None else None
        ),
        "trade_statistics_result_fingerprint": result_fingerprint,
        "normalized_snapshot_fingerprint": normalized_fingerprint,
        "confirmed_transaction_fingerprint": (
            result.request.confirmed_transaction_fingerprint
        ),
        "model_configuration_fingerprint": model_fingerprint,
    }
    return TradeStatisticsInterpretationInput(
        **canonical,
        input_fingerprint=_fingerprint(canonical),
    )
