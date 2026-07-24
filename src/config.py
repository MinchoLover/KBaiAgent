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
    openai_api_key: Optional[str] = field(default=None, repr=False)
    openai_model: str = "gpt-4o-mini"
    openai_fallback_model: str = "gpt-4o"
    openai_report_model: str = "gpt-4o-mini"
    openai_rag_model: str = "gpt-4o-mini"
    demo_mode: bool = True
    enable_live_document_extraction: bool = True
    enable_official_web_search: bool = False
    stage1_mode: str = "manual"
    stage1_base_url: str = ""
    stage1_allow_private_endpoints: bool = False
    stage1_allowed_hosts: Tuple[str, ...] = ()
    max_upload_mb: int = 15
    max_pdf_pages: int = 20
    openai_timeout_seconds: float = 60.0
    stage1_timeout_seconds: float = 10.0
    official_search_cache_ttl_hours: int = 24
    official_domains: Tuple[str, ...] = DEFAULT_OFFICIAL_DOMAINS

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
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
                True,
            ),
            enable_official_web_search=_env_bool(
                "ENABLE_OFFICIAL_WEB_SEARCH",
                False,
            ),
            stage1_mode=os.getenv("STAGE1_MODE", "manual").strip().lower(),
            stage1_base_url=os.getenv("STAGE1_BASE_URL", "").strip(),
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
