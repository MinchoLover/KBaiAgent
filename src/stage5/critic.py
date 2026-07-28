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
    (
        "헤지 후보",
        ("전략 후보", "헤지 후보", "환헤지 시뮬레이션 후보"),
    ),
    (
        "금융상품과 출처",
        ("금융상품", "상품 후보", "공식 출처 상담 후보"),
    ),
    ("한계", ("가정·한계", "한계·면책", "면책")),
    ("다음 행동", ("상담 시 질문", "상담 질문", "다음 행동")),
)
TRADE_RISK_TYPE_LABELS = {
    "IMPORT_PREPAYMENT_PERFORMANCE_RISK": (
        "수입 선지급·계약이행 위험"
    ),
    "EXPORT_RECEIVABLE_COLLECTION_RISK": "수출대금 회수 위험",
}
TRADE_RISK_PRIORITY_LABELS = {
    "STANDARD_REVIEW": "일반 검토",
    "ELEVATED_REVIEW": "추가 검토 필요",
    "HIGH_REVIEW": "우선 검토 필요",
    "UNKNOWN": "정보 확인 필요",
}


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


def _missing_sections(
    markdown: str,
    source_bundle: Any,
) -> List[str]:
    required = list(REQUIRED_SECTIONS)
    if (
        isinstance(source_bundle, dict)
        and isinstance(source_bundle.get("consultation"), dict)
    ):
        required.extend(
            [
                (
                    "거래·결제조건 위험",
                    ("거래·결제조건 위험", "결제·회수 위험"),
                ),
                (
                    "검토할 금융 대응",
                    ("검토할 금융 대응", "금융 대응"),
                ),
            ]
        )
    return [
        label
        for label, aliases in required
        if not any(alias in markdown for alias in aliases)
    ]


def _authoritative_product_source(
    source_bundle: Any,
) -> Tuple[List[Any], str]:
    if not isinstance(source_bundle, dict):
        return [], "stage4.candidates"
    consultation = source_bundle.get("consultation")
    if isinstance(consultation, dict):
        shortlist = consultation.get("official_candidate_shortlist")
        candidates = (
            shortlist.get("candidates", [])
            if isinstance(shortlist, dict)
            else []
        )
        return (
            candidates if isinstance(candidates, list) else [],
            "consultation.official_candidate_shortlist.candidates",
        )
    stage4 = source_bundle.get("stage4", {})
    candidates = (
        stage4.get("candidates", [])
        if isinstance(stage4, dict)
        else []
    )
    return (
        candidates if isinstance(candidates, list) else [],
        "stage4.candidates",
    )


def _product_grounding_issues(
    markdown: str,
    source_bundle: Any,
) -> List[str]:
    issues: List[str] = []
    candidates, source_prefix = _authoritative_product_source(
        source_bundle
    )
    product_section = re.search(
        r"(?is)##[^\n]*(?:금융상품|상품 후보|공식 출처 상담 후보)"
        r"[^\n]*\n"
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
                if re.fullmatch(
                    re.escape(source_prefix) + r"\.\d+",
                    item,
                )
            ]
            if not product_tags:
                issues.append(
                    "상품 후보 주장에 현재 상담과 연결된 공식 근거가 없습니다."
                )
                continue
            try:
                candidate = _resolve_path(
                    source_bundle,
                    product_tags[0],
                )
            except KeyError:
                continue
            if not isinstance(candidate, dict):
                issues.append("상품 후보 근거가 후보 객체가 아닙니다.")
                continue
            name = str(candidate.get("name", "")).strip()
            if name and name not in stripped:
                issues.append(
                    "상품명이 인용한 공식 후보와 일치하지 않습니다."
                )
            institution = str(
                candidate.get("institution", "")
            ).strip()
            if institution and institution not in stripped:
                issues.append(
                    "기관명이 인용한 공식 후보와 일치하지 않습니다."
                )
            source = candidate.get("source", {})
            official_url = (
                str(source.get("url", "")).strip()
                if isinstance(source, dict)
                else ""
            )
            line_urls = URL_RE.findall(stripped)
            if not line_urls:
                issues.append("상품 후보에 공식 URL이 없습니다.")
            elif any(item != official_url for item in line_urls):
                issues.append(
                    "상품 링크가 인용한 공식 후보 URL과 일치하지 않습니다."
                )
            if (
                re.search(
                    r"(?:가입|이용|대출|지원).{0,20}"
                    r"(?:가능합니다|가능함|확정|대상입니다)",
                    stripped,
                )
                and not re.search(
                    r"(?:여부|상담\s*필요|확인\s*필요|확정하지)",
                    stripped,
                )
            ):
                issues.append(
                    "공식 후보의 이용 자격이나 승인 가능성을 확정했습니다."
                )
    if not candidates and re.search(
        r"\[source:\s*" + re.escape(source_prefix) + r"\.",
        markdown,
    ):
        issues.append("빈 공식 shortlist에서 상품 후보를 생성했습니다.")
    return list(dict.fromkeys(issues))


def _consultation_grounding_issues(
    markdown: str,
    source_bundle: Any,
) -> List[str]:
    if not isinstance(source_bundle, dict):
        return []
    consultation = source_bundle.get("consultation")
    if not isinstance(consultation, dict):
        return []
    issues: List[str] = []
    trade_risk = consultation.get("trade_settlement_risk")
    trade_section = re.search(
        r"(?is)##[^\n]*(?:거래·결제조건 위험|결제·회수 위험)"
        r"[^\n]*\n(.*?)(?=\n##|\Z)",
        markdown,
    )
    if isinstance(trade_risk, dict):
        if (
            trade_section is None
            or not any(
                item.startswith("consultation.trade_settlement_risk")
                for item in SOURCE_TAG_RE.findall(
                    trade_section.group(1)
                )
            )
        ):
            issues.append(
                "거래·결제조건 위험 주장에 확인된 위험평가 근거가 없습니다."
            )
        else:
            trade_text = trade_section.group(1)
            risk_type = str(trade_risk.get("risk_type", ""))
            risk_type_label = TRADE_RISK_TYPE_LABELS.get(risk_type)
            if (
                risk_type_label is not None
                and risk_type_label not in trade_text
            ):
                issues.append(
                    "위험 유형이 인용한 거래위험 결과와 일치하지 않습니다."
                )
            review_priority = str(
                trade_risk.get("review_priority", "")
            )
            priority_label = TRADE_RISK_PRIORITY_LABELS.get(
                review_priority
            )
            if (
                priority_label is not None
                and priority_label not in trade_text
            ):
                issues.append(
                    "검토 우선도가 인용한 거래위험 결과와 일치하지 않습니다."
                )
            for line in trade_text.splitlines():
                factor_tags = [
                    item
                    for item in SOURCE_TAG_RE.findall(line)
                    if re.fullmatch(
                        r"consultation\.trade_settlement_risk"
                        r"\.factors\.\d+",
                        item,
                    )
                ]
                for factor_tag in factor_tags:
                    try:
                        factor = _resolve_path(
                            source_bundle,
                            factor_tag,
                        )
                    except KeyError:
                        continue
                    reason = (
                        str(factor.get("reason", "")).strip()
                        if isinstance(factor, dict)
                        else ""
                    )
                    if reason and reason not in line:
                        issues.append(
                            "위험 요인이 인용한 결정론 결과와 "
                            "일치하지 않습니다."
                        )
    elif re.search(
        r"\[source:\s*consultation\.trade_settlement_risk",
        markdown,
    ):
        issues.append(
            "거래·결제조건 위험 결과가 없는데 위험평가를 인용했습니다."
        )

    topics = consultation.get("consultation_topics", [])
    response_section = re.search(
        r"(?is)##[^\n]*검토할 금융 대응[^\n]*\n"
        r"(.*?)(?=\n##|\Z)",
        markdown,
    )
    if isinstance(topics, list) and topics:
        if response_section is None:
            issues.append("금융 대응 항목 섹션이 없습니다.")
        else:
            for line in response_section.group(1).splitlines():
                stripped = line.strip()
                if (
                    not stripped.startswith("-")
                    or "없습니다" in stripped
                ):
                    continue
                if not any(
                    re.fullmatch(
                        r"consultation\.consultation_topics\.\d+",
                        item,
                    )
                    for item in SOURCE_TAG_RE.findall(stripped)
                ):
                    issues.append(
                        "금융 대응 주장에 구조화된 상담 항목 근거가 없습니다."
                    )
                    continue
                topic_tag = next(
                    item
                    for item in SOURCE_TAG_RE.findall(stripped)
                    if re.fullmatch(
                        r"consultation\.consultation_topics\.\d+",
                        item,
                    )
                )
                try:
                    topic = _resolve_path(source_bundle, topic_tag)
                except KeyError:
                    continue
                title = (
                    str(topic.get("title", "")).strip()
                    if isinstance(topic, dict)
                    else ""
                )
                if title and title not in stripped:
                    issues.append(
                        "금융 대응 제목이 인용한 상담 항목과 "
                        "일치하지 않습니다."
                    )
    return list(dict.fromkeys(issues))


def _risk_boundary_issues(markdown: str) -> List[str]:
    issues: List[str] = []
    for line in markdown.splitlines():
        if (
            re.search(
                r"(?:공식\s*심사등급|부도확률|보험\s*인수판단)",
                line,
                re.IGNORECASE,
            )
            and not re.search(
                r"(?:아닙니다|아니며|제공하지|확정하지|판단하지)",
                line,
            )
        ):
            issues.append(
                "거래·결제 검토 결과를 공식 등급·확률·인수판단으로 "
                "표현했습니다."
            )
        if (
            re.search(
                r"(?:결제|회수).{0,25}위험",
                line,
                re.IGNORECASE,
            )
            and re.search(
                r"(?:선물환|환헤지).{0,20}(?:비율|비중).{0,20}"
                r"(?:높|늘|증가|낮|줄|감소)",
                line,
                re.IGNORECASE,
            )
            and "변경하지" not in line
        ):
            issues.append(
                "결제·회수 위험이 환헤지 비율을 직접 변경한다고 "
                "표현했습니다."
            )
    return list(dict.fromkeys(issues))


def _market_policy_issues(
    markdown: str,
    source_bundle: Any,
) -> List[str]:
    if not isinstance(source_bundle, dict):
        return []
    integration = source_bundle.get("market_integration")
    if not isinstance(integration, dict):
        return []
    issues: List[str] = []
    forecast_load = integration.get("forecast_load") or {}
    forecast = (
        forecast_load.get("forecast", {})
        if isinstance(forecast_load, dict)
        else {}
    )
    direction = (
        forecast.get("direction", {})
        if isinstance(forecast, dict)
        else {}
    )
    scenario_build = integration.get("scenario_build") or {}
    market_context = (
        forecast.get("market_context", {})
        if isinstance(forecast, dict)
        else {}
    )

    if re.search(
        r"q90.{0,40}(?:90\s*%\s*(?:확률|가능성)|90퍼센트)",
        markdown,
        re.IGNORECASE | re.DOTALL,
    ):
        issues.append("q90을 90% 발생확률로 오해하게 표현했습니다.")
    if (
        isinstance(direction, dict)
        and direction.get("calibrated_probability") is False
    ):
        for line in markdown.splitlines():
            if (
                re.search(
                    r"(?:방향\s*점수|up_score|down_score).{0,80}"
                    r"(?:실제\s*)?(?:발생)?확률",
                    line,
                    re.IGNORECASE,
                )
                and "보정된 실제 발생확률이 아닙니다" not in line
            ):
                issues.append(
                    "미보정 방향 점수를 실제 발생확률로 표현했습니다."
                )
                break
    if (
        isinstance(scenario_build, dict)
        and scenario_build.get("horizon_mismatch") is True
    ):
        for line in markdown.splitlines():
            if (
                re.search(
                    r"(?:결제기간|결제일까지|90일).{0,40}"
                    r"(?:예측|전망)",
                    line,
                    re.IGNORECASE,
                )
                and "예측하지" not in line
                and "예측이 아닙니다" not in line
            ):
                issues.append(
                    "21거래일 모델을 결제기간 밖으로 외삽했습니다."
                )
                break
    if (
        isinstance(market_context, dict)
        and market_context.get("news_used_as_predictor") is False
    ):
        for line in markdown.splitlines():
            if (
                re.search(
                    r"뉴스.{0,40}(?:환율|손실|결제액).{0,30}"
                    r"(?:계산에 반영|수치를 변경|숫자를 변경)",
                    line,
                    re.IGNORECASE,
                )
                and "반영하지" not in line
                and "변경하지" not in line
            ):
                issues.append(
                    "설명용 뉴스를 금융 숫자 계산에 사용한 것처럼 "
                    "표현했습니다."
                )
                break
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

    missing_sections = _missing_sections(markdown, source_bundle)
    for label in missing_sections:
        issue = "필수 보고서 섹션 누락: {}".format(label)
        issues.append(issue)
        recommendation_issues.append(issue)

    for issue in _product_grounding_issues(markdown, source_bundle):
        issues.append(issue)
        evidence_issues.append(issue)
        recommendation_issues.append(issue)

    for issue in _consultation_grounding_issues(
        markdown,
        source_bundle,
    ):
        issues.append(issue)
        evidence_issues.append(issue)
        recommendation_issues.append(issue)

    for issue in _risk_boundary_issues(markdown):
        issues.append(issue)
        recommendation_issues.append(issue)
        prohibited_claims.append(issue)

    for issue in _market_policy_issues(markdown, source_bundle):
        issues.append(issue)
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
