"""Compatibility adapter for the Stage 0 document intake package."""

from src.document_intake.extractor import (  # noqa: F401
    ExtractionError,
    ExtractionRun,
    extract_trade_document,
    extract_trade_document_with_metadata,
)


__all__ = [
    "ExtractionError",
    "ExtractionRun",
    "extract_trade_document",
    "extract_trade_document_with_metadata",
]
