import json
from pathlib import Path
from typing import Any, Optional

from openai import OpenAI
from pydantic import ValidationError

from src.config import Settings
from src.domain.trade_statistics_interpretation_models import (
    TradeStatisticsInterpretationDraft,
    TradeStatisticsInterpretationFallbackReason,
    TradeStatisticsInterpretationInput,
    TradeStatisticsInterpretationResult,
)
from src.trade_statistics.interpretation_fallback import (
    build_trade_statistics_fallback,
)
from src.trade_statistics.interpretation_validator import (
    TradeStatisticsInterpretationValidationError,
    validate_trade_statistics_interpretation,
)


PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "prompts"
    / "trade_statistics_interpretation.md"
)


def _result(
    *,
    interpretation_input: TradeStatisticsInterpretationInput,
    draft: TradeStatisticsInterpretationDraft,
    status: str,
    generation_model: Optional[str],
    fallback_reason: Optional[
        TradeStatisticsInterpretationFallbackReason
    ],
) -> TradeStatisticsInterpretationResult:
    return TradeStatisticsInterpretationResult(
        prompt_version=interpretation_input.prompt_version,
        status=status,
        fallback_reason=fallback_reason,
        reporting_country_code=interpretation_input.reporting_country_code,
        partner_country_code=interpretation_input.partner_country_code,
        trade_direction=interpretation_input.trade_direction,
        export_change_direction=(
            interpretation_input.export_change_direction
        ),
        source_result_fingerprint=(
            interpretation_input.trade_statistics_result_fingerprint
        ),
        normalized_snapshot_fingerprint=(
            interpretation_input.normalized_snapshot_fingerprint
        ),
        confirmed_transaction_fingerprint=(
            interpretation_input.confirmed_transaction_fingerprint
        ),
        model_configuration_fingerprint=(
            interpretation_input.model_configuration_fingerprint
        ),
        input_fingerprint=interpretation_input.input_fingerprint,
        generation_model=generation_model,
        summary=draft.summary,
        limitation=draft.limitation,
    )


def _fallback(
    *,
    interpretation_input: TradeStatisticsInterpretationInput,
    reason: TradeStatisticsInterpretationFallbackReason,
) -> TradeStatisticsInterpretationResult:
    draft = build_trade_statistics_fallback(
        interpretation_input.export_change_direction
    )
    validate_trade_statistics_interpretation(
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


def interpret_trade_statistics(
    *,
    interpretation_input: TradeStatisticsInterpretationInput,
    settings: Optional[Settings] = None,
    client: Optional[Any] = None,
) -> TradeStatisticsInterpretationResult:
    effective_settings = settings or Settings.from_env()
    if interpretation_input.export_change_direction == "UNAVAILABLE":
        return _fallback(
            interpretation_input=interpretation_input,
            reason="DATA_UNAVAILABLE",
        )
    if not effective_settings.enable_trade_statistics_interpretation:
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
            text_format=TradeStatisticsInterpretationDraft,
            store=False,
            timeout=effective_settings.openai_timeout_seconds,
        )
        draft = response.output_parsed
        if draft is None:
            return _fallback(
                interpretation_input=interpretation_input,
                reason="PARSE_FAILURE",
            )
        validate_trade_statistics_interpretation(
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
    except TradeStatisticsInterpretationValidationError:
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
