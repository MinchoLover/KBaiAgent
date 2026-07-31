import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Literal, Optional

from pydantic import Field, field_validator, model_validator

from schemas import StrictModel


CounterpartyRelationship = Literal["NEW", "EXISTING", "UNKNOWN"]
BalancePaymentMethod = Literal[
    "OPEN_ACCOUNT",
    "DOCUMENTARY_CREDIT",
    "DOCUMENTARY_COLLECTION_DP",
    "DOCUMENTARY_COLLECTION_DA",
    "DOCUMENTARY_COLLECTION_UNSPECIFIED",
    "OTHER",
    "NOT_APPLICABLE",
    "UNKNOWN",
]
PaymentTermBasis = Literal[
    "EXPLICIT_NET_TERM",
    "CONFIRMED_DATE_INTERVAL",
    "EVENT_BASED_UNRESOLVED",
    "NOT_APPLICABLE",
    "UNKNOWN",
]
ProtectionInformationStatus = Literal[
    "UNKNOWN",
    "NONE_CONFIRMED",
    "DETAILS_PROVIDED",
]
ProtectionType = Literal[
    "ADVANCE_PAYMENT_GUARANTEE",
    "PERFORMANCE_GUARANTEE",
    "PAYMENT_GUARANTEE",
    "EXPORT_CREDIT_INSURANCE",
    "STANDBY_LETTER_OF_CREDIT",
    "OTHER",
]
ProtectionApplicabilityStatus = Literal[
    "PRESENT_SCOPE_UNVERIFIED",
    "CONFIRMED_APPLICABLE",
]
FactSource = Literal[
    "DOCUMENT_EXPLICIT",
    "USER_CONFIRMED",
    "DETERMINISTIC_DERIVED",
    "UNKNOWN",
]
TradeRiskType = Literal[
    "IMPORT_PREPAYMENT_PERFORMANCE_RISK",
    "EXPORT_RECEIVABLE_COLLECTION_RISK",
]
TradeRiskReviewPriority = Literal[
    "STANDARD_REVIEW",
    "ELEVATED_REVIEW",
    "HIGH_REVIEW",
    "UNKNOWN",
]
TradeRiskFactorEffect = Literal[
    "RISK_SIGNAL",
    "MITIGANT",
    "INFORMATION_GAP",
]
TradeRiskReviewNeed = Literal[
    "ADVANCE_PAYMENT_PROTECTION_REVIEW",
    "RECEIVABLE_PROTECTION_REVIEW",
    "DOCUMENTARY_CREDIT_TERMS_REVIEW",
    "TRADE_TERMS_REVIEW",
    "HUMAN_REVIEW",
]


ADVANCE_RATIO_RE = re.compile(
    r"^(?:0(?:\.[0-9]+)?|1(?:\.0+)?)$"
)
REQUIRED_SOURCE_FIELDS = {
    "counterparty_relationship",
    "advance_payment_ratio",
    "balance_payment_method",
    "payment_term_days",
    "protection_information_status",
}


def canonical_ratio(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("선지급 비율은 0~1의 decimal 문자열이어야 합니다.")
    text = value.strip()
    if not ADVANCE_RATIO_RE.fullmatch(text):
        raise ValueError("선지급 비율은 0~1의 decimal 문자열이어야 합니다.")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            "선지급 비율은 0~1의 decimal 문자열이어야 합니다."
        ) from exc
    if not parsed.is_finite() or parsed < 0 or parsed > 1:
        raise ValueError("선지급 비율은 0 이상 1 이하여야 합니다.")
    if parsed == 0:
        return "0"
    if parsed == 1:
        return "1"
    return format(parsed.normalize(), "f")


class ProtectionMechanism(StrictModel):
    protection_type: ProtectionType
    applicability_status: ProtectionApplicabilityStatus
    source: Literal["DOCUMENT_EXPLICIT", "USER_CONFIRMED"]
    evidence_refs: List[str] = Field(default_factory=list)

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, value: List[str]) -> List[str]:
        refs = list(
            dict.fromkeys(
                item.strip() for item in value if item and item.strip()
            )
        )
        return refs


class TradeSettlementRiskInput(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    confirmed_trade_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    trade_type: Literal["IMPORT", "EXPORT"]
    counterparty_relationship: CounterpartyRelationship
    advance_payment_ratio: Optional[str] = None
    balance_payment_method: BalancePaymentMethod
    payment_term_days: Optional[int] = Field(default=None, ge=0)
    payment_term_basis: PaymentTermBasis
    protection_information_status: ProtectionInformationStatus
    protection_mechanisms: List[ProtectionMechanism] = Field(
        default_factory=list
    )
    field_sources: Dict[str, FactSource]

    @field_validator("advance_payment_ratio", mode="before")
    @classmethod
    def validate_advance_payment_ratio(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None
        return canonical_ratio(value)

    @model_validator(mode="after")
    def validate_cross_field_contract(self) -> "TradeSettlementRiskInput":
        ratio = (
            Decimal(self.advance_payment_ratio)
            if self.advance_payment_ratio is not None
            else None
        )
        if ratio == 1 and self.balance_payment_method != "NOT_APPLICABLE":
            raise ValueError(
                "전액 선지급이면 잔여대금 결제방식은 NOT_APPLICABLE이어야 합니다."
            )
        if (
            ratio is None or ratio < 1
        ) and self.balance_payment_method == "NOT_APPLICABLE":
            raise ValueError(
                "잔여대금이 있거나 선지급 비율이 미확인이면 "
                "NOT_APPLICABLE을 사용할 수 없습니다."
            )
        if (
            ratio is None or ratio < 1
        ) and self.payment_term_basis == "NOT_APPLICABLE":
            raise ValueError(
                "잔여대금이 있거나 선지급 비율이 미확인이면 "
                "결제기간 기준을 NOT_APPLICABLE로 둘 수 없습니다."
            )

        unresolved_bases = {
            "EVENT_BASED_UNRESOLVED",
            "NOT_APPLICABLE",
            "UNKNOWN",
        }
        if (
            self.payment_term_basis in unresolved_bases
            and self.payment_term_days is not None
        ):
            raise ValueError(
                "미확정·사건기준·해당없음 결제기간에는 일수를 저장할 수 없습니다."
            )
        if (
            self.payment_term_basis
            in {"EXPLICIT_NET_TERM", "CONFIRMED_DATE_INTERVAL"}
            and self.payment_term_days is None
        ):
            raise ValueError("확정된 결제기간 기준에는 일수가 필요합니다.")

        if (
            self.protection_information_status == "DETAILS_PROVIDED"
            and not self.protection_mechanisms
        ):
            raise ValueError(
                "보호수단 상세가 있다고 확인했으면 보호수단이 하나 이상 필요합니다."
            )
        if (
            self.protection_information_status
            in {"UNKNOWN", "NONE_CONFIRMED"}
            and self.protection_mechanisms
        ):
            raise ValueError(
                "보호수단 미확인·없음 상태에는 보호수단 상세를 저장할 수 없습니다."
            )
        protection_types = [
            item.protection_type for item in self.protection_mechanisms
        ]
        if len(protection_types) != len(set(protection_types)):
            raise ValueError("같은 종류의 보호수단을 중복 입력할 수 없습니다.")
        ordered = sorted(
            self.protection_mechanisms,
            key=lambda item: (
                item.protection_type,
                item.applicability_status,
                item.source,
                tuple(item.evidence_refs),
            ),
        )
        object.__setattr__(self, "protection_mechanisms", ordered)

        missing_sources = REQUIRED_SOURCE_FIELDS.difference(
            self.field_sources
        )
        if missing_sources:
            raise ValueError(
                "위험입력 출처가 누락되었습니다: {}".format(
                    ", ".join(sorted(missing_sources))
                )
            )
        return self


class TradeRiskConfirmationRecord(StrictModel):
    confirmed_input: TradeSettlementRiskInput
    confirmed_at: str
    confirmed_by: Optional[str] = None
    trade_risk_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("confirmed_at")
    @classmethod
    def validate_confirmed_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "거래위험 확인시각은 ISO 8601 datetime이어야 합니다."
            ) from exc
        if parsed.tzinfo is None:
            raise ValueError("거래위험 확인시각에는 timezone offset이 필요합니다.")
        return value


class TradeRiskFactor(StrictModel):
    code: str
    effect: TradeRiskFactorEffect
    reason: str
    evidence_refs: List[str] = Field(default_factory=list)
    rule_version: str


class TradeSettlementRiskAssessment(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    calculation_version: str
    input_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    risk_type: TradeRiskType
    review_priority: TradeRiskReviewPriority
    factors: List[TradeRiskFactor] = Field(default_factory=list)
    review_needs: List[TradeRiskReviewNeed] = Field(default_factory=list)
    information_gaps: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
