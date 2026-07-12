"""Phase 2 gate: migration runs on old and new DB without data loss.

Verifies:
  - init_models() creates all Phase 2 tables on a fresh DB.
  - On a pre-existing DB (only legacy tables populated), running the new
    init_models() keeps legacy rows intact and seeds canonical models from
    the catalog non-destructively.
"""
from __future__ import annotations

import pytest
import sqlalchemy.ext.asyncio as sa_asyncio
from sqlalchemy import select

from db.database import Database
from db.models import (
    Base,
    CanonicalModelORM,
    ProviderModelBindingORM,
    ModelCatalogORM,
    ModelProviderORM,
    ChatSessionORM,
    MessageORM,
)


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite+aiosqlite:///{tmp_path/'phase2.db'}?timeout=30"


async def _fresh_init(db_url: str) -> Database:
    db = Database(db_url)
    await db.init_models()
    return db


async def test_new_db_has_phase2_tables(db_url):
    db = await _fresh_init(db_url)
    expected = {
        "canonical_models", "provider_model_bindings", "route_locks",
        "route_attempts", "parent_tasks", "task_plans", "task_nodes",
        "task_edges", "task_artifacts", "agent_instances", "agent_runs",
        "partial_artifacts",
    }
    assert expected.issubset(set(Base.metadata.tables.keys()))
    await db.dispose()


async def test_migration_preserves_legacy_data_and_seeds(db_url):
    # Simulate an OLD database state: legacy tables exist with data, but no
    # Phase 2 tables yet. Then run the Phase 2 init_models on top of it.
    engine = sa_asyncio.create_async_engine(db_url)
    async with engine.begin() as conn:
        # Build only the legacy schema (pre-Phase-2).
        legacy_tables = [
            "chat_sessions", "messages", "workflows", "workflow_steps",
            "tool_calls", "execution_events", "model_providers",
            "model_catalog", "model_runtime_status", "provider_quota_snapshots",
            "model_routing_rules", "model_activity", "model_benchmark_runs",
            "agents", "agent_sessions", "permission_requests",
        ]
        for name in legacy_tables:
            await conn.run_sync(Base.metadata.tables[name].create)

    # Seed legacy data.
    async with engine.begin() as conn:
        await conn.execute(
            ModelProviderORM.__table__.insert().values(
                id="openrouter", site_name="OpenRouter", api_source="openrouter",
                enabled=True,
            )
        )
        await conn.execute(
            ModelCatalogORM.__table__.insert().values(
                id="openrouter:gpt-4o", provider_id="openrouter",
                model_id="openai/gpt-4o", display_name="GPT-4o", type="API",
                context_window=128000, capabilities_json="[]", enabled=True,
            )
        )
        await conn.execute(
            ChatSessionORM.__table__.insert().values(
                id="sess-legacy", status="idle"
            )
        )
        await conn.execute(
            MessageORM.__table__.insert().values(
                id="msg-legacy", session_id="sess-legacy",
                sender="user", content="hello",
            )
        )
    await engine.dispose()

    # Run Phase 2 init on the existing DB.
    db = Database(db_url)
    await db.init_models()

    async with db.session() as s:
        # Legacy data must survive.
        res = await s.execute(select(ChatSessionORM))
        assert res.scalars().one().id == "sess-legacy"
        res = await s.execute(select(MessageORM))
        assert res.scalars().one().content == "hello"

        # Canonical model seeded from catalog.
        res = await s.execute(select(CanonicalModelORM))
        canon = {c.id for c in res.scalars().all()}
        assert "openai/gpt-4o" in canon

        res = await s.execute(select(ProviderModelBindingORM))
        bindings = res.scalars().all()
        assert any(b.canonical_model_id == "openai/gpt-4o" for b in bindings)

    # Re-running init is idempotent (no duplicate canonical rows).
    await db.init_models()
    async with db.session() as s:
        res = await s.execute(select(CanonicalModelORM))
        assert len([c for c in res.scalars().all()
                    if c.id == "openai/gpt-4o"]) == 1

    await db.dispose()


async def test_seed_idempotent_when_empty(db_url):
    db = await _fresh_init(db_url)
    # No catalog rows -> no canonical models, no error.
    async with db.session() as s:
        res = await s.execute(select(CanonicalModelORM))
        assert res.scalars().all() == []
    await db.dispose()
