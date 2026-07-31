import json
import ipaddress
import socket
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlsplit

from src.domain.stage1_web_models import (
    ProviderHealth,
    Stage1ForecastLoadResult,
)
from src.stage1.web_forecast import (
    MAX_RAW_FORECAST_BYTES,
    normalize_stage1_web_forecast,
)


HttpFetcher = Callable[[str, float, int], bytes]


class Stage1ProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _checked_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_object(body: bytes) -> Dict[str, Any]:
    if len(body) > MAX_RAW_FORECAST_BYTES:
        raise Stage1ProviderError(
            "RESPONSE_TOO_LARGE",
            "Stage 1 응답이 허용 크기를 초과했습니다.",
        )
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Stage1ProviderError(
            "INVALID_JSON",
            "Stage 1 응답이 올바른 UTF-8 JSON이 아닙니다.",
        ) from exc
    if not isinstance(payload, dict):
        raise Stage1ProviderError(
            "INVALID_JSON_TYPE",
            "Stage 1 응답은 JSON object여야 합니다.",
        )
    return payload


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        del request, file_pointer, code, message, headers, new_url
        return None


def _default_http_fetch(
    url: str,
    timeout_seconds: float,
    maximum_bytes: int,
) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "KBaiAgent-stage1-adapter/1.0",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            content_type = str(
                response.headers.get("Content-Type", "")
            ).lower()
            if "application/json" not in content_type:
                raise Stage1ProviderError(
                    "INVALID_CONTENT_TYPE",
                    "Stage 1 응답 Content-Type이 JSON이 아닙니다.",
                )
            declared_length = response.headers.get("Content-Length")
            if (
                declared_length
                and int(declared_length) > maximum_bytes
            ):
                raise Stage1ProviderError(
                    "RESPONSE_TOO_LARGE",
                    "Stage 1 응답이 허용 크기를 초과했습니다.",
                )
            body = response.read(maximum_bytes + 1)
    except Stage1ProviderError:
        raise
    except urllib.error.HTTPError as exc:
        raise Stage1ProviderError(
            "HTTP_STATUS_{}".format(exc.code),
            "Stage 1 HTTP 서비스가 오류 상태를 반환했습니다.",
        ) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise Stage1ProviderError(
            "HTTP_UNAVAILABLE",
            "Stage 1 HTTP 서비스에 연결하지 못했습니다.",
        ) from exc
    if len(body) > maximum_bytes:
        raise Stage1ProviderError(
            "RESPONSE_TOO_LARGE",
            "Stage 1 응답이 허용 크기를 초과했습니다.",
        )
    return body


def _validate_base_url(
    base_url: str,
    *,
    allow_private_endpoints: bool,
    allowed_hosts: Tuple[str, ...],
) -> str:
    parsed = urlsplit(base_url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise Stage1ProviderError(
            "INVALID_BASE_URL",
            "Stage 1 base URL은 http 또는 https여야 합니다.",
        )
    if not parsed.hostname or parsed.username or parsed.password:
        raise Stage1ProviderError(
            "INVALID_BASE_URL",
            "Stage 1 base URL 형식이 올바르지 않습니다.",
        )
    if parsed.query or parsed.fragment:
        raise Stage1ProviderError(
            "INVALID_BASE_URL",
            "Stage 1 base URL에는 query나 fragment를 사용할 수 없습니다.",
        )
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme == "http" and parsed.hostname not in local_hosts:
        raise Stage1ProviderError(
            "INSECURE_REMOTE_URL",
            "원격 Stage 1 서비스는 HTTPS를 사용해야 합니다.",
        )
    hostname = parsed.hostname.lower()
    if hostname not in local_hosts:
        normalized_allowed = {
            item.strip().lower()
            for item in allowed_hosts
            if item.strip()
        }
        if hostname not in normalized_allowed:
            raise Stage1ProviderError(
                "HOST_NOT_ALLOWED",
                "원격 Stage 1 host는 STAGE1_ALLOWED_HOSTS에 등록해야 합니다.",
            )
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if (
            address is not None
            and not address.is_global
            and not allow_private_endpoints
        ):
            raise Stage1ProviderError(
                "PRIVATE_HOST_BLOCKED",
                "사설 Stage 1 IP는 명시적으로 허용해야 합니다.",
            )
    return base_url.strip().rstrip("/")


class Stage1ForecastProvider(ABC):
    @abstractmethod
    def fetch_latest(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> ProviderHealth:
        raise NotImplementedError


class HttpStage1ForecastProvider(Stage1ForecastProvider):
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8765",
        timeout_seconds: float = 10.0,
        retries: int = 1,
        maximum_bytes: int = MAX_RAW_FORECAST_BYTES,
        allow_private_endpoints: bool = False,
        allowed_hosts: Tuple[str, ...] = (),
        fetcher: Optional[HttpFetcher] = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Stage 1 HTTP timeout은 0보다 커야 합니다.")
        if retries < 0 or retries > 3:
            raise ValueError("Stage 1 HTTP retry는 0~3이어야 합니다.")
        if maximum_bytes <= 0:
            raise ValueError("Stage 1 maximum response bytes가 필요합니다.")
        self.base_url = _validate_base_url(
            base_url,
            allow_private_endpoints=allow_private_endpoints,
            allowed_hosts=allowed_hosts,
        )
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.maximum_bytes = maximum_bytes
        self.fetcher = fetcher or _default_http_fetch

    def _fetch(self, path: str) -> bytes:
        last_error: Optional[Exception] = None
        for unused_attempt in range(self.retries + 1):
            del unused_attempt
            try:
                return self.fetcher(
                    "{}{}".format(self.base_url, path),
                    self.timeout_seconds,
                    self.maximum_bytes,
                )
            except Exception as exc:
                last_error = exc
        if isinstance(last_error, Stage1ProviderError):
            raise last_error
        raise Stage1ProviderError(
            "HTTP_UNAVAILABLE",
            "Stage 1 HTTP 서비스에 연결하지 못했습니다.",
        ) from last_error

    def fetch_latest(self) -> Dict[str, Any]:
        return _json_object(self._fetch("/api/forecast"))

    def health(self) -> ProviderHealth:
        try:
            payload = _json_object(self._fetch("/health"))
            status_ok = payload.get("status") == "ok"
            available = payload.get("forecast_available")
            return ProviderHealth(
                provider="http",
                status="OK" if status_ok and available else "DEGRADED",
                reachable=True,
                forecast_available=(
                    bool(available) if available is not None else None
                ),
                checked_at=_checked_at(),
                warnings=(
                    []
                    if status_ok and available
                    else ["Stage 1 서비스는 응답했지만 forecast가 없습니다."]
                ),
            )
        except Exception as exc:
            error_code = (
                exc.code
                if isinstance(exc, Stage1ProviderError)
                else type(exc).__name__
            )
            return ProviderHealth(
                provider="http",
                status="UNAVAILABLE",
                reachable=False,
                forecast_available=False,
                checked_at=_checked_at(),
                error_code=str(error_code),
                warnings=["Stage 1 HTTP health 확인에 실패했습니다."],
            )


class FileStage1ForecastProvider(Stage1ForecastProvider):
    provider_name = "file"

    def __init__(self, path: Path) -> None:
        self.path = path

    def _body(self) -> bytes:
        if not self.path.is_file():
            raise Stage1ProviderError(
                "FILE_NOT_FOUND",
                "Stage 1 forecast 파일을 찾을 수 없습니다.",
            )
        size = self.path.stat().st_size
        if size > MAX_RAW_FORECAST_BYTES:
            raise Stage1ProviderError(
                "FILE_TOO_LARGE",
                "Stage 1 forecast 파일이 1MB를 초과합니다.",
            )
        return self.path.read_bytes()

    def fetch_latest(self) -> Dict[str, Any]:
        return _json_object(self._body())

    def health(self) -> ProviderHealth:
        exists = self.path.is_file()
        return ProviderHealth(
            provider=self.provider_name,
            status="OK" if exists else "UNAVAILABLE",
            reachable=exists,
            forecast_available=exists,
            checked_at=_checked_at(),
            error_code=None if exists else "FILE_NOT_FOUND",
            warnings=[] if exists else ["Stage 1 forecast 파일이 없습니다."],
        )


class MockStage1ForecastProvider(FileStage1ForecastProvider):
    provider_name = "mock"


class Stage1ForecastService:
    def __init__(
        self,
        *,
        http_provider: HttpStage1ForecastProvider,
        file_provider: FileStage1ForecastProvider,
        mock_provider: MockStage1ForecastProvider,
        maximum_path_return: Decimal,
        max_staleness_market_days: int,
    ) -> None:
        self.providers: Dict[str, Stage1ForecastProvider] = {
            "http": http_provider,
            "file": file_provider,
            "mock": mock_provider,
        }
        self.maximum_path_return = maximum_path_return
        self.max_staleness_market_days = max_staleness_market_days

    def _normalized(
        self,
        provider: Stage1ForecastProvider,
        provider_name: str,
        *,
        now: Optional[datetime],
    ):
        payload = provider.fetch_latest()
        return normalize_stage1_web_forecast(
            payload,
            provider=provider_name,
            max_path_return=self.maximum_path_return,
            max_staleness_market_days=self.max_staleness_market_days,
            now=now,
        )

    @staticmethod
    def _file_modified_at(
        provider: Stage1ForecastProvider,
    ) -> Optional[str]:
        if not isinstance(provider, FileStage1ForecastProvider):
            return None
        if not provider.path.is_file():
            return None
        return datetime.fromtimestamp(
            provider.path.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat()

    def load(
        self,
        provider_name: str,
        *,
        now: Optional[datetime] = None,
    ) -> Stage1ForecastLoadResult:
        normalized_name = provider_name.strip().lower()
        if normalized_name not in self.providers:
            raise ValueError(
                "STAGE1_PROVIDER는 http, file, mock 중 하나여야 합니다."
            )
        primary = self.providers[normalized_name]
        try:
            forecast = self._normalized(
                primary,
                normalized_name,
                now=now,
            )
            health = primary.health()
            warnings = list(forecast.quality.warnings)
            return Stage1ForecastLoadResult(
                source=normalized_name.upper(),
                forecast=forecast,
                provider_health=health,
                fallback_used=False,
                file_modified_at=self._file_modified_at(primary),
                warnings=warnings,
            )
        except Exception as primary_error:
            if normalized_name != "http":
                raise
            primary_health = ProviderHealth(
                provider="http",
                status="UNAVAILABLE",
                reachable=False,
                forecast_available=False,
                checked_at=_checked_at(),
                error_code=(
                    primary_error.code
                    if isinstance(primary_error, Stage1ProviderError)
                    else type(primary_error).__name__
                ),
                warnings=["Stage 1 HTTP forecast 로드에 실패했습니다."],
            )
            for fallback_name in ("file", "mock"):
                fallback = self.providers[fallback_name]
                try:
                    forecast = self._normalized(
                        fallback,
                        fallback_name,
                        now=now,
                    )
                    warnings = [
                        "FALLBACK_USED: Stage 1 HTTP 실패로 {} forecast를 "
                        "사용했습니다.".format(fallback_name)
                    ] + list(forecast.quality.warnings)
                    return Stage1ForecastLoadResult(
                        source=(
                            "FILE_FALLBACK"
                            if fallback_name == "file"
                            else "MOCK_FALLBACK"
                        ),
                        forecast=forecast,
                        provider_health=primary_health,
                        fallback_used=True,
                        file_modified_at=self._file_modified_at(fallback),
                        warnings=list(dict.fromkeys(warnings)),
                    )
                except Exception:
                    continue
            raise Stage1ProviderError(
                "ALL_PROVIDERS_FAILED",
                "Stage 1 HTTP와 표시된 fallback을 모두 사용할 수 없습니다.",
            ) from primary_error
