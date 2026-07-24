import json
from typing import Any, Optional

from openai import OpenAI

from schemas import TradeDocumentExtraction
from src.config import Settings
from src.document_intake.confirmation import ConfirmationRecord
from src.domain.product_models import Stage4Result
from src.domain.report_models import ReportResult
from src.domain.stage1_models import NormalizedScenarioSet
from src.domain.stage2_models import Stage2Result
from src.domain.stage3_models import Stage3Result
from src.stage5.critic import critique_report
from src.stage5.deterministic_fallback import (
    build_report_source_bundle,
    generate_deterministic_report,
)


REPORT_INSTRUCTIONS = """
제공된 JSON의 숫자를 절대 재계산하거나 수정하지 말고 한국어 보고서를 작성하라.
각 핵심 숫자 뒤에 [source: JSON.path]를 표시하라.
STRESS를 예측이라 부르지 말고, probability_valid=false이면 확률을 만들지 마라.
상품은 후보/상담 필요로 표현하고 승인·수익·손실회피를 보장하지 마라.
보고서 섹션은 거래 요약, 데이터 출처, 시나리오 성격, 현금흐름 영향,
위험 경보, 전략 후보, 상품 후보와 출처, 추가 정보, 상담 질문, 면책 순서다.
""".strip()


def generate_report(
    *,
    extraction: TradeDocumentExtraction,
    confirmation: ConfirmationRecord,
    stage1: NormalizedScenarioSet,
    stage2: Stage2Result,
    stage3: Stage3Result,
    stage4: Stage4Result,
    settings: Optional[Settings] = None,
    client: Optional[Any] = None,
) -> ReportResult:
    effective_settings = settings or Settings.from_env()
    fallback = generate_deterministic_report(
        extraction=extraction,
        confirmation=confirmation,
        stage1=stage1,
        stage2=stage2,
        stage3=stage3,
        stage4=stage4,
    )
    if not effective_settings.openai_api_key:
        return fallback

    bundle = build_report_source_bundle(
        extraction=extraction,
        confirmation=confirmation,
        stage1=stage1,
        stage2=stage2,
        stage3=stage3,
        stage4=stage4,
    )
    openai_client = client or OpenAI(
        api_key=effective_settings.openai_api_key,
        timeout=effective_settings.openai_timeout_seconds,
        max_retries=0,
    )
    try:
        response = openai_client.responses.create(
            model=effective_settings.openai_report_model,
            instructions=REPORT_INSTRUCTIONS,
            input=json.dumps(bundle, ensure_ascii=False),
            store=False,
        )
        markdown = str(response.output_text)
        critique = critique_report(
            markdown=markdown,
            source_bundle=bundle,
            scenario_kind=stage1.kind,
            probability_valid=stage1.probability_valid,
        )
        if critique.passed:
            return ReportResult(
                status="LLM_PASS",
                markdown=markdown,
                report_json=bundle,
                critique=critique,
            )

        revision = openai_client.responses.create(
            model=effective_settings.openai_report_model,
            instructions=REPORT_INSTRUCTIONS,
            input=(
                "다음 초안과 critic 문제를 고쳐라. 숫자는 JSON에 있는 값만 "
                "사용하라.\n문제: {}\n초안:\n{}\n근거 JSON:\n{}"
            ).format(
                json.dumps(critique.issues, ensure_ascii=False),
                markdown,
                json.dumps(bundle, ensure_ascii=False),
            ),
            store=False,
        )
        revised_markdown = str(revision.output_text)
        revised_critique = critique_report(
            markdown=revised_markdown,
            source_bundle=bundle,
            scenario_kind=stage1.kind,
            probability_valid=stage1.probability_valid,
        )
        if revised_critique.passed:
            return ReportResult(
                status="LLM_REVISED_PASS",
                markdown=revised_markdown,
                report_json=bundle,
                critique=revised_critique,
            )
        return fallback.model_copy(
            update={
                "warnings": fallback.warnings
                + ["LLM 보고서가 재검수에 실패해 fallback했습니다."]
            }
        )
    except Exception:
        return fallback.model_copy(
            update={
                "warnings": fallback.warnings
                + ["LLM 보고서 호출 실패로 fallback했습니다."]
            }
        )
