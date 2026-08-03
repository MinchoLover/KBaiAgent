import json
from typing import Any, List, Optional

from openai import OpenAI
from pydantic import ValidationError

from schemas import TradeDocumentExtraction
from src.config import Settings
from src.document_intake.confirmation import ConfirmationRecord
from src.domain.consultation_models import ConsultationPacket
from src.domain.confirmed_transaction_models import (
    ConfirmedTransactionSnapshot,
)
from src.domain.product_models import Stage4Result
from src.domain.report_models import (
    ReportResult,
    Stage5NarrativeDraft,
)
from src.domain.stage1_models import NormalizedScenarioSet
from src.domain.stage1_web_models import MarketIntegrationResult
from src.domain.stage2_models import Stage2Result
from src.domain.stage3_models import Stage3Result
from src.stage5.critic import critique_report
from src.stage5.deterministic_fallback import (
    build_report_source_bundle,
    generate_deterministic_report,
)
from src.stage5.grounding import (
    Stage5NarrativeValidationError,
    build_grounding_registry,
    build_narrative_prompt,
    render_grounded_narratives,
    validate_narrative_draft,
)


REPORT_INSTRUCTIONS = """
당신은 KBaiAgent 결정론 보고서에 삽입할 짧은 한국어 설명만 작성한다.
응답은 Stage5NarrativeDraft 구조를 정확히 따른다.
사용자 입력의 required_source_id_order에 있는 source_id를 같은 순서로 정확히 한 번씩
사용하고, 목록에 없는 source_id를 만들지 않는다.
숫자, 날짜, 통화, 비율, 순위, 국가코드, JSON path, source tag, Markdown을 쓰지 않는다.
상담 분야명, priority category, 상품명, 기관명, catalogue ID, URL을 쓰지 않는다.
승인·가입·대출·보험 인수 가능성, 최적 상품, 위험국가, 부도 가능성을 단정하지 않는다.
각 explanation은 제공된 scope의 의미와 상담에서 확인할 점을 한두 문장으로만 설명한다.
결정론 값·순위·상품·섹션은 코드가 렌더링하므로 이를 반복하거나 바꾸지 않는다.
""".strip()


def _critic_fallback(
    *,
    fallback: ReportResult,
    revision_count: int,
) -> ReportResult:
    return fallback.model_copy(
        update={
            "warnings": fallback.warnings
            + ["LLM 설명 계약 또는 최종 critic 검증 실패로 fallback했습니다."],
            "revision_count": revision_count,
            "fallback_reason": "CRITIC_REJECTED",
        }
    )


def _api_fallback(
    *,
    fallback: ReportResult,
    revision_count: int,
) -> ReportResult:
    return fallback.model_copy(
        update={
            "warnings": fallback.warnings
            + ["LLM 보고서 호출 실패로 fallback했습니다."],
            "revision_count": revision_count,
            "fallback_reason": "API_FAILURE",
        }
    )


def generate_report(
    *,
    extraction: TradeDocumentExtraction,
    confirmation: ConfirmationRecord,
    stage1: NormalizedScenarioSet,
    stage2: Stage2Result,
    stage3: Stage3Result,
    stage4: Stage4Result,
    market_integration: Optional[MarketIntegrationResult] = None,
    consultation_packet: Optional[ConsultationPacket] = None,
    confirmed_transaction: Optional[
        ConfirmedTransactionSnapshot
    ] = None,
    settings: Optional[Settings] = None,
    client: Optional[Any] = None,
    max_revisions: int = 1,
) -> ReportResult:
    if max_revisions not in {0, 1}:
        raise ValueError("보고서 재작성 횟수는 0 또는 1이어야 합니다.")

    effective_settings = settings or Settings.from_env()
    fallback = generate_deterministic_report(
        extraction=extraction,
        confirmation=confirmation,
        stage1=stage1,
        stage2=stage2,
        stage3=stage3,
        stage4=stage4,
        market_integration=market_integration,
        consultation_packet=consultation_packet,
        confirmed_transaction=confirmed_transaction,
    )
    authoritative_candidates = (
        (
            consultation_packet.official_candidate_shortlist.candidates
            if (
                consultation_packet.official_candidate_shortlist
                is not None
            )
            else []
        )
        if consultation_packet is not None
        else stage4.candidates
    )
    if not authoritative_candidates:
        return fallback.model_copy(
            update={
                "warnings": fallback.warnings
                + [
                    "상담 항목과 직접 연결된 공식 후보가 없어 LLM 상품 "
                    "생성을 차단하고 결정론 보고서를 사용했습니다."
                ],
                "fallback_reason": "DETERMINISTIC_POLICY",
                "revision_count": 0,
            }
        )
    if not effective_settings.enable_llm_report:
        return fallback.model_copy(
            update={
                "warnings": fallback.warnings
                + ["ENABLE_LLM_REPORT=false로 결정론 보고서를 사용했습니다."],
                "fallback_reason": "DETERMINISTIC_POLICY",
                "revision_count": 0,
            }
        )
    if not effective_settings.openai_api_key:
        return fallback.model_copy(
            update={
                "fallback_reason": "NO_API_KEY",
                "revision_count": 0,
            }
        )

    bundle = build_report_source_bundle(
        extraction=extraction,
        confirmation=confirmation,
        stage1=stage1,
        stage2=stage2,
        stage3=stage3,
        stage4=stage4,
        market_integration=market_integration,
        consultation_packet=consultation_packet,
        confirmed_transaction=confirmed_transaction,
    )
    registry = build_grounding_registry(bundle)
    openai_client = client or OpenAI(
        api_key=effective_settings.openai_api_key,
        timeout=effective_settings.openai_timeout_seconds,
        max_retries=0,
    )
    validation_feedback: List[str] = []
    revision_count = 0
    for attempt in range(max_revisions + 1):
        try:
            response = openai_client.responses.parse(
                model=effective_settings.openai_report_model,
                input=[
                    {
                        "role": "system",
                        "content": REPORT_INSTRUCTIONS,
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            build_narrative_prompt(
                                registry,
                                validation_feedback,
                            ),
                            ensure_ascii=False,
                        ),
                    },
                ],
                text_format=Stage5NarrativeDraft,
                store=False,
                timeout=effective_settings.openai_timeout_seconds,
            )
        except Exception:
            return _api_fallback(
                fallback=fallback,
                revision_count=revision_count,
            )

        parsed = response.output_parsed
        try:
            if parsed is None:
                raise Stage5NarrativeValidationError(
                    "구조화 설명 응답이 비어 있습니다."
                )
            draft = (
                parsed
                if isinstance(parsed, Stage5NarrativeDraft)
                else Stage5NarrativeDraft.model_validate(parsed)
            )
            validate_narrative_draft(
                draft=draft,
                registry=registry,
                source_bundle=bundle,
            )
            markdown = render_grounded_narratives(
                deterministic_markdown=fallback.markdown,
                draft=draft,
                registry=registry,
            )
            critique = critique_report(
                markdown=markdown,
                source_bundle=bundle,
                scenario_kind=stage1.kind,
                probability_valid=stage1.probability_valid,
            )
        except (Stage5NarrativeValidationError, ValidationError, ValueError) as exc:
            validation_feedback = [str(exc)]
        else:
            if critique.passed:
                return ReportResult(
                    status=(
                        "LLM_PASS"
                        if attempt == 0
                        else "LLM_REVISED_PASS"
                    ),
                    markdown=markdown,
                    report_json=bundle,
                    critique=critique,
                    generation_provider="OPENAI",
                    revision_count=attempt,
                    fallback_reason=None,
                )
            validation_feedback = critique.revision_instructions

        if attempt >= max_revisions:
            return _critic_fallback(
                fallback=fallback,
                revision_count=revision_count,
            )
        revision_count = 1

    return _critic_fallback(
        fallback=fallback,
        revision_count=revision_count,
    )
