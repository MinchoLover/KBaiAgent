import re
from typing import Any, Dict


SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"(?i)(OPENAI_API_KEY\s*[=:]\s*)([^\s,;]+)"
    ),
    re.compile(r"(?i)(authorization:\s*bearer\s+)([^\s]+)"),
)


def redact_text(value: str) -> str:
    redacted = str(value)
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def safe_event_log(
    *,
    request_id: str,
    fingerprint: str,
    status: str,
    latency_seconds: float,
) -> Dict[str, Any]:
    return {
        "request_id": redact_text(request_id),
        "fingerprint": fingerprint,
        "status": status,
        "latency_seconds": round(float(latency_seconds), 3),
    }
