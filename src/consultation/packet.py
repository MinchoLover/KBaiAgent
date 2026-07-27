import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from schemas import TradeDocumentExtraction
from src.document_intake.confirmation import ConfirmationRecord
from src.domain.consultation_models import (
    CompanySummary,
    ConsultationPacket,
    ConsultationPacketResult,
    ConsultationTopic,
    ExposureSummary,
    PacketRiskSummary,
    RiskAssessment,
    SourceDocumentReference,
)
from src.domain.stage1_models import NormalizedScenarioSet
from src.domain.stage2_models import Stage2Input, Stage2Result
from src.stage2.metrics import money_string


DISCLAIMER = (
    "본 결과는 금융상품 가입, 대출 승인 또는 헤지 실행을 결정하지 않습니다. "
    "환율 시나리오는 미래 환율의 확정 예측이 아닙니다. 실제 이용 가능 여부와 "
    "조건은 KB를 포함한 거래은행 상담과 심사를 통해 확인해야 합니다."
)


def _input_hash(
    *,
    confirmation: ConfirmationRecord,
    stage1: NormalizedScenarioSet,
    stage2_input: Stage2Input,
) -> str:
    canonical: Dict[str, Any] = {
        "confirmation": {
            "source_sha256": confirmation.source_sha256,
            "confirmed_values": confirmation.confirmed_values,
            "checks": confirmation.checks.model_dump(),
        },
        "stage1": stage1.model_dump(),
        "stage2_input": stage2_input.model_dump(),
    }
    serialized = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _worst_scenario(
    stage2_result: Stage2Result,
    assessment: RiskAssessment,
) -> Any:
    for item in stage2_result.scenario_results:
        if item.scenario_name == assessment.worst_scenario_id:
            return item
    raise ValueError("위험 분류의 worst scenario가 Stage 2 결과에 없습니다.")


def _confirmed_fields(
    confirmation: ConfirmationRecord,
) -> List[str]:
    checks = confirmation.checks
    fields: List[str] = []
    if getattr(checks, "trade_type_confirmed", False):
        fields.append("trade_type")
    if checks.currency_confirmed:
        fields.append("currency")
    if checks.amount_due_confirmed:
        fields.append("trade_amount_fx")
    if checks.due_date_confirmed:
        fields.append("settlement_date")
    return fields


def _settlement_date(stage2_result: Stage2Result) -> str:
    dates = list(
        dict.fromkeys(
            item.settlement_date
            for item in stage2_result.exposure_computations
        )
    )
    return ", ".join(dates)


def _required_documents(
    topics: List[ConsultationTopic],
) -> List[str]:
    return list(
        dict.fromkeys(
            document
            for topic in topics
            for document in topic.required_documents
        )
    )


def _questions(topics: List[ConsultationTopic]) -> List[str]:
    return list(
        dict.fromkeys(
            question
            for topic in topics
            for question in topic.questions
        )
    )


def _markdown(packet: ConsultationPacket) -> str:
    risk_lines = (
        "\n".join(
            "- `{}` · 시나리오 `{}` · 기준값 {} / 임계값 {}".format(
                item.risk_code,
                item.scenario_id or "공통",
                item.trigger_value,
                item.threshold or "없음",
            )
            for item in packet.risk_findings
        )
        or "- 현재 입력에서 구조화된 주요 위험 코드가 발생하지 않았습니다."
    )
    topic_lines = "\n".join(
        "- **{}** (`{}`): {} 최종 판단은 사용자와 KB 담당자가 합니다.".format(
            item.title,
            item.category,
            item.explanation,
        )
        for item in packet.consultation_topics
    )
    missing_lines = (
        "\n".join("- {}".format(item) for item in packet.missing_information)
        or "- 현재 패킷에 명시적으로 등록된 미확인 항목이 없습니다."
    )
    document_lines = (
        "\n".join("- {}".format(item) for item in packet.required_documents)
        or "- 상담 과정에서 필요한 서류를 확인해야 합니다."
    )
    question_lines = (
        "\n".join("- {}".format(item) for item in _questions(
            packet.consultation_topics
        ))
        or "- 실제 이용 가능 조건과 추가 확인사항은 무엇인가?"
    )
    loss_label = (
        "추가 원화 비용"
        if packet.company_summary.trade_type == "IMPORT"
        else "원화 수취 감소"
    )
    return """# KB 상담 준비 패킷

## 1. 거래 요약

- Case ID: `{case_id}`
- 거래 방향: {trade_type}
- 통화·금액: {currency} {trade_amount}
- 거래 상대국: {counterparty}
- 결제·수취일: {settlement_date}
- 열린 환노출: {currency} {open_exposure}
- 사용자 확인 필드: {confirmed_fields}

## 2. 핵심 계산 결과

- 가장 위험한 스트레스 시나리오: {worst_scenario}
- {loss_label}: {loss}원
- 결제·수취 후 현금: {ending_cash}원
- 최소 운영자금 부족: {buffer_shortfall}원
- 실제 현금 적자: {cash_deficit}원
- 대출한도 반영 후 지급 부족: {payment_gap}원

`최소 운영자금 부족`과 `대출한도 반영 후 지급 부족`은 서로 다른 지표입니다.

## 3. 위험 원인

{risk_lines}

## 4. 검토할 금융 대응

{topic_lines}

위 항목은 금융상품 추천이나 승인 결과가 아니라 상담 범주입니다.

## 5. 아직 확인할 정보

{missing_lines}

## 6. 준비할 서류

{document_lines}

## 7. KB 상담 시 질문

{question_lines}

## 8. 재현성 정보

- 계산 버전: `{calculation_version}`
- 입력 hash: `{input_hash}`
- 환율 기준시각: `{exchange_rate_as_of}`
- 시나리오 ID: {scenario_ids}
- 생성시각: `{generated_at}`

## 9. 고지문

{disclaimer}
""".format(
        case_id=packet.case_id,
        trade_type=packet.company_summary.trade_type,
        currency=packet.company_summary.currency,
        trade_amount=packet.company_summary.trade_amount_fx,
        counterparty=packet.company_summary.counterparty_country or "미확인",
        settlement_date=packet.company_summary.settlement_date,
        open_exposure=packet.exposure_summary.open_exposure_fx,
        confirmed_fields=(
            ", ".join(packet.user_confirmed_fields) or "없음"
        ),
        worst_scenario=packet.risk_summary.worst_scenario_id,
        loss_label=loss_label,
        loss=packet.risk_summary.additional_cost_or_receipt_loss_krw,
        ending_cash=packet.risk_summary.cash_after_settlement_krw,
        buffer_shortfall=packet.risk_summary.buffer_shortfall_krw,
        cash_deficit=packet.risk_summary.cash_deficit_krw,
        payment_gap=packet.risk_summary.payment_gap_krw,
        risk_lines=risk_lines,
        topic_lines=topic_lines,
        missing_lines=missing_lines,
        document_lines=document_lines,
        question_lines=question_lines,
        calculation_version=packet.calculation_version,
        input_hash=packet.input_hash,
        exchange_rate_as_of=packet.exchange_rate_as_of,
        scenario_ids=", ".join(packet.scenario_ids),
        generated_at=packet.generated_at,
        disclaimer=packet.disclaimer,
    )


def build_consultation_packet(
    *,
    case_id: str,
    extraction: TradeDocumentExtraction,
    confirmation: ConfirmationRecord,
    stage1: NormalizedScenarioSet,
    stage2_input: Stage2Input,
    stage2_result: Stage2Result,
    assessment: RiskAssessment,
    consultation_topics: List[ConsultationTopic],
    missing_information: Optional[List[str]] = None,
    generated_at: Optional[str] = None,
) -> ConsultationPacketResult:
    worst = _worst_scenario(stage2_result, assessment)
    loss = max(Decimal(worst.loss_vs_base), Decimal("0"))
    counterparty_country = (
        extraction.seller_country
        if stage2_result.trade_type == "IMPORT"
        else extraction.buyer_country
    )
    gaps = list(
        dict.fromkeys(
            item.strip()
            for item in (missing_information or [])
            if item and item.strip()
        )
    )
    packet = ConsultationPacket(
        case_id=case_id,
        calculation_version="{}+{}".format(
            stage2_result.calculation_version,
            assessment.calculation_version,
        ),
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        input_hash=_input_hash(
            confirmation=confirmation,
            stage1=stage1,
            stage2_input=stage2_input,
        ),
        exchange_rate_as_of=stage1.as_of,
        scenario_ids=[
            item.scenario_name for item in stage2_result.scenario_results
        ],
        company_summary=CompanySummary(
            trade_type=stage2_result.trade_type,
            currency=stage2_result.currency,
            counterparty_country=counterparty_country,
            settlement_date=_settlement_date(stage2_result),
            trade_amount_fx=stage2_result.total_foreign_amount,
        ),
        exposure_summary=ExposureSummary(
            gross_exposure_fx=stage2_result.total_foreign_amount,
            usable_fx_balance=stage2_result.held_fx_used,
            existing_hedge_fx=stage2_result.hedged_amount,
            open_exposure_fx=stage2_result.open_exposure,
        ),
        risk_summary=PacketRiskSummary(
            status=assessment.status,
            worst_scenario_id=assessment.worst_scenario_id,
            additional_cost_or_receipt_loss_krw=money_string(loss),
            cash_after_settlement_krw=worst.ending_cash,
            buffer_shortfall_krw=worst.maximum_buffer_shortfall,
            cash_deficit_krw=worst.cash_deficit,
            payment_gap_krw=worst.post_credit_shortfall,
            risk_codes=assessment.risk_codes,
        ),
        risk_findings=assessment.findings,
        consultation_topics=consultation_topics,
        missing_information=gaps,
        required_documents=_required_documents(consultation_topics),
        source_documents=[
            SourceDocumentReference(
                document_id=confirmation.source_sha256,
                filename=confirmation.source_filename,
                document_type=extraction.document_type,
            )
        ],
        user_confirmed_fields=_confirmed_fields(confirmation),
        disclaimer=DISCLAIMER,
    )
    return ConsultationPacketResult(
        packet=packet,
        markdown=_markdown(packet),
    )
