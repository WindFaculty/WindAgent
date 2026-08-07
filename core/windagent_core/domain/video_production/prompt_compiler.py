"""
Phase 11 — Prompt compiler domain (plan 03 §23-§24).

Domain objects for turning a bound shot into a provider-safe, versioned
GenerationRequest:

- `PromptBlock` — one named, ordered block of the canonical prompt template
  (plan §24.2: PROJECT STYLE / IDENTITY / LOCATION / PROPS / SHOT COMPOSITION /
  ACTION / CAMERA / LIGHTING / CONTINUITY / DIALOGUE-AUDIO INTENT / DURATION /
  NEGATIVE CONSTRAINTS). Empty OPTIONAL blocks are dropped by rule; a missing
  REQUIRED block fails compilation.
- `CompiledPrompt` — the assembled, sanitized prompt with a deterministic
  `prompt_hash` tied to the template version.
- `PromptCompilerIssue` — typed, blocking-or-warning finding from compilation
  (missing required block, mode missing input, oversized prompt, forbidden
  content, unknown field, injection suspect).
- `PromptSecurityFinding` — a sanitization finding (path/secret/control char)
  recorded redacted; never logged raw.
- `compute_prompt_hash` / `compute_request_hash` — deterministic SHA-256 with
  the plan §24.5 inputs so identical inputs yield identical hashes and any
  change (reference, prompt version, parameter) yields a new hash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    IssueSeverity,
    PromptBlockType,
    PromptCompilerIssueCode,
)
from windagent_core.domain.video_production.ids import (
    CompiledPromptId,
    PromptBlockId,
    PromptCompilerIssueId,
    PromptSecurityFindingId,
    ShotId,
)


class PromptBlock(BaseModel):
    """One ordered block of the canonical prompt template (plan §24.2)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    block_id: PromptBlockId
    block_type: PromptBlockType
    content: str = ""
    required: bool = True
    order: int = Field(ge=1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": str(self.block_id),
            "block_type": self.block_type.value,
            "content": self.content,
            "required": self.required,
            "order": self.order,
        }


class CompiledPrompt(BaseModel):
    """Assembled, sanitized prompt for one shot (plan §24.2)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    prompt_id: CompiledPromptId
    shot_id: ShotId
    blocks: List[PromptBlock] = Field(default_factory=list)
    text: str = ""
    template_version: str = "1.0.0"
    prompt_hash: str = Field(min_length=64, max_length=64)
    total_chars: int = Field(ge=0, default=0)

    def block(self, block_type: PromptBlockType) -> Optional[PromptBlock]:
        for b in self.blocks:
            if b.block_type == block_type:
                return b
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_id": str(self.prompt_id),
            "shot_id": str(self.shot_id),
            "blocks": [b.to_dict() for b in self.blocks],
            "text": self.text,
            "template_version": self.template_version,
            "prompt_hash": self.prompt_hash,
            "total_chars": self.total_chars,
        }


class PromptCompilerIssue(BaseModel):
    """Typed finding from prompt compilation (plan §24.2-§24.5)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    issue_id: PromptCompilerIssueId
    code: PromptCompilerIssueCode
    severity: IssueSeverity = IssueSeverity.BLOCKING
    message: str = Field(min_length=1)
    blocking: bool = True
    shot_id: Optional[ShotId] = None
    block_type: Optional[PromptBlockType] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": str(self.issue_id),
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "blocking": self.blocking,
            "shot_id": str(self.shot_id) if self.shot_id else None,
            "block_type": self.block_type.value if self.block_type else None,
            "details": self.details,
        }


class PromptSecurityFinding(BaseModel):
    """Sanitization finding — recorded redacted, never logged raw (plan §24.4)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    finding_id: PromptSecurityFindingId
    kind: str  # "local_path" | "secret_marker" | "control_unicode" | "oversized"
    severity: IssueSeverity = IssueSeverity.WARNING
    message: str = Field(min_length=1)
    field: str = ""  # which block / source field carried the finding
    redacted: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": str(self.finding_id),
            "kind": self.kind,
            "severity": self.severity.value,
            "message": self.message,
            "field": self.field,
            "redacted": self.redacted,
        }


def compute_prompt_hash(
    *,
    blocks_payload: List[Dict[str, Any]],
    template_version: str,
) -> str:
    """Deterministic SHA-256 over the canonical block payload + template version."""
    canonical = json.dumps(
        {
            "template_version": template_version,
            "blocks": blocks_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_request_hash(
    *,
    project_id: object,
    revision_id: object,
    shot_id: object,
    compiler_version: str,
    prompt_template_version: str,
    prompt_hash: str,
    reference_hashes: List[str],
    parameters: Dict[str, Any],
    model_capability_constraints: Dict[str, Any],
) -> str:
    """Deterministic SHA-256 request hash (plan §24.5).

    Hash inputs: canonical shot spec + compiler version + prompt template
    version + reference hashes + model capability constraints + generation
    parameters. Same inputs -> same hash; any change -> new hash.
    """
    canonical = json.dumps(
        {
            "project_id": str(project_id),
            "revision_id": str(revision_id),
            "shot_id": str(shot_id),
            "compiler_version": compiler_version,
            "prompt_template_version": prompt_template_version,
            "prompt_hash": prompt_hash,
            "reference_hashes": sorted(set(reference_hashes)),
            "parameters": parameters,
            "model_capability_constraints": model_capability_constraints,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "PromptBlock",
    "CompiledPrompt",
    "PromptCompilerIssue",
    "PromptSecurityFinding",
    "compute_prompt_hash",
    "compute_request_hash",
]
