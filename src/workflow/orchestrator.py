import uuid
from datetime import datetime, timedelta, timezone
from time import perf_counter_ns
from typing import Any, Callable, List, Literal, Optional, Tuple

from pydantic import Field

from schemas import StrictModel, TradeDocumentExtraction, ValidationResult
from src.country_environment.assessment import (
    assess_country_trade_environment,
)
from src.config import Settings
from src.application.market_integration_service import (
    integrate_stage1_market,
)
from src.application.stage2_input_service import (
    cashflow_error_detail,
    classify_cashflow_error,
)
from src.document_intake.confirmation import ConfirmationRecord
from src.domain.consultation_models import ConsultationPacket
from src.domain.country_environment_models import (
    CountryTradeEnvironmentAssessment,
    CountryTradeEnvironmentInput,
)
from src.domain.product_models import Stage4Result
from src.domain.report_models import ReportResult
from src.domain.stage1_models import Stage1LoadResult
from src.domain.stage1_web_models import MarketIntegrationResult
from src.domain.stage2_models import Stage2Input, Stage2Result
from src.domain.stage2_models import CashflowErrorDetail
from src.domain.stage3_models import Stage3Assumptions, Stage3Result
from src.stage1.adapter import load_stage1
from src.stage1.manual_scenarios import build_manual_stress_scenarios
from src.stage1.normalizer import normalize_stage1_scenarios
from src.stage2.binding import (
    confirmed_transaction_from_confirmation,
    validate_confirmed_transaction_snapshot,
    validate_snapshot_downstream_due_date,
    validate_stage2_trade_binding,
)
from src.stage2.engine import run_stage2
from src.stage3.optimizer import generate_strategy_candidates
from src.stage4.local_kb import search_offline_kb
from src.stage4.official_search import search_official_web
from src.stage5.deterministic_fallback import generate_deterministic_report
from src.stage5.report_agent import generate_report
from src.workflow.gates import confirmation_gate
from src.workflow.result import StageResult, StageStatus
from src.workflow.state import DocumentReference, WorkflowState
from src.workflow.trace import build_trace_event


Stage1Loader = Callable[..., Stage1LoadResult]
MarketIntegrationRunner = Callable[..., MarketIntegrationResult]
CashflowRunner = Callable[[Stage2Input, Any], Stage2Result]
HedgeRunner = Callable[..., Stage3Result]
ProductSearch = Callable[..., Stage4Result]
ReportGenerator = Callable[..., ReportResult]
CountryEnvironmentRunner = Callable[
    [CountryTradeEnvironmentInput],
    CountryTradeEnvironmentAssessment,
]


class WorkflowRequest(StrictModel):
    stage2_input: Stage2Input
    manual_base_rate: str
    stage1_mode: Literal[
        "MANUAL_STRESS",
        "EXTERNAL_STAGE1",
        "WEB_FORECAST",
    ] = "MANUAL_STRESS"
    stage1_payload: Optional[Any] = None
    stage1_endpoint: Optional[str] = None
    stage1_provider: Optional[Literal["http", "file", "mock"]] = None
    spot_provider: Optional[
        Literal["auto", "koreaexim", "manual", "fixture"]
    ] = None
    manual_spot_confirmed: bool = False
    grid_step_percent: int = Field(default=5)
    stability_preference: str = "0.7"
    stage3_assumptions: Optional[Stage3Assumptions] = None
    product_search_mode: Literal[
        "OFFLINE_KB",
        "OFFICIAL_WEB_SEARCH",
    ] = "OFFLINE_KB"
    product_query: Optional[str] = None


class WorkflowOrchestrator:
    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        stage1_loader: Stage1Loader = load_stage1,
        market_integration_runner: MarketIntegrationRunner = (
            integrate_stage1_market
        ),
        cashflow_runner: CashflowRunner = run_stage2,
        hedge_runner: HedgeRunner = generate_strategy_candidates,
        offline_product_search: ProductSearch = search_offline_kb,
        official_product_search: ProductSearch = search_official_web,
        report_generator: ReportGenerator = generate_report,
        country_environment_runner: CountryEnvironmentRunner = (
            assess_country_trade_environment
        ),
        fallback_report_generator: ReportGenerator = (
            generate_deterministic_report
        ),
        max_report_revisions: int = 1,
    ) -> None:
        if max_report_revisions not in {0, 1}:
            raise ValueError("보고서 재작성 횟수는 0 또는 1이어야 합니다.")
        self.settings = settings or Settings.from_env()
        self.stage1_loader = stage1_loader
        self.market_integration_runner = market_integration_runner
        self.cashflow_runner = cashflow_runner
        self.hedge_runner = hedge_runner
        self.offline_product_search = offline_product_search
        self.official_product_search = official_product_search
        self.report_generator = report_generator
        self.country_environment_runner = country_environment_runner
        self.fallback_report_generator = fallback_report_generator
        self.max_report_revisions = max_report_revisions

    @staticmethod
    def _new_case_id() -> str:
        return "case_{}".format(uuid.uuid4().hex)

    @staticmethod
    def _started() -> Tuple[datetime, int]:
        return datetime.now(timezone.utc), perf_counter_ns()

    @staticmethod
    def _duration_ms(started_ns: int) -> int:
        return max(0, int((perf_counter_ns() - started_ns) / 1_000_000))

    @staticmethod
    def _safe_error(stage: str, exc: Exception) -> str:
        return "{} 단계 실패 ({})".format(stage, type(exc).__name__)

    @staticmethod
    def _merge_messages(current: List[str], new: List[str]) -> List[str]:
        return list(dict.fromkeys(current + new))

    def _record(
        self,
        state: WorkflowState,
        stage: str,
        result: StageResult[Any],
        *,
        critic_passed: Optional[bool] = None,
        rewrite_count: int = 0,
    ) -> None:
        state.trace.append(
            build_trace_event(
                sequence=len(state.trace) + 1,
                case_id=state.case_id,
                stage=stage,
                result=result,
                mode=state.mode,
                user_confirmed=state.user_confirmed,
                critic_passed=critic_passed,
                rewrite_count=rewrite_count,
            )
        )
        state.warnings = self._merge_messages(
            state.warnings,
            result.warnings,
        )
        state.errors = self._merge_messages(state.errors, result.errors)

    def initialize(
        self,
        *,
        mode: Literal["OFFLINE", "ONLINE"],
        extraction: TradeDocumentExtraction,
        validation: ValidationResult,
        confirmation: Optional[ConfirmationRecord] = None,
        case_id: Optional[str] = None,
        intake_provider: Optional[str] = None,
        intake_duration_ms: Optional[int] = None,
        intake_retry_count: int = 0,
    ) -> WorkflowState:
        measured_started_at, started_ns = self._started()
        safe_duration_ms = max(0, int(intake_duration_ms or 0))
        confirmation_ready = bool(
            confirmation is not None
            and validation.stage2_allowed
            and confirmation.checks.all_critical_fields_confirmed(
                installment_schedule_confirmed=bool(
                    extraction.installments
                )
            )
        )
        warnings: List[str] = []
        if validation.missing_required_fields:
            warnings.append(
                "필수 필드 확인 필요: {}".format(
                    ", ".join(validation.missing_required_fields)
                )
            )
        confirmed_transaction = None
        if confirmation_ready and confirmation is not None:
            try:
                confirmed_transaction = (
                    confirmed_transaction_from_confirmation(
                        extraction=extraction,
                        validation=validation,
                        confirmation=confirmation,
                    )
                )
            except (TypeError, ValueError) as exc:
                warnings.append(
                    "확정 거래 snapshot을 만들 수 없습니다: {}".format(
                        str(exc)
                    )
                )
        confirmed = confirmed_transaction is not None
        if not confirmed:
            warnings.append("사용자 확인 전 downstream 계산을 차단했습니다.")
        finished_at = datetime.now(timezone.utc)
        started_at = (
            finished_at - timedelta(milliseconds=safe_duration_ms)
            if intake_duration_ms is not None
            else measured_started_at
        )
        intake = StageResult[TradeDocumentExtraction](
            status=(
                StageStatus.SUCCEEDED
                if confirmed
                else StageStatus.WAITING_FOR_USER
            ),
            data=extraction,
            warnings=warnings,
            evidence=[
                "stage0.extraction.evidence.{}".format(item.field)
                for item in extraction.evidence
            ],
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=(
                safe_duration_ms
                if intake_duration_ms is not None
                else self._duration_ms(started_ns)
            ),
            provider=(
                intake_provider
                or (
                    "offline_fixture"
                    if mode == "OFFLINE"
                    else "document_intake_adapter"
                )
            ),
            retry_count=max(0, intake_retry_count),
        )
        document = (
            DocumentReference(
                filename=confirmation.source_filename,
                sha256=confirmation.source_sha256,
            )
            if confirmation is not None
            else None
        )
        state = WorkflowState(
            case_id=case_id or self._new_case_id(),
            mode=mode,
            input_document=document,
            extracted_trade=extraction,
            extraction_confidence=(
                "HUMAN_CONFIRMED"
                if confirmed
                else (
                    "DETERMINISTIC_PASS"
                    if validation.validation_pass
                    else "REVIEW_REQUIRED"
                )
            ),
            extraction_evidence=extraction.evidence,
            confirmation=confirmation,
            confirmation_validation=validation,
            confirmed_transaction=confirmed_transaction,
            user_confirmed=confirmed,
            intake=intake,
            final_status=(
                StageStatus.RUNNING
                if confirmed
                else StageStatus.WAITING_FOR_USER
            ),
        )
        self._record(state, "intake", intake)
        return state

    def register_intake(
        self,
        state: WorkflowState,
        *,
        extraction: TradeDocumentExtraction,
        validation: ValidationResult,
        confirmation: Optional[ConfirmationRecord] = None,
        intake_provider: Optional[str] = None,
        intake_duration_ms: Optional[int] = None,
        intake_retry_count: int = 0,
    ) -> WorkflowState:
        updated = self.initialize(
            mode=state.mode,
            extraction=extraction,
            validation=validation,
            confirmation=confirmation,
            case_id=state.case_id,
            intake_provider=intake_provider,
            intake_duration_ms=intake_duration_ms,
            intake_retry_count=intake_retry_count,
        )
        new_event = updated.trace[0].model_copy(
            update={"sequence": len(state.trace) + 1}
        )
        updated.trace = list(state.trace) + [new_event]
        updated.warnings = self._merge_messages(
            state.warnings,
            updated.warnings,
        )
        updated.errors = self._merge_messages(
            state.errors,
            updated.errors,
        )
        return updated

    @staticmethod
    def _clear_after(state: WorkflowState, stage: str) -> None:
        if stage == "market_risk":
            state.market_risk = None
            state.market_integration = None
            state.stage2_input = None
            state.cashflow = None
            state.cashflow_error = None
            state.hedge = None
            state.selected_strategy = None
            state.product_search = None
            state.report = None
            state.report_draft = None
            state.critic_result = None
            state.final_report = None
            state.rewrite_count = 0
        elif stage == "cashflow":
            state.cashflow = None
            state.stage2_input = None
            state.cashflow_error = None
            state.hedge = None
            state.selected_strategy = None
            state.product_search = None
            state.report = None
            state.report_draft = None
            state.critic_result = None
            state.final_report = None
            state.rewrite_count = 0
        elif stage == "hedge":
            state.hedge = None
            state.selected_strategy = None
            state.product_search = None
            state.report = None
            state.report_draft = None
            state.critic_result = None
            state.final_report = None
            state.rewrite_count = 0
        elif stage == "product_search":
            state.product_search = None
            state.report = None
            state.report_draft = None
            state.critic_result = None
            state.final_report = None
            state.rewrite_count = 0

    def record_cashflow_failure(
        self,
        state: WorkflowState,
        detail: CashflowErrorDetail,
        *,
        provider: str = "stage2_input_validation",
    ) -> WorkflowState:
        """Persist a pre-calculation failure after invalidating stale results."""

        self._clear_after(state, "cashflow")
        started_at, started_ns = self._started()
        result = StageResult[Stage2Result](
            status=StageStatus.FAILED,
            errors=[detail.user_message],
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            duration_ms=self._duration_ms(started_ns),
            provider=provider,
        )
        state.cashflow = result
        state.cashflow_error = detail
        state.final_status = StageStatus.FAILED
        self._record(state, "cashflow", result)
        return state

    def _wait_for_confirmation(
        self,
        state: WorkflowState,
        stage: str,
    ) -> WorkflowState:
        self._clear_after(state, stage)
        decision = confirmation_gate(state)
        started_at, started_ns = self._started()
        result = StageResult[Any](
            status=StageStatus.WAITING_FOR_USER,
            warnings=decision.reasons,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            duration_ms=self._duration_ms(started_ns),
            provider="confirmation_gate",
        )
        setattr(state, stage, result)
        state.final_status = StageStatus.WAITING_FOR_USER
        self._record(state, stage, result)
        return state

    def run_market_risk(
        self,
        state: WorkflowState,
        *,
        stage2_input: Optional[Stage2Input] = None,
        expected_currency: Optional[str] = None,
        expected_target_date: Optional[str] = None,
        manual_base_rate: str,
        mode: str = "MANUAL_STRESS",
        payload: Optional[Any] = None,
        endpoint: Optional[str] = None,
        stage1_provider: Optional[str] = None,
        spot_provider: Optional[str] = None,
        manual_spot_confirmed: bool = False,
    ) -> WorkflowState:
        if not confirmation_gate(state).allowed:
            return self._wait_for_confirmation(state, "market_risk")
        self._clear_after(state, "market_risk")
        started_at, started_ns = self._started()
        snapshot = state.confirmed_transaction
        if snapshot is None:
            return self._wait_for_confirmation(state, "market_risk")
        if stage2_input is not None:
            try:
                validate_stage2_trade_binding(
                    expected=snapshot.trade_binding,
                    stage2_input=stage2_input,
                )
            except (TypeError, ValueError) as exc:
                result = StageResult[Stage1LoadResult](
                    status=StageStatus.FAILED,
                    errors=[
                        "확인된 거래와 Stage 2 입력을 결속하지 못했습니다: "
                        "{}".format(str(exc))
                    ],
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc),
                    duration_ms=self._duration_ms(started_ns),
                    provider="confirmed_trade_binding",
                )
                state.market_risk = result
                state.final_status = StageStatus.FAILED
                self._record(state, "market_risk", result)
                return state
        currency = snapshot.currency
        target_date = snapshot.due_date
        supplied_currency = str(expected_currency or "").strip().upper()
        supplied_target_date = str(expected_target_date or "").strip()
        if supplied_currency and supplied_currency != currency:
            result = StageResult[Stage1LoadResult](
                status=StageStatus.FAILED,
                errors=[
                    "Stage 1 통화가 canonical confirmed transaction과 "
                    "일치하지 않습니다."
                ],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="confirmed_trade_binding",
            )
            state.market_risk = result
            state.final_status = StageStatus.FAILED
            self._record(state, "market_risk", result)
            return state
        if supplied_target_date and supplied_target_date != target_date:
            result = StageResult[Stage1LoadResult](
                status=StageStatus.FAILED,
                errors=[
                    "Stage 1 target_date가 확정 결제일과 일치하지 않습니다 "
                    "(canonical confirmed due_date)."
                ],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="confirmed_trade_binding",
            )
            state.market_risk = result
            state.final_status = StageStatus.FAILED
            self._record(state, "market_risk", result)
            return state
        if not currency or not target_date:
            result = StageResult[Stage1LoadResult](
                status=StageStatus.FAILED,
                errors=[
                    "market_risk 실행에는 통화와 target date가 필요합니다."
                ],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="stage1_adapter",
            )
            state.market_risk = result
            state.final_status = StageStatus.FAILED
            self._record(state, "market_risk", result)
            return state
        warnings: List[str] = []
        if mode.strip().upper() == "WEB_FORECAST":
            try:
                integration = self.market_integration_runner(
                    settings=self.settings,
                    currency=currency,
                    settlement_date=target_date,
                    provider_name=stage1_provider,
                    spot_provider_name=spot_provider,
                    manual_spot_rate=manual_base_rate,
                    manual_spot_confirmed=manual_spot_confirmed,
                )
                state.market_integration = integration
                loaded = integration.stage1_load
                warnings = list(loaded.warnings)
                fallback_used = bool(
                    integration.forecast_load is None
                    or integration.forecast_load.fallback_used
                )
                status = (
                    StageStatus.FALLBACK
                    if fallback_used
                    else StageStatus.SUCCEEDED
                )
                provider_label = (
                    integration.forecast_load.source.lower()
                    if integration.forecast_load is not None
                    else "fixed_stress_only"
                )
                result = StageResult[Stage1LoadResult](
                    status=status,
                    data=loaded,
                    warnings=warnings,
                    evidence=[
                        "market_integration.forecast_load.forecast.source",
                        "market_integration.spot_quote",
                        "market_integration.scenario_build",
                    ],
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc),
                    duration_ms=self._duration_ms(started_ns),
                    provider="stage1_web_{}".format(provider_label),
                    fallback_used=fallback_used,
                )
                state.market_risk = result
                state.final_status = StageStatus.RUNNING
                self._record(state, "market_risk", result)
                return state
            except Exception as exc:
                result = StageResult[Stage1LoadResult](
                    status=StageStatus.FAILED,
                    errors=[
                        "Stage 1 또는 기준환율을 안전하게 준비하지 "
                        "못했습니다.",
                        self._safe_error("stage1_web_integration", exc),
                    ],
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc),
                    duration_ms=self._duration_ms(started_ns),
                    provider="stage1_web_integration",
                )
                state.market_risk = result
                state.final_status = StageStatus.FAILED
                self._record(state, "market_risk", result)
                return state
        try:
            loaded = self.stage1_loader(
                expected_currency=currency,
                expected_target_date=target_date,
                manual_base_rate=manual_base_rate,
                mode=mode,
                payload=payload,
                endpoint=endpoint,
                settings=self.settings,
            )
            fallback_used = loaded.source == "MANUAL_FALLBACK"
            status = (
                StageStatus.FALLBACK
                if fallback_used
                else StageStatus.SUCCEEDED
            )
            warnings = list(loaded.warnings)
        except Exception as exc:
            manual = build_manual_stress_scenarios(
                currency=currency,
                base_rate=manual_base_rate,
                target_date=target_date,
            )
            normalized = normalize_stage1_scenarios(
                manual,
                expected_currency=currency,
                expected_target_date=target_date,
            )
            warnings = [
                "외부 Stage 1 adapter 실패로 수동 스트레스 시나리오를 "
                "사용했습니다.",
                self._safe_error("market_risk_adapter", exc),
            ]
            loaded = Stage1LoadResult(
                source="MANUAL_FALLBACK",
                scenario_set=normalized,
                warnings=warnings,
            )
            fallback_used = True
            status = StageStatus.FALLBACK
        result = StageResult[Stage1LoadResult](
            status=status,
            data=loaded,
            warnings=warnings,
            evidence=[
                "stage1.scenario_set.as_of",
                "stage1.scenario_set.target_date",
                "stage1.scenario_set.application_rule",
            ],
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            duration_ms=self._duration_ms(started_ns),
            provider=(
                "manual_stress"
                if loaded.source != "EXTERNAL"
                else "stage1_json_rest_adapter"
            ),
            fallback_used=fallback_used,
        )
        state.market_risk = result
        state.final_status = StageStatus.RUNNING
        self._record(state, "market_risk", result)
        return state

    def run_cashflow(
        self,
        state: WorkflowState,
        stage2_input: Stage2Input,
    ) -> WorkflowState:
        if (
            state.confirmed_transaction is not None
            and state.extracted_trade is not None
            and state.confirmation_validation is not None
            and state.confirmation is not None
        ):
            try:
                validate_confirmed_transaction_snapshot(
                    snapshot=state.confirmed_transaction,
                    extraction=state.extracted_trade,
                    validation=state.confirmation_validation,
                    confirmation=state.confirmation,
                )
            except (TypeError, ValueError) as exc:
                detail = cashflow_error_detail(
                    code="STALE_CONFIRMED_STATE",
                    user_message=(
                        "확인 기록의 거래값이 현재 canonical snapshot과 "
                        "다릅니다. 거래정보를 다시 확인하고 확정하세요."
                    ),
                    stage2_input=stage2_input,
                    field_path="workflow.confirmed_transaction",
                    exception_type=type(exc).__name__,
                    technical_message="{}: {}".format(
                        type(exc).__name__,
                        str(exc),
                    ),
                )
                return self.record_cashflow_failure(
                    state,
                    detail,
                    provider="confirmed_transaction_gate",
                )
        if not confirmation_gate(state).allowed:
            return self._wait_for_confirmation(state, "cashflow")
        self._clear_after(state, "cashflow")
        started_at, started_ns = self._started()
        snapshot = state.confirmed_transaction
        if snapshot is None:
            detail = cashflow_error_detail(
                code="STALE_CONFIRMED_STATE",
                user_message=(
                    "확정 거래 snapshot이 없습니다. 거래정보를 다시 "
                    "확인하고 확정하세요."
                ),
                stage2_input=stage2_input,
                field_path="workflow.confirmed_transaction",
            )
            return self.record_cashflow_failure(
                state,
                detail,
                provider="confirmed_transaction_gate",
            )
        try:
            validate_stage2_trade_binding(
                expected=snapshot.trade_binding,
                stage2_input=stage2_input,
            )
        except (TypeError, ValueError) as exc:
            detail = classify_cashflow_error(
                exc,
                stage2_input=stage2_input,
            ).model_copy(
                update={
                    "code": "STALE_CONFIRMED_STATE",
                    "user_message": (
                        "확정 거래와 현재 금융 입력이 서로 다릅니다. "
                        "거래 확인을 다시 실행해 최신 확정값으로 분석하세요. "
                        "원인: {}"
                    ).format(str(exc)),
                    "field_path": "stage0.confirmation",
                }
            )
            result = StageResult[Stage2Result](
                status=StageStatus.FAILED,
                errors=[detail.user_message],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="confirmed_trade_binding",
            )
            state.cashflow = result
            state.cashflow_error = detail
            state.final_status = StageStatus.FAILED
            self._record(state, "cashflow", result)
            return state
        if state.market_risk is None or state.market_risk.data is None:
            detail = cashflow_error_detail(
                code="STALE_CONFIRMED_STATE",
                user_message=(
                    "환율 가정 결과가 없거나 현재 거래와 맞지 않습니다. "
                    "환율 위험 범위를 다시 준비하세요."
                ),
                stage2_input=stage2_input,
                due_date=(
                    stage2_input.exposures[0].settlement_date
                    if stage2_input.exposures
                    else None
                ),
                cashflow_base_date=stage2_input.as_of_date,
                field_path="workflow.market_risk",
            )
            result = StageResult[Stage2Result](
                status=StageStatus.FAILED,
                errors=[detail.user_message],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="decimal_cashflow_engine",
            )
            state.cashflow = result
            state.cashflow_error = detail
            state.final_status = StageStatus.FAILED
            self._record(state, "cashflow", result)
            return state
        try:
            validate_snapshot_downstream_due_date(
                snapshot=snapshot,
                stage1_target_date=(
                    state.market_risk.data.scenario_set.target_date
                ),
                stage2_dates=[
                    item.settlement_date
                    for item in stage2_input.exposures
                ],
            )
        except (TypeError, ValueError) as exc:
            detail = classify_cashflow_error(
                exc,
                stage2_input=stage2_input,
            ).model_copy(
                update={
                    "code": "STALE_CONFIRMED_STATE",
                    "user_message": (
                        "확정 결제일과 환율·현금흐름 입력의 날짜가 서로 "
                        "다릅니다. 거래 확인부터 다시 실행하세요."
                    ),
                    "field_path": (
                        "stage0.confirmation|stage1.target_date|"
                        "stage2.exposures[].settlement_date"
                    ),
                }
            )
            result = StageResult[Stage2Result](
                status=StageStatus.FAILED,
                errors=[detail.user_message],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="confirmed_trade_binding",
            )
            state.cashflow = result
            state.cashflow_error = detail
            state.final_status = StageStatus.FAILED
            self._record(state, "cashflow", result)
            return state
        try:
            calculated = self.cashflow_runner(
                stage2_input,
                state.market_risk.data.scenario_set,
            )
            result = StageResult[Stage2Result](
                status=StageStatus.SUCCEEDED,
                data=calculated,
                warnings=calculated.warnings,
                evidence=[
                    "stage2.confirmed_trade_sha256",
                    "stage2.base_required_or_proceeds_krw",
                    "stage2.scenario_results",
                    "stage2.stage3_constraints",
                ],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="decimal_cashflow_engine",
            )
            state.stage2_input = stage2_input
            state.cashflow = result
            state.cashflow_error = None
            state.final_status = StageStatus.RUNNING
        except Exception as exc:
            detail = classify_cashflow_error(
                exc,
                stage2_input=stage2_input,
            )
            result = StageResult[Stage2Result](
                status=StageStatus.FAILED,
                errors=[detail.user_message],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="decimal_cashflow_engine",
            )
            state.cashflow = result
            state.cashflow_error = detail
            state.final_status = StageStatus.FAILED
        self._record(state, "cashflow", result)
        return state

    def run_hedge(
        self,
        state: WorkflowState,
        *,
        grid_step_percent: int = 5,
        stability_preference: str = "0.7",
        assumptions: Optional[Stage3Assumptions] = None,
    ) -> WorkflowState:
        if not confirmation_gate(state).allowed:
            return self._wait_for_confirmation(state, "hedge")
        self._clear_after(state, "hedge")
        started_at, started_ns = self._started()
        if state.cashflow is None or state.cashflow.data is None:
            result = StageResult[Stage3Result](
                status=StageStatus.SKIPPED,
                errors=["cashflow 결과가 없어 hedge를 실행하지 않았습니다."],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="grid_hedge_optimizer",
            )
            state.hedge = result
            state.final_status = StageStatus.FAILED
            self._record(state, "hedge", result)
            return state
        try:
            candidates = self.hedge_runner(
                state.cashflow.data,
                grid_step_percent=grid_step_percent,
                stability_preference=stability_preference,
                assumptions=assumptions,
            )
            result = StageResult[Stage3Result](
                status=StageStatus.SUCCEEDED,
                data=candidates,
                warnings=candidates.warnings,
                evidence=[
                    "stage3.candidates",
                    "stage3.objective_mode",
                    "stage3.assumptions_contract",
                ],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="grid_hedge_optimizer",
            )
            state.hedge = result
            state.final_status = StageStatus.RUNNING
        except Exception as exc:
            result = StageResult[Stage3Result](
                status=StageStatus.FAILED,
                errors=[self._safe_error("hedge", exc)],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="grid_hedge_optimizer",
            )
            state.hedge = result
            state.final_status = StageStatus.FAILED
        self._record(state, "hedge", result)
        return state

    @staticmethod
    def _default_product_query(stage3: Stage3Result) -> str:
        if not stage3.candidates:
            return (
                "수출입 결제자금 환율관리 운영자금 상담 "
                "선물환 환변동보험"
            )
        return " ".join(
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

    def run_product_search(
        self,
        state: WorkflowState,
        *,
        query: Optional[str] = None,
        mode: str = "OFFLINE_KB",
    ) -> WorkflowState:
        if not confirmation_gate(state).allowed:
            return self._wait_for_confirmation(state, "product_search")
        self._clear_after(state, "product_search")
        started_at, started_ns = self._started()
        if (
            state.cashflow is None
            or state.cashflow.data is None
            or state.hedge is None
            or state.hedge.data is None
        ):
            result = StageResult[Stage4Result](
                status=StageStatus.SKIPPED,
                errors=[
                    "cashflow/hedge 결과가 없어 product_search를 실행하지 않았습니다."
                ],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="official_product_retrieval",
            )
            state.product_search = result
            state.final_status = StageStatus.FAILED
            self._record(state, "product_search", result)
            return state

        effective_query = query or self._default_product_query(
            state.hedge.data
        )
        fallback_used = False
        warnings: List[str] = []
        try:
            if mode == "OFFICIAL_WEB_SEARCH":
                try:
                    products = self.official_product_search(
                        query=effective_query,
                        trade_type=state.cashflow.data.trade_type,
                        settings=self.settings,
                    )
                    provider = "official_web_search"
                except Exception as exc:
                    products = self.offline_product_search(
                        query=effective_query,
                        trade_type=state.cashflow.data.trade_type,
                    )
                    provider = "offline_official_kb"
                    fallback_used = True
                    warnings.extend(
                        [
                            "공식 웹 검색 실패로 offline 공식 KB를 사용했습니다.",
                            self._safe_error("official_product_search", exc),
                        ]
                    )
            elif mode == "OFFLINE_KB":
                products = self.offline_product_search(
                    query=effective_query,
                    trade_type=state.cashflow.data.trade_type,
                )
                provider = "offline_official_kb"
            else:
                raise ValueError("지원하지 않는 상품 검색 모드입니다.")

            warnings = self._merge_messages(warnings, products.warnings)
            if not products.candidates:
                warnings.append("공식 출처가 확인된 상품 후보가 없습니다.")
                products = products.model_copy(
                    update={
                        "warnings": self._merge_messages(
                            products.warnings,
                            ["공식 출처가 확인된 상품 후보가 없습니다."],
                        )
                    }
                )
            result = StageResult[Stage4Result](
                status=(
                    StageStatus.FALLBACK
                    if fallback_used
                    else StageStatus.SUCCEEDED
                ),
                data=products,
                warnings=warnings,
                evidence=[
                    item.source.url for item in products.candidates
                ],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider=provider,
                fallback_used=fallback_used,
            )
            state.product_search = result
            state.final_status = StageStatus.RUNNING
        except Exception as exc:
            result = StageResult[Stage4Result](
                status=StageStatus.FAILED,
                errors=[self._safe_error("product_search", exc)],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="official_product_retrieval",
            )
            state.product_search = result
            state.final_status = StageStatus.FAILED
        self._record(state, "product_search", result)
        return state

    def _fallback_report(
        self,
        state: WorkflowState,
        consultation_packet: Optional[ConsultationPacket] = None,
    ) -> ReportResult:
        report_kwargs = {
            "extraction": state.extracted_trade,
            "confirmation": state.confirmation,
            "confirmed_transaction": state.confirmed_transaction,
            "stage1": state.market_risk.data.scenario_set,
            "stage2": state.cashflow.data,
            "stage3": state.hedge.data,
            "stage4": state.product_search.data,
            "market_integration": state.market_integration,
        }
        if consultation_packet is not None:
            report_kwargs["consultation_packet"] = consultation_packet
        return self.fallback_report_generator(**report_kwargs)

    def run_report(
        self,
        state: WorkflowState,
        *,
        consultation_packet: Optional[ConsultationPacket] = None,
    ) -> WorkflowState:
        if state.trace and state.trace[-1].stage == "report":
            state.trace.pop()
        state.report = None
        state.report_draft = None
        state.critic_result = None
        state.final_report = None
        state.rewrite_count = 0
        if not confirmation_gate(state).allowed:
            return self._wait_for_confirmation(state, "report")
        started_at, started_ns = self._started()
        required = (
            state.extracted_trade,
            state.confirmation,
            state.confirmed_transaction,
            state.market_risk,
            state.cashflow,
            state.hedge,
            state.product_search,
        )
        if any(item is None for item in required) or any(
            result.data is None
            for result in (
                state.market_risk,
                state.cashflow,
                state.hedge,
                state.product_search,
            )
        ):
            result = StageResult[ReportResult](
                status=StageStatus.SKIPPED,
                errors=["Stage 0~4 결과가 없어 report를 실행하지 않았습니다."],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="report_generator",
            )
            state.report = result
            state.final_status = StageStatus.FAILED
            self._record(state, "report", result)
            return state

        try:
            validate_snapshot_downstream_due_date(
                snapshot=state.confirmed_transaction,
                stage1_target_date=(
                    state.market_risk.data.scenario_set.target_date
                ),
                stage2_dates=[
                    item.settlement_date
                    for item in state.cashflow.data.exposure_computations
                ],
                consultation_date=(
                    consultation_packet.company_summary.settlement_date
                    if consultation_packet is not None
                    else state.confirmed_transaction.due_date
                ),
                stage5_date=state.confirmed_transaction.due_date,
            )
        except (TypeError, ValueError) as exc:
            result = StageResult[ReportResult](
                status=StageStatus.FAILED,
                errors=[
                    "Stage 5 날짜가 canonical confirmed due_date와 "
                    "일치하지 않습니다: {}".format(str(exc))
                ],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="confirmed_transaction_gate",
            )
            state.report = result
            state.final_status = StageStatus.FAILED
            self._record(state, "report", result)
            return state

        try:
            report_kwargs = {
                "extraction": state.extracted_trade,
                "confirmation": state.confirmation,
                "confirmed_transaction": state.confirmed_transaction,
                "stage1": state.market_risk.data.scenario_set,
                "stage2": state.cashflow.data,
                "stage3": state.hedge.data,
                "stage4": state.product_search.data,
                "market_integration": state.market_integration,
                "settings": self.settings,
                "max_revisions": self.max_report_revisions,
            }
            if consultation_packet is not None:
                report_kwargs["consultation_packet"] = consultation_packet
            report = self.report_generator(**report_kwargs)
        except Exception as exc:
            report = self._fallback_report(
                state,
                consultation_packet=consultation_packet,
            )
            report = report.model_copy(
                update={
                    "warnings": report.warnings
                    + [self._safe_error("report_generator", exc)]
                }
            )

        rewrite_count = int(getattr(report, "revision_count", 0))
        fallback_used = report.status == "DETERMINISTIC_FALLBACK"
        provider = str(
            getattr(
                report,
                "generation_provider",
                (
                    "deterministic_template"
                    if fallback_used
                    else "openai_report_generator"
                ),
            )
        )
        result = StageResult[ReportResult](
            status=(
                StageStatus.FALLBACK
                if fallback_used
                else StageStatus.SUCCEEDED
            ),
            data=report,
            warnings=report.warnings,
            evidence=[
                "report.report_json.stage0",
                "report.report_json.stage1",
                "report.report_json.stage2",
                "report.report_json.stage3",
                "report.report_json.stage4",
            ]
            + (
                [
                    "report.report_json.consultation."
                    "trade_settlement_risk",
                    "report.report_json.consultation."
                    "official_candidate_shortlist",
                ]
                if consultation_packet is not None
                else []
            )
            + (
                [
                    "report.report_json.consultation."
                    "country_environment",
                ]
                if (
                    consultation_packet is not None
                    and consultation_packet.country_environment is not None
                )
                else []
            ),
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            duration_ms=self._duration_ms(started_ns),
            provider=provider,
            fallback_used=fallback_used,
            retry_count=rewrite_count,
        )
        state.report = result
        state.report_draft = report.markdown
        state.critic_result = report.critique
        state.final_report = report
        state.rewrite_count = rewrite_count
        state.final_status = StageStatus.SUCCEEDED
        self._record(
            state,
            "report",
            result,
            critic_passed=report.critique.passed,
            rewrite_count=rewrite_count,
        )
        return state

    def run_country_environment(
        self,
        state: WorkflowState,
        value: CountryTradeEnvironmentInput,
    ) -> WorkflowState:
        if not confirmation_gate(state).allowed:
            return self._wait_for_confirmation(
                state,
                "country_environment",
            )
        started_at, started_ns = self._started()
        state.report = None
        state.report_draft = None
        state.critic_result = None
        state.final_report = None
        state.rewrite_count = 0
        try:
            assessment = self.country_environment_runner(value)
            result = StageResult[CountryTradeEnvironmentAssessment](
                status=StageStatus.SUCCEEDED,
                data=assessment,
                warnings=assessment.warnings,
                evidence=[
                    "country={}".format(assessment.country),
                    "snapshot_id={}".format(assessment.snapshot_id),
                    "rule_version={}".format(assessment.rule_version),
                    "review_priority={}".format(
                        assessment.review_priority
                    ),
                    "source_record_ids={}".format(
                        ",".join(assessment.source_record_ids)
                    ),
                    "warning_codes={}".format(
                        ",".join(assessment.warning_codes)
                    ),
                ],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="versioned_offline_snapshot",
            )
        except Exception as exc:
            result = StageResult[CountryTradeEnvironmentAssessment](
                status=StageStatus.FAILED,
                errors=[self._safe_error("country_environment", exc)],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=self._duration_ms(started_ns),
                provider="versioned_offline_snapshot",
            )
        state.country_environment = result
        self._record(state, "country_environment", result)
        return state

    @staticmethod
    def _stopped(state: WorkflowState) -> bool:
        return state.final_status in {
            StageStatus.FAILED,
            StageStatus.WAITING_FOR_USER,
        }

    def run(
        self,
        state: WorkflowState,
        request: WorkflowRequest,
    ) -> WorkflowState:
        if not confirmation_gate(state).allowed:
            return self._wait_for_confirmation(state, "market_risk")
        state = self.run_market_risk(
            state,
            stage2_input=request.stage2_input,
            manual_base_rate=request.manual_base_rate,
            mode=request.stage1_mode,
            payload=request.stage1_payload,
            endpoint=request.stage1_endpoint,
            stage1_provider=request.stage1_provider,
            spot_provider=request.spot_provider,
            manual_spot_confirmed=request.manual_spot_confirmed,
        )
        if self._stopped(state):
            return state
        state = self.run_cashflow(state, request.stage2_input)
        if self._stopped(state):
            return state
        state = self.run_hedge(
            state,
            grid_step_percent=request.grid_step_percent,
            stability_preference=request.stability_preference,
            assumptions=request.stage3_assumptions,
        )
        if self._stopped(state):
            return state
        state = self.run_product_search(
            state,
            query=request.product_query,
            mode=request.product_search_mode,
        )
        if self._stopped(state):
            return state
        return self.run_report(state)
