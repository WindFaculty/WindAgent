"""
Story prompt catalog (B2, frozen location: B0 registry freeze).

The registry is the ONLY source of prompt definitions for canonical Story
stages. Every entry declares a stable prompt ID ``story.<capability>.<name>``,
a semantic version, a content hash (SHA-256 over capability+version+template,
reusing ``PromptSpec.content_hash`` semantics), an input schema, an output
schema, and safety constraints.

Frozen rules (b0_registry_and_schema_freeze.md §3):
- Prompts are immutable once versioned; re-registering the same ID+version
  with different content is a registry violation (snapshot test).
- ``content_hash`` = SHA-256 over capability + version + template.
- Legacy video-pipeline prompts are extracted INCREMENTALLY as ``legacy=True``
  entries whose template/hash MUST match the live ``PromptSpec`` they were
  extracted from (equivalence tests); they are replaced stage by stage
  (B3+) and retired with the legacy stages.
- Registry entries never carry secrets or private reasoning.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_intelligence.video.continuation.service import CONTINUATION_PROMPT_V1
from windagent_intelligence.video.ideation.brief_expander import BRIEF_EXPANSION_PROMPT_V1
from windagent_intelligence.video.ideation.outliner import OUTLINE_PROMPT_V1
from windagent_intelligence.video.prompts import PromptSpec
from windagent_intelligence.video.screenplay.writer import SCREENPLAY_PROMPT_V1

from windagent_intelligence.story.prompts.schemas import (
    BRIEF_EXPANSION_OUTPUT_SCHEMA,
    CONTINUATION_TEXT_SPEC,
    OUTLINE_OUTPUT_SCHEMA,
    SCREENPLAY_TEXT_SPEC,
)

PROMPT_SCHEMA_VERSION = "studio.prompt/v1alpha1"

#: Prompt IDs are ``story.<capability>.<name>`` (B0 freeze).
_PROMPT_ID_RE = re.compile(r"^story\.[a-z0-9_]+(\.[a-z0-9_]+)*$")

#: Structured (schema-validated JSON) vs text-format (legacy) outputs.
OUTPUT_FORMAT_JSON = "json"
OUTPUT_FORMAT_TEXT = "text"

_DEFAULT_SAFETY_MAX_CHARS = 32_000


@dataclass(frozen=True)
class SafetyConstraints:
    """Declared output safety bounds for one prompt (frozen)."""

    max_output_chars: int = _DEFAULT_SAFETY_MAX_CHARS
    #: Case-insensitive regex patterns that make output fail closed.
    prohibited_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class StoryPromptEntry:
    """One immutable catalog entry: id/version/hash + schemas + safety."""

    prompt_id: str  # story.<capability>.<name>
    capability: str
    version: str  # semantic version, e.g. "1.0.0"
    template: str  # rendered into the user message ({placeholder} slots)
    output_schema: Dict[str, Any]
    input_schema: Optional[Dict[str, Any]] = None
    output_format: str = OUTPUT_FORMAT_JSON
    system: str = ""
    safety: SafetyConstraints = field(default_factory=SafetyConstraints)
    legacy: bool = False
    description: str = ""
    max_tokens: int = 2048
    temperature: float = 0.7
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _PROMPT_ID_RE.match(self.prompt_id):
            raise ValueError(
                f"prompt_id {self.prompt_id!r} must match 'story.<capability>.<name>'"
            )
        if self.output_format not in (OUTPUT_FORMAT_JSON, OUTPUT_FORMAT_TEXT):
            raise ValueError(f"unsupported output_format {self.output_format!r}")
        if self.output_format == OUTPUT_FORMAT_JSON and not self.output_schema:
            raise ValueError(f"prompt {self.prompt_id} must declare an output schema")
        if self.safety.max_output_chars <= 0:
            raise ValueError("safety.max_output_chars must be positive")

    @property
    def content_hash(self) -> str:
        """SHA-256 over capability+version+template (PromptSpec semantics)."""
        payload = f"{self.capability}::{self.version}::{self.template}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_prompt_spec(self) -> PromptSpec:
        """Compatibility projection onto the legacy PromptSpec primitive."""
        return PromptSpec(
            capability=self.capability,
            version=self.version,
            template=self.template,
            description=self.description,
            metadata={"prompt_id": self.prompt_id, **self.metadata},
        )

    def render(self, **kwargs: Any) -> str:
        """Render the template (missing keys left intact, PromptSpec semantics)."""
        return self.to_prompt_spec().render(**kwargs)

    def to_manifest_entry(self) -> Dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "capability": self.capability,
            "version": self.version,
            "content_hash": self.content_hash,
            "output_format": self.output_format,
            "legacy": self.legacy,
            "description": self.description,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": self.system,
            "safety": {
                "max_output_chars": self.safety.max_output_chars,
                "prohibited_patterns": list(self.safety.prohibited_patterns),
            },
            "input_schema_ref": None,
            "output_schema_ref": f"schemas/{self._schema_file_name()}",
        }

    def _schema_file_name(self) -> str:
        if self.output_format == OUTPUT_FORMAT_TEXT:
            name = self.output_schema.get("format", self.prompt_id.rsplit(".", 1)[-1])
        else:
            name = self.output_schema.get("title", self.prompt_id.rsplit(".", 1)[-1])
        return f"{name}.json"


#: Frozen catalog. Register via ``register_prompt``; never mutate in place.
STORY_PROMPT_REGISTRY: Dict[str, StoryPromptEntry] = {}


def register_prompt(entry: StoryPromptEntry) -> None:
    """Register one prompt; fail closed on ID+version content drift.

    Re-registering the same prompt_id with the same version but a different
    content hash (or different metadata) is a registry violation (immutable
    prompts, snapshot test). A new semantic version of the same prompt_id is
    a new entry; re-registering the identical entry is idempotent.
    """
    existing = STORY_PROMPT_REGISTRY.get(entry.prompt_id)
    if existing is not None:
        if existing == entry:
            return  # idempotent re-register
        if existing.version == entry.version:
            raise ValueError(
                f"prompt {entry.prompt_id!r} v{entry.version} already registered "
                f"with different content/metadata; bump the version for changes"
            )
        # new semantic version of the same prompt ID
        STORY_PROMPT_REGISTRY[entry.prompt_id] = entry
        return
    STORY_PROMPT_REGISTRY[entry.prompt_id] = entry


def prompt_for(prompt_id: str) -> StoryPromptEntry:
    """Look up a prompt; fail closed on unknown IDs (never silently default)."""
    try:
        return STORY_PROMPT_REGISTRY[prompt_id]
    except KeyError as exc:
        raise KeyError(f"no prompt registered for {prompt_id!r}") from exc


def registered_prompt_ids() -> List[str]:
    return sorted(STORY_PROMPT_REGISTRY)


def prompt_manifest() -> Dict[str, Any]:
    """Deterministic catalog manifest (sorted entries)."""
    return {
        "prompt_schema_version": PROMPT_SCHEMA_VERSION,
        "entries": {
            prompt_id: STORY_PROMPT_REGISTRY[prompt_id].to_manifest_entry()
            for prompt_id in registered_prompt_ids()
        },
    }


def validate_registry_invariants() -> List[str]:
    """Return catalog violations (empty = catalog is contract-clean)."""
    violations: List[str] = []
    for prompt_id, entry in STORY_PROMPT_REGISTRY.items():
        if entry.prompt_id != prompt_id:
            violations.append(f"{prompt_id}: dict key != entry.prompt_id")
        if not _PROMPT_ID_RE.match(entry.prompt_id):
            violations.append(f"{prompt_id}: malformed prompt ID")
        if not entry.version:
            violations.append(f"{prompt_id}: empty version")
        if not entry.template.strip():
            violations.append(f"{prompt_id}: empty template")
        if entry.output_format == OUTPUT_FORMAT_JSON and not entry.output_schema:
            violations.append(f"{prompt_id}: JSON output without output schema")
        if entry.safety.max_output_chars <= 0:
            violations.append(f"{prompt_id}: non-positive max_output_chars")
    return violations


# ---------------------------------------------------------------------------
# Incremental extraction of the legacy video-pipeline prompts (B2 step 1).
# Templates/hashes MUST equal the live PromptSpec constants (equivalence
# tests in test_story_b2_prompt_catalog.py).
# ---------------------------------------------------------------------------

def _legacy_entry(
    prompt_id: str,
    spec: PromptSpec,
    *,
    output_schema: Dict[str, Any],
    output_format: str,
    system: str,
    max_tokens: int,
    max_output_chars: int,
    description: str,
) -> StoryPromptEntry:
    return StoryPromptEntry(
        prompt_id=prompt_id,
        capability=spec.capability,
        version=spec.version,
        template=spec.template,
        output_schema=output_schema,
        output_format=output_format,
        system=system,
        safety=SafetyConstraints(max_output_chars=max_output_chars),
        legacy=True,
        description=description,
        max_tokens=max_tokens,
        temperature=0.7,
    )


register_prompt(
    _legacy_entry(
        "story.brief_expansion.expand",
        BRIEF_EXPANSION_PROMPT_V1,
        output_schema=BRIEF_EXPANSION_OUTPUT_SCHEMA,
        output_format=OUTPUT_FORMAT_JSON,
        system="You are the WindAgent creative brief expander.",
        max_tokens=1200,
        max_output_chars=8_000,
        description="Expand a raw idea into a creative brief JSON (legacy brief_expansion).",
    )
)
register_prompt(
    _legacy_entry(
        "story.outline.generate",
        OUTLINE_PROMPT_V1,
        output_schema=OUTLINE_OUTPUT_SCHEMA,
        output_format=OUTPUT_FORMAT_JSON,
        system="You are the WindAgent story outliner.",
        max_tokens=1500,
        max_output_chars=8_000,
        description="Turn a creative brief into a story outline JSON (legacy story_outline).",
    )
)
register_prompt(
    _legacy_entry(
        "story.screenplay.write",
        SCREENPLAY_PROMPT_V1,
        output_schema=SCREENPLAY_TEXT_SPEC,
        output_format=OUTPUT_FORMAT_TEXT,
        system="You are the WindAgent screenwriter.",
        max_tokens=4000,
        max_output_chars=30_000,
        description="Generate canonical screenplay TEXT (legacy; structured JSON at B6).",
    )
)
register_prompt(
    _legacy_entry(
        "story.continuation.continue",
        CONTINUATION_PROMPT_V1,
        output_schema=CONTINUATION_TEXT_SPEC,
        output_format=OUTPUT_FORMAT_TEXT,
        system="You are the WindAgent screenwriter (continuation).",
        max_tokens=3000,
        max_output_chars=20_000,
        description="Continue a screenplay in canonical text format (legacy; B6/B7).",
    )
)

__all__ = [
    "PROMPT_SCHEMA_VERSION",
    "OUTPUT_FORMAT_JSON",
    "OUTPUT_FORMAT_TEXT",
    "SafetyConstraints",
    "StoryPromptEntry",
    "STORY_PROMPT_REGISTRY",
    "register_prompt",
    "prompt_for",
    "registered_prompt_ids",
    "prompt_manifest",
    "validate_registry_invariants",
]
