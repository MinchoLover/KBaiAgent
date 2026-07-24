from decimal import Decimal, ROUND_HALF_UP
from typing import List

from src.stage2.metrics import date_value, decimal_value


def allocate_capped(
    total_text: str,
    cap_texts: List[str],
) -> List[str]:
    remaining = decimal_value(total_text, "allocation total")
    allocations: List[str] = []
    for cap_text in cap_texts:
        cap = decimal_value(cap_text, "allocation cap")
        allocated = min(remaining, cap)
        allocations.append(format(allocated, "f"))
        remaining -= allocated
    return allocations


def allocate_capped_by_date(
    total_text: str,
    cap_texts: List[str],
    settlement_dates: List[str],
    available_date: str,
) -> List[str]:
    if len(cap_texts) != len(settlement_dates):
        raise ValueError("allocation cap과 settlement date 개수가 다릅니다.")
    available = date_value(available_date, "allocation available_date")
    settlements = [
        date_value(value, "allocation settlement_date")
        for value in settlement_dates
    ]

    remaining = decimal_value(total_text, "dated allocation total")
    allocations: List[str] = []
    for cap_text, settlement in zip(cap_texts, settlements):
        cap = decimal_value(cap_text, "dated allocation cap")
        if available > settlement:
            allocations.append("0")
            continue
        allocated = min(remaining, cap)
        allocations.append(format(allocated, "f"))
        remaining -= allocated
    return allocations


def allocate_fee_proportionally(
    total_fee_text: str,
    weight_texts: List[str],
) -> List[str]:
    total_fee = decimal_value(total_fee_text, "total hedge fee")
    weights = [
        decimal_value(value, "hedge fee weight") for value in weight_texts
    ]
    weight_total = sum(weights, Decimal("0"))
    if weight_total == 0:
        return ["0" for unused_weight in weights]

    positive_indexes = [
        index for index, weight in enumerate(weights) if weight > 0
    ]
    last_positive = positive_indexes[-1]
    allocated_total = Decimal("0")
    allocations: List[Decimal] = []
    for index, weight in enumerate(weights):
        if weight == 0:
            allocation = Decimal("0")
        elif index == last_positive:
            allocation = total_fee - allocated_total
        else:
            proportional = (
                total_fee * weight / weight_total
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            allocation = min(
                proportional,
                total_fee - allocated_total,
            )
            allocated_total += allocation
        allocations.append(allocation)
    return [format(value, "f") for value in allocations]
