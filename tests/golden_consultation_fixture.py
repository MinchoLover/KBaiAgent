import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from schemas import TradeDocumentExtraction
from src.application.consultation_service import build_decision_support
from src.application.country_environment_service import (
    build_country_environment_input,
)
from src.application.stage2_input_service import (
    Stage2FormInput,
    build_stage2_input_from_form,
    validate_stage2_as_of_date,
)
from src.application.trade_statistics_service import (
    build_trade_statistics_request,
    retrieve_trade_statistics,
)
from src.consultation.trade_settlement_risk import (
    assess_trade_settlement_risk,
    create_trade_risk_confirmation,
)
from src.country_environment.assessment import (
    assess_country_trade_environment,
)
from src.document_intake.confirmation import (
    create_confirmation_record,
    validate_confirmation,
)
from src.document_intake.source_evidence import extract_pdf_page_texts
from src.domain.consultation_models import InstallmentPaymentStatus
from src.domain.stage1_models import ScenarioPoint, Stage1ScenarioSet
from src.domain.trade_risk_models import TradeSettlementRiskInput
from src.stage1.normalizer import normalize_stage1_scenarios
from src.stage2.binding import (
    confirmed_transaction_from_confirmation,
    document_input_from_confirmed_transaction,
)
from src.stage2.engine import run_stage2


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "dataset" / "golden_demo"


def build_golden_consultation_fixture(
    *,
    payment_status: Optional[InstallmentPaymentStatus] = None,
) -> Dict[str, Any]:
    extraction = TradeDocumentExtraction.model_validate_json(
        (GOLDEN_DIR / "expected_extraction.json").read_text(
            encoding="utf-8"
        )
    )
    demo_inputs = json.loads(
        (GOLDEN_DIR / "demo_inputs.json").read_text(encoding="utf-8")
    )
    pdf_path = GOLDEN_DIR / "golden_export_contract.pdf"
    source_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    confirmation = create_confirmation_record(
        original=extraction,
        confirmed=extraction,
        confirmed_due_date=extraction.explicit_due_date,
        currency_confirmed=True,
        amount_due_confirmed=True,
        due_date_confirmed=True,
        source_filename=pdf_path.name,
        source_sha256=source_sha256,
        company_country="KR",
        company_role_confirmed=True,
        trade_type_confirmed=True,
        confirmed_by="golden-consultation-fixture",
        confirmed_at="2026-07-29T09:00:00+09:00",
    )
    validation = validate_confirmation(
        extraction=extraction,
        record=confirmation,
        company_country="KR",
        source_page_texts=extract_pdf_page_texts(pdf_path.read_bytes()),
    )
    if not validation.stage2_allowed:
        raise ValueError("Golden 확정 거래가 Stage 2 gate를 통과하지 못했습니다.")
    confirmed_transaction = confirmed_transaction_from_confirmation(
        extraction=extraction,
        validation=validation,
        confirmation=confirmation,
    )
    document_input = document_input_from_confirmed_transaction(
        confirmed_transaction
    )
    stage1 = normalize_stage1_scenarios(
        Stage1ScenarioSet(
            currency="USD",
            as_of="2026-07-29T09:00:00+09:00",
            target_date="2026-08-20",
            kind="STRESS",
            scenarios=[
                ScenarioPoint(
                    name="BASE",
                    rate="1400.00",
                    is_base=True,
                    source_kind="SPOT_BASE",
                ),
                ScenarioPoint(
                    name="DOWN_5",
                    rate="1330.00",
                    source_kind="DETERMINISTIC_STRESS",
                ),
            ],
        ),
        expected_currency="USD",
        expected_target_date="2026-08-20",
    )
    finance = demo_inputs["company_finance_manual_inputs"]
    stage2_input = build_stage2_input_from_form(
        document_input=document_input,
        form=Stage2FormInput(
            as_of_date=finance["as_of_date"],
            current_krw_cash=finance["current_krw_cash"],
            minimum_cash_buffer=finance["minimum_cash_buffer"],
            credit_limit=finance["credit_limit"],
            usable_fx_balance=finance["usable_fx_balance"],
            acceptable_fx_loss=finance["acceptable_fx_loss"],
            same_currency_flow_amount="0",
            same_currency_flow_date=finance["as_of_date"],
            same_currency_flow_direction="OUTFLOW",
            existing_hedge_amount="0",
            existing_hedge_rate="1400",
            existing_hedge_fee="0",
            bank_spread_bps=finance["bank_spread_bps"],
            bank_fee=finance["bank_fee"],
            krw_cashflow_rows=finance["confirmed_krw_cashflows"],
        ),
    )
    validate_stage2_as_of_date(stage2_input)
    stage2 = run_stage2(stage2_input, stage1)
    trade_input = TradeSettlementRiskInput(
        confirmed_trade_sha256=source_sha256,
        trade_type="EXPORT",
        **demo_inputs["user_confirmed_trade_inputs"],
    )
    trade_confirmation = create_trade_risk_confirmation(
        confirmed_input=trade_input,
        confirmed_by="golden-consultation-fixture",
        confirmed_at="2026-07-29T09:00:00+09:00",
    )
    trade_risk = assess_trade_settlement_risk(trade_confirmation)
    country_environment_input = build_country_environment_input(
        extraction=extraction,
        trade_risk_confirmation=trade_confirmation,
    )
    country_environment = assess_country_trade_environment(
        country_environment_input
    )
    trade_statistics_request = build_trade_statistics_request(
        confirmed_transaction=confirmed_transaction,
        source_preference="OFFICIAL_FIXTURE",
    )
    trade_statistics = retrieve_trade_statistics(
        trade_statistics_request
    )
    decision = build_decision_support(
        case_id="golden_export_br_001",
        extraction=extraction,
        confirmation=confirmation,
        stage1=stage1,
        stage2_input=stage2_input,
        stage2_result=stage2,
        trade_settlement_risk=trade_risk,
        country_environment=country_environment,
        trade_statistics=trade_statistics,
        installment_payment_statuses=(
            [payment_status] if payment_status is not None else None
        ),
        generated_at="2026-07-29T09:00:00+09:00",
        confirmed_transaction=confirmed_transaction,
    )
    return {
        "extraction": extraction,
        "demo_inputs": demo_inputs,
        "confirmation": confirmation,
        "confirmed_transaction": confirmed_transaction,
        "validation": validation,
        "document_input": document_input,
        "stage1": stage1,
        "stage2_input": stage2_input,
        "stage2": stage2,
        "trade_risk": trade_risk,
        "country_environment_input": country_environment_input,
        "country_environment": country_environment,
        "trade_statistics_request": trade_statistics_request,
        "trade_statistics": trade_statistics,
        "decision": decision,
    }
