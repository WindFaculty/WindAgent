"""
Automated Secret Scanner for Code Video Recording Pipeline (Phase 9).

Performs strict static and dynamic analysis to guarantee that NO sensitive credentials,
real API keys, private tokens, or connection strings leak into code video recordings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Pattern, Sequence, Set, Tuple


@dataclass(frozen=True)
class SecretPattern:
    """Regex pattern rule for detecting sensitive secrets."""
    name: str
    regex: Pattern[str]
    description: str
    severity: str = "CRITICAL"


@dataclass
class SecretExposureMatch:
    """Detailed match information for a detected secret violation."""
    pattern_name: str
    line_number: int
    redacted_snippet: str
    severity: str
    context: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_name": self.pattern_name,
            "line_number": self.line_number,
            "redacted_snippet": self.redacted_snippet,
            "severity": self.severity,
            "context": self.context,
        }


@dataclass
class SecretScanResult:
    """Aggregate result from a secret scanning operation."""
    is_clean: bool
    matches: List[SecretExposureMatch] = field(default_factory=list)
    scanned_items_count: int = 0
    scan_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_clean": self.is_clean,
            "violation_count": len(self.matches),
            "matches": [m.to_dict() for m in self.matches],
            "scanned_items_count": self.scanned_items_count,
            "scan_timestamp": self.scan_timestamp,
        }


class SecretScanner:
    """
    Scans code snippets, terminal commands, outputs, and frame metadata for sensitive data.
    """

    # Prohibited patterns matching actual secret formats
    PROHIBITED_PATTERNS: List[SecretPattern] = [
        SecretPattern(
            name="ANTHROPIC_API_KEY_LIVE",
            regex=re.compile(r"sk-ant-(?:api[0-9]{2}-)?[A-Za-z0-9_\-]{20,}", re.IGNORECASE),
            description="Real Anthropic Claude API Key",
        ),
        SecretPattern(
            name="OPENAI_API_KEY_LIVE",
            regex=re.compile(r"sk-(?!ant-)(?:proj-)?[A-Za-z0-9_\-]{24,}", re.IGNORECASE),
            description="Real OpenAI API Key structure with excessive token entropy",
        ),
        SecretPattern(
            name="GENERIC_BEARER_TOKEN",
            regex=re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{30,}", re.IGNORECASE),
            description="Live Authorization Bearer Token",
        ),
        SecretPattern(
            name="AWS_ACCESS_KEY",
            regex=re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}"),
            description="Live AWS Access Key ID",
        ),
        SecretPattern(
            name="PRIVATE_KEY_BLOCK",
            regex=re.compile(r"-----BEGIN (?:[A-Z0-9_-]+\s+)*PRIVATE KEY-----"),
            description="Cryptographic Private Key Block",
        ),
        SecretPattern(
            name="DATABASE_URI_WITH_CREDS",
            regex=re.compile(r"(?:postgres|mysql|mongodb|redis):\/\/[a-zA-Z0-9_\-]+:[a-zA-Z0-9_\-]+@[a-zA-Z0-9_\-\.]+"),
            description="Database URI with cleartext credentials",
        ),
    ]


    # Whitelisted placeholder strings that are explicitly allowed in video demonstrations
    ALLOWED_PLACEHOLDERS: Set[str] = {
        "sk-...",
        "sk-... ✕",
        "sk-placeholder",
        "sk-proj-placeholder",
        "sk-dummy-key-for-testing",
        "your-api-key-here",
        "your_api_key_here",
        "your_openai_api_key_here",
        "your-openai-api-key",
        "test-api-key",
        "mock-key",
        "fake-key",
        "OPENAI_API_KEY=your_api_key_here",
    }

    def __init__(self, additional_patterns: Optional[List[SecretPattern]] = None) -> None:
        self.patterns = list(self.PROHIBITED_PATTERNS)
        if additional_patterns:
            self.patterns.extend(additional_patterns)

    def is_placeholder(self, token: str) -> bool:
        """Check if matched token is a benign educational placeholder."""
        token_clean = token.strip().lower()
        for placeholder in self.ALLOWED_PLACEHOLDERS:
            if placeholder.lower() in token_clean or token_clean in placeholder.lower():
                return True
        if "placeholder" in token_clean or "example" in token_clean or "dummy" in token_clean:
            return True
        return False

    def scan_text(self, text: str, context_label: str = "") -> List[SecretExposureMatch]:
        """
        Scan a block of text for secret pattern violations.
        """
        matches: List[SecretExposureMatch] = []
        if not text:
            return matches

        lines = text.splitlines()
        for line_idx, line in enumerate(lines, start=1):
            for pat in self.patterns:
                for match in pat.regex.finditer(line):
                    matched_str = match.group(0)
                    if self.is_placeholder(matched_str):
                        continue

                    # Redact middle characters for safe reporting
                    if len(matched_str) > 8:
                        redacted = matched_str[:4] + "*" * (len(matched_str) - 8) + matched_str[-4:]
                    else:
                        redacted = "****"

                    matches.append(
                        SecretExposureMatch(
                            pattern_name=pat.name,
                            line_number=line_idx,
                            redacted_snippet=redacted,
                            severity=pat.severity,
                            context=context_label or f"Line {line_idx}",
                        )
                    )
        return matches

    def scan_files(self, files_map: Dict[str, str]) -> SecretScanResult:
        """
        Scan a collection of filename -> text content mappings.
        """
        all_matches: List[SecretExposureMatch] = []
        for filename, content in files_map.items():
            file_matches = self.scan_text(content, context_label=f"File: {filename}")
            all_matches.extend(file_matches)

        return SecretScanResult(
            is_clean=len(all_matches) == 0,
            matches=all_matches,
            scanned_items_count=len(files_map),
        )

    def scan_pass_context(
        self,
        pass_id: str,
        files_map: Optional[Dict[str, str]] = None,
        terminal_history: Optional[List[str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> SecretScanResult:
        """
        Scan complete runtime context for a recording pass.
        """
        all_matches: List[SecretExposureMatch] = []
        items_count = 0

        if files_map:
            for fn, content in files_map.items():
                items_count += 1
                all_matches.extend(self.scan_text(content, context_label=f"Pass {pass_id} File {fn}"))

        if terminal_history:
            for idx, cmd in enumerate(terminal_history):
                items_count += 1
                all_matches.extend(self.scan_text(cmd, context_label=f"Pass {pass_id} Terminal #{idx}"))

        if env_vars:
            for k, v in env_vars.items():
                items_count += 1
                if not self.is_placeholder(v):
                    # Also scan value
                    all_matches.extend(self.scan_text(v, context_label=f"Pass {pass_id} Env {k}"))

        return SecretScanResult(
            is_clean=len(all_matches) == 0,
            matches=all_matches,
            scanned_items_count=items_count,
        )
