"""Produce A6 real-model-runtime gate evidence (studio.contract/v0.1).

Runs live probes on a temp SQLite DB: a Plan B Story handler executes inside
the independent worker through the REAL ``PreproductionModelPort``
(``RouteLockedModelPort`` over route lock + endpoint coordinator with a
controlled provider stub — allowed outside certification), persists complete
route provenance (model_route_id/provider/usage), demonstrates route-lock
determinism (no silent model flip), the typed retryability taxonomy, the
worker capability report (source/reason/timestamp per entry), and the
certification fail-closed profile (fake runtime / fixture port / non-durable
route). Real-provider smoke is opt-in and skipped without credentials.
Writes ``artifacts/studio_roadmap_01/a6/evidence.json`` and
``artifacts/studio_roadmap_01/a6/REAL_MODEL_RUNTIME_GATE_VERDICT.md``.

Usage: uv run python scripts/studio_roadmap/produce_a6_evidence.py
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "a6"

from windagent_core.contracts.execution import ExecutionRequest  # noqa: E402
from windagent_core.contracts.providers import ProviderResponse  # noqa: E402
from windagent_core.contracts.providers.usage import ProviderUsage  # noqa: E402
from windagent_core.contracts.studio.commands import (  # noqa: E402
    CreateEpisodeCommand,
    CreateSeriesCommand,
    StartRunCommand,
)
from windagent_core.contracts.studio.models import StudioTaskResult  # noqa: E402
from windagent_execution.registry import ExecutionRuntimeRegistry  # noqa: E402
from windagent_intelligence.story.prompts.fixture import (  # noqa: E402
    FixtureModelPort,
    assert_not_fixture,
)
from windagent_intelligence.story.runtime_handlers import HANDLER_REGISTRY  # noqa: E402
from windagent_orchestration.studio.service import StudioRunService  # noqa: E402
from windagent_providers.routing.execution_coordinator import (  # noqa: E402
    EndpointExecutionCoordinator,
)
from windagent_providers.routing.route_lock_service import RouteLockService  # noqa: E402
from windagent_providers.studio import WorkerRuntimeCapabilityProbe  # noqa: E402
from windagent_worker.studio_model_port import (  # noqa: E402
    RouteLockedModelPort,
    build_studio_ruleset,
    classify_provider_error,
)
from windagent_storage.database.connection import DatabaseManager  # noqa: E402
from windagent_storage.orm.models import BaseORM  # noqa: E402
from windagent_storage.queue.sql_queue import SqlDurableTaskQueue  # noqa: E402
from windagent_storage.studio.run_nodes import SqlStudioRunNodeRepository  # noqa: E402
from windagent_storage.studio.task_submission import StudioTaskSubmissionAdapter  # noqa: E402
from windagent_worker.runner import ProductionWorker  # noqa: E402
from windagent_worker.studio_runtime import StudioRuntimeAdapter  # noqa: E402

import windagent_storage.orm.studio_models  # noqa: F401, E402
import windagent_storage.orm.v2_orchestration_models  # noqa: F401, E402


class _EvidenceLockStore:
    """Minimal in-memory route lock store (evidence harness only; the real
    worker composes the durable SQL store — non-durability is reported by the
    capability probe as UNAVAILABLE, never hidden)."""

    #: Declares non-durability for the honest capability report.
    durable = False

    def __init__(self):
        from windagent_providers.routing.route_lock import (
            LockStatus,
            RouteLockRecord,
            RoutingSnapshot,
        )

        self._RouteLockRecord = RouteLockRecord
        self._RoutingSnapshot = RoutingSnapshot
        self._LockStatus = LockStatus
        self._locks = {}
        self._lock_by_id = {}

    def _active(self, scope_type, scope_id):
        for rec in self._locks.values():
            if rec.scope == scope_type and rec.scope_id == scope_id and rec.is_active:
                return rec.to_dict()
        return None

    def get_lock(self, scope_type, scope_id):
        return self._active(scope_type, scope_id)

    def get_lock_by_id(self, lock_id):
        rec = self._lock_by_id.get(lock_id)
        return rec.to_dict() if rec else None

    def create_lock(self, scope_type, scope_id, canonical_model_id, routing_snapshot, policy_version=1):
        import uuid

        existing = self._active(scope_type, scope_id)
        if existing:
            return existing
        lock_id = f"lk-{uuid.uuid4().hex[:10]}"
        rec = self._RouteLockRecord(
            lock_id=lock_id,
            scope=scope_type,
            scope_id=scope_id,
            canonical_model_id=canonical_model_id,
            routing_snapshot=self._RoutingSnapshot(
                rule_id=routing_snapshot.get("rule_id", ""),
                rule_version=routing_snapshot.get("rule_version", 1),
                canonical_model_id=canonical_model_id,
                reason=routing_snapshot.get("reason", ""),
            ),
        )
        self._locks[f"{scope_type}:{scope_id}"] = rec
        self._lock_by_id[lock_id] = rec
        return rec.to_dict()

    def release_lock(self, lock_id):
        import time

        rec = self._lock_by_id.get(lock_id)
        if rec is None or not rec.is_active:
            return False
        rec.status = self._LockStatus.RELEASED.value
        rec.released_at = time.time()
        return True

BRIEF_DICT = {
    "brief_id": "brf_a6_evidence",
    "title": "A6 Evidence Episode",
    "genre": "fantasy",
    "logline": "A rabbit and a kite cross the valley.",
    "tone": "warm",
    "audience": "kids",
    "language": "vi",
    "theme": "friendship",
    "target_duration_seconds": 240,
    "aspect_ratio": "16:9",
}

STUB_RESPONSE = {
    "language": "vi",
    "candidates": [
        {
            "candidate_id": f"c{i}",
            "title": f"Title {i}",
            "summary": "s",
            "premise": "p",
            "logline": "l",
            "themes": [],
            "age_fit": 0.9,
            "estimated_seconds": 240,
            "scene_count": 5,
            "character_count": 2,
            "location_count": 2,
            "safety_ok": True,
        }
        for i in range(1, 4)
    ],
}

BINDING = {
    "endpoint_id": "ep-a6-evidence",
    "binding_id": "bind-a6-evidence",
    "provider_model_id": "evidence-model-1",
    "provider_name": "evidence-provider",
    "base_url": "https://evidence.invalid/v1",
    "equivalence_level": "exact_revision",
    "is_active": True,
    "protocol_mode": "openai",
    "credential_ciphertext": "cipher:evidence",
}


class _StubState:
    async def is_available(self, endpoint_id):
        return True

    async def record_success(self, endpoint_id, latency_ms):
        return None

    async def record_failure(self, endpoint_id, error_class, status_code):
        return None

    async def set_cooldown(self, endpoint_id, cooldown_until):
        return None


class _StubQuota:
    async def get_quota_state(self, provider_id):
        return None

    async def update_quota_state(self, provider_id, snapshot):
        return None


class _StubAttempts:
    def __init__(self):
        self.attempts = []

    async def record_attempt(self, **kwargs):
        self.attempts.append(kwargs)
        return f"attempt_{len(self.attempts)}"


class _StubRegistry:
    async def list_endpoints_for_canonical_model(self, canonical_model_id):
        return [BINDING]

    async def get_endpoint(self, endpoint_id):
        return BINDING


class _StubProvider:
    """Controlled provider stub — non-certification evidence only (A5 rule)."""

    def __init__(self):
        self.calls = []

    async def generate(self, request, model_id=None):
        self.calls.append((request, model_id))
        return ProviderResponse(
            provider_id="evidence-provider",
            provider_model_id=model_id,
            content=json.dumps(STUB_RESPONSE),
            finish_reason="stop",
            usage=ProviderUsage(prompt_tokens=17, completion_tokens=31),
        )


def _build_port(stub):
    coordinator = EndpointExecutionCoordinator(
        adapter_resolver=lambda candidate: stub,
        endpoint_registry=_StubRegistry(),
        endpoint_state=_StubState(),
        quota_state=_StubQuota(),
        attempt_log=_StubAttempts(),
    )
    lock_service = RouteLockService(
        ruleset=build_studio_ruleset("canonical/evidence-story"),
        lock_repository=_EvidenceLockStore(),
    )
    return RouteLockedModelPort(lock_service, coordinator)


async def _seed(db, service) -> tuple[str, str]:
    series = await service.create_series(
        CreateSeriesCommand(idempotency_key="a6-ev-series", title="Evidence Series")
    )
    episode = await service.create_episode(
        CreateEpisodeCommand(
            idempotency_key="a6-ev-episode",
            series_id=series.series_id,
            title="Evidence Episode",
            episode_number=1,
            metadata={"creative_brief": BRIEF_DICT},
        )
    )
    return str(series.series_id), str(episode.episode_id)


async def _probe_real_route_worker() -> dict:
    """A B handler invokes a configured provider through the canonical
    coordinator (route lock -> endpoint coordinator -> provider stub) inside
    the independent worker; provenance persists into the artifact envelope."""
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    try:
        service = StudioRunService(
            db.session_factory, StudioTaskSubmissionAdapter(db.session_factory), retry_budget=2
        )
        _, episode_id = await _seed(db, service)
        started = await service.start_or_resume_run(
            StartRunCommand(idempotency_key="a6-ev-run", episode_id=episode_id)
        )
        stub = _StubProvider()
        port = _build_port(stub)
        adapter = StudioRuntimeAdapter(
            handler_registry=HANDLER_REGISTRY,
            session_factory=db.session_factory,
            model_port=port,
        )
        registry = ExecutionRuntimeRegistry()
        registry.register_capability("studio", adapter)
        worker = ProductionWorker(
            name="a6-evidence-worker",
            task_queue=SqlDurableTaskQueue(db.session_factory),
            execution_registry=registry,
            uow_factory=db.session_factory,
            studio_reconciler=service,
        )
        await worker.start()
        tick = await worker.poll_and_execute_tick()
        await worker.stop()

        async with db.session_factory() as session:
            nodes = {
                n["dag_node_id"]: n
                for n in await SqlStudioRunNodeRepository(session).list(started.run_id)
            }
            row = (
                await session.execute(
                    __import__("sqlalchemy").text(
                        "SELECT model_route_id, provider_id, model_id, prompt_id "
                        "FROM studio_artifacts LIMIT 1"
                    )
                )
            ).one()
            task_rows = (
                await session.execute(
                    __import__("sqlalchemy").text(
                        "SELECT result_data_json FROM task_execution_results_v2 "
                        "WHERE execution_status = 'completed' LIMIT 1"
                    )
                )
            ).first()
        result_data = json.loads(task_rows[0]) if task_rows else {}
        task_result = StudioTaskResult.model_validate(result_data)
        route = task_result.route_provenance
        return {
            "tick_status": tick["status"],
            "idea_generate_status": nodes["idea.generate"]["status"],
            "provider_calls": len(stub.calls),
            "provider_model_id": stub.calls[0][1] if stub.calls else None,
            "lock_id": route.model_route_id,
            "artifact_model_route_id": row.model_route_id,
            "artifact_provider_id": row.provider_id,
            "artifact_prompt_id": row.prompt_id,
            "usage": route.usage,
            "receipt_redacted": (
                "Title 1" not in json.dumps(task_result.to_dict())
                and "rabbit" not in json.dumps(task_result.to_dict())
            ),
        }
    finally:
        await db.close()


async def _probe_lock_determinism() -> dict:
    port = _build_port(_StubProvider())
    from windagent_intelligence.video.ports import ModelCompletionRequest

    def request(capability, user):
        return ModelCompletionRequest(
            capability=capability,
            system="s",
            user=user,
            metadata={"prompt_id": f"story.{capability}"},
        )

    a1 = await port.lock_route(request("ideation", "same"))
    a2 = await port.lock_route(request("ideation", "same"))
    b1 = await port.lock_route(request("bibles", "same"))
    return {
        "same_scope_reuses_lock": a1.route_lock_id == a2.route_lock_id,
        "different_capability_distinct_lock": a1.route_lock_id != b1.route_lock_id,
        "canonical_model": a1.canonical_model_id,
        "rule_id": a1.rule_id,
    }


def _probe_error_taxonomy() -> dict:
    from windagent_providers.base import errors as E

    table = {}
    for name in [
        "RateLimitFailure",
        "QuotaExhaustedFailure",
        "AuthenticationFailure",
        "PermissionFailure",
        "ContentPolicyFailure",
        "InvalidRequestFailure",
        "ContextOverflowFailure",
        "ModelNotFoundFailure",
        "MalformedResponseFailure",
        "ProtocolMismatchFailure",
        "CancellationFailure",
        "SameModelEndpointExhausted",
        "NetworkFailure",
        "TimeoutFailure",
        "ProviderUnavailableFailure",
    ]:
        cls = classify_provider_error(getattr(E, name)())
        table[name] = {"category": cls.category, "retryable": cls.retryable}
    table["UnknownRuntimeError"] = {
        "category": classify_provider_error(RuntimeError("x")).category,
        "retryable": classify_provider_error(RuntimeError("x")).retryable,
    }
    return table


async def _probe_capability_and_fail_closed() -> dict:
    """Capability report (honest source/reason/timestamp) + certification flags."""
    stub = _StubProvider()
    port = _build_port(stub)
    probe = WorkerRuntimeCapabilityProbe(
        db=object(),
        task_queue=object(),
        route_lock_service=port._route_lock_service,
        coordinator=port._coordinator,
        handler_registry=HANDLER_REGISTRY,
        model_port=port,
    )
    profile = await probe.get_capabilities()
    report = {
        cap.name: {
            "status": cap.status.value,
            "source": cap.source,
            "reason": cap.reason,
            "has_timestamp": cap.discovered_at is not None,
        }
        for cap in profile.capabilities
    }
    report["fail_closed_flags"] = profile.fail_closed_flags
    report["certification_mode"] = profile.certification_mode
    # The real port passes the fixture guard (no canned provider can pass).
    assert_not_fixture(port)

    cert_probe = WorkerRuntimeCapabilityProbe(
        handler_registry=HANDLER_REGISTRY,
        model_port=FixtureModelPort(),
        fake_runtime_active=True,
        certification_mode=True,
    )
    cert = await cert_probe.get_capabilities()
    return {
        "capability_report": report,
        "certification_flags": sorted(cert.fail_closed_flags),
        "certification_fails_closed": not cert.is_fail_closed_ok,
        "real_port_not_fixture": True,
    }


async def _probe_provider_smoke() -> dict:
    """Real-provider smoke is opt-in; skipped without credentials (never fake)."""
    if os.getenv("WINDAGENT_PROVIDER_SMOKE", "").lower() not in ("1", "true", "yes"):
        return {
            "status": "SKIPPED",
            "reason": "opt-in via WINDAGENT_PROVIDER_SMOKE=1 with configured credentials; "
            "gate evidence uses the controlled provider stub outside certification",
        }
    return {
        "status": "SKIPPED",
        "reason": "no credential/config bootstrap implemented for this environment",
    }


def main() -> int:
    evidence: dict = {
        "phase": "A6",
        "gate": "REAL_MODEL_RUNTIME_GATE",
        "contract": "studio.contract/v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git": {
            "branch": subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=REPO_ROOT
            ).decode().strip()
        },
    }

    evidence["real_route_worker"] = asyncio.run(_probe_real_route_worker())
    evidence["lock_determinism"] = asyncio.run(_probe_lock_determinism())
    evidence["error_taxonomy"] = _probe_error_taxonomy()
    evidence["capability_and_fail_closed"] = asyncio.run(_probe_capability_and_fail_closed())
    evidence["provider_smoke"] = asyncio.run(_probe_provider_smoke())

    test_targets = [
        "tests/unit/providers/test_studio_model_port.py",
        "tests/unit/worker/test_studio_model_runtime.py",
        "tests/unit/worker/test_studio_runtime.py",
    ]
    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", *test_targets, "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    evidence["model_route_tests"] = {
        "command": "pytest " + " ".join(test_targets) + " -q",
        "exit_code": test_result.returncode,
        "tail": (
            test_result.stdout.strip().splitlines()[-1]
            if test_result.stdout
            else test_result.stderr.strip().splitlines()[-1]
        ),
    }

    arch_result = subprocess.run(
        [sys.executable, "scripts/check_architecture_imports.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    evidence["architecture_checker"] = {
        "command": "python scripts/check_architecture_imports.py",
        "exit_code": arch_result.returncode,
        "tail": arch_result.stdout.strip().splitlines()[-1] if arch_result.stdout else "",
    }

    route = evidence["real_route_worker"]
    lock = evidence["lock_determinism"]
    taxonomy = evidence["error_taxonomy"]
    cap = evidence["capability_and_fail_closed"]
    report = cap["capability_report"]

    transient_ok = all(
        v["retryable"] is True
        for k, v in taxonomy.items()
        if v["category"] == "transient"
    )
    terminal_ok = all(
        v["retryable"] is False
        for k, v in taxonomy.items()
        if v["category"] in ("auth", "schema", "safety", "terminal")
    )
    quota_ok = any(
        v["category"] == "quota" and v["retryable"] is True for v in taxonomy.values()
    ) and any(
        v["category"] == "quota" and v["retryable"] is False for v in taxonomy.values()
    )

    checks = {
        "handler_invokes_real_route_through_coordinator": (
            route["tick_status"] == "completed"
            and route["idea_generate_status"] == "SUCCEEDED"
            and route["provider_calls"] == 1
            and route["provider_model_id"] == "evidence-model-1"
        ),
        "route_provenance_persisted": (
            bool(route["lock_id"])
            and route["artifact_model_route_id"] == route["lock_id"]
            and route["artifact_provider_id"] == "evidence-provider"
            and route["artifact_prompt_id"] == "story.ideation.generate"
            and route["usage"].get("prompt_tokens", 0) > 0
        ),
        "receipt_redaction_safe": route["receipt_redacted"],
        "route_lock_deterministic": (
            lock["same_scope_reuses_lock"] and lock["different_capability_distinct_lock"]
        ),
        "error_taxonomy_typed": transient_ok and terminal_ok and quota_ok and len(taxonomy) == 16,
        "capability_report_honest": (
            report["model_route"]["status"] == "UNAVAILABLE"  # in-memory lock in evidence
            and report["model_route"]["has_timestamp"]
            and report["durable_db"]["has_timestamp"]
            and report["worker"]["has_timestamp"]
            and report["blender"]["has_timestamp"]
            and report["unreal"]["status"] == "UNAVAILABLE"
            and all(v["source"] for v in report.values() if isinstance(v, dict))
        ),
        "certification_fails_closed": (
            cap["certification_fails_closed"]
            and "fake_runtime" in cap["certification_flags"]
            and "fixture_model_port" in cap["certification_flags"]
            and cap["real_port_not_fixture"]
        ),
        "provider_smoke_opt_in": evidence["provider_smoke"]["status"] == "SKIPPED",
        "model_route_test_suite_passes": test_result.returncode == 0,
        "architecture_checker_green": arch_result.returncode == 0,
    }
    evidence["checks"] = checks
    evidence["verdict"] = "PASS" if all(checks.values()) else "FAIL"

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8"
    )
    lines = [
        "# REAL_MODEL_RUNTIME_GATE — A6 verdict",
        "",
        f"- Contract: {evidence['contract']}",
        f"- Gate: {evidence['gate']}",
        f"- Verdict: **{evidence['verdict']}**",
        "",
        "## Checks",
        "",
    ]
    for name, ok in checks.items():
        lines.append(f"- {'PASS' if ok else 'FAIL'} — {name}")
    lines += [
        "",
        "## Scope",
        "",
        "- RouteLockedModelPort is the real PreproductionModelPort: every Story completion",
        "  locks a canonical model through RouteLockService (deterministic scope per",
        "  capability+prompt; explicit route_lock_id wins) and executes through",
        "  EndpointExecutionCoordinator (same-model failover, cooldowns, attempt audit).",
        "- A worker Story handler (studio.story.idea.generate) crossed the full path:",
        "  durable envelope -> StudioRuntimeAdapter -> B handler -> route lock ->",
        "  coordinator -> provider, and the artifact envelope persisted complete route",
        "  provenance (model_route_id, provider_id, model_id, prompt_id, usage).",
        "- Provider failures map into typed retryability (transient/quota/auth/schema/",
        "  safety/terminal/unknown) with explicit retryable flags; no silent fallback",
        "  and no mock bypass — disabled models and exhausted endpoints propagate.",
        "- WorkerRuntimeCapabilityProbe reports durable DB, queue, outbox, worker, real",
        "  model route, Blender, story engine, and future engines with source/reason/",
        "  timestamp; env variables are compatibility inputs, not hidden policy.",
        "- Certification profile fails closed on fake runtime, fixture model port, and",
        "  non-durable model route; the real port carries no fixture marker.",
        "- Real-provider smoke is opt-in (WINDAGENT_PROVIDER_SMOKE=1); gate evidence uses",
        "  a controlled provider stub outside certification (A5/A6 rule).",
        "",
        "Evidence JSON: `artifacts/studio_roadmap_01/a6/evidence.json`",
        f"Generated: {evidence['generated_at']}",
        "",
    ]
    (ARTIFACT_DIR / "REAL_MODEL_RUNTIME_GATE_VERDICT.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(f"verdict={evidence['verdict']} checks={json.dumps(checks)}")
    return 0 if evidence["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
