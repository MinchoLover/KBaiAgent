#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "dataset" / "golden_import_hedge_demo"
PDF_PATH = OUTPUT_DIR / "golden_import_payable_contract.pdf"
EXPECTED_EXTRACTION_PATH = OUTPUT_DIR / "expected_extraction.json"
DEMO_INPUTS_PATH = OUTPUT_DIR / "demo_inputs.json"

CASE_ID = "golden_import_us_hedge_001"
DOCUMENT_NUMBER = "GOLDEN-IMPORT-US-2026-001"
NOTICE = "SYNTHETIC SAMPLE - NOT LEGALLY BINDING"

SELLER_LINE = (
    "Seller: Northstar Industrial Components LLC | "
    "Country: United States (US)"
)
BUYER_LINE = (
    "Buyer: Mirae Industrial Solutions Co., Ltd. | "
    "Country: Republic of Korea (KR)"
)
CONTRACT_DATE_LINE = "Contract Date: 29 July 2026"
TOTAL_PRICE_QUOTE = (
    "The total Contract Price is one hundred thousand United States "
    "dollars (USD 100,000)."
)
PAYMENT_QUOTE = (
    "The Buyer shall pay one hundred percent (100%), equal to USD 100,000, "
    "by T/T remittance on or before 27 August 2026 (Payment Due Date)."
)
PAYMENT_TERMS_LINE = (
    "Payment Terms: 100% by T/T on or before 27 August 2026; "
    "one payment only."
)
NO_INSTALLMENT_LINE = (
    "This Contract contains one payment obligation and no installment "
    "schedule."
)
SHIPMENT_DATE_LINE = "Shipment Date: 12 August 2026"
INCOTERM_LINE = "Delivery Term: CIF Busan, Incoterms 2020"
LC_LINE = "No documentary credit is required under this Contract."
GUARANTEE_LINE = "No independent bank payment guarantee is provided."


PdfLine = Tuple[str, int, int, int, str]


def _page_one_lines() -> List[PdfLine]:
    return [
        ("F2", 11, 54, 808, NOTICE),
        ("F2", 18, 54, 774, "INTERNATIONAL IMPORT PURCHASE CONTRACT"),
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
            "The parties are fictional entities used only for this "
            "synthetic software demonstration.",
        ),
        ("F2", 12, 54, 580, "2. GOODS AND PURPOSE"),
        (
            "F1",
            10,
            54,
            555,
            "The Seller agrees to supply synthetic industrial components "
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
            "This page contains no address, telephone, email, registration "
            "number, bank account,",
        ),
        (
            "F1",
            9,
            54,
            377,
            "logo, signature, seal, or information about any real person "
            "or entity.",
        ),
        ("F2", 9, 54, 28, "{} | Page 1 of 2".format(NOTICE)),
    ]


def _page_two_lines() -> List[PdfLine]:
    return [
        ("F2", 11, 54, 808, NOTICE),
        ("F2", 18, 54, 774, "PAYMENT AND DELIVERY TERMS"),
        ("F2", 12, 54, 730, "4. SINGLE PAYMENT"),
        ("F1", 8, 54, 704, PAYMENT_QUOTE),
        ("F1", 9, 54, 676, PAYMENT_TERMS_LINE),
        ("F1", 9, 54, 650, NO_INSTALLMENT_LINE),
        (
            "F1",
            10,
            54,
            624,
            "Payment shall be settled on an Open Account basis by "
            "T/T remittance.",
        ),
        ("F2", 12, 54, 578, "5. DELIVERY"),
        ("F1", 10, 54, 552, SHIPMENT_DATE_LINE),
        ("F1", 10, 54, 530, INCOTERM_LINE),
        ("F2", 12, 54, 482, "6. DOCUMENTARY CREDIT AND GUARANTEE"),
        ("F1", 10, 54, 456, LC_LINE),
        ("F1", 10, 54, 434, GUARANTEE_LINE),
        (
            "F1",
            9,
            54,
            409,
            "Existing USD cash, existing forward contracts, liquidity, "
            "insurance, and credit limit",
        ),
        (
            "F1",
            9,
            54,
            391,
            "are not contract facts and must be confirmed separately by "
            "the user.",
        ),
        ("F2", 12, 54, 343, "7. SYNTHETIC AND NON-BINDING STATUS"),
        (
            "F1",
            9,
            54,
            317,
            "This document is a synthetic sample created solely for a "
            "software demonstration.",
        ),
        (
            "F1",
            9,
            54,
            299,
            "It has no legal effect and must not be used for payment, "
            "shipment, credit, or approval.",
        ),
        (
            "F1",
            9,
            54,
            281,
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
        color = (
            "0.70 0.05 0.05 rg"
            if text.startswith(NOTICE)
            else "0 0 0 rg"
        )
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
            b"<< /Title (Synthetic Golden Import Payable Contract) "
            b"/Author (KBaiAgent QA) /Creator (deterministic generator 1.0) "
            b"/Producer (KBaiAgent) "
            b"/CreationDate (D:20260729000000+09'00') "
            b"/ModDate (D:20260729000000+09'00') >>"
        ),
    }
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
    from schemas import FieldEvidence, TradeDocumentExtraction

    evidence = [
        FieldEvidence(
            field="document_notice",
            page=1,
            source_text=NOTICE,
            extraction_type="EXPLICIT",
            confidence_reason="The synthetic notice is explicit.",
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
            page=2,
            source_text=PAYMENT_QUOTE,
            extraction_type="EXPLICIT",
            confidence_reason="The single contractual payable is explicit.",
        ),
        FieldEvidence(
            field="explicit_due_date",
            page=2,
            source_text=PAYMENT_QUOTE,
            extraction_type="EXPLICIT",
            confidence_reason="The Payment Due Date is explicit.",
        ),
        FieldEvidence(
            field="payment_terms",
            page=2,
            source_text=PAYMENT_TERMS_LINE,
            extraction_type="EXPLICIT",
            confidence_reason="The single T/T payment term is explicit.",
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
        seller_name="Northstar Industrial Components LLC",
        seller_country="US",
        buyer_name="Mirae Industrial Solutions Co., Ltd.",
        buyer_country="KR",
        company_role="BUYER",
        trade_type="IMPORT",
        currency="USD",
        grand_total="100000.00",
        amount_due="100000.00",
        issue_date=None,
        contract_date="2026-07-29",
        shipment_date="2026-08-12",
        explicit_due_date="2026-08-27",
        derived_due_date=None,
        payment_terms=PAYMENT_TERMS_LINE,
        incoterm="CIF Busan, Incoterms 2020",
        installments=[],
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
            "test_split": True,
            "fine_tuning_candidate": False,
            "live_extraction_executed": False,
        },
        "country_normalization_expectations": [
            {
                "field": "seller_country",
                "raw_value": "United States (US)",
                "normalized_value": "US",
                "normalization_method": (
                    "VERIFIED_COUNTRY_NAME_AND_CODE"
                ),
                "warning": None,
            },
            {
                "field": "buyer_country",
                "raw_value": "Republic of Korea (KR)",
                "normalized_value": "KR",
                "normalization_method": (
                    "VERIFIED_COUNTRY_NAME_AND_CODE"
                ),
                "warning": None,
            },
        ],
        "document_facts_outside_extraction_schema": {
            "letter_of_credit_status": "NOT_REQUIRED",
            "letter_of_credit_source_quote": LC_LINE,
            "independent_bank_guarantee_status": "NOT_PROVIDED",
            "guarantee_source_quote": GUARANTEE_LINE,
            "installment_structure": "SINGLE_PAYMENT_ONLY",
            "installment_source_quote": NO_INSTALLMENT_LINE,
        },
        "user_confirmed_trade_inputs": {
            "counterparty_relationship": "EXISTING",
            "advance_payment_ratio": "0",
            "balance_payment_method": "OPEN_ACCOUNT",
            "payment_term_days": 29,
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
        "company_finance_manual_inputs": {
            "as_of_date": "2026-07-29",
            "usable_fx_balance": "10000.00",
            "current_krw_cash": "140000000.00",
            "minimum_cash_buffer": "10000000.00",
            "credit_limit": "0.00",
            "acceptable_fx_loss": "5000000.00",
            "confirmed_krw_cashflows": [],
            "existing_forward_usd": "0.00",
            "existing_forward_rate": "1400.00",
            "existing_forward_fee": "0.00",
            "bank_spread_bps": "0",
            "bank_fee": "0.00",
        },
        "stage1_fixture": {
            "base_rate": "1400.00",
            "adverse_rate": "1470.00",
            "fixed_10_adverse_rate": "1540.00",
            "target_date": "2026-08-27",
            "kind": "STRESS",
        },
        "kb_macro_hedge_expectation": {
            "scope": "SINGLE_USD_IMPORT_PAYABLE_REFERENCE_ONLY",
            "amount_usd": "100000.00",
            "payment_date": "2026-08-27",
            "existing_usd_cash": "10000.00",
            "existing_forward_usd": "0.00",
            "net_exposure_usd": "90000.00",
            "pricing_status": "MOCK",
            "maximum_status": "REFERENCE_ONLY",
            "candidate_count": 3,
            "candidate_ranks": [1, 2, 3],
        },
        "kb_macro_user_constraints": {
            "payment_certainty": "1.0",
            "maximum_acceptable_cost_krw": "135000000",
            "maximum_budget_exceedance_probability": "0.15",
            "risk_tolerance": "medium",
            "maximum_total_hedge_ratio": "1.0",
            "option_premium_budget_krw": "1500000",
            "allowed_instruments": [
                "forward",
                "vanilla_usd_call",
            ],
        },
        "fixture_disclosure": {
            "purpose": (
                "DIRECT_UPLOAD_PIPELINE_AND_HEDGE_ADAPTER_VALIDATION"
            ),
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
            "Generate the deterministic text-layer Golden single-payable "
            "import contract and API-free expected data."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help=(
            "Output directory. Defaults to "
            "dataset/golden_import_hedge_demo."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    generate(args.output_dir)
    print(
        "Generated Golden import hedge artifacts at {}".format(
            args.output_dir.resolve()
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
