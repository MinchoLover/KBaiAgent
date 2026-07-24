from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


DocumentType = Literal[
    "COMMERCIAL_INVOICE",
    "SALES_CONTRACT",
    "PURCHASE_ORDER",
    "UNKNOWN",
]
CompanyRole = Literal["BUYER", "SELLER"]
TradeType = Literal["IMPORT", "EXPORT", "UNKNOWN"]
ExtractionType = Literal["EXPLICIT", "DERIVED", "INFERRED"]
IssueSeverity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
DueDateSource = Literal[
    "EXPLICIT",
    "DERIVED",
    "INSTALLMENTS",
    "USER_CONFIRMED",
    "MISSING",
]


class StrictModel(BaseModel):
    """Common Pydantic v2 configuration for persisted JSON contracts."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class PaymentInstallment(StrictModel):
    sequence: Optional[int] = Field(
        default=None,
        ge=1,
        description="분할 지급 순서",
    )
    amount: Optional[str] = Field(
        default=None,
        description="양수 decimal 문자열. 예: 12500.00",
    )
    currency: Optional[str] = Field(
        default=None,
        description="ISO 4217 형태의 대문자 3글자 코드",
    )
    due_date: Optional[str] = Field(
        default=None,
        description="문서에 명시된 지급일 YYYY-MM-DD, 아니면 null",
    )
    condition: Optional[str] = Field(
        default=None,
        description="예: 30% advance 또는 after shipment",
    )


class FieldEvidence(StrictModel):
    field: str = Field(
        min_length=1,
        description="근거가 뒷받침하는 스키마 필드명",
    )
    page: Optional[int] = Field(
        default=None,
        ge=1,
        description="1부터 시작하는 페이지 번호. 모르면 null",
    )
    source_text: str = Field(
        min_length=1,
        description="문서에서 확인한 짧은 원문",
    )
    extraction_type: ExtractionType = Field(
        description="명시값, 결정론적 파생값, 또는 문맥 추론",
    )
    confidence_reason: str = Field(
        min_length=1,
        description="숫자 confidence가 아닌 근거/충돌에 대한 짧은 설명",
    )


class TradeDocumentExtraction(StrictModel):
    document_type: DocumentType
    document_number: Optional[str] = None

    seller_name: Optional[str] = None
    seller_country: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_country: Optional[str] = None

    company_role: CompanyRole
    trade_type: TradeType

    currency: Optional[str] = Field(
        default=None,
        description="ISO 4217 형태의 대문자 3글자 코드",
    )
    grand_total: Optional[str] = Field(
        default=None,
        description="기호와 구분자가 없는 양수 decimal 문자열",
    )
    amount_due: Optional[str] = Field(
        default=None,
        description="실제 미지급/미수 금액의 양수 decimal 문자열",
    )

    issue_date: Optional[str] = Field(
        default=None,
        description="발행일 YYYY-MM-DD",
    )
    contract_date: Optional[str] = Field(
        default=None,
        description="계약일 YYYY-MM-DD",
    )
    shipment_date: Optional[str] = Field(
        default=None,
        description="선적일 YYYY-MM-DD",
    )
    explicit_due_date: Optional[str] = Field(
        default=None,
        description="문서에 날짜로 직접 적힌 결제일 YYYY-MM-DD",
    )
    derived_due_date: Optional[str] = Field(
        default=None,
        description="Net N을 Python이 계산한 YYYY-MM-DD. 모델은 null 반환",
    )
    payment_terms: Optional[str] = None
    incoterm: Optional[str] = None

    installments: List[PaymentInstallment] = Field(default_factory=list)
    evidence: List[FieldEvidence] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    missing_required_fields: List[str] = Field(default_factory=list)
    needs_human_review: bool = True


class ConfirmationState(StrictModel):
    currency_confirmed: bool = False
    amount_due_confirmed: bool = False
    due_date_confirmed: bool = False
    confirmed_due_date: Optional[str] = None
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[str] = None

    def all_critical_fields_confirmed(
        self,
        installment_schedule_confirmed: bool = False,
    ) -> bool:
        return (
            self.currency_confirmed
            and self.amount_due_confirmed
            and self.due_date_confirmed
            and (
                bool(self.confirmed_due_date)
                or installment_schedule_confirmed
            )
        )


class ValidationIssue(StrictModel):
    code: str
    severity: IssueSeverity
    field: Optional[str] = None
    message: str


class ValidationResult(StrictModel):
    issues: List[ValidationIssue] = Field(default_factory=list)
    detected_currencies: List[str] = Field(default_factory=list)
    normalized_currency: Optional[str] = None
    resolved_due_date: Optional[str] = None
    due_date_source: DueDateSource = "MISSING"
    derived_trade_type: TradeType = "UNKNOWN"
    missing_required_fields: List[str] = Field(default_factory=list)
    needs_human_review: bool = True
    validation_pass: bool = False
    stage2_allowed: bool = False

    def has_severity(self, severity: IssueSeverity) -> bool:
        return any(issue.severity == severity for issue in self.issues)

    def has_blocking_issue(self) -> bool:
        return any(
            issue.severity in {"CRITICAL", "HIGH"}
            for issue in self.issues
        )
