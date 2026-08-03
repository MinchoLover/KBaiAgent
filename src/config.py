import os
from dataclasses import dataclass, field
from typing import Optional, Tuple


DEFAULT_OFFICIAL_DOMAINS: Tuple[str, ...] = (
    "kbstar.com",
    "kbfg.com",
    "ksure.or.kr",
    "kosmes.or.kr",
    "bizinfo.go.kr",
    "kodit.co.kr",
    "kibo.or.kr",
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_csv(name: str, default: Tuple[str, ...]) -> Tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    items = tuple(
        item.strip().lower()
        for item in value.split(",")
        if item.strip()
    )
    return items


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    show_internal_debug: bool = False
    openai_api_key: Optional[str] = field(default=None, repr=False)
    openai_model: str = "gpt-4o-mini"
    openai_fallback_model: str = "gpt-4o"
    openai_report_model: str = "gpt-4o-mini"
    openai_rag_model: str = "gpt-4o-mini"
    demo_mode: bool = True
    enable_live_document_extraction: bool = True
    enable_official_web_search: bool = False
    enable_stage3_optimizer: bool = True
    enable_kb_macro_hedge_reference: bool = False
    enable_product_rag: bool = True
    enable_llm_report: bool = True
    enable_country_economic_interpretation: bool = False
    enable_trade_statistics_interpretation: bool = False
    stage1_mode: str = "manual"
    stage1_provider: str = "http"
    stage1_base_url: str = "http://127.0.0.1:8765"
    stage1_forecast_file: str = (
        "src/integration_assets/stage1/latest_forecast.json"
    )
    stage1_allow_private_endpoints: bool = False
    stage1_allowed_hosts: Tuple[str, ...] = ()
    max_upload_mb: int = 15
    max_pdf_pages: int = 20
    openai_timeout_seconds: float = 60.0
    stage1_timeout_seconds: float = 10.0
    stage1_http_timeout_seconds: float = 10.0
    stage1_http_retries: int = 1
    stage1_max_response_bytes: int = 1024 * 1024
    stage1_max_staleness_market_days: int = 3
    stage1_max_path_return: str = "0.50"
    kb_macro_hedge_mode: str = "off"
    kb_macro_hedge_allowed_root: str = ""
    kb_macro_forecast_file: str = ""
    kb_macro_hedge_file: str = ""
    kb_macro_model_config_file: str = (
        "configs/hedge_recommendation_v1.json"
    )
    kb_macro_market_history_file: str = (
        "web_runtime/bundle_v1/market_history.csv"
    )
    kb_macro_quote_template_file: str = (
        "examples/mock_company_exposure.json"
    )
    kb_macro_expected_provider_commit_sha: str = ""
    kb_macro_expected_forecast_sha256: str = ""
    kb_macro_expected_hedge_sha256: str = ""
    kb_macro_expected_model_config_sha256: str = ""
    kb_macro_expected_market_history_sha256: str = ""
    kb_macro_expected_quote_template_sha256: str = ""
    kb_macro_max_file_bytes: int = 1024 * 1024
    kb_macro_cli_timeout_seconds: float = 30.0
    kb_macro_cli_max_output_bytes: int = 64 * 1024
    spot_rate_provider: str = "manual"
    manual_usdkrw_rate: Optional[str] = None
    koreaexim_key: Optional[str] = field(default=None, repr=False)
    ecos_key: Optional[str] = field(default=None, repr=False)
    credit_key: Optional[str] = field(default=None, repr=False)
    customs_trade_api_key: Optional[str] = field(
        default=None,
        repr=False,
    )
    trade_statistics_provider: str = "auto"
    trade_statistics_timeout_seconds: float = 10.0
    trade_statistics_snapshot_version: str = (
        "2026.08.01-kr-br-country-v1"
    )
    official_search_cache_ttl_hours: int = 24
    official_domains: Tuple[str, ...] = DEFAULT_OFFICIAL_DOMAINS

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_env=os.getenv("APP_ENV", "development").strip().lower(),
            show_internal_debug=_env_bool("SHOW_INTERNAL_DEBUG", False),
            openai_api_key=(
                os.getenv("OPENAI_API_KEY")
                or os.getenv("OPEN_AI_API_KEY")
                or None
            ),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            openai_fallback_model=os.getenv(
                "OPENAI_FALLBACK_MODEL",
                "gpt-4o",
            ),
            openai_report_model=os.getenv(
                "OPENAI_REPORT_MODEL",
                "gpt-4o-mini",
            ),
            openai_rag_model=os.getenv(
                "OPENAI_RAG_MODEL",
                "gpt-4o-mini",
            ),
            demo_mode=_env_bool("DEMO_MODE", True),
            enable_live_document_extraction=_env_bool(
                "ENABLE_LIVE_DOCUMENT_EXTRACTION",
                _env_bool("ENABLE_DOCUMENT_AI", True),
            ),
            enable_official_web_search=_env_bool(
                "ENABLE_OFFICIAL_WEB_SEARCH",
                False,
            ),
            enable_stage3_optimizer=_env_bool(
                "ENABLE_STAGE3_OPTIMIZER",
                True,
            ),
            enable_kb_macro_hedge_reference=_env_bool(
                "ENABLE_KB_MACRO_HEDGE_REFERENCE",
                False,
            ),
            enable_product_rag=_env_bool(
                "ENABLE_PRODUCT_RAG",
                True,
            ),
            enable_llm_report=_env_bool(
                "ENABLE_LLM_REPORT",
                True,
            ),
            enable_country_economic_interpretation=_env_bool(
                "ENABLE_COUNTRY_ECONOMIC_INTERPRETATION",
                False,
            ),
            enable_trade_statistics_interpretation=_env_bool(
                "ENABLE_TRADE_STATISTICS_INTERPRETATION",
                False,
            ),
            stage1_mode=os.getenv("STAGE1_MODE", "manual").strip().lower(),
            stage1_provider=os.getenv(
                "STAGE1_PROVIDER",
                "http",
            ).strip().lower(),
            stage1_base_url=os.getenv(
                "STAGE1_BASE_URL",
                "http://127.0.0.1:8765",
            ).strip(),
            stage1_forecast_file=os.getenv(
                "STAGE1_FORECAST_FILE",
                "src/integration_assets/stage1/latest_forecast.json",
            ).strip(),
            stage1_allow_private_endpoints=_env_bool(
                "STAGE1_ALLOW_PRIVATE_ENDPOINTS",
                False,
            ),
            stage1_allowed_hosts=_env_csv(
                "STAGE1_ALLOWED_HOSTS",
                (),
            ),
            max_upload_mb=_env_int("MAX_UPLOAD_MB", 15),
            max_pdf_pages=_env_int("MAX_PDF_PAGES", 20),
            openai_timeout_seconds=_env_float(
                "OPENAI_TIMEOUT_SECONDS",
                60.0,
            ),
            stage1_timeout_seconds=_env_float(
                "STAGE1_TIMEOUT_SECONDS",
                10.0,
            ),
            stage1_http_timeout_seconds=_env_float(
                "STAGE1_HTTP_TIMEOUT_SECONDS",
                _env_float("STAGE1_TIMEOUT_SECONDS", 10.0),
            ),
            stage1_http_retries=_env_int(
                "STAGE1_HTTP_RETRIES",
                1,
            ),
            stage1_max_response_bytes=_env_int(
                "STAGE1_MAX_RESPONSE_BYTES",
                1024 * 1024,
            ),
            stage1_max_staleness_market_days=_env_int(
                "STAGE1_MAX_STALENESS_MARKET_DAYS",
                3,
            ),
            stage1_max_path_return=os.getenv(
                "STAGE1_MAX_PATH_RETURN",
                "0.50",
            ).strip(),
            kb_macro_hedge_mode=os.getenv(
                "KB_MACRO_HEDGE_MODE",
                "off",
            ).strip().lower(),
            kb_macro_hedge_allowed_root=os.getenv(
                "KB_MACRO_HEDGE_ALLOWED_ROOT",
                "",
            ).strip(),
            kb_macro_forecast_file=os.getenv(
                "KB_MACRO_FORECAST_FILE",
                "",
            ).strip(),
            kb_macro_hedge_file=os.getenv(
                "KB_MACRO_HEDGE_FILE",
                "",
            ).strip(),
            kb_macro_model_config_file=os.getenv(
                "KB_MACRO_MODEL_CONFIG_FILE",
                "configs/hedge_recommendation_v1.json",
            ).strip(),
            kb_macro_market_history_file=os.getenv(
                "KB_MACRO_MARKET_HISTORY_FILE",
                "web_runtime/bundle_v1/market_history.csv",
            ).strip(),
            kb_macro_quote_template_file=os.getenv(
                "KB_MACRO_QUOTE_TEMPLATE_FILE",
                "examples/mock_company_exposure.json",
            ).strip(),
            kb_macro_expected_provider_commit_sha=os.getenv(
                "KB_MACRO_EXPECTED_PROVIDER_COMMIT_SHA",
                "",
            ).strip().lower(),
            kb_macro_expected_forecast_sha256=os.getenv(
                "KB_MACRO_EXPECTED_FORECAST_SHA256",
                "",
            ).strip().lower(),
            kb_macro_expected_hedge_sha256=os.getenv(
                "KB_MACRO_EXPECTED_HEDGE_SHA256",
                "",
            ).strip().lower(),
            kb_macro_expected_model_config_sha256=os.getenv(
                "KB_MACRO_EXPECTED_MODEL_CONFIG_SHA256",
                "",
            ).strip().lower(),
            kb_macro_expected_market_history_sha256=os.getenv(
                "KB_MACRO_EXPECTED_MARKET_HISTORY_SHA256",
                "",
            ).strip().lower(),
            kb_macro_expected_quote_template_sha256=os.getenv(
                "KB_MACRO_EXPECTED_QUOTE_TEMPLATE_SHA256",
                "",
            ).strip().lower(),
            kb_macro_max_file_bytes=_env_int(
                "KB_MACRO_MAX_FILE_BYTES",
                1024 * 1024,
            ),
            kb_macro_cli_timeout_seconds=_env_float(
                "KB_MACRO_CLI_TIMEOUT_SECONDS",
                30.0,
            ),
            kb_macro_cli_max_output_bytes=_env_int(
                "KB_MACRO_CLI_MAX_OUTPUT_BYTES",
                64 * 1024,
            ),
            spot_rate_provider=os.getenv(
                "SPOT_RATE_PROVIDER",
                "manual",
            ).strip().lower(),
            manual_usdkrw_rate=(
                os.getenv("MANUAL_USDKRW_RATE") or None
            ),
            koreaexim_key=os.getenv("KOREAEXIM_KEY") or None,
            ecos_key=os.getenv("ECOS_KEY") or None,
            credit_key=os.getenv("CREDIT_KEY") or None,
            customs_trade_api_key=(
                os.getenv("CUSTOMS_TRADE_API_KEY") or None
            ),
            trade_statistics_provider=os.getenv(
                "TRADE_STATISTICS_PROVIDER",
                "auto",
            ).strip().lower(),
            trade_statistics_timeout_seconds=_env_float(
                "TRADE_STATISTICS_TIMEOUT_SECONDS",
                10.0,
            ),
            trade_statistics_snapshot_version=os.getenv(
                "TRADE_STATISTICS_SNAPSHOT_VERSION",
                "2026.08.01-kr-br-country-v1",
            ).strip(),
            official_search_cache_ttl_hours=_env_int(
                "OFFICIAL_SEARCH_CACHE_TTL_HOURS",
                24,
            ),
            official_domains=_env_csv(
                "OFFICIAL_DOMAINS",
                DEFAULT_OFFICIAL_DOMAINS,
            ),
        )

    @property
    def live_extraction_ready(self) -> bool:
        return bool(
            self.openai_api_key
            and self.enable_live_document_extraction
        )
