"""Phase 3 gate (ban_ke_hoach §5.3-5.4, Scenario B).

Verify:
  - Route lock pins canonical model; switching model on same scope raises.
  - Same-model provider failover: 429 on binding A -> binding B chosen,
    no different canonical model ever selected.
  - All-same-model bindings dead -> stop, no cross-model call.
  - Partial stream saved as audit_only, not in transcript.
  - Tool idempotency key column exists and round-trips.
"""
from __future__ import annotations

import pytest

from db.database import Database
from db.models import (
    CanonicalModelORM,
    ProviderModelBindingORM,
    PartialArtifactORM,
    ToolCallORM,
)
from services.route_lock_service import (
    RouteLockService,
    classify_error,
    should_switch_provider,
    ErrorClass,
    ModelResponseError,
    ModelOfflineError,
)
from services.partial_audit import save_partial_artifact


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite+aiosqlite:///{tmp_path/'phase3.db'}?timeout=30"


async def _seed(db):
    async with db.session() as s:
        # Two bindings of SAME canonical model X on two providers.
        s.add(CanonicalModelORM(
            id="x", vendor="anthropic", family="sonnet", canonical_name="X",
            enabled=True,
        ))
        s.add(CanonicalModelORM(
            id="y", vendor="openai", family="gpt", canonical_name="Y", enabled=True,
        ))
        s.add(ProviderModelBindingORM(
            id="provA:x", canonical_model_id="x", provider_id="A",
            provider_model_id="x", priority=100, enabled=True,
        ))
        s.add(ProviderModelBindingORM(
            id="provB:x", canonical_model_id="x", provider_id="B",
            provider_model_id="x", priority=50, enabled=True,
        ))
        s.add(ProviderModelBindingORM(
            id="provC:y", canonical_model_id="y", provider_id="C",
            provider_model_id="y", priority=100, enabled=True,
        ))


async def test_lock_pins_canonical_and_blocks_switch(db_url):
    db = Database(db_url)
    await db.init_models()
    await _seed(db)
    svc = RouteLockService(db)

    lock = await svc.acquire_lock(
        scope_type="conversation", scope_id="conv1", canonical_model_id="x"
    )
    assert lock.canonical_model_id == "x"

    # Re-acquire same scope reuse.
    lock2 = await svc.acquire_lock(
        scope_type="conversation", scope_id="conv1", canonical_model_id="x"
    )
    assert lock2.id == lock.id

    # Attempt to switch canonical model on same scope -> forbidden.
    with pytest.raises(ValueError):
        await svc.acquire_lock(
            scope_type="conversation", scope_id="conv1", canonical_model_id="y"
        )
    await db.dispose()


async def test_same_model_failover_on_429(db_url):
    db = Database(db_url)
    await db.init_models()
    await _seed(db)
    svc = RouteLockService(db)

    # Binding A is best (priority 100). Provider B same model chosen after cooldown.
    b1 = await svc.select_binding("x")
    assert b1.binding_id == "provA:x"

    await svc.mark_binding_cooldown("provA:x")
    b2 = await svc.select_binding("x", exclude={"provA:x"})
    assert b2.binding_id == "provB:x"
    # Crucially still canonical model X, never Y.
    assert b2.canonical_model_id == "x"

    # Both X bindings dead -> no binding, never cross to Y.
    await svc.mark_binding_cooldown("provB:x")
    b3 = await svc.select_binding("x", exclude={"provA:x", "provB:x"})
    assert b3 is None
    await db.dispose()


async def test_error_classifier_and_policy(db_url):
    db = Database(db_url)
    await db.init_models()
    await _seed(db)
    assert classify_error(ModelResponseError("429 too many", status_code=429)) == ErrorClass.RATE_LIMIT
    assert classify_error(ModelResponseError("403 no", status_code=403)) == ErrorClass.AUTH
    assert classify_error(ModelResponseError("503 boom", status_code=503)) == ErrorClass.SERVER
    assert classify_error(ModelOfflineError("conn refused")) == ErrorClass.TIMEOUT_BEFORE_TOKEN
    assert should_switch_provider(ErrorClass.RATE_LIMIT) is True
    assert should_switch_provider(ErrorClass.CONTEXT_OVERFLOW) is False
    await db.dispose()


async def test_partial_audit_not_transcript(db_url):
    db = Database(db_url)
    await db.init_models()
    await _seed(db)
    aid = await save_partial_artifact(
        db, content_text="partial 40%", agent_session_id="as1",
        turn_id="t1", provider_binding_id="provA:x", error_class="stream_interrupted",
    )
    async with db.session() as s:
        art = await s.get(PartialArtifactORM, aid)
        assert art.visibility == "audit_only"
        assert art.content_text == "partial 40%"
    await db.dispose()


async def test_tool_call_idempotency_key(db_url):
    db = Database(db_url)
    await db.init_models()
    await _seed(db)
    async with db.session() as s:
        s.add(ToolCallORM(
            id="tc1", session_id="s1", tool_name="terminal",
            input_json="{}", output_json="{}", idempotency_key="idek_abc",
        ))
    async with db.session() as s:
        tc = await s.get(ToolCallORM, "tc1")
        assert tc.idempotency_key == "idek_abc"
    await db.dispose()
