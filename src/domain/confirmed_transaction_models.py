from typing import List, Literal, Optional

from pydantic import Field

from schemas import StrictModel


class ConfirmedTradeEvent(StrictModel):
    sequence: int = Field(ge=1)
    trade_type: Literal["IMPORT", "EXPORT"]
    currency: str
    foreign_amount: str
    settlement_date: str


class ConfirmedTradeBinding(StrictModel):
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    trade_type: Literal["IMPORT", "EXPORT"]
    currency: str
    events: List[ConfirmedTradeEvent] = Field(min_length=1)
    trade_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ConfirmedInstallment(StrictModel):
    sequence: int = Field(ge=1)
    amount: str
    currency: str
    due_date: str
    condition: Optional[str] = None


class ConfirmedTransactionSnapshot(StrictModel):
    """Immutable, user-confirmed source for every downstream stage."""

    schema_version: str = "1.0"
    source_filename: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed_at: str
    company_role: Literal["BUYER", "SELLER"]
    company_country: str = Field(pattern=r"^[A-Z]{2}$")
    trade_type: Literal["IMPORT", "EXPORT"]
    currency: str
    amount_due: str
    due_date: str
    contract_date: Optional[str] = None
    shipment_date: Optional[str] = None
    document_type: str
    document_number: Optional[str] = None
    grand_total: Optional[str] = None
    issue_date: Optional[str] = None
    seller_name: Optional[str] = None
    seller_country: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_country: Optional[str] = None
    payment_terms: Optional[str] = None
    incoterm: Optional[str] = None
    installments: List[ConfirmedInstallment] = Field(default_factory=list)
    trade_binding: ConfirmedTradeBinding
    input_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
