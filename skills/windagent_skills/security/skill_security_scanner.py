"""Static AST and Secret Security Scanner for Skills (Phase 12 — ban_ke_hoach_v1 §18, §29).

Enforces security invariants before any executable skill can be eligible for promotion:
1. AST Static Analysis:
   - Forbids dynamic code execution: eval, exec, compile, built-in import mechanisms.
   - Forbids namespace introspection escaping: __subclasses__(), __globals__, __code__.
   - Forbids dangerous OS/process calls: subprocess, os.system(), os.popen(), os.exec*(), os.kill().
   - Forbids raw socket networking or ctypes memory manipulations.
2. Secret & Credential Detection:
   - Identifies hardcoded API tokens, AWS keys, private keys, authorization headers.
3. Computes comprehensive SkillSecurityAuditResult with violation attribution and risk scoring.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, List, Optional, Set

from windagent_core.domain.skill_evolution import SkillSecurityAuditResult


FORBIDDEN_CALLS: Set[str] = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "globals",
    "locals",
}

FORBIDDEN_MODULES: Set[str] = {
    "subprocess",
    "ctypes",
    "socket",
    "pty",
    "commands",
    "pdb",
    "telnetlib",
    "winreg",
}

FORBIDDEN_OS_ATTRIBUTES: Set[str] = {
    "system",
    "popen",
    "spawnl",
    "spawnle",
    "spawnlp",
    "spawnlpe",
    "spawnv",
    "spawnve",
    "spawnvp",
    "spawnvpe",
    "execl",
    "execle",
    "execlp",
    "execlpe",
    "execv",
    "execve",
    "execvp",
    "execvpe",
    "kill",
    "killpg",
}

FORBIDDEN_DUNDERS: Set[str] = {
    "__subclasses__",
    "__globals__",
    "__code__",
    "__closure__",
    "__bases__",
}

# Regex patterns for detecting embedded credentials/secrets
SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key"),
    (re.compile(r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----"), "Private Key"),
    (re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"), "OpenAI/API Secret Token"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "GitHub Personal Access Token"),
    (re.compile(r"(?i)(password|secret|api_key|token)\s*=\s*['\"][A-Za-z0-9_\-\.]{16,}['\"]"), "Hardcoded Secret Assignment"),
]


class _SecurityASTVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: List[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Check direct call names (e.g. eval(), exec())
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                self.violations.append(
                    f"Forbidden dynamic execution call [{node.func.id}()] at line {node.lineno}."
                )

        # Check attribute calls (e.g. os.system(), obj.__subclasses__())
        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name in FORBIDDEN_DUNDERS:
                self.violations.append(
                    f"Forbidden dunder attribute access [{attr_name}] at line {node.lineno}."
                )
            if isinstance(node.func.value, ast.Name):
                module_name = node.func.value.id
                if module_name == "os" and attr_name in FORBIDDEN_OS_ATTRIBUTES:
                    self.violations.append(
                        f"Forbidden OS system/process execution [os.{attr_name}()] at line {node.lineno}."
                    )

        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            base_pkg = alias.name.split(".")[0]
            if base_pkg in FORBIDDEN_MODULES:
                self.violations.append(
                    f"Forbidden module import [{alias.name}] at line {node.lineno}."
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            base_pkg = node.module.split(".")[0]
            if base_pkg in FORBIDDEN_MODULES:
                self.violations.append(
                    f"Forbidden module import from [{node.module}] at line {node.lineno}."
                )
            if base_pkg == "os":
                for alias in node.names:
                    if alias.name in FORBIDDEN_OS_ATTRIBUTES:
                        self.violations.append(
                            f"Forbidden OS execution import [from os import {alias.name}] at line {node.lineno}."
                        )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in FORBIDDEN_DUNDERS:
            self.violations.append(
                f"Forbidden dunder introspection attribute [{node.attr}] at line {node.lineno}."
            )
        self.generic_visit(node)


class SkillSecurityScanner:
    """Performs static security analysis and secret detection on skill source code and manifests."""

    def scan_code(self, source_code: Optional[str]) -> tuple[bool, List[str]]:
        """Scans Python source code via AST analysis.
        Returns (ast_scan_passed, violations).
        """
        if not source_code or not source_code.strip():
            return True, []

        violations: List[str] = []
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            return False, [f"Python syntax error during security scan: {e}"]

        visitor = _SecurityASTVisitor()
        visitor.visit(tree)
        violations.extend(visitor.violations)

        return len(violations) == 0, violations

    def scan_secrets(self, content: str) -> tuple[bool, List[str]]:
        """Scans string content for hardcoded secrets / credentials.
        Returns (secret_scan_passed, violations).
        """
        if not content:
            return True, []

        violations: List[str] = []
        for pattern, desc in SECRET_PATTERNS:
            matches = pattern.findall(content)
            if matches:
                violations.append(f"Detected potential secret or credential pattern [{desc}].")

        return len(violations) == 0, violations

    def audit(
        self,
        source_code: Optional[str] = None,
        manifest_dict: Optional[Dict[str, Any]] = None,
        dependency_passed: bool = True,
        permission_passed: bool = True,
        dependency_violations: Optional[List[str]] = None,
        permission_violations: Optional[List[str]] = None,
    ) -> SkillSecurityAuditResult:
        """Executes a full security audit combining AST checks, secret checks,
        and externally verified dependency/permission results.
        """
        all_violations: List[str] = []

        # 1. AST Scan
        ast_passed, ast_violations = self.scan_code(source_code)
        all_violations.extend(ast_violations)

        # 2. Secret Scan (code + manifest prompt/description)
        combined_text = (source_code or "") + " "
        if manifest_dict:
            combined_text += f"{manifest_dict.get('description', '')} {manifest_dict.get('prompt_template', '')}"

        secret_passed, secret_violations = self.scan_secrets(combined_text)
        all_violations.extend(secret_violations)

        # 3. Add external dependency & permission violations
        if dependency_violations:
            all_violations.extend(dependency_violations)
        if permission_violations:
            all_violations.extend(permission_violations)

        # Calculate risk score
        risk_score = 0.0
        if ast_violations:
            risk_score += 0.5
        if secret_violations:
            risk_score += 0.4
        if not permission_passed:
            risk_score += 0.3
        if not dependency_passed:
            risk_score += 0.2
        risk_score = min(1.0, risk_score)

        overall_passed = (
            ast_passed
            and secret_passed
            and dependency_passed
            and permission_passed
            and len(all_violations) == 0
        )

        return SkillSecurityAuditResult(
            passed=overall_passed,
            ast_scan_passed=ast_passed,
            permission_audit_passed=permission_passed,
            dependency_validation_passed=dependency_passed,
            secret_scan_passed=secret_passed,
            violations=all_violations,
            risk_score=risk_score,
            details={
                "ast_violation_count": len(ast_violations),
                "secret_violation_count": len(secret_violations),
                "has_executable_code": bool(source_code and source_code.strip()),
            },
        )


__all__ = ["SkillSecurityScanner"]
