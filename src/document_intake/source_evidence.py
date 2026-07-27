import io
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Sequence, Tuple

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
        r"\bsettlement\s+date\b|결제일|지급일|납기일",
        re.IGNORECASE,
    ),
}
PARTY_LABEL_PATTERNS = {
    "seller": re.compile(r"\bseller\b|판매자", re.IGNORECASE),
    "buyer": re.compile(r"\bbuyer\b|구매자", re.IGNORECASE),
}


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
        )
    if field == "amount_due":
        return (
            _source_contains_amount(source_text, extraction.amount_due)
            and bool(AMOUNT_CONTEXT_RE.search(source_text))
        )
    if field in {
        "issue_date",
        "contract_date",
        "shipment_date",
        "explicit_due_date",
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
        if _contains_value(page_text, evidence.source_text):
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
