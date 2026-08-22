"""Canonical Studio story model-routing roles (P0.3.1).

The frozen Studio task contract (``story_task_io.json`` / ``StudioTaskType``)
is the single source of truth for role names. The story prompt registry
exposes short capability labels (``ideation``, ``screenplay``, ...) on every
``ModelCompletionRequest``; the durable per-role routing rules are authored
with the canonical task-type strings. This module is the mapping authority
between the two vocabularies so rules and requests always match without
duplicating knowledge at the call sites.

Resolution semantics (P0.3.4):

    exact role rule  →  capability/default rule  →  system default  →  FAIL CLOSED

A rule whose predicates pin a canonical story role is an "exact" rule; a rule
with no predicates matches any request ("default"); the worker appends a
system-default rule (lowest priority) only when an explicit default model is
configured. When nothing matches, routing fails closed with
``ROUTING_UNAVAILABLE`` — no random model selection, ever.
"""

from __future__ import annotations

from dataclasses import dataclass, field

STORY_ROLES_SCHEMA_VERSION = "studio.story-roles/v1"

#: Error code raised when no routing rule resolves for a required role.
ROUTING_UNAVAILABLE = "ROUTING_UNAVAILABLE"


class RoutingUnavailableError(RuntimeError):
    """Fail-closed signal: no routing rule resolved a required role.

    Raised instead of a random model selection when neither an exact rule, a
    default rule, nor a system default matches. Non-retryable at the provider
    layer: configuration must change first.
    """

    def __init__(self, role: str = "", reason: str = "") -> None:
        self.code = ROUTING_UNAVAILABLE
        self.role = role
        super().__init__(
            reason
            or f"{ROUTING_UNAVAILABLE}: no model route resolved for role {role!r}"
        )


@dataclass(frozen=True)
class StoryRoleSpec:
    """One canonical story role and how it appears in matching contexts."""

    #: Canonical role == frozen ``StudioTaskType`` value.
    role: str
    label: str
    #: Short capability label(s) emitted by the story prompt registry.
    capability_labels: tuple[str, ...] = ()
    #: Whether the current handler routes this role through an LLM.
    llm_routed: bool = True
    aliases: tuple[str, ...] = field(default_factory=tuple)


#: Canonical story roles. ``idea.evaluate`` is scored deterministically by the
#: IdeaEvaluationService today (no model port) and ``lock`` needs no LLM; both
#: stay declared so configuration can be prepared ahead of runtime changes.
STORY_MODEL_ROLES: dict[str, StoryRoleSpec] = {
    spec.role: spec
    for spec in (
        StoryRoleSpec(
            role="studio.story.idea.generate",
            label="Idea Generation",
            capability_labels=("ideation",),
        ),
        StoryRoleSpec(
            role="studio.story.idea.evaluate",
            label="Idea Evaluation",
            capability_labels=(),
            llm_routed=False,
        ),
        StoryRoleSpec(
            role="studio.story.bible.generate",
            label="Story Bible Generation",
            capability_labels=("bibles",),
        ),
        StoryRoleSpec(
            role="studio.story.beats.generate",
            label="Beat Sheet Generation",
            capability_labels=("beats",),
        ),
        StoryRoleSpec(
            role="studio.story.outline.generate",
            label="Outline Generation",
            capability_labels=("outline",),
        ),
        StoryRoleSpec(
            role="studio.story.screenplay.generate",
            label="Screenplay Generation",
            capability_labels=("screenplay",),
        ),
        StoryRoleSpec(
            role="studio.story.review",
            label="Screenplay Review",
            capability_labels=("review",),
            aliases=("studio.story.screenplay.review",),
        ),
        StoryRoleSpec(
            role="studio.story.revise",
            label="Screenplay Revision",
            capability_labels=("review-revision", "revise"),
            aliases=("studio.story.screenplay.revise",),
        ),
    )
}

#: Plan-vocabulary alias -> canonical role (frozen StudioTaskType string).
ROLE_ALIASES: dict[str, str] = {
    alias: spec.role
    for spec in STORY_MODEL_ROLES.values()
    for alias in spec.aliases
}

#: Prompt-registry capability label -> canonical role.
CAPABILITY_ALIASES: dict[str, str] = {
    label: spec.role
    for spec in STORY_MODEL_ROLES.values()
    for label in spec.capability_labels
}


def normalize_story_role(role: str) -> str:
    """Map a plan-style alias to the canonical role; unknown input unchanged."""
    return ROLE_ALIASES.get(role.strip(), role.strip())


def resolve_story_role(label: str) -> StoryRoleSpec | None:
    """Resolve a role/capability/alias string to its spec when it is one."""
    clean = label.strip()
    if clean in STORY_MODEL_ROLES:
        return STORY_MODEL_ROLES[clean]
    canonical = ROLE_ALIASES.get(clean) or CAPABILITY_ALIASES.get(clean)
    return STORY_MODEL_ROLES.get(canonical) if canonical else None


def expand_role_labels(label: str) -> list[str]:
    """All equivalent matching labels for one role/capability string.

    Rule evaluation requires every configured ``task_label`` to be present in
    the context, so BOTH sides (rule projection and request context) are
    expanded to the same full equivalence class: canonical role + plan
    aliases + prompt-registry capability labels. The first entry is always
    the original input, preserving behavior for non-story labels.
    """
    clean = label.strip()
    labels = [clean]
    spec = resolve_story_role(clean)
    if spec is not None:
        for item in (spec.role, *spec.aliases, *spec.capability_labels):
            if item not in labels:
                labels.append(item)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in labels:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def story_role_choices() -> list[dict]:
    """Server-authoritative role list for UI selectors and validation."""
    return [
        {
            "role": spec.role,
            "label": spec.label,
            "capability_labels": list(spec.capability_labels),
            "llm_routed": spec.llm_routed,
            "aliases": list(spec.aliases),
        }
        for spec in STORY_MODEL_ROLES.values()
    ]


__all__ = [
    "STORY_ROLES_SCHEMA_VERSION",
    "ROUTING_UNAVAILABLE",
    "RoutingUnavailableError",
    "STORY_MODEL_ROLES",
    "ROLE_ALIASES",
    "CAPABILITY_ALIASES",
    "StoryRoleSpec",
    "normalize_story_role",
    "resolve_story_role",
    "expand_role_labels",
    "story_role_choices",
]
