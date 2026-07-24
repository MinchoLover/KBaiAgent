import hashlib
from pathlib import Path
from typing import Any, Dict

from sample_data import sample_extraction
from src.config import Settings
from src.document_intake.confirmation import (
    create_confirmation_record,
    validate_confirmation,
)
from src.domain.stage2_models import (
    CompositeStress,
    ExposureInput,
    KrwCashflowEvent,
    Stage2Input,
)
from src.stage1.adapter import load_stage1
from src.stage2.engine import run_stage2
from src.stage3.optimizer import generate_strategy_candidates
from src.stage4.local_kb import search_offline_kb
from src.stage5.report_agent import generate_report


def run_offline_demo() -> Dict[str, Any]:
    extraction = sample_extraction("BUYER")
    confirmed_due_date = "2026-10-18"
    sample_path = (
        Path(__file__).resolve().parents[1]
        / "samples"
        / "sample_invoice.png"
    )
    record = create_confirmation_record(
        original=extraction,
        confirmed=extraction,
        confirmed_due_date=confirmed_due_date,
        currency_confirmed=True,
        amount_due_confirmed=True,
        due_date_confirmed=True,
        source_filename="sample_invoice.png",
        source_sha256=hashlib.sha256(sample_path.read_bytes()).hexdigest(),
        company_country="KR",
        confirmed_by="offline-demo",
        confirmed_at="2026-07-23T09:00:00+09:00",
    )
    validation = validate_confirmation(
        extraction=extraction,
        record=record,
        company_country="KR",
    )
    if not validation.stage2_allowed:
        raise RuntimeError("offline demo confirmation gate failed")

    stage1 = load_stage1(
        expected_currency="USD",
        expected_target_date=confirmed_due_date,
        manual_base_rate="1400",
        mode="MANUAL_STRESS",
    ).scenario_set
    stage2_input = Stage2Input(
        as_of_date="2026-07-23",
        exposures=[
            ExposureInput(
                sequence=1,
                trade_type="IMPORT",
                currency="USD",
                foreign_amount="100000.00",
                settlement_date=confirmed_due_date,
                usable_fx_balance="10000.00",
                same_currency_flows=[],
            )
        ],
        current_krw_cash="200000000",
        minimum_cash_buffer="50000000",
        credit_limit="30000000",
        acceptable_fx_loss="10000000",
        krw_cashflows=[
            KrwCashflowEvent(
                date="2026-08-31",
                amount="30000000",
                direction="INFLOW",
                category="REVENUE",
                description="예정 매출 입금",
            ),
            KrwCashflowEvent(
                date="2026-09-30",
                amount="20000000",
                direction="OUTFLOW",
                category="COST",
                description="예정 운영비",
            ),
        ],
        bank_spread_bps="15",
        bank_fee="50000",
        composite_stress=CompositeStress(),
    )
    stage2 = run_stage2(stage2_input, stage1)
    stage3 = generate_strategy_candidates(stage2)
    product_query = " ".join(
        stage3.candidates[0].required_product_types
        + [
            "선물환",
            "환변동보험",
            "외화예금",
            "수출입대출",
            "정책자금",
            "보증상품",
        ]
    )
    stage4 = search_offline_kb(
        query=product_query,
        trade_type=stage2.trade_type,
    )
    report = generate_report(
        extraction=extraction,
        confirmation=record,
        stage1=stage1,
        stage2=stage2,
        stage3=stage3,
        stage4=stage4,
        settings=Settings(),
    )
    return {
        "extraction": extraction,
        "confirmation": record,
        "validation": validation,
        "stage1": stage1,
        "stage2_input": stage2_input,
        "stage2": stage2,
        "stage3": stage3,
        "stage4": stage4,
        "report": report,
    }
