import json
from pathlib import Path
from typing import List, Optional

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


def load_official_kb(
    path: Optional[Path] = None,
) -> List[ProductRecord]:
    kb_path = path or DEFAULT_KB_PATH
    with kb_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    records = [ProductRecord.model_validate(item) for item in raw]
    return [
        record for record in records if is_official_url(record.source.url)
    ]


def search_offline_kb(
    *,
    query: str,
    trade_type: str,
    path: Optional[Path] = None,
) -> Stage4Result:
    records = load_official_kb(path)
    candidates = rank_records(
        records,
        query=query,
        trade_type=trade_type,
    )
    return Stage4Result(
        mode="OFFLINE_KB",
        query=query,
        candidates=candidates,
        warnings=[
            "자격·승인·금리·한도는 확정하지 않았으며 기관 상담이 필요합니다."
        ],
    )
