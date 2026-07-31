import json
from typing import Any, Optional

from openai import OpenAI

from schemas import TradeDocumentExtraction
from src.config import Settings
from src.document_intake.confirmation import ConfirmationRecord
from src.domain.consultation_models import ConsultationPacket
from src.domain.confirmed_transaction_models import (
    ConfirmedTransactionSnapshot,
)
from src.domain.product_models import Stage4Result
from src.domain.report_models import ReportResult
from src.domain.stage1_models import NormalizedScenarioSet
from src.domain.stage1_web_models import MarketIntegrationResult
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
q90은 90% 발생확률이 아니라 모델 예측분포의 상위 경로위험 분위수다.
HORIZON_MISMATCH이면 모델 분위수를 결제기간 예측처럼 표현하지 마라.
뉴스는 시장 설명용이며 환율·손실 숫자를 변경한 것처럼 쓰지 마라.
consultation이 있으면 거래·결제 위험과 상담 항목은 그 경로만 근거로 사용하라.
consultation.consultation_priorities가 있으면 rank·title·priority_reason·
numeric_rationale·missing_information·expected_decision·next_action·
official_candidates·disclaimer를 순서와 값 그대로 유지하라.
상담 priority를 LLM이 생성·재정렬하거나 승인등급·보험 인수등급·대출등급으로
바꾸지 마라.
buffer shortfall과 cash deficit·payment deficit를 구분하고, 뒤 두 값이 0이면
지급불능이나 대출 필요성으로 표현하지 마라.
예정 결제 노출액을 실제 현재 미수·미지급잔액으로 표현하지 마라.
Stage 3 후보를 최적 추천으로 표현하지 마라.
Markdown 다운로드를 실제 RM 전송·상담 예약·신청 완료로 표현하지 마라.
consultation.country_environment가 있으면 OECD 지급·이전, World Bank 거시환경,
WTO 무역·시장접근을 분리하고 공식 URL·자료기간·원값·해석·한계를 표시하라.
Brazil OECD 4는 공식 원자료 분류로만 쓰고 KBaiAgent 국가등급으로 쓰지 마라.
미국 고소득 OECD 미분류는 0·LOW·안전·자료 없음으로 바꾸지 마라.
세 국가 신호를 0~100 점수·가중평균·국가 신용등급·부도확률로 만들지 마라.
서로 다른 World Bank 관측연도를 같은 시점 자료처럼 표현하지 마라.
국가 신호로 Stage 2 현금흐름이나 Stage 3 환헤지 비율을 변경하지 마라.
consultation이 있으면 상품은 consultation.official_candidate_shortlist.candidates만
후보/상담 필요로 표현하고 stage4 원시 검색 목록을 사용자용 후보로 쓰지 마라.
shortlist가 없거나 비어 있으면 상품명이나 기관을 만들지 말고 공식 후보가 없다고 밝혀라.
거래·결제 위험을 공식 심사등급·부도확률·보험 인수판단으로 표현하지 마라.
결제·회수 위험 때문에 환헤지 비율을 직접 높이거나 낮추지 마라.
승인·수익·손실회피를 보장하지 마라.
보고서 섹션은 거래 요약, 데이터 출처, 시나리오 성격, 현금흐름 영향,
환율·유동성 위험, 거래·결제조건 위험, 국가·무역환경 검토,
환헤지 시뮬레이션, 검토할 금융 대응,
공식 후보와 출처, 추가 정보, 상담 질문, 면책 순서다.
""".strip()


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
                    "생성을 차단하고 "
                    "결정론 보고서를 사용했습니다."
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
    revision_count = 0
    try:
        openai_client = client or OpenAI(
            api_key=effective_settings.openai_api_key,
            timeout=effective_settings.openai_timeout_seconds,
            max_retries=0,
        )
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
                generation_provider="OPENAI",
                revision_count=0,
                fallback_reason=None,
            )

        if max_revisions == 0:
            return fallback.model_copy(
                update={
                    "warnings": fallback.warnings
                    + ["critic 실패 후 재작성 정책이 0회라 fallback했습니다."],
                    "revision_count": 0,
                    "fallback_reason": "CRITIC_REJECTED",
                }
            )

        revision_count = 1
        revision = openai_client.responses.create(
            model=effective_settings.openai_report_model,
            instructions=REPORT_INSTRUCTIONS,
            input=(
                "다음 초안과 critic 수정 지시를 고쳐라. 숫자는 JSON에 있는 "
                "값만 사용하라.\n수정 지시: {}\n초안:\n{}\n근거 JSON:\n{}"
            ).format(
                json.dumps(
                    critique.revision_instructions,
                    ensure_ascii=False,
                ),
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
                generation_provider="OPENAI",
                revision_count=revision_count,
                fallback_reason=None,
            )
        return fallback.model_copy(
            update={
                "warnings": fallback.warnings
                + ["LLM 보고서가 재검수에 실패해 fallback했습니다."],
                "revision_count": revision_count,
                "fallback_reason": "CRITIC_REJECTED",
            }
        )
    except Exception:
        return fallback.model_copy(
            update={
                "warnings": fallback.warnings
                + ["LLM 보고서 호출 실패로 fallback했습니다."],
                "revision_count": revision_count,
                "fallback_reason": "API_FAILURE",
            }
        )
