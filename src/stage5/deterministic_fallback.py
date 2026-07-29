from decimal import Decimal
from typing import Any, Dict, List, Optional

from schemas import TradeDocumentExtraction
from src.document_intake.confirmation import ConfirmationRecord
from src.domain.consultation_models import ConsultationPacket
from src.domain.product_models import Stage4Result
from src.domain.report_models import ReportResult
from src.domain.stage1_models import NormalizedScenarioSet
from src.domain.stage1_web_models import MarketIntegrationResult
from src.domain.stage2_models import Stage2Result
from src.domain.stage3_models import Stage3Result
from src.stage5.critic import critique_report


def _product_lines(
    *,
    stage4: Stage4Result,
    consultation_packet: Optional[ConsultationPacket],
) -> List[str]:
    if consultation_packet is not None:
        shortlist = consultation_packet.official_candidate_shortlist
        candidates = shortlist.candidates if shortlist is not None else []
        source_prefix = (
            "consultation.official_candidate_shortlist.candidates"
        )
    else:
        candidates = stage4.candidates
        source_prefix = "stage4.candidates"
    if not candidates:
        return [
            "- 공식 출처가 확인된 후보가 없습니다. 현재 상담 항목과 "
            "직접 연결되지 않은 상품을 임의로 만들지 않았습니다."
        ]
    return [
        "- {} — {} ([공식 출처]({})); 자격·승인 조건은 상담 필요 "
        "[source: {}.{}]".format(
            item.name,
            item.institution,
            item.source.url,
            source_prefix,
            index,
        )
        for index, item in enumerate(candidates)
    ]


def _trade_risk_lines(
    consultation_packet: Optional[ConsultationPacket],
) -> List[str]:
    if (
        consultation_packet is None
        or consultation_packet.trade_settlement_risk is None
    ):
        return ["- 거래·결제조건의 별도 위험평가 결과가 없습니다."]
    assessment = consultation_packet.trade_settlement_risk
    risk_type_labels = {
        "IMPORT_PREPAYMENT_PERFORMANCE_RISK": (
            "수입 선지급·계약이행 위험"
        ),
        "EXPORT_RECEIVABLE_COLLECTION_RISK": (
            "수출대금 회수 위험"
        ),
    }
    priority_labels = {
        "STANDARD_REVIEW": "일반 검토",
        "ELEVATED_REVIEW": "추가 검토 필요",
        "HIGH_REVIEW": "우선 검토 필요",
        "UNKNOWN": "정보 확인 필요",
    }
    lines = [
        "- 위험 유형은 **{}**, 검토 우선도는 **{}**입니다. "
        "[source: consultation.trade_settlement_risk]".format(
            risk_type_labels[assessment.risk_type],
            priority_labels[assessment.review_priority],
        )
    ]
    lines.extend(
        "- {} [source: consultation.trade_settlement_risk.factors.{}]".format(
            factor.reason,
            index,
        )
        for index, factor in enumerate(assessment.factors)
    )
    return lines


def _country_environment_lines(
    consultation_packet: Optional[ConsultationPacket],
) -> List[str]:
    if (
        consultation_packet is None
        or consultation_packet.country_environment is None
    ):
        return ["- 국가·무역환경의 별도 공식자료 검토 결과가 없습니다."]
    assessment = consultation_packet.country_environment
    priority_labels = {
        "STANDARD_REVIEW": "통상 검토",
        "ELEVATED_REVIEW": "추가 검토",
        "HIGH_REVIEW": "우선 검토",
        "INSUFFICIENT_INFORMATION": "정보 부족",
    }
    references = {
        item.source_record_id: (index, item)
        for index, item in enumerate(
            assessment.official_source_references
        )
    }
    lines = [
        "- 거래국은 **{}**, 거래 검토 우선순위는 **{}**입니다. "
        "이는 국가 신용등급이 아니라 상담 순서입니다. "
        "[source: consultation.country_environment]".format(
            assessment.country,
            priority_labels[assessment.review_priority],
        )
    ]
    oecd = assessment.oecd_payment_transfer
    oecd_reference = references.get(oecd.source_record_id or "")
    if oecd.status == "CLASSIFIED":
        oecd_text = (
            "OECD 공식 원자료 분류는 {}이며 KBaiAgent 자체 국가등급이 "
            "아닙니다.".format(oecd.raw_classification)
        )
    elif oecd.status == "HIGH_INCOME_OECD_UNCLASSIFIED":
        oecd_text = (
            "고소득 OECD 회원국 미분류이며 0 또는 낮은 위험으로 "
            "변환하지 않았습니다."
        )
    else:
        oecd_text = "OECD 원자료를 확인할 수 없어 정보 부족으로 처리했습니다."
    if oecd_reference is not None:
        reference_index, reference = oecd_reference
        lines.append(
            "- 지급·이전 환경 — {} 기준일 {}. {} 한계: {} "
            "([공식 출처]({})) "
            "[source: consultation.country_environment."
            "oecd_payment_transfer] "
            "[source: consultation.country_environment."
            "official_source_references.{}]".format(
                oecd_text,
                oecd.as_of_date,
                oecd.interpretation,
                oecd.limitations,
                reference.official_url,
                reference_index,
            )
        )
    else:
        lines.append(
            "- 지급·이전 환경 — {} {} 한계: {} "
            "[source: consultation.country_environment."
            "oecd_payment_transfer]".format(
                oecd_text,
                oecd.interpretation,
                oecd.limitations,
            )
        )
    for index, item in enumerate(
        assessment.world_bank_macro_environment.observations
    ):
        reference_index, reference = references[item.source_record_id]
        raw = (
            item.raw_value
            if item.raw_value is not None
            else item.raw_status or "자료 없음"
        )
        lines.append(
            "- 거시환경 — World Bank `{}` 원값 {} {}, 관측기간 {}, "
            "자료 기준일 {}. {} 한계: {} ([공식 출처]({})) "
            "[source: consultation.country_environment."
            "world_bank_macro_environment.observations.{}] "
            "[source: consultation.country_environment."
            "official_source_references.{}]".format(
                item.indicator_code,
                raw,
                item.raw_unit,
                item.observation_period,
                item.as_of_date,
                item.interpretation,
                item.limitations,
                reference.official_url,
                index,
                reference_index,
            )
        )
    for index, item in enumerate(
        assessment.wto_trade_market_access.observations
    ):
        reference_index, reference = references[item.source_record_id]
        raw = (
            item.raw_value
            if item.raw_value is not None
            else item.raw_status or "자료 없음"
        )
        lines.append(
            "- 무역·시장접근 — WTO `{}` 원값/status {} {}, 자료기간 {}, "
            "자료 기준일 {}. {} 한계: {} ([공식 출처]({})) "
            "[source: consultation.country_environment."
            "wto_trade_market_access.observations.{}] "
            "[source: consultation.country_environment."
            "official_source_references.{}]".format(
                item.indicator_code,
                raw,
                item.raw_unit,
                item.observation_period,
                item.as_of_date,
                item.interpretation,
                item.limitations,
                reference.official_url,
                index,
                reference_index,
            )
        )
    return lines


def _consultation_topic_lines(
    consultation_packet: Optional[ConsultationPacket],
) -> List[str]:
    if (
        consultation_packet is None
        or not consultation_packet.consultation_topics
    ):
        return ["- 별도로 구조화된 금융 상담 항목이 없습니다."]
    if consultation_packet.consultation_priorities:
        lines: List[str] = []
        authoritative_product_ids = {
            item.product_id
            for item in (
                consultation_packet.official_candidate_shortlist.candidates
                if (
                    consultation_packet.official_candidate_shortlist
                    is not None
                )
                else []
            )
        }
        for index, priority in enumerate(
            consultation_packet.consultation_priorities
        ):
            rationale = " · ".join(
                "{} {} {}".format(
                    item.label,
                    item.value,
                    (
                        item.currency
                        if item.unit == "FX"
                        else item.unit
                    ),
                )
                for item in priority.numeric_rationale
            ) or "별도 수치 없음"
            missing = (
                " / ".join(priority.missing_information)
                or "별도 등록 없음"
            )
            grounded_priority_candidates = [
                item
                for item in priority.official_candidates
                if item.product_id in authoritative_product_ids
            ]
            candidates = (
                " / ".join(
                    "{}({})".format(
                        item.name,
                        item.institution,
                    )
                    for item in grounded_priority_candidates
                )
                or "현재 검증된 공식 후보 없음"
            )
            lines.append(
                "- **{rank}순위 {title}** — 검토 순서 근거: "
                "{reason} 숫자·조건: {rationale}. 부족정보: {missing}. "
                "상담에서 기대하는 결정: {decision}. 다음 행동: "
                "{action}. 공식 후보: {candidates}. {disclaimer} "
                "[source: consultation.consultation_priorities.{index}]"
                .format(
                    rank=priority.rank,
                    title=priority.title,
                    reason=priority.priority_reason,
                    rationale=rationale,
                    missing=missing,
                    decision=priority.expected_decision,
                    action=priority.next_action,
                    candidates=candidates,
                    disclaimer=priority.disclaimer,
                    index=index,
                )
            )
        for index, topic in enumerate(
            consultation_packet.other_consultation_topics
        ):
            lines.append(
                "- 기타 확인사항 — **{}**: {} "
                "[source: consultation.other_consultation_topics.{}]"
                .format(topic.title, topic.explanation, index)
            )
        return lines
    return [
        "- **{}**: {} [source: consultation.consultation_topics.{}]".format(
            topic.title,
            topic.explanation,
            index,
        )
        for index, topic in enumerate(
            consultation_packet.consultation_topics
        )
    ]


def _missing_information_lines(
    consultation_packet: Optional[ConsultationPacket],
) -> List[str]:
    if (
        consultation_packet is None
        or not consultation_packet.missing_information
    ):
        return ["- 현재 보고서에 등록된 미확인 항목이 없습니다."]
    return [
        "- {} [source: consultation.missing_information.{}]".format(
            item,
            index,
        )
        for index, item in enumerate(
            consultation_packet.missing_information
        )
    ]


def _question_lines(
    consultation_packet: Optional[ConsultationPacket],
) -> List[str]:
    if consultation_packet is None:
        return [
            "- 실제 이용 가능 조건과 추가 확인사항은 무엇인가?",
        ]
    rows: List[str] = []
    seen = set()
    for priority_index, priority in enumerate(
        consultation_packet.consultation_priorities
    ):
        for question in priority.bank_questions:
            if question in seen:
                continue
            seen.add(question)
            rows.append(
                "- {} [source: consultation.consultation_priorities.{}]"
                .format(question, priority_index)
            )
            if len(rows) == 5:
                return rows
    for topic_index, topic in enumerate(
        consultation_packet.consultation_topics
    ):
        for question in topic.questions:
            if question in seen:
                continue
            seen.add(question)
            rows.append(
                "- {} [source: consultation.consultation_topics.{}]".format(
                    question,
                    topic_index,
                )
            )
            if len(rows) == 5:
                return rows
    return rows or ["- 실제 이용 가능 조건과 추가 확인사항은 무엇인가?"]


def _strategy_lines(stage3: Stage3Result) -> List[str]:
    if not stage3.candidates:
        return [
            "- 현재 입력과 제약을 모두 충족하는 시뮬레이션 후보가 "
            "없습니다. 추가 자금·결제조건 조정·은행 상담이 필요합니다. "
            "[source: stage3.status] "
            "[source: stage3.infeasible_reasons]"
        ]
    lines: List[str] = []
    for index, item in enumerate(stage3.candidates):
        expected_text = (
            " · 기대손실 {}".format(item.expected_loss)
            if item.expected_loss is not None
            else ""
        )
        lines.append(
            "- 후보 {rank}: 선물환 {forward} · 분할환전 {staged} · "
            "미헤지 {unhedged} · 최악손실 {worst} · 비용가정 {cost}"
            "{expected} · 제약 {constraint}. {reason} "
            "[source: stage3.candidates.{index}]".format(
                rank=item.rank,
                forward=item.forward_ratio,
                staged=item.staged_conversion_ratio,
                unhedged=item.unhedged_ratio,
                worst=item.worst_case_loss,
                cost=item.assumed_hedge_cost,
                expected=expected_text,
                constraint=(
                    "충족" if item.constraints_satisfied else "미충족"
                ),
                reason=item.rationale,
                index=index,
            )
        )
    return lines


def build_report_source_bundle(
    *,
    extraction: TradeDocumentExtraction,
    confirmation: ConfirmationRecord,
    stage1: NormalizedScenarioSet,
    stage2: Stage2Result,
    stage3: Stage3Result,
    stage4: Stage4Result,
    market_integration: Optional[MarketIntegrationResult] = None,
    consultation_packet: Optional[ConsultationPacket] = None,
) -> Dict[str, Any]:
    confirmed_values = {
        key: confirmation.confirmed_values.get(key)
        for key in (
            "trade_type",
            "currency",
            "amount_due",
            "settlement_date",
            "installment_due_dates",
        )
        if key in confirmation.confirmed_values
    }
    stage4_bundle: Dict[str, Any]
    if consultation_packet is None:
        stage4_bundle = stage4.model_dump()
    else:
        stage4_bundle = {
            "schema_version": stage4.schema_version,
            "mode": stage4.mode,
            "query": stage4.query,
            "retrieval_candidate_count": len(stage4.candidates),
            "warnings": stage4.warnings,
            "user_facing_candidates": (
                "consultation.official_candidate_shortlist.candidates"
            ),
        }
    bundle: Dict[str, Any] = {
        "stage0": {
            "extraction": {
                "document_type": extraction.document_type,
                "document_number": extraction.document_number,
                "company_role": extraction.company_role,
                "trade_type": extraction.trade_type,
                "currency": extraction.currency,
                "amount_due": extraction.amount_due,
                "payment_terms": extraction.payment_terms,
                "incoterm": extraction.incoterm,
                "seller_country": extraction.seller_country,
                "buyer_country": extraction.buyer_country,
                "installments": [
                    item.model_dump()
                    for item in extraction.installments
                ],
                "evidence_ids": [
                    "stage0.extraction.evidence.{}".format(item.field)
                    for item in extraction.evidence
                ],
            },
            "confirmation": {
                "source_filename": confirmation.source_filename,
                "source_sha256": confirmation.source_sha256,
                "confirmed_at": confirmation.confirmed_at,
                "company_role": confirmation.company_role,
                "company_country": confirmation.company_country,
                "confirmed_values": confirmed_values,
                "checks": confirmation.checks.model_dump(),
            },
        },
        "stage1": stage1.model_dump(),
        "stage2": stage2.model_dump(),
        "stage3": stage3.model_dump(),
        "stage4": stage4_bundle,
    }
    if market_integration is not None:
        bundle["market_integration"] = market_integration.model_dump()
    if consultation_packet is not None:
        bundle["consultation"] = consultation_packet.model_dump()
    return bundle


def generate_deterministic_report(
    *,
    extraction: TradeDocumentExtraction,
    confirmation: ConfirmationRecord,
    stage1: NormalizedScenarioSet,
    stage2: Stage2Result,
    stage3: Stage3Result,
    stage4: Stage4Result,
    market_integration: Optional[MarketIntegrationResult] = None,
    consultation_packet: Optional[ConsultationPacket] = None,
) -> ReportResult:
    bundle = build_report_source_bundle(
        extraction=extraction,
        confirmation=confirmation,
        stage1=stage1,
        stage2=stage2,
        stage3=stage3,
        stage4=stage4,
        market_integration=market_integration,
        consultation_packet=consultation_packet,
    )
    worst = max(
        stage2.scenario_results,
        key=lambda item: Decimal(item.loss_vs_base),
    )
    scenario_nature = (
        "수동 환율 값은 예측이 아니라 스트레스 가정입니다."
        if stage1.kind == "STRESS"
        else "외부 Stage 1 값은 FORECAST이며 보장값이 아닙니다."
    )
    settlement_value = confirmation.confirmed_values.get("settlement_date")
    if settlement_value:
        due_date = str(settlement_value)
        due_source = (
            "stage0.confirmation.confirmed_values.settlement_date"
        )
    else:
        installment_dates = confirmation.confirmed_values.get(
            "installment_due_dates",
            [],
        )
        due_date = (
            ", ".join(str(item) for item in installment_dates if item)
            if isinstance(installment_dates, list)
            else ""
        ) or "미확인"
        due_source = (
            "stage0.confirmation.confirmed_values.installment_due_dates"
        )
    product_lines = "\n".join(
        _product_lines(
            stage4=stage4,
            consultation_packet=consultation_packet,
        )
    )
    trade_risk_lines = "\n".join(
        _trade_risk_lines(consultation_packet)
    )
    country_environment_lines = "\n".join(
        _country_environment_lines(consultation_packet)
    )
    country_environment_policy_note = (
        "OECD·World Bank·WTO는 합산 점수로 만들지 않았고 국가 신호는 "
        "Stage 2 현금흐름이나 Stage 3 환헤지 비율을 변경하지 않습니다.\n"
        "[source: consultation.country_environment]"
        if (
            consultation_packet is not None
            and consultation_packet.country_environment is not None
        )
        else "국가 공식자료 검토가 연결되지 않아 별도 해석을 만들지 않았습니다."
    )
    consultation_topic_lines = "\n".join(
        _consultation_topic_lines(consultation_packet)
    )
    missing_information_lines = "\n".join(
        _missing_information_lines(consultation_packet)
    )
    question_lines = "\n".join(
        _question_lines(consultation_packet)
    )
    strategy_lines = "\n".join(_strategy_lines(stage3))
    market_context_lines = ""
    if (
        market_integration is not None
        and market_integration.forecast_load is not None
    ):
        forecast = market_integration.forecast_load.forecast
        mismatch_text = (
            "결제일은 모델 검증범위 밖이므로 모델 분위수 환율은 "
            "결제기간 계산에서 제외했습니다."
            if market_integration.scenario_build.horizon_mismatch
            else "결제일이 모델 검증범위 안이어서 경로위험 분위수를 "
            "시나리오 계산에 포함했습니다."
        )
        market_context_lines = """

- 방향 점수: {direction} (상승 {up_score}, 하락 {down_score}). 이 값은 보정된 실제 발생확률이 아닙니다. [source: market_integration.forecast_load.forecast.direction]
- 모델 검증범위: {horizon_days}거래일. {mismatch_text} [source: market_integration.forecast_load.forecast.horizon] [source: market_integration.scenario_build.horizon_mismatch]
- q90은 발생확률이 아니라 모델 예측분포의 상위 경로위험 분위수입니다. [source: market_integration.scenario_build.model_path_scenarios]
- 뉴스는 시장 문맥 설명에만 사용했고 환율·손실 숫자를 변경하지 않았습니다. [source: market_integration.forecast_load.forecast.market_context]
""".format(
            direction=forecast.direction.label,
            up_score=forecast.direction.up_score,
            down_score=forecast.direction.down_score,
            horizon_days=forecast.horizon.trading_days,
            mismatch_text=mismatch_text,
        )
    markdown = """# 수출입 금융 리스크 검토 보고서

## 1. 거래 요약

- 거래 방향: {trade_type} [source: stage2.trade_type]
- 거래 통화: {currency} [source: stage2.currency]
- 거래 외화금액: {amount} [source: stage2.total_foreign_amount]
- 결제 확인값: {due_date} [source: {due_source}]

## 2. 데이터 출처와 사용자 확인 여부

문서 파일 `{filename}`의 fingerprint를 기록했습니다. [source: stage0.confirmation.source_filename]
통화·금액·결제일 확인과 확인시각이 기록되었습니다. [source: stage0.confirmation.checks]

## 3. 환율 시나리오 성격

{scenario_nature} 적용 규칙: {application_rule} [source: stage1.kind] [source: stage1.application_rule]
{market_context_lines}

## 4. 현금흐름 영향

- BASE 필요/수취 원화: {base_flow} [source: stage2.base_required_or_proceeds_krw]
- 최악 손실 시나리오: {worst_name} [source: stage2.scenario_results]
- BASE 대비 손실: {worst_loss} [source: stage2.scenario_results]
- 결제 후 잔고: {ending_cash} [source: stage2.scenario_results]

## 5. 환율·유동성 위험 경보

- 최초 최소운영자금 부족일: {shortfall_date} [source: stage2.scenario_results]
- 최대 최소운영자금 부족액: {buffer_shortfall} [source: stage2.scenario_results]
- 대출한도 반영 후 부족액: {credit_shortfall} [source: stage2.scenario_results]

## 6. 거래·결제조건 위험

{trade_risk_lines}

이 결과는 금융기관의 공식 심사등급·부도확률·보험 인수판단이 아닙니다.

## 7. 국가·무역환경 검토

{country_environment_lines}

{country_environment_policy_note}

## 8. 환헤지 시뮬레이션 후보

{strategy_lines}

위 후보는 확정 자문이 아니라 입력 가정 아래 계산된 검토안입니다.
[source: stage3.status]

## 9. 검토할 금융 대응

{consultation_topic_lines}

결제·회수 위험이 환헤지 비율을 직접 변경하지 않으며, 최종 판단은 사용자와
거래은행·보험기관 담당자가 합니다.

## 10. 공식 출처 상담 후보

{product_lines}

## 11. 아직 확인할 정보

{missing_information_lines}

## 12. 은행·보험기관 상담 시 질문

{question_lines}

## 13. 가정·한계·면책

본 결과는 제공된 입력의 결정론적 계산과 공식자료 후보 정리이며 금융자문·승인·보장을
의미하지 않습니다. 실제 거래 전 은행·보험기관·전문가 확인이 필요합니다.
""".format(
        trade_type=stage2.trade_type,
        currency=stage2.currency,
        amount=stage2.total_foreign_amount,
        due_date=due_date,
        due_source=due_source,
        filename=confirmation.source_filename,
        scenario_nature=scenario_nature,
        application_rule=stage1.application_rule,
        market_context_lines=market_context_lines,
        base_flow=stage2.base_required_or_proceeds_krw,
        worst_name=worst.scenario_name,
        worst_loss=worst.loss_vs_base,
        ending_cash=worst.ending_cash,
        shortfall_date=worst.first_buffer_shortfall_date or "없음",
        buffer_shortfall=worst.maximum_buffer_shortfall,
        credit_shortfall=worst.post_credit_shortfall,
        trade_risk_lines=trade_risk_lines,
        country_environment_lines=country_environment_lines,
        country_environment_policy_note=country_environment_policy_note,
        strategy_lines=strategy_lines,
        consultation_topic_lines=consultation_topic_lines,
        product_lines=product_lines,
        missing_information_lines=missing_information_lines,
        question_lines=question_lines,
    )
    critique = critique_report(
        markdown=markdown,
        source_bundle=bundle,
        scenario_kind=stage1.kind,
        probability_valid=stage1.probability_valid,
    )
    return ReportResult(
        status="DETERMINISTIC_FALLBACK",
        markdown=markdown,
        report_json=bundle,
        critique=critique,
        warnings=[
            "LLM 없이 계산 JSON을 그대로 인용한 결정론 보고서입니다."
        ],
        generation_provider="DETERMINISTIC_TEMPLATE",
        revision_count=0,
        fallback_reason="DETERMINISTIC_POLICY",
    )
