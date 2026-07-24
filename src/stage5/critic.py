import json
import re
from typing import Any, List, Set, Tuple

from src.domain.report_models import ReportCritique


NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_])[-+]?\d[\d,]*(?:\.\d+)?%?")
SOURCE_TAG_RE = re.compile(r"\[source:\s*([A-Za-z0-9_.-]+)\]")
URL_RE = re.compile(r"https?://[^)\s]+")
REQUIRED_SECTIONS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("거래 요약", ("거래 요약",)),
    ("환노출·현금흐름", ("현금흐름 영향", "현재 환노출")),
    ("헤지 후보", ("전략 후보", "헤지 후보")),
    ("금융상품과 출처", ("금융상품", "상품 후보")),
    ("한계", ("가정·한계", "한계·면책", "면책")),
    ("다음 행동", ("상담 시 질문", "상담 질문", "다음 행동")),
)


def _normalized_number(token: str) -> str:
    return token.replace(",", "").rstrip("%")


def _source_numbers(source_bundle: Any) -> Set[str]:
    serialized = json.dumps(
        source_bundle,
        ensure_ascii=False,
        default=str,
    )
    return {
        _normalized_number(match.group(0))
        for match in NUMBER_RE.finditer(serialized)
    }


def _resolve_path(source_bundle: Any, path: str) -> Any:
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


def _missing_sections(markdown: str) -> List[str]:
    return [
        label
        for label, aliases in REQUIRED_SECTIONS
        if not any(alias in markdown for alias in aliases)
    ]


def _product_grounding_issues(
    markdown: str,
    source_bundle: Any,
) -> List[str]:
    issues: List[str] = []
    stage4 = (
        source_bundle.get("stage4", {})
        if isinstance(source_bundle, dict)
        else {}
    )
    stage4_candidates = (
        stage4.get("candidates", [])
        if isinstance(stage4, dict)
        else []
    )
    product_section = re.search(
        r"(?is)##[^\n]*(?:금융상품|상품 후보)[^\n]*\n"
        r"(.*?)(?=\n##|\Z)",
        markdown,
    )
    if product_section:
        for line in product_section.group(1).splitlines():
            stripped = line.strip()
            if not stripped.startswith("-") or "없습니다" in stripped:
                continue
            product_tags = [
                item
                for item in SOURCE_TAG_RE.findall(stripped)
                if item.startswith("stage4.candidates.")
            ]
            if not product_tags:
                issues.append(
                    "상품 후보 주장에 공식 Stage 4 근거가 없습니다."
                )
    if not stage4_candidates and re.search(
        r"\[source:\s*stage4\.candidates\.",
        markdown,
    ):
        issues.append("빈 Stage 4 결과에서 상품 후보를 생성했습니다.")
    return list(dict.fromkeys(issues))


def critique_report(
    *,
    markdown: str,
    source_bundle: Any,
    scenario_kind: str,
    probability_valid: bool,
) -> ReportCritique:
    issues: List[str] = []
    numeric_issues: List[str] = []
    evidence_issues: List[str] = []
    recommendation_issues: List[str] = []
    prohibited_claims: List[str] = []
    allowed_numbers = _source_numbers(source_bundle)
    source_tags = SOURCE_TAG_RE.findall(markdown)

    for path in source_tags:
        try:
            _resolve_path(source_bundle, path)
        except KeyError:
            issue = "존재하지 않는 JSON path 근거: {}".format(path)
            issues.append(issue)
            evidence_issues.append(issue)

    for line in markdown.splitlines():
        line_tags = SOURCE_TAG_RE.findall(line)
        has_source_tag = bool(line_tags)
        line_allowed_numbers: Set[str] = set()
        for path in line_tags:
            try:
                line_allowed_numbers.update(
                    _source_numbers(_resolve_path(source_bundle, path))
                )
            except KeyError:
                continue
        content = SOURCE_TAG_RE.sub("", URL_RE.sub("", line))
        content = re.sub(
            r"^\s*#{1,6}\s+\d+[.)]?\s*",
            "",
            content,
        )
        content = re.sub(
            r"\bStage\s+[0-5]\b",
            "Stage",
            content,
            flags=re.IGNORECASE,
        )
        matches = list(NUMBER_RE.finditer(content))
        if matches and not has_source_tag:
            issue = "숫자 주장에 같은 줄의 JSON path 근거가 없습니다."
            issues.append(issue)
            numeric_issues.append(issue)
            evidence_issues.append(issue)
        for match in matches:
            normalized = _normalized_number(match.group(0))
            if normalized not in allowed_numbers:
                issue = "근거 JSON에 없는 숫자: {}".format(match.group(0))
                issues.append(issue)
                numeric_issues.append(issue)
            elif normalized not in line_allowed_numbers:
                issue = (
                    "같은 줄 JSON path가 뒷받침하지 않는 숫자: {}".format(
                        match.group(0)
                    )
                )
                issues.append(issue)
                numeric_issues.append(issue)
                evidence_issues.append(issue)

    if (
        scenario_kind == "STRESS"
        and re.search(
            r"환율\s*(?:예측|전망)|forecast",
            markdown,
            re.IGNORECASE,
        )
        and "예측이 아니라" not in markdown
    ):
        issue = "스트레스 가정을 예측으로 표현했습니다."
        issues.append(issue)
        recommendation_issues.append(issue)
    if (
        not probability_valid
        and re.search(
            r"(?:\d+(?:\.\d+)?%\s*(?:확률|가능성)"
            r"|(?:확률|가능성)\s*(?:은|는|:)?\s*\d+(?:\.\d+)?%)",
            markdown,
        )
    ):
        issue = "유효한 probability 없이 확률 수치를 표현했습니다."
        issues.append(issue)
        numeric_issues.append(issue)
        recommendation_issues.append(issue)

    banned_patterns = (
        "승인이 보장",
        "손실이 발생하지 않",
        "수익을 보장",
        "환율 손실을 완전히 피",
        "승인됩니다",
        "확실히 승인",
        "무조건 승인",
        "손실 없음",
    )
    for pattern in banned_patterns:
        if pattern in markdown:
            issue = "금지된 보장 표현: {}".format(pattern)
            issues.append(issue)
            prohibited_claims.append(pattern)
            recommendation_issues.append(issue)

    if len(source_tags) < 5:
        issue = "핵심 주장에 JSON path 근거가 부족합니다."
        issues.append(issue)
        evidence_issues.append(issue)

    missing_sections = _missing_sections(markdown)
    for label in missing_sections:
        issue = "필수 보고서 섹션 누락: {}".format(label)
        issues.append(issue)
        recommendation_issues.append(issue)

    for issue in _product_grounding_issues(markdown, source_bundle):
        issues.append(issue)
        evidence_issues.append(issue)
        recommendation_issues.append(issue)

    unique_issues = list(dict.fromkeys(issues))
    deductions = min(100, len(unique_issues) * 10)
    return ReportCritique(
        passed=not unique_issues,
        score=100 - deductions,
        numeric_consistency=not numeric_issues,
        evidence_quality=not evidence_issues,
        recommendation_consistency=not recommendation_issues,
        prohibited_claims=list(dict.fromkeys(prohibited_claims)),
        missing_sections=missing_sections,
        revision_instructions=[
            "다음 문제를 수정하십시오: {}".format(issue)
            for issue in unique_issues
        ],
        issues=unique_issues,
    )
