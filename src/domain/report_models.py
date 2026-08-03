from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from schemas import StrictModel


Stage5GroundingSourceId = Literal[
    "TRANSACTION_CONTEXT",
    "CASHFLOW_CONTEXT",
    "HEDGE_CONTEXT",
    "TRADE_RISK_CONTEXT",
    "COUNTRY_ENVIRONMENT_CONTEXT",
    "TRADE_STATISTICS_CONTEXT",
    "CONSULTATION_CONTEXT",
    "SUPPORTING_CHECK_CONTEXT",
    "OFFICIAL_CANDIDATE_CONTEXT",
    "LIMITATIONS_CONTEXT",
]


class Stage5GroundingSource(StrictModel):
    source_id: Stage5GroundingSourceId
    canonical_path: str = Field(min_length=1)
    display_label: str = Field(min_length=1, max_length=80)
    prompt_scope: str = Field(min_length=1, max_length=200)


class Stage5NarrativeItem(StrictModel):
    source_id: Stage5GroundingSourceId
    explanation: str = Field(
        min_length=1,
        max_length=240,
        pattern=r"^[^0-9\[\]{}<>%$₩]+$",
    )


class Stage5NarrativeDraft(StrictModel):
    narratives: List[Stage5NarrativeItem] = Field(
        min_length=1,
        max_length=10,
    )


class ReportCritique(StrictModel):
    passed: bool
    score: int = Field(default=100, ge=0, le=100)
    numeric_consistency: bool = True
    evidence_quality: bool = True
    recommendation_consistency: bool = True
    prohibited_claims: List[str] = Field(default_factory=list)
    missing_sections: List[str] = Field(default_factory=list)
    revision_instructions: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)


class ReportResult(StrictModel):
    schema_version: str = "1.0"
    status: Literal[
        "LLM_PASS",
        "LLM_REVISED_PASS",
        "DETERMINISTIC_FALLBACK",
    ]
    markdown: str
    report_json: Dict[str, Any]
    critique: ReportCritique
    warnings: List[str] = Field(default_factory=list)
    generation_provider: Literal[
        "OPENAI",
        "DETERMINISTIC_TEMPLATE",
    ] = "DETERMINISTIC_TEMPLATE"
    revision_count: int = Field(default=0, ge=0, le=1)
    fallback_reason: Optional[
        Literal[
            "NO_API_KEY",
            "CRITIC_REJECTED",
            "API_FAILURE",
            "ORCHESTRATOR_FAILURE",
            "DETERMINISTIC_POLICY",
        ]
    ] = "DETERMINISTIC_POLICY"
