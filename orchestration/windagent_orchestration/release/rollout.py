"""Progressive, fail-closed rollout policy for multi-agent execution.

This module deliberately does not accept HTTP headers or other client supplied
identity.  An API/authentication layer may pass a previously authenticated
``actor_id`` when the release is in the internal-users stage.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class RolloutStage(str, Enum):
    """The only permitted sequence for a multi-agent release."""

    SCHEMA_DUAL_READ = "schema_dual_read"
    SHADOW_ORCHESTRATION = "shadow_orchestration"
    INTERNAL_USERS = "internal_users"
    FULL_ACTIVATION = "full_activation"


_ORDER = {
    RolloutStage.SCHEMA_DUAL_READ: 0,
    RolloutStage.SHADOW_ORCHESTRATION: 1,
    RolloutStage.INTERNAL_USERS: 2,
    RolloutStage.FULL_ACTIVATION: 3,
}


class ReleaseNotActive(RuntimeError):
    """Raised before a rollout stage is allowed to dispatch real runtimes."""


@dataclass(frozen=True)
class ReleaseDecision:
    stage: RolloutStage
    actor_id: str | None
    schema_enabled: bool
    dual_read_enabled: bool
    shadow_orchestration_enabled: bool
    runtime_activation_enabled: bool
    reason: str


@dataclass(frozen=True)
class MultiAgentReleasePolicy:
    """A small immutable control plane used by API and worker composition.

    In production the default is ``schema_dual_read``.  Local development
    defaults to ``full_activation`` to preserve existing developer workflows;
    production must explicitly advance through the rollout stages.
    """

    stage: RolloutStage
    internal_actor_ids: frozenset[str] = frozenset()

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> "MultiAgentReleasePolicy":
        environ = os.environ if environ is None else environ
        default = (
            RolloutStage.SCHEMA_DUAL_READ.value
            if environ.get("WINDAGENT_ENV", "").lower() == "production"
            else RolloutStage.FULL_ACTIVATION.value
        )
        raw_stage = environ.get("WINDAGENT_MULTI_AGENT_RELEASE_STAGE", default).strip().lower()
        try:
            stage = RolloutStage(raw_stage)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in RolloutStage)
            raise ValueError(
                f"invalid WINDAGENT_MULTI_AGENT_RELEASE_STAGE={raw_stage!r}; expected one of {allowed}"
            ) from exc
        actors = frozenset(
            actor.strip()
            for actor in environ.get("WINDAGENT_MULTI_AGENT_INTERNAL_ACTORS", "").split(",")
            if actor.strip()
        )
        return cls(stage=stage, internal_actor_ids=actors)

    def decision_for(self, actor_id: str | None = None) -> ReleaseDecision:
        if self.stage is RolloutStage.FULL_ACTIVATION:
            return ReleaseDecision(
                stage=self.stage,
                actor_id=actor_id,
                schema_enabled=True,
                dual_read_enabled=True,
                shadow_orchestration_enabled=False,
                runtime_activation_enabled=True,
                reason="full activation",
            )
        if self.stage is RolloutStage.INTERNAL_USERS and actor_id in self.internal_actor_ids:
            return ReleaseDecision(
                stage=self.stage,
                actor_id=actor_id,
                schema_enabled=True,
                dual_read_enabled=True,
                shadow_orchestration_enabled=False,
                runtime_activation_enabled=True,
                reason="authenticated internal actor is allowlisted",
            )
        if self.stage is RolloutStage.SHADOW_ORCHESTRATION:
            return ReleaseDecision(
                stage=self.stage,
                actor_id=actor_id,
                schema_enabled=True,
                dual_read_enabled=True,
                shadow_orchestration_enabled=True,
                runtime_activation_enabled=False,
                reason="shadow comparisons only; runtime dispatch is disabled",
            )
        reason = (
            "actor is not allowlisted for internal rollout"
            if self.stage is RolloutStage.INTERNAL_USERS
            else "schema and dual-read are enabled; runtime dispatch is disabled"
        )
        return ReleaseDecision(
            stage=self.stage,
            actor_id=actor_id,
            schema_enabled=True,
            dual_read_enabled=True,
            shadow_orchestration_enabled=False,
            runtime_activation_enabled=False,
            reason=reason,
        )

    def require_runtime_activation(self, actor_id: str | None = None) -> ReleaseDecision:
        decision = self.decision_for(actor_id)
        if not decision.runtime_activation_enabled:
            raise ReleaseNotActive(f"multi-agent rollout is not active: {decision.reason}")
        return decision

    def transition_to(self, next_stage: RolloutStage) -> "MultiAgentReleasePolicy":
        """Advance exactly one stage; configuration cannot skip safety gates."""
        if _ORDER[next_stage] != _ORDER[self.stage] + 1:
            raise ValueError(
                f"invalid rollout transition {self.stage.value} -> {next_stage.value}; "
                "advance one stage at a time"
            )
        return MultiAgentReleasePolicy(next_stage, self.internal_actor_ids)

    def with_internal_actors(self, actor_ids: Iterable[str]) -> "MultiAgentReleasePolicy":
        return MultiAgentReleasePolicy(
            self.stage,
            frozenset(actor.strip() for actor in actor_ids if actor.strip()),
        )
