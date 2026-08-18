"""
Workspace Security Scanner for Tutorial Preflight Verification.

Enforces zero-secret exposure policies prior to video recording takes:
- Scans all files in workspace for API keys (AIza, sk-, gsk_, nvapi-, Bearer)
- Scans terminal logs and output receipts
- Enforces .gitignore rules protecting .env files
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from windagent_core.errors.exceptions import PermissionDeniedError
from windagent_tools.code_video.workspace.sandbox import TutorialWorkspace

LEAK_PATTERNS = [
    (re.compile(r"AIza[a-zA-Z0-9_-]{20,}"), "GOOGLE_API_KEY"),
    (re.compile(r"sk-[a-zA-Z0-9_-]{12,}"), "OPENAI_API_KEY"),
    (re.compile(r"gsk_[a-zA-Z0-9_-]{12,}"), "GROQ_API_KEY"),
    (re.compile(r"nvapi-[a-zA-Z0-9_-]{12,}"), "NVIDIA_API_KEY"),
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{12,}", re.IGNORECASE), "BEARER_TOKEN"),
    (
        re.compile(
            r"(api[_-]?key|secret|password|auth_token)\s*=\s*['\"][a-zA-Z0-9_\-\.]{12,}['\"]",
            re.IGNORECASE,
        ),
        "GENERIC_SECRET_ASSIGNMENT",
    ),
]


@dataclass(frozen=True)
class SecurityViolation:
    """Details of a single secret detection."""
    source: str
    line_number: Optional[int]
    pattern_type: str
    snippet: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "line_number": self.line_number,
            "pattern_type": self.pattern_type,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class SecurityScanReport:
    """Comprehensive report produced by WorkspaceSecretScanner."""
    is_clean: bool
    violations: List[SecurityViolation]
    scanned_files_count: int
    scanned_files: List[str]
    timestamp_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_clean": self.is_clean,
            "violation_count": len(self.violations),
            "violations": [v.to_dict() for v in self.violations],
            "scanned_files_count": self.scanned_files_count,
            "scanned_files": list(self.scanned_files),
            "timestamp_utc": self.timestamp_utc,
        }


class WorkspaceSecretScanner:
    """
    Automated security preflight scanner for tutorial code and logs.
    """

    def __init__(self, workspace: TutorialWorkspace) -> None:
        self.workspace = workspace

    def scan_text(self, text: str, source_label: str = "text") -> List[SecurityViolation]:
        """Scan raw string content for forbidden secret patterns."""
        violations: List[SecurityViolation] = []
        if not text:
            return violations

        lines = text.splitlines()
        for line_idx, line in enumerate(lines, start=1):
            for pattern, pat_name in LEAK_PATTERNS:
                matches = pattern.finditer(line)
                for match in matches:
                    matched_val = match.group(0)
                    # Mask snippet for safe reporting
                    masked_snippet = (
                        f"{matched_val[:4]}...[REDACTED]...{matched_val[-3:]}"
                        if len(matched_val) > 8
                        else "***REDACTED***"
                    )
                    violations.append(
                        SecurityViolation(
                            source=source_label,
                            line_number=line_idx,
                            pattern_type=pat_name,
                            snippet=masked_snippet,
                        )
                    )
        return violations

    def scan_workspace(self) -> SecurityScanReport:
        """
        Scan all files in the tutorial workspace root.
        """
        violations: List[SecurityViolation] = []
        scanned_files: List[str] = []

        if not self.workspace.exists():
            return SecurityScanReport(
                is_clean=True,
                violations=[],
                scanned_files_count=0,
                scanned_files=[],
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
            )

        # 1. Walk and scan all regular and hidden files (.env, .gitignore, etc.)
        for root, dirs, filenames in os.walk(self.workspace.workspace_root):
            if ".git" in dirs:
                dirs.remove(".git")
            if ".checkpoints" in dirs:
                dirs.remove(".checkpoints")
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            if ".pytest_cache" in dirs:
                dirs.remove(".pytest_cache")

            rel_root = Path(root).relative_to(self.workspace.workspace_root)
            for fname in filenames:
                rel_path = (rel_root / fname).as_posix()
                if rel_path.startswith("./"):
                    rel_path = rel_path[2:]
                scanned_files.append(rel_path)

                full_path = Path(root) / fname
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                    file_violations = self.scan_text(content, source_label=rel_path)
                    violations.extend(file_violations)
                except Exception:
                    pass

        # 2. Verify .gitignore ignores .env if .gitignore exists
        if self.workspace.file_exists(".gitignore"):
            gi_content = self.workspace.read_file(".gitignore")
            if ".env" not in gi_content.splitlines() and "\n.env\n" not in gi_content:
                violations.append(
                    SecurityViolation(
                        source=".gitignore",
                        line_number=None,
                        pattern_type="GITIGNORE_MISSING_ENV",
                        snippet="'.env' rule missing in .gitignore",
                    )
                )

        return SecurityScanReport(
            is_clean=len(violations) == 0,
            violations=violations,
            scanned_files_count=len(scanned_files),
            scanned_files=sorted(scanned_files),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )

    def enforce_clean_workspace(self) -> SecurityScanReport:
        """
        Scan workspace and raise PermissionDeniedError if any violation exists.
        """
        report = self.scan_workspace()
        if not report.is_clean:
            violation_details = "\n".join(
                f"- [{v.pattern_type}] in {v.source}:{v.line_number or '?'} ({v.snippet})"
                for v in report.violations
            )
            raise PermissionDeniedError(
                message=f"Workspace security preflight failed with {len(report.violations)} violation(s):\n{violation_details}",
                code="WINDAGENT_ERR_SECURITY_LEAK_DETECTED",
                details={"violation_count": len(report.violations)},
            )
        return report


import os
__all__ = ["SecurityViolation", "SecurityScanReport", "WorkspaceSecretScanner", "LEAK_PATTERNS"]
