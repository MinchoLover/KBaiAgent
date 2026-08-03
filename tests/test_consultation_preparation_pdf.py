import hashlib
import io
import unittest
from datetime import datetime

from PIL import ImageChops
from pypdf import PdfReader

from scripts.verify_golden_user_flow import build_golden_user_flow_artifacts
from src.consultation.preparation_pdf import (
    PDF_DISCLAIMER,
    PDF_MIME,
    PDF_TITLE,
    ConsultationPreparationBindingError,
    build_consultation_preparation_content,
    build_consultation_preparation_pdf,
    consultation_preparation_pdf_filename,
    find_korean_pdf_font,
)


class ConsultationPreparationPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        artifacts = build_golden_user_flow_artifacts()
        cls.packet = artifacts["decision"].consultation_packet.packet
        cls.transaction = artifacts["workflow"].confirmed_transaction
        cls.stage2_result = artifacts["workflow"].cashflow.data
        cls.generated_at = datetime.fromisoformat(cls.packet.generated_at)
        cls.forecast_summary = {
            "headline": "하락 전망 · 모델 중심환율 1,425.25원",
            "range": (
                "예측 범위 1,389.22원~1,491.54원 · "
                "모델 전망기간 2026-07-31~2026-08-27"
            ),
            "data_as_of": "2026-07-29",
        }
        cls.font_path = find_korean_pdf_font()
        cls.content = build_consultation_preparation_content(
            packet=cls.packet,
            transaction=cls.transaction,
            stage2_result=cls.stage2_result,
            generated_at=cls.generated_at,
            forecast_summary=cls.forecast_summary,
        )
        cls.pdf_bytes = build_consultation_preparation_pdf(
            packet=cls.packet,
            transaction=cls.transaction,
            stage2_result=cls.stage2_result,
            generated_at=cls.generated_at,
            forecast_summary=cls.forecast_summary,
            font_path=cls.font_path,
        )

    def test_pdf_bytes_filename_mime_and_metadata(self):
        self.assertIsInstance(self.pdf_bytes, bytes)
        self.assertTrue(self.pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(len(self.pdf_bytes), 100000)
        self.assertEqual(PDF_MIME, "application/pdf")
        filename = consultation_preparation_pdf_filename(
            self.generated_at
        )
        self.assertEqual(filename, "KB_환담_상담준비서_20260729.pdf")
        self.assertTrue(filename.endswith(".pdf"))
        reader = PdfReader(io.BytesIO(self.pdf_bytes), strict=True)
        self.assertEqual(reader.metadata.title, PDF_TITLE)
        self.assertEqual(reader.metadata.author, "KB 환담")

    def test_pdf_is_deterministic_for_same_verified_inputs(self):
        second = build_consultation_preparation_pdf(
            packet=self.packet,
            transaction=self.transaction,
            stage2_result=self.stage2_result,
            generated_at=self.generated_at,
            forecast_summary=self.forecast_summary,
            font_path=self.font_path,
        )
        self.assertEqual(
            hashlib.sha256(self.pdf_bytes).hexdigest(),
            hashlib.sha256(second).hexdigest(),
        )

    def test_user_content_has_required_sections_and_no_internal_terms(self):
        text = self.content.all_text()
        for required in (
            "KB 환담 상담 준비서",
            "수출대금 회수 보호",
            "환율 관리",
            "준비할 자료",
            "은행 또는 기관에 물어볼 질문",
            "상담 후 결정할 사항",
            PDF_DISCLAIMER,
            "최소 운영자금 대비 부족액",
            "실제 현금 적자",
            "대출한도 반영 후 부족액",
            "외상거래(Open Account)",
            "전신송금(T/T)",
            "인수인도조건(D/A)",
        ):
            self.assertIn(required, text)
        for prohibited in (
            "DOWN_10",
            "UP_10",
            "post-credit",
            "overflow",
            "deferred",
            "auxiliary",
            "fingerprint",
            "critic",
            "fallback",
            "Stage1",
            "Stage2",
            "Stage3",
            "Stage 1",
            "Stage 2",
            "Stage 3",
            "profile",
            "shortlist",
            "stale",
            "binding",
            "hash",
        ):
            self.assertNotIn(prohibited.lower(), text.lower())

    def test_rendered_pages_are_a4_nonblank_and_within_five_pages(self):
        reader = PdfReader(io.BytesIO(self.pdf_bytes), strict=True)
        self.assertGreaterEqual(len(reader.pages), 3)
        self.assertLessEqual(len(reader.pages), 5)
        for page in reader.pages:
            self.assertAlmostEqual(float(page.mediabox.width), 595.2, places=1)
            self.assertAlmostEqual(float(page.mediabox.height), 841.92, places=1)
            self.assertEqual(len(page.images), 1)
            rendered = page.images[0].image.convert("RGB")
            self.assertEqual(rendered.size, (1240, 1754))
            blank = rendered.copy()
            blank.paste("white", (0, 0, rendered.width, rendered.height))
            difference = ImageChops.difference(rendered, blank)
            self.assertIsNotNone(difference.getbbox())

        detail_continuation = reader.pages[3].images[0].image.convert(
            "RGB"
        )
        card_top = detail_continuation.crop((400, 165, 840, 178))
        self.assertTrue(
            any(sum(pixel) < 735 for pixel in card_top.getdata()),
            "상담 상세 계속 페이지에 카드 경계가 없어 페이지 분할이 "
            "깨졌습니다.",
        )

    def test_korean_font_has_distinct_unicode_glyphs(self):
        self.assertTrue(self.font_path)
        self.assertIn("상담", self.content.all_text())
        self.assertNotIn("□", self.content.all_text())

    def test_stale_transaction_or_cashflow_is_rejected(self):
        stale_transaction = self.transaction.model_copy(
            update={"input_fingerprint": "a" * 64}
        )
        with self.assertRaises(ConsultationPreparationBindingError):
            build_consultation_preparation_pdf(
                packet=self.packet,
                transaction=stale_transaction,
                stage2_result=self.stage2_result,
                generated_at=self.generated_at,
                forecast_summary=self.forecast_summary,
                font_path=self.font_path,
            )
        stale_stage2 = self.stage2_result.model_copy(
            update={"confirmed_trade_sha256": "b" * 64}
        )
        with self.assertRaises(ConsultationPreparationBindingError):
            build_consultation_preparation_pdf(
                packet=self.packet,
                transaction=self.transaction,
                stage2_result=stale_stage2,
                generated_at=self.generated_at,
                forecast_summary=self.forecast_summary,
                font_path=self.font_path,
            )

    def test_recommendation_content_change_rebuilds_pdf(self):
        shortlist = self.packet.official_candidate_shortlist
        self.assertIsNotNone(shortlist)
        assert shortlist is not None
        changed_candidate = shortlist.candidates[0].model_copy(
            update={
                "display_name": (
                    "수출대금 회수 보호 적용 가능 여부와 보장범위 확인 상담"
                )
            }
        )
        changed_shortlist = shortlist.model_copy(
            update={
                "candidates": [changed_candidate]
                + shortlist.candidates[1:]
            }
        )
        changed_packet = self.packet.model_copy(
            update={"official_candidate_shortlist": changed_shortlist}
        )
        changed = build_consultation_preparation_pdf(
            packet=changed_packet,
            transaction=self.transaction,
            stage2_result=self.stage2_result,
            generated_at=self.generated_at,
            forecast_summary=self.forecast_summary,
            font_path=self.font_path,
        )
        self.assertNotEqual(
            hashlib.sha256(self.pdf_bytes).hexdigest(),
            hashlib.sha256(changed).hexdigest(),
        )

    def test_long_question_and_product_name_wrap_without_extra_page(self):
        first_area = self.packet.consultation_review_areas[0]
        changed_area = first_area.model_copy(
            update={
                "bank_questions": [
                    (
                        "현재 거래의 결제예정일과 외상거래 잔금에 적용할 수 "
                        "있는 보호수단별 보장범위·면책조건·비용·필요서류를 "
                        "각각 어떻게 비교해야 하나요?"
                    )
                ]
                + first_area.bank_questions[1:]
            }
        )
        changed_packet = self.packet.model_copy(
            update={
                "consultation_review_areas": [changed_area]
                + self.packet.consultation_review_areas[1:]
            }
        )
        generated = build_consultation_preparation_pdf(
            packet=changed_packet,
            transaction=self.transaction,
            stage2_result=self.stage2_result,
            generated_at=self.generated_at,
            forecast_summary=self.forecast_summary,
            font_path=self.font_path,
        )
        reader = PdfReader(io.BytesIO(generated), strict=True)
        self.assertLessEqual(len(reader.pages), 5)
        self.assertTrue(all(page.images for page in reader.pages))


if __name__ == "__main__":
    unittest.main()
