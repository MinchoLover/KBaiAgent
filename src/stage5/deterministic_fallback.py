from decimal import Decimal
from typing import Any, Dict, List, Optional

from schemas import TradeDocumentExtraction
from src.document_intake.confirmation import ConfirmationRecord
from src.domain.product_models import Stage4Result
from src.domain.report_models import ReportResult
from src.domain.stage1_models import NormalizedScenarioSet
from src.domain.stage1_web_models import MarketIntegrationResult
from src.domain.stage2_models import Stage2Result
from src.domain.stage3_models import Stage3Result
from src.stage5.critic import critique_report


def _product_lines(stage4: Stage4Result) -> List[str]:
    if not stage4.candidates:
        return ["- 공식 출처가 확인된 후보가 없습니다."]
    return [
        "- {} — {} ([공식 출처]({})); 자격·승인 조건은 상담 필요 "
        "[source: stage4.candidates.{}]".format(
            item.name,
            item.institution,
            item.source.url,
            index,
        )
        for index, item in enumerate(stage4.candidates)
    ]


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
        "stage4": stage4.model_dump(),
    }
    if market_integration is not None:
        bundle["market_integration"] = market_integration.model_dump()
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
) -> ReportResult:
    bundle = build_report_source_bundle(
        extraction=extraction,
        confirmation=confirmation,
        stage1=stage1,
        stage2=stage2,
        stage3=stage3,
        stage4=stage4,
        market_integration=market_integration,
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
    product_lines = "\n".join(_product_lines(stage4))
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
    markdown = """# 환율·현금흐름 리스크 검토 보고서

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

## 5. 위험 경보

- 최초 최소운영자금 부족일: {shortfall_date} [source: stage2.scenario_results]
- 최대 최소운영자금 부족액: {buffer_shortfall} [source: stage2.scenario_results]
- 대출한도 반영 후 부족액: {credit_shortfall} [source: stage2.scenario_results]

## 6. 전략 후보

{strategy_lines}

위 후보는 확정 자문이 아니라 입력 가정 아래 계산된 검토안입니다.
[source: stage3.status]

## 7. 금융상품·제도 후보와 출처

{product_lines}

## 8. 필요한 추가 정보

- 실제 은행 스프레드·수수료와 선물환 견적
- 기관별 최신 자격·한도·신청기간
- 확정된 원화 입출금 일정과 기존 헤지 계약서

## 9. 은행 상담 시 질문 목록

- 결제일과 통화 기준으로 가능한 선물환 한도와 전체 비용은 무엇인가?
- 중도 변경·조기결제·over-hedge 발생 시 조건은 무엇인가?
- 외화예금 및 환변동보험과 조합할 때 중복 노출은 없는가?

## 10. 가정·한계·면책

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
        strategy_lines=strategy_lines,
        product_lines=product_lines,
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
