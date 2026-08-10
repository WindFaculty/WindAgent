"""Produce A4 durable-orchestration gate evidence (studio.contract/v0.1).

Runs the 0011 migration on a temp SQLite DB, executes a live Studio run
through the real durable queue (persisted DAG/task correlation dump), runs
the A4 orchestration/migration/boundary test suites and the live architecture
checker, then writes
``artifacts/studio_roadmap_01/a4/evidence.json`` and
``artifacts/studio_roadmap_01/a4/DURABLE_ORCHESTRATION_GATE_VERDICT.md``.

Usage: uv run python scripts/studio_roadmap/produce_a4_evidence.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "a4"
MIGRATION_FILE = (
    REPO_ROOT
    / "storage"
    / "windagent_storage"
    / "migrations"
    / "alembic"
    / "versions"
    / "0011_studio_run_nodes.py"
)

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from windagent_storage.migrations.runner import (  # noqa: E402
    alembic_current,
    alembic_heads,
    alembic_upgrade_head,
)


def _migration_probe() -> dict:
    migration_sha = hashlib.sha256(MIGRATION_FILE.read_bytes()).hexdigest()
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    db_path = Path(handle.name)
    db_url = f"sqlite:///{db_path.as_posix()}"
    try:
        alembic_upgrade_head(db_url)
        engine = create_engine(db_url)
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("studio_run_nodes")}
        engine.dispose()
        return {
            "file": "storage/windagent_storage/migrations/alembic/versions/0011_studio_run_nodes.py",
            "revision": "0011_studio_run_nodes",
            "down_revision": "0010_studio_persistence",
            "sha256": migration_sha,
            "heads": list(alembic_heads()),
            "current_after_upgrade": list(alembic_current(db_url)),
            "studio_run_nodes_columns": sorted(columns),
        }
    finally:
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass


async def _live_run_probe() -> dict:
    """Run a real Studio run through the durable queue; dump correlation."""
    from windagent_core.contracts.studio.commands import (
        CreateEpisodeCommand,
        CreateSeriesCommand,
        StartRunCommand,
    )
    from windagent_core.contracts.studio.models import StudioTaskResult, StudioTaskStatus
    from windagent_core.domain.studio.lifecycle import ApprovalCheckpoint
    from windagent_core.domain.studio.revision import StudioProductionRevision
    from windagent_orchestration.studio.dag import NODE_IDEA_GENERATE
    from windagent_orchestration.studio.service import StudioRunService
    from windagent_storage.database.connection import DatabaseManager
    from windagent_storage.orm.models import BaseORM
    from windagent_storage.studio.run_nodes import SqlStudioRunNodeRepository
    from windagent_storage.studio.task_submission import StudioTaskSubmissionAdapter

    import windagent_storage.orm.studio_models  # noqa: F401
    import windagent_storage.orm.v2_orchestration_models  # noqa: F401

    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    try:
        service = StudioRunService(
            db.session_factory, StudioTaskSubmissionAdapter(db.session_factory), retry_budget=2
        )
        series = await service.create_series(
            CreateSeriesCommand(idempotency_key="a4-ev-series", title="Evidence Series")
        )
        episode = await service.create_episode(
            CreateEpisodeCommand(
                idempotency_key="a4-ev-episode",
                series_id=series.series_id,
                title="Evidence Episode",
                episode_number=1,
            )
        )
        from windagent_core.contracts.studio.ids import ProductionRevisionId

        from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

        async with StudioUnitOfWork(db.session_factory) as uow:
            ep = await uow.episodes.get(episode.episode_id)
            revision = StudioProductionRevision(
                revision_id=ProductionRevisionId(f"rev_a4_evidence"),
                series_id=series.series_id,
                episode_id=episode.episode_id,
                creator="producer",
                actor="producer",
                content_hash="e" * 64,
            )
            await uow.revisions.save(revision)
            await uow.episodes.save(
                ep.model_copy(
                    update={
                        "current_revision_id": revision.revision_id,
                        "optimistic_version": ep.optimistic_version + 1,
                    }
                )
            )
            await uow.commit()

        started = await service.start_or_resume_run(
            StartRunCommand(idempotency_key="a4-ev-run", episode_id=episode.episode_id)
        )
        async with db.session_factory() as session:
            node = await SqlStudioRunNodeRepository(session).get(
                started.run_id, NODE_IDEA_GENERATE
            )
        task_id = node["task_id"]

        # complete the root task through the reconciler (the only advancing path)
        outcome = await service.reconcile(
            StudioTaskResult(
                task_id=task_id,
                studio_run_id=started.run_id,
                dag_node_id=NODE_IDEA_GENERATE,
                status=StudioTaskStatus.SUCCEEDED,
                output_hashes=["e" * 64],
            )
        )

        async with db.session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT n.dag_node_id, n.status, n.task_id, n.attempt, "
                        "t.state AS queue_state, t.facts_json "
                        "FROM studio_run_nodes n LEFT JOIN task_runs t ON t.id = n.task_id "
                        "WHERE n.run_id = :rid ORDER BY n.dag_node_id"
                    ),
                    {"rid": str(started.run_id)},
                )
            ).all()
            events = (
                await session.execute(
                    text(
                        "SELECT event_type, count(*) FROM studio_events "
                        "WHERE studio_run_id = :rid GROUP BY event_type ORDER BY event_type"
                    ),
                    {"rid": str(started.run_id)},
                )
            ).all()
        return {
            "run_id": str(started.run_id),
            "episode_id": str(episode.episode_id),
            "reconciled": outcome,
            "node_correlation": [
                {
                    "dag_node_id": r[0],
                    "node_status": r[1],
                    "task_id": r[2],
                    "attempt": r[3],
                    "queue_state": r[4],
                    "has_envelope": "studio_envelope" in (r[5] or ""),
                }
                for r in rows
            ],
            "events": [{"event_type": e[0], "count": e[1]} for e in events],
            "dispatched_with_committed_identity": all(
                (n["node_status"] != "DISPATCHED") or n["task_id"] for n in
                [{"node_status": r[1], "task_id": r[2]} for r in rows]
            ),
        }
    finally:
        await db.close()


def main() -> int:
    evidence: dict = {
        "phase": "A4",
        "gate": "DURABLE_ORCHESTRATION_GATE",
        "contract": "studio.contract/v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git": {
            "branch": subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=REPO_ROOT
            ).decode().strip()
        },
    }

    evidence["migration"] = _migration_probe()
    evidence["live_run"] = asyncio.run(_live_run_probe())

    test_targets = [
        "tests/unit/orchestration/test_studio_run_service.py",
        "tests/unit/storage/migrations/test_0011_studio_run_nodes_migration.py",
        "tests/architecture/test_studio_a4_orchestration_boundary.py",
    ]
    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", *test_targets, "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    evidence["orchestration_tests"] = {
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

    live = evidence["live_run"]
    correlation = live["node_correlation"]
    dispatched = next(
        (n for n in correlation if n["node_status"] == "DISPATCHED"), None
    )
    checks = {
        "fresh_upgrade_reaches_0011": evidence["migration"]["current_after_upgrade"]
        == ["0011_studio_run_nodes"],
        "dag_task_correlation_persisted": bool(dispatched) and dispatched["has_envelope"],
        "root_dispatched_with_committed_identity": (
            dispatched is not None and bool(dispatched["task_id"])
        ),
        "completion_advanced_only_through_reconciliation": (
            live["reconciled"]["duplicate"] is False
            and dispatched is not None
            and dispatched["dag_node_id"] == "idea.evaluate"
        ),
        "orchestration_test_suite_passes": test_result.returncode == 0,
        "architecture_checker_green": arch_result.returncode == 0,
    }
    evidence["checks"] = checks
    evidence["verdict"] = "PASS" if all(checks.values()) else "FAIL"

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8"
    )
    lines = [
        "# DURABLE_ORCHESTRATION_GATE — A4 verdict",
        "",
        f"- Contract: {evidence['contract']}",
        f"- Gate: {evidence['gate']}",
        f"- Verdict: **{evidence['verdict']}**",
        f"- Migration: {evidence['migration']['revision']} (sha256 {evidence['migration']['sha256'][:16]}...)",
        f"- Current head: {evidence['migration']['current_after_upgrade']}",
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
        "- OrchestratorService extension seam routes Studio runs through the sole Story authority.",
        "- Deterministic DAG builder over frozen task types/checkpoints; run + node state persist BEFORE submission.",
        "- StudioTaskSubmissionPort adapter wraps the durable queue (task_runs + outbox, atomic) with",
        "  namespaced idempotency keys; nodes are marked DISPATCHED only with the committed task identity.",
        "- StudioCompletionReconciler is the ONLY DAG-advancing path: stale/duplicate/out-of-order completions",
        "  are rejected or no-op'd; bounded retry re-dispatches with a fresh (run, node, attempt) key.",
        "- Approval waits are durable run state (WAITING_APPROVAL); APPROVED resumes through the orchestrator,",
        "  REJECTED fails the run. Cancellation is idempotent; terminal history is never rewritten.",
        "- Restart/resume: submitted-but-unmarked work is found by idempotency; dispatched-without-task nodes",
        "  are re-submitted on resume; terminal runs reject all later completions.",
        "",
        "Evidence JSON: `artifacts/studio_roadmap_01/a4/evidence.json`",
        f"Generated: {evidence['generated_at']}",
        "",
    ]
    (ARTIFACT_DIR / "DURABLE_ORCHESTRATION_GATE_VERDICT.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(f"verdict={evidence['verdict']} checks={json.dumps(checks)}")
    return 0 if evidence["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
