"""Privacy scan for Live Record plans (ban_ke_hoach_v1.md Sections 23 + 33).

Preflight invariant: the Start button stays disabled until the frozen
preparation content is proven free of secrets. The scan runs over every text
surface that will be visible or executed during a take:

- ``payload_bundles``   → typed/pasted code and command lines;
- ``scenes[].narration_text`` / titles → teleprompter + plan summary sent to Gemini;
- action metadata       → target_file / command_ref / browser_semantic_target.

Detection layers:
1. exact-match against configured provider credentials (values resolved by the
   application service — raw keys never appear in findings);
2. high-signal regex patterns for common credential formats.

Findings are masked: only the first 4 characters plus the length are kept.
The report is fail-closed — any finding blocks recording.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

# ─── High-signal credential patterns ─────────────────────────────────────────

SECRET_PATTERNS: Sequence[tuple[str, re.Pattern[str]]] = (
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    ("openai_api_key", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("anthropic_api_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{30,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("generic_secret_assignment", re.compile(
        r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*['\"]?[^\s'\"]{8,}"
    )),
)

MIN_EXACT_MATCH_LENGTH = 8


@dataclass(frozen=True)
class PrivacyFinding:
    """One detected secret — always masked, never carrying the raw value."""

    location: str
    kind: str
    masked_preview: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "location": self.location,
            "kind": self.kind,
            "masked_preview": self.masked_preview,
        }


@dataclass(frozen=True)
class PrivacyScanReport:
    status: str  # PASS | BLOCKED
    findings: List[PrivacyFinding] = field(default_factory=list)
    scanned_locations: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "ok": self.ok,
            "findings": [f.to_dict() for f in self.findings],
            "scanned_locations": self.scanned_locations,
        }


def mask_secret(value: str) -> str:
    """Keep only a short non-reversible preview of a secret."""
    clean = (value or "").strip()
    if len(clean) <= 4:
        return "***"
    return f"{clean[:4]}…({len(clean)} chars)"


def _scan_text(location: str, text: str, extra_values: Sequence[str], findings: List[PrivacyFinding]) -> None:
    if not text or not text.strip():
        return
    for kind, pattern in SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append(
                PrivacyFinding(location=location, kind=kind, masked_preview=mask_secret(match.group(0)))
            )
    lowered = text.lower()
    for secret in extra_values:
        candidate = (secret or "").strip()
        if len(candidate) < MIN_EXACT_MATCH_LENGTH:
            continue
        if candidate.lower() in lowered:
            findings.append(
                PrivacyFinding(location=location, kind="configured_credential", masked_preview=mask_secret(candidate))
            )


def scan_live_record_plan(
    *,
    payload_bundles: Dict[str, str],
    scenes: Iterable[Any],
    actions: Iterable[Any],
    extra_secret_values: Optional[Sequence[str]] = None,
) -> PrivacyScanReport:
    """Scan one LiveExecutionPlan-shaped aggregate for embedded secrets."""
    extras = list(extra_secret_values or [])
    findings: List[PrivacyFinding] = []
    scanned = 0

    for action_id, payload in (payload_bundles or {}).items():
        scanned += 1
        _scan_text(f"payload_bundles[{action_id}]", payload or "", extras, findings)

    for scene in scenes or []:
        scene_id = getattr(scene, "scene_id", "?")
        narration = getattr(scene, "narration_text", None)
        if narration:
            scanned += 1
            _scan_text(f"scenes[{scene_id}].narration_text", narration, extras, findings)
        title = getattr(scene, "title", "")
        if title:
            scanned += 1
            _scan_text(f"scenes[{scene_id}].title", title, extras, findings)

    for action in actions or []:
        action_id = getattr(action, "action_id", "?")
        for field_name in ("target_file", "command_ref", "browser_semantic_target"):
            value = getattr(action, field_name, None)
            if value:
                scanned += 1
                _scan_text(f"actions[{action_id}].{field_name}", value, extras, findings)

    return PrivacyScanReport(
        status="BLOCKED" if findings else "PASS",
        findings=findings,
        scanned_locations=scanned,
    )


__all__ = [
    "PrivacyFinding",
    "PrivacyScanReport",
    "SECRET_PATTERNS",
    "mask_secret",
    "scan_live_record_plan",
]
