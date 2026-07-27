import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Set, Tuple

from schemas import (
    FieldEvidence,
    NormalizationAuditEntry,
    PaymentInstallment,
    TradeDocumentExtraction,
)


EMPTY_PLACEHOLDERS = {
    "",
    "yyyy-mm-dd",
    "none",
    "null",
    "n/a",
    "-",
}


def _alias_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = normalized.replace(".", "")
    normalized = re.sub(r"[,;:/()_\-]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


COUNTRY_ALIASES: Dict[str, str] = {
    "us": "US",
    "usa": "US",
    "united states": "US",
    "united states of america": "US",
    "kr": "KR",
    "republic of korea": "KR",
    "south korea": "KR",
    "korea republic of": "KR",
    "republic of korea south korea": "KR",
    "대한민국": "KR",
    "한국": "KR",
    "gb": "GB",
    "uk": "GB",
    "united kingdom": "GB",
    "great britain": "GB",
    "cn": "CN",
    "china": "CN",
    "people s republic of china": "CN",
    "jp": "JP",
    "japan": "JP",
    "de": "DE",
    "germany": "DE",
    "fr": "FR",
    "france": "FR",
    "french republic": "FR",
    "nl": "NL",
    "netherlands": "NL",
    "the netherlands": "NL",
    "kingdom of the netherlands": "NL",
    "no": "NO",
    "norway": "NO",
    "kingdom of norway": "NO",
    "vn": "VN",
    "viet nam": "VN",
    "vietnam": "VN",
    "sg": "SG",
    "singapore": "SG",
    "ca": "CA",
    "canada": "CA",
    "au": "AU",
    "australia": "AU",
    "commonwealth of australia": "AU",
    "tw": "TW",
    "taiwan": "TW",
    "taiwan roc": "TW",
    "republic of china": "TW",
}


def normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", str(value)).strip()
    return normalized or None


def normalize_date_text(value: Optional[str]) -> Optional[str]:
    normalized = normalize_optional_text(value)
    if normalized is None:
        return None
    if normalized.casefold() in EMPTY_PLACEHOLDERS:
        return None
    return normalized


def normalize_decimal_text(value: Optional[str]) -> Optional[str]:
    normalized = normalize_optional_text(value)
    if normalized is None:
        return None
    cleaned = (
        normalized.replace(",", "")
        .replace("$", "")
        .replace("€", "")
        .replace("£", "")
        .replace("¥", "")
        .replace("₩", "")
        .strip()
    )
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", cleaned):
        return normalized
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation:
        return normalized
    if not parsed.is_finite():
        return normalized
    return format(parsed, "f")


def normalize_country_name(
    value: Optional[str],
    field: str,
) -> Tuple[Optional[str], NormalizationAuditEntry]:
    raw_input = None if value is None else str(value)
    raw = normalize_optional_text(value)
    if raw is None:
        return None, NormalizationAuditEntry(
            field=field,
            raw_value=raw_input,
            normalized_value=None,
            status="EMPTY",
            message="{} 값이 비어 있습니다.".format(field),
        )
    if re.fullmatch(r"[A-Za-z]{2}", raw):
        normalized_code = raw.upper()
        return normalized_code, NormalizationAuditEntry(
            field=field,
            raw_value=raw_input,
            normalized_value=normalized_code,
            status=(
                "UNCHANGED"
                if raw == normalized_code
                else "NORMALIZED"
            ),
            message=(
                "{} 국가 코드를 {}로 사용합니다.".format(
                    field,
                    normalized_code,
                )
            ),
        )

    alias = COUNTRY_ALIASES.get(_alias_key(raw))
    if alias is not None:
        return alias, NormalizationAuditEntry(
            field=field,
            raw_value=raw_input,
            normalized_value=alias,
            status="NORMALIZED",
            message=(
                "{}가 '{}'로 추출되어 내부적으로 '{}' 코드로 "
                "정규화했습니다.".format(field, raw, alias)
            ),
        )
    return raw, NormalizationAuditEntry(
        field=field,
        raw_value=raw_input,
        normalized_value=raw,
        status="UNKNOWN_ALIAS",
        message=(
            "{}의 국가명 '{}'에 대응하는 확인된 ISO 별칭이 없어 "
            "원본을 유지했습니다.".format(field, raw)
        ),
    )


def country_alias_matches_text(text: str, country_code: str) -> bool:
    normalized_code = country_code.strip().upper()
    if re.search(
        r"(?<![A-Za-z]){}(?![A-Za-z])".format(
            re.escape(normalized_code)
        ),
        text,
    ):
        return True
    normalized_text = " {} ".format(_alias_key(text))
    aliases = [
        alias
        for alias, code in COUNTRY_ALIASES.items()
        if code == normalized_code and len(alias) > 2
    ]
    return any(
        " {} ".format(alias) in normalized_text
        for alias in aliases
    )


def _audit_change(
    field: str,
    raw_value: Optional[str],
    normalized_value: Optional[str],
    status: str,
    message: str,
) -> Optional[NormalizationAuditEntry]:
    if raw_value == normalized_value:
        return None
    return NormalizationAuditEntry(
        field=field,
        raw_value=raw_value,
        normalized_value=normalized_value,
        status=status,
        message=message,
    )


def normalize_extraction_values(
    extraction: TradeDocumentExtraction,
) -> Tuple[TradeDocumentExtraction, List[NormalizationAuditEntry]]:
    audit: List[NormalizationAuditEntry] = []
    seller_country, seller_audit = normalize_country_name(
        extraction.seller_country,
        "seller_country",
    )
    buyer_country, buyer_audit = normalize_country_name(
        extraction.buyer_country,
        "buyer_country",
    )
    for item in (seller_audit, buyer_audit):
        if item.status != "EMPTY":
            audit.append(item)

    updates = {
        "seller_country": seller_country,
        "buyer_country": buyer_country,
        "issue_date": normalize_date_text(extraction.issue_date),
        "contract_date": normalize_date_text(extraction.contract_date),
        "shipment_date": normalize_date_text(extraction.shipment_date),
        "explicit_due_date": normalize_date_text(
            extraction.explicit_due_date
        ),
        "currency": (
            normalize_optional_text(extraction.currency).upper()
            if normalize_optional_text(extraction.currency)
            else None
        ),
        "grand_total": normalize_decimal_text(extraction.grand_total),
        "amount_due": normalize_decimal_text(extraction.amount_due),
    }
    for field in (
        "issue_date",
        "contract_date",
        "shipment_date",
        "explicit_due_date",
        "grand_total",
        "amount_due",
        "currency",
    ):
        raw_value = getattr(extraction, field)
        normalized_value = updates[field]
        entry = _audit_change(
            field,
            raw_value,
            normalized_value,
            "NORMALIZED",
            "{} 값을 검증 전에 정규화했습니다.".format(field),
        )
        if entry is not None:
            audit.append(entry)

    installments: List[PaymentInstallment] = []
    for installment in extraction.installments:
        installments.append(
            installment.model_copy(
                update={
                    "amount": normalize_decimal_text(installment.amount),
                    "currency": (
                        normalize_optional_text(
                            installment.currency
                        ).upper()
                        if normalize_optional_text(installment.currency)
                        else None
                    ),
                    "due_date": normalize_date_text(
                        installment.due_date
                    ),
                    "condition": normalize_optional_text(
                        installment.condition
                    ),
                }
            )
        )
    updates["installments"] = installments
    return extraction.model_copy(update=updates), audit


def _currency_codes_in_text(
    text: str,
    supported_codes: Set[str],
) -> Set[str]:
    candidates = set(
        re.findall(r"(?<![A-Za-z])([A-Za-z]{3})(?![A-Za-z])", text)
    )
    return {
        item.upper()
        for item in candidates
        if item.upper() in supported_codes
    }


def augment_currency_evidence(
    extraction: TradeDocumentExtraction,
    supported_codes: Set[str],
) -> Tuple[TradeDocumentExtraction, List[NormalizationAuditEntry]]:
    currency = extraction.currency
    if currency is None or currency not in supported_codes:
        return extraction, []
    if any(item.field == "currency" for item in extraction.evidence):
        return extraction, []

    for item in extraction.evidence:
        if (
            item.field not in {"amount_due", "grand_total", "installments"}
            or item.extraction_type == "INFERRED"
        ):
            continue
        currencies = _currency_codes_in_text(
            item.source_text,
            supported_codes,
        )
        if currencies != {currency}:
            continue
        generated = FieldEvidence(
            field="currency",
            page=item.page,
            source_text=item.source_text,
            extraction_type="EXPLICIT",
            confidence_reason=(
                "{} evidence의 실제 원문에 통화 코드 {}가 직접 "
                "표기되어 동일 근거를 연결했습니다.".format(
                    item.field,
                    currency,
                )
            ),
        )
        updated = extraction.model_copy(
            update={"evidence": list(extraction.evidence) + [generated]}
        )
        return updated, [
            NormalizationAuditEntry(
                field="currency",
                raw_value=currency,
                normalized_value=currency,
                status="EVIDENCE_LINKED",
                message=(
                    "{} 원문 근거에서 명시 통화 {} evidence를 "
                    "안전하게 연결했습니다.".format(item.field, currency)
                ),
            )
        ]
    return extraction, []
