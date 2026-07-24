import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from openai import OpenAI

from src.config import DEFAULT_OFFICIAL_DOMAINS, Settings
from src.domain.product_models import (
    OfficialSource,
    ProductCandidate,
    Stage4Result,
)


DEFAULT_ALLOWED_DOMAINS = DEFAULT_OFFICIAL_DOMAINS
CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "official_search"
CACHE_SCHEMA_VERSION = "1.0"
MAX_CACHE_BYTES = 2_000_000


def is_official_url(
    url: str,
    allowed_domains: Optional[List[str]] = None,
) -> bool:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        return False
    hostname = (parsed.hostname or "").lower()
    domains = (
        allowed_domains
        if allowed_domains is not None
        else list(DEFAULT_ALLOWED_DOMAINS)
    )
    return any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in domains
    )


def _cache_path(
    query: str,
    cache_dir: Optional[Path] = None,
) -> Path:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return (cache_dir or CACHE_DIR) / "{}.json".format(digest)


def _parse_cache_time(value: Any) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("cache timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _read_cache(
    *,
    path: Path,
    ttl_hours: int,
    allowed_domains: List[str],
    expected_query: str,
    expected_trade_type: str,
    now: Optional[datetime] = None,
) -> Tuple[Optional[Stage4Result], List[str]]:
    if ttl_hours <= 0 or not path.exists():
        return None, []
    try:
        if path.stat().st_size > MAX_CACHE_BYTES:
            raise ValueError("cache size limit exceeded")
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if (
            isinstance(payload, dict)
            and payload.get("cache_schema_version")
            == CACHE_SCHEMA_VERSION
            and "result" in payload
        ):
            cached_at = _parse_cache_time(payload.get("cached_at"))
            cached = Stage4Result.model_validate(payload["result"])
        else:
            raise ValueError("legacy cache has no trusted timestamp")
        if (
            cached.mode != "OFFICIAL_WEB_SEARCH"
            or cached.query != expected_query
        ):
            raise ValueError("cache request binding mismatch")

        checked_at = now or datetime.now(timezone.utc)
        age_seconds = (checked_at - cached_at).total_seconds()
        if age_seconds < 0 or age_seconds > ttl_hours * 3600:
            return None, [
                "공식 검색 캐시가 TTL을 초과하거나 미래 시각이라 재검색했습니다."
            ]

        safe_candidates = [
            item
            for item in cached.candidates
            if (
                is_official_url(item.source.url, allowed_domains)
                and expected_trade_type in item.trade_types
            )
        ]
        removed_count = len(cached.candidates) - len(safe_candidates)
        warnings = list(cached.warnings)
        if removed_count:
            warnings.append(
                "현재 공식 도메인 allowlist와 맞지 않는 캐시 후보 {}건을 "
                "제외했습니다.".format(removed_count)
            )
        warnings.append(
            "공식 검색 캐시 사용 · cached_at={}".format(
                cached_at.isoformat()
            )
        )
        return (
            cached.model_copy(
                update={
                    "candidates": safe_candidates,
                    "warnings": list(dict.fromkeys(warnings)),
                }
            ),
            [],
        )
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return None, [
            "공식 검색 캐시를 검증하지 못해 재검색했습니다."
        ]


def _write_cache(
    *,
    path: Path,
    result: Stage4Result,
    now: Optional[datetime] = None,
) -> Optional[str]:
    cached_at = now or datetime.now(timezone.utc)
    envelope = {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "cached_at": cached_at.isoformat(),
        "result": result.model_dump(mode="json"),
    }
    temporary_path = path.with_suffix(".json.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(
                envelope,
                handle,
                ensure_ascii=False,
                indent=2,
            )
        temporary_path.replace(path)
    except (OSError, TypeError, UnicodeError, ValueError):
        return "검색 캐시를 저장하지 못했지만 검색 결과는 유지했습니다."
    return None


def _source_dict(source: Any) -> Dict[str, str]:
    if isinstance(source, dict):
        return {
            "url": str(source.get("url", "")),
            "title": str(source.get("title", "공식 출처")),
        }
    return {
        "url": str(getattr(source, "url", "")),
        "title": str(getattr(source, "title", "공식 출처")),
    }


def _extract_sources(response: Any) -> List[Dict[str, str]]:
    sources: List[Dict[str, str]] = []
    for output_item in getattr(response, "output", []) or []:
        action = getattr(output_item, "action", None)
        for source in getattr(action, "sources", []) or []:
            sources.append(_source_dict(source))
        for content in getattr(output_item, "content", []) or []:
            for annotation in getattr(content, "annotations", []) or []:
                url = getattr(annotation, "url", None)
                if url:
                    sources.append(
                        {
                            "url": str(url),
                            "title": str(
                                getattr(
                                    annotation,
                                    "title",
                                    "공식 출처",
                                )
                            ),
                        }
                    )
    unique: Dict[str, Dict[str, str]] = {}
    for item in sources:
        if item["url"]:
            unique[item["url"]] = item
    return list(unique.values())


def search_official_web(
    *,
    query: str,
    trade_type: str,
    settings: Optional[Settings] = None,
    client: Optional[Any] = None,
    use_cache: bool = True,
    cache_dir: Optional[Path] = None,
) -> Stage4Result:
    effective_settings = settings or Settings.from_env()
    if (
        not effective_settings.enable_official_web_search
        or not effective_settings.openai_api_key
    ):
        raise RuntimeError(
            "공식 웹 검색은 API 키와 ENABLE_OFFICIAL_WEB_SEARCH=true가 필요합니다."
        )

    allowed_domains = list(effective_settings.official_domains)
    cache_key = "|".join(
        [
            query,
            trade_type,
            effective_settings.openai_rag_model,
            ",".join(sorted(allowed_domains)),
        ]
    )
    cache_path = _cache_path(cache_key, cache_dir=cache_dir)
    cache_warnings: List[str] = []
    if use_cache:
        cached, cache_warnings = _read_cache(
            path=cache_path,
            ttl_hours=(
                effective_settings.official_search_cache_ttl_hours
            ),
            allowed_domains=allowed_domains,
            expected_query=query,
            expected_trade_type=trade_type,
        )
        if cached is not None:
            return cached

    openai_client = client or OpenAI(
        api_key=effective_settings.openai_api_key,
        timeout=effective_settings.openai_timeout_seconds,
        max_retries=1,
    )
    try:
        response = openai_client.responses.create(
            model=effective_settings.openai_rag_model,
            tools=[
                {
                    "type": "web_search",
                    "filters": {
                        "allowed_domains": list(
                            allowed_domains
                        )
                    },
                }
            ],
            tool_choice="required",
            include=["web_search_call.action.sources"],
            input=(
                "수출입 기업의 다음 필요 유형에 맞는 공식 금융상품·지원제도 "
                "후보를 검색하라: {}. 자격, 승인, 금리, 한도는 확정하지 말고 "
                "공식 페이지의 확인 가능한 설명만 요약하라.".format(query)
            ),
            store=False,
        )
    except Exception as exc:
        raise RuntimeError(
            "공식 웹 검색에 실패했습니다. 비밀값과 원문은 로그에 남기지 않았습니다."
        ) from exc
    source_rows = [
        item
        for item in _extract_sources(response)
        if is_official_url(
            item["url"],
            allowed_domains,
        )
    ][:8]
    summary = str(getattr(response, "output_text", "")).strip()
    candidates = [
        ProductCandidate(
            product_id="web_{}".format(index),
            name=item["title"] or "공식 상품/제도 후보",
            institution=urlparse(item["url"]).hostname or "official",
            category="OFFICIAL_WEB_RESULT",
            trade_types=[trade_type],
            keywords=[query],
            summary=summary[:500] or "공식 페이지 원문 확인 필요",
            eligibility="unknown",
            approval_status="consultation_required",
            target_customers=["{} 거래 기업".format(trade_type)],
            key_conditions=[
                "자격·한도·가격은 제공 기관의 최신 기준 확인 필요"
            ],
            required_documents=[
                "필요 서류는 공식 페이지와 기관 상담에서 확인"
            ],
            limitations=[
                "검색 결과는 후보이며 승인·가격·한도를 확정하지 않음"
            ],
            source=OfficialSource(
                title=item["title"] or "공식 출처",
                url=item["url"],
                verified_at=date.today().isoformat(),
                evidence_summary="Responses API web_search 공식 도메인 결과",
            ),
            relevance_score=str(max(1, len(source_rows) - index)),
            strategy_connection_reason=(
                "공식 도메인 검색 결과가 요청한 전략 유형과 연결됨"
            ),
        )
        for index, item in enumerate(source_rows)
    ]
    fresh_result = Stage4Result(
        mode="OFFICIAL_WEB_SEARCH",
        query=query,
        candidates=candidates,
        warnings=[
            "검색 결과는 후보이며 자격·승인·금리·한도는 기관 확인이 필요합니다."
        ],
    )
    result = fresh_result.model_copy(
        update={
            "warnings": list(
                dict.fromkeys(fresh_result.warnings + cache_warnings)
            )
        }
    )
    if (
        use_cache
        and effective_settings.official_search_cache_ttl_hours > 0
    ):
        cache_warning = _write_cache(
            path=cache_path,
            result=fresh_result,
        )
        if cache_warning:
            result = result.model_copy(
                update={
                    "warnings": result.warnings + [cache_warning]
                }
            )
    return result
