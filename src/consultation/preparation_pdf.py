import io
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader

from src.domain.confirmed_transaction_models import (
    ConfirmedTransactionSnapshot,
)
from src.domain.consultation_models import (
    ConsultationPacket,
    ConsultationReviewAreaView,
)
from src.domain.stage2_models import ScenarioResult, Stage2Result


PDF_TITLE = "KB 환담 상담 준비서"
PDF_SUBTITLE = "수출입 거래 금융상담을 위한 사전 정리자료"
PDF_MIME = "application/pdf"
PDF_DISCLAIMER = (
    "본 자료는 사용자가 확인한 거래정보와 시스템 분석 결과를 정리한 "
    "사전 상담 준비자료입니다. KB국민은행 또는 정책금융기관이 발급한 "
    "확인서·승인서가 아니며, 상품 가입·승인·한도·금리·보장 여부는 "
    "해당 기관의 상담과 심사를 통해 최종 결정됩니다."
)

A4_WIDTH = 1240
A4_HEIGHT = 1754
PDF_DPI = 150
MARGIN = 88
HEADER_HEIGHT = 124
FOOTER_HEIGHT = 182

NAVY = "#12345A"
DEEP_NAVY = "#0B2442"
YELLOW = "#FFCC00"
INK = "#172B4D"
MUTED = "#5C6B7A"
LINE = "#D7DEE8"
PALE_BLUE = "#F3F7FB"
PALE_YELLOW = "#FFF9E6"
WHITE = "#FFFFFF"
KOREA_TIMEZONE = timezone(timedelta(hours=9), name="KST")


class ConsultationPreparationPdfError(ValueError):
    pass


class ConsultationPreparationBindingError(
    ConsultationPreparationPdfError
):
    pass


class ConsultationPreparationFontError(ConsultationPreparationPdfError):
    pass


@dataclass(frozen=True)
class ConsultationPriorityContent:
    rank: int
    title: str
    institution_or_area: str
    reason: str
    core_check: str
    missing_information: Tuple[str, ...]
    preparation_documents: Tuple[str, ...]
    bank_questions: Tuple[str, ...]
    expected_decision: str
    next_action: str


@dataclass(frozen=True)
class ConsultationPreparationContent:
    document_number: str
    generated_at: str
    trade_type: str
    currency: str
    settlement_date: str
    consultation_purpose: str
    counterparty_country: str
    scheduled_amount: str
    balance_amount: str
    payment_method: str
    protection_status: str
    financial_rows: Tuple[Tuple[str, str], ...]
    document_analysis_lines: Tuple[str, ...]
    market_forecast_lines: Tuple[str, ...]
    stress_lines: Tuple[str, ...]
    priorities: Tuple[ConsultationPriorityContent, ...]
    preparation_documents: Tuple[str, ...]
    consultation_questions: Tuple[str, ...]
    missing_information: Tuple[str, ...]
    data_as_of: str
    exchange_rate_as_of: str
    official_source_as_of: str

    def all_text(self) -> str:
        values: List[str] = [
            PDF_TITLE,
            PDF_SUBTITLE,
            self.document_number,
            self.generated_at,
            self.trade_type,
            self.currency,
            self.settlement_date,
            self.consultation_purpose,
            self.counterparty_country,
            self.scheduled_amount,
            self.balance_amount,
            self.payment_method,
            self.protection_status,
            "이번 상담에서 먼저 확인할 내용",
            "거래 및 현금흐름 점검",
            "시장 전망 참고",
            "현금흐름 스트레스 점검",
            "준비할 자료",
            "은행 또는 기관에 물어볼 질문",
            "상담 후 결정할 사항",
            "전체 체크리스트",
            PDF_DISCLAIMER,
        ]
        for label, value in self.financial_rows:
            values.extend([label, value])
        values.extend(self.document_analysis_lines)
        values.extend(self.market_forecast_lines)
        values.extend(self.stress_lines)
        for priority in self.priorities:
            values.extend(
                [
                    priority.title,
                    priority.institution_or_area,
                    priority.reason,
                    priority.core_check,
                    priority.expected_decision,
                    priority.next_action,
                ]
            )
            values.extend(priority.missing_information)
            values.extend(priority.preparation_documents)
            values.extend(priority.bank_questions)
        values.extend(self.preparation_documents)
        values.extend(self.consultation_questions)
        values.extend(self.missing_information)
        return "\n".join(item for item in values if item)


COUNTRY_NAMES = {
    "BR": "브라질",
    "KR": "한국",
    "US": "미국",
    "JP": "일본",
    "CN": "중국",
    "DE": "독일",
    "GB": "영국",
    "CA": "캐나다",
}


def consultation_user_text(value: Optional[str]) -> str:
    if value is None or not str(value).strip():
        return "확인 필요"
    result = str(value).strip()
    literal_replacements = (
        ("Payment Terms:", "결제조건:"),
        ("payment terms", "결제조건"),
        ("payment/post-credit deficit", "대출한도 반영 후 부족액"),
        ("post-credit shortfall", "대출한도 반영 후 부족액"),
        ("post-credit 부족", "대출한도 반영 후 부족액"),
        ("지급/post-credit 부족", "대출한도 반영 후 부족액"),
        ("buffer shortfall", "최소 운영자금 대비 부족액"),
        ("목표 현금 버퍼 부족", "최소 운영자금 대비 부족액"),
        ("목표 buffer", "최소 유지 운영자금"),
        ("cash deficit", "실제 현금 적자"),
        ("ending cash", "예상 현금"),
        ("model horizon", "모델 전망기간"),
        ("finding과", "분석 신호와"),
        ("finding에 따라", "분석 신호에 따라"),
        ("finding의", "분석 신호의"),
        ("finding", "분석 신호"),
        ("spread", "은행 환율 적용 조건"),
        ("fee", "수수료"),
        ("UNKNOWN", "확인 필요"),
        ("NONE_CONFIRMED", "확인된 항목 없음"),
        ("NONE_IN_CALCULATION_INPUT", "계산 입력에서 확인되지 않음"),
        ("NOT_APPLICABLE", "해당 없음"),
        ("ELEVATED_REVIEW", "추가 검토 우선도"),
        ("HIGH_REVIEW", "높은 검토 우선도"),
        ("STANDARD_REVIEW", "정기 확인"),
        ("LOSS_LIMIT_EXCEEDED", "허용손실 초과 신호"),
        ("LIQUIDITY_BUFFER_RISK", "최소 운영자금 점검 신호"),
        ("PAYMENT_CAPACITY_RISK", "대출한도 반영 후 자금 점검 신호"),
    )
    for source, target in literal_replacements:
        result = re.sub(
            re.escape(source),
            target,
            result,
            flags=re.IGNORECASE,
        )
    token_replacements = (
        ("fallback", "대체 처리"),
        ("shortlist", "상담 후보"),
        ("profile", "확인한 거래조건"),
        ("overflow", "우선 상담 3개 밖의 추가 후보"),
        ("deferred", "추가 정보 확인 후 검토 가능"),
        ("auxiliary", "추가 확인 서비스"),
        ("stale", "현재 거래조건과 맞지 않는 이전 결과"),
        ("binding", "현재 거래정보와의 연결 확인"),
    )
    for source, target in token_replacements:
        result = re.sub(
            r"\b{}\b".format(re.escape(source)),
            target,
            result,
            flags=re.IGNORECASE,
        )
    result = re.sub(
        r"(?<!외상거래\()Open Account",
        "외상거래(Open Account)",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"(?<!전신송금\()T/T",
        "전신송금(T/T)",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"(?<!신용장\()L/C",
        "신용장(L/C)",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"(?<!지급인도조건\()D/P",
        "지급인도조건(D/P)",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"(?<!인수인도조건\()D/A",
        "인수인도조건(D/A)",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(r"\bDOWN_10\b", "환율 10% 하락 시", result)
    result = re.sub(r"\bUP_10\b", "환율 10% 상승 시", result)
    result = re.sub(r"\bDOWN_5\b", "환율 5% 하락 시", result)
    result = re.sub(r"\bUP_5\b", "환율 5% 상승 시", result)
    result = re.sub(r"\bBASE\b", "현재 기준", result)
    result = re.sub(
        r"\bStage\s*1\b|\bSTAGE1\b",
        "환율 전망",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"\bStage\s*2\b|\bSTAGE2\b",
        "현금흐름 분석",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"\bStage\s*3\b|\bSTAGE3\b",
        "환율 대응안",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(r"\bfingerprint\b", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\bhash\b", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\bcritic\b", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\bexposure\b", "예정 외화 노출", result, flags=re.IGNORECASE)
    result = re.sub(r"\s{2,}", " ", result)
    return result.strip(" ·") or "확인 필요"


def consultation_preparation_pdf_filename(generated_at: datetime) -> str:
    return "KB_환담_상담준비서_{}.pdf".format(
        generated_at.astimezone(KOREA_TIMEZONE).strftime("%Y%m%d")
    )


def _decimal(value: str, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ConsultationPreparationBindingError(
            "{} 값을 확인할 수 없습니다.".format(field)
        ) from exc
    if not parsed.is_finite():
        raise ConsultationPreparationBindingError(
            "{} 값이 유효하지 않습니다.".format(field)
        )
    return parsed


def _format_number(value: str, decimal_places: int = 0) -> str:
    parsed = _decimal(value, "표시 금액")
    return format(parsed, ",.{}f".format(decimal_places))


def _format_krw(value: str) -> str:
    return "{}원".format(_format_number(value))


def _format_fx(value: str, currency: str) -> str:
    parsed = _decimal(value, "외화 금액")
    places = 0 if parsed == parsed.to_integral_value() else 2
    return "{} {}".format(currency, format(parsed, ",.{}f".format(places)))


def _dedupe(values: Iterable[str]) -> Tuple[str, ...]:
    rows: List[str] = []
    seen = set()
    for value in values:
        visible = consultation_user_text(value)
        if visible and visible not in seen:
            seen.add(visible)
            rows.append(visible)
    return tuple(rows)


def _scenario_label(value: str) -> str:
    visible = consultation_user_text(value)
    if visible == value and value.startswith("MODEL_"):
        return "시장 전망 중심 시나리오"
    return visible


def _evidence_value(
    packet: ConsultationPacket,
    labels: Sequence[str],
) -> Optional[Tuple[str, Optional[str]]]:
    for review_area in packet.consultation_review_areas:
        for item in review_area.evidence_items:
            if item.label in labels:
                return item.value, item.currency
    for priority in packet.consultation_priorities:
        for item in priority.numeric_rationale:
            if item.label in labels:
                return item.value, item.currency
    return None


def _protection_status(packet: ConsultationPacket) -> str:
    statuses = (
        packet.protection_summary.documentary_credit,
        packet.protection_summary.credit_insurance,
        packet.protection_summary.independent_payment_guarantee,
    )
    if any("PROTECTION_PRESENT" in item for item in statuses):
        return "보호수단 존재 · 유형과 적용범위 상담 확인"
    if any("PRESENT_DETAILS_NOT_ASSESSED" in item for item in statuses):
        return "보호수단 세부조건 확인 필요"
    if all(item == "NONE_CONFIRMED" for item in statuses):
        return "확인된 보험·보증·신용장 없음"
    return "보호수단 확인 필요"


def _candidate_connection(
    packet: ConsultationPacket,
    review_area: ConsultationReviewAreaView,
) -> str:
    shortlist = packet.official_candidate_shortlist
    if shortlist is not None:
        categories = set(review_area.source_priority_categories)
        for candidate in shortlist.candidates:
            if (
                review_area.review_area_id in candidate.matched_review_areas
                or categories.intersection(
                    candidate.matched_consultation_categories
                )
            ):
                return "{} · {}".format(
                    consultation_user_text(candidate.institution),
                    consultation_user_text(
                        candidate.display_name or candidate.name
                    ),
                )
    return "{} 상담 분야".format(review_area.display_name)


def _official_source_as_of(packet: ConsultationPacket) -> str:
    shortlist = packet.official_candidate_shortlist
    if shortlist is None or not shortlist.candidates:
        return "자료 미확인"
    dates = sorted(
        {
            candidate.source.verified_at
            for candidate in shortlist.candidates
            if candidate.source.verified_at
        }
    )
    return dates[-1] if dates else "자료 미확인"


def _validate_binding(
    *,
    packet: ConsultationPacket,
    transaction: ConfirmedTransactionSnapshot,
    stage2_result: Stage2Result,
) -> ScenarioResult:
    if (
        packet.confirmed_transaction_fingerprint
        != transaction.input_fingerprint
    ):
        raise ConsultationPreparationBindingError(
            "상담 준비자료가 현재 거래정보와 일치하지 않습니다. "
            "최신 분석을 다시 실행해 주세요."
        )
    if (
        stage2_result.confirmed_trade_sha256
        != transaction.trade_binding.trade_sha256
    ):
        raise ConsultationPreparationBindingError(
            "현금흐름 결과가 현재 거래정보와 일치하지 않습니다. "
            "최신 분석을 다시 실행해 주세요."
        )
    company = packet.company_summary
    if (
        company.trade_type != transaction.trade_type
        or company.currency != transaction.currency
        or company.settlement_date != transaction.due_date
        or _decimal(company.trade_amount_fx, "상담 준비 거래금액")
        != _decimal(transaction.amount_due, "확정 거래금액")
    ):
        raise ConsultationPreparationBindingError(
            "상담 준비자료의 거래조건이 현재 확정 거래와 다릅니다."
        )
    if (
        stage2_result.trade_type != transaction.trade_type
        or stage2_result.currency != transaction.currency
        or _decimal(stage2_result.open_exposure, "현금흐름 예정 외화 노출")
        != _decimal(
            packet.exposure_summary.open_exposure_fx,
            "상담 준비 예정 외화 노출",
        )
    ):
        raise ConsultationPreparationBindingError(
            "상담 준비자료의 예정 외화 노출이 현재 현금흐름 결과와 다릅니다."
        )
    scenario = next(
        (
            item
            for item in stage2_result.scenario_results
            if item.scenario_name == packet.risk_summary.worst_scenario_id
        ),
        None,
    )
    if scenario is None:
        raise ConsultationPreparationBindingError(
            "상담 준비자료의 스트레스 시나리오를 현재 분석에서 찾을 수 없습니다."
        )
    comparisons = (
        (scenario.loss_vs_base, packet.risk_summary.additional_cost_or_receipt_loss_krw),
        (scenario.ending_cash, packet.risk_summary.cash_after_settlement_krw),
        (scenario.maximum_buffer_shortfall, packet.risk_summary.buffer_shortfall_krw),
        (scenario.cash_deficit, packet.risk_summary.cash_deficit_krw),
        (scenario.post_credit_shortfall, packet.risk_summary.payment_gap_krw),
    )
    if any(
        _decimal(left, "현금흐름 결과")
        != _decimal(right, "상담 준비 위험요약")
        for left, right in comparisons
    ):
        raise ConsultationPreparationBindingError(
            "상담 준비자료의 자금 영향이 현재 현금흐름 결과와 다릅니다."
        )
    if not packet.consultation_review_areas:
        raise ConsultationPreparationBindingError(
            "최신 상담 우선순위를 먼저 준비해 주세요."
        )
    return scenario


def build_consultation_preparation_content(
    *,
    packet: ConsultationPacket,
    transaction: ConfirmedTransactionSnapshot,
    stage2_result: Stage2Result,
    generated_at: datetime,
    forecast_summary: Optional[Dict[str, str]] = None,
) -> ConsultationPreparationContent:
    if generated_at.tzinfo is None:
        raise ConsultationPreparationPdfError(
            "상담 준비서 생성시각에는 timezone offset이 필요합니다."
        )
    adverse = _validate_binding(
        packet=packet,
        transaction=transaction,
        stage2_result=stage2_result,
    )
    trade_label = "수출" if transaction.trade_type == "EXPORT" else "수입"
    flow_label = "수취" if transaction.trade_type == "EXPORT" else "지급"
    impact_label = "감소" if transaction.trade_type == "EXPORT" else "증가"
    balance_evidence = _evidence_value(packet, ("잔금 예정", "잔금"))
    balance_amount = (
        _format_fx(balance_evidence[0], balance_evidence[1] or transaction.currency)
        if balance_evidence is not None
        else "확인 필요"
    )
    payment_evidence = _evidence_value(packet, ("결제방식",))
    payment_method = consultation_user_text(
        payment_evidence[0]
        if payment_evidence is not None
        else transaction.payment_terms
    )
    minimum_buffer = _evidence_value(
        packet,
        ("목표 buffer", "목표 현금 버퍼", "최소 유지 운영자금"),
    )
    minimum_buffer_value = (
        _format_krw(minimum_buffer[0])
        if minimum_buffer is not None
        else "확인 필요"
    )
    financial_rows = (
        (
            "예정 외화 노출",
            _format_fx(
                packet.exposure_summary.open_exposure_fx,
                transaction.currency,
            ),
        ),
        (
            "기준 원화 {}액".format(flow_label),
            _format_krw(stage2_result.base_required_or_proceeds_krw),
        ),
        (
            "대표 불리 시나리오",
            _scenario_label(adverse.scenario_name),
        ),
        (
            "기준 대비 {}액 {}".format(flow_label, impact_label),
            _format_krw(adverse.loss_vs_base),
        ),
        ("스트레스 후 예상 현금", _format_krw(adverse.ending_cash)),
        ("최소 유지 운영자금", minimum_buffer_value),
        (
            "최소 운영자금 대비 부족액",
            _format_krw(adverse.maximum_buffer_shortfall),
        ),
        ("실제 현금 적자", _format_krw(adverse.cash_deficit)),
        (
            "대출한도 반영 후 부족액",
            _format_krw(adverse.post_credit_shortfall),
        ),
    )
    forecast = forecast_summary or {}
    provenance = packet.document_analysis
    if provenance is None:
        document_analysis_lines: Tuple[str, ...] = ()
    else:
        document_label = (
            "Golden 수출 샘플"
            if provenance.document_source == "golden_sample"
            else "내 문서 업로드"
        )
        analysis_label = (
            "AI 실시간 분석"
            if provenance.analysis_source == "openai"
            else "검증된 데모 결과"
        )
        lines = [
            "문서 분석: {}".format(analysis_label),
            "입력 문서: {}".format(document_label),
            "source: {} · 사용 모델: {}".format(
                provenance.analysis_source,
                provenance.model,
            ),
        ]
        if provenance.fallback_used:
            lines.extend(
                [
                    (
                        "경고: 실시간 문서 분석 연결이 원활하지 않아 사전 "
                        "검증된 동일 샘플 결과를 사용했습니다."
                    ),
                    "warning code: {}".format(
                        ", ".join(provenance.warnings)
                    ),
                ]
            )
        document_analysis_lines = tuple(lines)
    market_lines = (
        consultation_user_text(
            forecast.get("headline")
            or "시장 전망 자료는 환율 전망 화면에서 확인이 필요합니다."
        ),
        consultation_user_text(
            forecast.get("range")
            or "모델 전망 범위는 확정 결제환율이나 발생확률이 아닙니다."
        ),
    )
    stress_lines = (
        "{} 기준 대비 영향 {}".format(
            _scenario_label(adverse.scenario_name),
            _format_krw(adverse.loss_vs_base),
        ),
        (
            "시장 전망은 방향과 변동 범위를 이해하기 위한 참고자료이며, "
            "현금흐름 금액은 검증된 스트레스 시나리오를 기준으로 계산했습니다."
        ),
    )
    priorities: List[ConsultationPriorityContent] = []
    for review_area in packet.consultation_review_areas:
        missing = _dedupe(review_area.missing_information)
        documents = _dedupe(review_area.preparation_documents)
        questions = _dedupe(review_area.bank_questions)
        priorities.append(
            ConsultationPriorityContent(
                rank=review_area.rank,
                title=consultation_user_text(review_area.display_name),
                institution_or_area=_candidate_connection(packet, review_area),
                reason=consultation_user_text(review_area.summary),
                core_check=(
                    missing[0]
                    if missing
                    else consultation_user_text(review_area.expected_decision)
                ),
                missing_information=missing[:5],
                preparation_documents=documents[:6],
                bank_questions=questions[:5],
                expected_decision=consultation_user_text(
                    review_area.expected_decision
                ),
                next_action=consultation_user_text(review_area.next_action),
            )
        )
    all_documents = _dedupe(
        item
        for priority in priorities
        for item in priority.preparation_documents
    )
    all_questions = _dedupe(
        item
        for priority in priorities
        for item in priority.bank_questions
    )
    all_missing = _dedupe(
        item
        for priority in priorities
        for item in priority.missing_information
    )
    generated_local = generated_at.astimezone(KOREA_TIMEZONE)
    counterparty = packet.company_summary.counterparty_country
    data_as_of = consultation_user_text(
        forecast.get("data_as_of") or packet.generated_at[:10]
    )
    return ConsultationPreparationContent(
        document_number="상담준비서-{}".format(
            generated_local.strftime("%Y%m%d-%H%M")
        ),
        generated_at=generated_local.strftime("%Y-%m-%d %H:%M %Z"),
        trade_type="{} 거래".format(trade_label),
        currency=transaction.currency,
        settlement_date=transaction.due_date,
        consultation_purpose=(
            "{}대금의 안전한 {}와 환율·운영자금 조건을 상담에서 확인"
        ).format(trade_label, flow_label),
        counterparty_country=(
            "{} ({})".format(
                COUNTRY_NAMES.get(counterparty, counterparty),
                counterparty,
            )
            if counterparty
            else "확인 필요"
        ),
        scheduled_amount=_format_fx(
            transaction.amount_due,
            transaction.currency,
        ),
        balance_amount=balance_amount,
        payment_method=payment_method,
        protection_status=_protection_status(packet),
        financial_rows=financial_rows,
        document_analysis_lines=document_analysis_lines,
        market_forecast_lines=market_lines,
        stress_lines=stress_lines,
        priorities=tuple(priorities),
        preparation_documents=all_documents,
        consultation_questions=all_questions,
        missing_information=all_missing,
        data_as_of=data_as_of,
        exchange_rate_as_of=packet.exchange_rate_as_of,
        official_source_as_of=_official_source_as_of(packet),
    )


def _font_candidates() -> List[Path]:
    configured = os.environ.get("KBAI_CONSULTATION_PDF_FONT", "").strip()
    candidates = [
        Path(configured) if configured else None,
        Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
        Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/gulim.ttc"),
    ]
    discovered: List[Path] = []
    for root in (
        Path("/usr/share/fonts/opentype"),
        Path("/usr/share/fonts/truetype"),
        Path("/Library/Fonts"),
    ):
        if root.exists():
            for pattern in (
                "**/NotoSansCJK*.ttc",
                "**/NanumGothic*.ttf",
                "**/NotoSansKR*.otf",
            ):
                discovered.extend(sorted(root.glob(pattern)))
    rows: List[Path] = []
    seen = set()
    for candidate in candidates + discovered:
        if candidate is None:
            continue
        text = str(candidate)
        if text not in seen:
            seen.add(text)
            rows.append(candidate)
    return rows


def _supports_korean(path: Path) -> bool:
    try:
        font = ImageFont.truetype(str(path), size=32)
        masks = [bytes(font.getmask(char)) for char in "한글상담"]
    except (OSError, ValueError):
        return False
    return all(masks) and len(set(masks)) >= 4


def find_korean_pdf_font() -> str:
    for candidate in _font_candidates():
        if candidate.is_file() and _supports_korean(candidate):
            return str(candidate)
    raise ConsultationPreparationFontError(
        "한글 Unicode 글리프를 지원하는 PDF 폰트를 찾지 못했습니다. "
        "Noto Sans CJK·나눔고딕·맑은 고딕 중 하나를 설치하거나 "
        "KBAI_CONSULTATION_PDF_FONT에 사용 가능한 폰트 경로를 설정해 주세요."
    )


class _Fonts:
    def __init__(self, path: str) -> None:
        self.title = ImageFont.truetype(path, 42)
        self.subtitle = ImageFont.truetype(path, 23)
        self.h1 = ImageFont.truetype(path, 31)
        self.h2 = ImageFont.truetype(path, 24)
        self.h3 = ImageFont.truetype(path, 20)
        self.body = ImageFont.truetype(path, 19)
        self.small = ImageFont.truetype(path, 15)
        self.metric = ImageFont.truetype(path, 25)


def _split_long_token(
    draw: ImageDraw.ImageDraw,
    token: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> List[str]:
    rows: List[str] = []
    current = ""
    for char in token:
        candidate = current + char
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if current and width > max_width:
            rows.append(current)
            current = char
        else:
            current = candidate
    if current:
        rows.append(current)
    return rows


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> List[str]:
    words = str(text).replace("\n", " \n ").split()
    lines: List[str] = []
    current = ""
    for word in words:
        if word == "\n":
            if current:
                lines.append(current)
                current = ""
            continue
        pieces = (
            _split_long_token(draw, word, font, max_width)
            if draw.textbbox((0, 0), word, font=font)[2] > max_width
            else [word]
        )
        for piece in pieces:
            candidate = "{} {}".format(current, piece).strip()
            width = draw.textbbox((0, 0), candidate, font=font)[2]
            if current and width > max_width:
                lines.append(current)
                current = piece
            else:
                current = candidate
    if current:
        lines.append(current)
    return lines or [""]


class _PdfRenderer:
    def __init__(
        self,
        content: ConsultationPreparationContent,
        font_path: str,
    ) -> None:
        self.content = content
        self.fonts = _Fonts(font_path)
        self.pages: List[Image.Image] = []
        self.image: Optional[Image.Image] = None
        self.draw: Optional[ImageDraw.ImageDraw] = None
        self.y = HEADER_HEIGHT + 45
        self.content_bottom = A4_HEIGHT - FOOTER_HEIGHT

    def new_page(self, title: str, subtitle: str = "") -> None:
        image = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), WHITE)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, A4_WIDTH, HEADER_HEIGHT), fill=NAVY)
        draw.rectangle(
            (0, HEADER_HEIGHT - 9, A4_WIDTH, HEADER_HEIGHT),
            fill=YELLOW,
        )
        draw.text(
            (MARGIN, 27),
            title,
            font=self.fonts.h1,
            fill=WHITE,
            stroke_width=1,
        )
        if subtitle:
            draw.text(
                (MARGIN, 75),
                subtitle,
                font=self.fonts.small,
                fill="#DCE7F3",
            )
        self.pages.append(image)
        self.image = image
        self.draw = draw
        self.y = HEADER_HEIGHT + 45

    def _require_draw(self) -> ImageDraw.ImageDraw:
        if self.draw is None:
            raise ConsultationPreparationPdfError("PDF 페이지가 준비되지 않았습니다.")
        return self.draw

    def _ensure(self, height: int, continuation_title: str) -> None:
        if self.y + height <= self.content_bottom:
            return
        self.new_page(continuation_title, "상담 준비 내용 계속")

    def heading(self, text: str, level: int = 2) -> None:
        draw = self._require_draw()
        font = self.fonts.h2 if level == 2 else self.fonts.h3
        height = 48 if level == 2 else 38
        self._ensure(height, text)
        draw = self._require_draw()
        draw.text(
            (MARGIN, self.y),
            text,
            font=font,
            fill=DEEP_NAVY,
            stroke_width=1 if level == 2 else 0,
        )
        if level == 2:
            draw.rectangle(
                (MARGIN, self.y + 37, MARGIN + 52, self.y + 42),
                fill=YELLOW,
            )
        self.y += height

    def paragraph(
        self,
        text: str,
        *,
        color: str = INK,
        font: Optional[ImageFont.FreeTypeFont] = None,
        max_width: Optional[int] = None,
        gap: int = 13,
    ) -> None:
        draw = self._require_draw()
        selected = font or self.fonts.body
        width = max_width or A4_WIDTH - MARGIN * 2
        lines = _wrap_text(draw, text, selected, width)
        line_height = selected.size + 10
        self._ensure(len(lines) * line_height + gap, "상담 준비 내용")
        draw = self._require_draw()
        for line in lines:
            draw.text((MARGIN, self.y), line, font=selected, fill=color)
            self.y += line_height
        self.y += gap

    def info_grid(self, rows: Sequence[Tuple[str, str]]) -> None:
        draw = self._require_draw()
        columns = 2
        gap = 14
        cell_width = (A4_WIDTH - MARGIN * 2 - gap) // columns
        cell_height = 94
        total_rows = (len(rows) + columns - 1) // columns
        self._ensure(total_rows * (cell_height + gap), "상담 요약")
        draw = self._require_draw()
        start_y = self.y
        for index, (label, value) in enumerate(rows):
            column = index % columns
            row = index // columns
            x = MARGIN + column * (cell_width + gap)
            y = start_y + row * (cell_height + gap)
            draw.rounded_rectangle(
                (x, y, x + cell_width, y + cell_height),
                radius=10,
                fill=PALE_BLUE,
                outline=LINE,
                width=1,
            )
            draw.text(
                (x + 18, y + 13),
                label,
                font=self.fonts.small,
                fill=MUTED,
            )
            lines = _wrap_text(
                draw,
                value,
                self.fonts.body,
                cell_width - 36,
            )[:2]
            for line_index, line in enumerate(lines):
                draw.text(
                    (x + 18, y + 42 + line_index * 25),
                    line,
                    font=self.fonts.body,
                    fill=INK,
                )
        self.y += total_rows * (cell_height + gap) + 10

    def priority_summary_card(
        self,
        priority: ConsultationPriorityContent,
    ) -> None:
        draw = self._require_draw()
        width = A4_WIDTH - MARGIN * 2
        reason_lines = _wrap_text(
            draw,
            priority.reason,
            self.fonts.small,
            width - 155,
        )[:2]
        check_lines = _wrap_text(
            draw,
            priority.core_check,
            self.fonts.small,
            width - 155,
        )[:2]
        height = 128 + (len(reason_lines) + len(check_lines)) * 20
        self._ensure(height + 14, "상담 요약")
        draw = self._require_draw()
        top = self.y
        draw.rounded_rectangle(
            (MARGIN, top, A4_WIDTH - MARGIN, top + height),
            radius=12,
            fill=WHITE,
            outline=LINE,
            width=2,
        )
        draw.ellipse(
            (MARGIN + 18, top + 18, MARGIN + 68, top + 68),
            fill=YELLOW,
        )
        draw.text(
            (MARGIN + 37, top + 29),
            str(priority.rank),
            font=self.fonts.h3,
            fill=DEEP_NAVY,
            anchor="mm",
        )
        draw.text(
            (MARGIN + 88, top + 15),
            priority.title,
            font=self.fonts.h3,
            fill=DEEP_NAVY,
            stroke_width=1,
        )
        draw.text(
            (MARGIN + 88, top + 48),
            priority.institution_or_area,
            font=self.fonts.small,
            fill=MUTED,
        )
        y = top + 78
        draw.text(
            (MARGIN + 88, y),
            "왜 먼저 확인하나요?",
            font=self.fonts.small,
            fill=NAVY,
        )
        for line in reason_lines:
            y += 21
            draw.text(
                (MARGIN + 220, y - 21),
                line,
                font=self.fonts.small,
                fill=INK,
            )
        y += 8
        draw.text(
            (MARGIN + 88, y),
            "현재 확인할 핵심",
            font=self.fonts.small,
            fill=NAVY,
        )
        for line in check_lines:
            y += 21
            draw.text(
                (MARGIN + 220, y - 21),
                line,
                font=self.fonts.small,
                fill=INK,
            )
        self.y += height + 14

    def metric_grid(self, rows: Sequence[Tuple[str, str]]) -> None:
        draw = self._require_draw()
        columns = 3
        gap = 12
        cell_width = (A4_WIDTH - MARGIN * 2 - gap * 2) // columns
        cell_height = 112
        total_rows = (len(rows) + columns - 1) // columns
        self._ensure(total_rows * (cell_height + gap), "현금흐름 점검")
        draw = self._require_draw()
        start_y = self.y
        for index, (label, value) in enumerate(rows):
            column = index % columns
            row = index // columns
            x = MARGIN + column * (cell_width + gap)
            y = start_y + row * (cell_height + gap)
            draw.rounded_rectangle(
                (x, y, x + cell_width, y + cell_height),
                radius=9,
                fill=PALE_BLUE,
                outline=LINE,
            )
            label_lines = _wrap_text(
                draw,
                label,
                self.fonts.small,
                cell_width - 28,
            )[:2]
            for line_index, line in enumerate(label_lines):
                draw.text(
                    (x + 14, y + 13 + line_index * 19),
                    line,
                    font=self.fonts.small,
                    fill=MUTED,
                )
            value_lines = _wrap_text(
                draw,
                value,
                self.fonts.h3,
                cell_width - 28,
            )[:2]
            for line_index, line in enumerate(value_lines):
                draw.text(
                    (x + 14, y + 59 + line_index * 25),
                    line,
                    font=self.fonts.h3,
                    fill=INK,
                    stroke_width=1,
                )
        self.y += total_rows * (cell_height + gap) + 12

    def notice_box(
        self,
        title: str,
        lines: Sequence[str],
        fill: str,
    ) -> None:
        draw = self._require_draw()
        width = A4_WIDTH - MARGIN * 2
        wrapped: List[str] = []
        for value in lines:
            wrapped.extend(
                _wrap_text(draw, value, self.fonts.body, width - 40)
            )
        height = 62 + len(wrapped) * 28
        self._ensure(height + 14, "거래 및 현금흐름 점검")
        draw = self._require_draw()
        top = self.y
        draw.rounded_rectangle(
            (MARGIN, top, A4_WIDTH - MARGIN, top + height),
            radius=10,
            fill=fill,
            outline=LINE,
        )
        draw.text(
            (MARGIN + 20, top + 16),
            title,
            font=self.fonts.h3,
            fill=DEEP_NAVY,
            stroke_width=1,
        )
        y = top + 54
        for line in wrapped:
            draw.text(
                (MARGIN + 20, y),
                line,
                font=self.fonts.body,
                fill=INK,
            )
            y += 28
        self.y += height + 14

    def _list_height(
        self,
        values: Sequence[str],
        width: int,
    ) -> int:
        draw = self._require_draw()
        total = 0
        for value in values:
            lines = _wrap_text(draw, value, self.fonts.small, width - 30)
            total += max(30, len(lines) * 21 + 7)
        return total

    def _checkbox_list(
        self,
        x: int,
        y: int,
        width: int,
        values: Sequence[str],
        empty_copy: str,
    ) -> int:
        draw = self._require_draw()
        rows = list(values) or [empty_copy]
        current = y
        for value in rows:
            lines = _wrap_text(draw, value, self.fonts.small, width - 30)
            draw.rectangle(
                (x, current + 4, x + 14, current + 18),
                outline=NAVY,
                width=1,
            )
            for line_index, line in enumerate(lines):
                draw.text(
                    (x + 24, current + line_index * 21),
                    line,
                    font=self.fonts.small,
                    fill=INK,
                )
            current += max(30, len(lines) * 21 + 7)
        return current

    def priority_detail(
        self,
        priority: ConsultationPriorityContent,
    ) -> None:
        draw = self._require_draw()
        card_width = A4_WIDTH - MARGIN * 2
        gap = 28
        column_width = (card_width - 48 - gap) // 2
        reason_lines = _wrap_text(
            draw,
            priority.reason,
            self.fonts.small,
            card_width - 48,
        )
        left_height = (
            34
            + self._list_height(
                priority.missing_information,
                column_width,
            )
            + 38
            + self._list_height(
                priority.preparation_documents,
                column_width,
            )
        )
        right_height = 34 + self._list_height(
            priority.bank_questions,
            column_width,
        )
        decision_lines = _wrap_text(
            draw,
            priority.expected_decision,
            self.fonts.small,
            card_width - 48,
        )
        action_lines = _wrap_text(
            draw,
            priority.next_action,
            self.fonts.small,
            card_width - 48,
        )
        height = (
            82
            + len(reason_lines) * 21
            + max(left_height, right_height)
            + 50
            + len(decision_lines) * 21
            + 45
            + len(action_lines) * 21
            + 28
        )
        self._ensure(
            height + 16,
            "상담 우선순위별 준비",
        )
        draw = self._require_draw()
        top = self.y
        draw.rounded_rectangle(
            (MARGIN, top, A4_WIDTH - MARGIN, top + height),
            radius=12,
            fill=WHITE,
            outline=LINE,
            width=2,
        )
        draw.text(
            (MARGIN + 22, top + 18),
            "{}순위 - {}".format(priority.rank, priority.title),
            font=self.fonts.h2,
            fill=DEEP_NAVY,
            stroke_width=1,
        )
        draw.text(
            (A4_WIDTH - MARGIN - 22, top + 22),
            priority.institution_or_area,
            font=self.fonts.small,
            fill=MUTED,
            anchor="ra",
        )
        current = top + 62
        draw.text(
            (MARGIN + 22, current),
            "1. 왜 먼저 상담하나요?",
            font=self.fonts.h3,
            fill=NAVY,
        )
        current += 31
        for line in reason_lines:
            draw.text(
                (MARGIN + 22, current),
                line,
                font=self.fonts.small,
                fill=INK,
            )
            current += 21
        current += 14
        left_x = MARGIN + 22
        right_x = left_x + column_width + gap
        columns_top = current
        draw.text(
            (left_x, current),
            "2. 상담 전에 확인할 내용",
            font=self.fonts.h3,
            fill=NAVY,
        )
        left_y = self._checkbox_list(
            left_x,
            current + 32,
            column_width,
            priority.missing_information,
            "현재 별도로 등록된 미확인 항목 없음",
        )
        draw.text(
            (left_x, left_y + 6),
            "3. 준비할 자료",
            font=self.fonts.h3,
            fill=NAVY,
        )
        left_y = self._checkbox_list(
            left_x,
            left_y + 38,
            column_width,
            priority.preparation_documents,
            "추가 준비자료 확인 필요",
        )
        draw.text(
            (right_x, current),
            "4. 은행 또는 기관에 물어볼 질문",
            font=self.fonts.h3,
            fill=NAVY,
        )
        right_y = self._checkbox_list(
            right_x,
            current + 32,
            column_width,
            priority.bank_questions,
            "상담 질문 확인 필요",
        )
        current = max(left_y, right_y, columns_top + max(left_height, right_height))
        current += 10
        draw.line(
            (MARGIN + 22, current, A4_WIDTH - MARGIN - 22, current),
            fill=LINE,
            width=1,
        )
        current += 14
        draw.text(
            (MARGIN + 22, current),
            "5. 상담 후 결정할 사항",
            font=self.fonts.h3,
            fill=NAVY,
        )
        current += 30
        for line in decision_lines:
            draw.text(
                (MARGIN + 22, current),
                line,
                font=self.fonts.small,
                fill=INK,
            )
            current += 21
        current += 10
        draw.text(
            (MARGIN + 22, current),
            "6. 다음 행동",
            font=self.fonts.h3,
            fill=NAVY,
        )
        current += 30
        for line in action_lines:
            draw.text(
                (MARGIN + 22, current),
                line,
                font=self.fonts.small,
                fill=INK,
            )
            current += 21
        self.y += height + 16

    def checklist_page(self) -> None:
        self.new_page("전체 체크리스트", "상담 전·상담 중·상담 후 확인")
        draw = self._require_draw()
        gap = 32
        width = (A4_WIDTH - MARGIN * 2 - gap) // 2
        left = MARGIN
        right = MARGIN + width + gap
        top = self.y
        draw.text(
            (left, top),
            "상담 전 준비자료",
            font=self.fonts.h2,
            fill=DEEP_NAVY,
            stroke_width=1,
        )
        left_y = self._checkbox_list(
            left,
            top + 42,
            width,
            self.content.preparation_documents,
            "준비자료 확인 필요",
        )
        draw.text(
            (left, left_y + 18),
            "아직 확인되지 않은 조건",
            font=self.fonts.h2,
            fill=DEEP_NAVY,
            stroke_width=1,
        )
        self._checkbox_list(
            left,
            left_y + 62,
            width,
            self.content.missing_information,
            "현재 별도로 등록된 미확인 항목 없음",
        )
        draw.text(
            (right, top),
            "상담 시 질문",
            font=self.fonts.h2,
            fill=DEEP_NAVY,
            stroke_width=1,
        )
        right_y = self._checkbox_list(
            right,
            top + 42,
            width,
            self.content.consultation_questions,
            "상담 질문 확인 필요",
        )
        record_y = min(max(right_y + 18, top + 430), self.content_bottom - 330)
        draw.text(
            (right, record_y),
            "상담 후 기록할 항목",
            font=self.fonts.h2,
            fill=DEEP_NAVY,
            stroke_width=1,
        )
        record_y += 49
        for label in (
            "상담 기관",
            "상담 일시",
            "담당자",
            "안내받은 상품",
            "추가 제출자료",
            "다음 연락일",
        ):
            draw.text(
                (right, record_y),
                label,
                font=self.fonts.small,
                fill=MUTED,
            )
            draw.line(
                (right + 120, record_y + 18, right + width, record_y + 18),
                fill=LINE,
                width=2,
            )
            record_y += 46

    def _footer(self, page_number: int, page_count: int) -> None:
        image = self.pages[page_number - 1]
        draw = ImageDraw.Draw(image)
        top = A4_HEIGHT - FOOTER_HEIGHT + 20
        draw.line((MARGIN, top, A4_WIDTH - MARGIN, top), fill=LINE, width=1)
        draw.text(
            (MARGIN, top + 12),
            "데이터 기준일 {} · 환율 기준일 {} · 공식 자료 확인일 {}".format(
                self.content.data_as_of,
                self.content.exchange_rate_as_of,
                self.content.official_source_as_of,
            ),
            font=self.fonts.small,
            fill=MUTED,
        )
        disclaimer_lines = _wrap_text(
            draw,
            PDF_DISCLAIMER,
            self.fonts.small,
            A4_WIDTH - MARGIN * 2 - 75,
        )[:4]
        y = top + 40
        for line in disclaimer_lines:
            draw.text(
                (MARGIN, y),
                line,
                font=self.fonts.small,
                fill=MUTED,
            )
            y += 20
        draw.text(
            (A4_WIDTH - MARGIN, top + 44),
            "{} / {}".format(page_number, page_count),
            font=self.fonts.small,
            fill=NAVY,
            anchor="ra",
        )

    def render(self, generated_at: datetime) -> bytes:
        self.new_page(PDF_TITLE, PDF_SUBTITLE)
        draw = self._require_draw()
        draw.text(
            (MARGIN, self.y),
            "이번 상담에서 먼저 확인할 내용",
            font=self.fonts.title,
            fill=DEEP_NAVY,
            stroke_width=1,
        )
        self.y += 58
        self.paragraph(self.content.consultation_purpose, color=MUTED)
        self.info_grid(
            (
                ("생성일시", self.content.generated_at),
                ("문서번호", self.content.document_number),
                ("거래 유형", self.content.trade_type),
                ("거래 상대국", self.content.counterparty_country),
                ("거래 통화", self.content.currency),
                ("예정 수취·지급 금액", self.content.scheduled_amount),
                ("잔금", self.content.balance_amount),
                ("결제예정일", self.content.settlement_date),
                ("결제방식", self.content.payment_method),
                ("보호수단", self.content.protection_status),
            )
        )
        self.heading("상담 우선순위 Top 3")
        for priority in self.content.priorities:
            self.priority_summary_card(priority)

        self.new_page(
            "거래 및 현금흐름 점검",
            "검증된 거래정보와 현금흐름 분석 결과",
        )
        self.metric_grid(self.content.financial_rows)
        if self.content.document_analysis_lines:
            self.notice_box(
                "문서 분석 출처",
                self.content.document_analysis_lines,
                (
                    PALE_YELLOW
                    if any(
                        "FALLBACK_USED" in line
                        for line in self.content.document_analysis_lines
                    )
                    else PALE_BLUE
                ),
            )
        self.notice_box(
            "시장 전망 참고",
            self.content.market_forecast_lines,
            PALE_BLUE,
        )
        self.notice_box(
            "현금흐름 스트레스 점검",
            self.content.stress_lines,
            PALE_YELLOW,
        )
        self.paragraph(
            "최소 운영자금 대비 부족액은 지급불능이나 필요 대출액을 뜻하지 "
            "않습니다. 실제 현금 적자와 대출한도 반영 후 부족액을 각각 "
            "구분해 확인하세요.",
            color=MUTED,
            font=self.fonts.small,
        )

        self.new_page(
            "상담 우선순위별 준비",
            "실제 상담에서 바로 확인할 질문과 준비자료",
        )
        for priority in self.content.priorities:
            self.priority_detail(priority)

        self.checklist_page()
        page_count = len(self.pages)
        if page_count < 3 or page_count > 5:
            raise ConsultationPreparationPdfError(
                "상담 준비서 페이지 수가 비정상입니다: {}페이지".format(
                    page_count
                )
            )
        for number in range(1, page_count + 1):
            self._footer(number, page_count)
        output = io.BytesIO()
        generated_utc = generated_at.astimezone(timezone.utc).timetuple()
        self.pages[0].save(
            output,
            format="PDF",
            save_all=True,
            append_images=self.pages[1:],
            resolution=float(PDF_DPI),
            title=PDF_TITLE,
            author="KB 환담",
            subject=PDF_SUBTITLE,
            keywords=(
                "상담 준비, 수출대금 회수 보호, 환율 관리, 준비할 자료, "
                "은행 또는 기관에 물어볼 질문, 상담 후 결정할 사항"
            ),
            creator="KB 환담 deterministic consultation preparation renderer",
            producer="Pillow PDF",
            creationDate=generated_utc,
            modDate=generated_utc,
        )
        return output.getvalue()


def build_consultation_preparation_pdf(
    *,
    packet: ConsultationPacket,
    transaction: ConfirmedTransactionSnapshot,
    stage2_result: Stage2Result,
    generated_at: datetime,
    forecast_summary: Optional[Dict[str, str]] = None,
    font_path: Optional[str] = None,
) -> bytes:
    content = build_consultation_preparation_content(
        packet=packet,
        transaction=transaction,
        stage2_result=stage2_result,
        generated_at=generated_at,
        forecast_summary=forecast_summary,
    )
    selected_font = font_path or find_korean_pdf_font()
    if not _supports_korean(Path(selected_font)):
        raise ConsultationPreparationFontError(
            "선택한 폰트가 한글 Unicode 글리프를 지원하지 않습니다."
        )
    pdf_bytes = _PdfRenderer(content, selected_font).render(generated_at)
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ConsultationPreparationPdfError(
            "상담 준비서가 올바른 PDF 형식으로 생성되지 않았습니다."
        )
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=True)
    except Exception as exc:
        raise ConsultationPreparationPdfError(
            "생성된 상담 준비서 PDF를 검증할 수 없습니다."
        ) from exc
    if not 3 <= len(reader.pages) <= 5:
        raise ConsultationPreparationPdfError(
            "상담 준비서 PDF 페이지 수가 비정상입니다."
        )
    return pdf_bytes
