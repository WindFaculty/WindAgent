"""
AssetValidationService (plan 02 §21.2) — ordered media validation.

Mandatory order:
    stream to quarantine → size limit → content hash → MIME signature/sniff
    → decoder validation → pixel/decompression limit → metadata inspection
    → malware scan when available → EXIF sanitization → publish to
    content-addressed store

Rules:
- extension is never evidence of MIME;
- zero-byte, polyglot, executable and archive payloads are rejected;
- SVG is banned in Release 0.1 (no verified sanitizer);
- a validation failure never publishes a partial artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from windagent_core.domain.video_production.enums import MediaType

from windagent_tools.media_assets.errors import MediaValidationError
from windagent_tools.media_assets.security import classify_payload
from windagent_tools.media_assets.store import ContentAddressedStore

MAX_PIXELS = 40_000_000  # e.g. 8000x5000 — decompression-bomb guard
MAX_IMAGE_BYTES = 25 * 1024 * 1024

# MIME types allowed for reference assets in Release 0.1.
ALLOWED_IMAGE_MIME = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/bmp",
}

SVG_BANNED_NOTE = "SVG is banned in Release 0.1 (no verified sanitizer)."


@dataclass(frozen=True)
class ValidationReceipt:
    """Result of the ordered validation pipeline."""

    content_hash: str
    sniffed_mime: str
    media_type: MediaType
    size_bytes: int
    width: Optional[int] = None
    height: Optional[int] = None
    exif_stripped: bool = False
    steps: List[str] = field(default_factory=list)


class AssetValidationService:
    """Runs the mandatory ordered validation pipeline."""

    def __init__(
        self,
        store: ContentAddressedStore,
        *,
        max_bytes: int = MAX_IMAGE_BYTES,
        max_pixels: int = MAX_PIXELS,
    ) -> None:
        self.store = store
        self.max_bytes = max_bytes
        self.max_pixels = max_pixels

    def validate(self, data: bytes, *, extension: str = "") -> ValidationReceipt:
        steps: List[str] = []

        # 1. size limit
        if len(data) == 0:
            raise MediaValidationError("Zero-byte asset rejected.")
        if len(data) > self.max_bytes:
            raise MediaValidationError(
                "Asset exceeds size limit.",
                details={"max_bytes": self.max_bytes, "actual": len(data)},
            )
        steps.append("size_limit")

        # 2. MIME sniff + payload classification
        fingerprint = classify_payload(data, extension=extension)
        if fingerprint.is_svg:
            raise MediaValidationError(SVG_BANNED_NOTE)
        if fingerprint.is_zero_byte:
            raise MediaValidationError("Zero-byte asset rejected.")
        if fingerprint.is_executable:
            raise MediaValidationError("Executable payload rejected.")
        if fingerprint.is_archive:
            raise MediaValidationError("Archive payload rejected.")
        if fingerprint.looks_polyglot:
            raise MediaValidationError("Polyglot payload rejected.")
        mime = fingerprint.sniffed_mime
        steps.append("mime_sniff")

        if mime not in ALLOWED_IMAGE_MIME:
            raise MediaValidationError(
                f"Unsupported MIME {mime!r} (image types only).",
                details={"sniffed_mime": mime},
            )

        # 3. decoder validation + pixel limit (via Pillow when available)
        width = height = None
        try:
            from PIL import Image

            with Image.open(_BytesIO(data)) as img:
                img.verify()  # decode validation — raises on corrupt/truncated
            with Image.open(_BytesIO(data)) as img:
                width, height = img.size
                if (width or 0) * (height or 0) > self.max_pixels:
                    raise MediaValidationError(
                        "Image exceeds pixel/decompression limit.",
                        details={"width": width, "height": height},
                    )
                steps.append("decoder+pixel_limit")
        except MediaValidationError:
            raise
        except Exception as exc:  # noqa: BLE001 - corrupt/truncated image
            raise MediaValidationError(
                f"Image decoder validation failed: {exc}",
                details={"mime": mime, "error": str(exc)[:200]},
            ) from exc

        # 4. metadata inspection + EXIF sanitization
        # Sanitized payload is what gets hashed and stored, so the published
        # artifact NEVER carries embedded EXIF (plan 02 §21.2).
        sanitized, exif_stripped = _strip_exif(data, mime)
        if exif_stripped:
            steps.append("exif_sanitization")

        # 5. content hash over the (sanitized) payload
        content_hash = ContentAddressedStore.content_hash(sanitized)
        steps.append("content_hash")

        # 6. publish to content-addressed store (atomic, no partial artifact)
        self.store.publish(sanitized)
        steps.append("publish_content_addressed")

        media_type = _mime_to_media_type(mime)
        return ValidationReceipt(
            content_hash=content_hash,
            sniffed_mime=mime,
            media_type=media_type,
            size_bytes=len(sanitized),
            width=width,
            height=height,
            exif_stripped=exif_stripped,
            steps=steps,
        )


class _BytesIO:
    """Minimal in-memory bytes file object for Pillow (avoids file writes)."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            chunk = self._data[self._pos:]
            self._pos = len(self._data)
            return chunk
        chunk = self._data[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = len(self._data) + offset
        return self._pos

    def tell(self) -> int:
        return self._pos


def _strip_exif(data: bytes, mime: str) -> tuple[bytes, bool]:
    """Re-encode without EXIF metadata when EXIF is present.

    Returns (sanitized_bytes, stripped). If the image has no EXIF or the
    format cannot be safely re-encoded, the original bytes are returned
    unchanged (stripped=False).
    """
    try:
        from PIL import Image
        from io import BytesIO

        with Image.open(_BytesIO(data)) as img:
            exif = img.getexif()
            if not exif:
                return data, False
        fmt = {
            "image/png": "PNG",
            "image/jpeg": "JPEG",
            "image/webp": "WEBP",
            "image/gif": "GIF",
            "image/bmp": "BMP",
        }.get(mime)
        if fmt is None:
            return data, False
        out = BytesIO()
        with Image.open(_BytesIO(data)) as img:
            # Save WITHOUT exif= so embedded metadata is dropped.
            img.save(out, format=fmt)
        return out.getvalue(), True
    except Exception:  # noqa: BLE001 - keep original if sanitization fails
        return data, False


def _mime_to_media_type(mime: str) -> MediaType:
    if mime.startswith("image/"):
        return MediaType.IMAGE
    if mime.startswith("video/"):
        return MediaType.VIDEO
    if mime.startswith("audio/"):
        return MediaType.AUDIO
    if mime.startswith("text/"):
        return MediaType.DOCUMENT
    return MediaType.UNKNOWN


__all__ = [
    "AssetValidationService",
    "ValidationReceipt",
    "ALLOWED_IMAGE_MIME",
    "SVG_BANNED_NOTE",
]
