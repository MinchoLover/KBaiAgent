import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from src.config import Settings


SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
}
MAX_IMAGE_PIXELS = 40_000_000
EXTENSION_MIME_TYPES: Dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class UploadValidationError(ValueError):
    pass


@dataclass(frozen=True)
class UploadMetadata:
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    page_count: Optional[int]


def sanitize_filename(filename: str) -> str:
    name = Path(filename or "uploaded_document").name
    name = name.replace("\x00", "")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    name = name.lstrip(".")[:128]
    return name or "uploaded_document"


def detect_magic_mime(file_bytes: bytes) -> Optional[str]:
    if file_bytes.startswith(b"%PDF-"):
        return "application/pdf"
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def _validate_pdf(file_bytes: bytes, max_pages: int) -> int:
    try:
        reader = PdfReader(io.BytesIO(file_bytes), strict=True)
        if reader.is_encrypted:
            raise UploadValidationError(
                "암호화된 PDF는 지원하지 않습니다."
            )
        page_count = len(reader.pages)
    except UploadValidationError:
        raise
    except Exception as exc:
        raise UploadValidationError(
            "손상되었거나 해석할 수 없는 PDF입니다."
        ) from exc

    if page_count < 1:
        raise UploadValidationError("페이지가 없는 PDF입니다.")
    if page_count > max_pages:
        raise UploadValidationError(
            "PDF는 최대 {}페이지까지 지원합니다.".format(max_pages)
        )
    return page_count


def _validate_image(file_bytes: bytes, expected_mime: str) -> None:
    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            actual_format = image.format
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise UploadValidationError(
                    "이미지 픽셀 수가 안전 제한을 초과합니다."
                )
            image.verify()
    except UploadValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise UploadValidationError(
            "손상되었거나 해석할 수 없는 이미지입니다."
        ) from exc

    expected_format = "PNG" if expected_mime == "image/png" else "JPEG"
    if actual_format != expected_format:
        raise UploadValidationError(
            "이미지 내용과 MIME 형식이 일치하지 않습니다."
        )


def validate_upload(
    *,
    file_bytes: bytes,
    filename: str,
    claimed_mime_type: Optional[str],
    settings: Optional[Settings] = None,
) -> UploadMetadata:
    effective_settings = settings or Settings.from_env()
    if not file_bytes:
        raise UploadValidationError("빈 파일입니다.")

    max_bytes = effective_settings.max_upload_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise UploadValidationError(
            "파일은 최대 {}MB까지 지원합니다.".format(
                effective_settings.max_upload_mb
            )
        )

    safe_filename = sanitize_filename(filename)
    extension = Path(safe_filename).suffix.lower()
    extension_mime = EXTENSION_MIME_TYPES.get(extension)
    magic_mime = detect_magic_mime(file_bytes)
    claimed = (claimed_mime_type or "").lower().split(";")[0].strip()
    if claimed == "image/jpg":
        claimed = "image/jpeg"

    if extension_mime is None:
        raise UploadValidationError(
            "PDF, PNG, JPG, JPEG 파일만 지원합니다."
        )
    if magic_mime is None or magic_mime not in SUPPORTED_MIME_TYPES:
        raise UploadValidationError(
            "파일 signature가 지원 형식과 일치하지 않습니다."
        )
    if extension_mime != magic_mime:
        raise UploadValidationError(
            "확장자와 파일 내용이 일치하지 않습니다."
        )
    if claimed and claimed != magic_mime:
        raise UploadValidationError(
            "브라우저 MIME과 파일 내용이 일치하지 않습니다."
        )

    page_count: Optional[int] = None
    if magic_mime == "application/pdf":
        page_count = _validate_pdf(
            file_bytes,
            effective_settings.max_pdf_pages,
        )
    else:
        _validate_image(file_bytes, magic_mime)

    return UploadMetadata(
        filename=safe_filename,
        mime_type=magic_mime,
        size_bytes=len(file_bytes),
        sha256=hashlib.sha256(file_bytes).hexdigest(),
        page_count=page_count,
    )
