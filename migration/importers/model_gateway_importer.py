"""Importer for legacy provider credentials and routing rules into V2 Model Gateway."""

from __future__ import annotations

from typing import Any


class ModelGatewayImporter:
    """Imports legacy model router definitions into unified V2 Model Gateway."""

    def __init__(self) -> None:
        self.imported_rules: list[dict[str, Any]] = []

    def import_legacy_routing_rule(self, legacy_rule: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        """Convert legacy routing dictionary into V2 versioned routing rule."""
        rule_id = legacy_rule.get("id") or f"rule-{legacy_rule['task_family']}"
        v2_rule = {
            "id": rule_id,
            "name": legacy_rule.get("name", f"Rule for {legacy_rule['task_family']}"),
            "task_family": legacy_rule["task_family"],
            "priority": legacy_rule.get("priority", 50),
            "target_model_id": legacy_rule["target_model"],
            "fallback_model_id": legacy_rule.get("fallback_model"),
            "is_active": legacy_rule.get("active", True),
        }

        if not dry_run:
            self.imported_rules.append(v2_rule)

        return v2_rule
