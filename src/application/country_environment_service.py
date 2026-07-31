from schemas import TradeDocumentExtraction
from src.country_environment.assessment import (
    assess_country_trade_environment,
)
from src.domain.country_environment_models import (
    CountryTradeEnvironmentAssessment,
    CountryTradeEnvironmentInput,
)
from src.domain.trade_risk_models import TradeRiskConfirmationRecord


def build_country_environment_input(
    *,
    extraction: TradeDocumentExtraction,
    trade_risk_confirmation: TradeRiskConfirmationRecord,
) -> CountryTradeEnvironmentInput:
    risk_input = trade_risk_confirmation.confirmed_input
    if extraction.trade_type != risk_input.trade_type:
        raise ValueError(
            "확정 문서와 거래·결제조건의 거래 방향이 일치하지 않습니다."
        )
    counterparty_country = (
        extraction.seller_country
        if risk_input.trade_type == "IMPORT"
        else extraction.buyer_country
    )
    if not counterparty_country:
        raise ValueError("사용자가 확인한 거래 상대국이 필요합니다.")
    if not extraction.currency:
        raise ValueError("사용자가 확인한 거래 통화가 필요합니다.")
    return CountryTradeEnvironmentInput(
        confirmed_trade_sha256=risk_input.confirmed_trade_sha256,
        country_confirmation_status="USER_CONFIRMED",
        trade_type=risk_input.trade_type,
        counterparty_country=counterparty_country,
        currency=extraction.currency,
        counterparty_relationship=risk_input.counterparty_relationship,
        balance_payment_method=risk_input.balance_payment_method,
        payment_term_days=risk_input.payment_term_days,
        protection_information_status=(
            risk_input.protection_information_status
        ),
        protection_mechanisms=risk_input.protection_mechanisms,
    )


def assess_confirmed_country_environment(
    *,
    extraction: TradeDocumentExtraction,
    trade_risk_confirmation: TradeRiskConfirmationRecord,
) -> CountryTradeEnvironmentAssessment:
    value = build_country_environment_input(
        extraction=extraction,
        trade_risk_confirmation=trade_risk_confirmation,
    )
    return assess_country_trade_environment(value)
