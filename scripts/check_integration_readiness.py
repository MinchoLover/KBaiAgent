#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import List

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.integration_readiness_service import (
    build_integration_readiness_report,
)
from src.config import Settings
from src.domain.integration_readiness_models import (
    IntegrationReadinessReport,
)


def _yes_no(value: object) -> str:
    if value is None:
        return "UNKNOWN"
    return "YES" if bool(value) else "NO"


def _human_lines(report: IntegrationReadinessReport) -> List[str]:
    stage1 = report.stage1
    spot = report.spot
    macro = report.kb_macro_hedge
    lines = [
        "KBaiAgent Integration Readiness: {}".format(report.status),
        "checked_at: {}".format(report.checked_at),
        "",
        "[Stage 1]",
        "status: {}".format(stage1.status),
        "configured_provider: {}".format(stage1.configured_provider),
        "endpoint_kind: {}".format(stage1.endpoint_kind),
        "health: {}".format(stage1.health_status or "UNKNOWN"),
        "active_source: {}".format(stage1.active_source or "UNKNOWN"),
        "forecast_fresh: {}".format(
            _yes_no(stage1.forecast_fresh)
        ),
        "fallback_used: {}".format(
            _yes_no(stage1.fallback_used)
        ),
        "upstream_partial_fallback_used: {}".format(
            _yes_no(stage1.partial_fallback_used)
        ),
        "research_only: {}".format(
            _yes_no(stage1.research_only)
        ),
        "prediction_date: {}".format(
            stage1.prediction_date or "UNKNOWN"
        ),
        "market_data_latest_date: {}".format(
            stage1.market_data_latest_date or "UNKNOWN"
        ),
        "",
        "[Spot]",
        "status: {}".format(spot.status),
        "configured_provider: {}".format(spot.configured_provider),
        "configured_source: {}".format(spot.configured_source),
        "active_source: {}".format(spot.active_source or "NOT_OBSERVED"),
        "credential_configured: {}".format(
            _yes_no(spot.credential_configured)
        ),
        "external_call_performed_by_check: NO",
        "",
        "[kb_macro_ai hedge reference]",
        "status: {}".format(macro.status),
        "feature_enabled: {}".format(
            _yes_no(macro.feature_enabled)
        ),
        "mode: {}".format(macro.configured_mode),
        "provider_root_available: {}".format(
            _yes_no(macro.provider_root_available)
        ),
        "expected_commit: {}".format(
            macro.expected_producer_commit_sha or "NOT_CONFIGURED"
        ),
        "actual_commit: {}".format(
            macro.actual_producer_commit_sha or "NOT_OBSERVED"
        ),
        "commit_matches: {}".format(
            _yes_no(macro.producer_commit_matches)
        ),
        "tracked_worktree_clean: {}".format(
            _yes_no(macro.tracked_worktree_clean)
        ),
        "cli_available: {}".format(_yes_no(macro.cli_available)),
        "current_trade_support: {} ({})".format(
            (
                "SUPPORTED"
                if macro.exposure.supported is True
                else "UNSUPPORTED"
                if macro.exposure.supported is False
                else "NOT_CHECKED"
            ),
            macro.exposure.detail,
        ),
    ]
    for asset in macro.assets:
        lines.extend(
            [
                "{}_expected_sha256: {}".format(
                    asset.asset,
                    asset.expected_sha256 or "NOT_CONFIGURED",
                ),
                "{}_actual_sha256: {}".format(
                    asset.asset,
                    asset.actual_sha256 or "NOT_OBSERVED",
                ),
                "{}_sha256_matches: {}".format(
                    asset.asset,
                    _yes_no(asset.sha256_matches),
                ),
            ]
        )
    if macro.local_cli_e2e is not None:
        e2e = macro.local_cli_e2e
        lines.extend(
            [
                "",
                "[local_cli synthetic E2E]",
                "status: {}".format(e2e.status),
                "executed: {}".format(_yes_no(e2e.executed)),
                "fixture_id: {}".format(e2e.fixture_id),
                "api_free: YES",
                "result_status: {}".format(
                    e2e.result_status or "UNKNOWN"
                ),
                "pricing_status: {}".format(
                    e2e.pricing_status or "UNKNOWN"
                ),
                "validation_passed: {}".format(
                    _yes_no(e2e.validation_passed)
                ),
                "candidate_count: {}".format(
                    (
                        e2e.candidate_count
                        if e2e.candidate_count is not None
                        else "UNKNOWN"
                    )
                ),
                "candidate_ranks: {}".format(
                    ",".join(str(item) for item in e2e.candidate_ranks)
                    or "NONE"
                ),
                "temporary_raw_output_deleted: {}".format(
                    _yes_no(e2e.temporary_raw_output_deleted)
                ),
            ]
        )
    lines.extend(
        [
            "",
            "API key values: NOT INCLUDED",
            "Stage 1~5 calculation changes: NONE",
            "External hedge publication boundary: REFERENCE ONLY",
        ]
    )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 1·spot·kb_macro_ai 연결 준비 상태를 비밀값 없이 점검합니다."
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="sanitized strict JSON만 출력합니다.",
    )
    parser.add_argument(
        "--run-local-cli-e2e",
        action="store_true",
        help=(
            "고정 단일 USD 100,000 수입 지급 fixture로 pinned local_cli를 "
            "실행합니다. 외부 API는 호출하지 않습니다."
        ),
    )
    parser.add_argument(
        "--passive-stage1",
        action="store_true",
        help="Stage 1 provider를 호출하지 않고 설정 상태만 표시합니다.",
    )
    args = parser.parse_args()

    load_dotenv(override=False)
    report = build_integration_readiness_report(
        settings=Settings.from_env(),
        active_stage1_check=not args.passive_stage1,
        run_local_cli_e2e=args.run_local_cli_e2e,
    )
    if args.json:
        print(
            json.dumps(
                report.model_dump(),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("\n".join(_human_lines(report)))
    return 0 if report.status in {"READY", "DEGRADED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
