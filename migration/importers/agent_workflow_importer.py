"""Importer for legacy workflow DAGs and agent prompts into V2 Agent Runtime."""

from __future__ import annotations

from typing import Any


class AgentWorkflowImporter:
    """Imports legacy agent workflows into V2 Agent Runtime DAG representations."""

    def __init__(self) -> None:
        self.imported_workflows: list[dict[str, Any]] = []

    def import_legacy_workflow(self, legacy_wf: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        """Convert legacy node/edge workflow structure into V2 Workflow aggregate."""
        nodes = []
        for n in legacy_wf.get("nodes", []):
            nodes.append({
                "id": n["id"],
                "label": n.get("name", n["id"]),
                "step_type": n.get("type", "generic_step"),
                "status": "pending",
            })

        edges = []
        for e in legacy_wf.get("transitions", legacy_wf.get("edges", [])):
            edges.append({
                "from": e.get("source", e.get("from")),
                "to": e.get("target", e.get("to")),
            })

        v2_wf = {
            "id": legacy_wf.get("id") or f"wf-{legacy_wf['name'].lower().replace(' ', '-')}",
            "name": legacy_wf["name"],
            "session_id": legacy_wf.get("session_id", "sess-migrated"),
            "status": "pending",
            "nodes": nodes,
            "edges": edges,
        }

        if not dry_run:
            self.imported_workflows.append(v2_wf)

        return v2_wf
