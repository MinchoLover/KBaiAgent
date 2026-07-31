from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

from src.domain.consultation_models import (
    RiskAssessment,
    RiskFinding,
    RiskStatus,
)
from src.domain.stage2_models import (
    ScenarioResult,
    Stage2Input,
    Stage2Result,
)


RISK_CLASSIFICATION_VERSION = "risk-classifier-1.0"


def _decimal(value: str, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(
            "{}은 decimal 문자열이어야 합니다.".format(field)
        ) from exc
    if not parsed.is_finite():
        raise ValueError("{}은 유한한 값이어야 합니다.".format(field))
    return parsed


def _positive(value: str, field: str) -> Decimal:
    return max(_decimal(value, field), Decimal("0"))


def _worst_scenario(result: Stage2Result) -> ScenarioResult:
    if not result.scenario_results:
        raise ValueError("위험 분류에는 Stage 2 시나리오 결과가 필요합니다.")
    return max(
        result.scenario_results,
        key=lambda item: (
            _positive(
                item.post_credit_shortfall,
                "post_credit_shortfall",
            ),
            _positive(item.cash_deficit, "cash_deficit"),
            _positive(
                item.maximum_buffer_shortfall,
                "maximum_buffer_shortfall",
            ),
            _positive(item.loss_vs_base, "loss_vs_base"),
            -_decimal(item.ending_cash, "ending_cash"),
        ),
    )


def _status(
    *,
    payment_gap: Decimal,
    cash_deficit: Decimal,
    buffer_shortfall: Decimal,
    loss_limit_exceeded: bool,
) -> RiskStatus:
    if payment_gap > 0:
        return "PAYMENT_GAP"
    if cash_deficit > 0:
        return "NEGATIVE_CASH"
    if buffer_shortfall > 0:
        return "BUFFER_SHORTFALL"
    if loss_limit_exceeded:
        return "LOSS_LIMIT_EXCEEDED"
    return "SAFE"


def _settlement_dates(result: Stage2Result) -> List[str]:
    return [
        item.settlement_date
        for item in result.exposure_computations
    ]


def _finding_key(item: RiskFinding) -> Tuple[str, Optional[str]]:
    return item.risk_code, item.scenario_id


def classify_stage2_risks(
    *,
    stage2_result: Stage2Result,
    stage2_input: Optional[Stage2Input] = None,
    missing_information: Optional[List[str]] = None,
) -> RiskAssessment:
    worst = _worst_scenario(stage2_result)
    loss = _positive(worst.loss_vs_base, "loss_vs_base")
    buffer_shortfall = _positive(
        worst.maximum_buffer_shortfall,
        "maximum_buffer_shortfall",
    )
    cash_deficit = _positive(worst.cash_deficit, "cash_deficit")
    payment_gap = _positive(
        worst.post_credit_shortfall,
        "post_credit_shortfall",
    )
    acceptable_loss = _decimal(
        str(
            stage2_result.stage3_constraints.get(
                "acceptable_fx_loss",
                "0",
            )
        ),
        "acceptable_fx_loss",
    )
    findings: List[RiskFinding] = []

    if loss > 0:
        risk_code = (
            "FX_COST_RISK"
            if stage2_result.trade_type == "IMPORT"
            else "FX_RECEIPT_RISK"
        )
        findings.append(
            RiskFinding(
                risk_code=risk_code,
                severity="WARNING",
                scenario_id=worst.scenario_name,
                trigger_value=str(loss),
                threshold="0",
                unit="KRW",
                explanation_data={
                    "trade_type": stage2_result.trade_type,
                    "scenario_rate": worst.scenario_rate,
                    "applied_rate": worst.applied_rate,
                    "loss_vs_base_krw": worst.loss_vs_base,
                    "open_exposure_fx": stage2_result.open_exposure,
                },
            )
        )

    loss_limit_exceeded = bool(
        worst.acceptable_loss_exceeded or loss > acceptable_loss
    )
    if loss_limit_exceeded:
        findings.append(
            RiskFinding(
                risk_code="LOSS_LIMIT_EXCEEDED",
                severity="WARNING",
                scenario_id=worst.scenario_name,
                trigger_value=str(loss),
                threshold=str(acceptable_loss),
                unit="KRW",
                explanation_data={
                    "loss_vs_base_krw": worst.loss_vs_base,
                    "acceptable_fx_loss_krw": str(acceptable_loss),
                },
            )
        )

    if buffer_shortfall > 0:
        minimum_buffer = str(
            stage2_result.stage3_constraints.get(
                "minimum_cash_buffer",
                "0",
            )
        )
        findings.append(
            RiskFinding(
                risk_code="LIQUIDITY_BUFFER_RISK",
                severity="WARNING",
                scenario_id=worst.scenario_name,
                trigger_value=str(buffer_shortfall),
                threshold="0",
                unit="KRW",
                explanation_data={
                    "minimum_cash_krw": worst.minimum_cash,
                    "minimum_cash_buffer_krw": minimum_buffer,
                    "buffer_shortfall_krw": (
                        worst.maximum_buffer_shortfall
                    ),
                    "first_shortfall_date": (
                        worst.first_buffer_shortfall_date or ""
                    ),
                },
            )
        )

    if cash_deficit > 0:
        findings.append(
            RiskFinding(
                risk_code="NEGATIVE_CASH_RISK",
                severity="CRITICAL",
                scenario_id=worst.scenario_name,
                trigger_value=str(cash_deficit),
                threshold="0",
                unit="KRW",
                explanation_data={
                    "cash_deficit_krw": worst.cash_deficit,
                    "ending_cash_krw": worst.ending_cash,
                },
            )
        )

    if payment_gap > 0:
        credit_limit = (
            stage2_input.credit_limit
            if stage2_input is not None
            else "미확인"
        )
        findings.append(
            RiskFinding(
                risk_code="PAYMENT_CAPACITY_RISK",
                severity="CRITICAL",
                scenario_id=worst.scenario_name,
                trigger_value=str(payment_gap),
                threshold="0",
                unit="KRW",
                explanation_data={
                    "payment_gap_krw": worst.post_credit_shortfall,
                    "cash_deficit_krw": worst.cash_deficit,
                    "usable_credit_limit_krw": credit_limit,
                },
            )
        )

    shortfall_date = worst.first_buffer_shortfall_date
    settlements = _settlement_dates(stage2_result)
    if shortfall_date and shortfall_date not in settlements:
        findings.append(
            RiskFinding(
                risk_code="TIMING_MISMATCH_RISK",
                severity="WARNING",
                scenario_id=worst.scenario_name,
                trigger_value=shortfall_date,
                threshold=min(settlements) if settlements else None,
                unit="DATE",
                explanation_data={
                    "first_shortfall_date": shortfall_date,
                    "settlement_dates": ",".join(settlements),
                },
            )
        )

    gaps = [
        item.strip()
        for item in (missing_information or [])
        if item and item.strip()
    ]
    if gaps:
        findings.append(
            RiskFinding(
                risk_code="DOCUMENT_INFORMATION_GAP",
                severity="WARNING",
                trigger_value=str(len(gaps)),
                threshold="0",
                unit="COUNT",
                explanation_data={
                    "missing_information": " | ".join(gaps),
                },
            )
        )

    unique_findings: List[RiskFinding] = []
    seen = set()
    for item in findings:
        key = _finding_key(item)
        if key not in seen:
            seen.add(key)
            unique_findings.append(item)

    return RiskAssessment(
        calculation_version=RISK_CLASSIFICATION_VERSION,
        status=_status(
            payment_gap=payment_gap,
            cash_deficit=cash_deficit,
            buffer_shortfall=buffer_shortfall,
            loss_limit_exceeded=loss_limit_exceeded,
        ),
        worst_scenario_id=worst.scenario_name,
        risk_codes=[
            item.risk_code for item in unique_findings
        ],
        findings=unique_findings,
    )
