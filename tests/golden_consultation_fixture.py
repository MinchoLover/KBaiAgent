import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from schemas import TradeDocumentExtraction
from src.application.consultation_service import build_decision_support
from src.application.country_environment_service import (
    build_country_environment_input,
)
from src.consultation.trade_settlement_risk import (
    assess_trade_settlement_risk,
    create_trade_risk_confirmation,
)
from src.country_environment.assessment import (
    assess_country_trade_environment,
)
from src.document_intake.confirmation import create_confirmation_record
from src.domain.consultation_models import InstallmentPaymentStatus
from src.domain.stage1_models import ScenarioPoint, Stage1ScenarioSet
from src.domain.stage2_models import (
    ExposureInput,
    KrwCashflowEvent,
    Stage2Input,
)
from src.domain.trade_risk_models import TradeSettlementRiskInput
from src.stage1.normalizer import normalize_stage1_scenarios
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
    stage2_input = Stage2Input(
        confirmed_trade_sha256=source_sha256,
        as_of_date=finance["as_of_date"],
        exposures=[
            ExposureInput(
                sequence=1,
                trade_type="EXPORT",
                currency="USD",
                foreign_amount=extraction.amount_due,
                settlement_date=extraction.explicit_due_date,
                usable_fx_balance=finance["usable_fx_balance"],
                same_currency_flows=[],
            )
        ],
        current_krw_cash=finance["current_krw_cash"],
        minimum_cash_buffer=finance["minimum_cash_buffer"],
        credit_limit=finance["credit_limit"],
        acceptable_fx_loss=finance["acceptable_fx_loss"],
        krw_cashflows=[
            KrwCashflowEvent.model_validate(item)
            for item in finance["confirmed_krw_cashflows"]
        ],
        bank_spread_bps=finance["bank_spread_bps"],
        bank_fee=finance["bank_fee"],
    )
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
    country_environment = assess_country_trade_environment(
        build_country_environment_input(
            extraction=extraction,
            trade_risk_confirmation=trade_confirmation,
        )
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
        installment_payment_statuses=(
            [payment_status] if payment_status is not None else None
        ),
        generated_at="2026-07-29T09:00:00+09:00",
    )
    return {
        "extraction": extraction,
        "demo_inputs": demo_inputs,
        "confirmation": confirmation,
        "stage1": stage1,
        "stage2_input": stage2_input,
        "stage2": stage2,
        "trade_risk": trade_risk,
        "country_environment": country_environment,
        "decision": decision,
    }
