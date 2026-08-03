import re
from typing import List, Set

from src.domain.country_economic_interpretation_models import (
    CountryEconomicInterpretationDraft,
    CountryEconomicInterpretationInput,
)


ASCII_DIGIT_RE = re.compile(r"[0-9]")
URL_RE = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
MARKUP_RE = re.compile(r"```|<[^>]+>|\||^\s*#{1,6}\s", re.MULTILINE)
REWRITTEN_VALUE_RE = re.compile(
    r"(?:퍼센트|백분율|\bUSD\b|\bKRW\b|달러|유로)",
    re.IGNORECASE,
)
PROHIBITED_PATTERNS = (
    re.compile(r"(?:안전|위험)한\s*국가"),
    re.compile(r"고위험\s*국가(?:로)?\s*(?:확정|판정)"),
    re.compile(r"저위험\s*국가(?:로)?\s*(?:확정|판정)"),
    re.compile(r"(?:거래처\s*)?부도.{0,12}(?:확률|가능성)"),
    re.compile(r"지급불능.{0,12}(?:확률|가능성)"),
    re.compile(r"(?:보험|대출).{0,12}승인\s*가능성"),
    re.compile(r"정책자금.{0,12}(?:대상|자격).{0,8}(?:확정|입니다)"),
    re.compile(r"환율.{0,8}(?:상승|하락).{0,8}(?:예상|전망|예측)"),
    re.compile(r"(?:반드시\s*가입|가입해야\s*함|가입해야\s*합니다)"),
    re.compile(r"(?:최적\s*상품|확정\s*추천|헤지\s*비율)"),
    re.compile(r"(?:국가\s*위험점수|종합\s*위험등급)"),
)
PRODUCT_OR_INSTITUTION_PATTERNS = (
    "한국무역보험공사",
    "국민은행",
    "중소벤처기업진흥공단",
    "단기수출보험",
    "환변동보험",
    "수출신용보증",
    "선물환거래",
    "외환스왑",
    "수출환어음매입",
    "신시장진출지원자금",
)


class CountryEconomicInterpretationValidationError(ValueError):
    def __init__(self, issues: List[str]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


def _sentence_count(value: str) -> int:
    return len(
        [item for item in re.split(r"[.!?。！？]+", value) if item.strip()]
    )


def _text_issues(value: str, field_path: str) -> List[str]:
    issues: List[str] = []
    if ASCII_DIGIT_RE.search(value):
        issues.append("{}에 아라비아 숫자가 있습니다.".format(field_path))
    if not re.search(r"[가-힣]", value):
        issues.append("{}가 한국어 설명이 아닙니다.".format(field_path))
    if REWRITTEN_VALUE_RE.search(value):
        issues.append("{}에 다시 쓴 지표값 또는 금액이 있습니다.".format(field_path))
    if URL_RE.search(value):
        issues.append("{}에 URL이 있습니다.".format(field_path))
    if MARKUP_RE.search(value):
        issues.append("{}에 Markdown 또는 HTML이 있습니다.".format(field_path))
    for pattern in PROHIBITED_PATTERNS:
        if pattern.search(value):
            issues.append("{}에 금지 판단 표현이 있습니다.".format(field_path))
            break
    if any(item in value for item in PRODUCT_OR_INSTITUTION_PATTERNS):
        issues.append("{}에 상품명 또는 기관명이 있습니다.".format(field_path))
    if re.search(r"(?:상담\s*)?순위|(?:위험|추천|신용)\s*점수", value):
        issues.append("{}에 순위 또는 점수가 있습니다.".format(field_path))
    return issues


def validate_country_economic_interpretation(
    *,
    draft: CountryEconomicInterpretationDraft,
    interpretation_input: CountryEconomicInterpretationInput,
) -> None:
    issues = _text_issues(draft.overall_summary, "overall_summary")
    if _sentence_count(draft.overall_summary) > 2:
        issues.append("overall_summary는 두 문장을 초과할 수 없습니다.")

    expected: List[str] = [
        item.indicator_id for item in interpretation_input.indicators
    ]
    actual: List[str] = [item.indicator_id for item in draft.sections]
    actual_set: Set[str] = set(actual)
    if len(actual) != len(actual_set):
        issues.append("indicator_id가 중복되었습니다.")
    unknown = [item for item in actual if item not in expected]
    if unknown:
        issues.append("입력에 없는 indicator_id가 생성되었습니다.")
    if actual != expected:
        issues.append("indicator section이 입력 순서와 일치하지 않습니다.")

    for index, section in enumerate(draft.sections):
        observation_path = "sections.{}.observation".format(index)
        check_path = "sections.{}.transaction_check".format(index)
        issues.extend(_text_issues(section.observation, observation_path))
        issues.extend(_text_issues(section.transaction_check, check_path))
        if _sentence_count(section.observation) != 1:
            issues.append("{}은 한 문장이어야 합니다.".format(observation_path))
        if _sentence_count(section.transaction_check) != 1:
            issues.append("{}은 한 문장이어야 합니다.".format(check_path))

    for index, limitation in enumerate(draft.limitations):
        path = "limitations.{}".format(index)
        issues.extend(_text_issues(limitation, path))
        if _sentence_count(limitation) != 1:
            issues.append("{}은 한 문장이어야 합니다.".format(path))

    if issues:
        raise CountryEconomicInterpretationValidationError(
            list(dict.fromkeys(issues))
        )
