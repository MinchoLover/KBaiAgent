import json
from pathlib import Path
from typing import Any, Optional

from openai import OpenAI
from pydantic import ValidationError

from src.config import Settings
from src.country_environment.interpretation_fallback import (
    build_deterministic_interpretation,
)
from src.country_environment.interpretation_validator import (
    CountryEconomicInterpretationValidationError,
    validate_country_economic_interpretation,
)
from src.domain.country_economic_interpretation_models import (
    CountryEconomicInterpretationDraft,
    CountryEconomicInterpretationInput,
    CountryEconomicInterpretationResult,
    InterpretationFallbackReason,
)


PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "prompts"
    / "country_economic_interpretation.md"
)


def _result(
    *,
    interpretation_input: CountryEconomicInterpretationInput,
    draft: CountryEconomicInterpretationDraft,
    status: str,
    generation_model: Optional[str],
    fallback_reason: Optional[InterpretationFallbackReason],
) -> CountryEconomicInterpretationResult:
    return CountryEconomicInterpretationResult(
        prompt_version=interpretation_input.prompt_version,
        status=status,
        fallback_reason=fallback_reason,
        country_code=interpretation_input.country_code,
        trade_direction=(
            interpretation_input.transaction_context.trade_direction
        ),
        source_assessment_fingerprint=(
            interpretation_input.country_environment_snapshot_fingerprint
        ),
        confirmed_transaction_fingerprint=(
            interpretation_input.confirmed_transaction_fingerprint
        ),
        model_configuration_fingerprint=(
            interpretation_input.model_configuration_fingerprint
        ),
        input_fingerprint=interpretation_input.input_fingerprint,
        generation_model=generation_model,
        overall_summary=draft.overall_summary,
        sections=draft.sections,
        limitations=draft.limitations,
    )


def _fallback(
    *,
    interpretation_input: CountryEconomicInterpretationInput,
    reason: InterpretationFallbackReason,
) -> CountryEconomicInterpretationResult:
    draft = build_deterministic_interpretation(
        interpretation_input.indicators
    )
    validate_country_economic_interpretation(
        draft=draft,
        interpretation_input=interpretation_input,
    )
    return _result(
        interpretation_input=interpretation_input,
        draft=draft,
        status="DETERMINISTIC_FALLBACK",
        generation_model=None,
        fallback_reason=reason,
    )


def interpret_country_economic_environment(
    *,
    interpretation_input: CountryEconomicInterpretationInput,
    settings: Optional[Settings] = None,
    client: Optional[Any] = None,
) -> CountryEconomicInterpretationResult:
    effective_settings = settings or Settings.from_env()
    if not effective_settings.enable_country_economic_interpretation:
        return _fallback(
            interpretation_input=interpretation_input,
            reason="AI_DISABLED",
        )
    if not effective_settings.openai_api_key:
        return _fallback(
            interpretation_input=interpretation_input,
            reason="NO_API_KEY",
        )

    try:
        openai_client = client or OpenAI(
            api_key=effective_settings.openai_api_key,
            timeout=effective_settings.openai_timeout_seconds,
            max_retries=0,
        )
        response = openai_client.responses.parse(
            model=effective_settings.openai_model,
            input=[
                {
                    "role": "system",
                    "content": PROMPT_PATH.read_text(encoding="utf-8"),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        interpretation_input.model_dump(),
                        ensure_ascii=False,
                    ),
                },
            ],
            text_format=CountryEconomicInterpretationDraft,
            store=False,
            timeout=effective_settings.openai_timeout_seconds,
        )
        draft = response.output_parsed
        if draft is None:
            return _fallback(
                interpretation_input=interpretation_input,
                reason="PARSE_FAILURE",
            )
        validate_country_economic_interpretation(
            draft=draft,
            interpretation_input=interpretation_input,
        )
        return _result(
            interpretation_input=interpretation_input,
            draft=draft,
            status="AI_VALIDATED",
            generation_model=effective_settings.openai_model,
            fallback_reason=None,
        )
    except CountryEconomicInterpretationValidationError:
        return _fallback(
            interpretation_input=interpretation_input,
            reason="VALIDATION_FAILED",
        )
    except (ValidationError, json.JSONDecodeError):
        return _fallback(
            interpretation_input=interpretation_input,
            reason="PARSE_FAILURE",
        )
    except Exception:
        return _fallback(
            interpretation_input=interpretation_input,
            reason="API_FAILURE",
        )
