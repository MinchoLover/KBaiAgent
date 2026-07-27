import json
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional

from src.domain.stage1_web_models import SpotQuote


KOREAEXIM_EXCHANGE_URL = (
    "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"
)
KoreaEximFetcher = Callable[[str, float], bytes]


class SpotRateError(RuntimeError):
    pass


def _positive_decimal(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("{}은 decimal이어야 합니다.".format(field)) from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("{}은 0보다 커야 합니다.".format(field))
    return parsed


def _pair_currency(pair: str) -> str:
    normalized = pair.strip().upper()
    parts = normalized.split("/")
    if (
        len(parts) != 2
        or len(parts[0]) != 3
        or parts[1] != "KRW"
    ):
        raise ValueError("환율 pair는 FX/KRW 형식이어야 합니다.")
    return parts[0]


def _quote_convention(currency: str) -> str:
    return "KRW_PER_1_{}".format(currency)


def _default_fetcher(url: str, timeout_seconds: float) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "KBaiAgent-spot-adapter/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            body = response.read(512 * 1024 + 1)
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
    ) as exc:
        raise SpotRateError(
            "한국수출입은행 환율 API 호출에 실패했습니다."
        ) from exc
    if len(body) > 512 * 1024:
        raise SpotRateError("공식 환율 API 응답 크기가 너무 큽니다.")
    return body


class SpotRateProvider(ABC):
    @abstractmethod
    def get_quote(
        self,
        pair: str,
        as_of: Optional[date] = None,
    ) -> SpotQuote:
        raise NotImplementedError


class ManualSpotRateProvider(SpotRateProvider):
    def __init__(
        self,
        *,
        rate: str,
        user_confirmed: bool,
        observed_at: Optional[str] = None,
    ) -> None:
        self.rate = rate
        self.user_confirmed = user_confirmed
        self.observed_at = observed_at

    def get_quote(
        self,
        pair: str,
        as_of: Optional[date] = None,
    ) -> SpotQuote:
        currency = _pair_currency(pair)
        if not self.user_confirmed:
            raise SpotRateError(
                "수동 기준환율은 사용자가 확인해야 계산에 사용할 수 있습니다."
            )
        parsed = _positive_decimal(self.rate, "수동 기준환율")
        observed_at = self.observed_at or datetime.now(
            timezone.utc
        ).isoformat()
        return SpotQuote(
            pair="{}/KRW".format(currency),
            rate=format(parsed, "f"),
            quote_convention=_quote_convention(currency),
            rate_type="USER_CONFIRMED_MANUAL",
            as_of=observed_at,
            source="USER_CONFIRMED_MANUAL",
            user_confirmed=True,
        )


class FixtureSpotRateProvider(SpotRateProvider):
    def __init__(
        self,
        *,
        rates: Optional[Dict[str, str]] = None,
        observed_at: str = "2026-07-27T09:00:00+09:00",
    ) -> None:
        self.rates = rates or {"USD/KRW": "1400.00"}
        self.observed_at = observed_at

    def get_quote(
        self,
        pair: str,
        as_of: Optional[date] = None,
    ) -> SpotQuote:
        del as_of
        normalized = pair.strip().upper()
        currency = _pair_currency(normalized)
        if normalized not in self.rates:
            raise SpotRateError(
                "fixture에 {} 환율이 없습니다.".format(normalized)
            )
        parsed = _positive_decimal(
            self.rates[normalized],
            "fixture 기준환율",
        )
        return SpotQuote(
            pair=normalized,
            rate=format(parsed, "f"),
            quote_convention=_quote_convention(currency),
            rate_type="TEST_FIXTURE",
            as_of=self.observed_at,
            source="TEST_FIXTURE_NOT_LIVE_RATE",
            user_confirmed=False,
        )


def _business_dates(end: date, count: int) -> List[date]:
    values: List[date] = []
    cursor = end
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor)
        cursor -= timedelta(days=1)
    return values


def _parse_koreaexim_quote(
    body: bytes,
    *,
    currency: str,
    requested_date: date,
) -> Optional[SpotQuote]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpotRateError(
            "한국수출입은행 환율 응답이 JSON이 아닙니다."
        ) from exc
    if not isinstance(payload, list):
        raise SpotRateError("한국수출입은행 환율 응답 형식이 다릅니다.")
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("result") == 3:
            raise SpotRateError("한국수출입은행 API 인증에 실패했습니다.")
        if item.get("result") == 4:
            raise SpotRateError("한국수출입은행 API 일일 한도를 초과했습니다.")
        unit_text = str(item.get("cur_unit") or "").upper()
        if not (
            unit_text == currency
            or unit_text.startswith("{}(".format(currency))
        ):
            continue
        rate = _positive_decimal(
            item.get("deal_bas_r"),
            "한국수출입은행 매매기준율",
        )
        unit = Decimal("1")
        if "(" in unit_text and ")" in unit_text:
            unit_text_value = unit_text.split("(", 1)[1].split(")", 1)[0]
            unit = _positive_decimal(
                unit_text_value,
                "한국수출입은행 환율 고시단위",
            )
        normalized_rate = rate / unit
        return SpotQuote(
            pair="{}/KRW".format(currency),
            rate=format(normalized_rate, "f"),
            quote_convention=_quote_convention(currency),
            rate_type="MARKET_OR_REFERENCE",
            as_of=requested_date.isoformat(),
            source="KOREAEXIM_DEAL_BASE_RATE",
            user_confirmed=False,
        )
    return None


class KoreaEximSpotRateProvider(SpotRateProvider):
    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 10.0,
        lookback_business_days: int = 7,
        fetcher: Optional[KoreaEximFetcher] = None,
    ) -> None:
        if not api_key.strip():
            raise SpotRateError("KOREAEXIM_KEY가 설정되지 않았습니다.")
        if timeout_seconds <= 0:
            raise ValueError("환율 API timeout은 0보다 커야 합니다.")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.lookback_business_days = lookback_business_days
        self.fetcher = fetcher or _default_fetcher

    def get_quote(
        self,
        pair: str,
        as_of: Optional[date] = None,
    ) -> SpotQuote:
        currency = _pair_currency(pair)
        end = as_of or datetime.now(timezone.utc).date()
        for requested_date in _business_dates(
            end,
            self.lookback_business_days,
        ):
            query = urllib.parse.urlencode(
                {
                    "authkey": self.api_key,
                    "searchdate": requested_date.strftime("%Y%m%d"),
                    "data": "AP01",
                }
            )
            body = self.fetcher(
                "{}?{}".format(KOREAEXIM_EXCHANGE_URL, query),
                self.timeout_seconds,
            )
            quote = _parse_koreaexim_quote(
                body,
                currency=currency,
                requested_date=requested_date,
            )
            if quote is not None:
                return quote
        raise SpotRateError(
            "최근 영업일에서 {} 공식 기준환율을 찾지 못했습니다.".format(
                currency
            )
        )


def resolve_spot_quote(
    *,
    provider_name: str,
    pair: str,
    manual_rate: Optional[str],
    manual_confirmed: bool,
    koreaexim_key: Optional[str],
    demo_mode: bool,
    as_of: Optional[date] = None,
    koreaexim_fetcher: Optional[KoreaEximFetcher] = None,
) -> SpotQuote:
    normalized = provider_name.strip().lower()
    if normalized not in {"auto", "koreaexim", "manual", "fixture"}:
        raise ValueError(
            "SPOT_RATE_PROVIDER는 auto, koreaexim, manual, fixture 중 "
            "하나여야 합니다."
        )
    if normalized in {"auto", "koreaexim"} and koreaexim_key:
        try:
            return KoreaEximSpotRateProvider(
                api_key=koreaexim_key,
                fetcher=koreaexim_fetcher,
            ).get_quote(pair, as_of=as_of)
        except SpotRateError:
            if normalized == "koreaexim":
                raise
    if normalized in {"auto", "manual"} and manual_rate:
        try:
            return ManualSpotRateProvider(
                rate=manual_rate,
                user_confirmed=manual_confirmed,
            ).get_quote(pair, as_of=as_of)
        except SpotRateError:
            if normalized == "manual":
                raise
    if normalized in {"auto", "fixture"} and demo_mode:
        return FixtureSpotRateProvider().get_quote(pair, as_of=as_of)
    raise SpotRateError(
        "공식 환율 또는 사용자 확인 수동 환율이 없어 분석을 차단했습니다."
    )
