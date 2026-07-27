import io
import re
import unicodedata
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
