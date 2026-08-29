"""Exact Diff Engine for Continual Harness Refinements (Phase 10 — ban_ke_hoach_v1 §15, §16).

Computes structured diffs and human-readable unified diffs between harness versions
or proposed refinement entries before mutation is committed.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from windagent_core.domain.harness import HarnessEntry, HarnessVersion


class DiffEngine:
    """Computes exact structured diffs and human-readable preview texts for harness state mutations."""

    @classmethod
    def compute_diff(
        cls,
        base_entries: List[HarnessEntry],
        target_entries: List[HarnessEntry],
    ) -> Dict[str, Any]:
        """Computes a detailed, structured diff between base and target harness entry sets."""
        base_map: Dict[str, HarnessEntry] = {e.entry_id: e for e in base_entries}
        target_map: Dict[str, HarnessEntry] = {e.entry_id: e for e in target_entries}

        added: List[Dict[str, Any]] = []
        modified: List[Dict[str, Any]] = []
        removed: List[Dict[str, Any]] = []
        unchanged_count = 0

        # Check for additions and modifications
        for entry_id, target_entry in target_map.items():
            if entry_id not in base_map:
                added.append(
                    {
                        "entry_id": target_entry.entry_id,
                        "kind": target_entry.kind.value,
                        "name": target_entry.name,
                        "priority": target_entry.priority,
                        "enabled": target_entry.enabled,
                        "scope": target_entry.scope,
                        "content": target_entry.content,
                    }
                )
            else:
                base_entry = base_map[entry_id]
                field_changes = cls._compare_entry_fields(base_entry, target_entry)
                if field_changes:
                    modified.append(
                        {
                            "entry_id": entry_id,
                            "kind": target_entry.kind.value,
                            "name": target_entry.name,
                            "changes": field_changes,
                        }
                    )
                else:
                    unchanged_count += 1

        # Check for removals
        for entry_id, base_entry in base_map.items():
            if entry_id not in target_map:
                removed.append(
                    {
                        "entry_id": base_entry.entry_id,
                        "kind": base_entry.kind.value,
                        "name": base_entry.name,
                    }
                )

        summary = f"+{len(added)} added, ~{len(modified)} modified, -{len(removed)} removed, {unchanged_count} unchanged"

        diff_payload = {
            "summary": summary,
            "added_count": len(added),
            "modified_count": len(modified),
            "removed_count": len(removed),
            "unchanged_count": unchanged_count,
            "added": added,
            "modified": modified,
            "removed": removed,
        }

        diff_payload["rendered_diff"] = cls.render_text_diff(diff_payload)
        return diff_payload

    @classmethod
    def compute_version_diff(
        cls,
        parent_version: Optional[HarnessVersion],
        new_version: HarnessVersion,
    ) -> Dict[str, Any]:
        """Computes exact diff between a parent HarnessVersion and new HarnessVersion."""
        base_entries = parent_version.entries if parent_version else []
        return cls.compute_diff(base_entries, new_version.entries)

    @classmethod
    def _compare_entry_fields(
        cls,
        old_entry: HarnessEntry,
        new_entry: HarnessEntry,
    ) -> Dict[str, Any]:
        """Identifies specific changed fields between two entry versions."""
        changes: Dict[str, Any] = {}

        if old_entry.name != new_entry.name:
            changes["name"] = {"old": old_entry.name, "new": new_entry.name}

        if old_entry.kind != new_entry.kind:
            changes["kind"] = {"old": old_entry.kind.value, "new": new_entry.kind.value}

        if old_entry.priority != new_entry.priority:
            changes["priority"] = {"old": old_entry.priority, "new": new_entry.priority}

        if old_entry.enabled != new_entry.enabled:
            changes["enabled"] = {"old": old_entry.enabled, "new": new_entry.enabled}

        if old_entry.scope != new_entry.scope:
            changes["scope"] = {"old": old_entry.scope, "new": new_entry.scope}

        if old_entry.content != new_entry.content:
            changes["content"] = {"old": old_entry.content, "new": new_entry.content}

        return changes

    @classmethod
    def render_text_diff(cls, diff: Dict[str, Any]) -> str:
        """Renders structured diff into a human-readable text preview block."""
        lines = [f"=== HARNESS DIFF PREVIEW: {diff.get('summary', '')} ==="]

        added = diff.get("added", [])
        if added:
            lines.append("\n[+] ADDED ENTRIES:")
            for a in added:
                content_preview = json.dumps(a.get("content", {}), indent=2)
                lines.append(f"  + [{a.get('kind')}] '{a.get('name')}' (id={a.get('entry_id')}, priority={a.get('priority')}):")
                for c_line in content_preview.splitlines():
                    lines.append(f"      {c_line}")

        modified = diff.get("modified", [])
        if modified:
            lines.append("\n[~] MODIFIED ENTRIES:")
            for m in modified:
                lines.append(f"  ~ [{m.get('kind')}] '{m.get('name')}' (id={m.get('entry_id')}):")
                for field, change in m.get("changes", {}).items():
                    lines.append(f"      - {field}: {change.get('old')}")
                    lines.append(f"      + {field}: {change.get('new')}")

        removed = diff.get("removed", [])
        if removed:
            lines.append("\n[-] REMOVED ENTRIES:")
            for r in removed:
                lines.append(f"  - [{r.get('kind')}] '{r.get('name')}' (id={r.get('entry_id')})")

        return "\n".join(lines)

