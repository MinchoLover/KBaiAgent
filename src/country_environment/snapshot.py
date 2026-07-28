import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import ValidationError

from src.domain.country_environment_models import (
    CountryEnvironmentSnapshot,
)


COUNTRY_ENVIRONMENT_SNAPSHOT_VERSION = "2026.07.29-v1"
DEFAULT_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[1]
    / "integration_assets"
    / "country_environment"
    / "snapshot_v1.json"
)


class CountrySnapshotError(ValueError):
    """Raised when the committed official-source snapshot fails closed."""


def canonical_snapshot_payload(
    snapshot: CountryEnvironmentSnapshot,
) -> Dict[str, Any]:
    payload = snapshot.model_dump(exclude={"snapshot_hash"})
    payload["supported_countries"] = sorted(
        payload["supported_countries"]
    )
    payload["source_records"] = sorted(
        payload["source_records"],
        key=lambda item: item["source_record_id"],
    )
    return payload


def canonical_snapshot_hash(
    snapshot: CountryEnvironmentSnapshot,
) -> str:
    serialized = json.dumps(
        canonical_snapshot_payload(snapshot),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_country_environment_snapshot(
    path: Optional[Path] = None,
    expected_snapshot_version: str = (
        COUNTRY_ENVIRONMENT_SNAPSHOT_VERSION
    ),
) -> CountryEnvironmentSnapshot:
    snapshot_path = path or DEFAULT_SNAPSHOT_PATH
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot = CountryEnvironmentSnapshot.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise CountrySnapshotError(
            "country environment snapshot을 검증할 수 없습니다."
        ) from exc
    if snapshot.snapshot_version != expected_snapshot_version:
        raise CountrySnapshotError(
            "지원하지 않는 country environment snapshot version입니다."
        )
    actual_hash = canonical_snapshot_hash(snapshot)
    if actual_hash != snapshot.snapshot_hash:
        raise CountrySnapshotError(
            "country environment snapshot hash가 일치하지 않습니다."
        )
    return snapshot
