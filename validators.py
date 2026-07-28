import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from schemas import (
    ConfirmationState,
    FieldEvidence,
    NormalizationAuditEntry,
    TradeDocumentExtraction,
    ValidationIssue,
    ValidationResult,
)
from src.document_intake.normalization import (
    augment_currency_evidence,
    country_alias_matches_text,
    normalize_country_name,
    normalize_extraction_values,
)
from src.document_intake.source_evidence import (
    augment_party_evidence,
    recover_source_grounded_evidence,
    verify_core_evidence_against_source,
)


ISO_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
DECIMAL_STRING_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
PLAIN_AMOUNT_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
GROUPED_AMOUNT_RE = re.compile(
    r"^-?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?$"
)
NET_TERM_RE = re.compile(
    r"\bnet\s*(\d{1,3})"
    r"(?:\s+(calendar|business)\s+days?|\s+days?)?\b",
    re.IGNORECASE,
)
NET_TERM_REFERENCE_RE = re.compile(
    r"\b(?:from|after)\s+(?:the\s+)?"
    r"(contract|invoice)\s+date\b",
    re.IGNORECASE,
)
COMPLEX_NET_TERM_RE = re.compile(
    r"\b(?:eom|end\s+of\s+month|following|acceptance|b/?l|"
    r"after\s+shipment|from\s+shipment|after\s+delivery|from\s+delivery)\b",
    re.IGNORECASE,
)
PROMPT_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"developer\s+message", re.IGNORECASE),
    re.compile(r"you\s+are\s+chatgpt", re.IGNORECASE),
    re.compile(r"prompt\s+injection", re.IGNORECASE),
)
ADVANCE_PAYMENT_RE = re.compile(
    r"\b(?:advance|advanced|prepayment|prepaid|upfront|down\s*payment)"
    r"\b|선급|선결제|계약금",
    re.IGNORECASE,
)

# The validator needs a deterministic vocabulary to avoid treating ordinary
# three-letter words (for example DUE) as currencies.
ISO_4217_CODES = {
    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG",
    "AZN", "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND",
    "BOB", "BRL", "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF",
    "CHF", "CLP", "CNY", "COP", "CRC", "CUP", "CVE", "CZK", "DJF",
    "DKK", "DOP", "DZD", "EGP", "ERN", "ETB", "EUR", "FJD", "FKP",
    "GBP", "GEL", "GHS", "GIP", "GMD", "GNF", "GTQ", "GYD", "HKD",
    "HNL", "HTG", "HUF", "IDR", "ILS", "INR", "IQD", "IRR", "ISK",
    "JMD", "JOD", "JPY", "KES", "KGS", "KHR", "KMF", "KPW", "KRW",
    "KWD", "KYD", "KZT", "LAK", "LBP", "LKR", "LRD", "LSL", "LYD",
    "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP", "MRU", "MUR",
    "MVR", "MWK", "MXN", "MYR", "MZN", "NAD", "NGN", "NIO", "NOK",
    "NPR", "NZD", "OMR", "PAB", "PEN", "PGK", "PHP", "PKR", "PLN",
    "PYG", "QAR", "RON", "RSD", "RUB", "RWF", "SAR", "SBD", "SCR",
    "SDG", "SEK", "SGD", "SHP", "SLE", "SOS", "SRD", "SSP", "STN",
    "SVC", "SYP", "SZL", "THB", "TJS", "TMT", "TND", "TOP", "TRY",
    "TTD", "TWD", "TZS", "UAH", "UGX", "USD", "UYU", "UZS", "VES",
    "VND", "VUV", "WST", "XAF", "XCD", "XOF", "XPF", "YER", "ZAR",
    "ZMW", "ZWL",
}


def _issue(
    code: str,
    severity: str,
    message: str,
    field: Optional[str] = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        field=field,
        message=message,
    )


def parse_amount(value: Optional[str]) -> Optional[Decimal]:
    """Parse a human-entered amount without silently accepting junk."""

    if value is None or not str(value).strip():
        return None

    cleaned = str(value).strip()
    cleaned = re.sub(r"^[A-Za-z]{3}\s*", "", cleaned)
    cleaned = re.sub(r"\s*[A-Za-z]{3}$", "", cleaned)
    cleaned = cleaned.replace("$", "").replace("€", "").replace("£", "")
    cleaned = cleaned.replace("¥", "").replace("₩", "").strip()

    if GROUPED_AMOUNT_RE.fullmatch(cleaned):
        cleaned = cleaned.replace(",", "")
    elif not PLAIN_AMOUNT_RE.fullmatch(cleaned):
        raise ValueError(
            "금액 형식을 해석할 수 없습니다: {}".format(value)
        )

    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(
            "금액 형식을 해석할 수 없습니다: {}".format(value)
        ) from exc


def parse_decimal_string(value: Optional[str]) -> Optional[Decimal]:
    """Parse the strict model/label contract: decimal strings only."""

    if value is None or not str(value).strip():
        return None

    text = str(value).strip()
    if not DECIMAL_STRING_RE.fullmatch(text):
        raise ValueError(
            "금액은 기호·쉼표 없는 양수 decimal 문자열이어야 합니다: "
            "{}".format(value)
        )

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            "금액 형식을 해석할 수 없습니다: {}".format(value)
        ) from exc


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    if value is None or not str(value).strip():
        return None

    text = str(value).strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            "날짜는 YYYY-MM-DD 형식이어야 합니다: {}".format(value)
        ) from exc

    if parsed.isoformat() != text:
        raise ValueError(
            "날짜는 YYYY-MM-DD 형식이어야 합니다: {}".format(value)
        )
    return parsed


def normalize_currency(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None

    currency = str(value).strip()
    if not ISO_CURRENCY_RE.fullmatch(currency):
        raise ValueError(
            "통화 코드는 USD처럼 대문자 영문 3글자여야 합니다."
        )
    return currency


def calculate_net_due_date(
    base_date: Optional[str],
    payment_terms: Optional[str],
) -> Optional[str]:
    if not base_date or not payment_terms:
        return None

    parsed_base = parse_iso_date(base_date)
    match = NET_TERM_RE.search(payment_terms)
    if parsed_base is None or match is None:
        return None
    if COMPLEX_NET_TERM_RE.search(payment_terms):
        return None

    days = int(match.group(1))
    if days < 0 or days > 365:
        return None
    day_kind = (match.group(2) or "calendar").lower()
    if day_kind == "business":
        cursor = parsed_base
        remaining = days
        while remaining > 0:
            cursor += timedelta(days=1)
            if cursor.weekday() < 5:
                remaining -= 1
        return cursor.isoformat()
    return (parsed_base + timedelta(days=days)).isoformat()


def _net_term_base_date(
    *,
    issue_date: Optional[str],
    contract_date: Optional[str],
    payment_terms: Optional[str],
    document_type: Optional[str],
) -> Optional[str]:
    if not payment_terms:
        return None
    reference = NET_TERM_REFERENCE_RE.search(payment_terms)
    if reference is not None:
        reference_name = reference.group(1).lower()
        return (
            contract_date
            if reference_name == "contract"
            else issue_date
        )
    if document_type == "SALES_CONTRACT":
        return contract_date or issue_date
    return issue_date or contract_date


def calculate_extraction_net_due_date(
    extraction: TradeDocumentExtraction,
) -> Optional[str]:
    base_date = _net_term_base_date(
        issue_date=extraction.issue_date,
        contract_date=extraction.contract_date,
        payment_terms=extraction.payment_terms,
        document_type=extraction.document_type,
    )
    return calculate_net_due_date(base_date, extraction.payment_terms)


def derive_due_date(
    explicit_due_date: Optional[str],
    issue_date: Optional[str],
    payment_terms: Optional[str],
    contract_date: Optional[str] = None,
    document_type: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    if explicit_due_date:
        parsed = parse_iso_date(explicit_due_date)
        return (
            parsed.isoformat() if parsed is not None else None,
            "EXPLICIT",
        )

    base_date = _net_term_base_date(
        issue_date=issue_date,
        contract_date=contract_date,
        payment_terms=payment_terms,
        document_type=document_type,
    )

    calculated = calculate_net_due_date(base_date, payment_terms)
    if calculated:
        return calculated, "DERIVED"
    return None, "MISSING"


def derive_trade_type(
    company_role: str,
    *,
    company_country: Optional[str] = None,
    seller_country: Optional[str] = None,
    buyer_country: Optional[str] = None,
) -> str:
    """Derive cross-border direction only with role and country evidence."""

    normalized_company = (company_country or "").strip().upper()
    normalized_seller = (seller_country or "").strip().upper()
    normalized_buyer = (buyer_country or "").strip().upper()
    if not (
        len(normalized_company) == 2
        and normalized_company.isalpha()
        and len(normalized_seller) == 2
        and normalized_seller.isalpha()
        and len(normalized_buyer) == 2
        and normalized_buyer.isalpha()
    ):
        return "UNKNOWN"
    if normalized_seller == normalized_buyer:
        return "UNKNOWN"
    if (
        company_role == "BUYER"
        and normalized_buyer == normalized_company
    ):
        return "IMPORT"
    if (
        company_role == "SELLER"
        and normalized_seller == normalized_company
    ):
        return "EXPORT"
    return "UNKNOWN"


def _prepare_extraction_for_validation(
    extraction: TradeDocumentExtraction,
    *,
    company_role: Optional[str],
    company_country: Optional[str],
    user_trade_type: Optional[str],
    source_page_texts: Optional[Sequence[str]] = None,
) -> Tuple[
    TradeDocumentExtraction,
    Optional[str],
    List[NormalizationAuditEntry],
    str,
    str,
]:
    normalized, audit = normalize_extraction_values(extraction)
    normalized, evidence_audit = augment_currency_evidence(
        normalized,
        ISO_4217_CODES,
    )
    audit.extend(evidence_audit)
    normalized, source_evidence_audit = verify_core_evidence_against_source(
        normalized,
        source_page_texts=source_page_texts,
    )
    audit.extend(source_evidence_audit)
    normalized, recovered_evidence_audit = (
        recover_source_grounded_evidence(
            normalized,
            source_page_texts=source_page_texts,
            evidence_audit=source_evidence_audit,
        )
    )
    audit.extend(recovered_evidence_audit)
    normalized, party_evidence_audit = augment_party_evidence(
        normalized,
        source_page_texts=source_page_texts,
    )
    audit.extend(party_evidence_audit)
    normalized, final_source_evidence_audit = (
        verify_core_evidence_against_source(
            normalized,
            source_page_texts=source_page_texts,
        )
    )
    audit.extend(final_source_evidence_audit)

    normalized_company_country, company_audit = normalize_country_name(
        company_country,
        "company_country",
    )
    if company_audit.status != "EMPTY":
        audit.append(company_audit)

    effective_role = company_role or normalized.company_role
    if normalized.company_role != effective_role:
        audit.append(
            NormalizationAuditEntry(
                field="company_role",
                raw_value=normalized.company_role,
                normalized_value=effective_role,
                status="USER_CONTEXT_APPLIED",
                message=(
                    "문서 모델 역할보다 사용자가 선택한 회사 역할 {}를 "
                    "적용했습니다.".format(effective_role)
                ),
            )
        )

    auto_trade_type = derive_trade_type(
        effective_role,
        company_country=normalized_company_country,
        seller_country=normalized.seller_country,
        buyer_country=normalized.buyer_country,
    )
    explicit_trade_type = (
        user_trade_type
        if user_trade_type in {"IMPORT", "EXPORT"}
        else None
    )
    final_trade_type = explicit_trade_type or auto_trade_type
    trade_type_source = (
        "USER_OVERRIDE"
        if explicit_trade_type is not None
        else "AUTO"
        if auto_trade_type in {"IMPORT", "EXPORT"}
        else "UNKNOWN"
    )
    normalized = normalized.model_copy(
        update={
            "company_role": effective_role,
            "trade_type": final_trade_type,
            "derived_due_date": None,
        }
    )
    if final_trade_type != extraction.trade_type:
        audit.append(
            NormalizationAuditEntry(
                field="trade_type",
                raw_value=extraction.trade_type,
                normalized_value=final_trade_type,
                status=trade_type_source,
                message=(
                    "정규화된 회사 역할과 당사자 국가를 기준으로 거래 방향을 "
                    "{}로 결정했습니다.".format(final_trade_type)
                    if trade_type_source == "AUTO"
                    else "사용자가 거래 방향을 {}로 명시했습니다.".format(
                        final_trade_type
                    )
                ),
            )
        )
    return (
        normalized,
        normalized_company_country,
        audit,
        auto_trade_type,
        trade_type_source,
    )


def _date_base(extraction: TradeDocumentExtraction) -> Optional[str]:
    if extraction.document_type == "SALES_CONTRACT":
        return extraction.contract_date or extraction.issue_date
    return extraction.issue_date or extraction.contract_date


def _evidence_fields(
    evidence: Sequence[FieldEvidence],
) -> Dict[str, List[FieldEvidence]]:
    grouped: Dict[str, List[FieldEvidence]] = {}
    for item in evidence:
        grouped.setdefault(item.field, []).append(item)
    return grouped


def _is_non_inferred_source_evidence(item: FieldEvidence) -> bool:
    return (
        item.extraction_type != "INFERRED"
        and bool(item.source_text.strip())
    )


def _evidence_contains_value(
    source_text: str,
    value: Optional[str],
) -> bool:
    if not value:
        return False
    source_key = re.sub(r"[^\w]+", " ", source_text.casefold())
    value_key = re.sub(r"[^\w]+", " ", value.casefold())
    source_key = re.sub(r"\s+", " ", source_key).strip()
    value_key = re.sub(r"\s+", " ", value_key).strip()
    return bool(source_key and value_key) and (
        " {} ".format(value_key) in " {} ".format(source_key)
    )


def _mentions_opposite_party(
    source_text: str,
    opposite_name: Optional[str],
    opposite_party: str,
) -> bool:
    if _evidence_contains_value(source_text, opposite_name):
        return True
    labels = {
        "seller": r"\bseller\b|판매자",
        "buyer": r"\bbuyer\b|구매자",
    }
    return bool(
        re.search(labels[opposite_party], source_text, re.IGNORECASE)
    )


def _currencies_from_text(text: str) -> Set[str]:
    candidates = set(re.findall(r"\b[A-Z]{3}\b", text))
    return candidates.intersection(ISO_4217_CODES)


def detect_currencies(
    extraction: TradeDocumentExtraction,
) -> List[str]:
    currencies: Set[str] = set()
    if extraction.currency and ISO_CURRENCY_RE.fullmatch(extraction.currency):
        currencies.add(extraction.currency)

    for installment in extraction.installments:
        if (
            installment.currency
            and ISO_CURRENCY_RE.fullmatch(installment.currency)
        ):
            currencies.add(installment.currency)

    for evidence in extraction.evidence:
        currencies.update(_currencies_from_text(evidence.source_text))

    return sorted(currencies)


def has_prompt_injection_text(
    extraction: TradeDocumentExtraction,
) -> bool:
    text_parts = [item.source_text for item in extraction.evidence]
    text_parts.extend(extraction.warnings)
    combined = "\n".join(text_parts)
    return any(pattern.search(combined) for pattern in PROMPT_INJECTION_PATTERNS)


def required_evidence_gaps(
    extraction: TradeDocumentExtraction,
    due_date_source: str,
) -> List[str]:
    grouped = _evidence_fields(extraction.evidence)
    required: List[str] = []

    if extraction.currency:
        required.append("currency")
    if extraction.amount_due:
        required.append("amount_due")

    base_field = (
        "contract_date"
        if extraction.document_type == "SALES_CONTRACT"
        and extraction.contract_date
        else "issue_date"
        if extraction.issue_date
        else "contract_date"
    )
    if _date_base(extraction):
        required.append(base_field)

    # Confirmation changes the resolved due-date source to USER_CONFIRMED,
    # but it must not erase the evidence obligation of an explicit document
    # date or payment term.
    if extraction.explicit_due_date:
        required.append("explicit_due_date")
    elif extraction.installments:
        required.append("installments")
    elif extraction.payment_terms:
        required.append("payment_terms")

    if extraction.trade_type != "UNKNOWN":
        required.extend(["seller_name", "buyer_name"])

    gaps = {
        field
        for field in required
        if not grouped.get(field)
        or not any(
            _is_non_inferred_source_evidence(item)
            for item in grouped[field]
        )
    }
    if extraction.trade_type != "UNKNOWN":
        for (
            name_field,
            country_field,
            name,
            country,
            opposite_name,
            opposite_party,
        ) in (
            (
                "seller_name",
                "seller_country",
                extraction.seller_name,
                extraction.seller_country,
                extraction.buyer_name,
                "buyer",
            ),
            (
                "buyer_name",
                "buyer_country",
                extraction.buyer_name,
                extraction.buyer_country,
                extraction.seller_name,
                "seller",
            ),
        ):
            name_evidence = grouped.get(name_field, [])
            if not name or not any(
                _is_non_inferred_source_evidence(item)
                and _evidence_contains_value(item.source_text, name)
                for item in name_evidence
            ):
                gaps.add(name_field)

            country_evidence = grouped.get(country_field, [])
            if not country or not any(
                _is_non_inferred_source_evidence(item)
                and country_alias_matches_text(item.source_text, country)
                and not _mentions_opposite_party(
                    item.source_text,
                    opposite_name,
                    opposite_party,
                )
                for item in country_evidence
            ):
                gaps.add(country_field)
    return sorted(gaps)


def _validate_amounts(
    extraction: TradeDocumentExtraction,
    issues: List[ValidationIssue],
) -> None:
    parsed: Dict[str, Optional[Decimal]] = {}
    for field, value in (
        ("grand_total", extraction.grand_total),
        ("amount_due", extraction.amount_due),
    ):
        try:
            parsed[field] = parse_decimal_string(value)
            if parsed[field] is not None and parsed[field] <= 0:
                issues.append(
                    _issue(
                        "NON_POSITIVE_AMOUNT",
                        "CRITICAL",
                        "{}은(는) 0보다 커야 합니다.".format(field),
                        field,
                    )
                )
        except ValueError as exc:
            parsed[field] = None
            issues.append(
                _issue(
                    "INVALID_AMOUNT_FORMAT",
                    "CRITICAL",
                    str(exc),
                    field,
                )
            )

    grand_total = parsed.get("grand_total")
    amount_due = parsed.get("amount_due")
    if (
        grand_total is not None
        and amount_due is not None
        and amount_due > grand_total
    ):
        issues.append(
            _issue(
                "AMOUNT_DUE_EXCEEDS_GRAND_TOTAL",
                "CRITICAL",
                "amount_due가 grand_total보다 큽니다.",
                "amount_due",
            )
        )

    if not extraction.installments:
        return

    installment_amounts: List[Decimal] = []
    installment_sequences: Set[int] = set()
    sequence_values: List[int] = []
    for index, installment in enumerate(extraction.installments):
        field = "installments[{}].amount".format(index)
        if installment.sequence is None:
            issues.append(
                _issue(
                    "MISSING_INSTALLMENT_SEQUENCE",
                    "HIGH",
                    "모든 분할결제 항목에 sequence가 필요합니다.",
                    "installments[{}].sequence".format(index),
                )
            )
        elif installment.sequence in installment_sequences:
            issues.append(
                _issue(
                    "DUPLICATE_INSTALLMENT_SEQUENCE",
                    "HIGH",
                    "분할결제 sequence는 중복될 수 없습니다.",
                    "installments[{}].sequence".format(index),
                )
            )
        else:
            installment_sequences.add(installment.sequence)
            sequence_values.append(installment.sequence)

        currency_field = "installments[{}].currency".format(index)
        try:
            installment_currency = normalize_currency(
                installment.currency
            )
            if installment_currency is None:
                issues.append(
                    _issue(
                        "MISSING_INSTALLMENT_CURRENCY",
                        "HIGH",
                        "모든 분할결제 항목에 currency가 필요합니다.",
                        currency_field,
                    )
                )
            elif (
                extraction.currency
                and installment_currency != extraction.currency
            ):
                issues.append(
                    _issue(
                        "INSTALLMENT_CURRENCY_MISMATCH",
                        "CRITICAL",
                        "분할결제 통화가 문서 거래 통화와 다릅니다.",
                        currency_field,
                    )
                )
        except ValueError as exc:
            issues.append(
                _issue(
                    "INVALID_INSTALLMENT_CURRENCY",
                    "CRITICAL",
                    str(exc),
                    currency_field,
                )
            )

        try:
            amount = parse_decimal_string(installment.amount)
            if amount is None or amount <= 0:
                issues.append(
                    _issue(
                        "INVALID_INSTALLMENT_AMOUNT",
                        "CRITICAL",
                        "모든 분할 금액은 0보다 커야 합니다.",
                        field,
                    )
                )
            else:
                installment_amounts.append(amount)
        except ValueError as exc:
            issues.append(
                _issue(
                    "INVALID_INSTALLMENT_AMOUNT",
                    "CRITICAL",
                    str(exc),
                    field,
                )
            )

    if (
        len(sequence_values) == len(extraction.installments)
        and sequence_values != list(
            range(1, len(extraction.installments) + 1)
        )
    ):
        issues.append(
            _issue(
                "INSTALLMENT_SEQUENCE_GAP",
                "HIGH",
                "분할결제 sequence는 1부터 연속된 순서여야 합니다.",
                "installments",
            )
        )

    if (
        amount_due is not None
        and len(installment_amounts) == len(extraction.installments)
        and abs(sum(installment_amounts, Decimal("0")) - amount_due)
        > Decimal("0.01")
    ):
        issues.append(
            _issue(
                "INSTALLMENT_SUM_MISMATCH",
                "CRITICAL",
                "분할결제 합계가 amount_due와 일치하지 않습니다.",
                "installments",
            )
        )


def _parse_dates(
    extraction: TradeDocumentExtraction,
    issues: List[ValidationIssue],
) -> Dict[str, Optional[date]]:
    parsed: Dict[str, Optional[date]] = {}
    for field, value in (
        ("issue_date", extraction.issue_date),
        ("contract_date", extraction.contract_date),
        ("shipment_date", extraction.shipment_date),
        ("explicit_due_date", extraction.explicit_due_date),
    ):
        try:
            parsed[field] = parse_iso_date(value)
        except ValueError as exc:
            parsed[field] = None
            issues.append(
                _issue(
                    "INVALID_DATE_FORMAT",
                    "CRITICAL",
                    str(exc),
                    field,
                )
            )

    installment_dates: List[date] = []
    for index, installment in enumerate(extraction.installments):
        field = "installments[{}].due_date".format(index)
        try:
            parsed_date = parse_iso_date(installment.due_date)
            if parsed_date is None:
                issues.append(
                    _issue(
                        "MISSING_INSTALLMENT_DUE_DATE",
                        "HIGH",
                        "모든 분할결제 항목에 due_date가 필요합니다.",
                        field,
                    )
                )
            else:
                installment_dates.append(parsed_date)
        except ValueError as exc:
            issues.append(
                _issue(
                    "INVALID_DATE_FORMAT",
                    "CRITICAL",
                    str(exc),
                    field,
                )
            )

    if installment_dates != sorted(installment_dates):
        issues.append(
            _issue(
                "INSTALLMENT_DATE_ORDER",
                "HIGH",
                "분할결제 due_date가 순서대로 증가하지 않습니다.",
                "installments",
            )
        )
    return parsed


def _validate_date_relationships(
    extraction: TradeDocumentExtraction,
    parsed: Dict[str, Optional[date]],
    resolved_due_date: Optional[str],
    issues: List[ValidationIssue],
    audit: List[NormalizationAuditEntry],
) -> None:
    contract = parsed.get("contract_date")
    issue = parsed.get("issue_date")
    shipment = parsed.get("shipment_date")

    if contract and issue and contract > issue:
        issues.append(
            _issue(
                "CONTRACT_AFTER_ISSUE",
                "HIGH",
                "contract_date가 issue_date보다 늦습니다.",
                "contract_date",
            )
        )
    if contract and shipment and contract > shipment:
        issues.append(
            _issue(
                "CONTRACT_AFTER_SHIPMENT",
                "HIGH",
                "contract_date가 shipment_date보다 늦습니다.",
                "contract_date",
            )
        )
    if issue and shipment and issue > shipment:
        issues.append(
            _issue(
                "ISSUE_AFTER_SHIPMENT",
                "MEDIUM",
                "issue_date가 shipment_date보다 늦습니다. 문서 맥락을 확인하세요.",
                "issue_date",
            )
        )

    if resolved_due_date:
        try:
            due = parse_iso_date(resolved_due_date)
        except ValueError:
            due = None
        if due:
            for field, value in (
                ("issue_date", issue),
                ("contract_date", contract),
                ("shipment_date", shipment),
            ):
                if value and value > due:
                    if (
                        field == "shipment_date"
                        and ADVANCE_PAYMENT_RE.search(
                            extraction.payment_terms or ""
                        )
                    ):
                        continue
                    issues.append(
                        _issue(
                            "DUE_DATE_BEFORE_{}".format(field.upper()),
                            "CRITICAL",
                            "결제일이 {}보다 빠릅니다.".format(field),
                            "explicit_due_date",
                        )
                    )

    try:
        calculated = calculate_extraction_net_due_date(extraction)
    except ValueError:
        calculated = None
    if extraction.explicit_due_date and calculated:
        if extraction.explicit_due_date != calculated:
            issues.append(
                _issue(
                    "DUE_DATE_CONFLICT",
                    "CRITICAL",
                    "명시 결제일과 Net N 결정론 계산 결제일이 충돌합니다.",
                    "explicit_due_date",
                )
            )
        else:
            audit.append(
                NormalizationAuditEntry(
                    field="explicit_due_date",
                    raw_value=extraction.explicit_due_date,
                    normalized_value=calculated,
                    status="VERIFIED",
                    message=(
                        "명시 결제일이 계약 조건의 Net N 결정론 계산값 "
                        "{}와 일치합니다.".format(calculated)
                    ),
                )
            )

    for index, installment in enumerate(extraction.installments):
        try:
            installment_due = parse_iso_date(installment.due_date)
        except ValueError:
            installment_due = None
        if installment_due is None:
            continue
        for field, value in (
            ("issue_date", issue),
            ("contract_date", contract),
            ("shipment_date", shipment),
        ):
            if value and installment_due < value:
                if (
                    field == "shipment_date"
                    and ADVANCE_PAYMENT_RE.search(
                        installment.condition or ""
                    )
                ):
                    continue
                issues.append(
                    _issue(
                        "INSTALLMENT_DUE_BEFORE_{}".format(field.upper()),
                        "CRITICAL",
                        "분할결제일이 {}보다 빠릅니다.".format(field),
                        "installments[{}].due_date".format(index),
                    )
                )


def _resolve_due_date(
    extraction: TradeDocumentExtraction,
    confirmations: ConfirmationState,
    issues: List[ValidationIssue],
) -> Tuple[Optional[str], str]:
    try:
        raw_due_date, raw_source = derive_due_date(
            extraction.explicit_due_date,
            extraction.issue_date,
            extraction.payment_terms,
            contract_date=extraction.contract_date,
            document_type=extraction.document_type,
        )
    except ValueError as exc:
        issues.append(
            _issue(
                "INVALID_DATE_FORMAT",
                "CRITICAL",
                str(exc),
                "explicit_due_date",
            )
        )
        raw_due_date, raw_source = None, "MISSING"

    if confirmations.confirmed_due_date:
        try:
            confirmed = parse_iso_date(confirmations.confirmed_due_date)
        except ValueError as exc:
            issues.append(
                _issue(
                    "INVALID_CONFIRMED_DUE_DATE",
                    "CRITICAL",
                    str(exc),
                    "confirmed_due_date",
                )
            )
            return raw_due_date, raw_source

        confirmed_text = (
            confirmed.isoformat() if confirmed is not None else None
        )
        if raw_due_date and confirmed_text != raw_due_date:
            issues.append(
                _issue(
                    "CONFIRMED_DUE_DATE_CONFLICT",
                    "CRITICAL",
                    "사용자 확인 결제일이 문서/결정론 계산값과 다릅니다.",
                    "confirmed_due_date",
                )
            )
        return confirmed_text, "USER_CONFIRMED"

    if raw_due_date:
        return raw_due_date, raw_source

    if extraction.installments and all(
        item.due_date for item in extraction.installments
    ):
        return None, "INSTALLMENTS"
    return None, "MISSING"


def validate_extraction(
    extraction: TradeDocumentExtraction,
    *,
    company_role: Optional[str] = None,
    company_country: Optional[str] = None,
    confirmations: Optional[ConfirmationState] = None,
    user_trade_type: Optional[str] = None,
    source_page_texts: Optional[Sequence[str]] = None,
) -> ValidationResult:
    """Validate model output without trusting model-provided review flags."""

    confirmation_state = confirmations or ConfirmationState()
    (
        extraction,
        normalized_company_country,
        normalization_audit,
        auto_trade_type,
        trade_type_source,
    ) = _prepare_extraction_for_validation(
        extraction,
        company_role=company_role,
        company_country=company_country,
        user_trade_type=user_trade_type,
        source_page_texts=source_page_texts,
    )
    issues: List[ValidationIssue] = []
    effective_role = company_role or extraction.company_role
    derived_trade_type = extraction.trade_type

    if extraction.company_role != effective_role:
        issues.append(
            _issue(
                "COMPANY_ROLE_MISMATCH",
                "HIGH",
                "모델의 company_role이 사용자 선택과 다릅니다.",
                "company_role",
            )
        )
    if (
        trade_type_source == "USER_OVERRIDE"
        and auto_trade_type in {"IMPORT", "EXPORT"}
        and derived_trade_type != auto_trade_type
    ):
        issues.append(
            _issue(
                "TRADE_TYPE_OVERRIDE_CONFLICT",
                "MEDIUM",
                "사용자가 선택한 trade_type이 정규화된 국가 기반 자동판정과 "
                "다릅니다. 사용자 선택을 유지하되 원문 재확인이 필요합니다.",
                "trade_type",
            )
        )

    unknown_country_fields = {
        item.field
        for item in normalization_audit
        if item.status == "UNKNOWN_ALIAS"
    }
    for item in normalization_audit:
        if item.status == "UNKNOWN_ALIAS":
            issues.append(
                _issue(
                    "UNKNOWN_COUNTRY_ALIAS",
                    "MEDIUM",
                    item.message,
                    item.field,
                )
            )

    if normalized_company_country:
        if (
            len(normalized_company_country) != 2
            or not normalized_company_country.isalpha()
        ):
            issues.append(
                _issue(
                    "INVALID_COMPANY_COUNTRY",
                    "CRITICAL",
                    "사용자 회사 국가는 ISO alpha-2 형태여야 합니다.",
                    "company_country",
                )
            )
        role_country = (
            extraction.buyer_country
            if effective_role == "BUYER"
            else extraction.seller_country
        )
        role_country_field = (
            "buyer_country"
            if effective_role == "BUYER"
            else "seller_country"
        )
        if (
            role_country
            and role_country.upper() != normalized_company_country
            and role_country_field not in unknown_country_fields
        ):
            issues.append(
                _issue(
                    "COMPANY_COUNTRY_ROLE_MISMATCH",
                    "HIGH",
                    "회사 역할에 해당하는 당사자 국가가 사용자 입력과 다릅니다.",
                    "company_role",
                )
            )

    for field, country in (
        ("seller_country", extraction.seller_country),
        ("buyer_country", extraction.buyer_country),
    ):
        if country and (
            len(country) != 2
            or not country.isalpha()
            or country != country.upper()
        ) and field not in unknown_country_fields:
            issues.append(
                _issue(
                    "INVALID_PARTY_COUNTRY",
                    "HIGH",
                    "{}는 대문자 ISO alpha-2 형태여야 합니다.".format(field),
                    field,
                )
            )

    normalized_currency: Optional[str]
    try:
        normalized_currency = normalize_currency(extraction.currency)
    except ValueError as exc:
        normalized_currency = None
        issues.append(
            _issue(
                "INVALID_CURRENCY",
                "CRITICAL",
                str(exc),
                "currency",
            )
        )

    detected_currencies = detect_currencies(extraction)
    if len(detected_currencies) > 1:
        issues.append(
            _issue(
                "MULTIPLE_CURRENCIES",
                "CRITICAL",
                "문서 근거에서 여러 통화가 감지되었습니다: {}".format(
                    ", ".join(detected_currencies)
                ),
                "currency",
            )
        )

    _validate_amounts(extraction, issues)
    parsed_dates = _parse_dates(extraction, issues)
    resolved_due_date, due_date_source = _resolve_due_date(
        extraction,
        confirmation_state,
        issues,
    )
    _validate_date_relationships(
        extraction,
        parsed_dates,
        resolved_due_date,
        issues,
        normalization_audit,
    )
    if (
        extraction.payment_terms
        and not extraction.explicit_due_date
        and not extraction.installments
        and NET_TERM_RE.search(extraction.payment_terms)
        and COMPLEX_NET_TERM_RE.search(extraction.payment_terms)
    ):
        issues.append(
            _issue(
                "UNSUPPORTED_PAYMENT_TERM_DERIVATION",
                "HIGH",
                "복합 Net 조건의 기준일을 자동 계산하지 않고 사람 검토로 보냅니다.",
                "payment_terms",
            )
        )

    evidence_gaps = required_evidence_gaps(
        extraction,
        due_date_source,
    )
    evidence_failure_statuses: Dict[str, str] = {}
    evidence_failure_priority = {
        "EVIDENCE_VALUE_MISMATCH": 3,
        "EVIDENCE_NOT_IN_SOURCE": 2,
        "EVIDENCE_UNVERIFIABLE": 1,
    }
    for entry in normalization_audit:
        if entry.status not in evidence_failure_priority:
            continue
        existing = evidence_failure_statuses.get(entry.field)
        if (
            existing is None
            or evidence_failure_priority[entry.status]
            > evidence_failure_priority[existing]
        ):
            evidence_failure_statuses[entry.field] = entry.status
    evidence_overrides = set(
        confirmation_state.user_confirmed_override_fields
        if confirmation_state.user_confirmed_override
        else []
    )
    unresolved_evidence_gaps: List[str] = []
    for field in evidence_gaps:
        if field in evidence_overrides:
            normalization_audit.append(
                NormalizationAuditEntry(
                    field=field,
                    raw_value=None,
                    normalized_value=None,
                    status="USER_CONFIRMED_OVERRIDE",
                    message=(
                        "AI evidence가 없지만 사용자가 원문에서 {} 값을 "
                        "직접 대조해 확인했습니다.".format(field)
                    ),
                )
            )
            continue
        unresolved_evidence_gaps.append(field)
        failure_status = evidence_failure_statuses.get(field)
        if failure_status == "EVIDENCE_VALUE_MISMATCH":
            issues.append(
                _issue(
                    "EVIDENCE_VALUE_MISMATCH",
                    "HIGH",
                    "핵심 필드 {}의 evidence 인용문과 현재 추출값이 다릅니다.".format(
                        field
                    ),
                    field,
                )
            )
        elif failure_status == "EVIDENCE_NOT_IN_SOURCE":
            issues.append(
                _issue(
                    "EVIDENCE_NOT_IN_SOURCE",
                    "HIGH",
                    "핵심 필드 {}의 evidence 인용문이 업로드 원문에 없습니다.".format(
                        field
                    ),
                    field,
                )
            )
        elif failure_status == "EVIDENCE_UNVERIFIABLE":
            issues.append(
                _issue(
                    "EVIDENCE_UNVERIFIABLE",
                    "HIGH",
                    "핵심 필드 {}는 독립 텍스트 원문으로 자동 대조할 수 없습니다.".format(
                        field
                    ),
                    field,
                )
            )
        issues.append(
            _issue(
                "MISSING_CORE_EVIDENCE",
                "HIGH",
                "핵심 필드 {}의 원문 evidence가 없습니다.".format(field),
                field,
            )
        )

    if (
        unresolved_evidence_gaps
        and source_page_texts is not None
        and not any(page_text.strip() for page_text in source_page_texts)
    ):
        issues.append(
            _issue(
                "OCR_REQUIRED",
                "MEDIUM",
                "PDF에 로컬 텍스트 레이어가 없어 원문 evidence를 "
                "자동 대조할 수 없습니다. 문서를 직접 검토하거나 OCR이 필요합니다.",
                "evidence",
            )
        )

    evidence_by_field = _evidence_fields(extraction.evidence)
    for field in ("currency", "amount_due", "explicit_due_date"):
        for evidence in evidence_by_field.get(field, []):
            if evidence.extraction_type == "INFERRED":
                if field in evidence_overrides:
                    normalization_audit.append(
                        NormalizationAuditEntry(
                            field=field,
                            raw_value=None,
                            normalized_value=None,
                            status="USER_CONFIRMED_OVERRIDE",
                            message=(
                                "AI evidence가 추론값이지만 사용자가 원문에서 "
                                "{} 값을 직접 대조해 확인했습니다.".format(field)
                            ),
                        )
                    )
                    continue
                issues.append(
                    _issue(
                        "INFERRED_CRITICAL_FIELD",
                        "HIGH",
                        "핵심 필드 {}가 추론값입니다.".format(field),
                        field,
                    )
                )

    if has_prompt_injection_text(extraction):
        issues.append(
            _issue(
                "PROMPT_INJECTION_TEXT_DETECTED",
                "MEDIUM",
                "문서 내 명령문을 데이터로만 취급하고 무시했습니다.",
                "evidence",
            )
        )

    for warning in extraction.warnings:
        if warning.strip():
            issues.append(
                _issue(
                    "MODEL_WARNING",
                    "MEDIUM",
                    warning.strip(),
                    "warnings",
                )
            )

    missing_required_fields: List[str] = []
    if normalized_currency is None:
        missing_required_fields.append("currency")
    try:
        amount_due = parse_decimal_string(extraction.amount_due)
    except ValueError:
        amount_due = None
    if amount_due is None or amount_due <= 0:
        missing_required_fields.append("amount_due")
    if not _date_base(extraction):
        missing_required_fields.append("issue_date_or_contract_date")
    if due_date_source == "MISSING":
        missing_required_fields.append("due_date")
    if derived_trade_type == "UNKNOWN":
        missing_required_fields.append("trade_type")

    for field in missing_required_fields:
        issues.append(
            _issue(
                "MISSING_REQUIRED_FIELD",
                "HIGH",
                "Stage 1/2 핵심 필드가 없습니다: {}".format(field),
                field,
            )
        )

    # Preserve stable ordering while removing exact duplicates.
    deduplicated: List[ValidationIssue] = []
    seen: Set[Tuple[str, str, Optional[str], str]] = set()
    for item in issues:
        key = (item.code, item.severity, item.field, item.message)
        if key not in seen:
            seen.add(key)
            deduplicated.append(item)

    has_blocking = any(
        item.severity in {"CRITICAL", "HIGH"} for item in deduplicated
    )
    validation_pass = not has_blocking and not missing_required_fields
    confirmations_complete = (
        confirmation_state.all_critical_fields_confirmed(
            installment_schedule_confirmed=(
                due_date_source == "INSTALLMENTS"
            )
        )
    )

    derived_or_inferred = (
        due_date_source == "DERIVED"
        or any(
            item.extraction_type == "INFERRED"
            for item in extraction.evidence
            if item.field in {
                "currency",
                "amount_due",
                "explicit_due_date",
                "payment_terms",
            }
        )
    )
    needs_human_review = (
        has_blocking
        or bool(missing_required_fields)
        or derived_or_inferred
        or not confirmations_complete
    )
    stage2_allowed = validation_pass and confirmations_complete

    return ValidationResult(
        issues=deduplicated,
        normalization_audit=normalization_audit,
        detected_currencies=detected_currencies,
        normalized_currency=normalized_currency,
        resolved_due_date=resolved_due_date,
        due_date_source=due_date_source,
        auto_trade_type=auto_trade_type,
        derived_trade_type=derived_trade_type,
        trade_type_source=trade_type_source,
        missing_required_fields=missing_required_fields,
        needs_human_review=needs_human_review,
        validation_pass=validation_pass,
        stage2_allowed=stage2_allowed,
    )


def apply_deterministic_review_state(
    extraction: TradeDocumentExtraction,
    *,
    company_role: Optional[str] = None,
    company_country: Optional[str] = None,
    confirmations: Optional[ConfirmationState] = None,
    user_trade_type: Optional[str] = None,
    source_page_texts: Optional[Sequence[str]] = None,
) -> Tuple[TradeDocumentExtraction, ValidationResult]:
    (
        deterministic,
        _,
        _,
        _,
        _,
    ) = _prepare_extraction_for_validation(
        extraction,
        company_role=company_role,
        company_country=company_country,
        user_trade_type=user_trade_type,
        source_page_texts=source_page_texts,
    )
    result = validate_extraction(
        extraction,
        company_role=company_role,
        company_country=company_country,
        confirmations=confirmations,
        user_trade_type=user_trade_type,
        source_page_texts=source_page_texts,
    )
    deterministic = deterministic.model_copy(
        update={
            "derived_due_date": (
                result.resolved_due_date
                if result.due_date_source == "DERIVED"
                else None
            ),
            "missing_required_fields": result.missing_required_fields,
            "needs_human_review": result.needs_human_review,
        }
    )
    return deterministic, result


def build_stage0_output(
    *,
    extraction: TradeDocumentExtraction,
    validation: ValidationResult,
    confirmations: ConfirmationState,
    source_filename: str,
    prompt_version: str,
    confirmation_record: Optional[Any] = None,
) -> Dict[str, Any]:
    if hasattr(confirmation_record, "model_dump"):
        confirmation_payload = confirmation_record.model_dump()
    elif isinstance(confirmation_record, dict):
        confirmation_payload = confirmation_record
    else:
        confirmation_payload = confirmations.model_dump()
    return {
        "schema_version": "1.0.0",
        "prompt_version": prompt_version,
        "source": {
            "type": "DOCUMENT_EXTRACTION",
            "filename": Path(source_filename).name,
            "sha256": (
                confirmation_payload.get("source_sha256")
                if isinstance(confirmation_payload, dict)
                else None
            ),
        },
        "extraction": extraction.model_dump(),
        "validation": validation.model_dump(),
        "confirmation": confirmation_payload,
    }


def build_stage1_output(
    *,
    extraction: TradeDocumentExtraction,
    validation: ValidationResult,
    confirmations: ConfirmationState,
    source_filename: str,
    prompt_version: str,
    confirmation_record: Optional[Any] = None,
) -> Dict[str, Any]:
    """Backward-compatible alias for the former document-stage name."""

    return build_stage0_output(
        extraction=extraction,
        validation=validation,
        confirmations=confirmations,
        source_filename=source_filename,
        prompt_version=prompt_version,
        confirmation_record=confirmation_record,
    )


def build_stage2_input(
    *,
    extraction: TradeDocumentExtraction,
    validation: ValidationResult,
    confirmations: ConfirmationState,
    source_filename: str,
    source_sha256: Optional[str] = None,
    confirmed_at: Optional[str] = None,
) -> Dict[str, Any]:
    if not confirmations.all_critical_fields_confirmed(
        installment_schedule_confirmed=bool(extraction.installments)
    ):
        raise ValueError(
            "회사 역할·거래 방향·금액·통화·결제일을 각각 사용자 확인해야 합니다."
        )
    if not validation.stage2_allowed:
        raise ValueError(
            "CRITICAL/HIGH 검증 오류 또는 필수값 누락을 해결해야 "
            "Stage 2로 전달할 수 있습니다."
        )

    currency = normalize_currency(extraction.currency)
    amount_due = parse_decimal_string(extraction.amount_due)
    if currency is None or amount_due is None or amount_due <= 0:
        raise ValueError("유효한 통화와 0보다 큰 amount_due가 필요합니다.")

    cashflow_events: List[Dict[str, Any]] = []
    if extraction.installments:
        for installment in extraction.installments:
            installment_amount = parse_decimal_string(installment.amount)
            installment_currency = normalize_currency(
                installment.currency or currency
            )
            installment_due = parse_iso_date(installment.due_date)
            if (
                installment_amount is None
                or installment_amount <= 0
                or installment_currency is None
                or installment_due is None
            ):
                raise ValueError("분할결제 항목이 완전하지 않습니다.")
            cashflow_events.append(
                {
                    "sequence": installment.sequence,
                    "currency": installment_currency,
                    "foreign_amount": format(installment_amount, "f"),
                    "settlement_date": installment_due.isoformat(),
                    "condition": installment.condition,
                }
            )
    else:
        settlement_text = (
            confirmations.confirmed_due_date
            or validation.resolved_due_date
        )
        settlement = parse_iso_date(settlement_text)
        if settlement is None:
            raise ValueError("결제 예정일이 필요합니다.")
        cashflow_events.append(
            {
                "sequence": 1,
                "currency": currency,
                "foreign_amount": format(amount_due, "f"),
                "settlement_date": settlement.isoformat(),
                "condition": extraction.payment_terms,
            }
        )

    contract = parse_iso_date(extraction.contract_date)
    return {
        "schema_version": "1.0.0",
        "source": {
            "type": "DOCUMENT_EXTRACTION",
            "filename": Path(source_filename).name,
            "sha256": source_sha256,
            "user_confirmed": True,
            "confirmed_fields": [
                "company_role",
                "trade_type",
                "currency",
                "amount_due",
                "due_date",
            ],
            "confirmed_at": confirmed_at,
        },
        "trade": {
            "trade_type": validation.derived_trade_type,
            "currency": currency,
            "foreign_amount": format(amount_due, "f"),
            "contract_date": (
                contract.isoformat() if contract is not None else None
            ),
            "settlement_date": (
                cashflow_events[0]["settlement_date"]
                if len(cashflow_events) == 1
                else None
            ),
            "cashflow_events": cashflow_events,
            "available_foreign_currency": "0",
        },
        "company_cash": {
            "current_krw_cash": None,
            "minimum_cash_buffer": None,
            "acceptable_loss": None,
        },
        "krw_cashflows": [],
        "status": "NEEDS_COMPANY_CASH_INPUT",
    }
