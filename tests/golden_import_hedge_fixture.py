import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from schemas import TradeDocumentExtraction
from src.application.kb_macro_hedge_service import (
    SUPPORTED_PROVIDER_COMMIT_SHA,
    evaluate_kb_macro_hedge_reference,
)
from src.application.stage2_input_service import (
    Stage2FormInput,
    build_stage2_input_from_form,
    validate_stage2_as_of_date,
)
from src.config import Settings
from src.document_intake.confirmation import (
    create_confirmation_record,
    validate_confirmation,
)
from src.document_intake.source_evidence import extract_pdf_page_texts
from src.domain.stage1_models import ScenarioPoint, Stage1ScenarioSet
from src.security.upload_guard import validate_upload
from src.stage1.normalizer import normalize_stage1_scenarios
from src.stage2.engine import run_stage2
from src.stage3.optimizer import generate_strategy_candidates
from validators import (
    apply_deterministic_review_state,
    build_stage2_input,
)


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_IMPORT_DIR = ROOT / "dataset" / "golden_import_hedge_demo"
GOLDEN_IMPORT_PDF = (
    GOLDEN_IMPORT_DIR / "golden_import_payable_contract.pdf"
)
EXPECTED_EXTRACTION_PATH = (
    GOLDEN_IMPORT_DIR / "expected_extraction.json"
)
DEMO_INPUTS_PATH = GOLDEN_IMPORT_DIR / "demo_inputs.json"
KB_MACRO_FIXTURE_ROOT = (
    ROOT / "tests" / "fixtures" / "kb_macro_hedge_reference"
)
KB_MACRO_FORECAST = KB_MACRO_FIXTURE_ROOT / "forecast.json"
KB_MACRO_HEDGE = KB_MACRO_FIXTURE_ROOT / "hedge.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def kb_macro_fixture_settings() -> Settings:
    return Settings(
        enable_kb_macro_hedge_reference=True,
        kb_macro_hedge_mode="fixture",
        kb_macro_hedge_allowed_root=str(KB_MACRO_FIXTURE_ROOT),
        kb_macro_forecast_file=KB_MACRO_FORECAST.name,
        kb_macro_hedge_file=KB_MACRO_HEDGE.name,
        kb_macro_expected_provider_commit_sha=(
            SUPPORTED_PROVIDER_COMMIT_SHA
        ),
        kb_macro_expected_forecast_sha256=_sha256(
            KB_MACRO_FORECAST
        ),
        kb_macro_expected_hedge_sha256=_sha256(KB_MACRO_HEDGE),
        kb_macro_max_file_bytes=1024 * 1024,
    )


def build_golden_import_hedge_fixture() -> Dict[str, Any]:
    pdf_bytes = GOLDEN_IMPORT_PDF.read_bytes()
    upload = validate_upload(
        file_bytes=pdf_bytes,
        filename=GOLDEN_IMPORT_PDF.name,
        claimed_mime_type="application/pdf",
        settings=Settings(max_upload_mb=15, max_pdf_pages=20),
    )
    page_texts = extract_pdf_page_texts(pdf_bytes)
    expected = TradeDocumentExtraction.model_validate_json(
        EXPECTED_EXTRACTION_PATH.read_text(encoding="utf-8")
    )
    demo_inputs = json.loads(
        DEMO_INPUTS_PATH.read_text(encoding="utf-8")
    )

    raw_extraction = expected.model_copy(
        update={
            "seller_country": "United States (US)",
            "buyer_country": "Republic of Korea (KR)",
            "trade_type": "UNKNOWN",
        }
    )
    extraction, initial_validation = apply_deterministic_review_state(
        raw_extraction,
        company_role="BUYER",
        company_country="Republic of Korea (KR)",
        source_page_texts=page_texts,
    )
    confirmation = create_confirmation_record(
        original=raw_extraction,
        confirmed=extraction,
        confirmed_due_date=extraction.explicit_due_date,
        currency_confirmed=True,
        amount_due_confirmed=True,
        due_date_confirmed=True,
        source_filename=upload.filename,
        source_sha256=upload.sha256,
        company_country="KR",
        company_role_confirmed=True,
        trade_type_confirmed=True,
        confirmed_by="golden-import-hedge-fixture",
        confirmed_at="2026-07-29T09:00:00+09:00",
    )
    validation = validate_confirmation(
        extraction=extraction,
        record=confirmation,
        company_country="KR",
        source_page_texts=page_texts,
    )
    if not validation.stage2_allowed:
        raise ValueError(
            "Golden 수입 확정 거래가 Stage 2 gate를 통과하지 못했습니다."
        )
    document_input = build_stage2_input(
        extraction=extraction,
        validation=validation,
        confirmations=confirmation.checks,
        source_filename=upload.filename,
        source_sha256=upload.sha256,
        confirmed_at=confirmation.confirmed_at,
    )

    stage1_fixture = demo_inputs["stage1_fixture"]
    stage1 = normalize_stage1_scenarios(
        Stage1ScenarioSet(
            currency="USD",
            as_of="2026-07-29T09:00:00+09:00",
            target_date=stage1_fixture["target_date"],
            kind=stage1_fixture["kind"],
            scenarios=[
                ScenarioPoint(
                    name="BASE",
                    rate=stage1_fixture["base_rate"],
                    is_base=True,
                    source_kind="SPOT_BASE",
                ),
                ScenarioPoint(
                    name="UP_5",
                    rate=stage1_fixture["adverse_rate"],
                    source_kind="DETERMINISTIC_STRESS",
                ),
                ScenarioPoint(
                    name="UP_10",
                    rate=stage1_fixture["fixed_10_adverse_rate"],
                    source_kind="DETERMINISTIC_STRESS",
                ),
            ],
        ),
        expected_currency="USD",
        expected_target_date=stage1_fixture["target_date"],
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
            same_currency_flow_direction="INFLOW",
            existing_hedge_amount=finance["existing_forward_usd"],
            existing_hedge_rate=finance["existing_forward_rate"],
            existing_hedge_fee=finance["existing_forward_fee"],
            bank_spread_bps=finance["bank_spread_bps"],
            bank_fee=finance["bank_fee"],
            krw_cashflow_rows=finance["confirmed_krw_cashflows"],
        ),
    )
    validate_stage2_as_of_date(stage2_input)
    stage2 = run_stage2(stage2_input, stage1)
    stage3 = generate_strategy_candidates(stage2)
    kb_macro_reference = evaluate_kb_macro_hedge_reference(
        settings=kb_macro_fixture_settings(),
        stage2_input=stage2_input,
        stage2_result=stage2,
        binding_mode="CURRENT_CONFIRMED_TRADE",
        fixture_constraints_confirmed=True,
    )
    if kb_macro_reference is None:
        raise ValueError("외부 헤지 fixture 결과를 생성하지 못했습니다.")

    return {
        "pdf_bytes": pdf_bytes,
        "upload": upload,
        "page_texts": page_texts,
        "raw_extraction": raw_extraction,
        "extraction": extraction,
        "initial_validation": initial_validation,
        "confirmation": confirmation,
        "validation": validation,
        "document_input": document_input,
        "demo_inputs": demo_inputs,
        "stage1": stage1,
        "stage2_input": stage2_input,
        "stage2": stage2,
        "stage3": stage3,
        "kb_macro_reference": kb_macro_reference,
    }
