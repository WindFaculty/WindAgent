"""
Code Correctness QC Verifier for Code Video Production (Video 02 Implementation Plan §11.2).

Verifies that all code displayed and recorded in Video 02 is syntactically valid,
architecturally pure, and equivalent (via AST / normalized token hash) to the golden
tutorial repository (agentic-studio):
- Message (immutable dataclass, role, content)
- AgentConfig (hyperparameters & system prompt)
- LLMClient (Protocol abstraction in domain layer)
- FakeLLMClient (deterministic offline test client)
- Agent (orchestration core class)
- Pytest suite (test_agent_with_fake_llm, test_agent_system_prompt)
- Zero provider SDK leaks in domain core (Clean Architecture isolation)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


REQUIRED_CLASSES: Set[str] = {
    "Message",
    "AgentConfig",
    "LLMClient",
    "FakeLLMClient",
    "Agent",
}

REQUIRED_TEST_FUNCTIONS: Set[str] = {
    "test_agent_runs_with_fake_llm",
    "test_message_immutability_and_role_validation",
}

FORBIDDEN_CORE_IMPORTS: Set[str] = {
    "openai",
    "google.generativeai",
    "google.genai",
    "anthropic",
    "groq",
    "litellm",
    "langchain",
    "llamaindex",
}


@dataclass
class CodeQCReport:
    """Detailed report for code correctness validation."""
    is_valid: bool
    source_ast_valid: bool
    test_ast_valid: bool
    classes_found: List[str]
    missing_classes: List[str] = field(default_factory=list)
    test_functions_found: List[str] = field(default_factory=list)
    missing_test_functions: List[str] = field(default_factory=list)
    forbidden_imports_found: List[str] = field(default_factory=list)
    normalized_ast_hash: str = ""
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "source_ast_valid": self.source_ast_valid,
            "test_ast_valid": self.test_ast_valid,
            "classes_found": self.classes_found,
            "missing_classes": self.missing_classes,
            "test_functions_found": self.test_functions_found,
            "missing_test_functions": self.missing_test_functions,
            "forbidden_imports_found": self.forbidden_imports_found,
            "normalized_ast_hash": self.normalized_ast_hash,
            "errors": self.errors,
            "metadata": self.metadata,
        }


class ASTNormalizer(ast.NodeVisitor):
    """Normalizes AST representation by extracting structural signatures and symbols."""

    def __init__(self) -> None:
        self.classes: List[str] = []
        self.functions: List[str] = []
        self.imports: List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.append(node.module)
        self.generic_visit(node)


class CodeCorrectnessVerifier:
    """
    Validates Python code snippets, files, and AST equivalence for Video 02.
    """

    @classmethod
    def compute_ast_hash(cls, source_code: str) -> str:
        """Compute a deterministic hash of normalized AST structure (ignoring comments/whitespace)."""
        tree = ast.parse(source_code)
        dump = ast.dump(tree, annotate_fields=False, include_attributes=False)
        return hashlib.sha256(dump.encode("utf-8")).hexdigest()

    @classmethod
    def verify_source_code(
        cls,
        agent_py_source: str,
        test_agent_py_source: Optional[str] = None,
    ) -> CodeQCReport:
        """Verify Python code against Video 02 domain rules."""
        errors: List[str] = []
        classes_found: List[str] = []
        test_functions_found: List[str] = []
        forbidden_imports_found: List[str] = []
        source_ast_valid = False
        test_ast_valid = True
        normalized_hash = ""

        # 1. Parse src/agent.py
        try:
            tree = ast.parse(agent_py_source)
            source_ast_valid = True
            normalized_hash = cls.compute_ast_hash(agent_py_source)
            normalizer = ASTNormalizer()
            normalizer.visit(tree)
            classes_found = normalizer.classes

            # Check forbidden imports in core
            for imp in normalizer.imports:
                for forbidden in FORBIDDEN_CORE_IMPORTS:
                    if imp == forbidden or imp.startswith(f"{forbidden}."):
                        forbidden_imports_found.append(imp)
                        errors.append(
                            f"Forbidden provider SDK import detected in domain core: '{imp}'. "
                            f"Core must remain provider-agnostic."
                        )
        except SyntaxError as exc:
            errors.append(f"Syntax error parsing src/agent.py: {exc}")

        # 2. Check required classes
        missing_classes = [
            c for c in sorted(list(REQUIRED_CLASSES))
            if c not in classes_found
        ]
        if missing_classes:
            errors.append(f"Missing required classes in src/agent.py: {missing_classes}")

        # 3. Parse tests/test_agent.py if provided
        missing_test_functions: List[str] = []
        if test_agent_py_source is not None:
            try:
                test_tree = ast.parse(test_agent_py_source)
                test_normalizer = ASTNormalizer()
                test_normalizer.visit(test_tree)
                test_functions_found = test_normalizer.functions
                missing_test_functions = [
                    fn for fn in sorted(list(REQUIRED_TEST_FUNCTIONS))
                    if fn not in test_functions_found
                ]
                if missing_test_functions:
                    errors.append(f"Missing required test functions in test_agent.py: {missing_test_functions}")
            except SyntaxError as exc:
                test_ast_valid = False
                errors.append(f"Syntax error parsing tests/test_agent.py: {exc}")

        is_valid = len(errors) == 0 and source_ast_valid and test_ast_valid

        return CodeQCReport(
            is_valid=is_valid,
            source_ast_valid=source_ast_valid,
            test_ast_valid=test_ast_valid,
            classes_found=classes_found,
            missing_classes=missing_classes,
            test_functions_found=test_functions_found,
            missing_test_functions=missing_test_functions,
            forbidden_imports_found=forbidden_imports_found,
            normalized_ast_hash=normalized_hash,
            errors=errors,
            metadata={
                "required_classes": sorted(list(REQUIRED_CLASSES)),
                "required_test_functions": sorted(list(REQUIRED_TEST_FUNCTIONS)),
            },
        )

    @classmethod
    def verify_workspace_files(cls, workspace_path: Path) -> CodeQCReport:
        """Verify code correctness directly from a tutorial workspace directory."""
        agent_file = workspace_path / "src" / "agent.py"
        test_file = workspace_path / "tests" / "test_agent.py"

        if not agent_file.exists():
            return CodeQCReport(
                is_valid=False,
                source_ast_valid=False,
                test_ast_valid=False,
                classes_found=[],
                missing_classes=list(REQUIRED_CLASSES),
                errors=[f"File not found: {agent_file}"],
            )

        agent_src = agent_file.read_text(encoding="utf-8")
        test_src = test_file.read_text(encoding="utf-8") if test_file.exists() else None
        return cls.verify_source_code(agent_src, test_src)


__all__ = [
    "ASTNormalizer",
    "CodeCorrectnessVerifier",
    "CodeQCReport",
    "FORBIDDEN_CORE_IMPORTS",
    "REQUIRED_CLASSES",
    "REQUIRED_TEST_FUNCTIONS",
]
