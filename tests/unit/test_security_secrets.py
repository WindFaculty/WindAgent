"""Secret store contracts: in-memory and environment backed."""

from __future__ import annotations

import pytest
from windagent.platform.security import (
    EnvironmentSecretStore,
    InMemorySecretStore,
    SecretValue,
)


def test_secret_value_is_always_redacted() -> None:
    value = SecretValue("super-secret")
    assert "super-secret" not in repr(value)
    assert "super-secret" not in str(value)
    assert value.reveal() == "super-secret"


async def test_in_memory_store_roundtrip() -> None:
    store = InMemorySecretStore()
    await store.write("auth/token_key", SecretValue("k1"))
    stored = await store.read("auth/token_key")
    assert stored is not None and stored.reveal() == "k1"
    assert await store.delete("auth/token_key") is True
    assert await store.delete("auth/token_key") is False
    assert await store.read("auth/token_key") is None


def test_in_memory_store_put_rejects_wrong_types() -> None:
    store = InMemorySecretStore()
    with pytest.raises(TypeError):
        store.put("name", "raw-secret")  # type: ignore[arg-type]


async def test_environment_store_maps_names_and_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WINDAGENT_SECRET_AUTH_TOKEN_KEY", "from-env")
    store = EnvironmentSecretStore()
    stored = await store.read("auth/token_key")
    assert stored is not None and stored.reveal() == "from-env"
    assert await store.read("auth/missing") is None


async def test_environment_store_is_read_only() -> None:
    store = EnvironmentSecretStore()
    with pytest.raises(NotImplementedError):
        await store.write("name", SecretValue("v"))
    with pytest.raises(NotImplementedError):
        await store.delete("name")


async def test_empty_secret_names_are_rejected() -> None:
    store = InMemorySecretStore()
    with pytest.raises((TypeError, ValueError)):
        await store.read("   ")
