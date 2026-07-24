from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


KRW_QUANTUM = Decimal("0.01")


def decimal_value(
    value: str,
    field: str,
    allow_zero: bool = True,
    allow_negative: bool = False,
) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(
            "{}은 decimal 문자열이어야 합니다.".format(field)
        ) from exc
    if not parsed.is_finite():
        raise ValueError("{}은 유한한 값이어야 합니다.".format(field))
    if not allow_zero and parsed == 0:
        raise ValueError("{}은 0이 아닌 값이어야 합니다.".format(field))
    if not allow_negative and parsed < 0:
        raise ValueError("{}은 0 이상 값이어야 합니다.".format(field))
    return parsed


def decimal_percent(value: str, field: str) -> Decimal:
    parsed = decimal_value(value, field)
    if parsed > 1:
        raise ValueError("{}은 0과 1 사이 비율이어야 합니다.".format(field))
    return parsed


def money_string(value: Decimal) -> str:
    return format(
        value.quantize(KRW_QUANTUM, rounding=ROUND_HALF_UP),
        "f",
    )


def decimal_string(value: Decimal) -> str:
    return format(value, "f")
