import re
from decimal import Decimal
from typing import Iterable, List, Tuple

from src.domain.product_models import ProductCandidate, ProductRecord


def tokenize(text: str) -> List[str]:
    return [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9가-힣_]+", text)
        if len(token) > 1
    ]


def rank_records(
    records: Iterable[ProductRecord],
    *,
    query: str,
    trade_type: str,
    limit: int = 8,
) -> List[ProductCandidate]:
    query_tokens = set(tokenize(query))
    scored: List[Tuple[Decimal, ProductRecord]] = []
    for record in records:
        if (
            trade_type not in record.trade_types
            and "BOTH" not in record.trade_types
        ):
            continue
        haystack = " ".join(
            [
                record.name,
                record.category,
                record.summary,
                " ".join(record.keywords),
            ]
        )
        record_tokens = set(tokenize(haystack))
        overlap = len(query_tokens.intersection(record_tokens))
        if overlap == 0:
            continue
        trade_bonus = Decimal("2")
        score = Decimal(overlap) + trade_bonus
        scored.append((score, record))

    scored.sort(key=lambda item: (-item[0], item[1].name))
    candidates: List[ProductCandidate] = []
    for score, record in scored[:limit]:
        payload = record.model_dump()
        payload.update(
            {
                "relevance_score": format(score, "f"),
                "target_customers": (
                    record.target_customers
                    or ["{} 거래 기업".format(trade_type)]
                ),
                "key_conditions": (
                    record.key_conditions
                    or ["자격·한도·가격은 제공 기관의 최신 기준 확인 필요"]
                ),
                "required_documents": (
                    record.required_documents
                    or ["필요 서류는 제공 기관의 최신 안내에서 확인"]
                ),
                "limitations": (
                    record.limitations
                    or ["자격·승인·가격·한도는 확정되지 않은 후보"]
                ),
                "strategy_connection_reason": (
                    "검색어와 공식 상품 분류가 일치해 전략 검토 후보로 연결"
                ),
            }
        )
        candidates.append(ProductCandidate.model_validate(payload))
    return candidates
