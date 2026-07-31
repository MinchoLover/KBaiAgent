import io
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Sequence, Set, Tuple

from pypdf import PdfReader

from schemas import (
    FieldEvidence,
    NormalizationAuditEntry,
    TradeDocumentExtraction,
)
from src.document_intake.normalization import (
    country_alias_matches_text,
    normalize_country_name,
)


PARTIES = ("seller", "buyer")
PARTY_WINDOW_LINES = 6
SEMANTIC_EVIDENCE_FIELDS = {
    "seller_name",
    "seller_country",
    "buyer_name",
    "buyer_country",
    "currency",
    "grand_total",
    "amount_due",
    "issue_date",
    "contract_date",
    "shipment_date",
    "explicit_due_date",
    "payment_terms",
    "installments",
}
AMOUNT_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Z]{3}\s*)?"
    r"(-?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)"
    r"(?![A-Za-z0-9])"
)
AMOUNT_CONTEXT_RE = re.compile(
    r"\b(?:amount|total|price|balance|due|payable|invoice|"
    r"contract\s+value)\b|금액|대금|총액|합계|잔액|지급|결제",
    re.IGNORECASE,
)
DATE_CONTEXT_PATTERNS = {
    "issue_date": re.compile(
        r"\b(?:issue|invoice)\s+date\b|발행일|인보이스\s*일자",
        re.IGNORECASE,
    ),
    "contract_date": re.compile(
        r"\b(?:contract|agreement)\s+date\b|계약일",
        re.IGNORECASE,
    ),
    "shipment_date": re.compile(
        r"\b(?:shipment|shipping)\s+date\b|선적일",
        re.IGNORECASE,
    ),
    "explicit_due_date": re.compile(
        r"\b(?:payment\s+)?due(?:\s+date)?\b|\bpay\s+by\b|"
        r"\bsettlement\s+date\b|\bon\s+or\s+before\b|"
        r"\bno\s+later\s+than\b|\bpayment\s+shall\s+be\s+made\s+by\b|"
        r"\bshall\s+be\s+paid\b.{0,80}\bby\b|결제일|지급일|납기일",
        re.IGNORECASE,
    ),
}
PARTY_LABEL_PATTERNS = {
    "seller": re.compile(r"\bseller\b|판매자", re.IGNORECASE),
    "buyer": re.compile(r"\bbuyer\b|구매자", re.IGNORECASE),
}
KNOWN_CURRENCY_CODES = {
    "AUD",
    "BRL",
    "CAD",
    "CHF",
    "CNY",
    "EUR",
    "GBP",
    "HKD",
    "INR",
    "JPY",
    "KRW",
    "MXN",
    "SGD",
    "USD",
}
CURRENCY_NAME_PATTERNS = {
    "USD": re.compile(
        r"\b(?:United\s+States|U\.?S\.?)\s+dollars?\b",
        re.IGNORECASE,
    ),
}
CONTRACT_TOTAL_CONTEXT_RE = re.compile(
    r"\b(?:total\s+)?contract\s+(?:price|value)\b",
    re.IGNORECASE,
)
INVOICE_TOTAL_CONTEXT_RE = re.compile(
    r"\b(?:invoice|grand)\s+total\b|\btotal\s+invoice\s+amount\b",
    re.IGNORECASE,
)
ORDER_TOTAL_CONTEXT_RE = re.compile(
    r"\b(?:purchase\s+order|order)\s+total\b|\btotal\s+order\s+amount\b",
    re.IGNORECASE,
)
EXPLICIT_AMOUNT_DUE_CONTEXT_RE = re.compile(
    r"\b(?:amount|balance|total)\s+due\b|\bnet\s+payable\b|"
    r"\bpayable\s+amount\b",
    re.IGNORECASE,
)
STRONG_DUE_DATE_CONTEXT_RE = re.compile(
    r"\b(?:payment\s+)?due\s+date\b|\bsettlement\s+date\b|"
    r"\bdue\s+no\s+later\s+than\b",
    re.IGNORECASE,
)
PAYMENT_DUE_ACTION_CONTEXT_RE = re.compile(
    r"\bpayment\s+shall\s+be\s+made\s+by\b|"
    r"\bshall\s+be\s+paid\b.{0,80}\bon\s+or\s+before\b|"
    r"\bpay\s+by\b",
    re.IGNORECASE,
)
WEAK_DUE_DATE_CONTEXT_RE = re.compile(
    r"\bon\s+or\s+before\b|\bno\s+later\s+than\b",
    re.IGNORECASE,
)
NON_DUE_DATE_CONTEXT_RE = re.compile(
    r"\b(?:contract|agreement|shipment|shipping|issue|invoice)\s+date\b",
    re.IGNORECASE,
)
MONTH_NUMBERS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
MONTH_PATTERN = "|".join(
    sorted(MONTH_NUMBERS, key=len, reverse=True)
)
DAY_MONTH_YEAR_RE = re.compile(
    r"\b([0-3]?[0-9])(?:st|nd|rd|th)?\s+({})[,]?\s+"
    r"([12][0-9]{{3}})\b".format(MONTH_PATTERN),
    re.IGNORECASE,
)
MONTH_DAY_YEAR_RE = re.compile(
    r"\b({})\s+([0-3]?[0-9])(?:st|nd|rd|th)?[,]?\s+"
    r"([12][0-9]{{3}})\b".format(MONTH_PATTERN),
    re.IGNORECASE,
)
ISO_DATE_IN_TEXT_RE = re.compile(
    r"(?<![0-9])([12][0-9]{3})-([01]?[0-9])-([0-3]?[0-9])(?![0-9])"
)


def extract_pdf_page_texts(file_bytes: bytes) -> List[str]:
    """Read text PDF pages in memory without persisting document content."""

    try:
        reader = PdfReader(io.BytesIO(file_bytes), strict=True)
        if reader.is_encrypted:
            return []
        return [page.extract_text() or "" for page in reader.pages]
    except Exception:
        # Upload validation reports malformed PDFs. Evidence recovery is a
        # best-effort safety net and must never make extraction less reliable.
        return []


def _search_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _contains_value(source_text: str, value: Optional[str]) -> bool:
    if not value:
        return False
    source_key = _search_key(source_text)
    value_key = _search_key(value)
    if not source_key or not value_key:
        return False
    return " {} ".format(value_key) in " {} ".format(source_key)


def _normalized_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _contains_exact_quote(source_text: str, quote: str) -> bool:
    """Match a verbatim quote while tolerating PDF line-wrap whitespace only."""

    normalized_source = _normalized_whitespace(source_text)
    normalized_quote = _normalized_whitespace(quote)
    return bool(
        normalized_quote
        and normalized_quote in normalized_source
    )


def _currency_codes_in_source(source_text: str) -> Set[str]:
    codes = {
        item
        for item in re.findall(
            r"(?<![A-Za-z])([A-Z]{3})(?![A-Za-z])",
            source_text,
        )
        if item in KNOWN_CURRENCY_CODES
    }
    for code, pattern in CURRENCY_NAME_PATTERNS.items():
        if pattern.search(source_text):
            codes.add(code)
    return codes


def _source_currency_is_consistent(
    source_text: str,
    expected_currency: Optional[str],
    *,
    require_presence: bool,
) -> bool:
    if not expected_currency:
        return not require_presence
    currency = expected_currency.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        return False
    detected = _currency_codes_in_source(source_text)
    if not detected:
        return not require_presence
    return detected == {currency}


def _source_contains_currency(source_text: str, value: Optional[str]) -> bool:
    if not value:
        return False
    currency = value.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        return False
    return bool(
        re.search(
            r"(?<![A-Za-z]){}(?![A-Za-z])".format(
                re.escape(currency)
            ),
            source_text,
        )
    )


def _source_contains_amount(source_text: str, value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        expected = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return False
    for match in AMOUNT_TOKEN_RE.finditer(source_text.upper()):
        try:
            candidate = Decimal(match.group(1).replace(",", ""))
        except (InvalidOperation, ValueError):
            continue
        if candidate == expected:
            return True
    return False


def _amount_values(source_text: str) -> List[Decimal]:
    values: List[Decimal] = []
    for match in AMOUNT_TOKEN_RE.finditer(source_text.upper()):
        try:
            value = Decimal(match.group(1).replace(",", ""))
        except (InvalidOperation, ValueError):
            continue
        if value not in values:
            values.append(value)
    return values


def _date_values(source_text: str) -> List[date]:
    values: List[date] = []

    def append_value(year: int, month: int, day: int) -> None:
        try:
            value = date(year, month, day)
        except ValueError:
            return
        if value not in values:
            values.append(value)

    for match in ISO_DATE_IN_TEXT_RE.finditer(source_text):
        append_value(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        )
    for match in DAY_MONTH_YEAR_RE.finditer(source_text):
        append_value(
            int(match.group(3)),
            MONTH_NUMBERS[match.group(2).lower()],
            int(match.group(1)),
        )
    for match in MONTH_DAY_YEAR_RE.finditer(source_text):
        append_value(
            int(match.group(3)),
            MONTH_NUMBERS[match.group(1).lower()],
            int(match.group(2)),
        )
    return values


def _source_contains_date(source_text: str, value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        expected = date.fromisoformat(value)
    except ValueError:
        return False

    year = str(expected.year)
    month = str(expected.month)
    day = str(expected.day)
    numeric_patterns = (
        r"(?<![0-9]){}\s*[-/.]\s*0?{}\s*[-/.]\s*0?{}(?![0-9])".format(
            year,
            month,
            day,
        ),
        r"(?<![0-9])0?{}\s*[-/.]\s*0?{}\s*[-/.]\s*{}(?![0-9])".format(
            month,
            day,
            year,
        ),
        r"{}\s*년\s*0?{}\s*월\s*0?{}\s*일".format(
            year,
            month,
            day,
        ),
    )
    if any(re.search(pattern, source_text) for pattern in numeric_patterns):
        return True

    month_names = (
        "january jan",
        "february feb",
        "march mar",
        "april apr",
        "may",
        "june jun",
        "july jul",
        "august aug",
        "september sept sep",
        "october oct",
        "november nov",
        "december dec",
    )
    month_pattern = "(?:{})".format(
        "|".join(month_names[expected.month - 1].split())
    )
    suffix = r"(?:st|nd|rd|th)?"
    patterns = (
        r"\b{}\s+0?{}{}[,]?\s+{}\b".format(
            month_pattern,
            day,
            suffix,
            year,
        ),
        r"\b0?{}{}\s+{}\s+{}\b".format(
            day,
            suffix,
            month_pattern,
            year,
        ),
    )
    return any(re.search(pattern, source_text, re.IGNORECASE) for pattern in patterns)


def _is_opposite_party_only(source_text: str, party: str) -> bool:
    opposite = "buyer" if party == "seller" else "seller"
    return bool(
        PARTY_LABEL_PATTERNS[opposite].search(source_text)
        and not PARTY_LABEL_PATTERNS[party].search(source_text)
    )


def _source_supports_installments(
    source_text: str,
    extraction: TradeDocumentExtraction,
) -> bool:
    if not extraction.installments:
        return False
    return any(
        _source_contains_amount(source_text, item.amount)
        and _source_contains_date(source_text, item.due_date)
        and (
            not item.currency
            or _source_contains_currency(source_text, item.currency)
        )
        for item in extraction.installments
    )


def _source_supports_field(
    evidence: FieldEvidence,
    extraction: TradeDocumentExtraction,
) -> bool:
    """Check that a quoted source actually supports its canonical field."""

    field = evidence.field
    source_text = evidence.source_text
    if field == "seller_name":
        return (
            _contains_value(source_text, extraction.seller_name)
            and not _is_opposite_party_only(source_text, "seller")
        )
    if field == "buyer_name":
        return (
            _contains_value(source_text, extraction.buyer_name)
            and not _is_opposite_party_only(source_text, "buyer")
        )
    if field == "seller_country":
        return country_alias_matches_text(
            source_text,
            extraction.seller_country or "",
        ) and not _is_opposite_party_only(source_text, "seller")
    if field == "buyer_country":
        return country_alias_matches_text(
            source_text,
            extraction.buyer_country or "",
        ) and not _is_opposite_party_only(source_text, "buyer")
    if field == "currency":
        return _source_contains_currency(source_text, extraction.currency)
    if field == "grand_total":
        return (
            _source_contains_amount(source_text, extraction.grand_total)
            and bool(AMOUNT_CONTEXT_RE.search(source_text))
            and _source_currency_is_consistent(
                source_text,
                extraction.currency,
                require_presence=False,
            )
        )
    if field == "amount_due":
        return (
            _source_contains_amount(source_text, extraction.amount_due)
            and bool(AMOUNT_CONTEXT_RE.search(source_text))
            and _source_currency_is_consistent(
                source_text,
                extraction.currency,
                require_presence=False,
            )
        )
    if field == "explicit_due_date":
        return (
            _source_contains_date(source_text, extraction.explicit_due_date)
            and _due_date_context_rank(source_text) is not None
        )
    if field in {
        "issue_date",
        "contract_date",
        "shipment_date",
    }:
        return (
            _source_contains_date(source_text, getattr(extraction, field))
            and bool(DATE_CONTEXT_PATTERNS[field].search(source_text))
        )
    if field == "payment_terms":
        return _contains_value(source_text, extraction.payment_terms)
    if field == "installments":
        return _source_supports_installments(source_text, extraction)
    return True


def verify_core_evidence_against_source(
    extraction: TradeDocumentExtraction,
    source_page_texts: Optional[Sequence[str]] = None,
) -> Tuple[TradeDocumentExtraction, List[NormalizationAuditEntry]]:
    """Keep only source-verified core evidence for text-backed documents.

    ``source_page_texts=None`` means the caller has no independent source text
    (for example an offline fixture). An explicit empty sequence means a live
    image/scanned document has no text layer, so core evidence must remain
    unverified until the reviewer records an explicit override.
    """

    if source_page_texts is None:
        return extraction, []

    pages = _compact_lines(source_page_texts)
    has_source_text = any(lines for lines in pages.values())
    verified: List[FieldEvidence] = []
    audit: List[NormalizationAuditEntry] = []

    for evidence in extraction.evidence:
        if (
            evidence.field not in SEMANTIC_EVIDENCE_FIELDS
            or evidence.extraction_type == "INFERRED"
        ):
            verified.append(evidence)
            continue

        if not has_source_text:
            audit.append(
                NormalizationAuditEntry(
                    field=evidence.field,
                    raw_value=None,
                    normalized_value=None,
                    status="EVIDENCE_UNVERIFIABLE",
                    message=(
                        "독립 텍스트 원문이 없어 {} evidence를 자동 "
                        "대조할 수 없습니다.".format(evidence.field)
                    ),
                )
            )
            continue

        source_page = _evidence_source_page(evidence, pages)
        if source_page is None:
            audit.append(
                NormalizationAuditEntry(
                    field=evidence.field,
                    raw_value=None,
                    normalized_value=None,
                    status="EVIDENCE_NOT_IN_SOURCE",
                    message=(
                        "{} evidence 인용문을 업로드 원문에서 찾지 "
                        "못했습니다.".format(evidence.field)
                    ),
                )
            )
            continue

        if not _source_supports_field(evidence, extraction):
            audit.append(
                NormalizationAuditEntry(
                    field=evidence.field,
                    raw_value=None,
                    normalized_value=None,
                    status="EVIDENCE_VALUE_MISMATCH",
                    message=(
                        "{} evidence 인용문이 현재 추출값을 뒷받침하지 "
                        "않습니다.".format(evidence.field)
                    ),
                )
            )
            continue

        verified.append(
            evidence.model_copy(update={"page": source_page})
        )

    return extraction.model_copy(update={"evidence": verified}), audit


def _compact_lines(page_texts: Sequence[str]) -> Dict[int, List[str]]:
    pages: Dict[int, List[str]] = {}
    for page_number, page_text in enumerate(page_texts, start=1):
        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in page_text.splitlines()
            if line.strip()
        ]
        pages[page_number] = lines
    return pages


def _has_explicit_field_evidence(
    extraction: TradeDocumentExtraction,
    field: str,
    value: Optional[str] = None,
    country_code: Optional[str] = None,
    pages: Optional[Dict[int, List[str]]] = None,
) -> bool:
    return any(
        item.field == field
        and item.extraction_type != "INFERRED"
        and item.source_text.strip()
        and (
            country_alias_matches_text(item.source_text, country_code)
            if country_code
            else _contains_value(item.source_text, value)
            if value
            else True
        )
        and (
            pages is None
            or _evidence_source_page(item, pages) is not None
        )
        for item in extraction.evidence
    )


def _country_code(value: Optional[str], field: str) -> Optional[str]:
    normalized, unused_audit = normalize_country_name(value, field)
    if (
        normalized
        and len(normalized) == 2
        and normalized.isalpha()
        and normalized == normalized.upper()
    ):
        return normalized
    return None


def _find_existing_evidence(
    extraction: TradeDocumentExtraction,
    *,
    party: str,
    field: str,
    value: Optional[str],
    country_code: Optional[str] = None,
    pages: Optional[Dict[int, List[str]]] = None,
) -> Optional[Tuple[Optional[int], str, str]]:
    opposite = "buyer" if party == "seller" else "seller"
    preferred_fields = {
        party,
        "{}_party".format(party),
        "{}_details".format(party),
        "{}_name".format(party),
        "{}_country".format(party),
        field,
    }
    ranked: List[Tuple[int, FieldEvidence, Optional[int]]] = []
    for item in extraction.evidence:
        if item.extraction_type == "INFERRED" or not item.source_text.strip():
            continue
        if item.field not in preferred_fields:
            continue
        if item.field.startswith(opposite):
            continue
        matches = (
            country_alias_matches_text(item.source_text, country_code)
            if country_code
            else _contains_value(item.source_text, value)
        )
        if not matches:
            continue
        source_page = _evidence_source_page(item, pages)
        if pages is not None and source_page is None:
            continue
        ranked.append((0, item, source_page))
    if not ranked:
        return None
    ranked.sort(key=lambda pair: pair[0])
    unused_rank, selected, source_page = ranked[0]
    return source_page or selected.page, selected.source_text, selected.field


def _evidence_source_page(
    evidence: FieldEvidence,
    pages: Optional[Dict[int, List[str]]],
) -> Optional[int]:
    """Return the uploaded text-PDF page containing an evidence quote.

    When a source text layer is available, generated evidence must be traced
    back to that text, rather than merely trusting a model-returned quote.
    """

    if pages is None:
        return evidence.page
    page_numbers: List[int] = []
    if evidence.page in pages:
        page_numbers.append(evidence.page)
    page_numbers.extend(
        number for number in pages if number not in page_numbers
    )
    for page_number in page_numbers:
        page_text = " ".join(pages[page_number])
        if _contains_exact_quote(page_text, evidence.source_text):
            return page_number
    return None


def _find_name_anchor(
    pages: Dict[int, List[str]],
    value: Optional[str],
) -> Optional[Tuple[int, int, str]]:
    if not value:
        return None
    matches: List[Tuple[int, int, int, str]] = []
    for page_number, lines in pages.items():
        for line_index, line in enumerate(lines):
            if _contains_value(line, value):
                has_party_label = bool(
                    re.search(
                        r"\blegal\s+name\b|\bseller\b|\bbuyer\b|법인명|"
                        r"판매자|구매자",
                        line,
                        re.IGNORECASE,
                    )
                )
                matches.append(
                    (
                        0 if has_party_label else 1,
                        page_number,
                        line_index,
                        line,
                    )
                )
    if not matches:
        return None
    matches.sort(key=lambda item: (item[0], item[1], item[2]))
    unused_rank, page_number, line_index, line = matches[0]
    return page_number, line_index, line


def _country_near_name(
    pages: Dict[int, List[str]],
    anchor: Optional[Tuple[int, int, str]],
    country_code: Optional[str],
    other_party_name: Optional[str],
) -> Optional[Tuple[int, str]]:
    if anchor is None or not country_code:
        return None
    page_number, anchor_index, unused_line = anchor
    lines = pages.get(page_number, [])

    # Prefer the same line or following lines in the party block. Stop before
    # the other party's name so a seller country cannot be attached to buyer.
    last_index = min(len(lines), anchor_index + PARTY_WINDOW_LINES + 1)
    for line in lines[anchor_index:last_index]:
        if (
            line != unused_line
            and other_party_name
            and _contains_value(line, other_party_name)
        ):
            break
        if country_alias_matches_text(line, country_code):
            return page_number, line

    # Some documents place Country immediately above Legal Name. Search a
    # small backward window, again stopping at the other party's anchor.
    first_index = max(0, anchor_index - PARTY_WINDOW_LINES)
    for line in reversed(lines[first_index:anchor_index]):
        if other_party_name and _contains_value(line, other_party_name):
            break
        if country_alias_matches_text(line, country_code):
            return page_number, line
    return None


def _unique_country_line(
    pages: Dict[int, List[str]],
    country_code: Optional[str],
) -> Optional[Tuple[int, str]]:
    if not country_code:
        return None
    matches: List[Tuple[int, str]] = []
    for page_number, lines in pages.items():
        for line in lines:
            if country_alias_matches_text(line, country_code):
                matches.append((page_number, line))
    if not matches:
        return None
    country_label_matches = [
        match
        for match in matches
        if re.search(r"\bcountry\b|국가", match[1], re.IGNORECASE)
    ]
    if len(country_label_matches) == 1:
        return country_label_matches[0]
    if len(matches) == 1:
        return matches[0]
    return None


def _generated_evidence(
    *,
    field: str,
    page: Optional[int],
    source_text: str,
    source_kind: str,
) -> FieldEvidence:
    return FieldEvidence(
        field=field,
        page=page,
        source_text=source_text,
        extraction_type="EXPLICIT",
        confidence_reason=(
            "{}의 실제 원문에서 추출값과 일치하는 문구를 결정론적으로 "
            "대조해 evidence를 연결했습니다.".format(source_kind)
        ),
    )


def _source_lines(
    source_page_texts: Sequence[str],
) -> List[Tuple[int, str]]:
    lines: List[Tuple[int, str]] = []
    for page_number, page_text in enumerate(source_page_texts, start=1):
        for source_line in page_text.splitlines():
            line = source_line.strip()
            if line:
                lines.append((page_number, line))
    return lines


def _has_verified_field_evidence(
    extraction: TradeDocumentExtraction,
    field: str,
) -> bool:
    return any(
        item.field == field
        and item.extraction_type != "INFERRED"
        and item.source_text.strip()
        for item in extraction.evidence
    )


def _discarded_evidence_reason(
    field: str,
    evidence_audit: Sequence[NormalizationAuditEntry],
) -> str:
    priority = {
        "EVIDENCE_VALUE_MISMATCH": 3,
        "EVIDENCE_NOT_IN_SOURCE": 2,
        "EVIDENCE_UNVERIFIABLE": 1,
    }
    statuses = [
        item.status
        for item in evidence_audit
        if item.field == field and item.status in priority
    ]
    if not statuses:
        return "MISSING_MODEL_EVIDENCE"
    return max(statuses, key=lambda item: priority[item])


def _installment_total_matches_amount_due(
    extraction: TradeDocumentExtraction,
) -> bool:
    if not extraction.installments or not extraction.amount_due:
        return False
    try:
        amount_due = Decimal(extraction.amount_due)
        amounts = [
            Decimal(item.amount)
            for item in extraction.installments
            if item.amount is not None
        ]
    except (InvalidOperation, ValueError):
        return False
    return (
        len(amounts) == len(extraction.installments)
        and sum(amounts, Decimal("0")) == amount_due
    )


def _amount_context_rank(
    line: str,
    extraction: TradeDocumentExtraction,
) -> Optional[Tuple[int, str]]:
    explicit_due = bool(EXPLICIT_AMOUNT_DUE_CONTEXT_RE.search(line))
    contract_total = bool(CONTRACT_TOTAL_CONTEXT_RE.search(line))
    invoice_total = bool(INVOICE_TOTAL_CONTEXT_RE.search(line))
    order_total = bool(ORDER_TOTAL_CONTEXT_RE.search(line))

    if extraction.document_type == "SALES_CONTRACT":
        if _installment_total_matches_amount_due(extraction):
            if contract_total:
                return 0, "SALES_CONTRACT_AGGREGATE"
            if explicit_due:
                return 1, "EXPLICIT_BALANCE_OR_AMOUNT_DUE"
            return None
        if explicit_due:
            return 0, "EXPLICIT_BALANCE_OR_AMOUNT_DUE"
        if (
            contract_total
            and extraction.grand_total == extraction.amount_due
        ):
            return 1, "SALES_CONTRACT_TOTAL_WITHOUT_SCHEDULE"
        return None

    if extraction.document_type == "COMMERCIAL_INVOICE":
        if explicit_due:
            return 0, "INVOICE_EXPLICIT_BALANCE"
        if invoice_total and extraction.grand_total == extraction.amount_due:
            return 1, "INVOICE_TOTAL_EQUALS_AMOUNT_DUE"
        return None

    if extraction.document_type == "PURCHASE_ORDER":
        if explicit_due:
            return 0, "ORDER_EXPLICIT_AMOUNT_DUE"
        if order_total and extraction.grand_total == extraction.amount_due:
            return 1, "ORDER_TOTAL_EQUALS_AMOUNT_DUE"
        return None

    if explicit_due:
        return 0, "EXPLICIT_BALANCE_OR_AMOUNT_DUE"
    return None


def _amount_recovery_candidate(
    extraction: TradeDocumentExtraction,
    lines: Sequence[Tuple[int, str]],
) -> Tuple[Optional[Tuple[int, str]], Optional[str]]:
    if not extraction.amount_due:
        return None, None
    try:
        expected = Decimal(extraction.amount_due)
    except (InvalidOperation, ValueError):
        return None, None

    candidates: List[
        Tuple[int, str, int, str, List[Decimal], bool]
    ] = []
    for page, line in lines:
        context = _amount_context_rank(line, extraction)
        if context is None:
            continue
        rank, semantic = context
        values = _amount_values(line)
        currency_matches = _source_currency_is_consistent(
            line,
            extraction.currency,
            require_presence=True,
        )
        if not currency_matches and expected not in values:
            continue
        candidates.append(
            (rank, semantic, page, line, values, currency_matches)
        )
    if not candidates:
        return None, None

    best_rank = min(item[0] for item in candidates)
    strongest = [item for item in candidates if item[0] == best_rank]
    if len(strongest) != 1:
        return None, "MULTIPLE_STRONG_AMOUNT_CANDIDATES"

    matching = [
        item
        for item in candidates
        if item[5] and item[4] == [expected]
    ]
    if len({item[1] for item in matching}) > 1:
        return None, "SAME_AMOUNT_IN_MULTIPLE_SEMANTIC_FIELDS"

    selected = strongest[0]
    if not selected[5]:
        return None, "AMOUNT_CURRENCY_CONFLICT_OR_MISSING"
    if selected[4] != [expected]:
        return None, "AMOUNT_CANDIDATE_VALUE_MISMATCH"
    return (selected[2], selected[3]), None


def _due_date_context_rank(line: str) -> Optional[int]:
    if STRONG_DUE_DATE_CONTEXT_RE.search(line):
        return 0
    if PAYMENT_DUE_ACTION_CONTEXT_RE.search(line):
        return 1
    if (
        WEAK_DUE_DATE_CONTEXT_RE.search(line)
        and re.search(r"\bpayment(?:\s+terms)?\b|지급|결제", line, re.IGNORECASE)
    ):
        return 2
    if NON_DUE_DATE_CONTEXT_RE.search(line):
        return None
    return None


def _due_date_recovery_candidate(
    extraction: TradeDocumentExtraction,
    lines: Sequence[Tuple[int, str]],
) -> Tuple[Optional[Tuple[int, str]], Optional[str]]:
    if not extraction.explicit_due_date:
        return None, None
    try:
        expected = date.fromisoformat(extraction.explicit_due_date)
    except ValueError:
        return None, None

    candidates: List[Tuple[int, int, str, List[date]]] = []
    for page, line in lines:
        rank = _due_date_context_rank(line)
        if rank is None:
            continue
        values = _date_values(line)
        if values:
            candidates.append((rank, page, line, values))
    if not candidates:
        return None, None

    best_rank = min(item[0] for item in candidates)
    strongest = [item for item in candidates if item[0] == best_rank]
    if len(strongest) != 1:
        return None, "MULTIPLE_STRONG_DUE_DATE_CANDIDATES"

    selected = strongest[0]
    if selected[3] != [expected]:
        return None, "DUE_DATE_CANDIDATE_VALUE_MISMATCH"
    return (selected[1], selected[2]), None


def _recovery_failure_audit(
    *,
    field: str,
    canonical_value: Optional[str],
    reason: str,
    discarded_reason: str,
) -> NormalizationAuditEntry:
    return NormalizationAuditEntry(
        field=field,
        raw_value=discarded_reason,
        normalized_value=canonical_value,
        status="EVIDENCE_RECOVERY_AMBIGUOUS",
        message=(
            "recovery_method=UNIQUE_SEMANTIC_TEXT_LINE; "
            "discarded_model_evidence={}; recovery_blocked={}; "
            "모호하거나 불일치한 원문 후보를 임의 선택하지 않았습니다.".format(
                discarded_reason,
                reason,
            )
        ),
    )


def recover_source_grounded_evidence(
    extraction: TradeDocumentExtraction,
    *,
    source_page_texts: Optional[Sequence[str]],
    evidence_audit: Sequence[NormalizationAuditEntry],
) -> Tuple[TradeDocumentExtraction, List[NormalizationAuditEntry]]:
    """Recover amount/due evidence only from a unique text-PDF source line."""

    if source_page_texts is None or not any(
        page_text.strip() for page_text in source_page_texts
    ):
        return extraction, []

    lines = _source_lines(source_page_texts)
    recovered: List[FieldEvidence] = []
    audit: List[NormalizationAuditEntry] = []
    finders = {
        "amount_due": _amount_recovery_candidate,
        "explicit_due_date": _due_date_recovery_candidate,
    }

    for field, finder in finders.items():
        if not getattr(extraction, field):
            continue
        if _has_verified_field_evidence(
            extraction.model_copy(
                update={"evidence": list(extraction.evidence) + recovered}
            ),
            field,
        ):
            continue
        discarded_reason = _discarded_evidence_reason(
            field,
            evidence_audit,
        )
        candidate, blocked_reason = finder(extraction, lines)
        if candidate is None:
            if blocked_reason:
                audit.append(
                    _recovery_failure_audit(
                        field=field,
                        canonical_value=getattr(extraction, field),
                        reason=blocked_reason,
                        discarded_reason=discarded_reason,
                    )
                )
            continue

        page, source_text = candidate
        canonical_value = getattr(extraction, field)
        recovery_method = "UNIQUE_SEMANTIC_TEXT_LINE"
        recovered.append(
            FieldEvidence(
                field=field,
                page=page,
                source_text=source_text,
                extraction_type="EXPLICIT",
                confidence_reason=(
                    "recovery_method={}; parsed_value={}; "
                    "discarded_model_evidence={}; 실제 PDF page {} 원문을 "
                    "결정론적으로 파싱해 canonical value와 일치함을 "
                    "확인했습니다.".format(
                        recovery_method,
                        canonical_value,
                        discarded_reason,
                        page,
                    )
                ),
            )
        )
        audit.append(
            NormalizationAuditEntry(
                field=field,
                raw_value=discarded_reason,
                normalized_value=canonical_value,
                status="EVIDENCE_RECOVERED_FROM_TEXT",
                message=(
                    "recovery_method={}; page={}; parsed_value={}; "
                    "discarded_model_evidence={}; 원문 quote를 그대로 "
                    "보존했습니다.".format(
                        recovery_method,
                        page,
                        canonical_value,
                        discarded_reason,
                    )
                ),
            )
        )

    if not recovered:
        return extraction, audit
    return extraction.model_copy(
        update={"evidence": list(extraction.evidence) + recovered}
    ), audit


def augment_party_evidence(
    extraction: TradeDocumentExtraction,
    source_page_texts: Optional[Sequence[str]] = None,
) -> Tuple[TradeDocumentExtraction, List[NormalizationAuditEntry]]:
    """Backfill party evidence only from verifiable source text.

    The function never constructs a source quote from extracted values. It may
    reuse a model-returned evidence quote that contains the exact party value,
    or, for text PDFs, a short line read directly from the uploaded page.
    """

    pages = _compact_lines(source_page_texts or [])
    source_pages = pages if source_page_texts is not None else None
    anchors = {
        party: _find_name_anchor(
            pages,
            getattr(extraction, "{}_name".format(party)),
        )
        for party in PARTIES
    }
    generated: List[FieldEvidence] = []
    audit: List[NormalizationAuditEntry] = []

    for party in PARTIES:
        opposite = "buyer" if party == "seller" else "seller"
        name_field = "{}_name".format(party)
        country_field = "{}_country".format(party)
        name_value = getattr(extraction, name_field)
        country_value = getattr(extraction, country_field)
        country_code = _country_code(country_value, country_field)

        if name_value and not _has_explicit_field_evidence(
            extraction.model_copy(
                update={"evidence": list(extraction.evidence) + generated}
            ),
            name_field,
            value=name_value,
            pages=source_pages,
        ):
            existing = _find_existing_evidence(
                extraction,
                party=party,
                field=name_field,
                value=name_value,
                pages=source_pages,
            )
            if existing is not None:
                page, source_text, source_field = existing
                source_kind = "{} evidence".format(source_field)
            elif anchors[party] is not None:
                page, unused_index, source_text = anchors[party]
                source_kind = "PDF page {}".format(page)
            else:
                page = None
                source_text = ""
                source_kind = ""
            if source_text:
                generated.append(
                    _generated_evidence(
                        field=name_field,
                        page=page,
                        source_text=source_text,
                        source_kind=source_kind,
                    )
                )
                audit.append(
                    NormalizationAuditEntry(
                        field=name_field,
                        raw_value=name_value,
                        normalized_value=name_value,
                        status="EVIDENCE_LINKED",
                        message=(
                            "{}의 실제 원문과 추출값을 대조해 {} evidence를 "
                            "연결했습니다.".format(source_kind, name_field)
                        ),
                    )
                )

        current = extraction.model_copy(
            update={"evidence": list(extraction.evidence) + generated}
        )
        if country_code and not _has_explicit_field_evidence(
            current,
            country_field,
            country_code=country_code,
            pages=source_pages,
        ):
            existing = _find_existing_evidence(
                extraction,
                party=party,
                field=country_field,
                value=country_code,
                country_code=country_code,
                pages=source_pages,
            )
            if existing is not None:
                page, source_text, source_field = existing
                source_kind = "{} evidence".format(source_field)
            else:
                nearby = _country_near_name(
                    pages,
                    anchors[party],
                    country_code,
                    getattr(extraction, "{}_name".format(opposite)),
                )
                if nearby is None and (
                    extraction.seller_country != extraction.buyer_country
                ):
                    nearby = _unique_country_line(pages, country_code)
                if nearby is not None:
                    page, source_text = nearby
                    source_kind = "PDF page {}".format(page)
                else:
                    page = None
                    source_text = ""
                    source_kind = ""
            if source_text:
                generated.append(
                    _generated_evidence(
                        field=country_field,
                        page=page,
                        source_text=source_text,
                        source_kind=source_kind,
                    )
                )
                audit.append(
                    NormalizationAuditEntry(
                        field=country_field,
                        raw_value=country_value,
                        normalized_value=country_code,
                        status="EVIDENCE_LINKED",
                        message=(
                            "{}의 실제 원문과 정규화 국가 코드를 대조해 {} "
                            "evidence를 연결했습니다.".format(
                                source_kind,
                                country_field,
                            )
                        ),
                    )
                )

    if not generated:
        return extraction, []
    return extraction.model_copy(
        update={"evidence": list(extraction.evidence) + generated}
    ), audit
