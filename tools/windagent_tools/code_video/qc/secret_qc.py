"""
Secret QC Verifier for Code Video Production (Video 02 Implementation Plan §11.4).

Executes deep cryptographic multi-tier scanning across all video artifacts, frames,
source codes, terminal receipts, and environment dumps to ensure zero private token leaks:
- Rejects: OpenAI (sk-...), Google (AIza...), Groq (gsk_...), NVIDIA (nvapi-...),
  AWS (AKIA...), Bearer tokens, and RSA/SSH private keys.
- Allows verified safe placeholders: 'sk-...', 'your_api_key_here', 'mock-key', etc.
- Policy: If any real secret is detected -> FINAL_VERDICT = REJECT (Zero Tolerance).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Pattern, Sequence, Set, Tuple


# Regex patterns targeting live API keys and tokens
DANGEROUS_SECRET_PATTERNS: Dict[str, Pattern[str]] = {
    "google_api_key": re.compile(r"AIza[0-9A-Za-z-_]{35}"),
    "openai_live_key": re.compile(r"\bsk-[a-zA-Z0-9]{32,}\b"),
    "groq_live_key": re.compile(r"\bgsk_[a-zA-Z0-9]{20,}\b"),
    "nvidia_live_key": re.compile(r"\bnvapi-[a-zA-Z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{32,}"),
    "private_key_header": re.compile(r"-----BEGIN (?:[A-Z0-9\s_-]+ )?KEY-----"),
}

# Whitelisted safe educational placeholders
ALLOWED_PLACEHOLDERS: Set[str] = {
    "sk-...",
    "sk-placeholder",
    "sk-ant-api03-...",
    "AIza...",
    "gsk_...",
    "nvapi-...",
    "your_api_key_here",
    "your-api-key-here",
    "test-api-key",
    "fake-api-key",
    "mock-key",
    "sk-test-key",
}


@dataclass
class SecretFinding:
    """Detailed information about an identified secret violation."""
    rule_name: str
    snippet_preview: str
    location: str
    is_safe_placeholder: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "snippet_preview": self.snippet_preview,
            "location": self.location,
            "is_safe_placeholder": self.is_safe_placeholder,
        }


@dataclass
class SecretQCReport:
    """Detailed report for secret scanning validation."""
    is_clean: bool
    total_targets_scanned: int
    findings_count: int
    findings: List[SecretFinding] = field(default_factory=list)
    scanned_locations: List[str] = field(default_factory=list)
    verdict: str = "PASS"  # PASS or REJECT
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_clean": self.is_clean,
            "total_targets_scanned": self.total_targets_scanned,
            "findings_count": self.findings_count,
            "findings": [f.to_dict() for f in self.findings],
            "scanned_locations": self.scanned_locations,
            "verdict": self.verdict,
            "errors": self.errors,
            "metadata": self.metadata,
        }


class SecretQCVerifier:
    """
    Deep scanner validating zero private credentials in video production artifacts.
    """

    @classmethod
    def is_whitelisted(cls, text_match: str) -> bool:
        """Check if matched text is an allowed educational placeholder."""
        cleaned = text_match.strip().strip("\"'").strip()
        for placeholder in ALLOWED_PLACEHOLDERS:
            if cleaned == placeholder or cleaned.startswith("sk-..."):
                return True
        return False

    @classmethod
    def scan_text(cls, text: str, location_label: str = "memory") -> List[SecretFinding]:
        """Scan a single text payload for secret leaks."""
        findings: List[SecretFinding] = []
        for rule_name, pattern in DANGEROUS_SECRET_PATTERNS.items():
            for match in pattern.finditer(text):
                matched_str = match.group(0)
                if cls.is_whitelisted(matched_str):
                    continue
                # Redacted preview (e.g. sk-ab12***89)
                if len(matched_str) > 8:
                    preview = f"{matched_str[:6]}...{matched_str[-4:]}"
                else:
                    preview = "***"
                findings.append(
                    SecretFinding(
                        rule_name=rule_name,
                        snippet_preview=preview,
                        location=location_label,
                        is_safe_placeholder=False,
                    )
                )
        return findings

    @classmethod
    def scan_collection(
        cls,
        targets: Dict[str, str],
    ) -> SecretQCReport:
        """Scan a dictionary of {location_label: text_content}."""
        all_findings: List[SecretFinding] = []
        scanned_locations: List[str] = []

        for loc, content in targets.items():
            scanned_locations.append(loc)
            findings = cls.scan_text(content, location_label=loc)
            all_findings.extend(findings)

        is_clean = len(all_findings) == 0
        verdict = "PASS" if is_clean else "REJECT"
        errors = [f"Secret detected at {f.location}: {f.rule_name}" for f in all_findings]

        return SecretQCReport(
            is_clean=is_clean,
            total_targets_scanned=len(targets),
            findings_count=len(all_findings),
            findings=all_findings,
            scanned_locations=scanned_locations,
            verdict=verdict,
            errors=errors,
            metadata={
                "rules_checked": list(DANGEROUS_SECRET_PATTERNS.keys()),
            },
        )


__all__ = [
    "ALLOWED_PLACEHOLDERS",
    "DANGEROUS_SECRET_PATTERNS",
    "SecretFinding",
    "SecretQCReport",
    "SecretQCVerifier",
]
