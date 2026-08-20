#!/usr/bin/env python3
"""Deterministic Phase 4 route inventory generator for Architecture V3.

Inspects the actual registered FastAPI application routes (HTTP + WebSocket)
under ``/api/v3`` and ``/ws/v3`` and writes a deterministic inventory to
``artifacts/architecture_v3/phase_04/route-inventory.json``.

Each route is classified by an explicit, deterministic authority policy
(``_POLICY``) that maps every registered (method, path) to a classification:

- ``DURABLE`` — backed by a durable authority. The ``authority`` names the real
  authority surface:
  - ``v3_resources:<namespace>`` — the namespaced generic V3 resource table for
    canonical Wave A–D aggregates (content, configuration, and the generic
    task/work-management projection).
  - ``multi-agent-sql:<namespace>`` — the dedicated multi-agent SQL authority
    (``conversations``, ``agent_instances``, ``conversation_events``) reached
    through ``OrchestratorService -> MultiAgentRepository``. These are the
    active API authority; the same-named generic ``v3_resources`` namespaces
    are legacy/demo constants and are never the active authority.
  - ``dedicated-sql:route_locks_v3`` — the dedicated route-lock SQL authority
    reached through ``RouteLockService`` (``SQLRouteLockRepository``).
  - ``settings-file:settings.json`` — the settings PATCH surface.
- ``DERIVED`` — read-only / derived runtime state (health, probes, simulations,
  metrics, WebSocket realtime streams, workspace files, browser sessions,
  memory, logs, settings GET/schema). The ``source`` names the durable/runtime
  source they derive from and never claims ``v3_resources`` when they do not
  read/write it.

The policy fails closed: any registered route without an explicit policy raises
instead of silently defaulting to DURABLE/v3_resources.

Usage:
    uv run python scripts/generate_architecture_v3_phase4_inventory.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _pkg in ["apps/api", "core", "providers", "workflows"]:
    _p = str(_REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from windagent_api.main import app  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Explicit, deterministic authority policy.
#
# Key: (method, path) as registered on the app.
# Value: dict with:
#   classification: "DURABLE" | "DERIVED"
#   authority:      the durable authority (v3_resources:<namespace>,
#                   multi-agent-sql:<namespace>, dedicated-sql:route_locks_v3,
#                   settings-file) or the runtime/derived source for DERIVED.
#   source:         for DERIVED, the durable/runtime source it derives from;
#                   for DURABLE, the same durable authority.
#   migration_disposition: "migrated-to-v3_resources" | "cutover-to-..." |
#                          "no-migration" | ...
#
# Every registered /api/v3 and /ws/v3 route MUST appear here. The generator
# fails closed if a route has no policy.
# ─────────────────────────────────────────────────────────────────────────────

_DURABLE = "DURABLE"
_DERIVED = "DERIVED"


def _durable(namespace: str) -> dict:
    return {
        "classification": _DURABLE,
        "authority": f"v3_resources:{namespace}",
        "source": f"v3_resources:{namespace}",
        "migration_disposition": "migrated-to-v3_resources",
    }


def _multi_agent(namespace: str) -> dict:
    """Dedicated multi-agent SQL authority (conversations / agent_instances /
    conversation_events) reached through OrchestratorService -> MultiAgentRepository.

    The same-named generic ``v3_resources`` namespaces are legacy/demo constants
    and are NOT the active API authority.
    """
    return {
        "classification": _DURABLE,
        "authority": f"multi-agent-sql:{namespace}",
        "source": f"multi-agent-sql:{namespace}",
        "migration_disposition": "cutover-to-dedicated-multi-agent-sql",
    }


def _route_lock() -> dict:
    """Dedicated route-lock SQL authority (route_locks_v3) reached through
    RouteLockService. The generic ``v3_resources:route_locks`` namespace is not
    the active authority."""
    return {
        "classification": _DURABLE,
        "authority": "dedicated-sql:route_locks_v3",
        "source": "dedicated-sql:route_locks_v3",
        "migration_disposition": "cutover-to-dedicated-route-lock-sql",
    }


def _derived(source: str, authority: str | None = None) -> dict:
    return {
        "classification": _DERIVED,
        "authority": authority or source,
        "source": source,
        "migration_disposition": "no-migration",
    }


def _studio_durable(namespace: str) -> dict:
    """Durable studio SQL authority (StudioApplicationService SQL adapters)."""
    return {
        "classification": _DURABLE,
        "authority": f"studio:{namespace}",
        "source": f"studio:{namespace}",
        "migration_disposition": "no-migration",
    }


_POLICY: dict[tuple[str, str], dict] = {
    # ── Agent definitions / instances (Wave D) ─────────────────────────────
    ("GET", "/api/v3/agent-definitions"): _durable("agent_definitions"),
    ("POST", "/api/v3/agent-definitions"): _durable("agent_definitions"),
    ("DELETE", "/api/v3/agent-definitions/{definition_id}"): _durable("agent_definitions"),
    ("GET", "/api/v3/agent-definitions/{definition_id}"): _durable("agent_definitions"),
    ("PATCH", "/api/v3/agent-definitions/{definition_id}"): _durable("agent_definitions"),
    ("GET", "/api/v3/agent-definitions/{definition_id}/activity"): _durable("agent_activity"),
    ("GET", "/api/v3/agent-instances"): _multi_agent("agent_instances"),
    ("POST", "/api/v3/agent-instances"): _multi_agent("agent_instances"),
    ("GET", "/api/v3/agent-instances/{instance_id}"): _multi_agent("agent_instances"),
    ("POST", "/api/v3/agent-instances/{instance_id}/restart"): _multi_agent("agent_instances"),
    ("POST", "/api/v3/agent-instances/{instance_id}/start"): _multi_agent("agent_instances"),
    ("POST", "/api/v3/agent-instances/{instance_id}/stop"): _multi_agent("agent_instances"),
    ("GET", "/api/v3/agents/metrics"): _derived(
        "v3_resources:agent_definitions,multi-agent-sql:agent_instances"
    ),

    # ── Assets (Wave C) ────────────────────────────────────────────────────
    ("GET", "/api/v3/assets"): _durable("assets"),
    ("POST", "/api/v3/assets"): _durable("assets"),
    ("GET", "/api/v3/assets/{asset_id}"): _durable("assets"),
    ("POST", "/api/v3/assets/{asset_id}/actions/approve"): _durable("assets"),
    ("POST", "/api/v3/assets/{asset_id}/actions/reject"): _durable("assets"),
    ("GET", "/api/v3/assets/{asset_id}/dependencies"): _durable("assets"),
    ("GET", "/api/v3/assets/{asset_id}/provenance"): _durable("assets"),
    ("GET", "/api/v3/assets/{asset_id}/revisions"): _durable("asset_revisions"),

    # ── Browser (runtime sessions, DERIVED) ────────────────────────────────
    ("GET", "/api/v3/browser/sessions"): _derived("runtime:browser-sessions"),
    ("POST", "/api/v3/browser/sessions"): _derived("runtime:browser-sessions"),
    ("DELETE", "/api/v3/browser/sessions/{session_id}"): _derived("runtime:browser-sessions"),
    ("GET", "/api/v3/browser/sessions/{session_id}"): _derived("runtime:browser-sessions"),
    ("POST", "/api/v3/browser/sessions/{session_id}/click"): _derived("runtime:browser-sessions"),
    ("GET", "/api/v3/browser/sessions/{session_id}/extract"): _derived("runtime:browser-sessions"),
    ("POST", "/api/v3/browser/sessions/{session_id}/navigate"): _derived("runtime:browser-sessions"),
    ("GET", "/api/v3/browser/sessions/{session_id}/screenshot"): _derived("runtime:browser-sessions"),
    ("POST", "/api/v3/browser/sessions/{session_id}/scroll"): _derived("runtime:browser-sessions"),
    ("POST", "/api/v3/browser/sessions/{session_id}/type"): _derived("runtime:browser-sessions"),

    # ── Characters (Wave C) ────────────────────────────────────────────────
    ("DELETE", "/api/v3/characters/{character_id}"): _durable("characters"),
    ("GET", "/api/v3/characters/{character_id}"): _durable("characters"),
    ("PATCH", "/api/v3/characters/{character_id}"): _durable("characters"),
    ("GET", "/api/v3/characters/{character_id}/assets"): _durable("characters"),
    ("GET", "/api/v3/characters/{character_id}/relationships"): _durable("characters"),

    # ── Conversations (dedicated multi-agent SQL authority) ────────────────
    ("GET", "/api/v3/conversations"): _multi_agent("conversations"),
    ("POST", "/api/v3/conversations"): _multi_agent("conversations"),
    # Conversation detail reads the dedicated conversations/agent_instances/
    # conversation_events authority plus the generic tasks projection.
    ("GET", "/api/v3/conversations/{conversation_id}"): {
        "classification": _DURABLE,
        "authority": (
            "multi-agent-sql:conversations,agent_instances,conversation_events"
        ),
        "source": (
            "multi-agent-sql:conversations,agent_instances,conversation_events,"
            "v3_resources:tasks"
        ),
        "migration_disposition": "cutover-to-dedicated-multi-agent-sql",
    },
    ("GET", "/api/v3/conversations/{conversation_id}/agents"): _multi_agent("agent_instances"),
    ("POST", "/api/v3/conversations/{conversation_id}/agents/{agent_id}/stop"): _multi_agent("agent_instances"),
    ("GET", "/api/v3/conversations/{conversation_id}/events"): _multi_agent("conversation_events"),
    ("GET", "/api/v3/conversations/{conversation_id}/tasks"): _durable("tasks"),

    # ── Dashboard (DERIVED) ────────────────────────────────────────────────
    ("GET", "/api/v3/dashboard/summary"): _derived("v3_resources:projects,episodes,tasks"),

    # ── Episodes (Wave A) ──────────────────────────────────────────────────
    ("GET", "/api/v3/episodes"): _durable("episodes"),
    ("DELETE", "/api/v3/episodes/{episode_id}"): _durable("episodes"),
    ("GET", "/api/v3/episodes/{episode_id}"): _durable("episodes"),
    ("PATCH", "/api/v3/episodes/{episode_id}"): _durable("episodes"),
    ("GET", "/api/v3/episodes/{episode_id}/artifacts"): _durable("episode_artifacts"),
    ("POST", "/api/v3/episodes/{episode_id}/cancel-run"): _durable("episode_runs"),
    ("POST", "/api/v3/episodes/{episode_id}/decision"): _durable("episodes"),
    ("POST", "/api/v3/episodes/{episode_id}/lock"): _durable("episodes"),
    ("GET", "/api/v3/episodes/{episode_id}/production"): _durable("production_plans"),
    ("POST", "/api/v3/episodes/{episode_id}/production/animation/submit"): _durable("production_jobs"),
    ("POST", "/api/v3/episodes/{episode_id}/production/audio/submit"): _durable("production_jobs"),
    ("GET", "/api/v3/episodes/{episode_id}/production/delivery"): _durable("delivery_artifacts"),
    ("GET", "/api/v3/episodes/{episode_id}/production/jobs"): _durable("production_jobs"),
    ("POST", "/api/v3/episodes/{episode_id}/production/plan"): _durable("production_plans"),
    ("POST", "/api/v3/episodes/{episode_id}/production/render/submit"): _durable("production_jobs"),
    ("POST", "/api/v3/episodes/{episode_id}/production/video/submit"): _durable("production_jobs"),
    ("POST", "/api/v3/episodes/{episode_id}/production/{stage}/cancel"): _durable("production_jobs"),
    ("POST", "/api/v3/episodes/{episode_id}/production/{stage}/retry"): _durable("production_jobs"),
    ("GET", "/api/v3/episodes/{episode_id}/runs"): _durable("episode_runs"),
    ("POST", "/api/v3/episodes/{episode_id}/select-idea"): _durable("episodes"),
    ("GET", "/api/v3/episodes/{episode_id}/shots"): _durable("shots"),
    ("POST", "/api/v3/episodes/{episode_id}/shots"): _durable("shots"),
    ("POST", "/api/v3/episodes/{episode_id}/start-generation"): _durable("episodes"),
    ("GET", "/api/v3/episodes/{episode_id}/storyboard"): _durable("storyboards"),
    ("POST", "/api/v3/episodes/{episode_id}/storyboard/actions/sync"): _durable("storyboards"),
    ("GET", "/api/v3/episodes/{episode_id}/storyboard/scenes"): _durable("scenes"),

    # ── Files (workspace files, DERIVED) ───────────────────────────────────
    ("GET", "/api/v3/files"): _derived("runtime:workspace-files"),
    ("POST", "/api/v3/files"): _derived("runtime:workspace-files"),
    ("POST", "/api/v3/files/upload"): _derived("runtime:workspace-files"),
    ("DELETE", "/api/v3/files/{file_id}"): _derived("runtime:workspace-files"),
    ("GET", "/api/v3/files/{file_id}"): _derived("runtime:workspace-files"),
    ("GET", "/api/v3/files/{file_id}/download"): _derived("runtime:workspace-files"),

    # ── Logs (DERIVED runtime log buffer) ──────────────────────────────────
    ("GET", "/api/v3/logs"): _derived("runtime:log-service"),
    ("GET", "/api/v3/logs/sources"): _derived("runtime:log-service"),

    # ── Memory (DERIVED) ───────────────────────────────────────────────────
    ("GET", "/api/v3/memory"): _derived("runtime:memory"),
    ("POST", "/api/v3/memory"): _derived("runtime:memory"),
    ("POST", "/api/v3/memory/search"): _derived("runtime:memory"),
    ("GET", "/api/v3/memory/{memory_id}"): _derived("runtime:memory"),

    # ── Models (Wave B) ────────────────────────────────────────────────────
    ("GET", "/api/v3/models"): _durable("models"),
    ("GET", "/api/v3/models/{model_id:path}"): _durable("models"),

    # ── Monitoring (DERIVED) ───────────────────────────────────────────────
    ("GET", "/api/v3/monitoring/agents"): _derived("runtime:monitoring"),
    ("GET", "/api/v3/monitoring/providers"): _derived("runtime:monitoring"),
    ("GET", "/api/v3/monitoring/queues"): _derived("runtime:monitoring"),
    ("GET", "/api/v3/monitoring/runs"): _derived("runtime:monitoring"),
    ("GET", "/api/v3/monitoring/workers"): _derived("runtime:monitoring"),

    # ── Production (Wave C) ────────────────────────────────────────────────
    ("GET", "/api/v3/production/jobs/{job_id}"): _durable("production_jobs"),

    # ── Project templates (DERIVED) ────────────────────────────────────────
    ("GET", "/api/v3/project-templates"): _derived("runtime:project-templates"),

    # ── Projects (Wave A) ──────────────────────────────────────────────────
    ("GET", "/api/v3/projects"): _durable("projects"),
    ("POST", "/api/v3/projects"): _durable("projects"),
    ("GET", "/api/v3/projects/{project_id}"): _durable("projects"),
    ("PATCH", "/api/v3/projects/{project_id}"): _durable("projects"),
    ("GET", "/api/v3/projects/{project_id}/characters"): _durable("characters"),
    ("POST", "/api/v3/projects/{project_id}/characters"): _durable("characters"),
    ("GET", "/api/v3/projects/{project_id}/episodes"): _durable("episodes"),
    ("POST", "/api/v3/projects/{project_id}/episodes"): _durable("episodes"),
    ("GET", "/api/v3/projects/{project_id}/world"): _durable("world_bibles"),
    ("PATCH", "/api/v3/projects/{project_id}/world"): _durable("world_bibles"),
    ("GET", "/api/v3/projects/{project_id}/world/factions"): _durable("factions"),
    ("POST", "/api/v3/projects/{project_id}/world/factions"): _durable("factions"),
    ("GET", "/api/v3/projects/{project_id}/world/locations"): _durable("locations"),
    ("POST", "/api/v3/projects/{project_id}/world/locations"): _durable("locations"),
    ("GET", "/api/v3/projects/{project_id}/world/lore"): _durable("lore"),
    ("POST", "/api/v3/projects/{project_id}/world/lore"): _durable("lore"),

    # ── Providers (Wave B) ─────────────────────────────────────────────────
    ("GET", "/api/v3/providers"): _durable("providers"),
    ("POST", "/api/v3/providers"): _durable("providers"),
    ("GET", "/api/v3/providers/health"): _derived("v3_resources:providers"),
    ("GET", "/api/v3/providers/{provider_id}"): _durable("providers"),
    ("GET", "/api/v3/providers/{provider_id}/endpoints"): _durable("providers"),
    ("GET", "/api/v3/providers/{provider_id}/health"): _derived("v3_resources:providers"),
    ("GET", "/api/v3/providers/{provider_id}/models"): _durable("models"),
    ("POST", "/api/v3/providers/{provider_id}/test-connection"): _derived("v3_resources:providers"),
    ("GET", "/api/v3/providers/rules"): _durable("routing_rules"),
    ("POST", "/api/v3/providers/rules"): _durable("routing_rules"),

    # ── Reviews (Wave C) ───────────────────────────────────────────────────
    ("GET", "/api/v3/reviews"): _durable("reviews"),
    ("POST", "/api/v3/reviews"): _durable("reviews"),
    ("GET", "/api/v3/reviews/{review_id}"): _durable("reviews"),
    ("GET", "/api/v3/reviews/{review_id}/comments"): _durable("review_comments"),
    ("POST", "/api/v3/reviews/{review_id}/comments"): _durable("review_comments"),
    ("POST", "/api/v3/reviews/{review_id}/decision"): _durable("review_decisions"),

    # ── Routing (Wave B) ───────────────────────────────────────────────────
    ("GET", "/api/v3/routing/graph"): _derived("v3_resources:routing_rules"),
    ("GET", "/api/v3/routing/locks/{lock_id}"): _route_lock(),
    ("GET", "/api/v3/routing/metrics"): _derived("v3_resources:routing_rules"),
    ("GET", "/api/v3/routing/rules"): _durable("routing_rules"),
    ("POST", "/api/v3/routing/rules"): _durable("routing_rules"),
    ("DELETE", "/api/v3/routing/rules/{rule_id}"): _durable("routing_rules"),
    ("GET", "/api/v3/routing/rules/{rule_id}"): _durable("routing_rules"),
    ("PATCH", "/api/v3/routing/rules/{rule_id}"): _durable("routing_rules"),
    ("POST", "/api/v3/routing/simulations"): _derived(
        "v3_resources:routing_rules,dedicated-sql:route_locks_v3"
    ),

    # ── Settings (GET/schema DERIVED; PATCH DURABLE settings-file) ─────────
    ("GET", "/api/v3/settings"): _derived("settings-file:settings.json"),
    ("PATCH", "/api/v3/settings"): {
        "classification": _DURABLE,
        "authority": "settings-file:settings.json",
        "source": "settings-file:settings.json",
        "migration_disposition": "no-migration",
    },
    ("GET", "/api/v3/settings/schema"): _derived("settings-file:settings.json"),

    # ── Shots (Wave C) ─────────────────────────────────────────────────────
    ("GET", "/api/v3/shots/{shot_id}"): _durable("shots"),
    ("PATCH", "/api/v3/shots/{shot_id}"): _durable("shots"),

    # ── Storyboard (Wave C) ────────────────────────────────────────────────
    ("POST", "/api/v3/storyboard/scenes"): _durable("scenes"),
    ("PATCH", "/api/v3/storyboard/scenes/{scene_id}"): _durable("scenes"),
    ("POST", "/api/v3/storyboard/scenes/{scene_id}/generations"): _durable("generation_jobs"),
    ("GET", "/api/v3/storyboard/scenes/{scene_id}/generations/{generation_id}"): _durable("generation_jobs"),

    # ── Studio (durable SQL authority + DERIVED views) ─────────────────────
    ("POST", "/api/v3/studio/series"): _studio_durable("series"),
    ("GET", "/api/v3/studio/series"): _studio_durable("series"),
    ("GET", "/api/v3/studio/series/{series_id}"): _studio_durable("series"),
    ("POST", "/api/v3/studio/series/{series_id}/episodes"): _studio_durable("episodes"),
    ("GET", "/api/v3/studio/series/{series_id}/episodes"): _studio_durable("episodes"),
    ("GET", "/api/v3/studio/episodes/{episode_id}"): _studio_durable("episodes"),
    ("POST", "/api/v3/studio/episodes/{episode_id}/runs"): _studio_durable("runs"),
    ("GET", "/api/v3/studio/runs/{run_id}"): _studio_durable("runs"),
    ("GET", "/api/v3/studio/runs/{run_id}/events"): _studio_durable("runs"),
    ("POST", "/api/v3/studio/episodes/{episode_id}/idea-selection"): _studio_durable("decisions"),
    ("POST", "/api/v3/studio/episodes/{episode_id}/approvals"): _studio_durable("decisions"),
    ("POST", "/api/v3/studio/episodes/{episode_id}/revisions"): _studio_durable("revisions"),
    ("POST", "/api/v3/studio/episodes/{episode_id}/screenplay-lock"): _studio_durable("decisions"),
    ("GET", "/api/v3/studio/episodes/{episode_id}/artifacts"): _studio_durable("artifacts"),
    ("GET", "/api/v3/studio/artifacts/{artifact_id}"): _studio_durable("artifacts"),
    ("GET", "/api/v3/studio/capabilities"): _derived("runtime:studio"),
    ("GET", "/api/v3/studio/readiness"): _derived("runtime:studio"),

    # ── System (DERIVED) ───────────────────────────────────────────────────
    ("GET", "/api/v3/system/health"): _derived("runtime:system"),
    ("GET", "/api/v3/system/metrics"): _derived("runtime:system"),

    # ── Tasks (Wave A) ─────────────────────────────────────────────────────
    ("GET", "/api/v3/tasks"): _durable("tasks"),
    ("POST", "/api/v3/tasks"): _durable("tasks"),
    ("GET", "/api/v3/tasks/{task_id}"): _durable("tasks"),
    ("PATCH", "/api/v3/tasks/{task_id}"): _durable("tasks"),
    ("POST", "/api/v3/tasks/{task_id}/cancel"): _durable("tasks"),
    ("POST", "/api/v3/tasks/{task_id}/retry"): _durable("tasks"),

    # ── Workflows (Wave A) ─────────────────────────────────────────────────
    ("GET", "/api/v3/workflow-runs"): _durable("workflow_runs"),
    ("POST", "/api/v3/workflow-runs"): _durable("workflow_runs"),
    ("GET", "/api/v3/workflow-runs/{run_id}"): _durable("workflow_runs"),
    ("POST", "/api/v3/workflow-runs/{run_id}/cancel"): _durable("workflow_runs"),
    ("POST", "/api/v3/workflow-runs/{run_id}/pause"): _durable("workflow_runs"),
    ("POST", "/api/v3/workflow-runs/{run_id}/resume"): _durable("workflow_runs"),
    ("POST", "/api/v3/workflow-runs/{run_id}/retry"): _durable("workflow_runs"),
    ("GET", "/api/v3/workflows"): _durable("workflows"),
    ("POST", "/api/v3/workflows"): _durable("workflows"),
    ("GET", "/api/v3/workflows/{workflow_id}"): _durable("workflows"),
    ("PATCH", "/api/v3/workflows/{workflow_id}"): _durable("workflows"),

    # ── WebSocket realtime streams (DERIVED) ───────────────────────────────
    ("WS", "/ws/v3/agent-system"): _derived("runtime:realtime"),
    ("WS", "/ws/v3/browser"): _derived("runtime:realtime"),
    ("WS", "/ws/v3/episodes/{episode_id}"): _derived("runtime:realtime"),
    ("WS", "/ws/v3/logs"): _derived("runtime:realtime"),
    ("WS", "/ws/v3/model-infra"): _derived("runtime:realtime"),
    ("WS", "/ws/v3/production/{episode_id}"): _derived("runtime:realtime"),
    ("WS", "/ws/v3/storyboard/{episode_id}"): _derived("runtime:realtime"),
    ("WS", "/ws/v3/system/metrics"): _derived("runtime:realtime"),
}


def _iter_routes(router, prefix: str = ""):
    """Recursively yield (method, path, module) for a router's routes.

    FastAPI 0.139+ wraps included routers in ``_IncludedRouter`` objects whose
    ``original_router`` is the actual ``APIRouter``. Traverse both shapes and
    carry the ``include_context`` prefix so nested-prefix routes resolve to
    their fully-qualified registered path (matching the architecture test's
    ``_actual_routes`` walker).
    """
    for route in getattr(router, "routes", []):
        # _IncludedRouter: descend into the wrapped APIRouter, carrying its
        # include prefix so nested-prefix routes resolve to the full path.
        original = getattr(route, "original_router", None)
        if original is not None:
            ctx = getattr(route, "include_context", None)
            child_prefix = getattr(ctx, "prefix", "") if ctx is not None else ""
            yield from _iter_routes(original, prefix + child_prefix)
            continue
        path = getattr(route, "path", "")
        if not path:
            continue
        effective_path = prefix + path
        methods = getattr(route, "methods", None)
        if methods:
            for method in sorted(methods):
                yield method, effective_path, _module_of(route)
        else:
            yield "WS", effective_path, _module_of(route)


def _module_of(route) -> str:
    endpoint = getattr(route, "endpoint", None)
    if endpoint is not None:
        return f"{endpoint.__module__}.{endpoint.__name__}"
    return ""


def _policy_for(method: str, path: str) -> dict:
    """Return the explicit policy for a route, failing closed if none exists."""
    policy = _POLICY.get((method, path))
    if policy is None:
        raise KeyError(
            f"No inventory authority policy for registered route {method} {path}. "
            "Add an explicit policy to _POLICY in "
            "scripts/generate_architecture_v3_phase4_inventory.py."
        )
    return policy


def build_inventory() -> dict:
    """Build the deterministic route inventory dict from the registered app.

    Exposed separately from ``main`` so architecture tests can re-derive the
    inventory in-process and assert byte/logical determinism against the
    committed artifact without spawning a subprocess.
    """
    routes = []
    seen = set()
    for method, path, module in _iter_routes(app):
        if not (path.startswith("/api/v3") or path.startswith("/ws/v3")):
            continue
        key = (method, path)
        if key in seen:
            continue
        seen.add(key)
        policy = _policy_for(method, path)
        routes.append(
            {
                "method": method,
                "path": path,
                "module": module,
                "classification": policy["classification"],
                "authority": policy["authority"],
                "source": policy["source"],
                "migration_disposition": policy["migration_disposition"],
            }
        )

    routes.sort(key=lambda r: (r["path"], r["method"]))
    return {
        "phase": "04",
        "generated_by": "scripts/generate_architecture_v3_phase4_inventory.py",
        "route_count": len(routes),
        "routes": routes,
    }


def main() -> int:
    inventory = build_inventory()

    out_dir = _REPO_ROOT / "artifacts" / "architecture_v3" / "phase_04"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "route-inventory.json"
    out_path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print(f"Wrote {len(inventory['routes'])} routes to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
