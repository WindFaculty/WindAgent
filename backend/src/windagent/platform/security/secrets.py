"""Concrete secret stores without infrastructure dependencies.

Both implementations satisfy the Phase 3 ``SecretStore`` protocol.  The
environment store maps a secret name to ``WINDAGENT_SECRET_<NORMALIZED_NAME>``
(e.g. ``auth/token_key`` → ``WINDAGENT_SECRET_AUTH_TOKEN_KEY``) so production
composition roots can provision signing material without a database.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .contracts import SecretValue

_ENV_PREFIX = "WINDAGENT_SECRET_"
_ENV_SANITIZE = re.compile(r"[^A-Za-z0-9]")


def _env_name(name: str) -> str:
    return _ENV_PREFIX + _ENV_SANITIZE.sub("_", name.strip()).upper()


@dataclass(slots=True)
class InMemorySecretStore:
    """Process-local secret store for composition roots and tests."""

    _secrets: dict[str, SecretValue] = field(default_factory=dict, init=False)

    def put(self, name: str, value: SecretValue) -> None:
        """Insert or replace one secret."""
        normalized = _required_name(name)
        if not isinstance(value, SecretValue):
            raise TypeError("value must be a SecretValue")
        self._secrets[normalized] = value

    async def read(self, name: str) -> SecretValue | None:
        return self._secrets.get(_required_name(name))

    async def write(self, name: str, value: SecretValue) -> None:
        self.put(name, value)

    async def delete(self, name: str) -> bool:
        return self._secrets.pop(_required_name(name), None) is not None


@dataclass(slots=True)
class EnvironmentSecretStore:
    """Reads secrets from process environment variables (write-disabled)."""

    async def read(self, name: str) -> SecretValue | None:
        raw = os.environ.get(_env_name(_required_name(name)))
        if not raw:
            return None
        return SecretValue(raw)

    async def write(self, name: str, value: SecretValue) -> None:
        raise NotImplementedError(
            "environment secrets are provisioned outside the process; "
            "this store is read-only"
        )

    async def delete(self, name: str) -> bool:
        raise NotImplementedError(
            "environment secrets are provisioned outside the process; "
            "this store is read-only"
        )


def _required_name(name: str) -> str:
    if not isinstance(name, str):
        raise TypeError("secret name must be a string")
    normalized = name.strip()
    if not normalized:
        raise ValueError("secret name cannot be empty")
    return normalized
