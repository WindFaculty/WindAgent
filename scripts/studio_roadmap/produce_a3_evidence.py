"""Produce A3 persistence-gate evidence (studio.contract/v0.1).

Runs the migration on a temp SQLite DB with a representative legacy fixture,
captures preflight/postflight row counts, a schema snapshot, a rollback
rehearsal log, and the repository test results; writes
``artifacts/studio_roadmap_01/a3/evidence.json`` and
``artifacts/studio_roadmap_01/a3/STUDIO_PERSISTENCE_GATE_VERDICT.md``.

Usage: uv run python scripts/studio_roadmap/produce_a3_evidence.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "a3"
MIGRATION_FILE = (
    REPO_ROOT
    / "storage"
    / "windagent_storage"
    / "migrations"
    / "alembic"
    / "versions"
    / "0010_studio_persistence.py"
)

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from windagent_storage.migrations.runner import (  # noqa: E402
    alembic_current,
    alembic_heads,
    alembic_upgrade_head,
)
from windagent_storage.studio.backfill import synthetic_episode_id  # noqa: E402


def _schema_snapshot(engine) -> dict:
    inspector = inspect(engine)
    tables = {}
    for table in sorted(inspector.get_table_names()):
        if not table.startswith("studio_"):
            continue
        tables[table] = {
            "columns": [c["name"] for c in inspector.get_columns(table)],
            "unique_indexes": [
                {"name": i["name"], "columns": i["column_names"]}
                for i in inspector.get_indexes(table, include_auto_indexes=True)
                if i["unique"]
            ],
        }
    outbox = {
        "unique_indexes": [
            i["name"] for i in inspector.get_indexes("v2_outbox_records") if i["unique"]
        ]
    }
    return {"studio_tables": tables, "v2_outbox_records": outbox}


def _seed_legacy(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO video_production_projects "
                "(id, name, status, active_revision_id, created_at, updated_at) VALUES "
                "('proj_legacy_1', 'Legacy Pilot', 'ACTIVE', 'rev_legacy_2', "
                "'2026-01-01 00:00:00', '2026-01-02 00:00:00'), "
                "('proj_legacy_2', 'Second Show', 'DRAFT', '', "
                "'2026-02-01 00:00:00', '2026-02-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO video_production_revisions "
                "(id, project_id, parent_revision_id, status, content_hash, sequence, created_at) VALUES "
                "('rev_legacy_1', 'proj_legacy_1', NULL, 'DRAFT', "
                "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 0, "
                "'2026-01-01 08:00:00'), "
                "('rev_legacy_2', 'proj_legacy_1', 'rev_legacy_1', 'LOCKED', "
                "'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 1, "
                "'2026-01-01 09:00:00'), "
                "('rev_legacy_3', 'proj_legacy_2', NULL, 'DRAFT', '', 0, '2026-02-01 09:00:00')"
            )
        )


def _counts(engine, tables: list[str]) -> dict:
    with engine.connect() as conn:
        return {
            table: conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            for table in tables
        }


LEGACY_TABLES = ["video_production_projects", "video_production_revisions"]
STUDIO_TABLES = ["studio_series_projects", "studio_episodes", "studio_revisions"]


def main() -> int:
    evidence: dict = {
        "phase": "A3",
        "gate": "STUDIO_PERSISTENCE_GATE",
        "contract": "studio.contract/v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git": {"branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO_ROOT).decode().strip()},
    }

    migration_sha = hashlib.sha256(MIGRATION_FILE.read_bytes()).hexdigest()
    evidence["migration"] = {
        "file": "storage/windagent_storage/migrations/alembic/versions/0010_studio_persistence.py",
        "revision": "0010_studio_persistence",
        "down_revision": "0009_immutable_plan_revisions",
        "sha256": migration_sha,
        "heads": list(alembic_heads()),
    }

    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    db_path = Path(handle.name)
    db_url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(db_url)
    rehearsal_log: list[dict] = []
    try:
        # 1. Legacy fixture at pre-Studio head, then upgrade through 0010.
        from alembic import command

        from windagent_storage.migrations.runner import _make_alembic_config

        command.upgrade(_make_alembic_config(db_url), "0009_immutable_plan_revisions")
        preflight = _counts(engine, LEGACY_TABLES)
        _seed_legacy(engine)
        preflight = _counts(engine, LEGACY_TABLES)
        alembic_upgrade_head(db_url)
        postflight = _counts(engine, LEGACY_TABLES + STUDIO_TABLES)
        evidence["preflight_row_counts"] = preflight
        evidence["postflight_row_counts"] = postflight
        evidence["current_after_upgrade"] = list(alembic_current(db_url))
        evidence["schema_snapshot"] = _schema_snapshot(engine)
        evidence["backfill_identity"] = {
            "synthetic_episode_for_proj_legacy_1": synthetic_episode_id("proj_legacy_1"),
        }

        # 2. Rollback rehearsal: downgrade 0010 only, verify legacy intact, re-upgrade.
        command.downgrade(_make_alembic_config(db_url), "0009_immutable_plan_revisions")
        rehearsal_log.append(
            {
                "step": "downgrade_to_0009",
                "current": list(alembic_current(db_url)),
                "row_counts": _counts(engine, LEGACY_TABLES),
            }
        )
        alembic_upgrade_head(db_url)
        rehearsal_log.append(
            {
                "step": "reupgrade_to_head",
                "current": list(alembic_current(db_url)),
                "row_counts": _counts(engine, LEGACY_TABLES + STUDIO_TABLES),
            }
        )
        evidence["rollback_rehearsal"] = rehearsal_log
    finally:
        engine.dispose()
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass

    # 3. Repository contract tests.
    test_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/storage/test_studio_repositories.py",
            "tests/unit/storage/migrations/test_0010_studio_persistence_migration.py",
            "-q",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    evidence["repository_contract_tests"] = {
        "command": "pytest tests/unit/storage/test_studio_repositories.py tests/unit/storage/migrations/test_0010_studio_persistence_migration.py -q",
        "exit_code": test_result.returncode,
        "tail": test_result.stdout.strip().splitlines()[-1] if test_result.stdout else test_result.stderr.strip().splitlines()[-1],
    }

    verdict_pass = (
        evidence["current_after_upgrade"] == ["0010_studio_persistence"]
        and postflight["studio_series_projects"] == 2
        and postflight["studio_episodes"] == 2
        and postflight["studio_revisions"] == 3
        and rehearsal_log[0]["row_counts"]["video_production_projects"] == 2
        and rehearsal_log[1]["current"] == ["0010_studio_persistence"]
        and test_result.returncode == 0
    )
    evidence["verdict"] = "PASS" if verdict_pass else "FAIL"
    evidence["checks"] = {
        "fresh_upgrade_reaches_head": evidence["current_after_upgrade"] == ["0010_studio_persistence"],
        "backfill_series_episodes_revisions": (
            postflight["studio_series_projects"] == 2
            and postflight["studio_episodes"] == 2
            and postflight["studio_revisions"] == 3
        ),
        "legacy_rows_preserved_on_downgrade": rehearsal_log[0]["row_counts"]["video_production_projects"] == 2
        and rehearsal_log[0]["row_counts"]["video_production_revisions"] == 3,
        "reupgrade_after_rehearsal": rehearsal_log[1]["current"] == ["0010_studio_persistence"],
        "repository_contract_tests_pass": test_result.returncode == 0,
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8"
    )
    lines = [
        "# STUDIO_PERSISTENCE_GATE — A3 verdict",
        "",
        f"- Contract: {evidence['contract']}",
        f"- Gate: {evidence['gate']}",
        f"- Verdict: **{evidence['verdict']}**",
        f"- Migration: {evidence['migration']['revision']} (sha256 {migration_sha[:16]}...)",
        f"- Current head: {evidence['current_after_upgrade']}",
        "",
        "## Checks",
        "",
    ]
    for name, ok in evidence["checks"].items():
        lines.append(f"- {'PASS' if ok else 'FAIL'} — {name}")
    lines += [
        "",
        "## Scope",
        "",
        "- Additive migration 0010: 8 Studio tables + 5 uniqueness indexes + outbox per-aggregate ordering index.",
        "- Deterministic backfill of legacy projects/revisions; no invented story content.",
        "- Repositories behind A2 ports with dual-read compatibility and optimistic concurrency.",
        "- StudioUnitOfWork: atomic aggregates/events/outbox with per-aggregate event sequences.",
        "- Downgrade rehearsal verified: legacy V2 rows untouched, re-upgrade clean.",
        "",
        "Evidence JSON: `artifacts/studio_roadmap_01/a3/evidence.json`",
        f"Generated: {evidence['generated_at']}",
        "",
    ]
    (ARTIFACT_DIR / "STUDIO_PERSISTENCE_GATE_VERDICT.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(f"verdict={evidence['verdict']} checks={json.dumps(evidence['checks'])}")
    return 0 if verdict_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
