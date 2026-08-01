from dataclasses import dataclass
from typing import Optional

from schemas import TradeDocumentExtraction
from src.document_intake.normalization import (
    country_alias_matches_text,
    normalize_country_name,
)


@dataclass(frozen=True)
class CompanyRoleMatch:
    role: str
    company_country: str
    matched_party: str


def _has_verified_country_evidence(
    extraction: TradeDocumentExtraction,
    field: str,
    country: str,
) -> bool:
    return any(
        item.field == field
        and item.extraction_type != "INFERRED"
        and bool(item.source_text.strip())
        and country_alias_matches_text(item.source_text, country)
        for item in extraction.evidence
    )


def match_company_role_from_verified_parties(
    extraction: TradeDocumentExtraction,
    company_country: str,
) -> Optional[CompanyRoleMatch]:
    """Match company role only from two source-grounded party countries."""

    normalized_company, _ = normalize_country_name(
        company_country,
        "company_country",
    )
    normalized_seller, _ = normalize_country_name(
        extraction.seller_country,
        "seller_country",
    )
    normalized_buyer, _ = normalize_country_name(
        extraction.buyer_country,
        "buyer_country",
    )
    if not (
        normalized_company
        and normalized_seller
        and normalized_buyer
        and normalized_seller != normalized_buyer
        and _has_verified_country_evidence(
            extraction,
            "seller_country",
            normalized_seller,
        )
        and _has_verified_country_evidence(
            extraction,
            "buyer_country",
            normalized_buyer,
        )
    ):
        return None

    seller_matches = normalized_seller == normalized_company
    buyer_matches = normalized_buyer == normalized_company
    if seller_matches == buyer_matches:
        return None
    if seller_matches:
        return CompanyRoleMatch(
            role="SELLER",
            company_country=normalized_company,
            matched_party="seller",
        )
    return CompanyRoleMatch(
        role="BUYER",
        company_country=normalized_company,
        matched_party="buyer",
    )
