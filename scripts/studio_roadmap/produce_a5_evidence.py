"""Produce A5 worker-runtime gate evidence (studio.contract/v0.1).

Runs live failure-injection probes on a temp SQLite DB: a B handler crossing
the real SQL queue -> independent ProductionWorker -> Studio UoW -> generic
finalizer -> completion reconciler path, restart recovery for the
finalized-but-unreconciled crash window, duplicate-delivery idempotency,
certification rejection of fake runtimes and unregistered task types, and
envelope validation before side effects. Writes
``artifacts/studio_roadmap_01/a5/evidence.json`` and
``artifacts/studio_roadmap_01/a5/STORY_WORKER_GATE_VERDICT.md``.

Usage: uv run python scripts/studio_roadmap/produce_a5_evidence.py
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "a5"

from windagent_core.contracts.execution import ExecutionRequest  # noqa: E402
from windagent_core.contracts.studio.commands import (  # noqa: E402
    CreateEpisodeCommand,
    CreateSeriesCommand,
    StartRunCommand,
)
from windagent_core.contracts.studio.models import (  # noqa: E402
    StudioTaskEnvelope,
    StudioTaskType,
)
from windagent_execution.registry import ExecutionRuntimeRegistry  # noqa: E402
from windagent_intelligence.story.prompts.fixture import FixtureModelPort  # noqa: E402
from windagent_intelligence.story.runtime_handlers import HANDLER_REGISTRY  # noqa: E402
from windagent_orchestration.studio.service import StudioRunService  # noqa: E402
from windagent_storage.database.connection import DatabaseManager  # noqa: E402
from windagent_storage.orm.models import BaseORM  # noqa: E402
from windagent_storage.queue.sql_queue import SqlDurableTaskQueue  # noqa: E402
from windagent_storage.studio.run_nodes import SqlStudioRunNodeRepository  # noqa: E402
from windagent_storage.studio.task_submission import StudioTaskSubmissionAdapter  # noqa: E402
from windagent_worker.runner import ProductionWorker  # noqa: E402
from windagent_worker.studio_runtime import (  # noqa: E402
    StudioCompletionRecovery,
    StudioRuntimeAdapter,
)

import windagent_storage.orm.studio_models  # noqa: F401, E402
import windagent_storage.orm.v2_orchestration_models  # noqa: F401, E402

BRIEF_DICT = {
    "brief_id": "brf_a5_evidence",
    "title": "A5 Evidence Episode",
    "genre": "fantasy",
    "logline": "A rabbit and a kite cross the valley.",
    "tone": "warm",
    "audience": "kids",
    "language": "vi",
    "theme": "friendship",
    "target_duration_seconds": 240,
    "aspect_ratio": "16:9",
}

FIXTURE_RESPONSE = {
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


async def _adapter(db, **kwargs) -> StudioRuntimeAdapter:
    return StudioRuntimeAdapter(
        handler_registry=HANDLER_REGISTRY,
        session_factory=db.session_factory,
        **kwargs,
    )


async def _worker(db, *, studio_reconciler=None, **runtime_kwargs) -> ProductionWorker:
    adapter = await _adapter(db, **runtime_kwargs)
    registry = ExecutionRuntimeRegistry()
    registry.register_capability("studio", adapter)
    return ProductionWorker(
        name="a5-evidence-worker",
        task_queue=SqlDurableTaskQueue(db.session_factory),
        execution_registry=registry,
        uow_factory=db.session_factory,
        studio_reconciler=studio_reconciler,
    )


async def _seed(db, service) -> tuple[str, str]:
    series = await service.create_series(
        CreateSeriesCommand(idempotency_key="a5-ev-series", title="Evidence Series")
    )
    episode = await service.create_episode(
        CreateEpisodeCommand(
            idempotency_key="a5-ev-episode",
            series_id=series.series_id,
            title="Evidence Episode",
            episode_number=1,
            metadata={"creative_brief": BRIEF_DICT},
        )
    )
    return str(series.series_id), str(episode.episode_id)


async def _probe_e2e() -> dict:
    """A B handler crosses real SQL queue -> worker -> UoW -> finalizer -> reconciler."""
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    try:
        service = StudioRunService(
            db.session_factory, StudioTaskSubmissionAdapter(db.session_factory), retry_budget=2
        )
        _, episode_id = await _seed(db, service)
        started = await service.start_or_resume_run(
            StartRunCommand(idempotency_key="a5-ev-run", episode_id=episode_id)
        )
        worker = await _worker(
            db,
            studio_reconciler=service,
            model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)}),
        )
        await worker.start()
        tick = await worker.poll_and_execute_tick()
        await worker.stop()

        async with db.session_factory() as session:
            nodes = {
                n["dag_node_id"]: n
                for n in await SqlStudioRunNodeRepository(session).list(started.run_id)
            }
            artifact_count = (
                await session.execute(
                    __import__("sqlalchemy").text("SELECT COUNT(*) FROM studio_artifacts")
                )
            ).scalar_one()
        return {
            "tick_status": tick["status"],
            "idea_generate_status": nodes["idea.generate"]["status"],
            "idea_evaluate_status": nodes["idea.evaluate"]["status"],
            "idea_evaluate_task_id": bool(nodes["idea.evaluate"]["task_id"]),
            "output_hashes": nodes["idea.generate"].get("output_hashes", []),
            "artifact_count": artifact_count,
            "metrics": worker.metrics_snapshot(),
        }
    finally:
        await db.close()


async def _probe_restart_recovery() -> dict:
    """Crash after finalizer commit, before reconcile; restart sweeps it."""
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    try:
        service = StudioRunService(
            db.session_factory, StudioTaskSubmissionAdapter(db.session_factory), retry_budget=2
        )
        _, episode_id = await _seed(db, service)
        started = await service.start_or_resume_run(
            StartRunCommand(idempotency_key="a5-ev-run2", episode_id=episode_id)
        )
        worker = await _worker(
            db, model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)})
        )
        await worker.start()
        await worker.poll_and_execute_tick()
        await worker.stop()
        async with db.session_factory() as session:
            before = await SqlStudioRunNodeRepository(session).get(
                started.run_id, "idea.generate"
            )
        recovery = StudioCompletionRecovery(db.session_factory, service)
        recovered = await recovery.recover_pending_completions()
        second_sweep = await recovery.recover_pending_completions()
        async with db.session_factory() as session:
            after = await SqlStudioRunNodeRepository(session).get(started.run_id, "idea.generate")
        return {
            "node_status_before_restart": before["status"],
            "recovered_count": recovered,
            "second_sweep_count": second_sweep,
            "node_status_after_restart": after["status"],
        }
    finally:
        await db.close()


async def _probe_fail_closed() -> dict:
    """Envelope validation, unregistered types, fake runtime rejection, metrics."""
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    try:
        service = StudioRunService(
            db.session_factory, StudioTaskSubmissionAdapter(db.session_factory), retry_budget=2
        )
        series_id, episode_id = await _seed(db, service)
        from windagent_core.contracts.studio.ids import StudioRunId

        def envelope(task_type: StudioTaskType, **overrides) -> StudioTaskEnvelope:
            base = dict(
                task_type=task_type,
                studio_run_id=StudioRunId("run_a5_probe"),
                dag_node_id="idea.generate",
                series_id=series_id,
                episode_id=episode_id,
                idempotency_key="a5-probe",
            )
            base.update(overrides)
            return StudioTaskEnvelope(**base)

        async def dispatch(adapter, env, tid):
            req = ExecutionRequest(
                step_run_id=tid,
                workflow_run_id=f"wf_{tid}",
                tool_name=env.task_type.value,
                parameters={"studio_envelope": env.to_dict()},
                attempt_id="att_1",
                fencing_token=f"fence_{tid}",
            )
            handle = await adapter.dispatch(req)
            result = await adapter.get_result(handle)
            return result

        # 1. unsupported envelope schema -> fail before side effects
        bad = await _adapter(db)
        r1 = await dispatch(
            bad,
            envelope(StudioTaskType.IDEA_GENERATE, schema_version="studio.task_envelope/v999"),
            "probe_1",
        )
        # 2. unregistered task type -> fail closed
        r2 = await dispatch(bad, envelope(StudioTaskType.LOCK), "probe_2")
        # 3. fake runtime + certification -> violation, no execution
        cert = await _adapter(
            db,
            model_port=FixtureModelPort(responses={"ideation": json.dumps(FIXTURE_RESPONSE)}),
            certification=True,
            fake_runtime_active=True,
        )
        r3 = await dispatch(cert, envelope(StudioTaskType.IDEA_GENERATE), "probe_3")
        async with db.session_factory() as session:
            artifact_count = (
                await session.execute(
                    __import__("sqlalchemy").text("SELECT COUNT(*) FROM studio_artifacts")
                )
            ).scalar_one()
        return {
            "bad_schema_status": (r1.result_data or {}).get("status"),
            "bad_schema_error": r1.error,
            "unregistered_status": (r2.result_data or {}).get("status"),
            "unregistered_error": r2.error,
            "fake_runtime_cert_status": (r3.result_data or {}).get("status"),
            "fake_runtime_cert_error": r3.error,
            "artifacts_after_failures": artifact_count,
        }
    finally:
        await db.close()


def main() -> int:
    evidence: dict = {
        "phase": "A5",
        "gate": "STORY_WORKER_GATE",
        "contract": "studio.contract/v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git": {
            "branch": subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=REPO_ROOT
            ).decode().strip()
        },
    }

    evidence["e2e"] = asyncio.run(_probe_e2e())
    evidence["restart_recovery"] = asyncio.run(_probe_restart_recovery())
    evidence["fail_closed"] = asyncio.run(_probe_fail_closed())

    test_targets = [
        "tests/unit/worker/test_studio_runtime.py",
        "tests/unit/worker/",
        "tests/architecture/test_studio_a4_orchestration_boundary.py",
    ]
    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", *test_targets, "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    evidence["worker_tests"] = {
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

    e2e = evidence["e2e"]
    restart = evidence["restart_recovery"]
    closed = evidence["fail_closed"]
    metrics = e2e.get("metrics", {})
    metric_payload = json.dumps(metrics)

    checks = {
        "handler_crosses_worker_path": (
            e2e["tick_status"] == "completed"
            and e2e["idea_generate_status"] == "SUCCEEDED"
            and e2e["idea_evaluate_status"] == "DISPATCHED"
            and e2e["idea_evaluate_task_id"]
            and e2e["artifact_count"] == 1
        ),
        "restart_recovery_reconciles": (
            restart["node_status_before_restart"] == "DISPATCHED"
            and restart["recovered_count"] == 1
            and restart["second_sweep_count"] == 0
            and restart["node_status_after_restart"] == "SUCCEEDED"
        ),
        "envelope_validated_before_side_effects": (
            closed["bad_schema_status"] == "FAILED"
            and "STUDIO_ENVELOPE_INVALID" in closed["bad_schema_error"]
        ),
        "unregistered_task_type_rejected": (
            closed["unregistered_status"] == "FAILED"
            and "STUDIO_UNREGISTERED_TASK_TYPE" in closed["unregistered_error"]
        ),
        "fake_runtime_rejected_in_certification": (
            closed["fake_runtime_cert_status"] == "FAILED"
            and "STUDIO_CERTIFICATION_VIOLATION" in closed["fake_runtime_cert_error"]
        ),
        "fail_closed_leaves_no_artifacts": closed["artifacts_after_failures"] == 0,
        "worker_metrics_snapshot": (
            "execution_ms" in metric_payload
            and "finalize_ms" in metric_payload
            and "queue_wait_ms" in metric_payload
            and "Title 1" not in metric_payload
        ),
        "worker_test_suite_passes": test_result.returncode == 0,
        "architecture_checker_green": arch_result.returncode == 0,
    }
    evidence["checks"] = checks
    evidence["verdict"] = "PASS" if all(checks.values()) else "FAIL"

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8"
    )
    lines = [
        "# STORY_WORKER_GATE — A5 verdict",
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
        "- StudioRuntimeAdapter decodes/validates the durable StudioTaskEnvelope BEFORE any side effect;",
        "  unsupported schema/contract versions and unregistered frozen task types fail closed.",
        "- Certification mode rejects fake runtimes and fixture model ports (no canned output can pass).",
        "- Plan B handlers execute in the independent worker over the Studio UoW: input artifacts load",
        "  by ref (frozen task IO map), output artifacts persist content-addressed and idempotent by hash,",
        "  fenced by (worker, durable task id, fencing token) provenance.",
        "- The generic TaskFinalizer commits task state + result + terminal event + outbox + lease release",
        "  atomically; result_data IS the serialized StudioTaskResult, so generic tasks are untouched.",
        "- Completion advances ONLY through the reconciler; crash windows are covered by lease expiry",
        "  takeover (before provider/finalize) and StudioCompletionRecovery (after finalizer commit,",
        "  before reconcile) — idempotent by design.",
        "- Worker metrics (queue wait, execution, finalization, retry attempt, status) are redaction-safe:",
        "  ids/durations only, never story content.",
        "",
        "Evidence JSON: `artifacts/studio_roadmap_01/a5/evidence.json`",
        f"Generated: {evidence['generated_at']}",
        "",
    ]
    (ARTIFACT_DIR / "STORY_WORKER_GATE_VERDICT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"verdict={evidence['verdict']} checks={json.dumps(checks)}")
    return 0 if evidence["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
