from typing import List, Literal

from pydantic import Field

from schemas import StrictModel


class OfficialSource(StrictModel):
    title: str
    url: str
    verified_at: str
    evidence_summary: str


class ProductRecord(StrictModel):
    product_id: str
    name: str
    institution: str
    category: str
    trade_types: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    summary: str
    eligibility: str = "unknown"
    approval_status: str = "consultation_required"
    target_customers: List[str] = Field(default_factory=list)
    key_conditions: List[str] = Field(default_factory=list)
    required_documents: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    source: OfficialSource


class ProductCandidate(ProductRecord):
    relevance_score: str
    strategy_connection_reason: str = (
        "전략과의 연결은 공식자료 확인 후 상담이 필요합니다."
    )
    verification_status: Literal[
        "OFFICIAL_SOURCE_VERIFIED"
    ] = "OFFICIAL_SOURCE_VERIFIED"
    candidate_status: str = "CANDIDATE_REQUIRES_HUMAN_CONSULTATION"


class Stage4Result(StrictModel):
    schema_version: str = "1.0"
    mode: Literal["OFFLINE_KB", "OFFICIAL_WEB_SEARCH"]
    query: str
    candidates: List[ProductCandidate] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
