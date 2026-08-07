"""Phase 1 — Migration, data integrity and platform security (G1.1–G1.3, G2.3, G9.3–G9.5).

Exit gates under test:
- ``alembic upgrade head`` builds a complete fresh DB.
- ``alembic downgrade base`` fully resets a test DB.
- Upgrade from a V2 fixture preserves needed data (title/status/metadata/objective).
- Secrets are stored with an ``enc:v1:`` ciphertext prefix; API/credential DTOs
  never expose the secret value.
- ``workspace_root=../../etc`` is rejected (400 at the API boundary).
- 8 parallel writers never hit "database is locked" (WAL + busy_timeout).
- ``redact_before_persist`` is applied at every persist boundary.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from windagent_storage.migrations.runner import (
    MultipleMigrationHeadsError,
    SchemaAheadOfMigrationsError,
    alembic_current,
    alembic_downgrade_base,
    alembic_heads,
    alembic_upgrade_head,
    verify_single_head,
)
from windagent_storage.orm.models import BaseORM, SessionORM

CIPHERTEXT_PREFIX = "enc:v1:"


@pytest.fixture
def fresh_db(tmp_path: Path) -> str:
    """A fresh file-backed SQLite URL under the test tmp dir."""
    return f"sqlite:///{tmp_path / 'fresh.db'}"


def _table_names(db_url: str) -> set[str]:
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).scalars().all()
        return set(rows)
    finally:
        engine.dispose()


class TestAlembicUpgrade:
    """G1.1 — alembic upgrade head / downgrade base."""

    def test_upgrade_head_builds_complete_fresh_schema(self, fresh_db: str):
        alembic_upgrade_head(fresh_db)
        tables = _table_names(fresh_db)

        required = {
            # V2 canonical
            "chat_sessions", "v2_tasks", "v2_workflow_runs", "v2_workflow_steps",
            "execution_events", "v2_outbox_records", "v2_artifacts",
            # V2 orchestration
            "task_runs", "execution_leases", "workflow_step_runs", "cancellation_requests",
            # V3 provider/routing
            "provider_vendors", "provider_credentials", "provider_endpoints",
            "canonical_models_v3", "endpoint_model_bindings", "route_locks_v3",
            "provider_routing_audit_v3", "route_attempts_v3",
            # Multi-agent aggregates (G1.2 / G1.3)
            "conversations", "parent_tasks", "agent_instances", "agent_sessions",
            "task_plan_versions", "task_nodes", "task_edges", "task_node_runs",
            "tool_executions", "worktrees", "conversation_events",
            # Alembic stamp
            "alembic_version",
        }
        missing = required - tables
        assert not missing, f"missing tables after upgrade head: {sorted(missing)}"

    def test_upgrade_head_is_idempotent(self, fresh_db: str):
        alembic_upgrade_head(fresh_db)
        alembic_upgrade_head(fresh_db)  # must not raise
        assert "conversations" in _table_names(fresh_db)

    def test_downgrade_base_resets_test_db(self, fresh_db: str):
        alembic_upgrade_head(fresh_db)
        assert len(_table_names(fresh_db)) > 30
        alembic_downgrade_base(fresh_db)
        remaining = _table_names(fresh_db)
        # Alembic keeps an empty alembic_version stamp table after a base
        # downgrade; every application table must be gone.
        assert remaining <= {"alembic_version"}, (
            f"downgrade base left application tables: {sorted(remaining)}"
        )

    def test_upgrade_from_v2_fixture_preserves_needed_data(self, tmp_path: Path):
        """G1.1 exit gate: upgrade from a V2 fixture loses no needed data."""
        fixture = f"sqlite:///{tmp_path / 'fixture.db'}"
        engine = create_engine(fixture)
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE chat_sessions (id TEXT PRIMARY KEY, title TEXT, status TEXT, "
                "agent_id TEXT, workspace_root TEXT, created_at TEXT, updated_at TEXT, "
                "last_event_sequence INTEGER, metadata_json TEXT)"
            ))
            conn.execute(text(
                "CREATE TABLE parent_tasks (id TEXT PRIMARY KEY, conversation_id TEXT, "
                "title TEXT, status TEXT, label TEXT, progress REAL, created_at TEXT)"
            ))
            conn.execute(text(
                "CREATE TABLE workflows (id TEXT PRIMARY KEY, session_id TEXT, status TEXT, created_at TEXT)"
            ))
            conn.execute(text(
                "CREATE TABLE workflow_steps (id TEXT PRIMARY KEY, workflow_id TEXT, name TEXT, "
                "tool_name TEXT, params_json TEXT, status TEXT, order_index INTEGER)"
            ))
            conn.execute(text(
                "CREATE TABLE task_artifacts (id TEXT PRIMARY KEY, artifact_type TEXT, "
                "path_or_uri TEXT, metadata_json TEXT, created_at TEXT)"
            ))
            conn.execute(text(
                "INSERT INTO chat_sessions (id, title, status, metadata_json) "
                "VALUES ('s1', 'Keep Me', 'active', '{\"x\": 1}')"  # space avoids text() bind parsing of ':1'
            ))
            conn.execute(text(
                "INSERT INTO parent_tasks (id, conversation_id, title, status) "
                "VALUES ('t1', 's1', 'Task Objective', 'pending')"
            ))
            conn.execute(text(
                "INSERT INTO workflows (id, session_id, status) VALUES ('w1', 's1', 'pending')"
            ))
            conn.execute(text(
                "INSERT INTO workflow_steps (id, workflow_id, name, tool_name, order_index) "
                "VALUES ('st1', 'w1', 'Step1', 'shell', 0)"
            ))
            conn.execute(text(
                "INSERT INTO task_artifacts (id, artifact_type, path_or_uri) "
                "VALUES ('a1', 'txt', '/tmp/a.txt')"
            ))
        engine.dispose()

        alembic_upgrade_head(fixture)

        check = create_engine(fixture)
        try:
            with check.connect() as conn:
                conv = conn.execute(
                    text("SELECT conversation_id, title, status, metadata_json FROM conversations")
                ).fetchone()
                assert conv is not None
                assert conv[0] == "s1" and conv[1] == "Keep Me" and conv[2] == "active"
                assert json.loads(conv[3]) == {"x": 1}

                parent = conn.execute(
                    text("SELECT parent_task_id, conversation_id, objective, status FROM parent_tasks")
                ).fetchone()
                assert parent is not None
                assert parent[0] == "t1" and parent[1] == "s1"
                assert parent[2] == "Task Objective"

                # Legacy -> V2 lane still preserved.
                assert conn.execute(text("SELECT COUNT(*) FROM v2_tasks")).scalar() == 1
                assert conn.execute(text("SELECT COUNT(*) FROM v2_workflow_runs")).scalar() == 1
                assert conn.execute(text("SELECT COUNT(*) FROM v2_workflow_steps")).scalar() == 1
                assert conn.execute(text("SELECT COUNT(*) FROM v2_artifacts")).scalar() == 1
        finally:
            check.dispose()

    def test_multi_agent_constraints_exist(self, fresh_db: str):
        """G1.2 — FK/index/unique constraints on the canonical aggregates."""
        alembic_upgrade_head(fresh_db)
        engine = create_engine(fresh_db)
        try:
            with engine.connect() as conn:

                def _unique_index_columns(table: str) -> list[str]:
                    rows = conn.execute(
                        text(f"PRAGMA index_list({table})")
                    ).fetchall()  # (seq, name, unique, origin, partial)
                    cols: list[str] = []
                    for _seq, name, unique, _origin, _partial in rows:
                        if not unique:
                            continue
                        info = conn.execute(
                            text(f"PRAGMA index_info('{name}')")
                        ).fetchall()
                        cols.extend(row[2] for row in info)
                    return cols

                assert "windagent_session_id" in _unique_index_columns(
                    "agent_sessions"
                ), "agent_sessions.windagent_session_id must be unique"
                assert "idempotency_key" in _unique_index_columns(
                    "tool_executions"
                ), "tool_executions.idempotency_key must be unique"

                parent_indexes = {
                    r[1]
                    for r in conn.execute(
                        text("PRAGMA index_list(parent_tasks)")
                    ).fetchall()
                }
                assert any("conversation_id" in i for i in parent_indexes), (
                    "parent_tasks.conversation_id must be indexed"
                )
                agent_indexes = {
                    r[1]
                    for r in conn.execute(
                        text("PRAGMA index_list(agent_instances)")
                    ).fetchall()
                }
                assert any("conversation_id" in i for i in agent_indexes), (
                    "agent_instances.conversation_id must be indexed"
                )
        finally:
            engine.dispose()

    def test_unique_windagent_session_id_enforced(self, fresh_db: str):
        """G1.2 acceptance: duplicate windagent_session_id raises IntegrityError."""
        from sqlalchemy.exc import IntegrityError

        alembic_upgrade_head(fresh_db)
        engine = create_engine(fresh_db)
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO conversations (conversation_id, status, created_at, updated_at) "
                    "VALUES ('c1', 'idle', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ))
                conn.execute(text(
                    "INSERT INTO agent_instances (agent_instance_id, conversation_id, agent_type, status, "
                    "created_at, updated_at) VALUES ('a1', 'c1', 'coder', 'created', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ))
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO agent_sessions (agent_session_id, agent_instance_id, windagent_session_id, "
                    "status, version, created_at, updated_at) VALUES "
                    "('s1', 'a1', 'ws-1', 'idle', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ))
            with pytest.raises(IntegrityError):
                with engine.begin() as conn:
                    conn.execute(text(
                        "INSERT INTO agent_sessions (agent_session_id, agent_instance_id, "
                        "windagent_session_id, status, version, created_at, updated_at) VALUES "
                        "('s2', 'a1', 'ws-1', 'idle', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ))
        finally:
            engine.dispose()


class TestAlembicHeadIntegrity:
    """Stage 1 GAP D — single-head and current-revision inspection."""

    def test_heads_declare_exactly_one_linear_chain(self):
        heads = alembic_heads()
        assert len(heads) == 1, f"revision graph must stay linear, got heads={heads}"
        # Intentional tripwire (GAP D): bump this only when a new migration is
        # appended to the chain — the test exists to fail loudly on drift.
        assert heads[0] == "0009_immutable_plan_revisions"

    def test_verify_single_head_passes_on_linear_chain(self):
        assert verify_single_head() == "0009_immutable_plan_revisions"

    def test_verify_single_head_raises_on_multiple_heads(self, monkeypatch):
        monkeypatch.setattr(
            "windagent_storage.migrations.runner.alembic_heads",
            lambda: ("0008_conversation_stream_recovery", "0009_immutable_plan_revisions"),
        )
        with pytest.raises(MultipleMigrationHeadsError):
            verify_single_head()

    def test_current_is_empty_before_any_migration(self, fresh_db: str):
        assert alembic_current(fresh_db) == ()

    def test_current_matches_head_after_upgrade(self, fresh_db: str):
        alembic_upgrade_head(fresh_db)
        assert alembic_current(fresh_db) == ("0009_immutable_plan_revisions",)
        assert verify_single_head(fresh_db) == "0009_immutable_plan_revisions"

    def test_current_empty_after_downgrade_base(self, fresh_db: str):
        alembic_upgrade_head(fresh_db)
        alembic_downgrade_base(fresh_db)
        assert alembic_current(fresh_db) == ()

    def test_current_does_not_create_missing_db_file(self, tmp_path: Path):
        db_path = tmp_path / "never-created.db"
        assert not db_path.exists()
        assert alembic_current(f"sqlite:///{db_path}") == ()
        assert not db_path.exists(), "alembic_current must not create a DB file"

    def test_verify_single_head_raises_on_unknown_stamp(self, fresh_db: str):
        from sqlalchemy import create_engine, text

        alembic_upgrade_head(fresh_db)
        engine = create_engine(fresh_db)
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO alembic_version (version_num) VALUES ('9999_future')"
                ))
        finally:
            engine.dispose()
        with pytest.raises(SchemaAheadOfMigrationsError):
            verify_single_head(fresh_db)


class TestSecretEncryption:
    """G2.3 — AES-GCM at rest, no fixed fallback key, metadata-only API."""

    def test_encrypt_requires_key_no_fallback(self, monkeypatch):
        from windagent_storage.security.encryption import (
            EncryptionKeyMissingError,
            encrypt,
        )

        monkeypatch.delenv("WINDAGENT_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("WINDA_AGENT_ENCRYPTION_KEY", raising=False)
        with pytest.raises(EncryptionKeyMissingError):
            encrypt("sk-secret-key-value")

    def test_encrypt_prefix_and_roundtrip(self, monkeypatch):
        import base64

        from windagent_storage.security.encryption import decrypt, encrypt

        monkeypatch.setenv("WINDAGENT_ENCRYPTION_KEY", base64.b64encode(b"k" * 32).decode())
        cipher = encrypt("sk-secret-key-value")
        assert cipher.startswith(CIPHERTEXT_PREFIX)
        assert decrypt(cipher) == "sk-secret-key-value"
        assert "sk-secret-key-value" not in cipher

    def test_decrypt_passthrough_for_legacy_plaintext(self, monkeypatch):
        from windagent_storage.security.encryption import decrypt

        monkeypatch.delenv("WINDAGENT_ENCRYPTION_KEY", raising=False)
        assert decrypt("plain-legacy-value") == "plain-legacy-value"

    def test_public_credential_dict_never_exposes_secret(self):
        from windagent_storage.security.credentials import public_credential_dict

        dto = public_credential_dict(
            credential_id="cred-1",
            label="prod",
            is_env_ref=False,
            env_var_name=None,
            secret_version=1,
            enabled=True,
        )
        serialized = json.dumps(dto)
        assert "secret" not in serialized.lower() or "has_secret" in dto
        for forbidden in ("ciphertext", "api_key", "apiKey"):
            assert forbidden not in serialized.lower()


class TestKeyRotation:
    """Stage 1 GAP C — key_version recording, rotation and on-read re-encrypt."""

    @pytest.fixture(autouse=True)
    def _keys(self, monkeypatch):
        import base64

        monkeypatch.setenv("WINDAGENT_ENCRYPTION_KEY", base64.b64encode(b"k" * 32).decode())
        monkeypatch.setenv("WINDAGENT_ENCRYPTION_KEY_V2", base64.b64encode(b"j" * 32).decode())

    def test_default_version_is_v1_legacy_shape(self):
        from windagent_storage.security.encryption import encrypt, key_version_of

        cipher = encrypt("secret-1")
        assert cipher.startswith("enc:v1:")
        assert key_version_of(cipher) == 1

    def test_pinned_v2_roundtrip_and_version_recorded(self):
        from windagent_storage.security.encryption import decrypt, encrypt, key_version_of

        cipher = encrypt("secret-2", key_version=2)
        assert key_version_of(cipher) == 2
        assert cipher.startswith("enc:v1:kv2:")
        assert decrypt(cipher) == "secret-2"

    def test_decrypt_uses_recorded_version(self, monkeypatch):
        """A v2 ciphertext must decrypt with the v2 key even when the current version differs."""
        from windagent_storage.security.encryption import decrypt, encrypt

        cipher_v2 = encrypt("old-but-readable", key_version=2)
        monkeypatch.setenv("WINDAGENT_ENCRYPTION_KEY_VERSION", "1")
        assert decrypt(cipher_v2) == "old-but-readable"

    def test_reencrypt_to_current_migrates_old_version(self, monkeypatch):
        from windagent_storage.security.encryption import (
            decrypt,
            encrypt,
            key_version_of,
            reencrypt_to_current,
        )

        old = encrypt("rotate-me", key_version=1)
        monkeypatch.setenv("WINDAGENT_ENCRYPTION_KEY_VERSION", "2")
        migrated = reencrypt_to_current(old)
        assert key_version_of(migrated) == 2
        assert decrypt(migrated) == "rotate-me"

    def test_reencrypt_keeps_plaintext_and_current_version_untouched(self, monkeypatch):
        from windagent_storage.security.encryption import (
            encrypt,
            key_version_of,
            reencrypt_to_current,
        )

        monkeypatch.setenv("WINDAGENT_ENCRYPTION_KEY_VERSION", "2")
        assert reencrypt_to_current("plain-legacy") == "plain-legacy"
        current = encrypt("already-current")
        assert reencrypt_to_current(current) == current

    def test_unknown_version_requires_its_key_env(self, monkeypatch):
        from windagent_storage.security.encryption import (
            EncryptionKeyMissingError,
            encrypt,
        )

        monkeypatch.delenv("WINDAGENT_ENCRYPTION_KEY_V3", raising=False)
        with pytest.raises(EncryptionKeyMissingError):
            encrypt("needs-v3", key_version=3)


class TestForeignKeyEnforcement:
    """Stage 1 GAP A — orphan FK inserts must fail at the DB boundary."""

    def test_orphan_agent_sessions_rejected_on_sync_connection(self, fresh_db: str):
        from sqlalchemy.exc import IntegrityError

        from windagent_storage.database.sync_factory import make_sync_session_factory

        alembic_upgrade_head(fresh_db)
        factory = make_sync_session_factory(fresh_db)
        with factory() as session:
            session.execute(text(
                "INSERT INTO conversations (conversation_id, status, created_at, updated_at) "
                "VALUES ('c1', 'idle', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
            session.execute(text(
                "INSERT INTO agent_instances (agent_instance_id, conversation_id, agent_type, status, "
                "created_at, updated_at) VALUES ('a1', 'c1', 'coder', 'created', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
            session.commit()
        with factory() as session, pytest.raises(IntegrityError):
            session.execute(text(
                "INSERT INTO agent_sessions (agent_session_id, agent_instance_id, "
                "windagent_session_id, status, version, created_at, updated_at) VALUES "
                "('s-orphan', 'NO-SUCH-INSTANCE', 'ws-orphan', 'idle', 1, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
            session.commit()

    @pytest.mark.asyncio
    async def test_orphan_agent_sessions_rejected_on_async_connection(self, tmp_path: Path):
        from sqlalchemy.exc import IntegrityError

        from windagent_storage.database.connection import DatabaseManager
        from windagent_storage.orm.models import BaseORM

        db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'fk.db'}")
        await db.upgrade_to_head(BaseORM.metadata)
        try:
            async with db.session_factory() as session:
                await session.execute(text(
                    "INSERT INTO conversations (conversation_id, status, created_at, updated_at) "
                    "VALUES ('c1', 'idle', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ))
                await session.execute(text(
                    "INSERT INTO agent_instances (agent_instance_id, conversation_id, agent_type, status, "
                    "created_at, updated_at) VALUES ('a1', 'c1', 'coder', 'created', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ))
                await session.commit()
            with pytest.raises(IntegrityError):
                async with db.session_factory() as session:
                    await session.execute(text(
                        "INSERT INTO agent_sessions (agent_session_id, agent_instance_id, "
                        "windagent_session_id, status, version, created_at, updated_at) VALUES "
                        "('s-orphan', 'NO-SUCH-INSTANCE', 'ws-orphan', 'idle', 1, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ))
                    await session.commit()
        finally:
            await db.close()


class TestWorkspaceRootValidation:
    """G9.5 — resolve() + containment; traversal/symlink escape rejected."""

    def test_traversal_rejected(self):
        from windagent_core.security.workspace import (
            WorkspaceRootViolation,
            validate_workspace_root,
        )

        with pytest.raises(WorkspaceRootViolation):
            validate_workspace_root("../../etc")

    def test_empty_rejected(self):
        from windagent_core.security.workspace import (
            WorkspaceRootViolation,
            validate_workspace_root,
        )

        with pytest.raises(WorkspaceRootViolation):
            validate_workspace_root("")

    def test_valid_path_inside_repo_accepted(self):
        from windagent_core.security.workspace import (
            find_repository_root,
            validate_workspace_root,
        )

        root = find_repository_root(Path(__file__))
        resolved = validate_workspace_root(".")
        assert resolved.is_relative_to(root)

    def test_symlink_escape_rejected(self, tmp_path: Path):
        from windagent_core.security.workspace import (
            WorkspaceRootViolation,
            validate_workspace_root,
        )

        outside = tmp_path.parent / f"outside-{tmp_path.name}"
        outside.mkdir(exist_ok=True)
        link = tmp_path / "escape"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation not permitted on this platform")
        try:
            with pytest.raises(WorkspaceRootViolation):
                validate_workspace_root(str(link), repo_root=tmp_path)
        finally:
            outside.rmdir()

    def test_api_rejects_traversal_with_400(self, tmp_path: Path, monkeypatch):
        """API boundary returns HTTP 400 for workspace_root=../../etc."""
        from fastapi.testclient import TestClient

        from windagent_api.main import app

        db_url = f"sqlite+aiosqlite:///{tmp_path / 'api.db'}"
        monkeypatch.setenv("WINDAGENT_DATABASE_URL", db_url)
        with TestClient(app) as client:
            res = client.post("/api/v2/sessions", json={"workspace_root": "../../etc"})
            assert res.status_code == 400
            assert "workspace_root" in res.json()["detail"]


class TestParallelWriters:
    """G9.3 — WAL + busy_timeout on the async DatabaseManager."""

    @pytest.mark.asyncio
    async def test_eight_parallel_writers_no_lock(self, tmp_path: Path):
        from windagent_storage.database.connection import DatabaseManager

        db_path = tmp_path / "parallel.db"
        db = DatabaseManager(f"sqlite+aiosqlite:///{db_path}")
        await db.upgrade_to_head(BaseORM.metadata)

        try:
            async def writer(i: int) -> None:
                now = datetime.now(timezone.utc)
                async with db.session_factory() as session:
                    session.add(
                        SessionORM(
                            id=f"w{i}",
                            title=f"Writer {i}",
                            status="idle",
                            created_at=now,
                            updated_at=now,
                            last_event_sequence=i,
                        )
                    )
                    await session.commit()

            errors = []
            try:
                await asyncio.gather(*(writer(i) for i in range(8)))
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(str(exc))

            assert not errors, f"parallel writers failed: {errors}"
            # journal_mode persisted to WAL for file DBs.
            async with db.session_factory() as session:
                res = await session.execute(text("PRAGMA journal_mode"))
                assert res.scalar() == "wal"
        finally:
            await db.close()


class TestRedactionAtPersist:
    """G9.4 — redact_before_persist at event / outbox / tool-argument boundaries."""

    def test_redact_before_persist_masks_secrets(self):
        from windagent_core.security.redaction import redact_before_persist

        cleaned = redact_before_persist(
            {"api_key": "sk-live-1234567890", "body": "Bearer sk-secret-abcdef", "safe": "hello"}
        )
        assert "sk-live-1234567890" not in json.dumps(cleaned)
        assert "sk-secret-abcdef" not in json.dumps(cleaned)
        assert cleaned["safe"] == "hello"

    @pytest.mark.asyncio
    async def test_event_persist_redacts_secrets_preserves_prose(self, tmp_path: Path):
        from windagent_core.domain.types import EventId, SessionId
        from windagent_core.events.envelope import EventEnvelope
        from windagent_core.domain.lifecycle import utc_now
        from windagent_storage.database.connection import DatabaseManager
        from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
        from uuid import uuid4

        db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'events.db'}")
        await db.upgrade_to_head(BaseORM.metadata)
        try:
            sid = str(uuid4())
            async with SqlUnitOfWork(db.session_factory) as uow:
                # Structured secret under a sensitive key must be masked.
                await uow.events.append(
                    EventEnvelope(
                        event_id=EventId(str(uuid4())),
                        event_type="tool_executed",
                        aggregate_id="agg-1",
                        aggregate_type="session",
                        session_id=SessionId(sid),
                        payload={"command": "run deploy", "api_key": "secret-value-123"},
                        occurred_at=utc_now(),
                        sequence=1,
                    )
                )
                # Legitimate user prose must NOT be pattern-corrupted.
                await uow.events.append(
                    EventEnvelope(
                        event_id=EventId(str(uuid4())),
                        event_type="message_received",
                        aggregate_id="agg-1",
                        aggregate_type="session",
                        session_id=SessionId(sid),
                        payload={"sender": "user", "content": "I use a password manager for my accounts"},
                        occurred_at=utc_now(),
                        sequence=2,
                    )
                )
                await uow.commit()

            async with SqlUnitOfWork(db.session_factory) as uow:
                events = await uow.events.get_events(stream_id=sid, after_sequence=0)
                assert len(events) == 2
                raw = json.dumps([e.payload for e in events])
                assert "secret-value-123" not in raw
                assert "REDACTED" in raw
                # Prose round-trips untouched.
                assert "I use a password manager for my accounts" in raw
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_tool_arguments_redacted_on_submit(self, tmp_path: Path):
        from windagent_core.contracts import WorkSubmission
        from windagent_storage.database.connection import DatabaseManager
        from windagent_storage.repositories.sql_repositories import SqlWorkRepository
        from uuid import uuid4

        db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'work.db'}")
        await db.upgrade_to_head(BaseORM.metadata)
        try:
            async with db.session_factory() as session:
                repo = SqlWorkRepository(session)
                await repo.submit(
                    WorkSubmission(
                        prompt="run deploy with api_key=canarysecret-12345",
                        task_id=str(uuid4()),
                        session_id=str(uuid4()),
                        tool_name="shell",
                        parameters={"api_key": "canarysecret-12345", "args": ["--flag"]},
                    )
                )
                await session.commit()

            async with db.session_factory() as session:
                from sqlalchemy import select

                from windagent_storage.orm.v2_orchestration_models import TaskRunORM

                orm = (await session.execute(select(TaskRunORM))).scalars().first()
                assert orm is not None
                facts = json.loads(orm.facts_json)
                raw = json.dumps(facts)
                assert "canarysecret-12345" not in raw
        finally:
            await db.close()


class TestRuntimeMigrationAdoption:
    """G1.1 architecture gates — runtime no longer calls create_tables directly."""

    _RUNTIME_FILES = [
        "apps/api/windagent_api/composition.py",
        "apps/api/windagent_api/dependencies.py",
        "apps/worker/windagent_worker/composition.py",
        "apps/cli/windagent_cli/composition.py",
    ]

    def test_runtime_composition_uses_upgrade_to_head(self):
        root = Path(__file__).resolve().parents[4]
        for rel in self._RUNTIME_FILES:
            path = root / rel
            content = path.read_text(encoding="utf-8")
            assert "upgrade_to_head" in content, f"{rel} must adopt upgrade_to_head"
            assert "create_tables" not in content, f"{rel} must not call create_tables"

    def test_encryption_has_no_fixed_fallback_key(self):
        root = Path(__file__).resolve().parents[4]
        content = (
            root / "storage/windagent_storage/security/encryption.py"
        ).read_text(encoding="utf-8")
        assert 'b"0" * 32' not in content
        assert "WINDAGENT_ENCRYPTION_KEY" in content
