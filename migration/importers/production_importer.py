"""Importer for legacy video production assets into V2 Production bounded context."""

from __future__ import annotations

from typing import Any


class ProductionImporter:
    """Imports legacy video projects and media assets into V2 Production schema."""

    def __init__(self) -> None:
        self.imported_projects: list[dict[str, Any]] = []
        self.imported_assets: list[dict[str, Any]] = []

    def import_legacy_project(self, legacy_proj: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        """Convert legacy video production metadata into V2 Production project."""
        v2_proj = {
            "id": legacy_proj.get("id") or f"prod-{legacy_proj['title'].lower().replace(' ', '-')}",
            "title": legacy_proj["title"],
            "format": legacy_proj.get("aspect_ratio", "16:9"),
            "fps": legacy_proj.get("framerate", 60),
            "resolution": legacy_proj.get("resolution", "1920x1080"),
            "status": "idle",
        }

        if not dry_run:
            self.imported_projects.append(v2_proj)

        return v2_proj

    def import_legacy_asset(self, project_id: str, legacy_asset: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        """Convert legacy asset entry into V2 MediaAsset entity with ACEScg mapping."""
        v2_asset = {
            "id": legacy_asset.get("id") or f"asset-{legacy_asset['filename']}",
            "project_id": project_id,
            "name": legacy_asset["filename"],
            "asset_type": legacy_asset.get("type", "video"),
            "file_path": legacy_asset["path"],
            "size_bytes": legacy_asset.get("size", 0),
            "colorspace": legacy_asset.get("color_space", "ACEScg"),
            "status": "ready",
        }

        if not dry_run:
            self.imported_assets.append(v2_asset)

        return v2_asset
