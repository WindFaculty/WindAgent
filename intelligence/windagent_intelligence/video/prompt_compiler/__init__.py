"""
Phase 11 — Prompt Compiler (plan 03 §23-§24).

The `PromptCompiler` turns every bound `ShotSpecification` into a versioned,
sanitized, provider-safe `GenerationRequest` via the canonical 12-block prompt
template, a strict trust boundary (plan §24.4) and mode-specific required-input
validation (plan §24.3). Deterministic hashes (prompt + request, plan §24.5)
make every request reproducible and traceable. Fully deterministic — never
calls a provider.
"""

from windagent_intelligence.video.prompt_compiler.blocks import (
    PROMPT_TEMPLATE_VERSION,
    PromptBlockBuilder,
)
from windagent_intelligence.video.prompt_compiler.modes import (
    MODE_REQUIRED_INPUTS,
    ModeCompiler,
)
from windagent_intelligence.video.prompt_compiler.models import CompiledRequestReceipt
from windagent_intelligence.video.prompt_compiler.security import PromptSanitizer
from windagent_intelligence.video.prompt_compiler.service import (
    COMPILER_VERSION,
    PromptCompiler,
)

__all__ = [
    "PromptCompiler",
    "COMPILER_VERSION",
    "PromptBlockBuilder",
    "PROMPT_TEMPLATE_VERSION",
    "PromptSanitizer",
    "ModeCompiler",
    "MODE_REQUIRED_INPUTS",
    "CompiledRequestReceipt",
]
