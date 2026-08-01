import re
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Literal, Optional

from pydantic import Field, field_validator, model_validator

from schemas import StrictModel


TradeStatisticsProviderStatus = Literal[
    "LIVE",
    "OFFICIAL_FIXTURE",
    "NO_DATA",
    "MISSING_API_KEY",
    "VALIDATION_FAILED",
    "UPSTREAM_UNAVAILABLE",
    "UNSUPPORTED_COUNTRY",
    "STALE_DATA",
    "FIXTURE_NOT_AVAILABLE",
]
TradeStatisticsErrorCode = Literal[
    "MISSING_PARTNER_COUNTRY",
    "INVALID_COUNTRY_CODE",
    "MISSING_HS_CODE",
    "INVALID_HS_CODE",
    "MISSING_API_KEY",
    "INVALID_PERIOD",
    "UPSTREAM_TIMEOUT",
    "UPSTREAM_ERROR",
    "RESPONSE_PARSE_ERROR",
    "NO_DATA",
    "INSUFFICIENT_HISTORY",
    "STALE_DATA",
    "FIXTURE_NOT_AVAILABLE",
    "VALIDATION_FAILED",
    "UNSUPPORTED_COUNTRY",
]
TradeStatisticsScope = Literal["COUNTRY_TOTAL", "HS_ITEM"]
TradeStatisticsSourcePreference = Literal[
    "LIVE",
    "OFFICIAL_FIXTURE",
]
TradeStatisticsRecentDirection = Literal[
    "INCREASED",
    "DECREASED",
    "SIMILAR",
    "NOT_COMPARABLE",
]
TradeStatisticsComparisonStatus = Literal[
    "AVAILABLE",
    "PREVIOUS_ZERO",
    "INSUFFICIENT_HISTORY",
    "MISSING_MONTHS",
]


PERIOD_RE = re.compile(r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")
DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
HS_LEVELS = {2, 4, 6, 10}


def _decimal_value(value: str, field_name: str) -> Decimal:
    if not isinstance(value, str) or not DECIMAL_RE.fullmatch(value):
        raise ValueError(
            "{}은 과학표기 없는 Decimal 문자열이어야 합니다.".format(
                field_name
            )
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(
            "{}을 Decimal로 해석할 수 없습니다.".format(field_name)
        ) from exc
    if not parsed.is_finite():
        raise ValueError("{}은 유한한 Decimal이어야 합니다.".format(field_name))
    return parsed


class TradeStatisticsRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    reporter_country: str
    partner_country: str
    trade_direction: Literal["IMPORT", "EXPORT"]
    period_start: str
    period_end: str
    hs_code: Optional[str] = None
    hs_level: Optional[int] = None
    hs_code_confirmed: bool = False
    source_preference: TradeStatisticsSourcePreference
    provider: Literal["KOREA_CUSTOMS_OPEN_API"] = (
        "KOREA_CUSTOMS_OPEN_API"
    )
    snapshot_version: Optional[str] = None
    confirmed_transaction_fingerprint: str = Field(
        pattern=r"^[a-f0-9]{64}$"
    )

    @field_validator("reporter_country", "partner_country")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        normalized = value.strip().upper()
        aliases = {
            "KOREA": "KR",
            "REPUBLIC OF KOREA": "KR",
            "KOR": "KR",
            "BRAZIL": "BR",
            "BRA": "BR",
            "UNITED STATES": "US",
            "UNITED STATES OF AMERICA": "US",
            "USA": "US",
        }
        normalized = aliases.get(normalized, normalized)
        if not re.fullmatch(r"[A-Z]{2}", normalized):
            raise ValueError("국가는 ISO alpha-2 코드여야 합니다.")
        return normalized

    @field_validator("period_start", "period_end")
    @classmethod
    def validate_period(cls, value: str) -> str:
        if not PERIOD_RE.fullmatch(value):
            raise ValueError("관측기간은 YYYY-MM 형식이어야 합니다.")
        return value

    @field_validator("hs_code")
    @classmethod
    def validate_hs_code_format(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized.isdigit():
            raise ValueError("HS Code는 숫자로만 구성되어야 합니다.")
        if len(normalized) not in HS_LEVELS:
            raise ValueError("HS Code 길이는 2·4·6·10 중 하나여야 합니다.")
        return normalized

    @model_validator(mode="after")
    def validate_request_contract(self) -> "TradeStatisticsRequest":
        if self.period_start > self.period_end:
            raise ValueError("조회 시작월은 종료월보다 늦을 수 없습니다.")
        if self.hs_code is None:
            if self.hs_level is not None or self.hs_code_confirmed:
                raise ValueError("HS Code가 없으면 HS 확인 상태를 저장할 수 없습니다.")
        else:
            if not self.hs_code_confirmed:
                raise ValueError("품목 통계에는 사용자가 확인한 HS Code가 필요합니다.")
            if self.hs_level != len(self.hs_code):
                raise ValueError("HS level과 HS Code 길이가 일치해야 합니다.")
        if self.source_preference == "OFFICIAL_FIXTURE" and not (
            self.snapshot_version
        ):
            raise ValueError("official fixture에는 snapshot version이 필요합니다.")
        return self

    @property
    def scope(self) -> TradeStatisticsScope:
        return "HS_ITEM" if self.hs_code is not None else "COUNTRY_TOTAL"


class TradeStatisticsObservation(StrictModel):
    period: str
    reporter_country: str = Field(pattern=r"^[A-Z]{2}$")
    partner_country: str = Field(pattern=r"^[A-Z]{2}$")
    hs_code: Optional[str] = None
    hs_level: Optional[int] = None
    export_value_usd: str
    import_value_usd: str
    trade_balance_usd: str
    export_weight_kg: Optional[str] = None
    import_weight_kg: Optional[str] = None
    source_record_id: str = Field(min_length=1)
    observation_status: Literal[
        "OFFICIAL_REPORTED"
    ] = "OFFICIAL_REPORTED"

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str) -> str:
        if not PERIOD_RE.fullmatch(value):
            raise ValueError("observation period는 YYYY-MM이어야 합니다.")
        return value

    @model_validator(mode="after")
    def validate_values(self) -> "TradeStatisticsObservation":
        export = _decimal_value(self.export_value_usd, "export_value_usd")
        imported = _decimal_value(self.import_value_usd, "import_value_usd")
        balance = _decimal_value(
            self.trade_balance_usd,
            "trade_balance_usd",
        )
        if export < 0 or imported < 0:
            raise ValueError("수출·수입금액은 음수일 수 없습니다.")
        if abs((export - imported) - balance) > Decimal("1000"):
            raise ValueError("무역수지가 수출금액-수입금액과 일치하지 않습니다.")
        for name, value in (
            ("export_weight_kg", self.export_weight_kg),
            ("import_weight_kg", self.import_weight_kg),
        ):
            if value is not None and _decimal_value(value, name) < 0:
                raise ValueError("중량은 음수일 수 없습니다.")
        if self.hs_code is None and self.hs_level is not None:
            raise ValueError("HS Code 없이 HS level을 저장할 수 없습니다.")
        if self.hs_code is not None:
            if (
                not self.hs_code.isdigit()
                or len(self.hs_code) not in HS_LEVELS
                or self.hs_level != len(self.hs_code)
            ):
                raise ValueError("observation HS Code 계약이 올바르지 않습니다.")
        return self


class TradeStatisticsSourceReference(StrictModel):
    source_name: str
    official_url: str
    source_title: str
    observation_period: str
    source_as_of: str
    collected_at: str
    provider_status: TradeStatisticsProviderStatus


class TradeStatisticsSnapshot(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    snapshot_version: str
    snapshot_id: str
    source_name: str
    provider_status: TradeStatisticsProviderStatus
    collected_at: str
    observation_start: str
    observation_end: str
    source_as_of: str
    reporter_country: str = Field(pattern=r"^[A-Z]{2}$")
    partner_country: str = Field(pattern=r"^[A-Z]{2}$")
    hs_code: Optional[str] = None
    hs_level: Optional[int] = None
    observations: List[TradeStatisticsObservation] = Field(
        default_factory=list
    )
    raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalized_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    warnings: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_snapshot_contract(self) -> "TradeStatisticsSnapshot":
        if self.observation_start > self.observation_end:
            raise ValueError("snapshot 관측기간이 올바르지 않습니다.")
        keys = []
        periods = []
        for item in self.observations:
            if (
                item.reporter_country != self.reporter_country
                or item.partner_country != self.partner_country
                or item.hs_code != self.hs_code
                or item.hs_level != self.hs_level
            ):
                raise ValueError("snapshot과 observation 범위가 일치하지 않습니다.")
            key = (
                item.period,
                item.reporter_country,
                item.partner_country,
                item.hs_code,
            )
            keys.append(key)
            periods.append(item.period)
        if len(keys) != len(set(keys)):
            raise ValueError("중복 observation은 허용하지 않습니다.")
        if periods != sorted(periods):
            raise ValueError("observation은 월 오름차순이어야 합니다.")
        if periods and (
            periods[0] < self.observation_start
            or periods[-1] > self.observation_end
        ):
            raise ValueError("observation이 snapshot 관측기간을 벗어났습니다.")
        return self

    @property
    def scope(self) -> TradeStatisticsScope:
        return "HS_ITEM" if self.hs_code is not None else "COUNTRY_TOTAL"


class TradeStatisticsSummary(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    provider_status: TradeStatisticsProviderStatus
    scope: TradeStatisticsScope
    reporter_country: str = Field(pattern=r"^[A-Z]{2}$")
    partner_country: str = Field(pattern=r"^[A-Z]{2}$")
    trade_direction: Literal["IMPORT", "EXPORT"]
    hs_code: Optional[str] = None
    hs_level: Optional[int] = None
    observation_start: str
    observation_end: str
    latest_period: str
    latest_12m_export_usd: Optional[str] = None
    latest_12m_import_usd: Optional[str] = None
    latest_12m_balance_usd: Optional[str] = None
    previous_12m_export_usd: Optional[str] = None
    previous_12m_import_usd: Optional[str] = None
    previous_12m_balance_usd: Optional[str] = None
    export_yoy_pct: Optional[str] = None
    import_yoy_pct: Optional[str] = None
    export_comparison_status: TradeStatisticsComparisonStatus
    import_comparison_status: TradeStatisticsComparisonStatus
    recent_direction: TradeStatisticsRecentDirection
    available_month_count: int = Field(ge=0)
    missing_month_count: int = Field(ge=0)
    user_summary: str
    missing_information: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    source_refs: List[TradeStatisticsSourceReference] = Field(
        default_factory=list
    )


class TradeStatisticsResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    status: TradeStatisticsProviderStatus
    request: TradeStatisticsRequest
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshot: Optional[TradeStatisticsSnapshot] = None
    summary: Optional[TradeStatisticsSummary] = None
    error_code: Optional[TradeStatisticsErrorCode] = None
    user_message: str
    warnings: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result_contract(self) -> "TradeStatisticsResult":
        available = self.status in {"LIVE", "OFFICIAL_FIXTURE"}
        if available != bool(self.snapshot is not None and self.summary is not None):
            raise ValueError("통계 가용 상태와 snapshot·summary가 일치하지 않습니다.")
        if available and self.error_code is not None:
            raise ValueError("정상 통계 결과에는 오류 코드를 저장할 수 없습니다.")
        if not available and self.error_code is None:
            raise ValueError("통계 미가용 상태에는 오류 코드가 필요합니다.")
        return self
