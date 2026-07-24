from decimal import Decimal
from typing import Dict


def ratio_sum_is_one(
    forward_ratio: Decimal,
    staged_ratio: Decimal,
    unhedged_ratio: Decimal,
) -> bool:
    return (
        forward_ratio + staged_ratio + unhedged_ratio
        == Decimal("1")
    )


def constraint_penalties(
    *,
    worst_case_loss: Decimal,
    acceptable_loss: Decimal,
    estimated_buffer_shortfall: Decimal,
) -> Dict[str, Decimal]:
    return {
        "loss_limit_violation": max(
            worst_case_loss - acceptable_loss,
            Decimal("0"),
        ),
        "buffer_shortfall": max(
            estimated_buffer_shortfall,
            Decimal("0"),
        ),
    }
