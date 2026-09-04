"""Model-gateway application commands (immutable intentions with payloads)."""

from __future__ import annotations

from dataclasses import dataclass, field

from windagent.platform.commands import Command

from .coordinator import ModelCompletionResult
from .gateway import InvocationRequest
from .models import CredentialView, EndpointView, ProviderView, RuleView


@dataclass(frozen=True, slots=True)
class RegisterProvider(Command[ProviderView]):
    """Register a vendor with an initial endpoint and optional credential."""

    name: str
    base_url: str
    protocol_mode: str = "openai"
    display_name: str | None = None
    vendor_type: str = "cloud"
    credential_secret: str | None = None
    credential_label: str = ""
    supports_model_discovery: bool = True


@dataclass(frozen=True, slots=True)
class UpdateProvider(Command[ProviderView]):
    """Update mutable provider fields (secrets are never editable)."""

    provider_id: str
    display_name: str | None = None
    base_url: str | None = None
    protocol_mode: str | None = None
    enabled: bool | None = None


@dataclass(frozen=True, slots=True)
class DeleteProvider(Command[dict[str, object]]):
    """Delete a provider after the in-use check."""

    provider_id: str
    allow_disabling_rules: bool = False


@dataclass(frozen=True, slots=True)
class RotateProviderCredential(Command[CredentialView]):
    """Store a new credential version; the secret is write-only."""

    provider_id: str
    secret: str
    label: str = ""


@dataclass(frozen=True, slots=True)
class RemoveProviderCredential(Command[bool]):
    """Revoke and delete a provider's stored credential."""

    provider_id: str


@dataclass(frozen=True, slots=True)
class AddProviderEndpoint(Command[EndpointView]):
    """Register an additional callable endpoint for a provider."""

    provider_id: str
    base_url: str
    protocol_mode: str | None = None
    priority: int = 50
    weight: int = 100


@dataclass(frozen=True, slots=True)
class UpsertRoutingRule(Command[RuleView]):
    """Create or update a routing rule (version-bumped on update)."""

    rule_id: str
    canonical_model_id: str
    fallback_model_id: str | None = None
    description: str = ""
    enabled: bool = True
    priority: int | None = None
    expected_version: int | None = None
    task_labels: tuple[str, ...] = field(default=())
    agent_types: tuple[str, ...] = field(default=())
    workflow_types: tuple[str, ...] = field(default=())
    required_capabilities: tuple[str, ...] = field(default=())
    min_context_tokens: int = 0
    requires_tools: bool = False
    requires_vision: bool = False
    cost_classes: tuple[str, ...] = field(default=())
    requires_local: bool = False
    requires_private: bool = False
    user_preference_model: str | None = None


@dataclass(frozen=True, slots=True)
class DeleteRoutingRule(Command[bool]):
    """Delete one routing rule."""

    rule_id: str


@dataclass(frozen=True, slots=True)
class InvokeModel(Command[ModelCompletionResult]):
    """Route and execute one model invocation through the single authority."""

    request: InvocationRequest


@dataclass(frozen=True, slots=True)
class ReselectModel(Command[object]):
    """Release a scope's active lock and pin a new decision."""

    scope_type: str
    scope_id: str
    new_context: object
    reason: str = "explicit_reselection"
