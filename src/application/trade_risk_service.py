import re
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

from schemas import StrictModel, TradeDocumentExtraction
from src.domain.trade_risk_models import (
    BalancePaymentMethod,
    FactSource,
    PaymentTermBasis,
)


NET_TERM_RE = re.compile(
    r"\bnet\s*(\d{1,4})"
    r"(?:\s+(?:calendar|business)\s+days?|\s+days?)?\b",
    re.IGNORECASE,
)
COMPLEX_TERM_RE = re.compile(
    r"\b(?:eom|end\s+of\s+month|following|acceptance|b/?l|"
    r"after\s+shipment|from\s+shipment|after\s+delivery|"
    r"from\s+delivery|inspection)\b",
    re.IGNORECASE,
)
ADVANCE_PERCENT_RE = re.compile(
    r"(\d{1,3}(?:\.\d+)?)\s*%\s*"
    r"(?:advance|prepayment|upfront|down\s*payment|선급|선결제|계약금)",
    re.IGNORECASE,
)


class TradeRiskPrefill(StrictModel):
    advance_payment_ratio: Optional[str] = None
    balance_payment_method: BalancePaymentMethod = "UNKNOWN"
    payment_term_days: Optional[int] = None
    payment_term_basis: PaymentTermBasis = "UNKNOWN"
    field_sources: Dict[str, FactSource]


def _has_verified_evidence(
    extraction: TradeDocumentExtraction,
    field: str,
    expected_value: str,
) -> bool:
    normalized_expected = " ".join(
        expected_value.casefold().split()
    )
    return any(
        item.field == field
        and item.extraction_type != "INFERRED"
        and item.source_text.strip()
        and normalized_expected
        in " ".join(item.source_text.casefold().split())
        for item in extraction.evidence
    )


def _payment_method(terms: str) -> BalancePaymentMethod:
    lowered = terms.casefold()
    if (
        "documents against acceptance" in lowered
        or re.search(r"\bd\s*/\s*a\b", lowered)
    ):
        return "DOCUMENTARY_COLLECTION_DA"
    if (
        "documents against payment" in lowered
        or re.search(r"\bd\s*/\s*p\b", lowered)
    ):
        return "DOCUMENTARY_COLLECTION_DP"
    if "documentary collection" in lowered:
        return "DOCUMENTARY_COLLECTION_UNSPECIFIED"
    if (
        "letter of credit" in lowered
        or "documentary credit" in lowered
        or re.search(r"\bl\s*/\s*c\b", lowered)
    ):
        return "DOCUMENTARY_CREDIT"
    if "open account" in lowered:
        return "OPEN_ACCOUNT"
    return "UNKNOWN"


def _advance_ratio(terms: str) -> Optional[str]:
    match = ADVANCE_PERCENT_RE.search(terms)
    if match is None:
        return None
    try:
        percent = Decimal(match.group(1))
    except InvalidOperation:
        return None
    if percent < 0 or percent > 100:
        return None
    ratio = percent / Decimal("100")
    if ratio == 0:
        return "0"
    if ratio == 1:
        return "1"
    return format(ratio.normalize(), "f")


def build_trade_risk_prefill(
    extraction: TradeDocumentExtraction,
) -> TradeRiskPrefill:
    sources: Dict[str, FactSource] = {
        "counterparty_relationship": "UNKNOWN",
        "advance_payment_ratio": "UNKNOWN",
        "balance_payment_method": "UNKNOWN",
        "payment_term_days": "UNKNOWN",
        "protection_information_status": "UNKNOWN",
    }
    terms = extraction.payment_terms or ""
    if not terms or not _has_verified_evidence(
        extraction,
        "payment_terms",
        terms,
    ):
        return TradeRiskPrefill(field_sources=sources)

    method = _payment_method(terms)
    ratio = _advance_ratio(terms)
    if ratio == "1":
        method = "NOT_APPLICABLE"
    match = NET_TERM_RE.search(terms)
    term_days: Optional[int] = None
    term_basis: PaymentTermBasis = "UNKNOWN"
    if match is not None and COMPLEX_TERM_RE.search(terms):
        term_basis = "EVENT_BASED_UNRESOLVED"
    elif match is not None:
        term_days = int(match.group(1))
        term_basis = "EXPLICIT_NET_TERM"

    if method != "UNKNOWN":
        sources["balance_payment_method"] = "DOCUMENT_EXPLICIT"
    if ratio is not None:
        sources["advance_payment_ratio"] = "DOCUMENT_EXPLICIT"
    if term_days is not None:
        sources["payment_term_days"] = "DETERMINISTIC_DERIVED"

    return TradeRiskPrefill(
        advance_payment_ratio=ratio,
        balance_payment_method=method,
        payment_term_days=term_days,
        payment_term_basis=term_basis,
        field_sources=sources,
    )
