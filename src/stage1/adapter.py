import ipaddress
import json
import socket
import urllib.request
from typing import Any, Callable, List, Optional, Tuple
from urllib.parse import urlparse

from src.config import Settings
from src.domain.stage1_models import (
    Stage1LoadResult,
    Stage1ScenarioSet,
)
from src.stage1.manual_scenarios import build_manual_stress_scenarios
from src.stage1.normalizer import normalize_stage1_scenarios


FetchFunction = Callable[[str, float], bytes]
ResolverFunction = Callable[[str, int], List[str]]
MAX_STAGE1_RESPONSE_BYTES = 1_000_000


class Stage1EndpointError(ValueError):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def _default_fetch(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        body = response.read(MAX_STAGE1_RESPONSE_BYTES + 1)
    if len(body) > MAX_STAGE1_RESPONSE_BYTES:
        raise ValueError("Stage 1 응답이 1MB 안전 제한을 초과합니다.")
    return body


def _default_resolver(hostname: str, port: int) -> List[str]:
    try:
        records = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise Stage1EndpointError(
            "Stage 1 endpoint hostname을 확인할 수 없습니다."
        ) from exc
    addresses = sorted(
        {
            str(record[4][0])
            for record in records
            if record[4] and record[4][0]
        }
    )
    if not addresses:
        raise Stage1EndpointError(
            "Stage 1 endpoint hostname의 IP 주소가 없습니다."
        )
    return addresses


def _normalize_hosts(hosts: Tuple[str, ...]) -> Tuple[str, ...]:
    normalized = []
    for item in hosts:
        host = str(item).strip().rstrip(".").lower()
        if not host:
            continue
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise Stage1EndpointError(
                "STAGE1_ALLOWED_HOSTS에 잘못된 hostname이 있습니다."
            ) from exc
        normalized.append(host)
    return tuple(dict.fromkeys(normalized))


def _is_non_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise Stage1EndpointError(
            "Stage 1 endpoint의 IP 주소를 검증할 수 없습니다."
        ) from exc
    return not address.is_global


def validate_stage1_endpoint(
    url: str,
    *,
    allow_private: bool = False,
    allowed_hosts: Tuple[str, ...] = (),
    resolver: Optional[ResolverFunction] = None,
) -> str:
    candidate = str(url).strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise Stage1EndpointError(
            "Stage 1 endpoint는 http 또는 https URL이어야 합니다."
        )
    if not allow_private and parsed.scheme != "https":
        raise Stage1EndpointError(
            "Stage 1 endpoint는 기본 정책에서 HTTPS여야 합니다."
        )
    if parsed.username is not None or parsed.password is not None:
        raise Stage1EndpointError(
            "Stage 1 endpoint URL에는 사용자정보를 포함할 수 없습니다."
        )
    if parsed.fragment:
        raise Stage1EndpointError(
            "Stage 1 endpoint URL에는 fragment를 포함할 수 없습니다."
        )
    raw_hostname = parsed.hostname
    if not raw_hostname or "%" in raw_hostname:
        raise Stage1EndpointError(
            "Stage 1 endpoint hostname이 올바르지 않습니다."
        )
    try:
        hostname = (
            raw_hostname.rstrip(".").lower().encode("idna").decode("ascii")
        )
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except (UnicodeError, ValueError) as exc:
        raise Stage1EndpointError(
            "Stage 1 endpoint hostname 또는 port가 올바르지 않습니다."
        ) from exc
    if not hostname or any(character.isspace() for character in hostname):
        raise Stage1EndpointError(
            "Stage 1 endpoint hostname이 올바르지 않습니다."
        )

    configured_hosts = _normalize_hosts(allowed_hosts)
    if configured_hosts and hostname not in configured_hosts:
        raise Stage1EndpointError(
            "Stage 1 endpoint hostname이 STAGE1_ALLOWED_HOSTS에 없습니다."
        )

    try:
        ipaddress.ip_address(hostname)
        addresses = [hostname]
    except ValueError:
        addresses = (resolver or _default_resolver)(hostname, port)
    if not allow_private and any(
        _is_non_public_address(address) for address in addresses
    ):
        raise Stage1EndpointError(
            "Stage 1 endpoint가 사설·로컬·예약 IP를 가리켜 차단했습니다."
        )
    return candidate


def _validate_payload_size(payload: Any) -> None:
    if isinstance(payload, bytes):
        size = len(payload)
    elif isinstance(payload, str):
        size = len(payload.encode("utf-8"))
    else:
        return
    if size > MAX_STAGE1_RESPONSE_BYTES:
        raise ValueError("Stage 1 응답이 1MB 안전 제한을 초과합니다.")


def _parse_payload(payload: Any) -> Stage1ScenarioSet:
    _validate_payload_size(payload)
    if isinstance(payload, Stage1ScenarioSet):
        return payload
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("Stage 1 payload는 JSON object여야 합니다.")
    return Stage1ScenarioSet.model_validate(payload)


def load_stage1(
    *,
    expected_currency: str,
    expected_target_date: str,
    manual_base_rate: str,
    mode: str = "MANUAL_STRESS",
    payload: Optional[Any] = None,
    endpoint: Optional[str] = None,
    settings: Optional[Settings] = None,
    fetcher: Optional[FetchFunction] = None,
    resolver: Optional[ResolverFunction] = None,
) -> Stage1LoadResult:
    effective_settings = settings or Settings.from_env()
    normalized_mode = mode.strip().upper()
    if normalized_mode not in {"MANUAL_STRESS", "EXTERNAL_STAGE1"}:
        raise ValueError(
            "Stage 1 mode는 MANUAL_STRESS 또는 EXTERNAL_STAGE1이어야 합니다."
        )
    if normalized_mode == "MANUAL_STRESS":
        manual = build_manual_stress_scenarios(
            currency=expected_currency,
            base_rate=manual_base_rate,
            target_date=expected_target_date,
        )
        return Stage1LoadResult(
            source="MANUAL",
            scenario_set=normalize_stage1_scenarios(
                manual,
                expected_currency=expected_currency,
                expected_target_date=expected_target_date,
            ),
        )

    warnings = []
    try:
        if payload is not None:
            raw = _parse_payload(payload)
        else:
            url = (endpoint or effective_settings.stage1_base_url).strip()
            url = validate_stage1_endpoint(
                url,
                allow_private=(
                    effective_settings.stage1_allow_private_endpoints
                ),
                allowed_hosts=effective_settings.stage1_allowed_hosts,
                resolver=resolver,
            )
            body = (fetcher or _default_fetch)(
                url,
                effective_settings.stage1_timeout_seconds,
            )
            raw = _parse_payload(body)
        normalized = normalize_stage1_scenarios(
            raw,
            expected_currency=expected_currency,
            expected_target_date=expected_target_date,
        )
        return Stage1LoadResult(
            source="EXTERNAL",
            scenario_set=normalized,
            warnings=normalized.warnings,
        )
    except Exception as exc:
        warnings.append(
            "외부 Stage 1을 불러오지 못해 수동 스트레스 시나리오로 "
            "fallback했습니다."
        )
        if isinstance(exc, Stage1EndpointError):
            warnings.append(
                "Stage 1 endpoint가 outbound 보안 정책을 통과하지 못했습니다."
            )
        manual = build_manual_stress_scenarios(
            currency=expected_currency,
            base_rate=manual_base_rate,
            target_date=expected_target_date,
        )
        normalized = normalize_stage1_scenarios(
            manual,
            expected_currency=expected_currency,
            expected_target_date=expected_target_date,
        )
        return Stage1LoadResult(
            source="MANUAL_FALLBACK",
            scenario_set=normalized,
            warnings=warnings,
        )
