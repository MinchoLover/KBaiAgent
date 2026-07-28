import re
from typing import Any, Dict, List, Literal, Optional, Union
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from schemas import StrictModel
from src.domain.trade_risk_models import (
    BalancePaymentMethod,
    CounterpartyRelationship,
    ProtectionInformationStatus,
    ProtectionMechanism,
)


SourceAxis = Literal[
    "OECD_PAYMENT_TRANSFER",
    "WORLD_BANK_MACRO_ENVIRONMENT",
    "WTO_TRADE_MARKET_ACCESS",
]
SnapshotValueFormat = Literal[
    "INTEGER",
    "DECIMAL_STRING",
    "TEXT",
    "DATE",
    "STATUS",
]
OecdClassificationStatus = Literal[
    "CLASSIFIED",
    "HIGH_INCOME_OECD_UNCLASSIFIED",
    "DATA_UNAVAILABLE",
]
CountryReviewPriority = Literal[
    "STANDARD_REVIEW",
    "ELEVATED_REVIEW",
    "HIGH_REVIEW",
    "INSUFFICIENT_INFORMATION",
]
CountryEnvironmentReviewNeed = Literal[
    "PAYMENT_TRANSFER_PROTECTION_REVIEW",
    "CREDIT_INSURANCE_REVIEW",
    "GUARANTEE_REVIEW",
    "DOCUMENTARY_CREDIT_TERMS_REVIEW",
    "PAYMENT_TERMS_REVIEW",
    "MACRO_ENVIRONMENT_MONITORING",
    "TRADE_MARKET_ACCESS_REVIEW",
    "INFORMATION_COMPLETENESS_REVIEW",
]
PriorityDirection = Literal[
    "NO_CHANGE",
    "MINIMUM_ELEVATED_REVIEW",
    "RAISE_TO_HIGH_REVIEW",
    "FAIL_CLOSED",
]


OFFICIAL_HOSTS = ("oecd.org", "worldbank.org", "wto.org")
DECIMAL_TEXT_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
DATE_OR_PERIOD_RE = re.compile(
    r"^(?:[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2}|"
    r"[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?"
    r"(?:\s+(?:to|through)\s+|/)"
    r"[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?)$"
)
WORLD_BANK_INDICATORS = {
    "NY.GDP.MKTP.KD.ZG",
    "FP.CPI.TOTL.ZG",
    "BN.CAB.XOKA.GD.ZS",
}


def is_official_https_url(value: str) -> bool:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    return bool(
        parsed.scheme == "https"
        and hostname
        and any(
            hostname == allowed or hostname.endswith("." + allowed)
            for allowed in OFFICIAL_HOSTS
        )
        and not parsed.username
        and not parsed.password
    )


class CountrySnapshotSourceRecord(StrictModel):
    source_record_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    source_name: Literal["OECD", "WORLD_BANK", "WTO"]
    source_axis: SourceAxis
    country: str = Field(pattern=r"^[A-Z]{2}$")
    indicator_code: Optional[str] = None
    official_url: str
    source_title: str
    as_of_date: str
    observation_period: str
    published_or_updated_at: str
    verified_at: str
    raw_value: Optional[Union[int, str]] = None
    raw_status: Optional[str] = None
    raw_unit: str
    value_format: SnapshotValueFormat
    interpretation: str
    limitations: str
    verification_status: Literal[
        "OFFICIAL_SOURCE_VERIFIED"
    ] = "OFFICIAL_SOURCE_VERIFIED"

    @field_validator("raw_value", mode="before")
    @classmethod
    def reject_float_and_boolean_raw_values(
        cls,
        value: Any,
    ) -> Any:
        if isinstance(value, bool) or isinstance(value, float):
            raise ValueError(
                "snapshot 원값은 float·boolean이 아닌 정수 또는 문자열이어야 합니다."
            )
        return value

    @field_validator("official_url")
    @classmethod
    def validate_official_url(cls, value: str) -> str:
        if not is_official_https_url(value):
            raise ValueError(
                "OECD·World Bank·WTO 공식 HTTPS URL만 허용합니다."
            )
        return value

    @field_validator(
        "as_of_date",
        "observation_period",
        "published_or_updated_at",
        "verified_at",
    )
    @classmethod
    def validate_date_or_period(cls, value: str) -> str:
        if not DATE_OR_PERIOD_RE.fullmatch(value):
            raise ValueError(
                "날짜·관측기간은 YYYY, YYYY-MM-DD 또는 명시적 기간이어야 합니다."
            )
        return value

    @model_validator(mode="after")
    def validate_source_contract(self) -> "CountrySnapshotSourceRecord":
        if self.raw_value is None and not self.raw_status:
            raise ValueError("source record에는 raw value 또는 status가 필요합니다.")
        if self.value_format == "INTEGER" and not (
            isinstance(self.raw_value, int)
            and not isinstance(self.raw_value, bool)
        ):
            raise ValueError("INTEGER 원값은 정수여야 합니다.")
        if self.value_format == "DECIMAL_STRING":
            if not (
                isinstance(self.raw_value, str)
                and DECIMAL_TEXT_RE.fullmatch(self.raw_value)
            ):
                raise ValueError(
                    "경제 소수 원값은 과학표기 없는 Decimal 문자열이어야 합니다."
                )
        if (
            self.source_axis == "WORLD_BANK_MACRO_ENVIRONMENT"
            and self.indicator_code not in WORLD_BANK_INDICATORS
        ):
            raise ValueError("승인된 World Bank 지표 코드가 필요합니다.")
        expected_source = {
            "OECD_PAYMENT_TRANSFER": "OECD",
            "WORLD_BANK_MACRO_ENVIRONMENT": "WORLD_BANK",
            "WTO_TRADE_MARKET_ACCESS": "WTO",
        }[self.source_axis]
        if self.source_name != expected_source:
            raise ValueError("source name과 source axis가 일치하지 않습니다.")
        return self


class CountryEnvironmentSnapshot(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    snapshot_version: str
    snapshot_id: str
    supported_countries: List[str]
    generated_or_curated_at: str
    source_records: List[CountrySnapshotSourceRecord]
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("generated_or_curated_at")
    @classmethod
    def validate_curated_datetime(cls, value: str) -> str:
        if not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
            r"[0-9]{2}:[0-9]{2}:[0-9]{2}[+-][0-9]{2}:[0-9]{2}",
            value,
        ):
            raise ValueError("snapshot 생성시각은 timezone 포함 ISO datetime이어야 합니다.")
        return value

    @model_validator(mode="after")
    def validate_snapshot_contract(self) -> "CountryEnvironmentSnapshot":
        if self.supported_countries != ["BR", "US"]:
            raise ValueError("v1 snapshot은 BR·US만 정렬된 순서로 지원합니다.")
        record_ids = [
            item.source_record_id for item in self.source_records
        ]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("source_record_id는 중복될 수 없습니다.")
        for record in self.source_records:
            if record.country not in self.supported_countries:
                raise ValueError(
                    "source record country가 지원 국가와 일치하지 않습니다."
                )
        for country in self.supported_countries:
            country_records = [
                item for item in self.source_records
                if item.country == country
            ]
            axes = {item.source_axis for item in country_records}
            if axes != {
                "OECD_PAYMENT_TRANSFER",
                "WORLD_BANK_MACRO_ENVIRONMENT",
                "WTO_TRADE_MARKET_ACCESS",
            }:
                raise ValueError(
                    "{}의 세 공식 source axis가 모두 필요합니다.".format(
                        country
                    )
                )
            wb_codes = {
                item.indicator_code
                for item in country_records
                if (
                    item.source_axis
                    == "WORLD_BANK_MACRO_ENVIRONMENT"
                )
            }
            if wb_codes != WORLD_BANK_INDICATORS:
                raise ValueError(
                    "{}의 World Bank 지표 세 종류가 모두 필요합니다.".format(
                        country
                    )
                )
        oecd_records = {
            item.country: item
            for item in self.source_records
            if item.source_axis == "OECD_PAYMENT_TRANSFER"
        }
        brazil = oecd_records["BR"]
        united_states = oecd_records["US"]
        if (
            brazil.as_of_date != "2026-06-26"
            or brazil.raw_value != 4
            or brazil.raw_status != "CLASSIFIED"
        ):
            raise ValueError("Brazil OECD 공식 원값 계약이 일치하지 않습니다.")
        if (
            united_states.as_of_date != "2026-06-26"
            or united_states.raw_value is not None
            or united_states.raw_status
            != "HIGH_INCOME_OECD_UNCLASSIFIED"
        ):
            raise ValueError("US OECD 미분류 계약이 일치하지 않습니다.")
        return self


class CountryTradeEnvironmentInput(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    confirmed_trade_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    country_confirmation_status: Literal[
        "USER_CONFIRMED"
    ] = "USER_CONFIRMED"
    trade_type: Literal["IMPORT", "EXPORT"]
    counterparty_country: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    counterparty_relationship: CounterpartyRelationship
    balance_payment_method: BalancePaymentMethod
    payment_term_days: Optional[int] = Field(default=None, ge=0)
    protection_information_status: ProtectionInformationStatus
    protection_mechanisms: List[ProtectionMechanism] = Field(
        default_factory=list
    )

    @field_validator("counterparty_country")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        normalized = value.strip().upper()
        aliases = {
            "UNITED STATES": "US",
            "UNITED STATES OF AMERICA": "US",
            "USA": "US",
            "BRAZIL": "BR",
            "BRA": "BR",
        }
        normalized = aliases.get(normalized, normalized)
        if not re.fullmatch(r"[A-Z]{2}", normalized):
            raise ValueError("거래 상대국은 ISO alpha-2 코드여야 합니다.")
        return normalized

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_protection_contract(
        self,
    ) -> "CountryTradeEnvironmentInput":
        if (
            self.protection_information_status == "DETAILS_PROVIDED"
            and not self.protection_mechanisms
        ):
            raise ValueError("보호수단 상세가 있으면 항목이 하나 이상 필요합니다.")
        if (
            self.protection_information_status
            in {"UNKNOWN", "NONE_CONFIRMED"}
            and self.protection_mechanisms
        ):
            raise ValueError("미확인·없음 상태에는 보호수단을 저장할 수 없습니다.")
        return self


class OfficialSourceReference(StrictModel):
    source_record_id: str
    source_name: str
    source_axis: SourceAxis
    official_url: str
    source_title: str
    as_of_date: str
    observation_period: str
    verified_at: str


class OecdPaymentTransferSignal(StrictModel):
    status: OecdClassificationStatus
    raw_classification: Optional[int] = None
    raw_unit: str
    as_of_date: str
    interpretation: str
    limitations: str
    action_signals: List[Literal[
        "PAYMENT_TRANSFER_PROTECTION_REVIEW_REQUIRED"
    ]] = Field(default_factory=list)
    source_record_id: Optional[str] = None


class WorldBankIndicatorObservation(StrictModel):
    source_record_id: str
    indicator_code: str
    indicator_name: str
    raw_value: Optional[str] = None
    raw_status: Optional[str] = None
    raw_unit: str
    as_of_date: str
    observation_period: str
    interpretation: str
    limitations: str


class WorldBankMacroEnvironmentSignal(StrictModel):
    status: Literal["AVAILABLE", "DATA_UNAVAILABLE"]
    observations: List[WorldBankIndicatorObservation] = Field(
        default_factory=list
    )
    warnings: List[str] = Field(default_factory=list)
    interpretation: str
    limitations: List[str] = Field(default_factory=list)


class WtoTradeObservation(StrictModel):
    source_record_id: str
    indicator_code: str
    raw_value: Optional[str] = None
    raw_status: Optional[str] = None
    raw_unit: str
    as_of_date: str
    observation_period: str
    interpretation: str
    limitations: str


class WtoTradeMarketAccessSignal(StrictModel):
    status: Literal["AVAILABLE", "DATA_UNAVAILABLE"]
    observations: List[WtoTradeObservation] = Field(default_factory=list)
    interpretation: str
    limitations: List[str] = Field(default_factory=list)


class CountryEnvironmentRuleContribution(StrictModel):
    rule_code: str
    source_axis: Optional[SourceAxis] = None
    observed_value_or_status: str
    review_need: Optional[CountryEnvironmentReviewNeed] = None
    priority_direction: PriorityDirection
    reason: str


class CountryTradeEnvironmentAssessment(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    country: str
    trade_type: Literal["IMPORT", "EXPORT"]
    review_priority: CountryReviewPriority
    oecd_payment_transfer: OecdPaymentTransferSignal
    world_bank_macro_environment: WorldBankMacroEnvironmentSignal
    wto_trade_market_access: WtoTradeMarketAccessSignal
    review_needs: List[CountryEnvironmentReviewNeed] = Field(
        default_factory=list
    )
    rule_contributions: List[CountryEnvironmentRuleContribution] = Field(
        default_factory=list
    )
    reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    warning_codes: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    official_source_references: List[OfficialSourceReference] = Field(
        default_factory=list
    )
    snapshot_version: str
    snapshot_id: str
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    rule_version: str
    source_record_ids: List[str] = Field(default_factory=list)
    input_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class CountryEnvironmentTrace(StrictModel):
    country: str
    snapshot_id: str
    rule_version: str
    review_priority: CountryReviewPriority
    source_record_ids: List[str] = Field(default_factory=list)
    warning_codes: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)
