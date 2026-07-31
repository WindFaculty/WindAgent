"""
Canonical validator for VideoProductionPackage v1.

Enforces the acceptance criteria of VP3_CANONICAL_PROTOCOL_VERIFIED:
- Missing / duplicate identifiers rejected.
- Broken references rejected.
- Unordered scene/shot ordering rejected.
- Assets without a content hash rejected.
- Mutation of a locked revision (hash mismatch after lock) rejected.
- Approval target hash must match the locked revision's content hash.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from windagent_core.domain.video_production.package import (
    VideoProductionPackage,
    validate_package_major,
)
from windagent_core.domain.video_production.errors import (
    UnsupportedMajorVersionError,
    VideoProductionProtocolError,
)


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation finding."""

    code: str
    message: str
    path: str = ""
    severity: str = "error"  # error | warning


class VideoProductionPackageValidator:
    """Stateless canonical validator for VideoProductionPackage v1."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @classmethod
    def validate(cls, package: VideoProductionPackage) -> List[ValidationIssue]:
        """Validate a parsed package; returns a list of issues (empty == valid)."""
        issues: List[ValidationIssue] = []
        try:
            validate_package_major(package.schema_version)
        except UnsupportedMajorVersionError as exc:
            return [ValidationIssue(code="UNSUPPORTED_MAJOR_VERSION", message=str(exc), path="schema_version")]

        issues.extend(cls._check_missing_ids(package))
        issues.extend(cls._check_duplicate_ids(package))
        issues.extend(cls._check_broken_references(package))
        issues.extend(cls._check_shot_ordering(package))
        issues.extend(cls._check_asset_hashes(package))
        issues.extend(cls._check_locked_revision_integrity(package))
        issues.extend(cls._check_approval_targets(package))
        return issues

    @classmethod
    def validate_dict(cls, data: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate raw dict data; major version fail-closed handled here.

        Raw structural checks (missing IDs, asset hashes) run BEFORE parsing so
        the rules fire even when strict Pydantic models would reject the payload.
        """
        try:
            schema_version = data.get("schema_version", "1.0.0")
            validate_package_major(schema_version)
        except UnsupportedMajorVersionError as exc:
            return [ValidationIssue(code="UNSUPPORTED_MAJOR_VERSION", message=str(exc), path="schema_version")]
        except VideoProductionProtocolError as exc:
            return [ValidationIssue(code="MALFORMED_SCHEMA_VERSION", message=str(exc), path="schema_version")]

        # Raw structural checks (do not require a successfully parsed package).
        # If raw issues exist we report them directly: the strict model would
        # otherwise reject the payload and obscure the intended rule.
        raw_issues = cls._check_raw_missing_ids(data)
        raw_issues.extend(cls._check_raw_asset_hashes(data))
        if raw_issues:
            return cls._dedupe(raw_issues)

        try:
            package = VideoProductionPackage.model_validate(data)
        except Exception as exc:  # pydantic ValidationError or domain error
            return [ValidationIssue(code="PARSE_FAILED", message=str(exc), path="$")]

        return cls.validate(package)

    @classmethod
    def is_valid(cls, package: VideoProductionPackage) -> bool:
        return not cls.validate(package)

    # ------------------------------------------------------------------
    # Raw structural checks (dict level)
    # ------------------------------------------------------------------
    @staticmethod
    def _check_raw_missing_ids(data: Dict[str, Any]) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        if not str(data.get("project_id") or "").strip():
            issues.append(ValidationIssue("MISSING_ID", "project_id is missing.", "project_id"))
        if not str(data.get("revision_id") or "").strip():
            issues.append(ValidationIssue("MISSING_ID", "revision_id is missing.", "revision_id"))

        for idx, item in enumerate(data.get("characters") or []):
            if not str(item.get("character_id") or "").strip():
                issues.append(ValidationIssue("MISSING_ID", "character_id is missing.", f"characters[{idx}].character_id"))
        for idx, item in enumerate(data.get("locations") or []):
            if not str(item.get("location_id") or "").strip():
                issues.append(ValidationIssue("MISSING_ID", "location_id is missing.", f"locations[{idx}].location_id"))
        for idx, item in enumerate(data.get("dialogue") or []):
            if not str(item.get("dialogue_id") or "").strip():
                issues.append(ValidationIssue("MISSING_ID", "dialogue_id is missing.", f"dialogue[{idx}].dialogue_id"))
        screenplay = data.get("screenplay") or {}
        for idx, scene in enumerate(screenplay.get("scenes") or []):
            if not str(scene.get("scene_id") or "").strip():
                issues.append(ValidationIssue("MISSING_ID", "scene_id is missing.", f"screenplay.scenes[{idx}].scene_id"))
            if not str(scene.get("location_id") or "").strip():
                issues.append(ValidationIssue("MISSING_ID", "location_id is missing.", f"screenplay.scenes[{idx}].location_id"))

        for idx, item in enumerate(data.get("props") or []):
            if not str(item.get("prop_id") or "").strip():
                issues.append(ValidationIssue("MISSING_ID", "prop_id is missing.", f"props[{idx}].prop_id"))
        style_bible = data.get("style_bible")
        if style_bible and not str(style_bible.get("style_id") or "").strip():
            issues.append(ValidationIssue("MISSING_ID", "style_id is missing.", "style_bible.style_id"))
        cinematic_plan = data.get("cinematic_plan") or {}
        graph = cinematic_plan.get("graph") or {}
        for idx, shot in enumerate(graph.get("shots") or []):
            if not str(shot.get("shot_id") or "").strip():
                issues.append(ValidationIssue("MISSING_ID", "shot_id is missing.", f"cinematic_plan.graph.shots[{idx}].shot_id"))
        for idx, asset in enumerate(data.get("assets") or []):
            if not str(asset.get("asset_id") or "").strip():
                issues.append(ValidationIssue("MISSING_ID", "asset_id is missing.", f"assets[{idx}].asset_id"))
        return issues

    @staticmethod
    def _check_raw_asset_hashes(data: Dict[str, Any]) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for idx, asset in enumerate(data.get("assets") or []):
            content_hash = str(asset.get("content_hash") or "")
            if not content_hash or len(content_hash) != 64:
                issues.append(
                    ValidationIssue(
                        "ASSET_MISSING_HASH",
                        f"Asset {asset.get('asset_id')} must carry a 64-char SHA-256 content hash.",
                        f"assets[{idx}].content_hash",
                    )
                )
        return issues

    @staticmethod
    def _dedupe(issues: List[ValidationIssue]) -> List[ValidationIssue]:
        seen = set()
        result = []
        for issue in issues:
            key = (issue.code, issue.path)
            if key not in seen:
                seen.add(key)
                result.append(issue)
        return result

    # ------------------------------------------------------------------
    # Rule: missing identifiers
    # ------------------------------------------------------------------
    @staticmethod
    def _check_missing_ids(package: VideoProductionPackage) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        if not str(package.project_id).strip():
            issues.append(ValidationIssue("MISSING_ID", "project_id is missing.", "project_id"))
        if not str(package.revision_id).strip():
            issues.append(ValidationIssue("MISSING_ID", "revision_id is missing.", "revision_id"))
        if not package.provenance or not str(package.provenance.created_by).strip():
            issues.append(ValidationIssue("MISSING_ID", "provenance.created_by is missing.", "provenance.created_by"))

        for idx, item in enumerate(package.characters):
            if not str(item.character_id).strip():
                issues.append(ValidationIssue("MISSING_ID", "character_id is missing.", f"characters[{idx}].character_id"))
        for idx, item in enumerate(package.locations):
            if not str(item.location_id).strip():
                issues.append(ValidationIssue("MISSING_ID", "location_id is missing.", f"locations[{idx}].location_id"))
        for idx, item in enumerate(package.dialogue):
            if not str(item.dialogue_id).strip():
                issues.append(ValidationIssue("MISSING_ID", "dialogue_id is missing.", f"dialogue[{idx}].dialogue_id"))
        return issues

    # ------------------------------------------------------------------
    # Rule: duplicate identifiers
    # ------------------------------------------------------------------
    @staticmethod
    def _check_duplicate_ids(package: VideoProductionPackage) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []

        def _dups(items: List[Any], id_attr: str, label: str) -> List[ValidationIssue]:
            seen: set = set()
            found: List[ValidationIssue] = []
            for item in items:
                id_value = str(getattr(item, id_attr))
                if id_value in seen:
                    found.append(ValidationIssue("DUPLICATE_ID", f"Duplicate {label} id {id_value!r}.", id_value))
                seen.add(id_value)
            return found

        issues.extend(_dups(package.characters, "character_id", "character"))
        issues.extend(_dups(package.locations, "location_id", "location"))
        issues.extend(_dups(package.props, "prop_id", "prop"))
        issues.extend(_dups(package.dialogue, "dialogue_id", "dialogue"))
        issues.extend(_dups(package.assets, "asset_id", "asset"))

        if package.screenplay is not None:
            issues.extend(_dups(package.screenplay.scene_ids, "value", "scene"))

        if package.cinematic_plan is not None:
            graph = package.cinematic_plan.graph
            issues.extend(_dups(graph.shots, "shot_id", "shot"))
            issues.extend(_dups(graph.dependencies, "dependency_id", "shot dependency"))
        return issues

    # ------------------------------------------------------------------
    # Rule: broken references
    # ------------------------------------------------------------------
    @staticmethod
    def _check_broken_references(package: VideoProductionPackage) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        character_ids = {str(c.character_id) for c in package.characters}
        location_ids = {str(loc.location_id) for loc in package.locations}
        asset_ids = {str(a.asset_id) for a in package.assets}
        dialogue_ids = {str(dlg.dialogue_id) for dlg in package.dialogue}
        scene_ids: set = set()
        shot_ids: set = set()
        if package.screenplay is not None:
            scene_ids = {str(s) for s in package.screenplay.scene_ids}
        if package.cinematic_plan is not None:
            shot_ids = {str(s.shot_id) for s in package.cinematic_plan.graph.shots}

        def _ref(value: Any, valid: set, path: str) -> Optional[ValidationIssue]:
            if str(value) not in valid:
                return ValidationIssue("BROKEN_REFERENCE", f"Reference {path}={value!r} does not exist.", path)
            return None

        # Character bible references
        for c in package.characters:
            for ref in c.portrait_asset_ids:
                issue = _ref(ref, asset_ids, f"characters/{c.character_id}/portrait_asset_ids")
                if issue:
                    issues.append(issue)

        # Location / prop / style references
        for loc in package.locations:
            for ref in loc.reference_asset_ids:
                issue = _ref(ref, asset_ids, f"locations/{loc.location_id}/reference_asset_ids")
                if issue:
                    issues.append(issue)
        for prop in package.props:
            for ref in prop.reference_asset_ids:
                issue = _ref(ref, asset_ids, f"props/{prop.prop_id}/reference_asset_ids")
                if issue:
                    issues.append(issue)
        if package.style_bible:
            for ref in package.style_bible.reference_asset_ids:
                issue = _ref(ref, asset_ids, "style_bible/reference_asset_ids")
                if issue:
                    issues.append(issue)

        # Embedded scene references (roadmap: screenplay.scenes)
        if package.screenplay is not None:
            for scene in package.screenplay.scenes:
                issue = _ref(scene.location_id, location_ids, f"scenes/{scene.scene_id}/location_id")
                if issue:
                    issues.append(issue)
                for ref in scene.character_ids:
                    issue = _ref(ref, character_ids, f"scenes/{scene.scene_id}/character_ids")
                    if issue:
                        issues.append(issue)
                for ref in scene.dialogue_line_ids:
                    issue = _ref(ref, dialogue_ids, f"scenes/{scene.scene_id}/dialogue_line_ids")
                    if issue:
                        issues.append(issue)

        # Dialogue references
        for d in package.dialogue:
            issue = _ref(d.scene_id, scene_ids, f"dialogue/{d.dialogue_id}/scene_id")
            if issue:
                issues.append(issue)
            issue = _ref(d.character_id, character_ids, f"dialogue/{d.dialogue_id}/character_id")
            if issue:
                issues.append(issue)

        # Cinematic plan references
        if package.cinematic_plan is not None:
            graph = package.cinematic_plan.graph
            for shot in graph.shots:
                issue = _ref(shot.scene_id, scene_ids, f"shots/{shot.shot_id}/scene_id")
                if issue:
                    issues.append(issue)
                for ref in shot.reference_asset_ids:
                    issue = _ref(ref, asset_ids, f"shots/{shot.shot_id}/reference_asset_ids")
                    if issue:
                        issues.append(issue)
                for ref in shot.dialogue_line_ids:
                    issue = _ref(ref, dialogue_ids, f"shots/{shot.shot_id}/dialogue_line_ids")
                    if issue:
                        issues.append(issue)
            for dep in graph.dependencies:
                issue = _ref(dep.from_shot_id, shot_ids, f"dependencies/{dep.dependency_id}/from_shot_id")
                if issue:
                    issues.append(issue)
                issue = _ref(dep.to_shot_id, shot_ids, f"dependencies/{dep.dependency_id}/to_shot_id")
                if issue:
                    issues.append(issue)
        return issues

    # ------------------------------------------------------------------
    # Rule: unordered scene/shot ordering
    # ------------------------------------------------------------------
    @staticmethod
    def _check_shot_ordering(package: VideoProductionPackage) -> List[ValidationIssue]:
        """Shots within a scene must appear in strictly increasing `order`.

        The check compares the AUTHORED list order (not a sorted copy) so
        out-of-sequence shot lists are rejected.
        """
        issues: List[ValidationIssue] = []
        if package.cinematic_plan is None:
            return issues
        graph = package.cinematic_plan.graph
        by_scene: Dict[str, List[Any]] = {}
        for shot in graph.shots:
            by_scene.setdefault(str(shot.scene_id), []).append(shot)
        for scene_id, shots in by_scene.items():
            for prev, curr in zip(shots, shots[1:]):
                if curr.order <= prev.order:
                    issues.append(
                        ValidationIssue(
                            "UNORDERED_SHOT",
                            f"Shots in scene {scene_id} are not ordered (order {prev.order} followed by {curr.order}).",
                            "cinematic_plan.graph.shots",
                        )
                    )
                    break
        return issues

    # ------------------------------------------------------------------
    # Rule: assets must carry a content hash
    # ------------------------------------------------------------------
    @staticmethod
    def _check_asset_hashes(package: VideoProductionPackage) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for idx, asset in enumerate(package.assets):
            if not asset.content_hash or len(asset.content_hash) != 64:
                issues.append(
                    ValidationIssue(
                        "ASSET_MISSING_HASH",
                        f"Asset {asset.asset_id} must carry a 64-char SHA-256 content hash.",
                        f"assets[{idx}].content_hash",
                    )
                )
        if package.final_deliverable is not None:
            if not package.final_deliverable.content_hash or len(package.final_deliverable.content_hash) != 64:
                issues.append(
                    ValidationIssue(
                        "ASSET_MISSING_HASH",
                        "Final deliverable must carry a 64-char SHA-256 content hash.",
                        "final_deliverable.content_hash",
                    )
                )
        return issues

    # ------------------------------------------------------------------
    # Rule: locked revision integrity (no silent mutation)
    # ------------------------------------------------------------------
    @staticmethod
    def _check_locked_revision_integrity(package: VideoProductionPackage) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        locked = package.approvals.locked if package.approvals else False
        if not locked:
            return issues
        actual_hash = package.content_hash()
        for approval in package.approvals.approvals:
            if approval.target_hash != actual_hash:
                issues.append(
                    ValidationIssue(
                        "LOCKED_REVISION_MUTATION",
                        f"Locked revision content hash {actual_hash[:12]}… does not match "
                        f"approval target hash {approval.target_hash[:12]}…; the artifact was mutated after lock.",
                        "approvals",
                    )
                )
        return issues

    # ------------------------------------------------------------------
    # Rule: approval targets must reference an existing approval hash
    # ------------------------------------------------------------------
    @staticmethod
    def _check_approval_targets(package: VideoProductionPackage) -> List[ValidationIssue]:
        """Approval must point at the package's specific revision + content hash."""
        issues: List[ValidationIssue] = []
        if not package.approvals:
            return issues
        for approval in package.approvals.approvals:
            if not approval.target_hash or len(approval.target_hash) != 64:
                issues.append(
                    ValidationIssue(
                        "INVALID_APPROVAL_TARGET",
                        f"Approval {approval.approval_id} must reference a 64-char target hash.",
                        "approvals",
                    )
                )
            if str(approval.revision_id) != str(package.revision_id):
                issues.append(
                    ValidationIssue(
                        "INVALID_APPROVAL_TARGET",
                        f"Approval {approval.approval_id} targets revision {approval.revision_id} "
                        f"but the package is revision {package.revision_id}.",
                        "approvals",
                    )
                )
        return issues


__all__ = ["ValidationIssue", "VideoProductionPackageValidator"]
