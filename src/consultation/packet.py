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
from src.domain.product_models import OfficialCandidateShortlist
from src.domain.stage1_models import NormalizedScenarioSet
from src.domain.stage2_models import Stage2Input, Stage2Result
from src.domain.trade_risk_models import TradeSettlementRiskAssessment
from src.stage2.metrics import money_string


DISCLAIMER = (
    "본 결과는 금융상품 가입, 대출 승인 또는 헤지 실행을 결정하지 않습니다. "
    "환율 시나리오는 미래 환율의 확정 예측이 아닙니다. 실제 이용 가능 여부와 "
    "조건은 KB를 포함한 거래은행 상담과 심사를 통해 확인해야 합니다."
    " 거래·결제 검토 우선도는 금융기관의 공식 심사등급이나 부도확률이 "
    "아닙니다."
)


def _input_hash(
    *,
    confirmation: ConfirmationRecord,
    stage1: NormalizedScenarioSet,
    stage2_input: Stage2Input,
    trade_settlement_risk: Optional[
        TradeSettlementRiskAssessment
    ] = None,
    official_candidate_shortlist: Optional[
        OfficialCandidateShortlist
    ] = None,
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
    if trade_settlement_risk is not None:
        canonical["trade_risk_input_fingerprint"] = (
            trade_settlement_risk.input_fingerprint
        )
    if official_candidate_shortlist is not None:
        canonical["official_candidate_shortlist"] = {
            "selection_policy": (
                official_candidate_shortlist.selection_policy
            ),
            "trade_type": official_candidate_shortlist.trade_type,
            "candidates": [
                {
                    "product_id": candidate.product_id,
                    "category": candidate.category,
                    "source_url": candidate.source.url,
                    "source_verified_at": candidate.source.verified_at,
                    "matched_consultation_categories": (
                        candidate.matched_consultation_categories
                    ),
                }
                for candidate in official_candidate_shortlist.candidates
            ],
            "unmatched_consultation_categories": (
                official_candidate_shortlist
                .unmatched_consultation_categories
            ),
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
    if getattr(checks, "company_role_confirmed", False):
        fields.append("company_role")
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
    if packet.trade_settlement_risk is None:
        trade_risk_lines = (
            "- 거래처·결제·보호조건의 별도 확인 결과가 없습니다."
        )
        trade_risk_assumptions = "- 없음"
    else:
        trade_risk = packet.trade_settlement_risk
        priority_labels = {
            "STANDARD_REVIEW": "일반 검토",
            "ELEVATED_REVIEW": "추가 검토 필요",
            "HIGH_REVIEW": "우선 검토 필요",
            "UNKNOWN": "정보 확인 필요",
        }
        risk_type_labels = {
            "IMPORT_PREPAYMENT_PERFORMANCE_RISK": (
                "수입 선지급·계약이행 위험"
            ),
            "EXPORT_RECEIVABLE_COLLECTION_RISK": (
                "수출대금 회수 위험"
            ),
        }
        factor_lines = [
            "- {}: {}".format(
                {
                    "RISK_SIGNAL": "위험 신호",
                    "MITIGANT": "확인된 완화요소",
                    "INFORMATION_GAP": "정보 부족",
                }[factor.effect],
                factor.reason,
            )
            for factor in trade_risk.factors
        ]
        trade_risk_lines = "\n".join(
            [
                "- 위험 유형: {}".format(
                    risk_type_labels[trade_risk.risk_type]
                ),
                "- 검토 우선도: **{}**".format(
                    priority_labels[trade_risk.review_priority]
                ),
            ]
            + factor_lines
        )
        trade_risk_assumptions = (
            "\n".join(
                "- {}".format(item)
                for item in trade_risk.assumptions
            )
            or "- 별도 수치 가정 없음"
        )
    topic_lines = "\n".join(
        "- **{}**: {} 최종 판단은 사용자와 KB 담당자가 합니다.".format(
            item.title,
            item.explanation,
        )
        for item in packet.consultation_topics
    )
    if packet.official_candidate_shortlist is None:
        official_candidate_lines = (
            "- 공식 후보 검색을 아직 실행하지 않았습니다."
        )
    elif not packet.official_candidate_shortlist.candidates:
        official_candidate_lines = (
            "- 상담 필요 항목과 직접 연결되는 공식 후보를 찾지 못했습니다. "
            "후보를 임의로 만들지 않았습니다."
        )
    else:
        official_candidate_lines = "\n".join(
            "- **{}** · {} · [{}]({}) · 자료 확인일 {}  \n"
            "  연결 근거: {}".format(
                candidate.name,
                candidate.institution,
                candidate.source.title,
                candidate.source.url,
                candidate.source.verified_at,
                candidate.strategy_connection_reason,
            )
            for candidate in packet.official_candidate_shortlist.candidates
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

## 3. 환율·유동성 위험 원인

{risk_lines}

## 4. 거래·결제조건 위험

{trade_risk_lines}

적용 가정:

{trade_risk_assumptions}

## 5. 검토할 금융 대응

{topic_lines}

위 항목은 금융상품 추천이나 승인 결과가 아니라 상담 범주입니다.

## 6. 공식 출처 상담 후보

{official_candidate_lines}

후보는 최대 3개이며, 자격·승인·가격·한도는 제공 기관에서 다시 확인해야 합니다.

## 7. 아직 확인할 정보

{missing_lines}

## 8. 준비할 서류

{document_lines}

## 9. KB 상담 시 질문

{question_lines}

## 10. 재현성 정보

- 계산 버전: `{calculation_version}`
- 입력 hash: `{input_hash}`
- 환율 기준시각: `{exchange_rate_as_of}`
- 시나리오 ID: {scenario_ids}
- 생성시각: `{generated_at}`

## 11. 고지문

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
        trade_risk_lines=trade_risk_lines,
        trade_risk_assumptions=trade_risk_assumptions,
        topic_lines=topic_lines,
        official_candidate_lines=official_candidate_lines,
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
    trade_settlement_risk: Optional[
        TradeSettlementRiskAssessment
    ] = None,
    official_candidate_shortlist: Optional[
        OfficialCandidateShortlist
    ] = None,
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
    if trade_settlement_risk is not None:
        gaps = list(
            dict.fromkeys(
                gaps + trade_settlement_risk.information_gaps
            )
        )
    calculation_versions = [
        stage2_result.calculation_version,
        assessment.calculation_version,
    ]
    if trade_settlement_risk is not None:
        calculation_versions.append(
            trade_settlement_risk.calculation_version
        )
    packet = ConsultationPacket(
        case_id=case_id,
        calculation_version="+".join(calculation_versions),
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        input_hash=_input_hash(
            confirmation=confirmation,
            stage1=stage1,
            stage2_input=stage2_input,
            trade_settlement_risk=trade_settlement_risk,
            official_candidate_shortlist=official_candidate_shortlist,
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
        trade_settlement_risk=trade_settlement_risk,
        consultation_topics=consultation_topics,
        official_candidate_shortlist=official_candidate_shortlist,
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
