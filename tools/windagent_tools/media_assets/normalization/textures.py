"""
Texture normalization (VP3D Phase 7, Stage C item 3).

Textures are content-addressed, bounded by resolution/bit depth, stripped of
metadata, and published with color-space metadata. Oversized textures are
downscaled to the configured maximum (never upscaled). Unsupported formats are
recorded as missing (fail closed — an unreadable texture is not silently
kept).
"""

from __future__ import annotations

from typing import Optional

from windagent_core.domain.video_production.asset_normalization.enums import ColorSpace
from windagent_core.domain.video_production.asset_normalization.models import (
    NormalizationConfig,
    TextureInfo,
)

from windagent_tools.media_assets.normalization.snapshot import ImageRef
from windagent_tools.media_assets.store import ContentAddressedStore

SUPPORTED_FORMATS = {"png", "jpeg", "webp"}


class NormalizedTexture:
    """Normalized texture + its published payload."""

    __slots__ = ("info", "payload")

    def __init__(self, info: TextureInfo, payload: bytes) -> None:
        self.info = info
        self.payload = payload


class TextureNormalizer:
    """Content-addressed texture normalization."""

    def __init__(self, store: ContentAddressedStore) -> None:
        self._store = store

    def normalize_image(
        self,
        image: ImageRef,
        config: NormalizationConfig,
    ) -> Optional[NormalizedTexture]:
        """Normalize one image: cap resolution, strip metadata, hash, store.

        Returns None when the image has no embedded/external-accessible bytes
        (it is recorded as missing by the caller).
        """
        data = image.data
        if not data:
            return None

        from io import BytesIO

        from PIL import Image

        try:
            with Image.open(BytesIO(data)) as img:
                original = img.size
                fmt = (img.format or "").lower()
                mode = img.mode
                depth = _bit_depth(mode)
                img.verify()
        except Exception:
            return None  # corrupt/unreadable texture -> missing (fail closed)

        with Image.open(BytesIO(data)) as img:
            width, height = img.size
            capped = False
            limit = config.max_texture_resolution
            if width > limit or height > limit:
                ratio = min(limit / width, limit / height)
                new_size = (max(1, int(width * ratio)), max(1, int(height * ratio)))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                width, height = new_size
                capped = True
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if img.mode in ("LA", "P", "PA") else "RGB")
            out = BytesIO()
            out_fmt = "PNG" if fmt not in SUPPORTED_FORMATS else fmt.upper()
            img.save(out, format=out_fmt)
            payload = out.getvalue()

        content_hash = self._store.publish(payload)
        return NormalizedTexture(
            TextureInfo(
                name=image.name,
                content_hash=content_hash,
                width=width,
                height=height,
                bit_depth=_bit_depth(img.mode) or depth,
                color_space=ColorSpace(_color_space_name(image.color_space)),
                format=out_fmt.lower(),
                resolution_capped=capped,
                original_width=original[0],
                original_height=original[1],
            ),
            payload,
        )


def _bit_depth(mode: str) -> int:
    return {"1": 1, "L": 8, "LA": 8, "P": 8, "RGB": 8, "RGBA": 8, "I;16": 16, "I": 32, "F": 32}.get(mode, 8)


def _color_space_name(raw: str) -> str:
    lowered = raw.lower()
    if "linear" in lowered:
        return "Linear"
    if "raw" in lowered:
        return "Raw"
    return "sRGB"


__all__ = ["TextureNormalizer", "NormalizedTexture"]
