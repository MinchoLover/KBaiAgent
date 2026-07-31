from typing import List

from pydantic import Field

from schemas import StrictModel
from src.stage2.binding import validate_confirmed_transaction_snapshot
from src.workflow.state import WorkflowState


class GateDecision(StrictModel):
    allowed: bool
    reasons: List[str] = Field(default_factory=list)


def confirmation_gate(state: WorkflowState) -> GateDecision:
    reasons: List[str] = []
    if state.extracted_trade is None:
        reasons.append("추출된 거래정보가 없습니다.")
    if state.confirmation is None:
        reasons.append("사용자 확인 기록이 없습니다.")
    if state.confirmation_validation is None:
        reasons.append("확인 후 결정론 검증 결과가 없습니다.")
    elif not state.confirmation_validation.stage2_allowed:
        if state.confirmation_validation.missing_required_fields:
            reasons.append(
                "필수 필드 확인 필요: {}".format(
                    ", ".join(
                        state.confirmation_validation.missing_required_fields
                    )
                )
            )
        reasons.append("결정론 검증 gate가 열리지 않았습니다.")
    if state.confirmation is not None and not (
        state.confirmation.checks.all_critical_fields_confirmed(
            installment_schedule_confirmed=bool(
                state.extracted_trade
                and state.extracted_trade.installments
            )
        )
    ):
        reasons.append(
            "거래 방향·통화·금액·결제일 사용자 확인이 완료되지 않았습니다."
        )
    if state.confirmed_transaction is None:
        reasons.append("canonical confirmed transaction snapshot이 없습니다.")
    elif (
        state.extracted_trade is not None
        and state.confirmation is not None
        and state.confirmation_validation is not None
    ):
        try:
            validate_confirmed_transaction_snapshot(
                snapshot=state.confirmed_transaction,
                extraction=state.extracted_trade,
                validation=state.confirmation_validation,
                confirmation=state.confirmation,
            )
        except (TypeError, ValueError) as exc:
            reasons.append(
                "canonical confirmed transaction이 stale 상태입니다: "
                "{}".format(str(exc))
            )
    return GateDecision(allowed=not reasons, reasons=list(dict.fromkeys(reasons)))
