from decimal import Decimal


def candidate_reason(
    forward: Decimal,
    staged: Decimal,
    unhedged: Decimal,
    constraints_satisfied: bool,
) -> str:
    parts = []
    if forward > 0:
        parts.append("선물환 비중으로 최악 환율 손실을 제한")
    if staged > 0:
        parts.append("분할환전 비중으로 시점 집중을 완화")
    if unhedged > 0:
        parts.append("일부 미헤지로 유리한 환율 가능성과 비용 절감 유지")
    if constraints_satisfied:
        parts.append("입력된 손실·유동성 제약을 계산상 충족")
    else:
        parts.append("일부 제약 미충족으로 추가 조정 또는 상담 필요")
    return "; ".join(parts)
