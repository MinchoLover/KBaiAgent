#!/usr/bin/env python3
"""Verify the committed official KR-BR trade-statistics fixture."""

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.domain.trade_statistics_models import TradeStatisticsRequest
from src.trade_statistics.analysis import summarize_trade_statistics
from src.trade_statistics.fixture import (
    DEFAULT_FIXTURE_PATH,
    DEFAULT_RAW_PATH,
    TRADE_STATISTICS_FIXTURE_VERSION,
    canonical_snapshot_hash,
    file_sha256,
    load_trade_statistics_fixture,
)
from src.trade_statistics.periods import month_range


def trade_statistics_fixture_summary() -> Dict[str, Any]:
    request = TradeStatisticsRequest(
        reporter_country="KR",
        partner_country="BR",
        trade_direction="EXPORT",
        period_start="2024-07",
        period_end="2026-06",
        source_preference="OFFICIAL_FIXTURE",
        snapshot_version=TRADE_STATISTICS_FIXTURE_VERSION,
        confirmed_transaction_fingerprint="0" * 64,
    )
    snapshot = load_trade_statistics_fixture(request)
    summary = summarize_trade_statistics(request, snapshot)
    expected_periods = month_range(
        snapshot.observation_start,
        snapshot.observation_end,
    )
    actual_periods = [item.period for item in snapshot.observations]
    if actual_periods != expected_periods:
        raise ValueError("fixture 관측월이 연속 24개월과 일치하지 않습니다.")
    raw_payload = json.loads(DEFAULT_RAW_PATH.read_text(encoding="utf-8"))
    total_record = raw_payload.get("total_record")
    if not isinstance(total_record, dict):
        raise ValueError("공식 raw asset의 TOTAL record가 없습니다.")
    monthly_export = sum(
        (
            Decimal(item.export_value_usd)
            for item in snapshot.observations
        ),
        Decimal("0"),
    )
    monthly_import = sum(
        (
            Decimal(item.import_value_usd)
            for item in snapshot.observations
        ),
        Decimal("0"),
    )
    monthly_balance = sum(
        (
            Decimal(item.trade_balance_usd)
            for item in snapshot.observations
        ),
        Decimal("0"),
    )
    return {
        "verified": True,
        "source": snapshot.source_name,
        "provider_status": snapshot.provider_status,
        "scope": summary.scope,
        "snapshot_version": snapshot.snapshot_version,
        "observation_period": "{}~{}".format(
            snapshot.observation_start,
            snapshot.observation_end,
        ),
        "source_as_of": snapshot.source_as_of,
        "month_count": len(snapshot.observations),
        "raw_asset": str(DEFAULT_RAW_PATH.relative_to(ROOT)),
        "normalized_asset": str(
            DEFAULT_FIXTURE_PATH.relative_to(ROOT)
        ),
        "raw_sha256": file_sha256(DEFAULT_RAW_PATH),
        "normalized_sha256": canonical_snapshot_hash(snapshot),
        "all_24m_export_usd": format(monthly_export, "f"),
        "all_24m_import_usd": format(monthly_import, "f"),
        "all_24m_balance_usd": format(monthly_balance, "f"),
        "latest_12m_export_usd": summary.latest_12m_export_usd,
        "latest_12m_import_usd": summary.latest_12m_import_usd,
        "latest_12m_balance_usd": summary.latest_12m_balance_usd,
        "export_yoy_pct": summary.export_yoy_pct,
        "import_yoy_pct": summary.import_yoy_pct,
        "official_total_thousand_usd": {
            "export": total_record.get("expUsdAmt"),
            "import": total_record.get("impUsdAmt"),
            "balance": total_record.get("cmtrBlncAmt"),
        },
    }


def main() -> int:
    try:
        result = trade_statistics_fixture_summary()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "verified": False,
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
