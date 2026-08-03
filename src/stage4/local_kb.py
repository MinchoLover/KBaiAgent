import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from src.domain.product_models import (
    ProductRecord,
    Stage4Result,
)
from src.stage4.official_search import is_official_url
from src.stage4.ranking import rank_records


DEFAULT_KB_PATH = (
    Path(__file__).resolve().parents[2]
    / "knowledge_base"
    / "official_products.json"
)

CATALOGUE_ALLOWED_DOMAINS = [
    "ksure.or.kr",
    "kbstar.com",
    "kosmes.or.kr",
]


def load_official_kb(
    path: Optional[Path] = None,
) -> List[ProductRecord]:
    kb_path = path or DEFAULT_KB_PATH
    with kb_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    records = [ProductRecord.model_validate(item) for item in raw]
    all_product_ids = [record.product_id for record in records]
    if len(all_product_ids) != len(set(all_product_ids)):
        raise ValueError("공식 catalogue product_id는 중복될 수 없습니다.")
    all_catalogue_ids = [
        record.catalogue_id
        for record in records
        if record.catalogue_id is not None
    ]
    if len(all_catalogue_ids) != len(set(all_catalogue_ids)):
        raise ValueError("공식 catalogue catalogue_id는 중복될 수 없습니다.")
    if path is None and len(all_catalogue_ids) != len(records):
        raise ValueError(
            "프로젝트 공식 catalogue의 모든 항목에 catalogue_id가 필요합니다."
        )
    official_records = [
        record for record in records if is_official_url(record.source.url)
    ]
    return official_records


def active_official_catalogue(
    path: Optional[Path] = None,
) -> List[ProductRecord]:
    records = [
        record
        for record in load_official_kb(path)
        if (
            record.active
            and record.source_status == "VERIFIED"
            and record.catalogue_id == record.product_id
        )
    ]
    for record in records:
        if not is_official_url(
            record.source.url,
            CATALOGUE_ALLOWED_DOMAINS,
        ):
            raise ValueError(
                "active catalogue URL이 공식기관 allowlist 밖에 있습니다."
            )
        if not record.official_name or not record.candidate_family:
            raise ValueError(
                "active catalogue에는 공식명과 candidate family가 필요합니다."
            )
        try:
            date.fromisoformat(record.source.verified_at)
        except ValueError as exc:
            raise ValueError(
                "active catalogue에는 ISO 형식 출처 확인일이 필요합니다."
            ) from exc
    return records


def active_official_catalogue_by_id(
    path: Optional[Path] = None,
) -> Dict[str, ProductRecord]:
    return {
        record.product_id: record
        for record in active_official_catalogue(path)
    }


def search_offline_kb(
    *,
    query: str,
    trade_type: str,
    path: Optional[Path] = None,
) -> Stage4Result:
    records = active_official_catalogue(path)
    candidates = rank_records(
        records,
        query=query,
        trade_type=trade_type,
        limit=len(records),
    )
    return Stage4Result(
        mode="OFFLINE_KB",
        query=query,
        candidates=candidates,
        warnings=[
            "자격·승인·금리·한도는 확정하지 않았으며 기관 상담이 필요합니다."
        ],
    )
