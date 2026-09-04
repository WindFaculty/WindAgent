"""Actor identities and the store that resolves them.

An ``Identity`` is the verified description of a principal; tokens and
requests only ever carry an ``ActorId``.  The durable identity store becomes
a feature-module concern later; the foundation ships the contract plus the
in-memory store used by composition roots and tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from windagent.kernel.ids import ActorId


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be empty")
    return normalized


class IdentityKind(StrEnum):
    """The two principal kinds V2 recognizes."""

    USER = "user"
    SERVICE = "service"


@dataclass(frozen=True, slots=True)
class Identity:
    """The authoritative description of one actor."""

    actor_id: ActorId
    kind: IdentityKind
    name: str
    roles: tuple[str, ...] = ()
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.actor_id, ActorId):
            raise TypeError("actor_id must be an ActorId")
        if not isinstance(self.kind, IdentityKind):
            raise TypeError("kind must be an IdentityKind")
        object.__setattr__(self, "name", _required_text(self.name, "name"))
        normalized_roles = tuple(
            _required_text(role, "role") for role in self.roles
        )
        if len(set(normalized_roles)) != len(normalized_roles):
            raise ValueError("roles must not contain duplicates")
        object.__setattr__(self, "roles", normalized_roles)

    def has_role(self, role: str) -> bool:
        """Return whether the identity carries ``role``."""
        return role in self.roles


@runtime_checkable
class IdentityStore(Protocol):
    """Resolves actor IDs to verified identities."""

    async def get(self, actor_id: ActorId) -> Identity | None:
        """Return the identity for ``actor_id`` when it exists."""


@dataclass(slots=True)
class InMemoryIdentityStore:
    """Process-local identity store for composition roots and tests."""

    _identities: dict[str, Identity] = field(default_factory=dict, init=False)

    def put(self, identity: Identity) -> None:
        """Insert or replace one identity."""
        if not isinstance(identity, Identity):
            raise TypeError("identity must be an Identity")
        self._identities[identity.actor_id.value] = identity

    async def get(self, actor_id: ActorId) -> Identity | None:
        if not isinstance(actor_id, ActorId):
            raise TypeError("actor_id must be an ActorId")
        return self._identities.get(actor_id.value)
