from datetime import date, datetime
from typing import List, Tuple
from zoneinfo import ZoneInfo


KOREA_TIMEZONE = ZoneInfo("Asia/Seoul")


def parse_month(value: str) -> Tuple[int, int]:
    try:
        year_text, month_text = value.split("-", 1)
        year = int(year_text)
        month = int(month_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("관측기간은 YYYY-MM 형식이어야 합니다.") from exc
    if len(value) != 7 or value[4] != "-" or not 1 <= month <= 12:
        raise ValueError("관측기간은 YYYY-MM 형식이어야 합니다.")
    return year, month


def format_month(year: int, month: int) -> str:
    return "{:04d}-{:02d}".format(year, month)


def shift_month(value: str, offset: int) -> str:
    year, month = parse_month(value)
    ordinal = (year * 12 + month - 1) + offset
    shifted_year, shifted_month_zero = divmod(ordinal, 12)
    return format_month(shifted_year, shifted_month_zero + 1)


def month_range(start: str, end: str) -> List[str]:
    parse_month(start)
    parse_month(end)
    if start > end:
        raise ValueError("조회 시작월은 종료월보다 늦을 수 없습니다.")
    values: List[str] = []
    current = start
    while current <= end:
        values.append(current)
        current = shift_month(current, 1)
    return values


def split_period_range(
    start: str,
    end: str,
    *,
    max_months: int = 12,
) -> List[Tuple[str, str]]:
    if max_months < 1:
        raise ValueError("요청 분할 월수는 1 이상이어야 합니다.")
    periods = month_range(start, end)
    chunks: List[Tuple[str, str]] = []
    for index in range(0, len(periods), max_months):
        chunk = periods[index : index + max_months]
        chunks.append((chunk[0], chunk[-1]))
    return chunks


def latest_complete_month(as_of: date) -> str:
    first_of_month = date(as_of.year, as_of.month, 1)
    if first_of_month.month == 1:
        return format_month(first_of_month.year - 1, 12)
    return format_month(first_of_month.year, first_of_month.month - 1)


def korea_today() -> date:
    """Return the calendar date used by the Korean customs publication."""
    return datetime.now(KOREA_TIMEZONE).date()
