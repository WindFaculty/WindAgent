"""
PromptSanitizer (Phase 11) — trust boundary between source data and the
compiled prompt (plan 03 §24.4).

Rules enforced before any prompt is published:
- local path / profile markers are REDACTED and BLOCK compilation;
- secret markers (api keys, tokens, passwords, bearer) are REDACTED and BLOCK
  compilation;
- injection-suspect text (instruction overrides, script tags, template
  syntax) is flagged and BLOCKS compilation;
- control / escape Unicode is stripped (non-blocking finding);
- a hard token/length cap produces a BLOCKING finding (plan §29: prompt too
  long -> explicit compile failure, never silent truncation of the request);
- only allow-listed fields reach the prompt — the compiler never reads
  instructions from EXIF, web page text, alt text, or asset metadata.

Every finding is recorded redacted (never logged raw), and the sanitizer never
emits partial raw content.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import List

from windagent_core.domain.video_production.enums import IssueSeverity
from windagent_core.domain.video_production.ids import PromptSecurityFindingId

# Local path / profile markers (Windows drive paths, POSIX home/tmp/var/etc).
_LOCAL_PATH_PATTERNS = [
    re.compile(r"(?i)\b[a-z]:[\\/][^\s;,\"]+"),
    re.compile(r"(?i)\b(?:/home|/Users|/tmp|/var|/etc|/usr|/opt|/root)/[^\s;,\"]+"),
    re.compile(r"(?i)\b~[\\/][^\s;,\"]+"),
]

# Secret markers — the VALUE is redacted, the key name is preserved.
_SECRET_VALUE_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?key|secret|password|passwd)\s*[=:]\s*\S+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
]

# Injection-suspect text (plan §24.4: instructions must never come from
# untrusted metadata or arbitrary model output into the prompt).
_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore (all |the )?(previous|above) instructions"),
    re.compile(r"(?i)disregard (all |the )?(previous|above)"),
    re.compile(r"(?i)system prompt"),
    re.compile(r"(?i)you are now (?:a |an )?(?:helpful )?assistant"),
    re.compile(r"<\s*script[\s>]|<\s*/\s*script\s*>"),
    re.compile(r"\{\{\s*[^}]*\}\}"),  # template injection
]

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

DEFAULT_MAX_PROMPT_CHARS = 6000
REDACTION = "[REDACTED]"

# Finding kind -> severity mapping.
_KIND_SEVERITY = {
    "local_path": IssueSeverity.BLOCKING,
    "secret_marker": IssueSeverity.BLOCKING,
    "injection_suspect": IssueSeverity.BLOCKING,
    "oversized": IssueSeverity.BLOCKING,
    "control_unicode": IssueSeverity.WARNING,
}
_BLOCKING_KINDS = {
    kind
    for kind, severity in _KIND_SEVERITY.items()
    if severity == IssueSeverity.BLOCKING
}


@dataclass(frozen=True)
class SanitizedResult:
    """Sanitized text + typed findings (recorded redacted)."""

    text: str
    kinds: List[str] = field(default_factory=list)  # finding kinds, in order
    finding_ids: List[PromptSecurityFindingId] = field(default_factory=list)
    char_count: int = 0
    blocked_kinds: List[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.blocked_kinds)


class PromptSanitizer:
    """Deterministic prompt sanitization with typed findings."""

    def __init__(
        self,
        *,
        id_factory=None,
        max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS,
    ) -> None:
        self._id_factory = id_factory
        self.max_prompt_chars = max_prompt_chars

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def sanitize(
        self,
        text: str,
        *,
        field: str = "",
        allow_overflow: bool = False,
    ) -> SanitizedResult:
        """Sanitize one text field. `allow_overflow` disables the length gate
        (used for golden fixtures that must compile even when verbose);
        production compilation keeps the gate ON (blocking)."""
        kinds: List[str] = []
        finding_ids: List[PromptSecurityFindingId] = []
        blocked_kinds: List[str] = []

        def _note(kind: str) -> None:
            kinds.append(kind)
            finding_ids.append(self._finding(kind, field))
            if kind in _BLOCKING_KINDS:
                blocked_kinds.append(kind)

        cleaned = _strip_control(text)
        if len(cleaned) != len(text):
            _note("control_unicode")
        cleaned, path_found = _redact_paths(cleaned)
        if path_found:
            _note("local_path")
        cleaned, secret_found = _redact_secrets(cleaned)
        if secret_found:
            _note("secret_marker")
        if _has_injection(cleaned):
            _note("injection_suspect")
        if len(cleaned) > self.max_prompt_chars and not allow_overflow:
            _note("oversized")

        return SanitizedResult(
            text=cleaned,
            kinds=kinds,
            finding_ids=finding_ids,
            char_count=len(cleaned),
            blocked_kinds=blocked_kinds,
        )

    def _finding(self, kind: str, field: str) -> PromptSecurityFindingId:
        seed = f"{kind}:{field}"
        if self._id_factory is not None:
            return self._id_factory.security_finding_id(seed)
        return PromptSecurityFindingId(
            "psf_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        )


def _strip_control(text: str) -> str:
    """Strip control / escape Unicode while preserving newline and tab."""
    return _CONTROL_CHARS.sub("", text)


def _redact_paths(text: str) -> tuple[str, bool]:
    found = False
    out = text
    for pattern in _LOCAL_PATH_PATTERNS:
        if pattern.search(out):
            found = True
        out = pattern.sub(REDACTION, out)
    return out, found


def _redact_secrets(text: str) -> tuple[str, bool]:
    found = False
    out = text
    for pattern in _SECRET_VALUE_PATTERNS:
        if pattern.search(out):
            found = True
        out = pattern.sub(REDACTION, out)
    return out, found


def _has_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


__all__ = ["PromptSanitizer", "SanitizedResult", "REDACTION"]
