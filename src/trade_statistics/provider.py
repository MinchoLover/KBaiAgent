import hashlib
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, Dict, List, Optional, Protocol, Set, Tuple

from src.domain.trade_statistics_models import (
    TradeStatisticsErrorCode,
    TradeStatisticsObservation,
    TradeStatisticsRequest,
    TradeStatisticsSnapshot,
)
from src.trade_statistics.periods import (
    korea_today,
    latest_complete_month,
    month_range,
    shift_month,
    split_period_range,
)


CUSTOMS_OPEN_API_ENDPOINT = (
    "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
)
CUSTOMS_SOURCE_NAME = "KOREA_CUSTOMS_SERVICE"


class TradeStatisticsProviderError(ValueError):
    def __init__(
        self,
        code: TradeStatisticsErrorCode,
        user_message: str,
    ) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


class TradeStatisticsProvider(Protocol):
    def fetch(
        self,
        request: TradeStatisticsRequest,
    ) -> TradeStatisticsSnapshot:
        ...


Transport = Callable[[str, float], bytes]


def _default_transport(url: str, timeout_seconds: float) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/xml"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def _text(element: ET.Element, name: str) -> Optional[str]:
    child = element.find(name)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _required_text(element: ET.Element, name: str) -> str:
    value = _text(element, name)
    if value is None:
        raise TradeStatisticsProviderError(
            "RESPONSE_PARSE_ERROR",
            "공식 통계 응답에 필수 필드가 없습니다. 현재 거래 계산에는 "
            "영향을 주지 않습니다.",
        )
    return value


def _normalize_period(value: str) -> str:
    compact = value.strip().replace(".", "").replace("-", "")
    if len(compact) != 6 or not compact.isdigit():
        raise TradeStatisticsProviderError(
            "RESPONSE_PARSE_ERROR",
            "공식 통계 응답의 관측월 형식이 올바르지 않습니다. 현재 "
            "거래 계산에는 영향을 주지 않습니다.",
        )
    return "{}-{}".format(compact[:4], compact[4:])


def _decimal_text(value: str, field_name: str) -> str:
    normalized = value.strip().replace(",", "")
    try:
        parsed = Decimal(normalized)
    except InvalidOperation as exc:
        raise TradeStatisticsProviderError(
            "RESPONSE_PARSE_ERROR",
            "공식 통계 응답의 {} 값을 숫자로 확인할 수 없습니다.".format(
                field_name
            ),
        ) from exc
    if not parsed.is_finite():
        raise TradeStatisticsProviderError(
            "RESPONSE_PARSE_ERROR",
            "공식 통계 응답의 {} 값이 유한한 숫자가 아닙니다.".format(
                field_name
            ),
        )
    return format(parsed, "f")


def _response_items(root: ET.Element) -> List[ET.Element]:
    items = root.findall(".//item")
    if items:
        return items
    # 일부 공공데이터 응답은 item wrapper 없이 row를 반복합니다.
    candidates = root.findall(".//nitemtrade")
    return candidates


@dataclass(frozen=True)
class _CustomsAmounts:
    export_value: Decimal
    import_value: Decimal
    balance_value: Decimal
    export_weight: Optional[Decimal]
    import_weight: Optional[Decimal]


@dataclass(frozen=True)
class _CustomsDetailRow:
    period: str
    response_hs: Optional[str]
    amounts: _CustomsAmounts


def _amounts_from_item(item: ET.Element) -> _CustomsAmounts:
    export_weight_raw = _text(item, "expWgt")
    import_weight_raw = _text(item, "impWgt")
    amounts = _CustomsAmounts(
        export_value=Decimal(
            _decimal_text(_required_text(item, "expDlr"), "expDlr")
        ),
        import_value=Decimal(
            _decimal_text(_required_text(item, "impDlr"), "impDlr")
        ),
        balance_value=Decimal(
            _decimal_text(
                _required_text(item, "balPayments"),
                "balPayments",
            )
        ),
        export_weight=(
            Decimal(_decimal_text(export_weight_raw, "expWgt"))
            if export_weight_raw is not None
            else None
        ),
        import_weight=(
            Decimal(_decimal_text(import_weight_raw, "impWgt"))
            if import_weight_raw is not None
            else None
        ),
    )
    if (
        abs(
            (amounts.export_value - amounts.import_value)
            - amounts.balance_value
        )
        > Decimal("1")
    ):
        raise TradeStatisticsProviderError(
            "VALIDATION_FAILED",
            "공식 통계 응답의 무역수지가 수출입금액과 일치하지 "
            "않습니다. 검증되지 않은 값은 표시하지 않습니다.",
        )
    return amounts


def _sum_amounts(rows: List[_CustomsDetailRow]) -> _CustomsAmounts:
    export_weights = [
        row.amounts.export_weight
        for row in rows
        if row.amounts.export_weight is not None
    ]
    import_weights = [
        row.amounts.import_weight
        for row in rows
        if row.amounts.import_weight is not None
    ]
    return _CustomsAmounts(
        export_value=sum(
            (row.amounts.export_value for row in rows),
            Decimal("0"),
        ),
        import_value=sum(
            (row.amounts.import_value for row in rows),
            Decimal("0"),
        ),
        balance_value=sum(
            (row.amounts.balance_value for row in rows),
            Decimal("0"),
        ),
        export_weight=(
            sum(export_weights, Decimal("0"))
            if len(export_weights) == len(rows)
            else None
        ),
        import_weight=(
            sum(import_weights, Decimal("0"))
            if len(import_weights) == len(rows)
            else None
        ),
    )


def _validate_total_amounts(
    total: _CustomsAmounts,
    calculated: _CustomsAmounts,
) -> None:
    # The official gateway can apply a small adjustment to the total-row
    # weights. Financial totals must still reconcile exactly within USD 1.
    for official, aggregated in (
        (total.export_value, calculated.export_value),
        (total.import_value, calculated.import_value),
        (total.balance_value, calculated.balance_value),
    ):
        if abs(official - aggregated) > Decimal("1"):
            raise TradeStatisticsProviderError(
                "VALIDATION_FAILED",
                "공식 통계 총계가 상세 수출입금액 합계와 일치하지 "
                "않습니다. 검증되지 않은 값은 표시하지 않습니다.",
            )


def _decimal_display(value: Decimal) -> str:
    return format(value, "f")


def parse_customs_xml(
    raw: bytes,
    request: TradeStatisticsRequest,
    *,
    requested_start: Optional[str] = None,
    requested_end: Optional[str] = None,
    as_of: Optional[date] = None,
) -> List[TradeStatisticsObservation]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise TradeStatisticsProviderError(
            "RESPONSE_PARSE_ERROR",
            "공식 통계 응답을 해석하지 못했습니다. 현재 거래 계산에는 "
            "영향을 주지 않습니다.",
        ) from exc
    result_code = root.findtext(".//resultCode")
    if result_code is None:
        raise TradeStatisticsProviderError(
            "RESPONSE_PARSE_ERROR",
            "공식 통계 응답에 결과코드가 없습니다. 현재 거래 계산에는 "
            "영향을 주지 않습니다.",
        )
    if result_code.strip() not in {"00", "000"}:
        raise TradeStatisticsProviderError(
            "UPSTREAM_ERROR",
            "공식 통계 API가 조회를 완료하지 못했습니다. 현재 거래 "
            "계산에는 영향을 주지 않습니다.",
        )
    start = requested_start or request.period_start
    end = requested_end or request.period_end
    allowed_periods = set(month_range(start, end))
    effective_as_of = as_of or korea_today()
    current_month = "{:04d}-{:02d}".format(
        effective_as_of.year,
        effective_as_of.month,
    )
    detail_rows: List[_CustomsDetailRow] = []
    aggregate_rows: List[_CustomsDetailRow] = []
    total_rows: List[_CustomsAmounts] = []
    raw_keys: Set[Tuple[str, str]] = set()
    for item in _response_items(root):
        raw_period = _required_text(item, "year")
        if raw_period == "총계":
            total_rows.append(_amounts_from_item(item))
            continue
        period = _normalize_period(raw_period)
        if period not in allowed_periods or period > current_month:
            raise TradeStatisticsProviderError(
                "VALIDATION_FAILED",
                "공식 통계 응답이 요청기간을 벗어났습니다. 검증되지 않은 "
                "값은 표시하지 않습니다.",
            )
        country_code = _required_text(item, "statCd").upper()
        if country_code != request.partner_country:
            raise TradeStatisticsProviderError(
                "VALIDATION_FAILED",
                "공식 통계 응답의 거래 상대국이 요청과 일치하지 않습니다.",
            )
        response_hs = _text(item, "hsCd")
        if response_hs in {"", "TOTAL", "ALL", "-"}:
            response_hs = None
        if request.hs_code is not None and (
            response_hs is None
            or not response_hs.isdigit()
            or not response_hs.startswith(request.hs_code)
            or len(response_hs) not in {2, 4, 6, 10}
        ):
            raise TradeStatisticsProviderError(
                "VALIDATION_FAILED",
                "공식 통계 응답의 HS Code가 요청과 일치하지 않습니다.",
            )
        if request.hs_code is None and response_hs is not None and (
            not response_hs.isdigit()
            or len(response_hs) not in {2, 4, 6, 10}
        ):
            raise TradeStatisticsProviderError(
                "VALIDATION_FAILED",
                "공식 통계 응답의 HS Code 형식을 확인할 수 없습니다.",
            )
        raw_key = (period, response_hs or "COUNTRY_TOTAL")
        if raw_key in raw_keys:
            raise TradeStatisticsProviderError(
                "VALIDATION_FAILED",
                "공식 통계 응답에 중복 상세행이 있습니다. 검증되지 "
                "않은 값은 표시하지 않습니다.",
            )
        raw_keys.add(raw_key)
        row = _CustomsDetailRow(
            period=period,
            response_hs=response_hs,
            amounts=_amounts_from_item(item),
        )
        if response_hs is None:
            aggregate_rows.append(row)
        else:
            detail_rows.append(row)
    if len(total_rows) > 1:
        raise TradeStatisticsProviderError(
            "VALIDATION_FAILED",
            "공식 통계 응답에 총계행이 중복됐습니다. 검증되지 않은 "
            "값은 표시하지 않습니다.",
        )
    if detail_rows and aggregate_rows:
        raise TradeStatisticsProviderError(
            "VALIDATION_FAILED",
            "공식 통계 응답에 월별 총계와 상세행이 혼재합니다. "
            "검증되지 않은 값은 표시하지 않습니다.",
        )
    source_rows = detail_rows or aggregate_rows
    if total_rows and source_rows:
        _validate_total_amounts(total_rows[0], _sum_amounts(source_rows))
    grouped: Dict[str, List[_CustomsDetailRow]] = {}
    for row in source_rows:
        grouped.setdefault(row.period, []).append(row)
    observations: List[TradeStatisticsObservation] = []
    for period in sorted(grouped):
        amounts = _sum_amounts(grouped[period])
        observations.append(
            TradeStatisticsObservation(
                period=period,
                reporter_country=request.reporter_country,
                partner_country=request.partner_country,
                hs_code=request.hs_code,
                hs_level=request.hs_level,
                export_value_usd=_decimal_display(amounts.export_value),
                import_value_usd=_decimal_display(amounts.import_value),
                trade_balance_usd=_decimal_display(amounts.balance_value),
                export_weight_kg=(
                    _decimal_display(amounts.export_weight)
                    if amounts.export_weight is not None
                    else None
                ),
                import_weight_kg=(
                    _decimal_display(amounts.import_weight)
                    if amounts.import_weight is not None
                    else None
                ),
                source_record_id="kcs-open-api-{}-{}-{}".format(
                    request.partner_country.lower(),
                    request.hs_code or "total",
                    period,
                ),
            )
        )
    return observations


def _merge_observations(
    groups: List[List[TradeStatisticsObservation]],
) -> List[TradeStatisticsObservation]:
    by_key: Dict[
        Tuple[str, str, str, Optional[str]],
        TradeStatisticsObservation,
    ] = {}
    for group in groups:
        for item in group:
            key = (
                item.period,
                item.reporter_country,
                item.partner_country,
                item.hs_code,
            )
            if key in by_key:
                raise TradeStatisticsProviderError(
                    "VALIDATION_FAILED",
                    "공식 통계 응답에 중복 관측월이 있습니다. 검증되지 "
                    "않은 값은 표시하지 않습니다.",
                )
            by_key[key] = item
    return sorted(by_key.values(), key=lambda item: item.period)


class CustomsOpenApiProvider:
    def __init__(
        self,
        *,
        api_key: Optional[str],
        timeout_seconds: float = 10.0,
        transport: Transport = _default_transport,
        endpoint: str = CUSTOMS_OPEN_API_ENDPOINT,
        as_of: Optional[date] = None,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._endpoint = endpoint
        self._as_of = as_of or korea_today()

    def _url(
        self,
        request: TradeStatisticsRequest,
        start: str,
        end: str,
    ) -> str:
        if not self._api_key:
            raise TradeStatisticsProviderError(
                "MISSING_API_KEY",
                "공식 무역통계 API 키 설정이 필요합니다. 현재 거래 "
                "계산에는 영향을 주지 않습니다.",
            )
        parameters = {
            "serviceKey": self._api_key,
            "strtYymm": start.replace("-", ""),
            "endYymm": end.replace("-", ""),
            "cntyCd": request.partner_country,
        }
        if request.hs_code is not None:
            parameters["hsSgn"] = request.hs_code
        return "{}?{}".format(
            self._endpoint,
            urllib.parse.urlencode(parameters, safe="%"),
        )

    def fetch(
        self,
        request: TradeStatisticsRequest,
    ) -> TradeStatisticsSnapshot:
        if request.source_preference != "LIVE":
            raise TradeStatisticsProviderError(
                "VALIDATION_FAILED",
                "live provider에는 LIVE 요청이 필요합니다.",
            )
        if request.reporter_country != "KR":
            raise TradeStatisticsProviderError(
                "UNSUPPORTED_COUNTRY",
                "현재 공식 관세청 provider는 한국 기준 거래만 "
                "지원합니다.",
            )
        latest_allowed = latest_complete_month(self._as_of)
        if self._as_of.day < 15:
            latest_allowed = shift_month(latest_allowed, -1)
        if request.period_end > latest_allowed:
            raise TradeStatisticsProviderError(
                "INVALID_PERIOD",
                "공식 통계가 확정된 최신 관측월 이후는 조회하지 않습니다.",
            )
        groups: List[List[TradeStatisticsObservation]] = []
        raw_hashes: List[str] = []
        for start, end in split_period_range(
            request.period_start,
            request.period_end,
            max_months=12,
        ):
            try:
                raw = self._transport(
                    self._url(request, start, end),
                    self._timeout_seconds,
                )
            except (TimeoutError, socket.timeout) as exc:
                raise TradeStatisticsProviderError(
                    "UPSTREAM_TIMEOUT",
                    "공식 통계 API 응답 시간이 초과됐습니다. 현재 거래 "
                    "계산에는 영향을 주지 않습니다.",
                ) from exc
            except urllib.error.HTTPError as exc:
                raise TradeStatisticsProviderError(
                    "UPSTREAM_ERROR",
                    "공식 통계 API에 연결하지 못했습니다. 현재 거래 "
                    "계산에는 영향을 주지 않습니다.",
                ) from exc
            except (urllib.error.URLError, OSError) as exc:
                raise TradeStatisticsProviderError(
                    "UPSTREAM_ERROR",
                    "공식 통계 API에 연결하지 못했습니다. 현재 거래 "
                    "계산에는 영향을 주지 않습니다.",
                ) from exc
            raw_hashes.append(hashlib.sha256(raw).hexdigest())
            groups.append(
                parse_customs_xml(
                    raw,
                    request,
                    requested_start=start,
                    requested_end=end,
                    as_of=self._as_of,
                )
            )
        observations = _merge_observations(groups)
        if not observations:
            raise TradeStatisticsProviderError(
                "NO_DATA",
                "요청 범위의 공식 무역통계가 없습니다. 현재 거래 계산에는 "
                "영향을 주지 않습니다.",
            )
        collected_at = datetime.now(timezone.utc).isoformat()
        combined_raw_hash = hashlib.sha256(
            json.dumps(
                raw_hashes,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()
        draft = TradeStatisticsSnapshot(
            snapshot_version="live-{}".format(collected_at[:10]),
            snapshot_id="kcs-live-{}-{}-{}-{}".format(
                request.partner_country.lower(),
                request.hs_code or "country",
                request.period_start,
                request.period_end,
            ),
            source_name=CUSTOMS_SOURCE_NAME,
            provider_status="LIVE",
            collected_at=collected_at,
            observation_start=request.period_start,
            observation_end=request.period_end,
            source_as_of=observations[-1].period,
            reporter_country=request.reporter_country,
            partner_country=request.partner_country,
            hs_code=request.hs_code,
            hs_level=request.hs_level,
            observations=observations,
            raw_sha256=combined_raw_hash,
            normalized_sha256="0" * 64,
            warnings=[],
            limitations=[
                "수출은 FOB, 수입은 CIF 기준의 통관 통계입니다.",
                "수출입 신고의 정정·취하에 따라 과거 값이 변경될 수 "
                "있습니다.",
                "개별 계약의 수익성, 거래처 신용도, 환율 방향 또는 "
                "금융상품 승인 결과를 뜻하지 않습니다.",
            ],
            metadata={
                "official_page_url": (
                    "https://www.data.go.kr/data/15100475/openapi.do"
                ),
                "export_basis": "FOB",
                "import_basis": "CIF",
                "weight_basis": "NET_WEIGHT_KG",
                "request_chunk_count": str(len(groups)),
                "raw_chunk_sha256s": ",".join(raw_hashes),
            },
        )
        # Local import avoids a fixture/provider import cycle.
        from src.trade_statistics.fixture import canonical_snapshot_hash

        return draft.model_copy(
            update={"normalized_sha256": canonical_snapshot_hash(draft)}
        )
