from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from schemas import StrictModel


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
