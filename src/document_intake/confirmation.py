from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field, field_validator

from schemas import (
    ConfirmationState,
    StrictModel,
    TradeDocumentExtraction,
    ValidationResult,
)
from validators import apply_deterministic_review_state, parse_iso_date
from src.document_intake.normalization import normalize_country_name


REVIEW_EDITABLE_EXTRACTION_FIELDS = (
    "document_type",
    "document_number",
    "seller_name",
    "seller_country",
    "buyer_name",
    "buyer_country",
    "company_role",
    "trade_type",
    "currency",
    "grand_total",
    "amount_due",
    "issue_date",
    "contract_date",
    "shipment_date",
    "explicit_due_date",
    "payment_terms",
    "incoterm",
    "installments",
)


def discard_stale_evidence_after_review(
    original: TradeDocumentExtraction,
    reviewed: TradeDocumentExtraction,
) -> TradeDocumentExtraction:
    """Drop model evidence for values changed by a reviewer.

    Evidence belongs to the value extracted from the source, never to a later
    user edit.  A reviewer can explicitly attest to a resulting evidence gap
    at the confirmation gate; this function deliberately does not add a
    replacement evidence item.
    """

    changed_fields = {
        field
        for field in REVIEW_EDITABLE_EXTRACTION_FIELDS
        if getattr(original, field) != getattr(reviewed, field)
    }
    if not changed_fields:
        return reviewed
    return reviewed.model_copy(
        update={
            "evidence": [
                item
                for item in reviewed.evidence
                if item.field not in changed_fields
            ]
        }
    )


class ReviewAuditSnapshot(StrictModel):
    company_role: Literal["BUYER", "SELLER"]
    company_country: str
    trade_type: Literal["IMPORT", "EXPORT", "UNKNOWN"]
    seller_country: Optional[str] = None
    buyer_country: Optional[str] = None
    currency: Optional[str] = None
    amount_due: Optional[str] = None
    contract_date: Optional[str] = None
    explicit_due_date: Optional[str] = None


class ReviewAuditEntry(StrictModel):
    changed_at: str
    before: ReviewAuditSnapshot
    after: ReviewAuditSnapshot

    @field_validator("changed_at")
    @classmethod
    def validate_changed_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "review changed_at은 ISO 8601 datetime이어야 합니다."
            ) from exc
        if parsed.tzinfo is None:
            raise ValueError("review changed_at에는 timezone offset이 필요합니다.")
        return value


class ConfirmationRecord(StrictModel):
    source_filename: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed_at: str
    company_role: Literal["BUYER", "SELLER"]
    company_country: str = Field(pattern=r"^[A-Z]{2}$")
    trade_type_source: Literal["AUTO", "USER_OVERRIDE", "UNKNOWN"] = "AUTO"
    original_values: Dict[str, Any] = Field(default_factory=dict)
    confirmed_values: Dict[str, Any] = Field(default_factory=dict)
    review_audit_trail: List[ReviewAuditEntry] = Field(default_factory=list)
    checks: ConfirmationState

    @field_validator("confirmed_at")
    @classmethod
    def validate_confirmed_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "confirmed_at은 ISO 8601 datetime이어야 합니다."
            ) from exc
        if parsed.tzinfo is None:
            raise ValueError("confirmed_at에는 timezone offset이 필요합니다.")
        return value


def create_confirmation_record(
    *,
    original: TradeDocumentExtraction,
    confirmed: TradeDocumentExtraction,
    confirmed_due_date: Optional[str],
    currency_confirmed: bool,
    amount_due_confirmed: bool,
    due_date_confirmed: bool,
    source_filename: str,
    source_sha256: str,
    company_country: str,
    company_role_confirmed: bool = False,
    trade_type_confirmed: bool = False,
    trade_type_source: Literal[
        "AUTO",
        "USER_OVERRIDE",
        "UNKNOWN",
    ] = "AUTO",
    evidence_override_fields: Optional[List[str]] = None,
    review_audit_trail: Optional[List[Dict[str, Any]]] = None,
    confirmed_by: Optional[str] = None,
    confirmed_at: Optional[str] = None,
) -> ConfirmationRecord:
    if (
        due_date_confirmed
        and not confirmed_due_date
        and not confirmed.installments
    ):
        raise ValueError("최종 결제일 확인값이 필요합니다.")
    if confirmed_due_date:
        parsed_due = parse_iso_date(confirmed_due_date)
        if parsed_due is None:
            raise ValueError("결제일 확인값이 필요합니다.")

    timestamp = confirmed_at or datetime.now(timezone.utc).isoformat()
    checks = ConfirmationState(
        company_role_confirmed=company_role_confirmed,
        trade_type_confirmed=trade_type_confirmed,
        currency_confirmed=currency_confirmed,
        amount_due_confirmed=amount_due_confirmed,
        due_date_confirmed=due_date_confirmed,
        confirmed_due_date=confirmed_due_date,
        confirmed_by=confirmed_by,
        confirmed_at=timestamp,
        user_confirmed_override=bool(evidence_override_fields),
        user_confirmed_override_fields=evidence_override_fields or [],
    )
    original_values = original.model_dump()
    original_values["installment_due_dates"] = [
        item.due_date for item in original.installments
    ]
    confirmed_values = confirmed.model_dump()
    confirmed_values["settlement_date"] = confirmed_due_date
    confirmed_values["installment_due_dates"] = [
        item.due_date for item in confirmed.installments
    ]
    normalized_company_country, _ = normalize_country_name(
        company_country,
        "company_country",
    )
    if (
        normalized_company_country is None
        or len(normalized_company_country) != 2
        or not normalized_company_country.isalpha()
    ):
        raise ValueError("확인 기록의 회사 국가를 ISO alpha-2로 정규화할 수 없습니다.")
    return ConfirmationRecord(
        source_filename=Path(source_filename).name,
        source_sha256=source_sha256.lower(),
        confirmed_at=timestamp,
        company_role=confirmed.company_role,
        company_country=normalized_company_country,
        trade_type_source=trade_type_source,
        original_values=original_values,
        confirmed_values=confirmed_values,
        review_audit_trail=review_audit_trail or [],
        checks=checks,
    )


def validate_confirmation(
    *,
    extraction: TradeDocumentExtraction,
    record: ConfirmationRecord,
    company_country: str,
) -> ValidationResult:
    normalized_company_country, _ = normalize_country_name(
        company_country,
        "company_country",
    )
    if normalized_company_country is None:
        raise ValueError("현재 회사 국가가 필요합니다.")
    if normalized_company_country != record.company_country:
        raise ValueError(
            "확인 기록의 회사 국가가 현재 회사 국가와 일치하지 않습니다."
        )
    _, validation = apply_deterministic_review_state(
        extraction,
        company_role=record.company_role,
        company_country=normalized_company_country,
        confirmations=record.checks,
        user_trade_type=(
            extraction.trade_type
            if record.trade_type_source == "USER_OVERRIDE"
            else None
        ),
    )
    return validation
