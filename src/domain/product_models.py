import hashlib
import json
from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import Field, model_validator

from schemas import StrictModel


OfficialCandidateInputSource = Literal[
    "USER_CONFIRMED",
    "DOCUMENT_CONFIRMED",
    "COMPANY_PROFILE_CONFIRMED",
    "DERIVED_FROM_CONFIRMED_FIELDS",
    "UNKNOWN",
]


OFFICIAL_CANDIDATE_INPUT_FIELDS = (
    "shipment_status",
    "receivable_status",
    "trade_form",
    "customs_clearance",
    "relationship_scope",
    "credit_information_status",
    "credit_investigation_intent",
    "funding_purposes",
    "receivable_financing_intent",
    "early_cash_conversion_intent",
    "bank_financing_intent",
    "repayment_responsibility_acknowledgement",
    "short_term_export_insurance_linkage_review",
    "sme_status",
    "annual_export_band",
    "market_entry_purpose",
    "policy_finance_need",
    "production_or_working_capital_need",
)


FUNDING_PURPOSE_ORDER = (
    "MANUFACTURING",
    "PROCESSING",
    "RAW_MATERIAL_PROCUREMENT",
    "FINISHED_GOODS_PROCUREMENT",
    "EXPORT_PERFORMANCE",
    "RECEIVABLE_EARLY_CASH_CONVERSION",
    "GENERAL_WORKING_CAPITAL",
    "PRODUCTION_FACILITY",
    "NONE",
    "UNKNOWN",
)


class OfficialCandidateInputProfile(StrictModel):
    """사용자가 확인한 상품 후보 판단 사실의 최소 계약."""

    schema_version: Literal["1.0"] = "1.0"
    shipment_status: Literal[
        "PRE_SHIPMENT", "COMPLETED", "UNKNOWN"
    ] = "UNKNOWN"
    receivable_status: Literal[
        "EXISTS", "NOT_YET", "NONE", "UNKNOWN"
    ] = "UNKNOWN"
    trade_form: Literal[
        "GENERAL_EXPORT",
        "PROCESSING_TRADE",
        "INTERMEDIARY_TRADE",
        "RESALE_TRADE",
        "UNKNOWN",
    ] = "UNKNOWN"
    customs_clearance: Literal["YES", "NO", "UNKNOWN"] = "UNKNOWN"
    relationship_scope: Literal[
        "SINGLE_ONE_OFF",
        "RECURRING_SINGLE_BUYER",
        "RECURRING_MULTIPLE_BUYERS",
        "UNKNOWN",
    ] = "UNKNOWN"
    credit_information_status: Literal[
        "SUFFICIENT", "INSUFFICIENT", "UNKNOWN"
    ] = "UNKNOWN"
    credit_investigation_intent: Literal[
        "YES", "NO", "UNKNOWN"
    ] = "UNKNOWN"
    funding_purposes: List[
        Literal[
            "MANUFACTURING",
            "PROCESSING",
            "RAW_MATERIAL_PROCUREMENT",
            "FINISHED_GOODS_PROCUREMENT",
            "EXPORT_PERFORMANCE",
            "RECEIVABLE_EARLY_CASH_CONVERSION",
            "GENERAL_WORKING_CAPITAL",
            "PRODUCTION_FACILITY",
            "NONE",
            "UNKNOWN",
        ]
    ] = Field(default_factory=lambda: ["UNKNOWN"])
    receivable_financing_intent: Literal[
        "NONE", "NEGO_OR_PURCHASE", "KB_RECEIVABLE_PURCHASE", "UNKNOWN"
    ] = "UNKNOWN"
    early_cash_conversion_intent: Literal[
        "YES", "NO", "NOT_APPLICABLE", "UNKNOWN"
    ] = "UNKNOWN"
    bank_financing_intent: Literal["YES", "NO", "UNKNOWN"] = "UNKNOWN"
    repayment_responsibility_acknowledgement: Literal[
        "ACKNOWLEDGED", "NOT_ACKNOWLEDGED", "NOT_APPLICABLE", "UNKNOWN"
    ] = "UNKNOWN"
    short_term_export_insurance_linkage_review: Literal[
        "AGREED_TO_REVIEW", "NOT_AGREED", "NOT_APPLICABLE", "UNKNOWN"
    ] = "UNKNOWN"
    sme_status: Literal[
        "CONFIRMED", "NOT_CONFIRMED", "UNKNOWN"
    ] = "UNKNOWN"
    annual_export_band: Literal[
        "BELOW_USD_100K", "AT_LEAST_USD_100K", "UNKNOWN"
    ] = "UNKNOWN"
    market_entry_purpose: Literal["YES", "NO", "UNKNOWN"] = "UNKNOWN"
    policy_finance_need: Literal["YES", "NO", "UNKNOWN"] = "UNKNOWN"
    production_or_working_capital_need: Literal[
        "YES", "NO", "UNKNOWN"
    ] = "UNKNOWN"
    field_sources: Dict[str, OfficialCandidateInputSource] = Field(
        default_factory=dict
    )
    confirmed_at: Optional[str] = None
    confirmed_by: Optional[str] = None
    bound_transaction_fingerprint: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    input_fingerprint: Optional[str] = None

    @model_validator(mode="after")
    def validate_profile(self) -> "OfficialCandidateInputProfile":
        purposes = sorted(
            set(self.funding_purposes),
            key=FUNDING_PURPOSE_ORDER.index,
        )
        if not purposes:
            raise ValueError("funding_purposes는 비어 있을 수 없습니다.")
        if ("NONE" in purposes or "UNKNOWN" in purposes) and len(purposes) > 1:
            raise ValueError(
                "funding_purposes의 NONE/UNKNOWN은 다른 값과 함께 선택할 수 없습니다."
            )
        object.__setattr__(self, "funding_purposes", purposes)

        unexpected = set(self.field_sources) - set(
            OFFICIAL_CANDIDATE_INPUT_FIELDS
        )
        if unexpected:
            raise ValueError(
                "알 수 없는 상품 입력 provenance 필드가 있습니다: "
                + ", ".join(sorted(unexpected))
            )
        sources = {
            field_name: self.field_sources.get(field_name, "UNKNOWN")
            for field_name in OFFICIAL_CANDIDATE_INPUT_FIELDS
        }
        object.__setattr__(self, "field_sources", sources)

        for field_name in OFFICIAL_CANDIDATE_INPUT_FIELDS:
            value = getattr(self, field_name)
            is_unknown = (
                value == "UNKNOWN"
                or (
                    field_name == "funding_purposes"
                    and value == ["UNKNOWN"]
                )
            )
            if not is_unknown and sources[field_name] == "UNKNOWN":
                raise ValueError(
                    "확정 상품 입력값에는 provenance가 필요합니다: {}".format(
                        field_name
                    )
                )

        has_confirmation = any(
            source != "UNKNOWN" for source in sources.values()
        )
        if has_confirmation and (not self.confirmed_at or not self.confirmed_by):
            raise ValueError(
                "확인된 상품 입력에는 confirmed_at과 confirmed_by가 필요합니다."
            )
        if has_confirmation and self.bound_transaction_fingerprint is None:
            raise ValueError(
                "확인된 상품 입력에는 bound transaction fingerprint가 필요합니다."
            )
        if self.confirmed_at:
            try:
                parsed = datetime.fromisoformat(self.confirmed_at)
            except ValueError as exc:
                raise ValueError(
                    "confirmed_at은 ISO 8601 형식이어야 합니다."
                ) from exc
            if parsed.tzinfo is None:
                raise ValueError("confirmed_at에는 timezone offset이 필요합니다.")

        payload = {
            "schema_version": self.schema_version,
            "bound_transaction_fingerprint": (
                self.bound_transaction_fingerprint
            ),
            "values": {
                field_name: getattr(self, field_name)
                for field_name in OFFICIAL_CANDIDATE_INPUT_FIELDS
            },
            "field_sources": sources,
        }
        expected = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if self.input_fingerprint and self.input_fingerprint != expected:
            raise ValueError("상품 입력 fingerprint가 canonical 값과 다릅니다.")
        object.__setattr__(self, "input_fingerprint", expected)
        return self


OfficialCandidateProfileIssueSeverity = Literal[
    "HARD_BLOCK",
    "WARNING_AND_RECONFIRM",
]


class OfficialCandidateProfileIssue(StrictModel):
    code: str
    severity: OfficialCandidateProfileIssueSeverity
    field_names: List[str]
    user_message: str


class OfficialCandidateProfileValidation(StrictModel):
    issues: List[OfficialCandidateProfileIssue] = Field(default_factory=list)

    @property
    def hard_blocking_issues(self) -> List[OfficialCandidateProfileIssue]:
        return [
            issue for issue in self.issues if issue.severity == "HARD_BLOCK"
        ]

    @property
    def warning_issues(self) -> List[OfficialCandidateProfileIssue]:
        return [
            issue
            for issue in self.issues
            if issue.severity == "WARNING_AND_RECONFIRM"
        ]

    @property
    def recommendation_allowed(self) -> bool:
        return not self.hard_blocking_issues


def assess_official_candidate_input_profile(
    profile: OfficialCandidateInputProfile,
    *,
    has_confirmed_lc: bool = False,
) -> OfficialCandidateProfileValidation:
    """사용자가 수정할 수 있는 상품 입력의 교차 일관성을 판정한다."""

    issues: List[OfficialCandidateProfileIssue] = []

    def add_issue(
        code: str,
        severity: OfficialCandidateProfileIssueSeverity,
        field_names: List[str],
        user_message: str,
    ) -> None:
        issues.append(
            OfficialCandidateProfileIssue(
                code=code,
                severity=severity,
                field_names=field_names,
                user_message=user_message,
            )
        )

    positive_receivable_financing = (
        profile.receivable_financing_intent
        in {"NEGO_OR_PURCHASE", "KB_RECEIVABLE_PURCHASE"}
    )
    if (
        profile.shipment_status == "PRE_SHIPMENT"
        and profile.receivable_status == "EXISTS"
    ):
        add_issue(
            "PRE_SHIPMENT_RECEIVABLE_EXISTS",
            "HARD_BLOCK",
            ["shipment_status", "receivable_status"],
            "아직 선적 전인데 수출채권이 이미 발생한 것으로 선택했습니다. "
            "선적 상태와 채권 발생 여부를 다시 확인해 주세요.",
        )
    if (
        profile.receivable_status in {"NOT_YET", "NONE"}
        and positive_receivable_financing
    ):
        add_issue(
            "RECEIVABLE_UNAVAILABLE_FOR_FINANCING",
            "HARD_BLOCK",
            ["receivable_status", "receivable_financing_intent"],
            "현재 매입할 수출채권이 없는데 채권 매입·네고 계획이 선택됐습니다. "
            "두 항목 중 하나를 수정해 주세요.",
        )
    if profile.receivable_status in {"NOT_YET", "NONE"} and (
        profile.early_cash_conversion_intent == "YES"
        or "RECEIVABLE_EARLY_CASH_CONVERSION"
        in profile.funding_purposes
    ):
        add_issue(
            "RECEIVABLE_UNAVAILABLE_FOR_EARLY_CASH_CONVERSION",
            "HARD_BLOCK",
            [
                "receivable_status",
                "early_cash_conversion_intent",
                "funding_purposes",
            ],
            "현재 발생한 수출채권이 없는데 채권 조기 현금화 필요가 "
            "선택됐습니다. 채권 상태와 자금 목적을 다시 확인해 주세요.",
        )
    if (
        profile.early_cash_conversion_intent == "NO"
        and profile.receivable_financing_intent == "KB_RECEIVABLE_PURCHASE"
    ):
        add_issue(
            "KB_PURCHASE_WITHOUT_EARLY_CASH_NEED",
            "HARD_BLOCK",
            [
                "early_cash_conversion_intent",
                "receivable_financing_intent",
            ],
            "조기 현금화가 필요 없다고 확인했지만 KB 수출채권 매입 상담을 "
            "선택했습니다. 실제 자금조달 의사를 다시 확인해 주세요.",
        )
    if (
        profile.early_cash_conversion_intent == "NOT_APPLICABLE"
        and positive_receivable_financing
    ):
        add_issue(
            "RECEIVABLE_FINANCING_NOT_APPLICABLE",
            "HARD_BLOCK",
            [
                "early_cash_conversion_intent",
                "receivable_financing_intent",
            ],
            "채권 조기 현금화가 해당 없는데 채권 매입·네고 계획이 "
            "선택됐습니다. 적용 여부를 다시 확인해 주세요.",
        )
    if (
        profile.repayment_responsibility_acknowledgement == "NOT_APPLICABLE"
        and positive_receivable_financing
    ):
        add_issue(
            "REPAYMENT_ACKNOWLEDGEMENT_NOT_APPLICABLE",
            "HARD_BLOCK",
            [
                "repayment_responsibility_acknowledgement",
                "receivable_financing_intent",
            ],
            "채권 매입·네고를 검토하려면 수출자 상환책임 안내의 적용 여부를 "
            "확인해야 합니다.",
        )
    if profile.policy_finance_need == "NO" and (
        profile.market_entry_purpose == "YES"
        or profile.production_or_working_capital_need == "YES"
    ):
        add_issue(
            "POLICY_FINANCE_PURPOSE_CONFLICT",
            "HARD_BLOCK",
            [
                "policy_finance_need",
                "market_entry_purpose",
                "production_or_working_capital_need",
            ],
            "정책금융 상담은 원하지 않는다고 선택했지만 정책자금 목적 항목이 "
            "함께 선택됐습니다. 정책금융 의사와 자금 목적을 다시 확인해 주세요.",
        )

    if (
        profile.shipment_status == "PRE_SHIPMENT"
        and profile.customs_clearance == "YES"
    ):
        add_issue(
            "PRE_SHIPMENT_CUSTOMS_CLEARANCE_RECONFIRM",
            "WARNING_AND_RECONFIRM",
            ["shipment_status", "customs_clearance"],
            "선적 전인데 수출 통관을 완료한 상태가 맞는지 한 번 더 확인해 "
            "주세요.",
        )
    if (
        profile.shipment_status == "COMPLETED"
        and profile.receivable_status == "NOT_YET"
    ):
        add_issue(
            "COMPLETED_RECEIVABLE_NOT_YET_RECONFIRM",
            "WARNING_AND_RECONFIRM",
            ["shipment_status", "receivable_status"],
            "선적은 완료됐지만 수출채권은 아직 발생하지 않은 상태가 맞는지 "
            "결제조건과 함께 확인해 주세요.",
        )
    if (
        profile.credit_information_status == "INSUFFICIENT"
        and profile.credit_investigation_intent == "NO"
    ):
        add_issue(
            "CREDIT_INFORMATION_INSUFFICIENT_INVESTIGATION_DECLINED",
            "WARNING_AND_RECONFIRM",
            ["credit_information_status", "credit_investigation_intent"],
            "거래처 신용정보는 부족하지만 공식 신용조사는 원하지 않는 것으로 "
            "확인됩니다. 이 경우 신용조사 서비스는 표시하지 않습니다.",
        )
    if has_confirmed_lc and positive_receivable_financing:
        add_issue(
            "LC_WITH_NON_LC_RECEIVABLE_FINANCING_RECONFIRM",
            "WARNING_AND_RECONFIRM",
            ["receivable_financing_intent"],
            "확인된 결제방식은 L/C인데 무신용장 채권 매입·네고 의사가 "
            "선택됐습니다. 실제 결제방식과 상담 목적을 다시 확인해 주세요.",
        )
    return OfficialCandidateProfileValidation(issues=issues)


class OfficialSource(StrictModel):
    title: str
    url: str
    verified_at: str
    evidence_summary: str


class ProductVariant(StrictModel):
    variant_id: str
    official_name: str
    variant_type: Literal[
        "FORWARD",
        "PARTIAL_COVER_OPTION",
        "FULL_COVER_OPTION_EARLY_SETTLEMENT",
        "FULL_COVER_OPTION_MONTH_END",
    ]
    summary: str
    maximum_hedge_period: str
    early_settlement: Literal[
        "AVAILABLE",
        "UNAVAILABLE",
        "CONDITIONAL",
    ]
    upside_payment_obligation: Literal["REQUIRED", "NONE"]
    settlement_method: str
    limitations: List[str] = Field(default_factory=list)


class ProductRecord(StrictModel):
    product_id: str
    catalogue_id: Optional[str] = None
    name: str
    official_name: Optional[str] = None
    display_name: Optional[str] = None
    institution: str
    category: str
    product_type: Optional[str] = None
    candidate_family: Optional[str] = None
    source_status: Literal[
        "VERIFIED",
        "REVIEW_REQUIRED",
        "EXPIRED",
    ] = "VERIFIED"
    active: bool = True
    trade_types: List[str] = Field(default_factory=list)
    company_roles: List[str] = Field(default_factory=list)
    supported_review_areas: List[str] = Field(default_factory=list)
    required_signals: List[str] = Field(default_factory=list)
    required_any_signals: List[str] = Field(default_factory=list)
    excluded_signals: List[str] = Field(default_factory=list)
    deferral_signals: List[str] = Field(default_factory=list)
    prerequisite_information: List[str] = Field(default_factory=list)
    consultation_questions: List[str] = Field(default_factory=list)
    companion_candidate_ids: List[str] = Field(default_factory=list)
    replacement_or_successor_id: Optional[str] = None
    has_variants: bool = False
    auto_select_variant: bool = False
    variant_consultation_required: bool = False
    variants: List[ProductVariant] = Field(default_factory=list)
    variant_selection_questions: List[str] = Field(default_factory=list)
    customer_rate_available: Optional[bool] = None
    live_quote_available: Optional[bool] = None
    branch_limit_review_required: bool = False
    financial_shortlist_eligible: bool = True
    current_application_status: Optional[
        Literal["CONFIRMED_OPEN", "UNKNOWN", "CLOSED", "NOT_APPLICABLE"]
    ] = None
    keywords: List[str] = Field(default_factory=list)
    summary: str
    eligibility: str = "unknown"
    approval_status: str = "consultation_required"
    target_customers: List[str] = Field(default_factory=list)
    key_conditions: List[str] = Field(default_factory=list)
    required_documents: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    source: OfficialSource

    @model_validator(mode="after")
    def validate_catalogue_binding(self) -> "ProductRecord":
        if (
            self.catalogue_id is not None
            and self.catalogue_id != self.product_id
        ):
            raise ValueError(
                "catalogue_id는 stable product_id와 같아야 합니다."
            )
        if self.active and self.source_status != "VERIFIED":
            raise ValueError(
                "active catalogue 항목은 검증 완료 출처여야 합니다."
            )
        if self.auto_select_variant:
            raise ValueError("catalogue는 상품 하위 유형을 자동 선택할 수 없습니다.")
        if self.has_variants != bool(self.variants):
            raise ValueError(
                "has_variants와 구조화된 variant 목록이 일치해야 합니다."
            )
        if self.variants and not self.variant_consultation_required:
            raise ValueError(
                "상품 하위 유형이 있으면 상담 확인이 필요합니다."
            )
        variant_ids = [item.variant_id for item in self.variants]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError("상품 하위 유형 ID는 중복될 수 없습니다.")
        return self


class ProductCandidate(ProductRecord):
    relevance_score: str
    strategy_connection_reason: str = (
        "전략과의 연결은 공식자료 확인 후 상담이 필요합니다."
    )
    verification_status: Literal[
        "OFFICIAL_SOURCE_VERIFIED"
    ] = "OFFICIAL_SOURCE_VERIFIED"
    candidate_status: str = "CANDIDATE_REQUIRES_HUMAN_CONSULTATION"
    matched_consultation_categories: List[str] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    matched_review_areas: List[str] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    selection_reasons: List[str] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    deferred_reasons: List[str] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    explicit_profile_match: bool = Field(
        default=False,
        exclude_if=lambda value: not value,
    )


class AuxiliaryServiceCandidate(ProductRecord):
    candidate_status: Literal[
        "AUXILIARY_SERVICE_REQUIRES_HUMAN_CONSULTATION"
    ] = "AUXILIARY_SERVICE_REQUIRES_HUMAN_CONSULTATION"
    matched_signals: List[str] = Field(default_factory=list)
    selection_reasons: List[str] = Field(default_factory=list)


class AuxiliaryServiceCandidates(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    trade_type: Literal["IMPORT", "EXPORT"]
    candidates: List[AuxiliaryServiceCandidate] = Field(
        default_factory=list,
        max_length=3,
    )
    source_profile_fingerprint: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    source_transaction_fingerprint: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    suppressed_catalogue_ids: List[str] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    warnings: List[str] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )

    @model_validator(mode="after")
    def validate_grounding(self) -> "AuxiliaryServiceCandidates":
        if bool(self.source_profile_fingerprint) != bool(
            self.source_transaction_fingerprint
        ):
            raise ValueError(
                "보조서비스 profile과 transaction binding은 함께 필요합니다."
            )
        seen = set()
        for candidate in self.candidates:
            if (
                not candidate.catalogue_id
                or candidate.catalogue_id != candidate.product_id
                or not candidate.active
                or candidate.source_status != "VERIFIED"
                or candidate.product_type != "AUXILIARY_SERVICE"
                or candidate.financial_shortlist_eligible
            ):
                raise ValueError(
                    "보조서비스 후보는 active verified auxiliary catalogue 항목이어야 합니다."
                )
            if candidate.catalogue_id in seen:
                raise ValueError("보조서비스 catalogue_id는 중복될 수 없습니다.")
            if self.trade_type not in candidate.trade_types:
                raise ValueError(
                    "보조서비스 후보의 거래방향이 projection과 일치해야 합니다."
                )
            seen.add(candidate.catalogue_id)
        return self


class Stage4Result(StrictModel):
    schema_version: str = "1.0"
    mode: Literal["OFFLINE_KB", "OFFICIAL_WEB_SEARCH"]
    query: str
    candidates: List[ProductCandidate] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


OfficialCandidateEvaluationStatus = Literal[
    "ELIGIBLE",
    "ELIGIBLE_OVERFLOW",
    "DEFERRED_MISSING_INFORMATION",
    "EXCLUDED_CONFLICT",
    "EXCLUDED_NOT_APPLICABLE",
]


class OfficialCandidateEvaluation(StrictModel):
    catalogue_id: str
    status: OfficialCandidateEvaluationStatus
    reasons: List[str] = Field(default_factory=list)


class OfficialCandidateShortlist(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    trade_type: Literal["IMPORT", "EXPORT"]
    source_mode: Literal["OFFLINE_KB", "OFFICIAL_WEB_SEARCH"]
    query: str
    selection_policy: Literal[
        "CONSULTATION_CATEGORY_MATCH",
        "CATALOGUE_SIGNAL_FILTER_V1",
    ] = "CATALOGUE_SIGNAL_FILTER_V1"
    candidates: List[ProductCandidate] = Field(
        default_factory=list,
        max_length=3,
    )
    unmatched_consultation_categories: List[str] = Field(
        default_factory=list
    )
    deferred_catalogue_ids: List[str] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    excluded_catalogue_ids: List[str] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    eligible_overflow_candidates: List[ProductCandidate] = Field(
        default_factory=list,
        max_length=3,
        exclude_if=lambda value: not value,
    )
    overflow_reasons: Dict[str, str] = Field(
        default_factory=dict,
        exclude_if=lambda value: not value,
    )
    candidate_evaluations: List[OfficialCandidateEvaluation] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
    )
    source_profile_fingerprint: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
        exclude_if=lambda value: value is None,
    )
    source_transaction_fingerprint: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
        exclude_if=lambda value: value is None,
    )
    warnings: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_grounded_candidates(
        self,
    ) -> "OfficialCandidateShortlist":
        if bool(self.source_profile_fingerprint) != bool(
            self.source_transaction_fingerprint
        ):
            raise ValueError(
                "금융후보 profile과 transaction binding은 함께 필요합니다."
            )
        all_financial_candidates = (
            list(self.candidates) + list(self.eligible_overflow_candidates)
        )
        seen_catalogue_ids = set()
        for candidate in all_financial_candidates:
            if self.selection_policy == "CATALOGUE_SIGNAL_FILTER_V1":
                if (
                    not candidate.catalogue_id
                    or candidate.catalogue_id != candidate.product_id
                ):
                    raise ValueError(
                        "공식 후보에는 stable catalogue_id가 필요합니다."
                    )
                if (
                    not candidate.active
                    or candidate.source_status != "VERIFIED"
                ):
                    raise ValueError(
                        "비활성 또는 미검증 catalogue 항목은 후보가 될 수 없습니다."
                    )
                if (
                    not candidate.financial_shortlist_eligible
                    or candidate.product_type == "AUXILIARY_SERVICE"
                ):
                    raise ValueError(
                        "보조서비스는 공식 금융후보 shortlist에 포함할 수 없습니다."
                    )
            if self.trade_type not in candidate.trade_types:
                raise ValueError(
                    "공식 후보의 거래방향이 shortlist와 일치해야 합니다."
                )
            if not candidate.matched_consultation_categories:
                raise ValueError(
                    "공식 후보에는 연결된 상담 범주가 필요합니다."
                )
            if (
                candidate.catalogue_id is not None
                and candidate.catalogue_id in seen_catalogue_ids
            ):
                raise ValueError(
                    "Top 3와 후순위 적격 후보의 catalogue_id는 중복될 수 없습니다."
                )
            if candidate.catalogue_id is not None:
                seen_catalogue_ids.add(candidate.catalogue_id)
        evaluation_ids = [
            item.catalogue_id for item in self.candidate_evaluations
        ]
        if len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError("공식 후보 판정 catalogue_id는 중복될 수 없습니다.")
        return self
