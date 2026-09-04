"""Importer for legacy studio creative assets into V2 Studio bounded context."""

from __future__ import annotations

from typing import Any


class StudioImporter:
    """Imports legacy story drafts, characters, and storyboard scenes into V2 Studio schema."""

    def __init__(self) -> None:
        self.imported_projects: list[dict[str, Any]] = []
        self.imported_characters: list[dict[str, Any]] = []
        self.imported_scenes: list[dict[str, Any]] = []

    def import_legacy_project(self, legacy_proj: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        """Convert legacy studio project into V2 Studio project aggregate."""
        v2_proj = {
            "id": legacy_proj.get("id") or f"proj-{legacy_proj['title'].lower().replace(' ', '-')}",
            "title": legacy_proj["title"],
            "genre": legacy_proj.get("genre", "General Fiction"),
            "synopsis": legacy_proj.get("synopsis", ""),
            "status": legacy_proj.get("status", "draft"),
            "created_at": legacy_proj.get("created_at", "2026-09-02T00:00:00Z"),
        }

        if not dry_run:
            self.imported_projects.append(v2_proj)

        return v2_proj

    def import_legacy_character(self, project_id: str, legacy_char: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        """Convert legacy character sheet into V2 Character entity."""
        v2_char = {
            "id": legacy_char.get("id") or f"char-{legacy_char['name'].lower().replace(' ', '-')}",
            "project_id": project_id,
            "name": legacy_char["name"],
            "role": legacy_char.get("role", "supporting"),
            "visual_traits": legacy_char.get("appearance", legacy_char.get("visual_traits", "")),
            "voice_profile": legacy_char.get("voice", legacy_char.get("voice_profile", "")),
        }

        if not dry_run:
            self.imported_characters.append(v2_char)

        return v2_char
