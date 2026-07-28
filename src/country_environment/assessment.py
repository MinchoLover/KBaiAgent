import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

from src.country_environment.snapshot import (
    COUNTRY_ENVIRONMENT_SNAPSHOT_VERSION,
    CountrySnapshotError,
    load_country_environment_snapshot,
)
from src.domain.country_environment_models import (
    CountryEnvironmentReviewNeed,
    CountryEnvironmentRuleContribution,
    CountryEnvironmentSnapshot,
    CountryEnvironmentTrace,
    CountryReviewPriority,
    CountrySnapshotSourceRecord,
    CountryTradeEnvironmentAssessment,
    CountryTradeEnvironmentInput,
    OecdPaymentTransferSignal,
    OfficialSourceReference,
    WorldBankIndicatorObservation,
    WorldBankMacroEnvironmentSignal,
    WtoTradeMarketAccessSignal,
    WtoTradeObservation,
)


COUNTRY_ENVIRONMENT_RULE_VERSION = "country-environment-rules-1.0"
COUNTRY_ENVIRONMENT_DISCLAIMER = (
    "거래 검토 우선순위는 국가 신용등급·부도확률·은행 공식 심사등급이 "
    "아니며 보험·보증·신용장·결제조건 상담 순서를 정리한 것입니다."
)
ZERO_HASH = "0" * 64
INDICATOR_NAMES = {
    "NY.GDP.MKTP.KD.ZG": "GDP growth (annual %)",
    "FP.CPI.TOTL.ZG": "Inflation, consumer prices (annual %)",
    "BN.CAB.XOKA.GD.ZS": "Current account balance (% of GDP)",
}


def _dedupe(values: List[str]) -> List[str]:
    return list(dict.fromkeys(values))


def _records_for_country(
    snapshot: CountryEnvironmentSnapshot,
    country: str,
) -> List[CountrySnapshotSourceRecord]:
    return sorted(
        [
            item for item in snapshot.source_records
            if item.country == country
        ],
        key=lambda item: item.source_record_id,
    )


def country_environment_fingerprint(
    *,
    value: CountryTradeEnvironmentInput,
    snapshot_version: str,
    snapshot_hash: str,
    source_record_ids: List[str],
) -> str:
    canonical = {
        "input": value.model_dump(),
        "snapshot_version": snapshot_version,
        "snapshot_hash": snapshot_hash,
        "rule_version": COUNTRY_ENVIRONMENT_RULE_VERSION,
        "source_record_ids": sorted(source_record_ids),
    }
    serialized = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _source_reference(
    record: CountrySnapshotSourceRecord,
) -> OfficialSourceReference:
    return OfficialSourceReference(
        source_record_id=record.source_record_id,
        source_name=record.source_name,
        source_axis=record.source_axis,
        official_url=record.official_url,
        source_title=record.source_title,
        as_of_date=record.as_of_date,
        observation_period=record.observation_period,
        verified_at=record.verified_at,
    )


def _unavailable_assessment(
    *,
    value: CountryTradeEnvironmentInput,
    reason: str,
    warning_code: str,
    snapshot_version: str,
    snapshot_id: str,
    snapshot_hash: str,
    source_record_ids: Optional[List[str]] = None,
) -> CountryTradeEnvironmentAssessment:
    record_ids = source_record_ids or []
    fingerprint = country_environment_fingerprint(
        value=value,
        snapshot_version=snapshot_version,
        snapshot_hash=snapshot_hash,
        source_record_ids=record_ids,
    )
    return CountryTradeEnvironmentAssessment(
        country=value.counterparty_country,
        trade_type=value.trade_type,
        review_priority="INSUFFICIENT_INFORMATION",
        oecd_payment_transfer=OecdPaymentTransferSignal(
            status="DATA_UNAVAILABLE",
            raw_classification=None,
            raw_unit="OECD 0-7 classification where classified",
            as_of_date="DATA_UNAVAILABLE",
            interpretation="검증된 OECD 원자료를 확인할 수 없습니다.",
            limitations=reason,
        ),
        world_bank_macro_environment=WorldBankMacroEnvironmentSignal(
            status="DATA_UNAVAILABLE",
            observations=[],
            warnings=[reason],
            interpretation="검증된 거시환경 관측값을 확인할 수 없습니다.",
            limitations=[reason],
        ),
        wto_trade_market_access=WtoTradeMarketAccessSignal(
            status="DATA_UNAVAILABLE",
            observations=[],
            interpretation="검증된 무역·시장접근 자료를 확인할 수 없습니다.",
            limitations=[reason],
        ),
        review_needs=["INFORMATION_COMPLETENESS_REVIEW"],
        rule_contributions=[
            CountryEnvironmentRuleContribution(
                rule_code=warning_code,
                source_axis=None,
                observed_value_or_status="DATA_UNAVAILABLE",
                review_need="INFORMATION_COMPLETENESS_REVIEW",
                priority_direction="FAIL_CLOSED",
                reason=reason,
            )
        ],
        reasons=[reason],
        warnings=[COUNTRY_ENVIRONMENT_DISCLAIMER, reason],
        warning_codes=[warning_code],
        assumptions=[],
        limitations=[reason],
        official_source_references=[],
        snapshot_version=snapshot_version,
        snapshot_id=snapshot_id,
        snapshot_hash=snapshot_hash,
        rule_version=COUNTRY_ENVIRONMENT_RULE_VERSION,
        source_record_ids=record_ids,
        input_fingerprint=fingerprint,
    )


def _oecd_signal(
    record: CountrySnapshotSourceRecord,
) -> OecdPaymentTransferSignal:
    if record.raw_status == "CLASSIFIED":
        actions = (
            ["PAYMENT_TRANSFER_PROTECTION_REVIEW_REQUIRED"]
            if record.raw_value == 4
            else []
        )
        return OecdPaymentTransferSignal(
            status="CLASSIFIED",
            raw_classification=int(record.raw_value),
            raw_unit=record.raw_unit,
            as_of_date=record.as_of_date,
            interpretation=record.interpretation,
            limitations=record.limitations,
            action_signals=actions,
            source_record_id=record.source_record_id,
        )
    return OecdPaymentTransferSignal(
        status="HIGH_INCOME_OECD_UNCLASSIFIED",
        raw_classification=None,
        raw_unit=record.raw_unit,
        as_of_date=record.as_of_date,
        interpretation=record.interpretation,
        limitations=record.limitations,
        action_signals=[],
        source_record_id=record.source_record_id,
    )


def _world_bank_signal(
    records: List[CountrySnapshotSourceRecord],
) -> WorldBankMacroEnvironmentSignal:
    observations = [
        WorldBankIndicatorObservation(
            source_record_id=item.source_record_id,
            indicator_code=str(item.indicator_code),
            indicator_name=INDICATOR_NAMES[str(item.indicator_code)],
            raw_value=(
                str(item.raw_value)
                if item.raw_value is not None
                else None
            ),
            raw_status=item.raw_status,
            raw_unit=item.raw_unit,
            as_of_date=item.as_of_date,
            observation_period=item.observation_period,
            interpretation=item.interpretation,
            limitations=item.limitations,
        )
        for item in sorted(
            records,
            key=lambda row: str(row.indicator_code),
        )
    ]
    periods = {item.observation_period for item in observations}
    warnings = []
    if len(periods) > 1:
        warnings.append(
            "World Bank 지표의 최신 비결측 관측연도가 서로 달라 같은 "
            "시점 자료로 비교하지 않았습니다."
        )
    return WorldBankMacroEnvironmentSignal(
        status="AVAILABLE",
        observations=observations,
        warnings=warnings,
        interpretation=(
            "거시환경 원값과 관측연도를 상담 문맥으로만 제공하며 "
            "임의 임계값·점수·환율예측에 사용하지 않았습니다."
        ),
        limitations=_dedupe([item.limitations for item in observations]),
    )


def _wto_signal(
    records: List[CountrySnapshotSourceRecord],
) -> WtoTradeMarketAccessSignal:
    observations = [
        WtoTradeObservation(
            source_record_id=item.source_record_id,
            indicator_code=str(item.indicator_code),
            raw_value=(
                str(item.raw_value)
                if item.raw_value is not None
                else None
            ),
            raw_status=item.raw_status,
            raw_unit=item.raw_unit,
            as_of_date=item.as_of_date,
            observation_period=item.observation_period,
            interpretation=item.interpretation,
            limitations=item.limitations,
        )
        for item in sorted(
            records,
            key=lambda row: str(row.indicator_code),
        )
    ]
    return WtoTradeMarketAccessSignal(
        status="AVAILABLE",
        observations=observations,
        interpretation=(
            "WTO 자료는 통관·관세·시장접근 조건을 재확인할 근거이며 "
            "국가 신용위험이나 상품 승인 판단으로 변환하지 않았습니다."
        ),
        limitations=_dedupe([item.limitations for item in observations]),
    )


def assess_country_trade_environment(
    value: CountryTradeEnvironmentInput,
    *,
    snapshot: Optional[CountryEnvironmentSnapshot] = None,
    snapshot_path: Optional[Path] = None,
) -> CountryTradeEnvironmentAssessment:
    try:
        effective_snapshot = snapshot or load_country_environment_snapshot(
            snapshot_path
        )
    except CountrySnapshotError:
        return _unavailable_assessment(
            value=value,
            reason=(
                "versioned offline snapshot이 없거나 schema·version·hash "
                "검증에 실패했습니다."
            ),
            warning_code="SNAPSHOT_VALIDATION_FAILED",
            snapshot_version=COUNTRY_ENVIRONMENT_SNAPSHOT_VERSION,
            snapshot_id="SNAPSHOT_UNAVAILABLE",
            snapshot_hash=ZERO_HASH,
        )

    if value.counterparty_country not in (
        effective_snapshot.supported_countries
    ):
        return _unavailable_assessment(
            value=value,
            reason=(
                "{}는 v1 공식 snapshot 지원 국가가 아닙니다.".format(
                    value.counterparty_country
                )
            ),
            warning_code="UNSUPPORTED_COUNTRY",
            snapshot_version=effective_snapshot.snapshot_version,
            snapshot_id=effective_snapshot.snapshot_id,
            snapshot_hash=effective_snapshot.snapshot_hash,
        )

    records = _records_for_country(
        effective_snapshot,
        value.counterparty_country,
    )
    by_axis: Dict[str, List[CountrySnapshotSourceRecord]] = {}
    for record in records:
        by_axis.setdefault(record.source_axis, []).append(record)
    if any(
        not by_axis.get(axis)
        for axis in (
            "OECD_PAYMENT_TRANSFER",
            "WORLD_BANK_MACRO_ENVIRONMENT",
            "WTO_TRADE_MARKET_ACCESS",
        )
    ):
        return _unavailable_assessment(
            value=value,
            reason="핵심 공식 source provenance가 누락되었습니다.",
            warning_code="SOURCE_PROVENANCE_MISSING",
            snapshot_version=effective_snapshot.snapshot_version,
            snapshot_id=effective_snapshot.snapshot_id,
            snapshot_hash=effective_snapshot.snapshot_hash,
            source_record_ids=[
                item.source_record_id for item in records
            ],
        )

    oecd = _oecd_signal(by_axis["OECD_PAYMENT_TRANSFER"][0])
    world_bank = _world_bank_signal(
        by_axis["WORLD_BANK_MACRO_ENVIRONMENT"]
    )
    wto = _wto_signal(by_axis["WTO_TRADE_MARKET_ACCESS"])
    priority: CountryReviewPriority = "STANDARD_REVIEW"
    needs: List[CountryEnvironmentReviewNeed] = [
        "MACRO_ENVIRONMENT_MONITORING",
        "TRADE_MARKET_ACCESS_REVIEW",
    ]
    contributions: List[CountryEnvironmentRuleContribution] = []
    reasons: List[str] = []
    warning_codes: List[str] = []

    if oecd.status == "HIGH_INCOME_OECD_UNCLASSIFIED":
        reason = (
            "미국은 고소득 OECD 회원국 미분류이며 이를 0·LOW·안전 또는 "
            "위험 감경으로 변환하지 않았습니다."
        )
        reasons.append(reason)
        contributions.append(
            CountryEnvironmentRuleContribution(
                rule_code="OECD_HIGH_INCOME_UNCLASSIFIED_NOT_MITIGANT",
                source_axis="OECD_PAYMENT_TRANSFER",
                observed_value_or_status=oecd.status,
                priority_direction="NO_CHANGE",
                reason=reason,
            )
        )
        warning_codes.append("OECD_UNCLASSIFIED_NOT_LOW")
    elif (
        "PAYMENT_TRANSFER_PROTECTION_REVIEW_REQUIRED"
        in oecd.action_signals
    ):
        reason = (
            "Brazil OECD 공식 원자료 분류 4를 자체 국가등급으로 바꾸지 "
            "않고 지급·이전 보호수단 검토 신호로만 사용했습니다."
        )
        reasons.append(reason)
        needs.append("PAYMENT_TRANSFER_PROTECTION_REVIEW")
        contributions.append(
            CountryEnvironmentRuleContribution(
                rule_code="OECD_CLASSIFICATION_4_PROTECTION_REVIEW",
                source_axis="OECD_PAYMENT_TRANSFER",
                observed_value_or_status="4",
                review_need="PAYMENT_TRANSFER_PROTECTION_REVIEW",
                priority_direction="NO_CHANGE",
                reason=reason,
            )
        )

    unprotected_long_open_account = bool(
        value.balance_payment_method == "OPEN_ACCOUNT"
        and value.payment_term_days is not None
        and value.payment_term_days >= 90
        and value.protection_information_status == "NONE_CONFIRMED"
        and not value.protection_mechanisms
    )
    if unprotected_long_open_account:
        priority = "ELEVATED_REVIEW"
        needs.extend(
            [
                "CREDIT_INSURANCE_REVIEW",
                "GUARANTEE_REVIEW",
                "DOCUMENTARY_CREDIT_TERMS_REVIEW",
                "PAYMENT_TERMS_REVIEW",
            ]
        )
        reason = (
            "90일 이상 Open Account이며 보험·보증 등 보호수단이 없다고 "
            "확인되어 최소 추가 검토가 필요합니다."
        )
        reasons.append(reason)
        contributions.append(
            CountryEnvironmentRuleContribution(
                rule_code="OPEN_ACCOUNT_90_DAY_UNPROTECTED",
                source_axis=None,
                observed_value_or_status=(
                    "OPEN_ACCOUNT/{}D/NONE_CONFIRMED".format(
                        value.payment_term_days
                    )
                ),
                review_need="PAYMENT_TERMS_REVIEW",
                priority_direction="MINIMUM_ELEVATED_REVIEW",
                reason=reason,
            )
        )

    if (
        unprotected_long_open_account
        and "PAYMENT_TRANSFER_PROTECTION_REVIEW_REQUIRED"
        in oecd.action_signals
    ):
        priority = "HIGH_REVIEW"
        reason = (
            "동일한 90일 이상 무보호 Open Account 조건에 OECD 지급·이전 "
            "보호 검토 신호가 추가되어 보호수단을 우선 검토합니다."
        )
        reasons.append(reason)
        contributions.append(
            CountryEnvironmentRuleContribution(
                rule_code="PAYMENT_TRANSFER_SIGNAL_WITH_UNPROTECTED_TERMS",
                source_axis="OECD_PAYMENT_TRANSFER",
                observed_value_or_status="4+UNPROTECTED_OPEN_ACCOUNT",
                review_need="PAYMENT_TRANSFER_PROTECTION_REVIEW",
                priority_direction="RAISE_TO_HIGH_REVIEW",
                reason=reason,
            )
        )

    contributions.extend(
        [
            CountryEnvironmentRuleContribution(
                rule_code="WORLD_BANK_CONTEXT_ONLY",
                source_axis="WORLD_BANK_MACRO_ENVIRONMENT",
                observed_value_or_status="SEPARATE_RAW_INDICATORS",
                review_need="MACRO_ENVIRONMENT_MONITORING",
                priority_direction="NO_CHANGE",
                reason=world_bank.interpretation,
            ),
            CountryEnvironmentRuleContribution(
                rule_code="WTO_MARKET_ACCESS_CONTEXT_ONLY",
                source_axis="WTO_TRADE_MARKET_ACCESS",
                observed_value_or_status="MEMBERSHIP_TARIFF_TPR",
                review_need="TRADE_MARKET_ACCESS_REVIEW",
                priority_direction="NO_CHANGE",
                reason=wto.interpretation,
            ),
        ]
    )
    warnings = [COUNTRY_ENVIRONMENT_DISCLAIMER] + world_bank.warnings
    if world_bank.warnings:
        warning_codes.append("WORLD_BANK_OBSERVATION_PERIOD_MISMATCH")
    source_record_ids = [item.source_record_id for item in records]
    fingerprint = country_environment_fingerprint(
        value=value,
        snapshot_version=effective_snapshot.snapshot_version,
        snapshot_hash=effective_snapshot.snapshot_hash,
        source_record_ids=source_record_ids,
    )
    limitations = _dedupe(
        [oecd.limitations]
        + world_bank.limitations
        + wto.limitations
    )
    return CountryTradeEnvironmentAssessment(
        country=value.counterparty_country,
        trade_type=value.trade_type,
        review_priority=priority,
        oecd_payment_transfer=oecd,
        world_bank_macro_environment=world_bank,
        wto_trade_market_access=wto,
        review_needs=_dedupe(needs),
        rule_contributions=contributions,
        reasons=_dedupe(reasons),
        warnings=_dedupe(warnings),
        warning_codes=_dedupe(warning_codes),
        assumptions=[
            "payment_term_days는 확인된 calendar day 조건으로 사용했습니다.",
            "세 공식 축은 합산·가중평균하지 않았습니다.",
        ],
        limitations=limitations,
        official_source_references=[
            _source_reference(item) for item in records
        ],
        snapshot_version=effective_snapshot.snapshot_version,
        snapshot_id=effective_snapshot.snapshot_id,
        snapshot_hash=effective_snapshot.snapshot_hash,
        rule_version=COUNTRY_ENVIRONMENT_RULE_VERSION,
        source_record_ids=source_record_ids,
        input_fingerprint=fingerprint,
    )


def country_environment_trace(
    assessment: CountryTradeEnvironmentAssessment,
) -> CountryEnvironmentTrace:
    return CountryEnvironmentTrace(
        country=assessment.country,
        snapshot_id=assessment.snapshot_id,
        rule_version=assessment.rule_version,
        review_priority=assessment.review_priority,
        source_record_ids=assessment.source_record_ids,
        warning_codes=assessment.warning_codes,
        metadata={"snapshot_version": assessment.snapshot_version},
    )
