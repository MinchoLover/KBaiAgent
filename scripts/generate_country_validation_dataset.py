#!/usr/bin/env python3
"""Generate the isolated US/Brazil synthetic validation dataset.

The documents produced by this script are synthetic, test-only artifacts.
They contain no real companies, people, addresses, accounts, identifiers,
logos, signatures, or seals.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prompt import get_prompt_version  # noqa: E402
from schemas import TradeDocumentExtraction  # noqa: E402
from validators import apply_deterministic_review_state  # noqa: E402


DATASET = ROOT / "dataset" / "country_validation"
DOCUMENTS = DATASET / "documents"
LABELS = DATASET / "labels"
FIXTURE_PREDICTIONS = DATASET / "predictions" / "fixture"
MANIFEST = DATASET / "manifest.jsonl"

NOTICE_EN = "TEST DOCUMENT - NO LEGAL EFFECT"
NOTICE_KO = "합성 테스트 문서 - 법적 효력 없음"
NOTICE_PT = "DOCUMENTO SINTÉTICO - SEM EFEITO LEGAL"
FIXED_SEED = 20260729


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf"
        ),
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _notice_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
            if bold
            else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
        ),
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return _font(size, bold=bold)


def _evidence(
    field: str,
    source_text: str,
    reason: str,
    extraction_type: str = "EXPLICIT",
) -> Dict[str, Any]:
    return {
        "field": field,
        "page": 1,
        "source_text": source_text,
        "extraction_type": extraction_type,
        "confidence_reason": reason,
    }


def _base_label(**updates: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "document_type": "COMMERCIAL_INVOICE",
        "document_number": None,
        "seller_name": None,
        "seller_country": None,
        "buyer_name": None,
        "buyer_country": None,
        "company_role": "BUYER",
        "trade_type": "IMPORT",
        "currency": None,
        "grand_total": None,
        "amount_due": None,
        "issue_date": None,
        "contract_date": None,
        "shipment_date": None,
        "explicit_due_date": None,
        "derived_due_date": None,
        "payment_terms": None,
        "incoterm": None,
        "installments": [],
        "evidence": [],
        "warnings": [],
        "missing_required_fields": [],
        "needs_human_review": True,
    }
    data.update(updates)
    return data


def _notice_evidence(country: str) -> List[Dict[str, Any]]:
    items = [
        _evidence(
            "document_notice",
            NOTICE_EN,
            "The English test-only notice is printed at the top.",
        ),
        _evidence(
            "document_notice",
            NOTICE_KO,
            "The Korean test-only notice is printed at the top.",
        ),
    ]
    if country == "BR":
        items.append(
            _evidence(
                "document_notice",
                NOTICE_PT,
                "The Portuguese synthetic-document notice is printed at the top.",
            )
        )
    return items


def _party_lines(
    seller_name: str,
    seller_country_name: str,
    seller_country: str,
    buyer_name: str,
    buyer_country_name: str,
    buyer_country: str,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    seller_line = "Seller: {}".format(seller_name)
    seller_country_line = "Seller Country: {} ({})".format(
        seller_country_name,
        seller_country,
    )
    buyer_line = "Buyer: {}".format(buyer_name)
    buyer_country_line = "Buyer Country: {} ({})".format(
        buyer_country_name,
        buyer_country,
    )
    lines = [
        seller_line,
        seller_country_line,
        buyer_line,
        buyer_country_line,
    ]
    evidence = [
        _evidence(
            "seller_name",
            seller_line,
            "The seller name is explicitly labelled.",
        ),
        _evidence(
            "seller_country",
            seller_country_line,
            "The seller country and ISO alpha-2 code are explicit.",
        ),
        _evidence(
            "buyer_name",
            buyer_line,
            "The buyer name is explicitly labelled.",
        ),
        _evidence(
            "buyer_country",
            buyer_country_line,
            "The buyer country and ISO alpha-2 code are explicit.",
        ),
    ]
    return lines, evidence


def _case(
    *,
    case_id: str,
    title: str,
    extension: str,
    country: str,
    trade_type: str,
    category: str,
    difficulty: str,
    lines: List[str],
    label: Dict[str, Any],
    notes: str,
    expected_validation_status: str,
    expected_review_reasons: List[str],
    effect: str,
    mask_line_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "case_id": case_id,
        "title": title,
        "extension": extension,
        "country": country,
        "trade_type": trade_type,
        "category": category,
        "difficulty": difficulty,
        "lines": lines,
        "label": label,
        "notes": notes,
        "expected_validation_status": expected_validation_status,
        "expected_review_reasons": expected_review_reasons,
        "effect": effect,
        "mask_line_prefix": mask_line_prefix,
    }


def _cases() -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []

    seller = "Liberty Lantern Test Equipment LLC"
    buyer = "Blue Hanul Synthetic Imports Ltd."
    party_lines, party_evidence = _party_lines(
        seller,
        "United States",
        "US",
        buyer,
        "Republic of Korea",
        "KR",
    )
    contract_line = "Contract Date: 2026-08-05"
    currency_line = "Contract Currency: USD"
    total_line = "Total Amount / Amount Due: USD 120000.00"
    terms_line = "Payment Terms: Split payment - 30% and 70%"
    installment_1_line = (
        "Installment 1: 30% | USD 36000.00 | Due 2026-08-20"
    )
    installment_2_line = (
        "Installment 2: 70% | USD 84000.00 | Due 2026-10-20"
    )
    label = _base_label(
        document_type="SALES_CONTRACT",
        document_number="US-IMP-SPLIT-001",
        seller_name=seller,
        seller_country="US",
        buyer_name=buyer,
        buyer_country="KR",
        company_role="BUYER",
        trade_type="IMPORT",
        currency="USD",
        grand_total="120000.00",
        amount_due="120000.00",
        contract_date="2026-08-05",
        payment_terms="Split payment - 30% and 70%",
        installments=[
            {
                "sequence": 1,
                "amount": "36000.00",
                "currency": "USD",
                "due_date": "2026-08-20",
                "condition": "30% scheduled first payment",
            },
            {
                "sequence": 2,
                "amount": "84000.00",
                "currency": "USD",
                "due_date": "2026-10-20",
                "condition": "70% scheduled final payment",
            },
        ],
        evidence=(
            _notice_evidence("US")
            + party_evidence
            + [
                _evidence(
                    "contract_date",
                    contract_line,
                    "The contract date is explicit.",
                ),
                _evidence(
                    "currency",
                    currency_line,
                    "The contract currency is explicit.",
                ),
                _evidence(
                    "grand_total",
                    total_line,
                    "The total amount is explicit.",
                ),
                _evidence(
                    "amount_due",
                    total_line,
                    "The full contract amount remains due.",
                ),
                _evidence(
                    "payment_terms",
                    terms_line,
                    "The split-payment terms are explicit.",
                ),
                _evidence(
                    "installments",
                    installment_1_line,
                    "The first installment amount and date are explicit.",
                ),
                _evidence(
                    "installments",
                    installment_2_line,
                    "The second installment amount and date are explicit.",
                ),
            ]
        ),
    )
    cases.append(
        _case(
            case_id="us_import_split_scan_001",
            title="SYNTHETIC SALES CONTRACT",
            extension=".pdf",
            country="US",
            trade_type="IMPORT",
            category="split_payment",
            difficulty="MEDIUM",
            lines=[
                "Document No: US-IMP-SPLIT-001",
                "## PARTIES",
            ]
            + party_lines
            + [
                "## CONTRACT DETAILS",
                contract_line,
                currency_line,
                total_line,
                terms_line,
                "## PAYMENT SCHEDULE",
                installment_1_line,
                installment_2_line,
                "Control Check: USD 36000.00 + USD 84000.00 = USD 120000.00",
            ],
            label=label,
            notes=(
                "Image-only scanned US import contract with an exact 30/70 "
                "payment schedule."
            ),
            expected_validation_status="CONDITIONAL_REVIEW",
            expected_review_reasons=[
                "SCANNED_IMAGE_REQUIRES_OCR_OR_USER_CONFIRMATION"
            ],
            effect="scan",
        )
    )

    seller = "Samba Quartz Synthetic Machines Ltda."
    buyer = "Mirae Sandbox Materials Ltd."
    party_lines, party_evidence = _party_lines(
        seller,
        "Brazil",
        "BR",
        buyer,
        "Republic of Korea",
        "KR",
    )
    contract_line = "Contract Date: 2026-08-07"
    currency_line = "Contract Currency: USD"
    total_line = "Total Amount / Amount Due: USD 84000.00"
    terms_line = "Payment Terms: 20% advance payment; 80% remaining balance"
    installment_1_line = (
        "Installment 1: 20% advance payment | USD 16800.00 | 2026-08-14"
    )
    installment_2_line = (
        "Installment 2: 80% remaining balance | USD 67200.00 | 2026-11-14"
    )
    label = _base_label(
        document_type="SALES_CONTRACT",
        document_number="BR-IMP-ADV-002",
        seller_name=seller,
        seller_country="BR",
        buyer_name=buyer,
        buyer_country="KR",
        company_role="BUYER",
        trade_type="IMPORT",
        currency="USD",
        grand_total="84000.00",
        amount_due="84000.00",
        contract_date="2026-08-07",
        payment_terms="20% advance payment; 80% remaining balance",
        installments=[
            {
                "sequence": 1,
                "amount": "16800.00",
                "currency": "USD",
                "due_date": "2026-08-14",
                "condition": "20% advance payment",
            },
            {
                "sequence": 2,
                "amount": "67200.00",
                "currency": "USD",
                "due_date": "2026-11-14",
                "condition": "80% remaining balance",
            },
        ],
        evidence=(
            _notice_evidence("BR")
            + party_evidence
            + [
                _evidence(
                    "contract_date",
                    contract_line,
                    "The contract date is explicit.",
                ),
                _evidence(
                    "currency",
                    currency_line,
                    "The contract currency is explicit.",
                ),
                _evidence(
                    "grand_total",
                    total_line,
                    "The total amount is explicit.",
                ),
                _evidence(
                    "amount_due",
                    total_line,
                    "The full amount remains due.",
                ),
                _evidence(
                    "payment_terms",
                    terms_line,
                    "Advance payment and remaining balance are distinguished.",
                ),
                _evidence(
                    "installments",
                    installment_1_line,
                    "The advance installment is explicit.",
                ),
                _evidence(
                    "installments",
                    installment_2_line,
                    "The remaining-balance installment is explicit.",
                ),
            ]
        ),
    )
    cases.append(
        _case(
            case_id="br_import_advance_photo_002",
            title="SYNTHETIC IMPORT CONTRACT",
            extension=".jpg",
            country="BR",
            trade_type="IMPORT",
            category="advance_payment",
            difficulty="MEDIUM",
            lines=[
                "Document No: BR-IMP-ADV-002",
                "## PARTIES",
            ]
            + party_lines
            + [
                "## CONTRACT DETAILS",
                contract_line,
                currency_line,
                total_line,
                terms_line,
                "## PAYMENT SCHEDULE",
                installment_1_line,
                installment_2_line,
            ],
            label=label,
            notes=(
                "Brazil import contract photo with mild perspective, shadow, "
                "and JPEG compression."
            ),
            expected_validation_status="CONDITIONAL_REVIEW",
            expected_review_reasons=[
                "PHOTO_REQUIRES_OCR_OR_USER_CONFIRMATION"
            ],
            effect="photo",
        )
    )

    seller = "Dawn Peninsula Synthetic Electronics Ltd."
    buyer = "Prairie Comet Test Distribution LLC"
    party_lines, party_evidence = _party_lines(
        seller,
        "Republic of Korea",
        "KR",
        buyer,
        "United States",
        "US",
    )
    issue_line = "Invoice Date: 2026-08-03"
    currency_line = "Invoice Currency: USD"
    amount_line = "Invoice Total / Amount Due: USD 98000.00"
    terms_line = "Payment Terms: Net 60 Days"
    label = _base_label(
        document_type="COMMERCIAL_INVOICE",
        document_number="US-EXP-N60-003",
        seller_name=seller,
        seller_country="KR",
        buyer_name=buyer,
        buyer_country="US",
        company_role="SELLER",
        trade_type="EXPORT",
        currency="USD",
        grand_total="98000.00",
        amount_due="98000.00",
        issue_date="2026-08-03",
        explicit_due_date=None,
        derived_due_date=None,
        payment_terms="Net 60 Days",
        evidence=(
            _notice_evidence("US")
            + party_evidence
            + [
                _evidence(
                    "issue_date",
                    issue_line,
                    "The invoice date is explicit.",
                ),
                _evidence(
                    "currency",
                    currency_line,
                    "The invoice currency is explicit.",
                ),
                _evidence(
                    "grand_total",
                    amount_line,
                    "The invoice total is explicit.",
                ),
                _evidence(
                    "amount_due",
                    amount_line,
                    "The full invoice amount remains due.",
                ),
                _evidence(
                    "payment_terms",
                    terms_line,
                    "Net 60 is explicit; the model must not write a due date.",
                ),
                _evidence(
                    "derived_due_date",
                    terms_line,
                    "Python deterministically derives the date from this term.",
                    extraction_type="DERIVED",
                ),
            ]
        ),
    )
    cases.append(
        _case(
            case_id="us_export_net60_scan_003",
            title="SYNTHETIC COMMERCIAL INVOICE",
            extension=".pdf",
            country="US",
            trade_type="EXPORT",
            category="net_terms",
            difficulty="MEDIUM",
            lines=[
                "Invoice No: US-EXP-N60-003",
                "## PARTIES",
            ]
            + party_lines
            + [
                "## INVOICE DETAILS",
                issue_line,
                currency_line,
                amount_line,
                terms_line,
                "Due Date: Not printed; derive only by deterministic policy",
            ],
            label=label,
            notes=(
                "Image-only US export invoice. Net 60 is derivable from the "
                "issue date, but no explicit due date is printed."
            ),
            expected_validation_status="CONDITIONAL_REVIEW",
            expected_review_reasons=[
                "NET_TERM_DERIVED_BY_DETERMINISTIC_PYTHON",
                "SCANNED_IMAGE_REQUIRES_OCR_OR_USER_CONFIRMATION",
            ],
            effect="scan",
        )
    )

    seller = "Hanbit Fictional Precision Ltd."
    buyer = "Rio Nebula Synthetic Retail Ltda."
    party_lines, party_evidence = _party_lines(
        seller,
        "Republic of Korea",
        "KR",
        buyer,
        "Brazil",
        "BR",
    )
    contract_line = "Contract Date: 2026-08-08"
    currency_line = "Contract Currency: USD"
    amount_line = "Contract Amount / Amount Due: USD 150000.00"
    terms_line = "Payment Terms: Payment due 60 days after B/L date"
    label = _base_label(
        document_type="SALES_CONTRACT",
        document_number="BR-EXP-BL60-004",
        seller_name=seller,
        seller_country="KR",
        buyer_name=buyer,
        buyer_country="BR",
        company_role="SELLER",
        trade_type="EXPORT",
        currency="USD",
        grand_total="150000.00",
        amount_due="150000.00",
        contract_date="2026-08-08",
        explicit_due_date=None,
        derived_due_date=None,
        payment_terms="Payment due 60 days after B/L date",
        evidence=(
            _notice_evidence("BR")
            + party_evidence
            + [
                _evidence(
                    "contract_date",
                    contract_line,
                    "The contract date is explicit.",
                ),
                _evidence(
                    "currency",
                    currency_line,
                    "The contract currency is explicit.",
                ),
                _evidence(
                    "grand_total",
                    amount_line,
                    "The contract amount is explicit.",
                ),
                _evidence(
                    "amount_due",
                    amount_line,
                    "The full contract amount remains due.",
                ),
                _evidence(
                    "payment_terms",
                    terms_line,
                    "The B/L-based payment condition is explicit.",
                ),
            ]
        ),
    )
    cases.append(
        _case(
            case_id="br_export_bl_event_photo_004",
            title="SYNTHETIC EXPORT CONTRACT",
            extension=".jpg",
            country="BR",
            trade_type="EXPORT",
            category="event_based_terms",
            difficulty="HARD",
            lines=[
                "Document No: BR-EXP-BL60-004",
                "## PARTIES",
            ]
            + party_lines
            + [
                "## CONTRACT DETAILS",
                contract_line,
                currency_line,
                amount_line,
                terms_line,
                "B/L Date: Not available in this document",
                "Review Note: A person must supply or verify the B/L date",
            ],
            label=label,
            notes=(
                "Brazil export contract photo with an event-based term and no "
                "B/L date. The due date must remain unresolved."
            ),
            expected_validation_status="CONDITIONAL_REVIEW",
            expected_review_reasons=[
                "EVENT_BASED_DUE_DATE_UNRESOLVED",
                "USER_CONFIRMATION_REQUIRED",
            ],
            effect="photo",
        )
    )

    seller = "Copper Eagle Fictional Supply LLC"
    buyer = "Seoul Sandbox Assembly Ltd."
    party_lines, party_evidence = _party_lines(
        seller,
        "United States",
        "US",
        buyer,
        "Republic of Korea",
        "KR",
    )
    issue_line = "Invoice Date: 2026-08-09"
    currency_line = "Invoice Currency: USD"
    subtotal_line = "Subtotal: USD 100000.00"
    freight_line = "Freight: USD 5000.00"
    grand_total_line = "Grand Total: USD 105000.00"
    paid_line = "Amount Paid: USD 25000.00"
    balance_line = "Balance Due: USD 80000.00"
    due_line = "Payment Due Date: 2026-09-30"
    label = _base_label(
        document_type="COMMERCIAL_INVOICE",
        document_number="US-IMP-BAL-005",
        seller_name=seller,
        seller_country="US",
        buyer_name=buyer,
        buyer_country="KR",
        company_role="BUYER",
        trade_type="IMPORT",
        currency="USD",
        grand_total="105000.00",
        amount_due="80000.00",
        issue_date="2026-08-09",
        explicit_due_date="2026-09-30",
        payment_terms="Balance due on 2026-09-30",
        evidence=(
            _notice_evidence("US")
            + party_evidence
            + [
                _evidence(
                    "issue_date",
                    issue_line,
                    "The invoice date is explicit.",
                ),
                _evidence(
                    "currency",
                    currency_line,
                    "The invoice currency is explicit.",
                ),
                _evidence(
                    "grand_total",
                    grand_total_line,
                    "The grand total is explicitly labelled.",
                ),
                _evidence(
                    "amount_due",
                    balance_line,
                    "Balance Due, not the largest number, is the target.",
                ),
                _evidence(
                    "explicit_due_date",
                    due_line,
                    "The payment due date is explicit.",
                ),
                _evidence(
                    "payment_terms",
                    "Payment Terms: Balance due on 2026-09-30",
                    "The balance-due term is explicit.",
                ),
            ]
        ),
    )
    cases.append(
        _case(
            case_id="us_import_balance_scan_005",
            title="SYNTHETIC COMMERCIAL INVOICE",
            extension=".pdf",
            country="US",
            trade_type="IMPORT",
            category="balance_due",
            difficulty="HARD",
            lines=[
                "Invoice No: US-IMP-BAL-005",
                "## PARTIES",
            ]
            + party_lines
            + [
                "## INVOICE DETAILS",
                issue_line,
                currency_line,
                subtotal_line,
                freight_line,
                grand_total_line,
                paid_line,
                balance_line,
                due_line,
                "Payment Terms: Balance due on 2026-09-30",
            ],
            label=label,
            notes=(
                "Image-only US import invoice designed to catch selection of "
                "Grand Total instead of the lower Balance Due."
            ),
            expected_validation_status="CONDITIONAL_REVIEW",
            expected_review_reasons=[
                "SCANNED_IMAGE_REQUIRES_OCR_OR_USER_CONFIRMATION"
            ],
            effect="scan",
        )
    )

    seller = "Morning Calm Synthetic Robotics Ltd."
    buyer = "Amazonia Paper Kite Test Comercio Ltda."
    party_lines, party_evidence = _party_lines(
        seller,
        "Republic of Korea",
        "KR",
        buyer,
        "Brazil",
        "BR",
    )
    contract_line = "Contract Date: 2026-08-11"
    currency_line = "Contract Currency: USD"
    amount_line = "Contract Amount / Amount Due: USD 200000.00"
    terms_line = "Payment Terms: 15% advance; 85% after final acceptance"
    installment_1_line = (
        "Installment 1: 15% advance | USD 30000.00 | Due 2026-08-18"
    )
    installment_2_line = (
        "Installment 2: 85% | USD 170000.00 | After final acceptance"
    )
    label = _base_label(
        document_type="SALES_CONTRACT",
        document_number="BR-EXP-MIX-006",
        seller_name=seller,
        seller_country="KR",
        buyer_name=buyer,
        buyer_country="BR",
        company_role="SELLER",
        trade_type="EXPORT",
        currency="USD",
        grand_total="200000.00",
        amount_due="200000.00",
        contract_date="2026-08-11",
        explicit_due_date=None,
        derived_due_date=None,
        payment_terms="15% advance; 85% after final acceptance",
        installments=[
            {
                "sequence": 1,
                "amount": "30000.00",
                "currency": "USD",
                "due_date": "2026-08-18",
                "condition": "15% advance",
            },
            {
                "sequence": 2,
                "amount": "170000.00",
                "currency": "USD",
                "due_date": None,
                "condition": "85% after final acceptance",
            },
        ],
        evidence=(
            _notice_evidence("BR")
            + party_evidence
            + [
                _evidence(
                    "contract_date",
                    contract_line,
                    "The contract date is explicit.",
                ),
                _evidence(
                    "currency",
                    currency_line,
                    "The contract currency is explicit.",
                ),
                _evidence(
                    "grand_total",
                    amount_line,
                    "The contract amount is explicit.",
                ),
                _evidence(
                    "amount_due",
                    amount_line,
                    "The full contract amount remains due.",
                ),
                _evidence(
                    "payment_terms",
                    terms_line,
                    "The mixed split condition is explicit.",
                ),
                _evidence(
                    "installments",
                    installment_1_line,
                    "The dated advance installment is explicit.",
                ),
                _evidence(
                    "installments",
                    installment_2_line,
                    "The undated acceptance-based installment is explicit.",
                ),
            ]
        ),
    )
    cases.append(
        _case(
            case_id="br_export_mixed_split_scan_006",
            title="SYNTHETIC SALES CONTRACT",
            extension=".pdf",
            country="BR",
            trade_type="EXPORT",
            category="mixed_split_terms",
            difficulty="HARD",
            lines=[
                "Document No: BR-EXP-MIX-006",
                "## PARTIES",
            ]
            + party_lines
            + [
                "## CONTRACT DETAILS",
                contract_line,
                currency_line,
                amount_line,
                terms_line,
                "## PAYMENT SCHEDULE",
                installment_1_line,
                installment_2_line,
                "Final Acceptance Date: Not available in this document",
            ],
            label=label,
            notes=(
                "Image-only Brazil export contract. The second installment "
                "cannot be dated without final acceptance."
            ),
            expected_validation_status="BLOCKED",
            expected_review_reasons=[
                "MISSING_INSTALLMENT_DUE_DATE",
                "USER_CONFIRMATION_REQUIRED",
            ],
            effect="scan",
        )
    )

    seller = "Frontier Firefly Test Parts LLC"
    buyer = "Hangang Fictional Procurement Ltd."
    party_lines, party_evidence = _party_lines(
        seller,
        "United States",
        "US",
        buyer,
        "Republic of Korea",
        "KR",
    )
    issue_line = "Purchase Order Date: 2026-08-12"
    amount_line = "Order Total / Amount Due: 47500.00"
    due_line = "Requested Payment Date: 2026-10-01"
    label = _base_label(
        document_type="PURCHASE_ORDER",
        document_number="US-IMP-NOCUR-007",
        seller_name=seller,
        seller_country="US",
        buyer_name=buyer,
        buyer_country="KR",
        company_role="BUYER",
        trade_type="IMPORT",
        currency=None,
        grand_total="47500.00",
        amount_due="47500.00",
        issue_date="2026-08-12",
        explicit_due_date="2026-10-01",
        payment_terms="Payment requested on 2026-10-01",
        evidence=(
            _notice_evidence("US")
            + party_evidence
            + [
                _evidence(
                    "issue_date",
                    issue_line,
                    "The purchase-order date is explicit.",
                ),
                _evidence(
                    "grand_total",
                    amount_line,
                    "The order total is explicit but has no currency.",
                ),
                _evidence(
                    "amount_due",
                    amount_line,
                    "The amount due is explicit but has no currency.",
                ),
                _evidence(
                    "explicit_due_date",
                    due_line,
                    "The requested payment date is explicit.",
                ),
                _evidence(
                    "payment_terms",
                    "Payment Terms: Payment requested on 2026-10-01",
                    "The requested payment term is explicit.",
                ),
            ]
        ),
    )
    cases.append(
        _case(
            case_id="us_import_missing_currency_photo_007",
            title="SYNTHETIC PURCHASE ORDER",
            extension=".jpg",
            country="US",
            trade_type="IMPORT",
            category="missing_currency",
            difficulty="HARD",
            lines=[
                "Purchase Order No: US-IMP-NOCUR-007",
                "## PARTIES",
            ]
            + party_lines
            + [
                "## ORDER DETAILS",
                issue_line,
                amount_line,
                due_line,
                "Payment Terms: Payment requested on 2026-10-01",
                "Currency: Not stated anywhere in this purchase order",
            ],
            label=label,
            notes=(
                "US import purchase order photo with a numeric amount but no "
                "currency. USD must not be guessed."
            ),
            expected_validation_status="BLOCKED",
            expected_review_reasons=["MISSING_REQUIRED_CURRENCY"],
            effect="photo",
        )
    )

    seller = "Jeju Cloud Synthetic Instruments Ltd."
    buyer = "Capybara Cosmos Test Imports Ltda."
    party_lines, party_evidence = _party_lines(
        seller,
        "Republic of Korea",
        "KR",
        buyer,
        "Brazil",
        "BR",
    )
    issue_line = "Invoice Date: 2026-08-14"
    currency_line = "Invoice Currency: USD"
    amount_line = "Invoice Total / Amount Due: USD 73000.00"
    label = _base_label(
        document_type="COMMERCIAL_INVOICE",
        document_number="BR-EXP-BLUR-008",
        seller_name=seller,
        seller_country="KR",
        buyer_name=buyer,
        buyer_country="BR",
        company_role="SELLER",
        trade_type="EXPORT",
        currency="USD",
        grand_total="73000.00",
        amount_due="73000.00",
        issue_date="2026-08-14",
        explicit_due_date=None,
        derived_due_date=None,
        payment_terms=None,
        evidence=(
            _notice_evidence("BR")
            + party_evidence
            + [
                _evidence(
                    "issue_date",
                    issue_line,
                    "The invoice date remains readable.",
                ),
                _evidence(
                    "currency",
                    currency_line,
                    "The invoice currency remains readable.",
                ),
                _evidence(
                    "grand_total",
                    amount_line,
                    "The invoice total remains readable.",
                ),
                _evidence(
                    "amount_due",
                    amount_line,
                    "The amount due remains readable.",
                ),
            ]
        ),
    )
    cases.append(
        _case(
            case_id="br_export_occluded_due_photo_008",
            title="SYNTHETIC COMMERCIAL INVOICE",
            extension=".jpg",
            country="BR",
            trade_type="EXPORT",
            category="occluded_due_date",
            difficulty="HARD",
            lines=[
                "Invoice No: BR-EXP-BLUR-008",
                "## PARTIES",
            ]
            + party_lines
            + [
                "## INVOICE DETAILS",
                issue_line,
                currency_line,
                amount_line,
                "Payment Due: 2026-12-18",
                "Photo Note: Due-date area was damaged before ingestion",
            ],
            label=label,
            notes=(
                "Low-quality Brazil export invoice photo. Party, currency, "
                "and amount remain readable; the due-date region is occluded."
            ),
            expected_validation_status="BLOCKED",
            expected_review_reasons=[
                "PAYMENT_DUE_REGION_UNREADABLE",
                "MISSING_REQUIRED_DUE_DATE",
            ],
            effect="low_quality_photo",
            mask_line_prefix="Payment Due:",
        )
    )
    return cases


def _draw_page(spec: Dict[str, Any]) -> Image.Image:
    width, height = 1240, 1754
    page = Image.new("RGB", (width, height), (247, 244, 232))
    draw = ImageDraw.Draw(page)
    red = (184, 28, 36)
    navy = (27, 49, 77)
    ink = (28, 33, 38)
    muted = (82, 91, 99)

    draw.rectangle((28, 28, width - 28, height - 28), outline=(122, 126, 123), width=3)
    draw.rounded_rectangle(
        (55, 48, width - 55, 166 if spec["country"] == "BR" else 137),
        radius=10,
        fill=(255, 239, 239),
        outline=red,
        width=3,
    )
    draw.text((77, 61), NOTICE_EN, font=_font(31, bold=True), fill=red)
    draw.text((77, 101), NOTICE_KO, font=_notice_font(27, bold=True), fill=red)
    if spec["country"] == "BR":
        draw.text((77, 135), NOTICE_PT, font=_font(19, bold=True), fill=red)

    title_y = 205 if spec["country"] == "BR" else 180
    draw.text((76, title_y), spec["title"], font=_font(43, bold=True), fill=navy)
    draw.text(
        (78, title_y + 57),
        "SYNTHETIC RECORD / FOR QA ONLY / NOT FOR PAYMENT",
        font=_font(19, bold=True),
        fill=muted,
    )
    draw.line(
        (76, title_y + 95, width - 76, title_y + 95),
        fill=navy,
        width=4,
    )

    body_font = _font(27)
    body_bold = _font(28, bold=True)
    y = title_y + 125
    masked_box: Optional[Tuple[int, int, int, int]] = None
    row = 0
    for line in spec["lines"]:
        if line.startswith("## "):
            y += 18
            draw.rounded_rectangle(
                (76, y, width - 76, y + 52),
                radius=7,
                fill=(220, 228, 234),
            )
            draw.text((94, y + 10), line[3:], font=body_bold, fill=navy)
            y += 69
            row = 0
            continue

        if row % 2 == 0:
            draw.rectangle(
                (76, y - 7, width - 76, y + 42),
                fill=(252, 250, 243),
            )
        draw.text((90, y), line, font=body_font, fill=ink)
        if spec.get("mask_line_prefix") and line.startswith(
            spec["mask_line_prefix"]
        ):
            masked_box = (82, y - 9, width - 85, y + 43)
        y += 51
        row += 1

    footer_y = height - 135
    draw.line((76, footer_y, width - 76, footer_y), fill=(154, 158, 155), width=2)
    draw.text(
        (76, footer_y + 18),
        "No real entity, account, identifier, signature, seal, or logo is used.",
        font=_font(19),
        fill=muted,
    )
    draw.text(
        (76, footer_y + 52),
        "Dataset seed: {} | Case: {}".format(FIXED_SEED, spec["case_id"]),
        font=_font(17),
        fill=muted,
    )

    if masked_box is not None:
        crop = page.crop(masked_box).filter(ImageFilter.GaussianBlur(radius=9))
        page.paste(crop, masked_box)
        mask_draw = ImageDraw.Draw(page, "RGBA")
        left, top, right, bottom = masked_box
        mask_draw.rounded_rectangle(
            (left + 250, top + 4, right - 95, bottom - 3),
            radius=9,
            fill=(102, 104, 104, 225),
        )
        mask_draw.line(
            (left + 260, top + 15, right - 110, bottom - 11),
            fill=(65, 67, 68, 220),
            width=7,
        )
    return page


def _scanner_effect(image: Image.Image, case_index: int) -> Image.Image:
    angle = (0.35, -0.55, 0.7, -0.4)[case_index % 4]
    scanned = image.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=False,
        fillcolor=(238, 238, 234),
    )
    scanned = ImageEnhance.Contrast(scanned).enhance(0.97)
    scanned = ImageEnhance.Color(scanned).enhance(0.22)
    overlay = Image.new("RGBA", scanned.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    for y in range(43 + case_index * 3, scanned.height, 97):
        draw.line((35, y, scanned.width - 35, y), fill=(45, 45, 45, 8), width=1)
    return Image.alpha_composite(scanned.convert("RGBA"), overlay).convert("RGB")


def _photo_effect(
    image: Image.Image,
    case_index: int,
    low_quality: bool,
) -> Image.Image:
    width, height = image.size
    inset = 8 + case_index
    # Pillow QUAD order is upper-left, lower-left, lower-right, upper-right.
    quad = (
        inset,
        1,
        3,
        height - 2,
        width - 4,
        height - 10,
        width - 20,
        8 + case_index,
    )
    perspective = image.transform(
        (width, height),
        Image.Transform.QUAD,
        quad,
        resample=Image.Resampling.BICUBIC,
        fillcolor=(239, 236, 224),
    )
    angle = (0.65, -0.9, 1.05, -0.7)[case_index % 4]
    paper = perspective.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=(230, 224, 207),
    )
    canvas = Image.new("RGB", (1430, 1940), (197, 191, 175))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow, "RGBA")
    x = (canvas.width - paper.width) // 2
    y = (canvas.height - paper.height) // 2
    shadow_draw.rounded_rectangle(
        (x + 20, y + 28, x + paper.width + 28, y + paper.height + 32),
        radius=18,
        fill=(25, 28, 30, 105),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=18))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow).convert("RGB")
    canvas.paste(paper, (x, y))

    lighting = Image.linear_gradient("L").resize(canvas.size)
    lighting = ImageEnhance.Contrast(lighting).enhance(0.42)
    warm = Image.new("RGB", canvas.size, (238, 218, 177))
    canvas = Image.composite(warm, canvas, lighting.point(lambda p: p // 12))
    canvas = ImageEnhance.Contrast(canvas).enhance(0.96 if not low_quality else 0.88)
    canvas = ImageEnhance.Sharpness(canvas).enhance(0.96 if not low_quality else 0.68)
    if low_quality:
        canvas = canvas.filter(ImageFilter.GaussianBlur(radius=0.55))
    return canvas


def _render_document(
    spec: Dict[str, Any],
    output_path: Path,
    case_index: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    page = _draw_page(spec)
    if spec["effect"] == "scan":
        rendered = _scanner_effect(page, case_index)
    else:
        rendered = _photo_effect(
            page,
            case_index,
            low_quality=spec["effect"] == "low_quality_photo",
        )

    extension = output_path.suffix.lower()
    if extension == ".pdf":
        fixed_pdf_time = time.struct_time(
            (2026, 7, 29, 0, 0, 0, 2, 210, 0)
        )
        rendered.save(
            output_path,
            "PDF",
            resolution=150.0,
            save_all=False,
            creationDate=fixed_pdf_time,
            modDate=fixed_pdf_time,
        )
    elif extension in {".jpg", ".jpeg"}:
        rendered.save(
            output_path,
            "JPEG",
            quality=77 if spec["effect"] == "low_quality_photo" else 84,
            optimize=True,
            progressive=False,
        )
    elif extension == ".png":
        rendered.save(output_path, "PNG", optimize=True)
    else:
        raise ValueError("Unsupported output extension: {}".format(extension))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def generate(render_documents: bool = True) -> None:
    DOCUMENTS.mkdir(parents=True, exist_ok=True)
    LABELS.mkdir(parents=True, exist_ok=True)
    FIXTURE_PREDICTIONS.mkdir(parents=True, exist_ok=True)
    manifest_rows: List[Dict[str, Any]] = []

    for index, spec in enumerate(_cases()):
        document_path = DOCUMENTS / "{}{}".format(
            spec["case_id"],
            spec["extension"],
        )
        if render_documents:
            _render_document(spec, document_path, index)

        raw = TradeDocumentExtraction.model_validate(spec["label"])
        label, unused_validation = apply_deterministic_review_state(
            raw,
            company_role=raw.company_role,
            company_country="KR",
        )
        del unused_validation

        label_path = LABELS / "{}.json".format(spec["case_id"])
        prediction_path = FIXTURE_PREDICTIONS / "{}.json".format(
            spec["case_id"]
        )
        _write_json(label_path, label.model_dump())
        _write_json(
            prediction_path,
            {
                "extraction": label.model_dump(),
                "metadata": {
                    "mode": "fixture",
                    "evaluation_mode": "FIXTURE",
                    "fixture_only": True,
                    "model_accuracy_claim_allowed": False,
                    "purpose": "EVALUATOR_PIPELINE_VALIDATION",
                    "latency_seconds": "0",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_api_cost": "0",
                    "prompt_version": get_prompt_version(),
                },
            },
        )
        manifest_rows.append(
            {
                "case_id": spec["case_id"],
                "document_path": document_path.relative_to(ROOT).as_posix(),
                "label_path": label_path.relative_to(ROOT).as_posix(),
                "category": spec["category"],
                "difficulty": spec["difficulty"],
                "notes": spec["notes"],
                "split": "test",
                "company_country": "KR",
                "counterparty_country": spec["country"],
                "trade_type": spec["trade_type"],
                "user_confirmed": False,
                "human_approved": False,
                "fine_tuning_eligible": False,
                "synthetic_document": True,
                "real_customer_document": False,
                "expected_validation_status": spec[
                    "expected_validation_status"
                ],
                "expected_review_reasons": spec["expected_review_reasons"],
            }
        )

    with MANIFEST.open("w", encoding="utf-8") as handle:
        for row in manifest_rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the isolated US/Brazil validation dataset."
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Regenerate labels, fixture predictions, and manifest only.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate(render_documents=not args.json_only)
    print(
        "Generated 8 isolated country-validation cases at {}".format(
            DATASET.relative_to(ROOT)
        )
    )


if __name__ == "__main__":
    main()
