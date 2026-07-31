import hashlib
import json
import re
from typing import Any, Dict, List, Sequence

from schemas import TradeDocumentExtraction, ValidationResult
from src.document_intake.confirmation import (
    ConfirmationRecord,
    validate_confirmation,
)
from src.domain.confirmed_transaction_models import (
    ConfirmedInstallment,
    ConfirmedTradeBinding,
    ConfirmedTradeEvent,
    ConfirmedTransactionSnapshot,
)
from src.domain.stage2_models import Stage2Input
from src.stage2.metrics import date_value, decimal_string, decimal_value


SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def _normalized_currency(value: Any, field: str) -> str:
    currency = str(value or "").strip()
    if (
        len(currency) != 3
        or not currency.isalpha()
        or currency != currency.upper()
    ):
        raise ValueError(
            "{}는 대문자 ISO 통화 코드 3글자여야 합니다.".format(field)
        )
    return currency


def _normalized_amount(value: Any, field: str) -> str:
    parsed = decimal_value(
        str(value),
        field,
        allow_zero=False,
    )
    return decimal_string(parsed)


def _canonical_amount(value: str) -> str:
    parsed = decimal_value(
        value,
        "confirmed trade amount",
        allow_zero=False,
    )
    return decimal_string(parsed.normalize())


def _normalized_source_sha256(value: Any) -> str:
    source_sha256 = str(value or "").strip().lower()
    if not SHA256_RE.fullmatch(source_sha256):
        raise ValueError("확인된 문서의 SHA-256 fingerprint가 필요합니다.")
    return source_sha256


def _normalized_event(
    *,
    sequence: Any,
    trade_type: Any,
    currency: Any,
    foreign_amount: Any,
    settlement_date: Any,
) -> ConfirmedTradeEvent:
    if trade_type not in {"IMPORT", "EXPORT"}:
        raise ValueError("확인된 거래 방향은 IMPORT 또는 EXPORT여야 합니다.")
    try:
        normalized_sequence = int(sequence)
    except (TypeError, ValueError) as exc:
        raise ValueError("확인된 거래 sequence는 정수여야 합니다.") from exc
    if str(sequence).strip() != str(normalized_sequence):
        raise ValueError("확인된 거래 sequence는 정수여야 합니다.")
    return ConfirmedTradeEvent(
        sequence=normalized_sequence,
        trade_type=trade_type,
        currency=_normalized_currency(currency, "confirmed trade currency"),
        foreign_amount=_normalized_amount(
            foreign_amount,
            "confirmed trade foreign_amount",
        ),
        settlement_date=date_value(
            str(settlement_date),
            "confirmed trade settlement_date",
        ).isoformat(),
    )


def _build_binding(
    *,
    source_sha256: Any,
    trade_type: Any,
    currency: Any,
    events: List[ConfirmedTradeEvent],
) -> ConfirmedTradeBinding:
    normalized_source = _normalized_source_sha256(source_sha256)
    if trade_type not in {"IMPORT", "EXPORT"}:
        raise ValueError("확인된 거래 방향은 IMPORT 또는 EXPORT여야 합니다.")
    normalized_currency = _normalized_currency(
        currency,
        "confirmed trade currency",
    )
    if not events:
        raise ValueError("확인된 결제 이벤트가 필요합니다.")
    sequences = [item.sequence for item in events]
    if sequences != list(range(1, len(events) + 1)):
        raise ValueError("확인된 거래 sequence는 1부터 연속이어야 합니다.")
    if any(item.trade_type != trade_type for item in events):
        raise ValueError("확인된 거래 방향이 결제 이벤트와 일치하지 않습니다.")
    if any(item.currency != normalized_currency for item in events):
        raise ValueError("확인된 거래 통화가 결제 이벤트와 일치하지 않습니다.")

    canonical: Dict[str, Any] = {
        "source_sha256": normalized_source,
        "trade_type": trade_type,
        "currency": normalized_currency,
        "events": [
            {
                "sequence": item.sequence,
                "trade_type": item.trade_type,
                "currency": item.currency,
                "foreign_amount": _canonical_amount(item.foreign_amount),
                "settlement_date": item.settlement_date,
            }
            for item in events
        ],
    }
    serialized = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    trade_sha256 = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return ConfirmedTradeBinding(
        source_sha256=normalized_source,
        trade_type=trade_type,
        currency=normalized_currency,
        events=events,
        trade_sha256=trade_sha256,
    )


def _confirmed_values_match_extraction(
    extraction: TradeDocumentExtraction,
    confirmation: ConfirmationRecord,
) -> bool:
    extraction_payload = extraction.model_dump()
    confirmed_payload = confirmation.confirmed_values
    fields = (
        "document_type",
        "document_number",
        "seller_name",
        "seller_country",
        "buyer_name",
        "buyer_country",
        "company_role",
        "trade_type",
        "currency",
        "grand_total",
        "amount_due",
        "issue_date",
        "contract_date",
        "shipment_date",
        "explicit_due_date",
        "derived_due_date",
        "payment_terms",
        "incoterm",
        "installments",
    )
    return all(
        confirmed_payload.get(field) == extraction_payload.get(field)
        for field in fields
    )


def confirmed_due_date_from_confirmation(
    confirmation: ConfirmationRecord,
) -> str:
    """Return the one canonical downstream date without a date fallback."""

    checks_value = confirmation.checks.confirmed_due_date
    snapshot_value = confirmation.confirmed_values.get(
        "settlement_date"
    )
    if not checks_value or not snapshot_value:
        raise ValueError(
            "확정 결제일이 없습니다. 계약일이나 분할결제 첫 회차일을 "
            "대신 사용할 수 없습니다."
        )
    checks_date = date_value(
        str(checks_value),
        "confirmation.checks.confirmed_due_date",
    ).isoformat()
    snapshot_date = date_value(
        str(snapshot_value),
        "confirmation.confirmed_values.settlement_date",
    ).isoformat()
    if checks_date != snapshot_date:
        raise ValueError(
            "확인 기록의 결제일 snapshot이 현재 확인값과 다릅니다."
        )
    return checks_date


def validate_downstream_due_date(
    *,
    confirmation: ConfirmationRecord,
    stage1_target_date: str,
    stage2_dates: Sequence[str],
) -> str:
    """Fail closed when any downstream stage diverges from confirmation."""

    confirmed_due_date = confirmed_due_date_from_confirmation(
        confirmation
    )
    normalized_stage1 = date_value(
        stage1_target_date,
        "stage1.scenario_set.target_date",
    ).isoformat()
    if normalized_stage1 != confirmed_due_date:
        raise ValueError(
            "Stage 1 target_date가 확정 결제일과 일치하지 않습니다."
        )
    if not stage2_dates:
        raise ValueError("Stage 2 결제·수취일이 없습니다.")
    for index, value in enumerate(stage2_dates):
        normalized = date_value(
            value,
            "stage2.exposures[{}].settlement_date".format(index),
        ).isoformat()
        if normalized != confirmed_due_date:
            raise ValueError(
                "Stage 2 결제·수취일이 확정 결제일과 일치하지 않습니다."
            )
    return confirmed_due_date


def confirmed_trade_from_confirmation(
    *,
    extraction: TradeDocumentExtraction,
    validation: ValidationResult,
    confirmation: ConfirmationRecord,
) -> ConfirmedTradeBinding:
    if confirmation.company_role != extraction.company_role:
        raise ValueError("확인 기록의 회사 역할이 현재 거래와 일치하지 않습니다.")
    if not _confirmed_values_match_extraction(extraction, confirmation):
        raise ValueError("확인 기록의 거래값이 현재 추출값과 일치하지 않습니다.")

    recomputed = validate_confirmation(
        extraction=extraction,
        record=confirmation,
        company_country=confirmation.company_country,
    )
    if not recomputed.stage2_allowed:
        raise ValueError("확인된 거래가 Stage 2 결정론 검증을 통과하지 못했습니다.")
    if validation.model_dump() != recomputed.model_dump():
        raise ValueError("Stage 2 검증 상태가 결정론 재검증 결과와 다릅니다.")

    trade_type = recomputed.derived_trade_type
    currency = recomputed.normalized_currency
    if trade_type not in {"IMPORT", "EXPORT"} or currency is None:
        raise ValueError("확인된 거래 방향과 통화를 결정할 수 없습니다.")

    settlement_date = confirmed_due_date_from_confirmation(
        confirmation
    )
    events = [
        _normalized_event(
            sequence=1,
            trade_type=trade_type,
            currency=currency,
            foreign_amount=extraction.amount_due,
            settlement_date=settlement_date,
        )
    ]

    return _build_binding(
        source_sha256=confirmation.source_sha256,
        trade_type=trade_type,
        currency=currency,
        events=events,
    )


def confirmed_transaction_from_confirmation(
    *,
    extraction: TradeDocumentExtraction,
    validation: ValidationResult,
    confirmation: ConfirmationRecord,
) -> ConfirmedTransactionSnapshot:
    """Materialize the only transaction object allowed after confirmation."""

    binding = confirmed_trade_from_confirmation(
        extraction=extraction,
        validation=validation,
        confirmation=confirmation,
    )
    due_date = confirmed_due_date_from_confirmation(confirmation)
    amount_due = _normalized_amount(
        extraction.amount_due,
        "confirmed transaction amount_due",
    )
    if len(binding.events) != 1:
        raise ValueError(
            "확정 거래 snapshot에는 하나의 분석 대상 예정 노출이 필요합니다."
        )
    event = binding.events[0]
    if event.settlement_date != due_date:
        raise ValueError("확정 거래 snapshot의 결제일이 거래 binding과 다릅니다.")
    if _canonical_amount(event.foreign_amount) != _canonical_amount(
        amount_due
    ):
        raise ValueError("확정 거래 snapshot의 금액이 거래 binding과 다릅니다.")

    installments: List[ConfirmedInstallment] = []
    for index, item in enumerate(extraction.installments):
        sequence = item.sequence or index + 1
        if item.amount is None or item.due_date is None:
            raise ValueError("확정 분할결제 금액과 날짜가 필요합니다.")
        installments.append(
            ConfirmedInstallment(
                sequence=sequence,
                amount=_normalized_amount(
                    item.amount,
                    "confirmed installment amount",
                ),
                currency=_normalized_currency(
                    item.currency or binding.currency,
                    "confirmed installment currency",
                ),
                due_date=date_value(
                    item.due_date,
                    "confirmed installment due_date",
                ).isoformat(),
                condition=item.condition,
            )
        )

    canonical: Dict[str, Any] = {
        "source_sha256": binding.source_sha256,
        "company_role": confirmation.company_role,
        "company_country": confirmation.company_country,
        "trade_type": binding.trade_type,
        "currency": binding.currency,
        "amount_due": _canonical_amount(amount_due),
        "due_date": due_date,
        "contract_date": (
            date_value(
                extraction.contract_date,
                "confirmed transaction contract_date",
            ).isoformat()
            if extraction.contract_date
            else None
        ),
        "shipment_date": (
            date_value(
                extraction.shipment_date,
                "confirmed transaction shipment_date",
            ).isoformat()
            if extraction.shipment_date
            else None
        ),
        "document_type": extraction.document_type,
        "document_number": extraction.document_number,
        "grand_total": extraction.grand_total,
        "issue_date": (
            date_value(
                extraction.issue_date,
                "confirmed transaction issue_date",
            ).isoformat()
            if extraction.issue_date
            else None
        ),
        "seller_name": extraction.seller_name,
        "seller_country": extraction.seller_country,
        "buyer_name": extraction.buyer_name,
        "buyer_country": extraction.buyer_country,
        "payment_terms": extraction.payment_terms,
        "incoterm": extraction.incoterm,
        "installments": [
            item.model_dump() for item in installments
        ],
        "trade_sha256": binding.trade_sha256,
    }
    serialized = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    input_fingerprint = hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()
    return ConfirmedTransactionSnapshot(
        source_filename=confirmation.source_filename,
        source_sha256=binding.source_sha256,
        confirmed_at=confirmation.confirmed_at,
        company_role=confirmation.company_role,
        company_country=confirmation.company_country,
        trade_type=binding.trade_type,
        currency=binding.currency,
        amount_due=amount_due,
        due_date=due_date,
        contract_date=canonical["contract_date"],
        shipment_date=canonical["shipment_date"],
        document_type=extraction.document_type,
        document_number=extraction.document_number,
        grand_total=extraction.grand_total,
        issue_date=canonical["issue_date"],
        seller_name=extraction.seller_name,
        seller_country=extraction.seller_country,
        buyer_name=extraction.buyer_name,
        buyer_country=extraction.buyer_country,
        payment_terms=extraction.payment_terms,
        incoterm=extraction.incoterm,
        installments=installments,
        trade_binding=binding,
        input_fingerprint=input_fingerprint,
    )


def validate_confirmed_transaction_snapshot(
    *,
    snapshot: ConfirmedTransactionSnapshot,
    extraction: TradeDocumentExtraction,
    validation: ValidationResult,
    confirmation: ConfirmationRecord,
) -> None:
    current = confirmed_transaction_from_confirmation(
        extraction=extraction,
        validation=validation,
        confirmation=confirmation,
    )
    if current.input_fingerprint != snapshot.input_fingerprint:
        raise ValueError(
            "확인 기록의 거래값이 canonical confirmed transaction "
            "snapshot과 다릅니다."
        )
    if (
        current.trade_binding.trade_sha256
        != snapshot.trade_binding.trade_sha256
    ):
        raise ValueError(
            "확인 기록의 거래 binding이 canonical snapshot과 다릅니다."
        )


def validate_snapshot_downstream_due_date(
    *,
    snapshot: ConfirmedTransactionSnapshot,
    stage1_target_date: str,
    stage2_dates: Sequence[str],
    consultation_date: Any = None,
    stage5_date: Any = None,
) -> str:
    """Fail closed if any downstream consumer leaves the snapshot date."""

    expected = date_value(
        snapshot.due_date,
        "confirmed_transaction.due_date",
    ).isoformat()
    values = [
        ("stage1.scenario_set.target_date", stage1_target_date),
    ]
    values.extend(
        (
            "stage2.exposures[{}].settlement_date".format(index),
            value,
        )
        for index, value in enumerate(stage2_dates)
    )
    if consultation_date is not None:
        values.append(
            (
                "consultation.company_summary.settlement_date",
                consultation_date,
            )
        )
    if stage5_date is not None:
        values.append(("stage5.report.settlement_date", stage5_date))
    if not stage2_dates:
        raise ValueError("Stage 2 결제·수취일이 없습니다.")
    for field, value in values:
        normalized = date_value(str(value), field).isoformat()
        if normalized != expected:
            raise ValueError(
                "{}가 canonical confirmed due_date와 다릅니다.".format(
                    field
                )
            )
    return expected


def document_input_from_confirmed_transaction(
    snapshot: ConfirmedTransactionSnapshot,
) -> Dict[str, Any]:
    """Project the canonical snapshot into the stable Stage 2 REST contract."""

    event = snapshot.trade_binding.events[0]
    return {
        "schema_version": "1.0.0",
        "source": {
            "type": "DOCUMENT_EXTRACTION",
            "filename": snapshot.source_filename,
            "sha256": snapshot.source_sha256,
            "user_confirmed": True,
            "confirmed_fields": [
                "company_role",
                "trade_type",
                "currency",
                "amount_due",
                "due_date",
            ],
            "confirmed_at": snapshot.confirmed_at,
            "confirmed_transaction_fingerprint": (
                snapshot.input_fingerprint
            ),
        },
        "trade": {
            "trade_type": snapshot.trade_type,
            "currency": snapshot.currency,
            "foreign_amount": snapshot.amount_due,
            "contract_date": snapshot.contract_date,
            "shipment_date": snapshot.shipment_date,
            "settlement_date": snapshot.due_date,
            "settlement_date_source": (
                "workflow.confirmed_transaction.due_date"
            ),
            "cashflow_events": [
                {
                    "sequence": event.sequence,
                    "currency": event.currency,
                    "foreign_amount": event.foreign_amount,
                    "settlement_date": event.settlement_date,
                    "condition": snapshot.payment_terms,
                }
            ],
            "installment_schedule": [
                {
                    "sequence": item.sequence,
                    "currency": item.currency,
                    "foreign_amount": item.amount,
                    "settlement_date": item.due_date,
                    "condition": item.condition,
                }
                for item in snapshot.installments
            ],
            "available_foreign_currency": "0",
        },
        "company_cash": {
            "current_krw_cash": None,
            "minimum_cash_buffer": None,
            "acceptable_loss": None,
        },
        "krw_cashflows": [],
        "status": "NEEDS_COMPANY_CASH_INPUT",
    }


def confirmed_trade_from_document_input(
    document_input: Dict[str, Any],
) -> ConfirmedTradeBinding:
    source = document_input.get("source")
    trade = document_input.get("trade")
    if not isinstance(source, dict) or not isinstance(trade, dict):
        raise ValueError("확인된 Stage 0 문서 입력이 필요합니다.")
    if source.get("user_confirmed") is not True:
        raise ValueError("사용자 확인된 Stage 0 문서 입력이 필요합니다.")
    confirmed_fields = source.get("confirmed_fields")
    if not isinstance(confirmed_fields, list) or not {
        "company_role",
        "trade_type",
        "currency",
        "amount_due",
        "due_date",
    }.issubset(set(confirmed_fields)):
        raise ValueError(
            "회사 역할·거래 방향·통화·금액·결제일 확인 기록이 필요합니다."
        )

    trade_type = trade.get("trade_type")
    currency = trade.get("currency")
    cashflow_events = trade.get("cashflow_events")
    if not isinstance(cashflow_events, list) or not cashflow_events:
        raise ValueError("확인된 결제 현금흐름이 필요합니다.")

    events: List[ConfirmedTradeEvent] = []
    for item in cashflow_events:
        if not isinstance(item, dict):
            raise ValueError("확인된 결제 현금흐름 형식이 올바르지 않습니다.")
        events.append(
            _normalized_event(
                sequence=item.get("sequence"),
                trade_type=trade_type,
                currency=item.get("currency"),
                foreign_amount=item.get("foreign_amount"),
                settlement_date=item.get("settlement_date"),
            )
        )

    declared_total = _normalized_amount(
        trade.get("foreign_amount"),
        "confirmed trade foreign_amount",
    )
    event_total = sum(
        (
            decimal_value(item.foreign_amount, "confirmed event amount")
            for item in events
        ),
        decimal_value("0", "confirmed event total"),
    )
    if decimal_value(declared_total, "confirmed trade total") != event_total:
        raise ValueError("확인된 거래금액과 결제 이벤트 합계가 다릅니다.")

    return _build_binding(
        source_sha256=source.get("sha256"),
        trade_type=trade_type,
        currency=currency,
        events=events,
    )


def confirmed_analysis_due_date_from_document_input(
    document_input: Dict[str, Any],
) -> str:
    """Read the canonical UI/Stage 1 date and reject schedule fallbacks."""

    trade = document_input.get("trade")
    if not isinstance(trade, dict):
        raise ValueError("확정 거래 snapshot이 필요합니다.")
    raw_due_date = trade.get("settlement_date")
    if not raw_due_date:
        raise ValueError(
            "확정 거래 snapshot에 결제일이 없습니다. 계약일이나 첫 "
            "분할결제일을 대신 사용하지 않습니다."
        )
    due_date = date_value(
        str(raw_due_date),
        "trade.settlement_date",
    ).isoformat()
    binding = confirmed_trade_from_document_input(document_input)
    if len(binding.events) != 1:
        raise ValueError(
            "금융분석용 확정 거래는 하나의 예정 노출 이벤트여야 합니다."
        )
    if binding.events[0].settlement_date != due_date:
        raise ValueError(
            "금융분석용 거래 이벤트의 날짜가 확정 결제일과 다릅니다."
        )
    return due_date


def validate_stage2_trade_binding(
    *,
    expected: ConfirmedTradeBinding,
    stage2_input: Stage2Input,
) -> None:
    if stage2_input.confirmed_trade_sha256 is None:
        raise ValueError("Stage 2 입력에 확인된 거래 fingerprint가 없습니다.")
    if stage2_input.confirmed_trade_sha256 != expected.trade_sha256:
        raise ValueError("Stage 2 입력의 거래 fingerprint가 확인 기록과 다릅니다.")
    if len(stage2_input.exposures) != len(expected.events):
        raise ValueError("Stage 2 결제 이벤트 개수가 확인 기록과 다릅니다.")

    for expected_event, actual in zip(
        expected.events,
        stage2_input.exposures,
    ):
        if actual.sequence != expected_event.sequence:
            raise ValueError("Stage 2 거래 sequence가 확인 기록과 다릅니다.")
        if actual.trade_type != expected_event.trade_type:
            raise ValueError("Stage 2 거래 방향이 확인 기록과 다릅니다.")
        if actual.currency != expected_event.currency:
            raise ValueError("Stage 2 거래 통화가 확인 기록과 다릅니다.")
        if (
            decimal_value(actual.foreign_amount, "Stage 2 foreign_amount")
            != decimal_value(
                expected_event.foreign_amount,
                "confirmed trade foreign_amount",
            )
        ):
            raise ValueError("Stage 2 거래금액이 확인 기록과 다릅니다.")
        actual_settlement = date_value(
            actual.settlement_date,
            "Stage 2 settlement_date",
        ).isoformat()
        if actual_settlement != expected_event.settlement_date:
            raise ValueError("Stage 2 결제일이 확인 기록과 다릅니다.")
