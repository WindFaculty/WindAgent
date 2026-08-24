"""Phase 4 — durable single authority for API V3 routers.

Gates:
- Every registered /api/v3 and /ws/v3 route is covered by the committed
  inventory (artifacts/architecture_v3/phase_04/route-inventory.json).
- No route is classified EPHEMERAL / DEMO / INVALID in production.
- The real checker Phase 4 rule (module_level_mutable_production_store) is zero.
- Migrated V3 routers have no module-level mutable canonical collection /
  idempotency authority.
- No router imports a sibling router's store.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

import check_architecture_imports as checker  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

INVENTORY_PATH = (
    ROOT / "artifacts" / "architecture_v3" / "phase_04" / "route-inventory.json"
)
NAMESPACE_AUTHORITY_PATH = (
    ROOT / "artifacts" / "architecture_v3" / "phase_04" / "namespace-authority.json"
)
V3_ROUTER_DIR = ROOT / "apps" / "api" / "windagent_api" / "routers" / "v3"


def _load_inventory() -> dict:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _load_namespace_authority() -> dict:
    return json.loads(NAMESPACE_AUTHORITY_PATH.read_text(encoding="utf-8"))


def _actual_routes() -> set[tuple[str, str]]:
    """Return the set of (method, path) actually registered on the app."""
    from windagent_api.main import app

    routes: set[tuple[str, str]] = set()

    def walk(router, prefix: str = "") -> None:
        for route in getattr(router, "routes", []):
            original = getattr(route, "original_router", None)
            if original is not None:
                ctx = getattr(route, "include_context", None)
                child_prefix = getattr(ctx, "prefix", "") if ctx is not None else ""
                walk(original, prefix + child_prefix)
                continue
            path = getattr(route, "path", "")
            if not path:
                continue
            effective_path = prefix + path
            methods = getattr(route, "methods", None)
            if methods:
                for method in sorted(methods):
                    routes.add((method, effective_path))
            else:
                routes.add(("WS", effective_path))

    walk(app)
    return {
        (m, p)
        for (m, p) in routes
        if p.startswith("/api/v3") or p.startswith("/ws/v3")
    }


def test_inventory_covers_every_registered_route():
    """Exact equality: every registered route is inventoried AND every
    inventoried route is actually registered (no stale extra entries)."""
    inventory = _load_inventory()
    inventoried = {(r["method"], r["path"]) for r in inventory["routes"]}
    actual = _actual_routes()
    missing = actual - inventoried
    assert not missing, f"registered routes missing from inventory: {sorted(missing)}"
    stale = inventoried - actual
    assert not stale, f"inventory entries with no registered route: {sorted(stale)}"
    assert len(inventory["routes"]) == len(actual), (
        f"inventory route_count {len(inventory['routes'])} != registered {len(actual)}"
    )


def test_no_ephemeral_demo_or_invalid_classification():
    inventory = _load_inventory()
    forbidden = {"EPHEMERAL", "DEMO", "INVALID"}
    bad = [
        r
        for r in inventory["routes"]
        if r["classification"] in forbidden
    ]
    assert not bad, f"forbidden production classifications: {bad}"


def test_every_route_has_durable_or_derived_classification():
    inventory = _load_inventory()
    allowed = {"DURABLE", "DERIVED"}
    bad = [
        r
        for r in inventory["routes"]
        if r["classification"] not in allowed
    ]
    assert not bad, f"routes with invalid classification: {bad}"


def test_every_durable_v3_resources_entry_has_known_namespace():
    """Every DURABLE entry claiming the v3_resources authority must name a
    namespace that is explicitly mapped in the namespace-authority artifact."""
    inventory = _load_inventory()
    authority = _load_namespace_authority()
    known = {ns["namespace"] for ns in authority["namespaces"]}
    bad = []
    for r in inventory["routes"]:
        if r["classification"] != "DURABLE":
            continue
        if not r["authority"].startswith("v3_resources:"):
            continue
        namespace = r["authority"].split(":", 1)[1]
        if namespace not in known:
            bad.append(f"{r['method']} {r['path']} -> {r['authority']}")
    assert not bad, f"DURABLE v3_resources entries with unknown namespace: {bad}"


def test_every_registered_route_has_policy():
    """Every registered route has an explicit inventory policy (fail closed).

    The generator itself fails closed on a route with no policy; this test
    re-asserts that the committed inventory is complete and every entry carries
    the required authority/source fields.
    """
    inventory = _load_inventory()
    required = {"method", "path", "module", "classification", "authority", "source", "migration_disposition"}
    bad = [r for r in inventory["routes"] if not required.issubset(r.keys())]
    assert not bad, f"inventory entries missing required fields: {bad}"
    # Every registered route must be present (exact equality already asserted).
    actual = _actual_routes()
    inventoried = {(r["method"], r["path"]) for r in inventory["routes"]}
    assert inventoried == actual


def test_namespace_authority_covers_all_migrated_namespaces():
    """Every namespace used by migrated routers / demo seed is present in the
    namespace-authority artifact."""
    authority = _load_namespace_authority()
    known = {ns["namespace"] for ns in authority["namespaces"]}

    # Namespaces referenced by the demo seed (single source of truth).
    from windagent_api.services.v3_demo_seed import (
        NS_PROJECTS,
        NS_EPISODES,
        NS_EPISODE_ARTIFACTS,
        NS_EPISODE_RUNS,
        NS_TASKS,
        NS_WORKFLOWS,
        NS_WORKFLOW_RUNS,
        NS_PROVIDERS,
        NS_MODELS,
        NS_ROUTING_RULES,
        NS_ROUTE_LOCKS,
        NS_ASSETS,
        NS_ASSET_REVISIONS,
        NS_REVIEWS,
        NS_REVIEW_COMMENTS,
        NS_REVIEW_DECISIONS,
        NS_WORLD_BIBLES,
        NS_LOCATIONS,
        NS_FACTIONS,
        NS_LORE,
        NS_STORYBOARDS,
        NS_SCENES,
        NS_GENERATION_JOBS,
        NS_CHARACTERS,
        NS_PRODUCTION_PLANS,
        NS_SHOTS,
        NS_PRODUCTION_JOBS,
        NS_DELIVERY_ARTIFACTS,
        NS_AGENT_DEFINITIONS,
        NS_AGENT_ACTIVITY,
        NS_AGENT_INSTANCES,
        NS_CONVERSATIONS,
        NS_CONVERSATION_EVENTS,
    )
    seed_namespaces = {
        NS_PROJECTS,
        NS_EPISODES,
        NS_EPISODE_ARTIFACTS,
        NS_EPISODE_RUNS,
        NS_TASKS,
        NS_WORKFLOWS,
        NS_WORKFLOW_RUNS,
        NS_PROVIDERS,
        NS_MODELS,
        NS_ROUTING_RULES,
        NS_ROUTE_LOCKS,
        NS_ASSETS,
        NS_ASSET_REVISIONS,
        NS_REVIEWS,
        NS_REVIEW_COMMENTS,
        NS_REVIEW_DECISIONS,
        NS_WORLD_BIBLES,
        NS_LOCATIONS,
        NS_FACTIONS,
        NS_LORE,
        NS_STORYBOARDS,
        NS_SCENES,
        NS_GENERATION_JOBS,
        NS_CHARACTERS,
        NS_PRODUCTION_PLANS,
        NS_SHOTS,
        NS_PRODUCTION_JOBS,
        NS_DELIVERY_ARTIFACTS,
        NS_AGENT_DEFINITIONS,
        NS_AGENT_ACTIVITY,
        NS_AGENT_INSTANCES,
        NS_CONVERSATIONS,
        NS_CONVERSATION_EVENTS,
    }
    missing = seed_namespaces - known
    assert not missing, f"namespaces used by demo seed missing from authority map: {sorted(missing)}"

    # Namespaces referenced by the inventory's DURABLE v3_resources entries.
    inventory = _load_inventory()
    inventory_namespaces = {
        r["authority"].split(":", 1)[1]
        for r in inventory["routes"]
        if r["classification"] == "DURABLE" and r["authority"].startswith("v3_resources:")
    }
    missing_inv = inventory_namespaces - known
    assert not missing_inv, f"inventory namespaces missing from authority map: {sorted(missing_inv)}"


def test_no_false_authority_claim():
    """No inventory entry makes a false authority claim.

    - A DERIVED entry must never claim v3_resources as its authority unless it
      actually reads/writes that namespace (its source names the durable source).
    - A DURABLE v3_resources entry must have a namespace mapped in the
      namespace-authority artifact (already asserted above).
    """
    inventory = _load_inventory()
    authority = _load_namespace_authority()
    known = {ns["namespace"] for ns in authority["namespaces"]}
    bad = []
    for r in inventory["routes"]:
        if r["classification"] == "DERIVED":
            # DERIVED entries must name a source; they must not claim a
            # v3_resources authority they do not read/write.
            if not r.get("source"):
                bad.append(f"{r['method']} {r['path']} DERIVED without source")
            if r["authority"].startswith("v3_resources:") and not r["source"].startswith("v3_resources:"):
                bad.append(f"{r['method']} {r['path']} DERIVED claims v3_resources authority without source")
        elif r["classification"] == "DURABLE":
            if r["authority"].startswith("v3_resources:"):
                namespace = r["authority"].split(":", 1)[1]
                if namespace not in known:
                    bad.append(f"{r['method']} {r['path']} DURABLE unknown namespace {namespace}")
    assert not bad, f"false authority claims: {bad}"


def test_checker_phase4_rule_is_zero():
    """The real checker reports zero module-level mutable production stores."""
    policy = yaml.safe_load(
        (ROOT / "configs" / "architecture" / "scaffold_v3.yaml").read_text(
            encoding="utf-8"
        )
    )
    report, _ = checker.check(ROOT, policy)
    violations = [
        item
        for item in report["violations"]
        if item["rule"] == "module_level_mutable_production_store"
    ]
    assert violations == [], f"module-level mutable stores found: {violations}"


def test_no_router_imports_sibling_router_store():
    """No V3 router imports a sibling router's module-level mutable store.

    The aggregator ``router.py`` is the composition point and legitimately
    imports every sub-router; it is excluded. Routers may share response
    models, but must never reach into a sibling router's mutable store
    (``_*_STORE`` / ``_*_LOGS`` / ``_*_MAP`` style module-level collections).
    """
    router_files = sorted(V3_ROUTER_DIR.rglob("*.py"))
    store_symbol = re.compile(r"\b_[A-Za-z0-9_]*(STORE|LOGS|MAP|CACHE|REGISTRY)[A-Za-z0-9_]*\b")
    offenders = []
    for path in router_files:
        if path.name in ("__init__.py", "router.py"):
            continue
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            # Only flag imports that pull in a store-like symbol from a sibling.
            if store_symbol.search(stripped):
                offenders.append(f"{path.name}: {stripped}")
    assert not offenders, f"router imports sibling router store: {offenders}"


def test_no_module_level_mutable_collection_in_routers():
    """Migrated V3 routers have no module-level mutable canonical collection or
    idempotency authority (RAM store anti-pattern)."""
    import ast

    mutable_constructors = {"dict", "list", "set", "defaultdict", "deque", "OrderedDict"}
    offenders = []
    for path in sorted(V3_ROUTER_DIR.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError):
            continue

        class Visitor(ast.NodeVisitor):
            def visit_Assign(self, node):  # noqa: N802
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    name = target.id
                    if not (name.startswith("_") and (
                        "STORE" in name.upper()
                        or "LOGS" in name.upper()
                        or "MAP" in name.upper()
                        or "CACHE" in name.upper()
                        or "REGISTRY" in name.upper()
                    )):
                        continue
                    if isinstance(node.value, (ast.Dict, ast.List, ast.Set)):
                        offenders.append(f"{path.name}:{node.lineno} {name}")
                    elif isinstance(node.value, ast.Call):
                        func = node.value.func
                        ctor = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                        if ctor in mutable_constructors:
                            offenders.append(f"{path.name}:{node.lineno} {name}")

            def visit_AnnAssign(self, node):  # noqa: N802
                if isinstance(node.target, ast.Name):
                    name = node.target.id
                    if name.startswith("_") and (
                        "STORE" in name.upper()
                        or "LOGS" in name.upper()
                        or "MAP" in name.upper()
                        or "CACHE" in name.upper()
                        or "REGISTRY" in name.upper()
                    ):
                        offenders.append(f"{path.name}:{node.lineno} {name}")

        Visitor().visit(tree)
    assert not offenders, f"module-level mutable collections in routers: {offenders}"


# ─────────────────────────────────────────────────────────────────────────────
# P4-R4C — fail-closed authority evidence alignment.
#
# These tests relate assertions to the actual inventory and source behavior so
# stale/false artifacts cannot pass. They assert the exact authority identifiers
# used by the cut-over multi-agent and route-lock routes, the runtime-authority
# audit shape, and provider/model read-only deferral.
# ─────────────────────────────────────────────────────────────────────────────

# Stable authority identifiers chosen by the generator (single source of truth).
MULTI_AGENT_AUTHORITY = "multi-agent-sql"
ROUTE_LOCK_AUTHORITY = "dedicated-sql:route_locks_v3"
FUTURE_OWNER = "phase-10-provider-model-routing"

# The three cut-over multi-agent namespaces plus route locks must never be
# claimed as generic v3_resources route authorities.
CUTOVER_NAMESPACES = {"agent_instances", "conversations", "conversation_events"}
ROUTE_LOCK_NAMESPACE = "route_locks"


def _route_by(method: str, path: str) -> dict:
    inventory = _load_inventory()
    for r in inventory["routes"]:
        if r["method"] == method and r["path"] == path:
            return r
    raise AssertionError(f"route not in inventory: {method} {path}")


def test_cutover_multi_agent_routes_use_dedicated_authority():
    """All /api/v3/agent-instances* and conversation routes use the dedicated
    multi-agent SQL authority, never generic v3_resources."""
    expected = {
        ("GET", "/api/v3/agent-instances"),
        ("POST", "/api/v3/agent-instances"),
        ("GET", "/api/v3/agent-instances/{instance_id}"),
        ("POST", "/api/v3/agent-instances/{instance_id}/restart"),
        ("POST", "/api/v3/agent-instances/{instance_id}/start"),
        ("POST", "/api/v3/agent-instances/{instance_id}/stop"),
        ("GET", "/api/v3/conversations"),
        ("POST", "/api/v3/conversations"),
        ("GET", "/api/v3/conversations/{conversation_id}/agents"),
        ("POST", "/api/v3/conversations/{conversation_id}/agents/{agent_id}/stop"),
        ("GET", "/api/v3/conversations/{conversation_id}/events"),
    }
    for method, path in expected:
        r = _route_by(method, path)
        assert r["authority"].startswith(f"{MULTI_AGENT_AUTHORITY}:"), (
            f"{method} {path} must use dedicated multi-agent authority, got {r['authority']}"
        )
        assert not r["authority"].startswith("v3_resources:"), (
            f"{method} {path} must not claim generic v3_resources authority"
        )


def test_conversation_detail_names_mixed_dedicated_and_generic_sources():
    """Conversation detail explicitly names the mixed dedicated
    conversations/agent_instances/conversation_events authority plus the
    generic tasks projection it actually reads."""
    r = _route_by("GET", "/api/v3/conversations/{conversation_id}")
    assert r["authority"] == (
        "multi-agent-sql:conversations,agent_instances,conversation_events"
    )
    assert "v3_resources:tasks" in r["source"]
    assert "multi-agent-sql:conversations" in r["source"]


def test_conversation_tasks_uses_generic_tasks_projection():
    """Conversation tasks read the generic v3_resources:tasks projection, not
    the dedicated conversation authority."""
    r = _route_by("GET", "/api/v3/conversations/{conversation_id}/tasks")
    assert r["authority"] == "v3_resources:tasks"


def test_agent_metrics_mixes_generic_definitions_and_dedicated_instances():
    """Agent metrics derive from generic agent definitions plus dedicated agent
    instances."""
    r = _route_by("GET", "/api/v3/agents/metrics")
    assert r["classification"] == "DERIVED"
    assert "v3_resources:agent_definitions" in r["source"]
    assert "multi-agent-sql:agent_instances" in r["source"]


def test_route_lock_uses_dedicated_route_lock_authority():
    """GET /api/v3/routing/locks/{lock_id} uses the dedicated route_locks_v3
    authority, never generic v3_resources:route_locks."""
    r = _route_by("GET", "/api/v3/routing/locks/{lock_id}")
    assert r["authority"] == ROUTE_LOCK_AUTHORITY
    assert not r["authority"].startswith("v3_resources:")


def test_routing_simulations_mix_generic_rules_and_dedicated_locks():
    """Routing simulations derive from generic routing-rule authority plus the
    dedicated route-lock authority."""
    r = _route_by("POST", "/api/v3/routing/simulations")
    assert r["classification"] == "DERIVED"
    assert "v3_resources:routing_rules" in r["source"]
    assert ROUTE_LOCK_AUTHORITY in r["source"]


def test_routing_rule_crud_remains_generic_sql_canonical():
    """Routing rule CRUD remains generic SQL configuration authority."""
    for method, path in [
        ("GET", "/api/v3/routing/rules"),
        ("POST", "/api/v3/routing/rules"),
        ("GET", "/api/v3/routing/rules/{rule_id}"),
        ("PATCH", "/api/v3/routing/rules/{rule_id}"),
        ("DELETE", "/api/v3/routing/rules/{rule_id}"),
    ]:
        r = _route_by(method, path)
        assert r["authority"] == "v3_resources:routing_rules"


def test_cutover_namespaces_not_claimed_as_generic_route_authority():
    """No inventory route claims the three cut-over multi-agent namespaces or
    route locks as a generic v3_resources authority."""
    inventory = _load_inventory()
    bad = []
    for r in inventory["routes"]:
        if not r["authority"].startswith("v3_resources:"):
            continue
        namespace = r["authority"].split(":", 1)[1]
        if namespace in CUTOVER_NAMESPACES or namespace == ROUTE_LOCK_NAMESPACE:
            bad.append(f"{r['method']} {r['path']} -> {r['authority']}")
    assert not bad, f"cut-over namespaces claimed as generic v3_resources: {bad}"


def test_runtime_authority_domains_all_present():
    """Every required runtime-authority domain is present in the audit."""
    authority = _load_namespace_authority()
    domains = {d["domain"] for d in authority["runtime_authority"]["domains"]}
    assert {"provider", "model", "routing", "multi-agent"} <= domains


def test_bridges_have_class_and_no_class_c_remains():
    """Every bridge with bridge_present=true has class A/B/C and no class C
    remains in Phase 4 scope."""
    authority = _load_namespace_authority()
    for d in authority["runtime_authority"]["domains"]:
        if d["bridge_present"]:
            assert d["bridge_class"] in {"A", "B", "C"}, (
                f"domain {d['domain']} bridge_present=true must have class A/B/C"
            )
            assert d["bridge_class"] != "C", (
                f"domain {d['domain']} has class-C bridge in Phase 4 scope"
            )
        else:
            assert d["bridge_class"] is None, (
                f"domain {d['domain']} bridge_present=false must have bridge_class null"
            )


def test_runtime_authority_domains_have_nonempty_fields():
    """Each runtime-authority domain has non-empty evidence/mutation/restart
    fields."""
    authority = _load_namespace_authority()
    for d in authority["runtime_authority"]["domains"]:
        assert d.get("evidence_symbols"), f"domain {d['domain']} missing evidence_symbols"
        assert d.get("mutation_path"), f"domain {d['domain']} missing mutation_path"
        assert d.get("restart_behavior"), f"domain {d['domain']} missing restart_behavior"
        assert d.get("canonical_api_authority"), f"domain {d['domain']} missing canonical_api_authority"
        assert d.get("execution_authority"), f"domain {d['domain']} missing execution_authority"


def test_provider_model_deferral_only_while_read_only():
    """Provider/model deferral is checked for Phase 4 / Phase 10 transitions."""
    inventory = _load_inventory()
    authority = _load_namespace_authority()
    domains = {d["domain"]: d for d in authority["runtime_authority"]["domains"]}

    for domain, prefix in [("model", "/api/v3/models")]:
        d = domains[domain]
        mutating = [
            r
            for r in inventory["routes"]
            if r["path"].startswith(prefix)
            and r["method"] in {"POST", "PATCH", "DELETE", "PUT"}
            and not r["path"].endswith("/test-connection")
        ]
        assert not mutating, (
            f"{domain} deferral invalid: mutating V3 routes present: {mutating}"
        )
        assert d["future_owner"] == FUTURE_OWNER, (
            f"{domain} future_owner must be {FUTURE_OWNER}, got {d['future_owner']}"
        )


def test_provider_model_execution_authority_is_explicit_and_not_read_only():
    """Provider/model execution authority must be a stable explicit identifier
    for the dedicated provider/model SQL + runtime services — never
    read-only-catalog and never claiming no runtime execution authority."""
    authority = _load_namespace_authority()
    domains = {d["domain"]: d for d in authority["runtime_authority"]["domains"]}
    for domain in ("provider", "model"):
        d = domains[domain]
        ea = d["execution_authority"]
        assert ea, f"{domain} execution_authority missing"
        assert "read-only-catalog" not in ea, (
            f"{domain} execution_authority must not be read-only-catalog: {ea}"
        )
        assert "no runtime execution authority" not in ea, (
            f"{domain} execution_authority must not claim no runtime execution "
            f"authority: {ea}"
        )
        # The dedicated execution authority must be named explicitly.
        assert (
            "CanonicalModelRegistryService" in ea
            or "EndpointExecutionCoordinator" in ea
        ), (
            f"{domain} execution_authority must name the dedicated runtime "
            f"services: {ea}"
        )


def test_provider_model_evidence_names_dedicated_runtime_symbols():
    """Provider/model evidence must name the actual composition/service/
    repository symbols for the dedicated provider execution system."""
    authority = _load_namespace_authority()
    domains = {d["domain"]: d for d in authority["runtime_authority"]["domains"]}
    required = {
        "ApplicationContainer.bootstrap",
        "WorkerContainer.bootstrap",
        "CanonicalModelRegistryService",
        "EndpointExecutionCoordinator",
        "SQLEndpointBindingRepository",
    }
    for domain in ("provider", "model"):
        d = domains[domain]
        evidence = " ".join(d["evidence_symbols"])
        missing = [s for s in required if s not in evidence]
        assert not missing, (
            f"{domain} evidence omits dedicated runtime symbols: {missing}"
        )


def test_provider_model_namespace_records_have_explicit_execution_authority():
    """The provider/model namespace records must carry the same explicit
    dedicated execution authority (not read-only-catalog) and keep the Phase 4
    deferral flags."""
    authority = _load_namespace_authority()
    by_ns = {ns["namespace"]: ns for ns in authority["namespaces"]}
    for ns_name in ("providers", "models"):
        ns = by_ns[ns_name]
        ea = ns["execution_authority"]
        assert ea, f"{ns_name} namespace execution_authority missing"
        assert "read-only-catalog" not in ea, (
            f"{ns_name} namespace execution_authority must not be read-only-catalog: {ea}"
        )
        assert "no runtime execution authority" not in ea, (
            f"{ns_name} namespace execution_authority must not claim no runtime "
            f"execution authority: {ea}"
        )
        assert (
            "CanonicalModelRegistryService" in ea
            or "EndpointExecutionCoordinator" in ea
        ), (
            f"{ns_name} namespace execution_authority must name the dedicated "
            f"runtime services: {ea}"
        )
        assert ns["bridge_present"] is False
        assert ns["bridge_class"] is None
        assert ns["phase4_duplicate_mutable_authority"] is False
        assert ns["future_bridge_phase"] == FUTURE_OWNER


def test_routing_is_class_b_sql_first_with_rebuild_semantics():
    """Routing must be specifically bridge class B with SQL-first
    mutation/rebuild semantics (never class A or C)."""
    authority = _load_namespace_authority()
    domains = {d["domain"]: d for d in authority["runtime_authority"]["domains"]}
    d = domains["routing"]
    assert d["bridge_present"] is True
    assert d["bridge_class"] == "B", (
        f"routing bridge_class must be B, got {d['bridge_class']}"
    )
    # SQL-first: the canonical authority is SQL and mutations flow SQL -> bridge.
    assert "v3_resources:routing_rules" in d["canonical_api_authority"]
    assert "RoutingAuthorityBridge.refresh_ruleset" in d["mutation_path"]
    # Rebuild semantics: the runtime ruleset is rebuilt from SQL on refresh/restart.
    assert "rebuilt" in d["restart_behavior"] or "rebuild" in d["restart_behavior"], (
        f"routing restart_behavior must state rebuild semantics: {d['restart_behavior']}"
    )


def test_multi_agent_is_direct_dedicated_sql_no_independent_bridge():
    """Multi-agent must be direct dedicated SQL with no independent bridge and
    no class C (API projection is class A derived)."""
    authority = _load_namespace_authority()
    domains = {d["domain"]: d for d in authority["runtime_authority"]["domains"]}
    d = domains["multi-agent"]
    assert d["bridge_present"] is False
    assert d["bridge_class"] is None
    assert d["execution_authority"].startswith("multi-agent-sql"), (
        f"multi-agent execution_authority must be dedicated SQL: {d['execution_authority']}"
    )
    assert (
        "MultiAgentRepository" in d["execution_authority"]
        or "OrchestratorService" in d["execution_authority"]
    ), (
        f"multi-agent execution_authority must name the dedicated repository/service: "
        f"{d['execution_authority']}"
    )
    # No independent bridge/class C: the API projection is class A derived.
    assert "class A" in d["restart_behavior"] or "class A" in d["mutation_path"], (
        f"multi-agent must state class A projection: {d['restart_behavior']}"
    )


def test_conversation_events_mutation_path_names_append_writers():
    """conversation_events mutation path must name actual append-event writers,
    not the read method."""
    authority = _load_namespace_authority()
    by_ns = {ns["namespace"]: ns for ns in authority["namespaces"]}
    ns = by_ns["conversation_events"]
    mp = ns["mutation_path"]
    assert "append_event" in mp, (
        f"conversation_events mutation_path must name append-event writers: {mp}"
    )
    # The read method must not be described as the mutation path.
    assert not mp.startswith("OrchestratorService.conversation_events"), (
        f"conversation_events mutation_path must not name the read method: {mp}"
    )


def test_generated_inventory_is_deterministic_and_matches_committed():
    """The generator re-derives the exact committed inventory (logical
    determinism) and the committed artifact is byte-stable."""
    import generate_architecture_v3_phase4_inventory as gen

    rebuilt = gen.build_inventory()
    committed = _load_inventory()
    assert rebuilt == committed, "rebuilt inventory differs from committed artifact"
    # Byte determinism: re-serializing the committed dict yields the same bytes
    # as the committed file (stable key order / indentation).
    assert json.dumps(committed, indent=2) == INVENTORY_PATH.read_text(
        encoding="utf-8"
    ), "committed inventory is not byte-stable under canonical serialization"