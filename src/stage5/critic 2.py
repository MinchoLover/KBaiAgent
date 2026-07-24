import json
import re
from typing import Any, List, Set

from src.domain.report_models import ReportCritique


NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_])[-+]?\d[\d,]*(?:\.\d+)?%?")
SOURCE_TAG_RE = re.compile(r"\[source:\s*([A-Za-z0-9_.-]+)\]")
URL_RE = re.compile(r"https?://[^)\s]+")


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


def critique_report(
    *,
    markdown: str,
    source_bundle: Any,
    scenario_kind: str,
    probability_valid: bool,
) -> ReportCritique:
    issues: List[str] = []
    allowed_numbers = _source_numbers(source_bundle)
    source_tags = SOURCE_TAG_RE.findall(markdown)
    for path in source_tags:
        try:
            _resolve_path(source_bundle, path)
        except KeyError:
            issues.append("존재하지 않는 JSON path 근거: {}".format(path))

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
            issues.append("숫자 주장에 같은 줄의 JSON path 근거가 없습니다.")
        for match in matches:
            normalized = _normalized_number(match.group(0))
            if normalized not in allowed_numbers:
                issues.append(
                    "근거 JSON에 없는 숫자: {}".format(match.group(0))
                )
            elif normalized not in line_allowed_numbers:
                issues.append(
                    "같은 줄 JSON path가 뒷받침하지 않는 숫자: {}".format(
                        match.group(0)
                    )
                )

    if (
        scenario_kind == "STRESS"
        and re.search(r"환율\s*(?:예측|전망)|forecast", markdown, re.IGNORECASE)
        and "예측이 아니라" not in markdown
    ):
        issues.append("스트레스 가정을 예측으로 표현했습니다.")
    if (
        not probability_valid
        and re.search(
            r"(?:\d+(?:\.\d+)?%\s*(?:확률|가능성)"
            r"|(?:확률|가능성)\s*(?:은|는|:)?\s*\d+(?:\.\d+)?%)",
            markdown,
        )
    ):
        issues.append("유효한 probability 없이 확률 수치를 표현했습니다.")

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
            issues.append("금지된 보장 표현: {}".format(pattern))

    if len(source_tags) < 5:
        issues.append("핵심 주장에 JSON path 근거가 부족합니다.")
    return ReportCritique(
        passed=not issues,
        issues=list(dict.fromkeys(issues)),
    )
