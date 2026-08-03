import re
from typing import List

from src.domain.trade_statistics_interpretation_models import (
    TradeStatisticsInterpretationDraft,
    TradeStatisticsInterpretationInput,
)


ASCII_DIGIT_RE = re.compile(r"[0-9]")
URL_RE = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
MARKUP_RE = re.compile(
    r"```|<[^>]+>|\||\*\*|__|^\s*#{1,6}\s",
    re.MULTILINE,
)
VALUE_RE = re.compile(
    r"(?:퍼센트|백분율|\bUSD\b|\bKRW\b|달러|유로|[₩$€¥])",
    re.IGNORECASE,
)
PROHIBITED_PATTERNS = (
    re.compile(r"(?:안전|위험)한\s*(?:국가|시장|거래처)"),
    re.compile(r"(?:거래처|구매자).{0,12}(?:신용도|신용등급).{0,12}(?:높|낮|좋|나쁘)"),
    re.compile(r"(?:부도|지급불능|대금\s*회수).{0,16}(?:확률|가능성).{0,12}(?:높|낮|있|없)"),
    re.compile(r"환율.{0,10}(?:상승|하락).{0,10}(?:예상|전망|예측)"),
    re.compile(r"(?:헤지\s*비율|국가\s*위험점수|종합\s*위험등급)"),
    re.compile(r"(?:반드시\s*가입|가입해야\s*함|가입해야\s*합니다)"),
    re.compile(r"(?:최적\s*상품|확정\s*추천|거래\s*(?:진행|중단))"),
    re.compile(
        r"(?:금융\s*)?상품.{0,10}(?:추천|가입)|"
        r"(?:보험|대출|보증|정책자금).{0,10}(?:추천|필수|가입)"
    ),
    re.compile(r"(?:승인|자격).{0,12}(?:확정|보장|가능합니다)"),
    re.compile(
        r"(?:수출|수입|교역|무역수지).{0,18}(?:증가|감소|흑자|적자)"
        r".{0,24}(?:때문|따라서|그러므로).{0,24}"
        r"(?:안전|위험|신용|회수|지급능력)"
    ),
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
    "정책자금",
)


class TradeStatisticsInterpretationValidationError(ValueError):
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
    if VALUE_RE.search(value):
        issues.append("{}에 통계값 또는 통화금액이 있습니다.".format(field_path))
    if URL_RE.search(value):
        issues.append("{}에 URL이 있습니다.".format(field_path))
    if MARKUP_RE.search(value):
        issues.append("{}에 Markdown 또는 HTML이 있습니다.".format(field_path))
    if any(pattern.search(value) for pattern in PROHIBITED_PATTERNS):
        issues.append("{}에 금지 판단 표현이 있습니다.".format(field_path))
    if any(item in value for item in PRODUCT_OR_INSTITUTION_PATTERNS):
        issues.append("{}에 상품명 또는 기관명이 있습니다.".format(field_path))
    if re.search(r"(?:상담\s*)?순위|(?:위험|추천|신용)\s*점수", value):
        issues.append("{}에 순위 또는 점수가 있습니다.".format(field_path))
    return issues


def _direction_issue(
    summary: str,
    direction: str,
) -> List[str]:
    requirements = {
        "INCREASED": ("증가",),
        "DECREASED": ("감소",),
        "UNCHANGED": ("유사", "큰 변화"),
        "UNAVAILABLE": ("자료", "어렵"),
    }
    if any(item in summary for item in requirements[direction]):
        return []
    return ["summary가 결정론적 수출 증감 방향과 일치하지 않습니다."]


def _limitation_issues(value: str) -> List[str]:
    issues: List[str] = []
    if not all(item in value for item in ("양국", "전체", "교역")):
        issues.append("limitation에 양국 전체 교역 정보라는 한계가 없습니다.")
    if not (
        "개별 거래처" in value
        and "신용" in value
        and re.search(r"(?:아니|않|의미하지)", value)
    ):
        issues.append("limitation에 개별 거래처 신용평가 한계가 없습니다.")
    if not (
        "대금 회수" in value
        and "가능성" in value
        and re.search(r"(?:아니|않|의미하지)", value)
    ):
        issues.append("limitation에 대금 회수 가능성 한계가 없습니다.")
    return issues


def validate_trade_statistics_interpretation(
    *,
    draft: TradeStatisticsInterpretationDraft,
    interpretation_input: TradeStatisticsInterpretationInput,
) -> None:
    issues = _text_issues(draft.summary, "summary")
    issues.extend(_text_issues(draft.limitation, "limitation"))
    if _sentence_count(draft.summary) != 1:
        issues.append("summary는 한 문장이어야 합니다.")
    if _sentence_count(draft.limitation) != 1:
        issues.append("limitation은 한 문장이어야 합니다.")
    issues.extend(
        _direction_issue(
            draft.summary,
            interpretation_input.export_change_direction,
        )
    )
    issues.extend(_limitation_issues(draft.limitation))
    if issues:
        raise TradeStatisticsInterpretationValidationError(
            list(dict.fromkeys(issues))
        )
