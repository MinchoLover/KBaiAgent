from schemas import FieldEvidence, TradeDocumentExtraction
from validators import apply_deterministic_review_state


def sample_extraction(
    company_role: str = "BUYER",
) -> TradeDocumentExtraction:
    if company_role == "SELLER":
        seller_name = "Busan Demo Machines Ltd."
        seller_country = "KR"
        buyer_name = "Pacific Example Industries Inc."
        buyer_country = "US"
    else:
        seller_name = "Northstar Demo Components Inc."
        seller_country = "US"
        buyer_name = "Han River Demo Imports Ltd."
        buyer_country = "KR"

    extraction = TradeDocumentExtraction(
        document_type="COMMERCIAL_INVOICE",
        document_number="INV-DEMO-2026-001",
        seller_name=seller_name,
        seller_country=seller_country,
        buyer_name=buyer_name,
        buyer_country=buyer_country,
        company_role=company_role,
        trade_type="EXPORT" if company_role == "SELLER" else "IMPORT",
        currency="USD",
        grand_total="100000.00",
        amount_due="100000.00",
        issue_date="2026-07-20",
        contract_date=None,
        shipment_date="2026-07-25",
        explicit_due_date=None,
        derived_due_date=None,
        payment_terms="Net 90 Days",
        incoterm="FOB Busan",
        installments=[],
        evidence=[
            FieldEvidence(
                field="document_notice",
                page=1,
                source_text="TEST DOCUMENT - NO LEGAL EFFECT",
                extraction_type="EXPLICIT",
                confidence_reason="The test-only notice is printed at the top.",
            ),
            FieldEvidence(
                field="seller_name",
                page=1,
                source_text="Seller: {} ({})".format(
                    seller_name,
                    seller_country,
                ),
                extraction_type="EXPLICIT",
                confidence_reason="Seller label is explicit.",
            ),
            FieldEvidence(
                field="buyer_name",
                page=1,
                source_text="Buyer: {} ({})".format(
                    buyer_name,
                    buyer_country,
                ),
                extraction_type="EXPLICIT",
                confidence_reason="Buyer label is explicit.",
            ),
            FieldEvidence(
                field="amount_due",
                page=1,
                source_text="BALANCE DUE: USD 100000.00",
                extraction_type="EXPLICIT",
                confidence_reason="Balance Due is explicitly labeled.",
            ),
            FieldEvidence(
                field="currency",
                page=1,
                source_text="Currency: USD",
                extraction_type="EXPLICIT",
                confidence_reason="Currency label is explicit.",
            ),
            FieldEvidence(
                field="issue_date",
                page=1,
                source_text="Invoice Date: 2026-07-20",
                extraction_type="EXPLICIT",
                confidence_reason="Invoice Date is explicit.",
            ),
            FieldEvidence(
                field="payment_terms",
                page=1,
                source_text="Payment Terms: Net 90 Days",
                extraction_type="EXPLICIT",
                confidence_reason="Net term is explicit.",
            ),
        ],
        warnings=[],
        missing_required_fields=[],
        needs_human_review=True,
    )
    deterministic, unused_validation = apply_deterministic_review_state(
        extraction,
        company_role=company_role,
        company_country="KR",
    )
    del unused_validation
    return deterministic
