import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from pydantic import ValidationError

from src.domain.trade_statistics_models import (
    TradeStatisticsRequest,
    TradeStatisticsSnapshot,
)


TRADE_STATISTICS_FIXTURE_VERSION = "2026.08.01-kr-br-country-v1"
ASSET_ROOT = (
    Path(__file__).resolve().parents[1]
    / "integration_assets"
    / "trade_statistics"
)
DEFAULT_FIXTURE_PATH = ASSET_ROOT / "snapshot_kr_br_country_v1.json"
DEFAULT_RAW_PATH = (
    ASSET_ROOT / "raw" / "kr_br_country_2024-07_2026-06.json"
)
FIXTURE_REGISTRY: Dict[
    Tuple[str, str, Optional[str], str], Tuple[Path, Path]
] = {
    (
        "KR",
        "BR",
        None,
        TRADE_STATISTICS_FIXTURE_VERSION,
    ): (DEFAULT_FIXTURE_PATH, DEFAULT_RAW_PATH),
}


class TradeStatisticsFixtureError(ValueError):
    """Raised when a committed official-source fixture fails closed."""


def canonical_snapshot_payload(
    snapshot: TradeStatisticsSnapshot,
) -> Dict[str, Any]:
    payload = snapshot.model_dump(exclude={"normalized_sha256"})
    payload["observations"] = sorted(
        payload["observations"],
        key=lambda item: (
            item["period"],
            item["reporter_country"],
            item["partner_country"],
            item.get("hs_code") or "",
        ),
    )
    return payload


def canonical_snapshot_hash(snapshot: TradeStatisticsSnapshot) -> str:
    serialized = json.dumps(
        canonical_snapshot_payload(snapshot),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except OSError as exc:
        raise TradeStatisticsFixtureError(
            "무역통계 공식 원자료를 읽을 수 없습니다."
        ) from exc
    return digest.hexdigest()


def _raw_decimal(value: object, field_name: str) -> Decimal:
    if not isinstance(value, str):
        raise TradeStatisticsFixtureError(
            "공식 원자료 {} 값이 문자열이 아닙니다.".format(field_name)
        )
    try:
        parsed = Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise TradeStatisticsFixtureError(
            "공식 원자료 {} 값을 숫자로 검증할 수 없습니다.".format(
                field_name
            )
        ) from exc
    if not parsed.is_finite():
        raise TradeStatisticsFixtureError(
            "공식 원자료 {} 값이 유한한 숫자가 아닙니다.".format(
                field_name
            )
        )
    return parsed


def _validate_raw_binding(
    snapshot: TradeStatisticsSnapshot,
    raw_path: Path,
) -> None:
    try:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TradeStatisticsFixtureError(
            "무역통계 공식 원자료 JSON을 검증할 수 없습니다."
        ) from exc
    if raw.get("source_name") != "Korea Customs Service Trade Statistics":
        raise TradeStatisticsFixtureError(
            "무역통계 공식 원자료 source가 일치하지 않습니다."
        )
    if raw.get("response_unit") != "THOUSAND_USD":
        raise TradeStatisticsFixtureError(
            "무역통계 공식 원자료 단위가 일치하지 않습니다."
        )
    request = raw.get("request")
    if not isinstance(request, dict) or (
        request.get("priodKind") != "MON"
        or request.get("priodFr")
        != snapshot.observation_start.replace("-", "")
        or request.get("priodTo")
        != snapshot.observation_end.replace("-", "")
    ):
        raise TradeStatisticsFixtureError(
            "무역통계 공식 원자료 요청 범위가 snapshot과 다릅니다."
        )
    allowed_hosts = {"tradedata.go.kr", "www.data.go.kr"}
    for url_key in (
        "official_page_url",
        "official_query_endpoint",
        "official_open_api_documentation",
    ):
        url = raw.get(url_key)
        parsed = urlparse(str(url))
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
            raise TradeStatisticsFixtureError(
                "무역통계 원자료 공식 URL을 검증할 수 없습니다."
            )
    records = raw.get("records")
    if not isinstance(records, list):
        raise TradeStatisticsFixtureError(
            "무역통계 공식 원자료 records가 없습니다."
        )
    by_period: Dict[str, Dict[str, object]] = {}
    for item in records:
        if not isinstance(item, dict):
            raise TradeStatisticsFixtureError(
                "무역통계 공식 원자료 record 형식이 올바르지 않습니다."
            )
        period_value = str(item.get("priodTitle", "")).replace(".", "-")
        if str(item.get("cntyCd", "")).upper() != snapshot.partner_country:
            raise TradeStatisticsFixtureError(
                "무역통계 공식 원자료 상대국이 snapshot과 다릅니다."
            )
        if period_value in by_period:
            raise TradeStatisticsFixtureError(
                "무역통계 공식 원자료에 중복 월이 있습니다."
            )
        by_period[period_value] = item
    if set(by_period) != {item.period for item in snapshot.observations}:
        raise TradeStatisticsFixtureError(
            "공식 원자료와 정규화 snapshot의 관측월이 일치하지 않습니다."
        )
    if raw.get("response_count") != len(records) + 1:
        raise TradeStatisticsFixtureError(
            "무역통계 공식 원자료 record 수가 일치하지 않습니다."
        )
    for observation in snapshot.observations:
        raw_item = by_period[observation.period]
        expected_export = _raw_decimal(
            raw_item.get("expUsdAmt"), "expUsdAmt"
        ) * Decimal("1000")
        expected_import = _raw_decimal(
            raw_item.get("impUsdAmt"), "impUsdAmt"
        ) * Decimal("1000")
        expected_balance = _raw_decimal(
            raw_item.get("cmtrBlncAmt"), "cmtrBlncAmt"
        ) * Decimal("1000")
        actual = (
            Decimal(observation.export_value_usd),
            Decimal(observation.import_value_usd),
            Decimal(observation.trade_balance_usd),
        )
        expected = (expected_export, expected_import, expected_balance)
        if actual != expected:
            raise TradeStatisticsFixtureError(
                "공식 원자료와 정규화 snapshot 값이 일치하지 않습니다."
            )
    total = raw.get("total_record")
    if not isinstance(total, dict):
        raise TradeStatisticsFixtureError(
            "무역통계 공식 원자료 TOTAL record가 없습니다."
        )
    totals = (
        sum(
            Decimal(item.export_value_usd)
            for item in snapshot.observations
        ),
        sum(
            Decimal(item.import_value_usd)
            for item in snapshot.observations
        ),
        sum(
            Decimal(item.trade_balance_usd)
            for item in snapshot.observations
        ),
    )
    reported = (
        _raw_decimal(total.get("expUsdAmt"), "total.expUsdAmt")
        * Decimal("1000"),
        _raw_decimal(total.get("impUsdAmt"), "total.impUsdAmt")
        * Decimal("1000"),
        _raw_decimal(total.get("cmtrBlncAmt"), "total.cmtrBlncAmt")
        * Decimal("1000"),
    )
    if any(
        abs(calculated - official) > Decimal("1000")
        for calculated, official in zip(totals, reported)
    ):
        raise TradeStatisticsFixtureError(
            "월별 합계와 공식 TOTAL이 허용 반올림 범위를 벗어납니다."
        )


def load_trade_statistics_fixture(
    request: TradeStatisticsRequest,
    *,
    snapshot_path: Optional[Path] = None,
    raw_path: Optional[Path] = None,
) -> TradeStatisticsSnapshot:
    if request.source_preference != "OFFICIAL_FIXTURE":
        raise TradeStatisticsFixtureError(
            "official fixture 요청만 snapshot을 사용할 수 있습니다."
        )
    registry_key = (
        request.reporter_country,
        request.partner_country,
        request.hs_code,
        request.snapshot_version or "",
    )
    registered = FIXTURE_REGISTRY.get(registry_key)
    if registered is None and snapshot_path is None:
        raise TradeStatisticsFixtureError(
            "현재 거래 범위에 맞는 공식 무역통계 fixture가 없습니다."
        )
    effective_snapshot_path = snapshot_path or registered[0]
    effective_raw_path = raw_path or (
        registered[1] if registered is not None else DEFAULT_RAW_PATH
    )
    try:
        payload = json.loads(
            effective_snapshot_path.read_text(encoding="utf-8")
        )
        snapshot = TradeStatisticsSnapshot.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise TradeStatisticsFixtureError(
            "무역통계 공식 snapshot을 검증할 수 없습니다."
        ) from exc
    if snapshot.snapshot_version != request.snapshot_version:
        raise TradeStatisticsFixtureError(
            "요청한 무역통계 snapshot version과 일치하지 않습니다."
        )
    if (
        snapshot.reporter_country != request.reporter_country
        or snapshot.partner_country != request.partner_country
        or snapshot.hs_code != request.hs_code
        or snapshot.hs_level != request.hs_level
    ):
        raise TradeStatisticsFixtureError(
            "무역통계 snapshot 범위가 현재 거래와 일치하지 않습니다."
        )
    if (
        snapshot.observation_start != request.period_start
        or snapshot.observation_end != request.period_end
    ):
        raise TradeStatisticsFixtureError(
            "무역통계 snapshot 관측기간이 요청과 일치하지 않습니다."
        )
    if file_sha256(effective_raw_path) != snapshot.raw_sha256:
        raise TradeStatisticsFixtureError(
            "무역통계 공식 원자료 hash가 일치하지 않습니다."
        )
    if canonical_snapshot_hash(snapshot) != snapshot.normalized_sha256:
        raise TradeStatisticsFixtureError(
            "무역통계 정규화 snapshot hash가 일치하지 않습니다."
        )
    _validate_raw_binding(snapshot, effective_raw_path)
    return snapshot
