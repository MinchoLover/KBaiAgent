#!/usr/bin/env python3
import argparse
import mimetypes
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import Settings  # noqa: E402
from src.document_intake.extractor import (  # noqa: E402
    ExtractionError,
    extract_trade_document_with_metadata,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="한 문서만 호출하는 비용 발생 live smoke test",
    )
    parser.add_argument("document")
    parser.add_argument(
        "--company-role",
        choices=["BUYER", "SELLER"],
        default="BUYER",
    )
    parser.add_argument("--company-country", default="KR")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.live_extraction_ready:
        print(
            "SKIPPED: OPENAI_API_KEY와 "
            "ENABLE_LIVE_DOCUMENT_EXTRACTION=true가 필요합니다."
        )
        return 2

    path = Path(args.document).resolve()
    if not path.is_file():
        print("ERROR: 문서가 없습니다: {}".format(path))
        return 2
    print(
        "주의: 실제 OpenAI API를 1개 문서에 호출하며 토큰 비용이 발생합니다."
    )
    try:
        result = extract_trade_document_with_metadata(
            file_bytes=path.read_bytes(),
            filename=path.name,
            mime_type=mimetypes.guess_type(str(path))[0],
            company_role=args.company_role,
            company_country=args.company_country,
            settings=settings,
        )
    except ExtractionError as exc:
        print("FAILED: {}".format(exc))
        return 1
    print(
        "PASS document_type={} validation_pass={} latency_seconds={}".format(
            result.extraction.document_type,
            result.validation.validation_pass,
            result.usage.latency_seconds,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
