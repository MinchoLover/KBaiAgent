import hashlib
import json
from typing import Dict, List, Optional

from src.config import Settings
from src.domain.confirmed_transaction_models import (
    ConfirmedTransactionSnapshot,
)
from src.domain.country_economic_interpretation_models import (
    CountryEconomicIndicatorInput,
    CountryEconomicInterpretationInput,
    CountryEconomicSourceReference,
    CountryEconomicTransactionContext,
)
from src.domain.country_environment_models import (
    CountryTradeEnvironmentAssessment,
    CountryTradeEnvironmentInput,
    OfficialSourceReference,
)


COUNTRY_ECONOMIC_INTERPRETATION_SCHEMA_VERSION = "1.0"
COUNTRY_ECONOMIC_INTERPRETATION_PROMPT_VERSION = "country-economy-ko-1.0"
COUNTRY_NAMES = {
    "BR": "브라질",
    "US": "미국",
}
WORLD_BANK_INDICATOR_IDS = {
    "NY.GDP.MKTP.KD.ZG": "GDP_GROWTH",
    "FP.CPI.TOTL.ZG": "INFLATION",
    "BN.CAB.XOKA.GD.ZS": "CURRENT_ACCOUNT",
}


def model_configuration_fingerprint(settings: Settings) -> str:
    payload = {
        "model": settings.openai_model,
        "timeout_seconds": str(settings.openai_timeout_seconds),
        "feature_enabled": settings.enable_country_economic_interpretation,
        "schema_version": COUNTRY_ECONOMIC_INTERPRETATION_SCHEMA_VERSION,
        "prompt_version": COUNTRY_ECONOMIC_INTERPRETATION_PROMPT_VERSION,
    }
    return _fingerprint(payload)


def _fingerprint(payload: Dict[str, object]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _source(
    reference: OfficialSourceReference,
) -> CountryEconomicSourceReference:
    return CountryEconomicSourceReference(**reference.model_dump())


def _reference_map(
    assessment: CountryTradeEnvironmentAssessment,
) -> Dict[str, OfficialSourceReference]:
    return {
        item.source_record_id: item
        for item in assessment.official_source_references
    }


def _protection_status(
    *,
    country_input: CountryTradeEnvironmentInput,
    protection_types: List[str],
) -> Dict[str, str]:
    if country_input.protection_information_status == "UNKNOWN":
        default = "UNKNOWN"
    elif country_input.protection_information_status == "NONE_CONFIRMED":
        default = "NONE_CONFIRMED"
    else:
        default = "NOT_PRESENT_IN_CONFIRMED_DETAILS"
    documentary_credit = (
        "PRESENT_CONFIRMED"
        if (
            country_input.balance_payment_method == "DOCUMENTARY_CREDIT"
            or "STANDBY_LETTER_OF_CREDIT" in protection_types
        )
        else default
    )
    insurance = (
        "PRESENT_CONFIRMED"
        if "EXPORT_CREDIT_INSURANCE" in protection_types
        else default
    )
    guarantee = (
        "PRESENT_CONFIRMED"
        if any(
            item
            in {
                "ADVANCE_PAYMENT_GUARANTEE",
                "PERFORMANCE_GUARANTEE",
                "PAYMENT_GUARANTEE",
            }
            for item in protection_types
        )
        else default
    )
    return {
        "documentary_credit_status": documentary_credit,
        "insurance_status": insurance,
        "guarantee_status": guarantee,
    }


def _expected_partner(
    confirmed_transaction: ConfirmedTransactionSnapshot,
) -> Optional[str]:
    if confirmed_transaction.trade_type == "EXPORT":
        return confirmed_transaction.buyer_country
    return confirmed_transaction.seller_country


def build_country_economic_interpretation_input(
    *,
    assessment: CountryTradeEnvironmentAssessment,
    country_input: CountryTradeEnvironmentInput,
    confirmed_transaction: ConfirmedTransactionSnapshot,
    settings: Settings,
) -> CountryEconomicInterpretationInput:
    if assessment.input_fingerprint != country_input_fingerprint(
        assessment=assessment,
        country_input=country_input,
    ):
        raise ValueError("국가환경 assessment와 확인 입력이 일치하지 않습니다.")
    if (
        assessment.country != country_input.counterparty_country
        or assessment.trade_type != country_input.trade_type
        or assessment.trade_type != confirmed_transaction.trade_type
        or assessment.country != _expected_partner(confirmed_transaction)
        or country_input.confirmed_trade_sha256
        not in {
            confirmed_transaction.source_sha256,
            confirmed_transaction.trade_binding.trade_sha256,
        }
    ):
        raise ValueError("국가환경 해석의 확정 거래 맥락이 일치하지 않습니다.")

    references = _reference_map(assessment)
    indicators: List[CountryEconomicIndicatorInput] = []
    for observation in assessment.world_bank_macro_environment.observations:
        indicator_id = WORLD_BANK_INDICATOR_IDS.get(
            observation.indicator_code
        )
        reference = references.get(observation.source_record_id)
        if indicator_id is None or reference is None:
            continue
        indicators.append(
            CountryEconomicIndicatorInput(
                indicator_id=indicator_id,
                deterministic_value=observation.raw_value,
                deterministic_status=observation.raw_status,
                unit=observation.raw_unit,
                period=observation.observation_period,
                as_of=observation.as_of_date,
                source=_source(reference),
            )
        )
    oecd = assessment.oecd_payment_transfer
    oecd_reference = references.get(oecd.source_record_id or "")
    if oecd_reference is not None:
        indicators.append(
            CountryEconomicIndicatorInput(
                indicator_id="OECD_CLASSIFICATION",
                deterministic_value=(
                    str(oecd.raw_classification)
                    if oecd.raw_classification is not None
                    else None
                ),
                deterministic_status=oecd.status,
                unit=oecd.raw_unit,
                period=oecd_reference.observation_period,
                as_of=oecd.as_of_date,
                source=_source(oecd_reference),
            )
        )
    indicator_order = {
        "GDP_GROWTH": 0,
        "INFLATION": 1,
        "CURRENT_ACCOUNT": 2,
        "OECD_CLASSIFICATION": 3,
    }
    indicators = sorted(
        indicators,
        key=lambda item: indicator_order[item.indicator_id],
    )
    if not indicators:
        raise ValueError("해석할 검증 완료 국가 경제지표가 없습니다.")

    configured_fingerprint = model_configuration_fingerprint(settings)
    protection_types = [
        item.protection_type for item in country_input.protection_mechanisms
    ]
    context = CountryEconomicTransactionContext(
        trade_direction=country_input.trade_type,
        payment_method=country_input.balance_payment_method,
        **_protection_status(
            country_input=country_input,
            protection_types=protection_types,
        ),
    )
    canonical: Dict[str, object] = {
        "schema_version": COUNTRY_ECONOMIC_INTERPRETATION_SCHEMA_VERSION,
        "prompt_version": COUNTRY_ECONOMIC_INTERPRETATION_PROMPT_VERSION,
        "country_code": assessment.country,
        "country_name": COUNTRY_NAMES.get(assessment.country, assessment.country),
        "country_environment_snapshot_fingerprint": assessment.input_fingerprint,
        "country_environment_snapshot_hash": assessment.snapshot_hash,
        "confirmed_transaction_fingerprint": confirmed_transaction.input_fingerprint,
        "model_configuration_fingerprint": configured_fingerprint,
        "transaction_context": context.model_dump(),
        "indicators": [item.model_dump() for item in indicators],
    }
    return CountryEconomicInterpretationInput(
        **canonical,
        input_fingerprint=_fingerprint(canonical),
    )


def country_input_fingerprint(
    *,
    assessment: CountryTradeEnvironmentAssessment,
    country_input: CountryTradeEnvironmentInput,
) -> str:
    """Return the current assessment fingerprint after strict input binding.

    The assessment module owns fingerprint construction. Re-assessment is the
    only safe way to verify that the top-level input and assessment still bind.
    """
    from src.country_environment.assessment import (
        assess_country_trade_environment,
    )

    rebuilt = assess_country_trade_environment(country_input)
    if (
        rebuilt.snapshot_hash != assessment.snapshot_hash
        or rebuilt.snapshot_version != assessment.snapshot_version
    ):
        return ""
    return rebuilt.input_fingerprint
