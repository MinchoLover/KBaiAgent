import re
from typing import Any, Dict, List, Sequence, Set, Tuple

from src.domain.report_models import (
    Stage5GroundingSource,
    Stage5NarrativeDraft,
)


class Stage5NarrativeValidationError(ValueError):
    pass


_BASE_SOURCE_SPECS: Tuple[Tuple[str, str, str, str], ...] = (
    (
        "TRANSACTION_CONTEXT",
        "stage0.confirmation.checks",
        "확정 거래",
        "사용자가 확인한 거래조건과 확인 절차의 의미",
    ),
    (
        "CASHFLOW_CONTEXT",
        "stage2.scenario_results",
        "현금흐름",
        "결정론적으로 계산된 시나리오별 현금흐름의 상담 의미",
    ),
    (
        "HEDGE_CONTEXT",
        "stage3.status",
        "환헤지 검토",
        "확정 추천이 아닌 시뮬레이션 후보라는 제한",
    ),
)

_OPTIONAL_CONSULTATION_SPECS: Tuple[
    Tuple[str, str, str, str], ...
] = (
    (
        "TRADE_RISK_CONTEXT",
        "consultation.trade_settlement_risk",
        "결제조건 위험",
        "확인된 거래·결제조건 위험평가의 상담 의미",
    ),
    (
        "COUNTRY_ENVIRONMENT_CONTEXT",
        "consultation.country_environment",
        "국가환경",
        "공식 국가환경 신호를 거래처 판정과 분리해 보는 의미",
    ),
    (
        "TRADE_STATISTICS_CONTEXT",
        "consultation.trade_statistics",
        "무역통계",
        "공식 무역통계의 관측 범위와 한계",
    ),
    (
        "CONSULTATION_CONTEXT",
        "consultation.consultation_review_areas",
        "상담 검토 분야",
        "기존 순위를 바꾸지 않고 상담에서 확인할 의미",
    ),
    (
        "SUPPORTING_CHECK_CONTEXT",
        "consultation.consultation_supporting_checks",
        "추가 확인사항",
        "금융지원 후보와 분리된 정보 보완의 의미",
    ),
    (
        "OFFICIAL_CANDIDATE_CONTEXT",
        "consultation.official_candidate_shortlist.candidates",
        "공식 후보",
        "catalogue 후보도 기관 확인과 심사가 필요하다는 제한",
    ),
)

_TAIL_SOURCE_SPEC: Tuple[str, str, str, str] = (
    "LIMITATIONS_CONTEXT",
    "stage1.application_rule",
    "적용 한계",
    "시나리오와 보고서가 확정 자문이나 보장이 아니라는 한계",
)

_PROHIBITED_PATTERNS: Tuple[str, ...] = (
    r"승인.{0,12}가능",
    r"가입.{0,12}가능",
    r"대출.{0,12}가능",
    r"보험\s*인수.{0,12}가능",
    r"최적\s*상품",
    r"반드시\s*가입",
    r"위험\s*국가",
    r"부도\s*가능성",
    r"대금\s*회수.{0,12}불가능",
    r"확정.{0,12}(?:금리|한도|보험료)",
    r"(?:금리|한도|보험료).{0,12}확정",
    r"정책자금",
    r"추천\s*상품",
    r"\bsource\b",
    r"\bJSON\b",
    r"\bstage[0-9]*\b",
    r"consultation\.",
    r"https?://",
    r"#{1,6}\s",
)


def resolve_canonical_path(source_bundle: Any, path: str) -> Any:
    current = source_bundle
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index < 0 or index >= len(current):
                raise KeyError(path)
            current = current[index]
        else:
            raise KeyError(path)
    return current


def _path_exists(source_bundle: Dict[str, Any], path: str) -> bool:
    try:
        value = resolve_canonical_path(source_bundle, path)
    except KeyError:
        return False
    if isinstance(value, list):
        return bool(value)
    return value is not None


def build_grounding_registry(
    source_bundle: Dict[str, Any],
) -> List[Stage5GroundingSource]:
    specs: List[Tuple[str, str, str, str]] = list(
        _BASE_SOURCE_SPECS
    )
    specs.extend(
        spec
        for spec in _OPTIONAL_CONSULTATION_SPECS
        if _path_exists(source_bundle, spec[1])
    )
    if not any(
        spec[0] == "OFFICIAL_CANDIDATE_CONTEXT" for spec in specs
    ) and _path_exists(source_bundle, "stage4.candidates"):
        specs.append(
            (
                "OFFICIAL_CANDIDATE_CONTEXT",
                "stage4.candidates",
                "공식 후보",
                "공식 출처 후보도 기관 확인과 심사가 필요하다는 제한",
            )
        )
    specs.append(_TAIL_SOURCE_SPEC)
    registry = [
        Stage5GroundingSource(
            source_id=source_id,
            canonical_path=canonical_path,
            display_label=display_label,
            prompt_scope=prompt_scope,
        )
        for source_id, canonical_path, display_label, prompt_scope in specs
    ]
    for source in registry:
        resolve_canonical_path(source_bundle, source.canonical_path)
    if len({item.source_id for item in registry}) != len(registry):
        raise ValueError("Stage5 grounding source ID가 중복됐습니다.")
    return registry


def build_narrative_prompt(
    registry: Sequence[Stage5GroundingSource],
    validation_feedback: Sequence[str] = (),
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "required_source_id_order": [
            item.source_id for item in registry
        ],
        "allowed_sources": [
            {
                "source_id": item.source_id,
                "scope": item.prompt_scope,
            }
            for item in registry
        ],
        "rules": [
            "각 source_id에 설명을 정확히 하나씩 작성",
            "source_id 순서를 변경하지 않음",
            "숫자·날짜·통화·비율·순위·상품명·기관명·URL을 쓰지 않음",
            "JSON path·source tag·Markdown을 만들지 않음",
            "승인·가입·대출·보험 인수 가능성을 단정하지 않음",
            "결정론 값의 의미와 상담에서 확인할 점만 짧게 설명",
        ],
    }
    if validation_feedback:
        payload["validation_feedback"] = list(validation_feedback)
    return payload


def _authoritative_terms(source_bundle: Dict[str, Any]) -> Set[str]:
    terms: Set[str] = set()
    stage0 = source_bundle.get("stage0")
    extraction = (
        stage0.get("extraction")
        if isinstance(stage0, dict)
        else None
    )
    if isinstance(extraction, dict):
        for field in (
            "company_role",
            "trade_type",
            "currency",
            "payment_terms",
            "seller_country",
            "buyer_country",
        ):
            value = str(extraction.get(field, "")).strip()
            if value:
                terms.add(value)
    consultation = source_bundle.get("consultation")
    if not isinstance(consultation, dict):
        return terms
    for collection_name, fields in (
        (
            "consultation_priorities",
            ("category", "title"),
        ),
        (
            "consultation_review_areas",
            ("review_area_id", "display_name"),
        ),
        (
            "consultation_supporting_checks",
            ("check_id", "display_name"),
        ),
    ):
        collection = consultation.get(collection_name, [])
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            for field in fields:
                value = str(item.get(field, "")).strip()
                if value:
                    terms.add(value)
    shortlist = consultation.get("official_candidate_shortlist")
    candidates = (
        shortlist.get("candidates", [])
        if isinstance(shortlist, dict)
        else []
    )
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            for field in (
                "catalogue_id",
                "product_id",
                "name",
                "official_name",
                "display_name",
                "institution",
            ):
                value = str(candidate.get(field, "")).strip()
                if value:
                    terms.add(value)
            source = candidate.get("source")
            if isinstance(source, dict):
                url = str(source.get("url", "")).strip()
                if url:
                    terms.add(url)
    return terms


def validate_narrative_draft(
    *,
    draft: Stage5NarrativeDraft,
    registry: Sequence[Stage5GroundingSource],
    source_bundle: Dict[str, Any],
) -> None:
    expected_ids = [item.source_id for item in registry]
    actual_ids = [item.source_id for item in draft.narratives]
    if actual_ids != expected_ids:
        raise Stage5NarrativeValidationError(
            "허용된 source ID의 개수 또는 순서가 일치하지 않습니다."
        )
    authoritative_terms = _authoritative_terms(source_bundle)
    for item in draft.narratives:
        text = item.explanation
        if re.search(r"[0-9\[\]{}<>%$₩]", text):
            raise Stage5NarrativeValidationError(
                "LLM 설명에 결정론 코드가 렌더링해야 할 값이 포함됐습니다."
            )
        if any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in _PROHIBITED_PATTERNS
        ):
            raise Stage5NarrativeValidationError(
                "LLM 설명에 금지된 판정·path·Markdown 표현이 포함됐습니다."
            )
        if any(term and term in text for term in authoritative_terms):
            raise Stage5NarrativeValidationError(
                "LLM 설명이 결정론적 순위·분야·상품 식별자를 재작성했습니다."
            )


def render_grounded_narratives(
    *,
    deterministic_markdown: str,
    draft: Stage5NarrativeDraft,
    registry: Sequence[Stage5GroundingSource],
) -> str:
    by_id = {item.source_id: item.explanation for item in draft.narratives}
    lines = ["### 검증된 AI 설명", ""]
    for source in registry:
        lines.append(
            "- {label}: {text} [source: {path}]".format(
                label=source.display_label,
                text=by_id[source.source_id],
                path=source.canonical_path,
            )
        )
    marker = "\n## 3. 환율 시나리오 성격"
    if marker not in deterministic_markdown:
        raise ValueError("결정론 보고서의 섹션 조립 지점을 찾지 못했습니다.")
    block = "\n\n{}\n".format("\n".join(lines))
    return deterministic_markdown.replace(marker, block + marker, 1)
