"""Typed identifiers for the Production bounded context."""

from __future__ import annotations

from windagent.kernel.ids import Identifier


class ProductionProjectId(Identifier):
    """Identifier for a production project aggregate."""


class ProductionRevisionId(Identifier):
    """Identifier for an immutable production revision."""


class ProductionAssetId(Identifier):
    """Identifier for a production asset aggregate."""


class AssetRevisionId(Identifier):
    """Identifier for an immutable asset revision."""


class AudioTrackId(Identifier):
    """Identifier for an audio track."""


class MixPlanId(Identifier):
    """Identifier for an audio mix plan."""


class CodeVideoProjectId(Identifier):
    """Identifier for a code-video tutorial project."""


class RenderJobId(Identifier):
    """Identifier for a render job."""


class EdlId(Identifier):
    """Identifier for an edit decision list."""


__all__ = [
    "AssetRevisionId",
    "AudioTrackId",
    "CodeVideoProjectId",
    "EdlId",
    "MixPlanId",
    "ProductionAssetId",
    "ProductionProjectId",
    "ProductionRevisionId",
    "RenderJobId",
]
