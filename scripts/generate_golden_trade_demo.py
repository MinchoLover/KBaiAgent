#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "dataset" / "golden_demo"
PDF_PATH = OUTPUT_DIR / "golden_export_contract.pdf"
EXPECTED_EXTRACTION_PATH = OUTPUT_DIR / "expected_extraction.json"
DEMO_INPUTS_PATH = OUTPUT_DIR / "demo_inputs.json"

CASE_ID = "golden_export_br_001"
DOCUMENT_NUMBER = "GOLDEN-EXPORT-BR-2026-001"
NOTICE = "SYNTHETIC SAMPLE - NOT LEGALLY BINDING"

SELLER_LINE = (
    "Seller: Hanbit Precision Co., Ltd. | "
    "Country: Republic of Korea (KR)"
)
BUYER_LINE = (
    "Buyer: Aurora Comercio de Equipamentos Ltda. | "
    "Country: Brazil (BR)"
)
CONTRACT_DATE_LINE = "Contract Date: 29 July 2026"
TOTAL_PRICE_QUOTE = (
    "The total Contract Price is one hundred thousand United States "
    "dollars (USD 100,000)."
)
ADVANCE_QUOTE = (
    "The Buyer shall remit twenty percent (20%), equal to USD 20,000, "
    "on 29 July 2026 as an advance payment."
)
BALANCE_QUOTE = (
    "The remaining eighty percent (80%), equal to USD 80,000, shall be "
    "paid by T/T remittance on or before 20 August 2026 (Payment Due Date)."
)
PAYMENT_TERMS_LINE = (
    "Payment Terms: 20% advance; 80% balance by T/T on or before "
    "20 August 2026."
)
SHIPMENT_DATE_LINE = "Shipment Date: 5 August 2026"
INCOTERM_LINE = "Delivery Term: FOB Busan, Incoterms 2020"
LC_LINE = "No documentary credit is required under this Contract."
GUARANTEE_LINE = "No independent bank payment guarantee is provided."


PdfLine = Tuple[str, int, int, int, str]


def _page_one_lines() -> List[PdfLine]:
    return [
        ("F2", 11, 54, 808, NOTICE),
        ("F2", 18, 54, 774, "INTERNATIONAL SALES CONTRACT"),
        ("F1", 10, 54, 748, "Contract No.: {}".format(DOCUMENT_NUMBER)),
        ("F1", 10, 54, 730, CONTRACT_DATE_LINE),
        ("F2", 12, 54, 695, "1. PARTIES"),
        ("F1", 10, 54, 670, SELLER_LINE),
        ("F1", 10, 54, 648, BUYER_LINE),
        (
            "F1",
            9,
            54,
            624,
            "The parties named above are fictional entities used only for "
            "this synthetic demonstration.",
        ),
        ("F2", 12, 54, 580, "2. GOODS AND PURPOSE"),
        (
            "F1",
            10,
            54,
            555,
            "The Seller agrees to supply synthetic precision equipment "
            "for evaluation purposes only.",
        ),
        (
            "F1",
            10,
            54,
            533,
            "No actual goods, shipment instruction, account, or legal "
            "obligation is created.",
        ),
        ("F2", 12, 54, 489, "3. CONTRACT PRICE"),
        ("F1", 9, 54, 463, TOTAL_PRICE_QUOTE),
        (
            "F1",
            10,
            54,
            438,
            "The Contract currency is United States dollars (USD).",
        ),
        (
            "F1",
            9,
            54,
            395,
            "This page intentionally contains no address, telephone, "
            "email, registration number,",
        ),
        (
            "F1",
            9,
            54,
            377,
            "bank account, logo, signature, seal, or information about "
            "any real person or entity.",
        ),
        ("F2", 9, 54, 28, "{} | Page 1 of 2".format(NOTICE)),
    ]


def _page_two_lines() -> List[PdfLine]:
    return [
        ("F2", 11, 54, 808, NOTICE),
        ("F2", 18, 54, 774, "PAYMENT AND DELIVERY TERMS"),
        ("F2", 12, 54, 730, "4. PAYMENT"),
        ("F1", 8, 54, 704, ADVANCE_QUOTE),
        ("F1", 8, 54, 680, BALANCE_QUOTE),
        ("F1", 9, 54, 654, PAYMENT_TERMS_LINE),
        (
            "F1",
            10,
            54,
            630,
            "The balance shall be settled on an Open Account basis by "
            "T/T remittance.",
        ),
        ("F2", 12, 54, 582, "5. DELIVERY"),
        ("F1", 10, 54, 556, SHIPMENT_DATE_LINE),
        ("F1", 10, 54, 534, INCOTERM_LINE),
        ("F2", 12, 54, 486, "6. DOCUMENTARY CREDIT AND GUARANTEE"),
        ("F1", 10, 54, 460, LC_LINE),
        ("F1", 10, 54, 438, GUARANTEE_LINE),
        (
            "F1",
            9,
            54,
            413,
            "Credit insurance, counterparty history, liquidity, hedge, "
            "and credit limit are not",
        ),
        (
            "F1",
            9,
            54,
            395,
            "contract facts and must be confirmed separately by the user.",
        ),
        ("F2", 12, 54, 347, "7. SYNTHETIC AND NON-BINDING STATUS"),
        (
            "F1",
            9,
            54,
            321,
            "This document is a synthetic sample created solely for a "
            "software demonstration.",
        ),
        (
            "F1",
            9,
            54,
            303,
            "It has no legal effect and must not be used for payment, "
            "shipment, credit, or approval.",
        ),
        (
            "F1",
            9,
            54,
            285,
            "No real address, account, registration number, logo, "
            "signature, stamp, or seal is included.",
        ),
        ("F2", 9, 54, 28, "{} | Page 2 of 2".format(NOTICE)),
    ]


def page_text_lines() -> List[List[str]]:
    return [
        [item[4] for item in _page_one_lines()],
        [item[4] for item in _page_two_lines()],
    ]


def _pdf_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def _content_stream(lines: List[PdfLine]) -> bytes:
    commands: List[str] = [
        "q",
        "1 1 1 rg",
        "0 0 595 842 re",
        "f",
        "Q",
    ]
    for font, size, x, y, text in lines:
        color = "0.70 0.05 0.05 rg" if text.startswith(NOTICE) else "0 0 0 rg"
        commands.extend(
            [
                "BT",
                "/{} {} Tf".format(font, size),
                color,
                "1 0 0 1 {} {} Tm".format(x, y),
                "({}) Tj".format(_pdf_escape(text)),
                "ET",
            ]
        )
    commands.append("")
    return "\n".join(commands).encode("ascii")


def _stream_object(content: bytes) -> bytes:
    return (
        "<< /Length {} >>\nstream\n".format(len(content)).encode("ascii")
        + content
        + b"endstream"
    )


def build_pdf_bytes() -> bytes:
    page_one = _content_stream(_page_one_lines())
    page_two = _content_stream(_page_two_lines())
    objects: Dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        3: (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> "
            b"/Contents 7 0 R >>"
        ),
        4: (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> "
            b"/Contents 8 0 R >>"
        ),
        5: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        6: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        7: _stream_object(page_one),
        8: _stream_object(page_two),
        9: (
            b"<< /Title (Synthetic Golden Export Contract) "
            b"/Author (KBaiAgent QA) /Creator (deterministic generator 1.0) "
            b"/Producer (KBaiAgent) "
            b"/CreationDate (D:20260729000000+09'00') "
            b"/ModDate (D:20260729000000+09'00') >>"
        ),
    }

    # The binary marker includes NUL so Git and transport tools do not treat
    # the PDF cross-reference records as a whitespace-sensitive text file.
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\x00\n")
    offsets: Dict[int, int] = {}
    for number in range(1, 10):
        offsets[number] = len(output)
        output.extend("{} 0 obj\n".format(number).encode("ascii"))
        output.extend(objects[number])
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(b"xref\n0 10\n")
    output.extend(b"0000000000 65535 f \n")
    for number in range(1, 10):
        output.extend(
            "{:010d} 00000 n \n".format(offsets[number]).encode("ascii")
        )
    output.extend(
        (
            "trailer\n"
            "<< /Size 10 /Root 1 0 R /Info 9 0 R >>\n"
            "startxref\n"
            "{}\n"
            "%%EOF\n"
        ).format(xref_offset).encode("ascii")
    )
    return bytes(output)


def expected_extraction_payload() -> Dict[str, Any]:
    from schemas import FieldEvidence, PaymentInstallment
    from schemas import TradeDocumentExtraction

    evidence = [
        FieldEvidence(
            field="document_notice",
            page=1,
            source_text=NOTICE,
            extraction_type="EXPLICIT",
            confidence_reason="The synthetic non-binding notice is explicit.",
        ),
        FieldEvidence(
            field="document_notice",
            page=2,
            source_text=NOTICE,
            extraction_type="EXPLICIT",
            confidence_reason="The notice is repeated on every page.",
        ),
        FieldEvidence(
            field="seller_name",
            page=1,
            source_text=SELLER_LINE,
            extraction_type="EXPLICIT",
            confidence_reason="The Seller label identifies the party.",
        ),
        FieldEvidence(
            field="seller_country",
            page=1,
            source_text=SELLER_LINE,
            extraction_type="EXPLICIT",
            confidence_reason="The Seller country name and ISO code agree.",
        ),
        FieldEvidence(
            field="buyer_name",
            page=1,
            source_text=BUYER_LINE,
            extraction_type="EXPLICIT",
            confidence_reason="The Buyer label identifies the party.",
        ),
        FieldEvidence(
            field="buyer_country",
            page=1,
            source_text=BUYER_LINE,
            extraction_type="EXPLICIT",
            confidence_reason="The Buyer country name and ISO code agree.",
        ),
        FieldEvidence(
            field="contract_date",
            page=1,
            source_text=CONTRACT_DATE_LINE,
            extraction_type="EXPLICIT",
            confidence_reason="The Contract Date label is explicit.",
        ),
        FieldEvidence(
            field="currency",
            page=1,
            source_text=TOTAL_PRICE_QUOTE,
            extraction_type="EXPLICIT",
            confidence_reason="The total price states the USD code.",
        ),
        FieldEvidence(
            field="grand_total",
            page=1,
            source_text=TOTAL_PRICE_QUOTE,
            extraction_type="EXPLICIT",
            confidence_reason="The total Contract Price is explicit.",
        ),
        FieldEvidence(
            field="amount_due",
            page=1,
            source_text=TOTAL_PRICE_QUOTE,
            extraction_type="EXPLICIT",
            confidence_reason="The full contractual receivable is explicit.",
        ),
        FieldEvidence(
            field="explicit_due_date",
            page=2,
            source_text=BALANCE_QUOTE,
            extraction_type="EXPLICIT",
            confidence_reason="The Payment Due Date is explicit.",
        ),
        FieldEvidence(
            field="payment_terms",
            page=2,
            source_text=PAYMENT_TERMS_LINE,
            extraction_type="EXPLICIT",
            confidence_reason="The split and T/T due date are explicit.",
        ),
        FieldEvidence(
            field="installments",
            page=2,
            source_text=ADVANCE_QUOTE,
            extraction_type="EXPLICIT",
            confidence_reason="The advance percentage and amount are explicit.",
        ),
        FieldEvidence(
            field="installments",
            page=2,
            source_text=BALANCE_QUOTE,
            extraction_type="EXPLICIT",
            confidence_reason="The balance percentage, amount, and date are explicit.",
        ),
        FieldEvidence(
            field="shipment_date",
            page=2,
            source_text=SHIPMENT_DATE_LINE,
            extraction_type="EXPLICIT",
            confidence_reason="The Shipment Date label is explicit.",
        ),
        FieldEvidence(
            field="incoterm",
            page=2,
            source_text=INCOTERM_LINE,
            extraction_type="EXPLICIT",
            confidence_reason="The delivery term is explicit.",
        ),
    ]
    extraction = TradeDocumentExtraction(
        document_type="SALES_CONTRACT",
        document_number=DOCUMENT_NUMBER,
        seller_name="Hanbit Precision Co., Ltd.",
        seller_country="KR",
        buyer_name="Aurora Comercio de Equipamentos Ltda.",
        buyer_country="BR",
        company_role="SELLER",
        trade_type="EXPORT",
        currency="USD",
        grand_total="100000.00",
        amount_due="100000.00",
        issue_date=None,
        contract_date="2026-07-29",
        shipment_date="2026-08-05",
        explicit_due_date="2026-08-20",
        derived_due_date=None,
        payment_terms=PAYMENT_TERMS_LINE,
        incoterm="FOB Busan, Incoterms 2020",
        installments=[
            PaymentInstallment(
                sequence=1,
                amount="20000.00",
                currency="USD",
                due_date="2026-07-29",
                condition="20% advance on contract date",
            ),
            PaymentInstallment(
                sequence=2,
                amount="80000.00",
                currency="USD",
                due_date="2026-08-20",
                condition="80% balance by T/T on or before due date",
            ),
        ],
        evidence=evidence,
        warnings=[],
        missing_required_fields=[],
        needs_human_review=True,
    )
    return extraction.model_dump()


def demo_inputs_payload() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "case_id": CASE_ID,
        "source_document": PDF_PATH.relative_to(ROOT).as_posix(),
        "classification": {
            "synthetic_document": True,
            "real_customer_document": False,
            "not_legally_binding": True,
            "live_extraction_executed": False,
        },
        "country_normalization_expectations": [
            {
                "field": "seller_country",
                "raw_value": "Republic of Korea (KR)",
                "normalized_value": "KR",
                "normalization_method": "VERIFIED_COUNTRY_NAME_AND_CODE",
                "warning": None,
            },
            {
                "field": "buyer_country",
                "raw_value": "Brazil (BR)",
                "normalized_value": "BR",
                "normalization_method": "VERIFIED_COUNTRY_NAME_AND_CODE",
                "warning": None,
            },
        ],
        "document_facts_outside_extraction_schema": {
            "letter_of_credit_status": "NOT_REQUIRED",
            "letter_of_credit_source_quote": LC_LINE,
            "independent_bank_guarantee_status": "NOT_PROVIDED",
            "guarantee_source_quote": GUARANTEE_LINE,
        },
        "user_confirmed_trade_inputs": {
            "counterparty_relationship": "EXISTING",
            "advance_payment_ratio": "0.2",
            "balance_payment_method": "OPEN_ACCOUNT",
            "payment_term_days": 22,
            "payment_term_basis": "CONFIRMED_DATE_INTERVAL",
            "protection_information_status": "NONE_CONFIRMED",
            "protection_mechanisms": [],
            "field_sources": {
                "counterparty_relationship": "USER_CONFIRMED",
                "advance_payment_ratio": "DOCUMENT_EXPLICIT",
                "balance_payment_method": "DOCUMENT_EXPLICIT",
                "payment_term_days": "DETERMINISTIC_DERIVED",
                "protection_information_status": "USER_CONFIRMED",
            },
        },
        "presenter_only_inputs": {
            "company_type": "CORPORATION",
            "credit_insurance": "NO",
            "independent_guarantee": "NO",
            "existing_hedge": "NONE",
        },
        "company_finance_manual_inputs": {
            "as_of_date": "2026-07-29",
            "usable_fx_balance": "0.00",
            "current_krw_cash": "20000000.00",
            "minimum_cash_buffer": "10000000.00",
            "credit_limit": "0.00",
            "acceptable_fx_loss": "5000000.00",
            "confirmed_krw_cashflows": [
                {
                    "date": "2026-08-20",
                    "amount": "145000000.00",
                    "direction": "OUTFLOW",
                    "category": "COST",
                    "description": "수출대금으로 충당할 합성 운영비",
                }
            ],
            "bank_spread_bps": "0",
            "bank_fee": "0.00",
        },
        "stage1_horizon_expectation": {
            "forecast_prediction_date": "2026-07-27",
            "forecast_horizon_trading_days": 21,
            "forecast_horizon_end_date": "2026-08-25",
            "settlement_date": "2026-08-20",
            "within_supported_horizon": True,
        },
        "fixture_disclosure": {
            "purpose": "GOLDEN_DEMO_EXPECTED_DATA_VALIDATION",
            "evaluation_mode": "FIXTURE",
            "model_accuracy_claim_allowed": False,
            "live_extraction": False,
        },
    }


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def generate(output_dir: Path = OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / PDF_PATH.name).write_bytes(build_pdf_bytes())
    _write_json(
        output_dir / EXPECTED_EXTRACTION_PATH.name,
        expected_extraction_payload(),
    )
    _write_json(
        output_dir / DEMO_INPUTS_PATH.name,
        demo_inputs_payload(),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the deterministic text-layer Golden export contract "
            "and API-free expected data."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory. Defaults to dataset/golden_demo.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    generate(args.output_dir)
    print(
        "Generated Golden demo artifacts at {}".format(
            args.output_dir.resolve()
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
