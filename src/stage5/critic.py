import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any, List, Set, Tuple

from src.consultation.review_area import (
    project_consultation_presentation,
)
from src.domain.consultation_models import ConsultationPriorityView
from src.domain.report_models import ReportCritique
from src.stage4.local_kb import active_official_catalogue_by_id


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
COUNTRY_REVIEW_PRIORITY_LABELS = {
    "STANDARD_REVIEW": "통상 검토",
    "ELEVATED_REVIEW": "추가 검토",
    "HIGH_REVIEW": "우선 검토",
    "INSUFFICIENT_INFORMATION": "정보 부족",
}
TRADE_STATISTICS_DISPLAY_PERCENT_PATHS = {
    "consultation.trade_statistics.summary.export_yoy_pct",
    "consultation.trade_statistics.summary.import_yoy_pct",
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


def _display_numbers_for_path(
    source_bundle: Any,
    path: str,
) -> Set[str]:
    if path not in TRADE_STATISTICS_DISPLAY_PERCENT_PATHS:
        return set()
    try:
        value = _resolve_path(source_bundle, path)
        if value is None:
            return set()
        rendered = "{:+,.1f}%".format(Decimal(str(value)))
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return set()
    return {_normalized_number(rendered)}


def _missing_sections(
    markdown: str,
    source_bundle: Any,
) -> List[str]:
    required = list(REQUIRED_SECTIONS)
    if (
        isinstance(source_bundle, dict)
        and isinstance(source_bundle.get("consultation"), dict)
    ):
        consultation = source_bundle["consultation"]
        required.extend(
            [
                (
                    "거래·결제조건 위험",
                    ("거래·결제조건 위험", "결제·회수 위험"),
                ),
                (
                    "상담 우선순위",
                    (
                        "상담 우선순위",
                        "검토할 금융 대응",
                        "금융 대응",
                    ),
                ),
            ]
        )
        if consultation.get("consultation_supporting_checks"):
            required.append(
                (
                    "추가 확인사항",
                    ("추가 확인사항",),
                )
            )
        if isinstance(
            consultation.get("country_environment"),
            dict,
        ):
            required.append(
                (
                    "국가·무역환경 검토",
                    ("국가·무역환경 검토",),
                )
            )
        if isinstance(consultation.get("trade_statistics"), dict):
            required.append(
                (
                    "거래국 무역 통계",
                    ("거래국 무역 통계",),
                )
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
        section_text = product_section.group(1)
        candidate_positions: List[int] = []
        for index in range(len(candidates)):
            source_path = "{}.{}".format(source_prefix, index)
            position = section_text.find(
                "[source: {}]".format(source_path)
            )
            if position < 0:
                issues.append(
                    "packet shortlist의 공식 후보가 보고서에서 누락됐습니다."
                )
            else:
                candidate_positions.append(position)
        if candidate_positions != sorted(candidate_positions):
            issues.append(
                "공식 후보 순서가 packet shortlist와 다르게 변경됐습니다."
            )
        for line in section_text.splitlines():
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

    response_section = re.search(
        r"(?is)##[^\n]*(?:상담 우선순위|검토할 금융 대응)[^\n]*\n"
        r"(.*?)(?=\n##|\Z)",
        markdown,
    )
    supporting_section = re.search(
        r"(?is)##[^\n]*추가 확인사항[^\n]*\n"
        r"(.*?)(?=\n##|\Z)",
        markdown,
    )
    review_areas = consultation.get("consultation_review_areas", [])
    supporting_checks = consultation.get(
        "consultation_supporting_checks",
        [],
    )
    if (
        isinstance(review_areas, list)
        and isinstance(supporting_checks, list)
        and (review_areas or supporting_checks)
    ):
        priority_payloads = consultation.get(
            "consultation_priorities",
            [],
        )
        priority_fingerprint = str(
            consultation.get("consultation_priority_fingerprint", "")
        )
        try:
            expected_presentation = project_consultation_presentation(
                priorities=[
                    ConsultationPriorityView.model_validate(item)
                    for item in priority_payloads
                ],
                priority_fingerprint=priority_fingerprint,
            )
        except (TypeError, ValueError):
            issues.append(
                "상담 검토 분야를 기존 priority에 결정론적으로 연결할 수 "
                "없습니다."
            )
        else:
            if [
                item.model_dump()
                for item in expected_presentation.review_areas
            ] != review_areas:
                issues.append(
                    "상담 검토 분야 projection이 기존 priority와 "
                    "일치하지 않습니다."
                )
            if [
                item.model_dump()
                for item in expected_presentation.supporting_checks
            ] != supporting_checks:
                issues.append(
                    "추가 확인사항 projection이 기존 priority와 "
                    "일치하지 않습니다."
                )
        represented_categories: List[str] = []
        for item in review_areas + supporting_checks:
            if isinstance(item, dict):
                categories = item.get("source_priority_categories", [])
                if isinstance(categories, list):
                    represented_categories.extend(
                        str(category) for category in categories
                    )
        priority_categories = [
            str(item.get("category", ""))
            for item in priority_payloads
            if isinstance(item, dict)
        ]
        if (
            len(represented_categories) != len(priority_categories)
            or sorted(represented_categories)
            != sorted(priority_categories)
        ):
            issues.append(
                "기존 priority가 상담 검토 분야와 추가 확인사항 중 "
                "정확히 한 곳에 분류되지 않았습니다."
            )
        if any(
            isinstance(item, dict)
            and item.get("review_area_id") == "POLICY_FINANCE"
            for item in review_areas
        ):
            issues.append(
                "명시적 policy finance category 없이 정책자금 검토가 "
                "생성됐습니다."
            )
        if review_areas and response_section is None:
            issues.append("상담 검토 분야 섹션이 없습니다.")
        response_text = (
            response_section.group(1)
            if response_section is not None
            else ""
        )
        expected_paths = [
            "consultation.consultation_review_areas.{}".format(index)
            for index in range(len(review_areas))
        ]
        actual_paths = [
            item
            for item in SOURCE_TAG_RE.findall(response_text)
            if item.startswith(
                "consultation.consultation_review_areas."
            )
        ]
        if actual_paths != expected_paths:
            issues.append(
                "상담 검토 분야 개수 또는 순서가 구조화 결과와 "
                "일치하지 않습니다."
            )
        rendered_priority_count = len(
            re.findall(
                r"(?:^|\n)\s*-\s*\*\*\d+순위\s+",
                response_text,
            )
        )
        if rendered_priority_count != len(review_areas):
            issues.append(
                "존재하지 않는 상담 검토 분야가 추가됐거나 기존 분야가 "
                "삭제됐습니다."
            )
        positions: List[int] = []
        for index, review_area in enumerate(review_areas):
            if not isinstance(review_area, dict):
                continue
            source_path = expected_paths[index]
            source_tag = "[source: {}]".format(source_path)
            position = response_text.find(source_tag)
            if position < 0:
                issues.append(
                    "상담 검토 분야에 구조화된 projection 근거가 없습니다."
                )
                continue
            positions.append(position)
            sourced_text = " ".join(
                line
                for line in response_text.splitlines()
                if source_tag in line
            )
            display_name = str(
                review_area.get("display_name", "")
            ).strip()
            rank = review_area.get("rank")
            expected_heading = (
                "**{}순위 {}**".format(rank, display_name)
                if rank is not None and display_name
                else ""
            )
            if expected_heading and expected_heading not in sourced_text:
                issues.append(
                    "상담 검토 분야 표시명이 구조화 결과와 일치하지 않습니다."
                )
            if rank is not None and "{}순위".format(rank) not in sourced_text:
                issues.append(
                    "상담 검토 분야 rank가 기존 priority rank와 "
                    "일치하지 않습니다."
                )
            for field, issue in (
                (
                    "summary",
                    "상담 검토 분야 선정 이유가 누락되거나 변경됐습니다.",
                ),
                (
                    "expected_decision",
                    "상담 검토 분야 expected decision이 누락되거나 변경됐습니다.",
                ),
                (
                    "next_action",
                    "상담 검토 분야 next action이 누락되거나 변경됐습니다.",
                ),
                (
                    "disclaimer",
                    "상담 검토 분야 고지문이 누락되거나 변경됐습니다.",
                ),
            ):
                expected = str(review_area.get(field, "")).strip()
                if expected and expected not in sourced_text:
                    issues.append(issue)
            evidence_items = review_area.get("evidence_items", [])
            if isinstance(evidence_items, list):
                for evidence in evidence_items:
                    if not isinstance(evidence, dict):
                        continue
                    label = str(evidence.get("label", "")).strip()
                    value = str(evidence.get("value", "")).strip()
                    if (
                        (label and label not in sourced_text)
                        or (value and value not in sourced_text)
                    ):
                        issues.append(
                            "상담 검토 분야의 기존 evidence가 누락되거나 "
                            "변경됐습니다."
                        )
                        break
            missing_information = review_area.get(
                "missing_information",
                [],
            )
            if isinstance(missing_information, list) and any(
                str(item).strip()
                and str(item).strip() not in sourced_text
                for item in missing_information
            ):
                issues.append(
                    "상담 검토 분야의 확인 필요 정보가 누락되거나 변경됐습니다."
                )
        if positions != sorted(positions):
            issues.append(
                "상담 검토 분야가 기존 priority rank와 다르게 재정렬됐습니다."
            )
        if supporting_checks and supporting_section is None:
            issues.append("추가 확인사항 섹션이 없습니다.")
        if not supporting_checks and supporting_section is not None:
            issues.append(
                "존재하지 않는 추가 확인사항이 보고서에 생성됐습니다."
            )
        supporting_text = (
            supporting_section.group(1)
            if supporting_section is not None
            else ""
        )
        expected_supporting_paths = [
            "consultation.consultation_supporting_checks.{}".format(
                index
            )
            for index in range(len(supporting_checks))
        ]
        actual_supporting_paths = [
            item
            for item in SOURCE_TAG_RE.findall(supporting_text)
            if item.startswith(
                "consultation.consultation_supporting_checks."
            )
        ]
        if actual_supporting_paths != expected_supporting_paths:
            issues.append(
                "추가 확인사항 개수 또는 순서가 구조화 결과와 "
                "일치하지 않습니다."
            )
        supporting_positions: List[int] = []
        for index, supporting_check in enumerate(supporting_checks):
            if not isinstance(supporting_check, dict):
                continue
            source_path = expected_supporting_paths[index]
            source_tag = "[source: {}]".format(source_path)
            position = supporting_text.find(source_tag)
            if position < 0:
                issues.append(
                    "추가 확인사항에 구조화된 projection 근거가 없습니다."
                )
                continue
            supporting_positions.append(position)
            sourced_text = " ".join(
                line
                for line in supporting_text.splitlines()
                if source_tag in line
            )
            display_name = str(
                supporting_check.get("display_name", "")
            ).strip()
            if display_name and "**{}**".format(
                display_name
            ) not in sourced_text:
                issues.append(
                    "추가 확인사항 표시명이 구조화 결과와 일치하지 않습니다."
                )
            source_rank = supporting_check.get("source_rank")
            if (
                source_rank is not None
                and "원본 priority rank: {}".format(source_rank)
                not in sourced_text
            ):
                issues.append(
                    "추가 확인사항 source rank가 기존 priority rank와 "
                    "일치하지 않습니다."
                )
            for field, issue in (
                (
                    "summary",
                    "추가 확인사항의 기존 이유가 누락되거나 변경됐습니다.",
                ),
                (
                    "next_action",
                    "추가 확인사항 next action이 누락되거나 변경됐습니다.",
                ),
                (
                    "disclaimer",
                    "추가 확인사항 고지문이 누락되거나 변경됐습니다.",
                ),
            ):
                expected = str(
                    supporting_check.get(field, "")
                ).strip()
                if expected and expected not in sourced_text:
                    issues.append(issue)
            evidence_items = supporting_check.get("evidence_items", [])
            if isinstance(evidence_items, list):
                for evidence in evidence_items:
                    if not isinstance(evidence, dict):
                        continue
                    label = str(evidence.get("label", "")).strip()
                    value = str(evidence.get("value", "")).strip()
                    if (
                        (label and label not in sourced_text)
                        or (value and value not in sourced_text)
                    ):
                        issues.append(
                            "추가 확인사항의 기존 evidence가 누락되거나 "
                            "변경됐습니다."
                        )
                        break
            missing_information = supporting_check.get(
                "missing_information",
                [],
            )
            if isinstance(missing_information, list) and any(
                str(item).strip()
                and str(item).strip() not in sourced_text
                for item in missing_information
            ):
                issues.append(
                    "추가 확인사항의 확인 필요 정보가 누락되거나 변경됐습니다."
                )
        if supporting_positions != sorted(supporting_positions):
            issues.append(
                "추가 확인사항이 기존 priority rank와 다르게 재정렬됐습니다."
            )
        shortlist = consultation.get("official_candidate_shortlist")
        shortlist_candidates = (
            shortlist.get("candidates", [])
            if isinstance(shortlist, dict)
            else []
        )
        for candidate in shortlist_candidates:
            if not isinstance(candidate, dict):
                continue
            name = str(candidate.get("name", "")).strip()
            if name and name in response_text:
                issues.append(
                    "상담 검토 분야와 공식 금융지원 후보가 한 섹션에 "
                    "혼합됐습니다."
                )
                break
            institution = str(candidate.get("institution", "")).strip()
            if (
                (name and name in supporting_text)
                or (institution and institution in supporting_text)
            ):
                issues.append(
                    "추가 확인사항과 공식 금융지원 후보가 한 섹션에 "
                    "혼합됐습니다."
                )
                break
        return list(dict.fromkeys(issues))
    priorities = consultation.get("consultation_priorities", [])
    if isinstance(priorities, list) and priorities:
        if response_section is None:
            issues.append("금융 대응 항목 섹션이 없습니다.")
            return list(dict.fromkeys(issues))
        response_text = response_section.group(1)
        shortlist = consultation.get("official_candidate_shortlist")
        shortlist_candidates = (
            shortlist.get("candidates", [])
            if isinstance(shortlist, dict)
            else []
        )
        authoritative_product_ids = {
            str(item.get("product_id", ""))
            for item in shortlist_candidates
            if isinstance(item, dict)
        }
        positions: List[int] = []
        for index, priority in enumerate(priorities):
            if not isinstance(priority, dict):
                continue
            source_path = (
                "consultation.consultation_priorities.{}".format(index)
            )
            position = response_text.find(
                "[source: {}]".format(source_path)
            )
            if position < 0:
                issues.append(
                    "상담 Top 3 항목에 구조화된 priority 근거가 없습니다."
                )
                continue
            positions.append(position)
            sourced_lines = [
                line
                for line in response_text.splitlines()
                if "[source: {}]".format(source_path) in line
            ]
            sourced_text = " ".join(sourced_lines)
            title = str(priority.get("title", "")).strip()
            if title and title not in sourced_text:
                issues.append(
                    "금융 대응 제목이 인용한 상담 항목과 일치하지 않습니다."
                )
            rank = priority.get("rank")
            if rank is not None and "{}순위".format(rank) not in sourced_text:
                issues.append(
                    "상담 검토 순위가 구조화된 priority와 일치하지 않습니다."
                )
            for field, issue in (
                (
                    "priority_reason",
                    "상담 priority 이유가 구조화 결과와 일치하지 않습니다.",
                ),
                (
                    "expected_decision",
                    "상담 expected decision이 구조화 결과와 일치하지 않습니다.",
                ),
                (
                    "next_action",
                    "상담 next action이 구조화 결과와 일치하지 않습니다.",
                ),
                (
                    "disclaimer",
                    "상담 검토 순위 고지문이 누락되거나 변경됐습니다.",
                ),
            ):
                expected = str(priority.get(field, "")).strip()
                if expected and expected not in sourced_text:
                    issues.append(issue)
            official_candidates = priority.get(
                "official_candidates",
                [],
            )
            if isinstance(official_candidates, list):
                for candidate in official_candidates:
                    if not isinstance(candidate, dict):
                        continue
                    product_id = str(
                        candidate.get("product_id", "")
                    )
                    if product_id not in authoritative_product_ids:
                        continue
                    name = str(candidate.get("name", "")).strip()
                    if name and name not in sourced_text:
                        issues.append(
                            "상품명이 인용한 공식 후보와 일치하지 않습니다."
                        )
                    institution = str(
                        candidate.get("institution", "")
                    ).strip()
                    if institution and institution not in sourced_text:
                        issues.append(
                            "기관명이 인용한 공식 후보와 일치하지 않습니다."
                        )
        if positions != sorted(positions):
            issues.append(
                "상담 Top 3가 구조화된 결정론 순서와 다르게 재정렬됐습니다."
            )
        return list(dict.fromkeys(issues))

    topics = consultation.get("consultation_topics", [])
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


def _trade_statistics_grounding_issues(
    markdown: str,
    source_bundle: Any,
) -> List[str]:
    if not isinstance(source_bundle, dict):
        return []
    consultation = source_bundle.get("consultation")
    if not isinstance(consultation, dict):
        return []
    statistics = consultation.get("trade_statistics")
    section = re.search(
        r"(?is)##[^\n]*거래국 무역 통계[^\n]*\n"
        r"(.*?)(?=\n##|\Z)",
        markdown,
    )
    if not isinstance(statistics, dict):
        if re.search(
            r"\[source:\s*consultation\.trade_statistics",
            markdown,
        ):
            return ["무역통계 결과가 없는데 해당 근거를 인용했습니다."]
        return []
    issues: List[str] = []
    if (
        section is None
        or not any(
            item.startswith("consultation.trade_statistics")
            for item in SOURCE_TAG_RE.findall(section.group(1))
        )
    ):
        issues.append("거래국 무역통계 주장에 구조화된 근거가 없습니다.")
    return issues


def _catalogue_shortlist_issues(source_bundle: Any) -> List[str]:
    if not isinstance(source_bundle, dict):
        return []
    consultation = source_bundle.get("consultation")
    if not isinstance(consultation, dict):
        return []
    shortlist = consultation.get("official_candidate_shortlist")
    if not isinstance(shortlist, dict):
        return []
    if shortlist.get("selection_policy") != "CATALOGUE_SIGNAL_FILTER_V1":
        return []
    candidates = shortlist.get("candidates", [])
    if not isinstance(candidates, list):
        return ["공식 후보 shortlist가 목록 형식이 아닙니다."]
    issues: List[str] = []
    catalogue = active_official_catalogue_by_id()
    families: Set[str] = set()
    review_area_ids = {
        str(item.get("review_area_id", ""))
        for item in consultation.get("consultation_review_areas", [])
        if isinstance(item, dict)
    }
    supporting_terms: Set[str] = set()
    for item in consultation.get("consultation_supporting_checks", []):
        if not isinstance(item, dict):
            continue
        supporting_terms.update(
            str(item.get(field, "")).strip()
            for field in (
                "check_id",
                "display_name",
                "source_priority_category",
            )
        )
    for candidate in candidates:
        if not isinstance(candidate, dict):
            issues.append("공식 후보가 객체 형식이 아닙니다.")
            continue
        catalogue_id = str(candidate.get("catalogue_id", ""))
        product_id = str(candidate.get("product_id", ""))
        record = catalogue.get(catalogue_id)
        if not catalogue_id or catalogue_id != product_id or record is None:
            issues.append(
                "최종 후보가 active catalogue stable ID에 연결되지 않았습니다."
            )
            continue
        expected = {
            "name": record.name,
            "official_name": record.official_name,
            "institution": record.institution,
            "category": record.category,
            "candidate_family": record.candidate_family,
        }
        if any(candidate.get(field) != value for field, value in expected.items()):
            issues.append(
                "최종 후보의 명칭·기관·분류가 catalogue와 일치하지 않습니다."
            )
        source = candidate.get("source")
        if (
            not isinstance(source, dict)
            or source.get("url") != record.source.url
        ):
            issues.append("최종 후보 URL이 catalogue와 일치하지 않습니다.")
        family = str(candidate.get("candidate_family", ""))
        if family and family in families:
            issues.append("최종 후보에 동일 candidate family가 중복됐습니다.")
        families.add(family)
        if candidate.get("category") == "OFFICIAL_WEB_RESULT":
            issues.append("AI 공식 웹 검색 결과가 최종 후보에 진입했습니다.")
        if (
            candidate.get("category") == "POLICY_FINANCE"
            and "POLICY_FINANCE" not in review_area_ids
        ):
            issues.append(
                "정책자금 검토 분야 없이 정책자금 후보가 생성됐습니다."
            )
        selection_text = " ".join(
            [str(candidate.get("strategy_connection_reason", ""))]
            + [
                str(item)
                for item in candidate.get("selection_reasons", [])
            ]
        )
        if any(term and term in selection_text for term in supporting_terms):
            issues.append(
                "추가 확인사항이 공식 후보 eligibility 또는 선정 이유로 사용됐습니다."
            )
    if len(candidates) > 3:
        issues.append("공식 후보가 최대 3개를 초과했습니다.")
    return list(dict.fromkeys(issues))
    text = section.group(1)
    summary = statistics.get("summary")
    if not isinstance(summary, dict):
        return issues
    scope = str(summary.get("scope", ""))
    expected_scope = (
        "국가 전체 교역" if scope == "COUNTRY_TOTAL" else "확인된 HS 품목"
    )
    if scope in {"COUNTRY_TOTAL", "HS_ITEM"} and expected_scope not in text:
        issues.append("무역통계 범위가 구조화된 요약과 일치하지 않습니다.")
    hs_code = summary.get("hs_code")
    if hs_code is None:
        if "HS Code가 확인되지 않아" not in text:
            issues.append("HS Code 미확인 상태가 보고서에 유지되지 않았습니다.")
    elif str(hs_code) not in text:
        issues.append("HS Code가 구조화된 무역통계 요약과 일치하지 않습니다.")
    source_refs = summary.get("source_refs", [])
    official_urls = {
        str(item.get("official_url", ""))
        for item in source_refs
        if isinstance(item, dict)
    }
    for url in URL_RE.findall(text):
        if url not in official_urls:
            issues.append("무역통계 URL이 snapshot 공식 출처와 일치하지 않습니다.")
    return list(dict.fromkeys(issues))


def _trade_statistics_policy_boundary_issues(markdown: str) -> List[str]:
    issues: List[str] = []
    subject = r"(?:무역통계|교역(?:규모|흐름|증감)|수출입\s*(?:통계|증감))"
    negation = r"(?:아니|않|금지|의미하지|변경하지|판단하지|예측하지)"
    for line in markdown.splitlines():
        if not re.search(subject, line, re.IGNORECASE):
            continue
        if re.search(negation, line):
            continue
        if re.search(
            r"(?:부도확률|거래처\s*신용위험|국가\s*위험\s*점수)",
            line,
            re.IGNORECASE,
        ):
            issues.append(
                "무역통계를 거래처·국가 신용위험이나 부도확률로 "
                "변환했습니다."
            )
        if re.search(
            r"환율.{0,25}(?:상승|하락).{0,18}(?:예측|근거|가능성)",
            line,
            re.IGNORECASE,
        ):
            issues.append("무역통계를 환율 방향 예측 근거로 사용했습니다.")
        if re.search(
            r"(?:환헤지|헤지).{0,18}(?:비율|비중).{0,18}"
            r"(?:변경|조정|늘|줄|증가|감소)",
            line,
            re.IGNORECASE,
        ):
            issues.append("무역통계로 헤지 비율을 변경했습니다.")
        if re.search(
            r"(?:금융상품\s*승인\s*가능성|상담\s*(?:우선)?순위)"
            r".{0,18}(?:변경|상승|하락|높|낮)",
            line,
            re.IGNORECASE,
        ):
            issues.append(
                "무역통계로 금융상품 승인 가능성이나 상담 순위를 "
                "변경했습니다."
            )
    return list(dict.fromkeys(issues))


def _trade_statistics_interpretation_grounding_issues(
    markdown: str,
    source_bundle: Any,
) -> List[str]:
    if not isinstance(source_bundle, dict):
        return []
    consultation = source_bundle.get("consultation")
    if not isinstance(consultation, dict):
        return []
    interpretation = consultation.get(
        "trade_statistics_interpretation"
    )
    if not isinstance(interpretation, dict):
        if "consultation.trade_statistics_interpretation" in markdown:
            return ["무역통계 해석이 없는데 해당 근거를 인용했습니다."]
        return []
    expected = [
        str(interpretation.get("summary", "")).strip(),
        str(interpretation.get("limitation", "")).strip(),
    ]
    if any(item and item not in markdown for item in expected):
        return [
            "검증 완료된 무역통계 해석이 보고서에서 재작성되거나 "
            "누락됐습니다."
        ]
    return []


def _country_interpretation_grounding_issues(
    markdown: str,
    source_bundle: Any,
) -> List[str]:
    if not isinstance(source_bundle, dict):
        return []
    consultation = source_bundle.get("consultation")
    if not isinstance(consultation, dict):
        return []
    interpretation = consultation.get(
        "country_economic_interpretation"
    )
    if not isinstance(interpretation, dict):
        if "consultation.country_economic_interpretation" in markdown:
            return ["국가 경제환경 해석이 없는데 해당 근거를 인용했습니다."]
        return []
    expected = [str(interpretation.get("overall_summary", "")).strip()]
    for section in interpretation.get("sections", []):
        if not isinstance(section, dict):
            continue
        expected.extend(
            [
                str(section.get("observation", "")).strip(),
                str(section.get("transaction_check", "")).strip(),
            ]
        )
    expected.extend(
        str(item).strip()
        for item in interpretation.get("limitations", [])
    )
    missing = [item for item in expected if item and item not in markdown]
    if missing:
        return [
            "검증 완료된 국가 경제환경 설명이 보고서에서 재작성되거나 누락됐습니다."
        ]
    return []


def _consultation_priority_boundary_issues(
    markdown: str,
    source_bundle: Any,
) -> List[str]:
    del source_bundle
    issues: List[str] = []
    for line in markdown.splitlines():
        negated = bool(
            re.search(
                r"(?:아니|않|금지|확정하지|판단하지|보장하지)",
                line,
            )
        )
        if (
            re.search(
                r"(?:상담|검토).{0,20}(?:순위|우선순위).{0,30}"
                r"(?:승인등급|승인\s*가능성|보험\s*인수등급|대출\s*등급)",
                line,
                re.IGNORECASE,
            )
            and not negated
        ):
            issues.append(
                "상담 검토 순위를 승인·인수·대출 등급으로 표현했습니다."
            )
        if (
            re.search(
                r"(?:buffer|버퍼|운영자금).{0,45}"
                r"(?:지급불능|부도|대출.{0,12}필요)",
                line,
                re.IGNORECASE,
            )
            and not negated
        ):
            issues.append(
                "buffer shortfall을 지급불능 또는 대출 필요성으로 표현했습니다."
            )
        if (
            re.search(
                r"(?:예정\s*(?:수취|결제)\s*(?:액|노출액)|"
                r"USD\s*100[,\s]?000).{0,40}"
                r"(?:실제\s*)?(?:현재\s*)?(?:미수|미지급)잔액",
                line,
                re.IGNORECASE,
            )
            and not negated
        ):
            issues.append(
                "예정 결제 노출액을 실제 현재 미수·미지급잔액으로 표현했습니다."
            )
        if (
            re.search(
                r"(?:Stage\s*3|헤지|선물환).{0,35}"
                r"(?:최적\s*(?:추천|상품|헤지)|반드시\s*실행|"
                r"가장\s*좋은\s*추천)",
                line,
                re.IGNORECASE,
            )
            and not negated
        ):
            issues.append(
                "Stage 3 계산상 후보를 최적 추천 또는 실행 지시로 표현했습니다."
            )
        if (
            re.search(
                r"(?:RM|상담자|영업점|KB\s*내부).{0,35}"
                r"(?:전송\s*완료|예약\s*완료|신청\s*완료|"
                r"심사\s*연결\s*완료)",
                line,
                re.IGNORECASE,
            )
            and not negated
        ):
            issues.append(
                "다운로드 또는 상담 준비를 실제 RM 전송·예약·신청으로 "
                "표현했습니다."
            )
    return list(dict.fromkeys(issues))


def _country_environment_grounding_issues(
    markdown: str,
    source_bundle: Any,
) -> List[str]:
    if not isinstance(source_bundle, dict):
        return []
    consultation = source_bundle.get("consultation")
    if not isinstance(consultation, dict):
        return []
    country_environment = consultation.get("country_environment")
    section = re.search(
        r"(?is)##[^\n]*국가·무역환경 검토[^\n]*\n"
        r"(.*?)(?=\n##|\Z)",
        markdown,
    )
    if not isinstance(country_environment, dict):
        if re.search(
            r"\[source:\s*consultation\.country_environment",
            markdown,
        ):
            return [
                "국가·무역환경 결과가 없는데 해당 근거를 인용했습니다."
            ]
        return []
    issues: List[str] = []
    if (
        section is None
        or not any(
            item.startswith("consultation.country_environment")
            for item in SOURCE_TAG_RE.findall(section.group(1))
        )
    ):
        issues.append(
            "국가·무역환경 주장에 구조화된 T4 근거가 없습니다."
        )
        return issues
    text = section.group(1)
    country = str(country_environment.get("country", ""))
    if country and country not in text:
        issues.append("거래국이 T4 구조화 결과와 일치하지 않습니다.")
    priority = str(
        country_environment.get("review_priority", "")
    )
    priority_label = COUNTRY_REVIEW_PRIORITY_LABELS.get(priority)
    if priority_label and priority_label not in text:
        issues.append(
            "국가·무역환경 검토 우선순위가 구조화 결과와 일치하지 않습니다."
        )

    references = country_environment.get(
        "official_source_references",
        [],
    )
    official_urls = {
        str(item.get("official_url", ""))
        for item in references
        if isinstance(item, dict)
    }
    for url in URL_RE.findall(text):
        if url not in official_urls:
            issues.append(
                "국가·무역환경 URL이 snapshot 공식 출처와 일치하지 않습니다."
            )

    oecd = country_environment.get("oecd_payment_transfer", {})
    if isinstance(oecd, dict):
        status = str(oecd.get("status", ""))
        raw = oecd.get("raw_classification")
        if status == "CLASSIFIED" and raw == 4:
            if re.search(
                r"(?:KBaiAgent\s*)?(?:국가|위험|신용)\s*등급"
                r".{0,12}(?<![0-9])4(?![0-9])",
                text,
                re.IGNORECASE,
            ):
                issues.append(
                    "Brazil OECD raw 4를 자체 국가등급으로 표현했습니다."
                )
        if status == "HIGH_INCOME_OECD_UNCLASSIFIED":
            for line in text.splitlines():
                if "미분류" not in line:
                    continue
                affirmative_low_claim = re.search(
                    r"미분류.{0,35}"
                    r"(?:\bLOW\b|(?<![0-9])0(?![0-9])|안전|"
                    r"낮은\s*위험).{0,12}"
                    r"(?:입니다|이다|로\s*(?:판정|분류|간주)|"
                    r"으로\s*(?:판정|분류|간주))",
                    line,
                    re.IGNORECASE,
                )
                if (
                    affirmative_low_claim
                    or (
                        re.search(
                            r"(?:\bLOW\b|(?<![0-9])0(?![0-9])|"
                            r"안전|낮은\s*위험)",
                            line,
                            re.IGNORECASE,
                        )
                        and not re.search(
                            r"(?:아니|않|금지|변환하지|의미하지)",
                            line,
                        )
                    )
                ):
                    issues.append(
                        "US OECD 미분류를 LOW·0·안전으로 표현했습니다."
                    )
                if (
                    re.search(r"(?:자료\s*없음|정보\s*부족)", line)
                    and not re.search(r"(?:아니|구분)", line)
                ):
                    issues.append(
                        "US OECD 미분류를 DATA_UNAVAILABLE과 혼동했습니다."
                    )

    if (
        re.search(
            r"(?:OECD|World Bank|WTO).{0,80}"
            r"(?:합산|가중평균|종합).{0,30}"
            r"(?:0\s*[~～-]\s*100|100\s*점|점수)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        and not re.search(
            r"(?:합산|가중평균|종합).{0,20}"
            r"(?:않|아니|금지|만들지)",
            text,
        )
    ):
        issues.append("세 국가 신호를 하나의 숫자 점수로 합산했습니다.")

    world_bank = country_environment.get(
        "world_bank_macro_environment",
        {},
    )
    observations = (
        world_bank.get("observations", [])
        if isinstance(world_bank, dict)
        else []
    )
    periods = {
        str(item.get("observation_period", ""))
        for item in observations
        if isinstance(item, dict)
    }
    if len(periods) > 1:
        for line in text.splitlines():
            if (
                re.search(
                    r"(?:모든|세)\s*지표.{0,25}"
                    r"(?:같은\s*시점|동일\s*연도|2025년)",
                    line,
                )
                and not re.search(r"(?:아니|않|다르)", line)
            ):
                issues.append(
                    "서로 다른 World Bank 관측연도를 같은 시점으로 표현했습니다."
                )
    return list(dict.fromkeys(issues))


def _country_policy_boundary_issues(markdown: str) -> List[str]:
    issues: List[str] = []
    for line in markdown.splitlines():
        if (
            re.search(
                r"(?:국가|OECD|World Bank|WTO).{0,35}"
                r"(?:신용등급|부도확률|공식\s*심사등급)",
                line,
                re.IGNORECASE,
            )
            and not re.search(
                r"(?:아니|않|금지|제공하지|만들지|변환하지)",
                line,
            )
        ):
            issues.append(
                "국가 신호를 국가 신용등급·부도확률·공식 심사등급으로 표현했습니다."
            )
        if (
            re.search(
                r"(?:국가|OECD|World Bank|WTO).{0,45}"
                r"(?:환헤지|선물환).{0,20}(?:비율|비중).{0,20}"
                r"(?:변경|조정|높|낮|늘|줄)",
                line,
                re.IGNORECASE,
            )
            and not re.search(r"(?:않|아니|금지)", line)
        ):
            issues.append("국가 신호로 환헤지 비율을 변경했습니다.")
        if (
            re.search(
                r"(?:국가|OECD|World Bank|WTO).{0,45}"
                r"(?:Stage\s*2|현금흐름|현금).{0,20}"
                r"(?:변경|조정|증가|감소)",
                line,
                re.IGNORECASE,
            )
            and not re.search(r"(?:않|아니|금지)", line)
        ):
            issues.append("국가 신호로 Stage 2 현금흐름을 변경했습니다.")
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
    for path in TRADE_STATISTICS_DISPLAY_PERCENT_PATHS:
        allowed_numbers.update(
            _display_numbers_for_path(source_bundle, path)
        )
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
                line_allowed_numbers.update(
                    _display_numbers_for_path(source_bundle, path)
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

    for issue in _catalogue_shortlist_issues(source_bundle):
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

    for issue in _country_environment_grounding_issues(
        markdown,
        source_bundle,
    ):
        issues.append(issue)
        evidence_issues.append(issue)
        recommendation_issues.append(issue)

    for issue in _country_interpretation_grounding_issues(
        markdown,
        source_bundle,
    ):
        issues.append(issue)
        evidence_issues.append(issue)
        recommendation_issues.append(issue)

    for issue in _trade_statistics_grounding_issues(
        markdown,
        source_bundle,
    ):
        issues.append(issue)
        evidence_issues.append(issue)
        recommendation_issues.append(issue)

    for issue in _trade_statistics_interpretation_grounding_issues(
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

    for issue in _consultation_priority_boundary_issues(
        markdown,
        source_bundle,
    ):
        issues.append(issue)
        recommendation_issues.append(issue)
        prohibited_claims.append(issue)

    for issue in _country_policy_boundary_issues(markdown):
        issues.append(issue)
        recommendation_issues.append(issue)
        prohibited_claims.append(issue)

    for issue in _trade_statistics_policy_boundary_issues(markdown):
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
