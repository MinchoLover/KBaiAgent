from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from pydantic import Field, field_validator

from schemas import (
    ConfirmationState,
    StrictModel,
    TradeDocumentExtraction,
    ValidationResult,
)
from validators import apply_deterministic_review_state, parse_iso_date


class ConfirmationRecord(StrictModel):
    source_filename: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed_at: str
    company_role: Literal["BUYER", "SELLER"]
    original_values: Dict[str, Any] = Field(default_factory=dict)
    confirmed_values: Dict[str, Any] = Field(default_factory=dict)
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
        currency_confirmed=currency_confirmed,
        amount_due_confirmed=amount_due_confirmed,
        due_date_confirmed=due_date_confirmed,
        confirmed_due_date=confirmed_due_date,
        confirmed_by=confirmed_by,
        confirmed_at=timestamp,
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
    return ConfirmationRecord(
        source_filename=Path(source_filename).name,
        source_sha256=source_sha256.lower(),
        confirmed_at=timestamp,
        company_role=confirmed.company_role,
        original_values=original_values,
        confirmed_values=confirmed_values,
        checks=checks,
    )


def validate_confirmation(
    *,
    extraction: TradeDocumentExtraction,
    record: ConfirmationRecord,
    company_country: str,
) -> ValidationResult:
    _, validation = apply_deterministic_review_state(
        extraction,
        company_role=record.company_role,
        company_country=company_country,
        confirmations=record.checks,
    )
    return validation
