"""Identity contracts and the in-memory identity store."""

from __future__ import annotations

import pytest
from windagent.kernel.ids import ActorId
from windagent.platform.security import Identity, IdentityKind, InMemoryIdentityStore


def _identity(**overrides: object) -> Identity:
    values: dict[str, object] = {
        "actor_id": ActorId.new(),
        "kind": IdentityKind.USER,
        "name": "ops-bot",
        "roles": ("admin",),
    }
    values.update(overrides)
    return Identity(**values)  # type: ignore[arg-type]


def test_identity_normalizes_and_exposes_roles() -> None:
    identity = _identity(roles=("a", "b"))
    assert identity.has_role("a")
    assert not identity.has_role("c")


@pytest.mark.parametrize(
    "overrides",
    [
        {"actor_id": "not-an-actor"},
        {"kind": "user"},
        {"name": "   "},
        {"roles": ("a", "a")},
    ],
)
def test_identity_rejects_invalid_input(overrides: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        _identity(**overrides)


async def test_identity_store_roundtrip() -> None:
    store = InMemoryIdentityStore()
    identity = _identity()
    store.put(identity)
    assert await store.get(identity.actor_id) == identity
    assert await store.get(ActorId.new()) is None


async def test_identity_store_put_replaces() -> None:
    store = InMemoryIdentityStore()
    actor_id = ActorId.new()
    store.put(_identity(actor_id=actor_id, name="before"))
    store.put(_identity(actor_id=actor_id, name="after"))
    identity = await store.get(actor_id)
    assert identity is not None and identity.name == "after"


async def test_identity_store_rejects_wrong_types() -> None:
    store = InMemoryIdentityStore()
    with pytest.raises(TypeError):
        store.put("not-an-identity")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        await store.get("not-an-actor")  # type: ignore[arg-type]
