"""Policy and secret-storage contracts with no identity implementation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from windagent.kernel.ids import ActorId, EntityId
from windagent.kernel.types.json import freeze_json_mapping


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be empty")
    return normalized


class PolicyEffect(StrEnum):
    """The only outcomes available from a policy evaluation."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(frozen=True, slots=True)
class PolicyRequest:
    """A domain-neutral request to authorize a proposed operation."""

    action: str
    resource_type: str
    actor_id: ActorId | None = None
    resource_id: EntityId | None = None
    context: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", _required_text(self.action, "action"))
        object.__setattr__(self, "resource_type", _required_text(self.resource_type, "resource_type"))
        if self.actor_id is not None and not isinstance(self.actor_id, ActorId):
            raise TypeError("actor_id must be an ActorId or None")
        if self.resource_id is not None and not isinstance(self.resource_id, EntityId):
            raise TypeError("resource_id must be an EntityId or None")
        if not isinstance(self.context, Mapping):
            raise TypeError("context must be a mapping")
        object.__setattr__(self, "context", freeze_json_mapping(self.context))


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """A policy outcome plus optional machine-readable explanation."""

    effect: PolicyEffect
    reason: str | None = None
    policy_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.effect, PolicyEffect):
            raise TypeError("effect must be a PolicyEffect")
        if self.reason is not None:
            object.__setattr__(self, "reason", _required_text(self.reason, "reason"))
        if self.policy_id is not None:
            object.__setattr__(self, "policy_id", _required_text(self.policy_id, "policy_id"))


@dataclass(frozen=True, slots=True, init=False)
class SecretValue:
    """Secret text whose normal string representations are always redacted."""

    _plaintext: str

    def __init__(self, plaintext: str) -> None:
        if not isinstance(plaintext, str):
            raise TypeError("secret plaintext must be a string")
        if not plaintext:
            raise ValueError("secret plaintext cannot be empty")
        object.__setattr__(self, "_plaintext", plaintext)

    def reveal(self) -> str:
        """Return the plaintext only at the explicit use boundary."""

        return self._plaintext

    def __repr__(self) -> str:
        return "SecretValue(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


@runtime_checkable
class SecretStore(Protocol):
    """Stores secrets by opaque names without exposing storage technology."""

    async def read(self, name: str) -> SecretValue | None:
        """Return a secret value when the named secret exists."""

    async def write(self, name: str, value: SecretValue) -> None:
        """Create or replace a named secret."""

    async def delete(self, name: str) -> bool:
        """Delete a named secret, reporting whether it existed."""


@runtime_checkable
class PolicyEngine(Protocol):
    """Evaluates whether an operation is allowed, denied, or needs approval."""

    async def decide(self, request: PolicyRequest) -> PolicyDecision:
        """Evaluate the policy request without performing the operation itself."""
