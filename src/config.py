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
    openai_api_key: Optional[str] = field(default=None, repr=False)
    openai_model: str = "gpt-4o-mini"
    openai_fallback_model: str = "gpt-4o"
    openai_report_model: str = "gpt-4o-mini"
    openai_rag_model: str = "gpt-4o-mini"
    demo_mode: bool = True
    enable_live_document_extraction: bool = True
    enable_official_web_search: bool = False
    enable_stage3_optimizer: bool = True
    enable_product_rag: bool = True
    enable_llm_report: bool = True
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
    spot_rate_provider: str = "manual"
    manual_usdkrw_rate: Optional[str] = None
    koreaexim_key: Optional[str] = field(default=None, repr=False)
    ecos_key: Optional[str] = field(default=None, repr=False)
    credit_key: Optional[str] = field(default=None, repr=False)
    official_search_cache_ttl_hours: int = 24
    official_domains: Tuple[str, ...] = DEFAULT_OFFICIAL_DOMAINS

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_env=os.getenv("APP_ENV", "development").strip().lower(),
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
            enable_product_rag=_env_bool(
                "ENABLE_PRODUCT_RAG",
                True,
            ),
            enable_llm_report=_env_bool(
                "ENABLE_LLM_REPORT",
                True,
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
