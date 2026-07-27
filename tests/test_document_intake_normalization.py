import json
import unittest
from pathlib import Path

from schemas import ConfirmationState, FieldEvidence, TradeDocumentExtraction
from src.document_intake.confirmation import (
    create_confirmation_record,
    validate_confirmation,
)
from src.document_intake.normalization import (
    augment_currency_evidence,
    normalize_country_name,
    normalize_date_text,
)
from validators import (
    ISO_4217_CODES,
    apply_deterministic_review_state,
    build_stage2_input,
    calculate_net_due_date,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    ROOT / "tests" / "fixtures" / "kbfx_sales_contract_extraction.json"
)


def raw_contract() -> TradeDocumentExtraction:
    return TradeDocumentExtraction.model_validate(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    )


def issue_codes(validation):
    return {item.code for item in validation.issues}


class CountryNormalizationTests(unittest.TestCase):
    def test_required_aliases_normalize_to_iso_alpha_2(self):
        aliases = {
            "United States": "US",
            "United States of America": "US",
            "USA": "US",
            "U.S.A.": "US",
            "US": "US",
            "Republic of Korea": "KR",
            "South Korea": "KR",
            "Korea, Republic of": "KR",
            "Republic of Korea (South Korea)": "KR",
            "대한민국": "KR",
            "한국": "KR",
            "KR": "KR",
        }
        for source, expected in aliases.items():
            with self.subTest(source=source):
                normalized, audit = normalize_country_name(
                    source,
                    "country",
                )
                self.assertEqual(normalized, expected)
                self.assertEqual(audit.raw_value, source)

    def test_alias_matching_ignores_case_spaces_and_punctuation(self):
        normalized, audit = normalize_country_name(
            "  u.s.a.  ",
            "seller_country",
        )
        self.assertEqual(normalized, "US")
        self.assertEqual(audit.raw_value, "  u.s.a.  ")

    def test_unknown_country_is_preserved_and_warned(self):
        normalized, audit = normalize_country_name(
            "Atlantis",
            "seller_country",
        )
        self.assertEqual(normalized, "Atlantis")
        self.assertEqual(audit.status, "UNKNOWN_ALIAS")


class TradeTypeDerivationTests(unittest.TestCase):
    def test_buyer_korea_and_seller_us_is_import(self):
        extraction, validation = apply_deterministic_review_state(
            raw_contract(),
            company_role="BUYER",
            company_country="KR",
        )
        self.assertEqual(extraction.seller_country, "US")
        self.assertEqual(extraction.buyer_country, "KR")
        self.assertEqual(extraction.trade_type, "IMPORT")
        self.assertEqual(validation.auto_trade_type, "IMPORT")
        self.assertEqual(validation.trade_type_source, "AUTO")

    def test_seller_korea_and_buyer_us_is_export(self):
        raw = raw_contract().model_copy(
            update={
                "company_role": "SELLER",
                "seller_country": "Republic of Korea",
                "buyer_country": "United States",
            }
        )
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="SELLER",
            company_country="대한민국",
        )
        self.assertEqual(extraction.trade_type, "EXPORT")
        self.assertEqual(validation.auto_trade_type, "EXPORT")

    def test_domestic_trade_remains_unknown(self):
        raw = raw_contract().model_copy(
            update={"seller_country": "Republic of Korea"}
        )
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertEqual(extraction.trade_type, "UNKNOWN")
        self.assertIn("MISSING_REQUIRED_FIELD", issue_codes(validation))

    def test_role_country_conflict_remains_unknown_with_warning(self):
        raw = raw_contract().model_copy(
            update={
                "seller_country": "Republic of Korea",
                "buyer_country": "United States",
            }
        )
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertEqual(extraction.trade_type, "UNKNOWN")
        self.assertIn(
            "COMPANY_COUNTRY_ROLE_MISMATCH",
            issue_codes(validation),
        )

    def test_explicit_user_trade_type_wins_and_conflict_is_recorded(self):
        extraction, validation = apply_deterministic_review_state(
            raw_contract(),
            company_role="BUYER",
            company_country="KR",
            user_trade_type="EXPORT",
        )
        self.assertEqual(extraction.trade_type, "EXPORT")
        self.assertEqual(validation.auto_trade_type, "IMPORT")
        self.assertEqual(validation.trade_type_source, "USER_OVERRIDE")
        self.assertIn(
            "TRADE_TYPE_OVERRIDE_CONFLICT",
            issue_codes(validation),
        )


class EvidenceNormalizationTests(unittest.TestCase):
    def test_currency_evidence_is_linked_from_real_amount_source(self):
        extraction, audit = augment_currency_evidence(
            raw_contract(),
            ISO_4217_CODES,
        )
        evidence = [
            item
            for item in extraction.evidence
            if item.field == "currency"
        ]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(
            evidence[0].source_text,
            "Total Contract Price: USD 100,000.00",
        )
        self.assertEqual(evidence[0].extraction_type, "EXPLICIT")
        self.assertEqual(audit[0].status, "EVIDENCE_LINKED")

    def test_currency_evidence_is_not_invented_without_source_code(self):
        raw = raw_contract()
        evidence = [
            item.model_copy(
                update={"source_text": "Total Contract Price: 100,000.00"}
            )
            if item.field == "amount_due"
            else item
            for item in raw.evidence
        ]
        extraction, audit = augment_currency_evidence(
            raw.model_copy(update={"evidence": evidence}),
            ISO_4217_CODES,
        )
        self.assertFalse(
            any(item.field == "currency" for item in extraction.evidence)
        )
        self.assertEqual(audit, [])
        normalized, validation = apply_deterministic_review_state(
            extraction,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertFalse(
            any(item.field == "currency" for item in normalized.evidence)
        )
        self.assertIn("MISSING_CORE_EVIDENCE", issue_codes(validation))

    def test_existing_currency_evidence_removes_gap(self):
        raw = raw_contract().model_copy(
            update={
                "evidence": list(raw_contract().evidence)
                + [
                    FieldEvidence(
                        field="currency",
                        page=1,
                        source_text="Currency: USD",
                        extraction_type="EXPLICIT",
                        confidence_reason="통화 코드가 직접 표시됨",
                    )
                ]
            }
        )
        unused_extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        del unused_extraction
        currency_gaps = [
            item
            for item in validation.issues
            if (
                item.code == "MISSING_CORE_EVIDENCE"
                and item.field == "currency"
            )
        ]
        self.assertEqual(currency_gaps, [])

    def test_inferred_currency_can_only_pass_with_user_override_record(self):
        raw = raw_contract()
        evidence = [
            item.model_copy(update={"extraction_type": "INFERRED"})
            if item.field == "amount_due"
            else item
            for item in raw.evidence
        ]
        evidence.append(
            FieldEvidence(
                field="currency",
                page=1,
                source_text="Currency appears to be USD",
                extraction_type="INFERRED",
                confidence_reason="문맥 추론",
            )
        )
        raw = raw.model_copy(update={"evidence": evidence})
        extraction, initial = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertTrue(
            any(
                item.code == "INFERRED_CRITICAL_FIELD"
                and item.field == "currency"
                for item in initial.issues
            )
        )
        checks = ConfirmationState(
            company_role_confirmed=True,
            trade_type_confirmed=True,
            currency_confirmed=True,
            amount_due_confirmed=True,
            due_date_confirmed=True,
            confirmed_due_date="2026-10-25",
            user_confirmed_override=True,
            user_confirmed_override_fields=["currency"],
        )
        unused_extraction, confirmed = apply_deterministic_review_state(
            extraction,
            company_role="BUYER",
            company_country="KR",
            confirmations=checks,
        )
        del unused_extraction
        self.assertFalse(
            any(
                item.code == "INFERRED_CRITICAL_FIELD"
                and item.field == "currency"
                for item in confirmed.issues
            )
        )


class DateNormalizationTests(unittest.TestCase):
    def test_date_placeholders_become_none(self):
        for value in (
            "",
            " ",
            "YYYY-MM-DD",
            "yyyy-mm-dd",
            "None",
            "null",
            "N/A",
            "-",
        ):
            with self.subTest(value=value):
                self.assertIsNone(normalize_date_text(value))

    def test_net_90_calendar_days_from_contract_date_matches(self):
        self.assertEqual(
            calculate_net_due_date(
                "2026-07-27",
                "Net 90 calendar days from the Contract Date",
            ),
            "2026-10-25",
        )
        extraction, validation = apply_deterministic_review_state(
            raw_contract(),
            company_role="BUYER",
            company_country="KR",
        )
        self.assertIsNone(extraction.issue_date)
        self.assertNotIn("DUE_DATE_CONFLICT", issue_codes(validation))
        self.assertTrue(
            any(
                item.field == "explicit_due_date"
                and item.status == "VERIFIED"
                for item in validation.normalization_audit
            )
        )

    def test_due_date_conflict_is_reported(self):
        raw = raw_contract().model_copy(
            update={"explicit_due_date": "2026-10-24"}
        )
        unused_extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        del unused_extraction
        self.assertIn("DUE_DATE_CONFLICT", issue_codes(validation))

    def test_business_days_are_not_calendar_days(self):
        self.assertEqual(
            calculate_net_due_date(
                "2026-07-24",
                "Net 2 business days from the Contract Date",
            ),
            "2026-07-28",
        )


class SalesContractEndToEndTests(unittest.TestCase):
    def test_fixture_normalizes_without_original_five_errors(self):
        extraction, validation = apply_deterministic_review_state(
            raw_contract(),
            company_role="BUYER",
            company_country="KR",
        )
        self.assertEqual(
            {
                "seller_country": extraction.seller_country,
                "buyer_country": extraction.buyer_country,
                "trade_type": extraction.trade_type,
                "issue_date": extraction.issue_date,
            },
            {
                "seller_country": "US",
                "buyer_country": "KR",
                "trade_type": "IMPORT",
                "issue_date": None,
            },
        )
        self.assertTrue(
            any(item.field == "currency" for item in extraction.evidence)
        )
        self.assertTrue(
            {
                "COMPANY_COUNTRY_ROLE_MISMATCH",
                "INVALID_PARTY_COUNTRY",
            }.isdisjoint(issue_codes(validation))
        )
        self.assertFalse(
            any(
                item.code == "MISSING_REQUIRED_FIELD"
                and item.field == "trade_type"
                for item in validation.issues
            )
        )
        self.assertFalse(
            any(
                item.code == "MISSING_CORE_EVIDENCE"
                and item.field == "currency"
                for item in validation.issues
            )
        )

    def test_stage2_is_blocked_before_confirmation_and_built_after(self):
        raw = raw_contract()
        extraction, validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        with self.assertRaises(ValueError):
            build_stage2_input(
                extraction=extraction,
                validation=validation,
                confirmations=ConfirmationState(),
                source_filename="KBFX_sample_international_sales_contract.pdf",
            )

        record = create_confirmation_record(
            original=raw,
            confirmed=extraction,
            confirmed_due_date="2026-10-25",
            company_role_confirmed=True,
            trade_type_confirmed=True,
            currency_confirmed=True,
            amount_due_confirmed=True,
            due_date_confirmed=True,
            source_filename="KBFX_sample_international_sales_contract.pdf",
            source_sha256="b" * 64,
            company_country="Republic of Korea",
            trade_type_source=validation.trade_type_source,
            confirmed_by="regression-test",
            confirmed_at="2026-07-27T12:00:00+09:00",
            review_audit_trail=[
                {
                    "changed_at": "2026-07-27T11:59:00+09:00",
                    "before": {
                        "company_role": "BUYER",
                        "company_country": "KR",
                        "trade_type": "UNKNOWN",
                        "seller_country": "United States",
                        "buyer_country": "Republic of Korea",
                        "currency": "USD",
                        "amount_due": "100000.00",
                        "contract_date": "2026-07-27",
                        "explicit_due_date": "2026-10-25",
                    },
                    "after": {
                        "company_role": "BUYER",
                        "company_country": "KR",
                        "trade_type": "IMPORT",
                        "seller_country": "US",
                        "buyer_country": "KR",
                        "currency": "USD",
                        "amount_due": "100000.00",
                        "contract_date": "2026-07-27",
                        "explicit_due_date": "2026-10-25",
                    },
                }
            ],
        )
        confirmed_validation = validate_confirmation(
            extraction=extraction,
            record=record,
            company_country="KR",
        )
        self.assertTrue(confirmed_validation.stage2_allowed)
        payload = build_stage2_input(
            extraction=extraction,
            validation=confirmed_validation,
            confirmations=record.checks,
            source_filename=record.source_filename,
            source_sha256=record.source_sha256,
            confirmed_at=record.confirmed_at,
        )
        self.assertEqual(payload["trade"]["trade_type"], "IMPORT")
        self.assertEqual(payload["trade"]["currency"], "USD")
        self.assertEqual(payload["trade"]["foreign_amount"], "100000.00")
        self.assertEqual(
            payload["trade"]["settlement_date"],
            "2026-10-25",
        )
        self.assertEqual(
            set(payload["source"]["confirmed_fields"]),
            {
                "company_role",
                "trade_type",
                "currency",
                "amount_due",
                "due_date",
            },
        )
        self.assertEqual(
            record.original_values["seller_country"],
            "United States",
        )
        self.assertEqual(len(record.review_audit_trail), 1)
        self.assertEqual(
            record.review_audit_trail[0].before.trade_type,
            "UNKNOWN",
        )

    def test_user_evidence_override_is_explicit_and_not_fake_ai_evidence(self):
        raw = raw_contract()
        evidence = [
            item.model_copy(
                update={"source_text": "Total Contract Price: 100,000.00"}
            )
            if item.field == "amount_due"
            else item
            for item in raw.evidence
        ]
        raw = raw.model_copy(update={"evidence": evidence})
        extraction, initial_validation = apply_deterministic_review_state(
            raw,
            company_role="BUYER",
            company_country="KR",
        )
        self.assertIn(
            "MISSING_CORE_EVIDENCE",
            issue_codes(initial_validation),
        )
        record = create_confirmation_record(
            original=raw,
            confirmed=extraction,
            confirmed_due_date="2026-10-25",
            company_role_confirmed=True,
            trade_type_confirmed=True,
            currency_confirmed=True,
            amount_due_confirmed=True,
            due_date_confirmed=True,
            source_filename="contract.pdf",
            source_sha256="c" * 64,
            company_country="KR",
            evidence_override_fields=["currency"],
            confirmed_by="regression-test",
            confirmed_at="2026-07-27T12:00:00+09:00",
        )
        validation = validate_confirmation(
            extraction=extraction,
            record=record,
            company_country="KR",
        )
        self.assertTrue(validation.stage2_allowed)
        self.assertFalse(
            any(item.field == "currency" for item in extraction.evidence)
        )
        self.assertTrue(record.checks.user_confirmed_override)
        self.assertEqual(
            record.checks.user_confirmed_override_fields,
            ["currency"],
        )


class StreamlitReviewFlowTests(unittest.TestCase):
    def test_user_country_edits_are_revalidated_from_latest_widgets(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(
            str(ROOT / "app.py"),
            default_timeout=20,
        ).run()
        mode = next(
            radio
            for radio in app.radio
            if radio.label == "분석할 문서"
        )
        mode.set_value("데모 모드").run()
        analyze = next(
            button
            for button in app.button
            if button.label == "문서 분석하고 거래정보 채우기"
        )
        analyze.click().run()
        self.assertEqual(len(app.exception), 0)

        seller_country = next(
            widget
            for widget in app.text_input
            if widget.key == "review_seller_country_widget"
        )
        buyer_country = next(
            widget
            for widget in app.text_input
            if widget.key == "review_buyer_country_widget"
        )
        issue_date = next(
            widget
            for widget in app.text_input
            if widget.key == "review_issue_date_widget"
        )
        seller_country.set_value("United States")
        buyer_country.set_value("Republic of Korea")
        issue_date.set_value("YYYY-MM-DD")
        review = next(
            button
            for button in app.button
            if button.label == "수정 내용 저장 및 다시 검증"
        )
        review.click().run()
        self.assertEqual(len(app.exception), 0)

        extraction = TradeDocumentExtraction.model_validate(
            app.session_state["extraction"]
        )
        validation = app.session_state["extraction_validation"]
        self.assertEqual(extraction.seller_country, "US")
        self.assertEqual(extraction.buyer_country, "KR")
        self.assertEqual(extraction.trade_type, "IMPORT")
        self.assertIsNone(extraction.issue_date)
        self.assertFalse(
            any(
                item["code"]
                in {
                    "INVALID_PARTY_COUNTRY",
                    "COMPANY_COUNTRY_ROLE_MISMATCH",
                }
                for item in validation["issues"]
            )
        )
        self.assertEqual(
            len(app.session_state["review_audit_trail"]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
