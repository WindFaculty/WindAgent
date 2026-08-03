"""
Phase 11 — Prompt compiler result types (plan 03 §24).

`CompiledRequestReceipt` is the immutable result of `PromptCompiler.compile_all`:
the full set of versioned `GenerationRequest`s (one per shot) plus the typed
compiler issues and redacted security findings. A blocking issue means the set
was NOT published — the compiler raises `ValidationFailureError` instead of
returning a partial request set (fail closed, plan §24.2/§24.3/§24.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from windagent_core.domain.video_production.generation_job import GenerationRequest
from windagent_core.domain.video_production.prompt_compiler import (
    FlowGenerationSpecification,
    PromptCompilerIssue,
    PromptSecurityFinding,
)


@dataclass(frozen=True)
class CompiledRequestReceipt:
    """Result of prompt compilation — never a partial request set."""

    requests: List[GenerationRequest] = field(default_factory=list)
    specifications: List[FlowGenerationSpecification] = field(default_factory=list)
    issues: List[PromptCompilerIssue] = field(default_factory=list)
    security_findings: List[PromptSecurityFinding] = field(default_factory=list)
    compiler_version: str = "1.0.0"
    prompt_template_version: str = "1.0.0"

    @property
    def blocking_issues(self) -> List[PromptCompilerIssue]:
        return [i for i in self.issues if i.blocking]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requests": [
                {
                    "request_id": str(r.request_id),
                    "project_id": str(r.project_id),
                    "revision_id": str(r.revision_id),
                    "shot_id": str(r.shot_id),
                    "generation_mode": r.generation_mode.value,
                    "prompt_version": r.prompt_version,
                    "prompt_hash": r.prompt_hash,
                    "reference_hashes": list(r.reference_hashes),
                    "request_hash": r.request_hash,
                    "parameters": r.parameters,
                }
                for r in self.requests
            ],
            "specifications": [s.to_dict() for s in self.specifications],
            "issues": [i.to_dict() for i in self.issues],
            "security_findings": [f.to_dict() for f in self.security_findings],
            "compiler_version": self.compiler_version,
            "prompt_template_version": self.prompt_template_version,
        }


__all__ = ["CompiledRequestReceipt"]
