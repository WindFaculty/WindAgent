"""
Deterministic Repository Builder for Tutorial Workspaces.

Builds and scaffolds the standard repository layout for Video 02 (agentic-studio):
- src/__init__.py
- src/agent.py
- tests/__init__.py
- tests/test_agent.py
- .env.example
- .gitignore
- pyproject.toml
- README.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from windagent_core.errors.exceptions import ValidationError
from windagent_tools.code_video.workspace.sandbox import TutorialWorkspace

DEFAULT_GITIGNORE = """# Python byte-compiled files
__pycache__/
*.py[cod]
*$py.class

# Testing and coverage
.pytest_cache/
.coverage
htmlcov/

# Environment and secrets (NEVER COMMIT)
.env
.venv/
env/
venv/

# Distribution / packaging
dist/
build/
*.egg-info/
"""

DEFAULT_ENV_EXAMPLE = """# Agentic Studio Environment Template
# Copy this file to .env and configure your credentials.
# NEVER commit .env to version control.

PROVIDER_API_KEY=your_api_key_here
MODEL_NAME=gpt-4o-mini
TEMPERATURE=0.7
"""

DEFAULT_PYPROJECT_TOML = """[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "agentic-studio"
version = "0.1.0"
description = "A minimal AI Agent architecture built in Python"
readme = "README.md"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
"""

DEFAULT_README_MD = """# Agentic Studio (v0.1)

A clean, modular AI Agent implementation in Python.

## Architecture

```text
User ──> Agent ──> LLM ──> Answer
```

## Structure

```text
agentic-studio/
├── src/
│   ├── __init__.py
│   └── agent.py
├── tests/
│   ├── __init__.py
│   └── test_agent.py
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

## Running Tests

```bash
pytest
```
"""


class TutorialRepositoryBuilder:
    """
    Deterministic repository scaffolder and validator for tutorial workspaces.
    """

    REQUIRED_TUTORIAL_FILES: List[str] = [
        ".env.example",
        ".gitignore",
        "pyproject.toml",
        "README.md",
        "src/__init__.py",
        "src/agent.py",
        "tests/__init__.py",
        "tests/test_agent.py",
    ]

    def __init__(self, workspace: TutorialWorkspace) -> None:
        self.workspace = workspace

    def build_initial_scaffold(
        self,
        initial_agent_code: Optional[str] = None,
        initial_test_code: Optional[str] = None,
    ) -> List[str]:
        """
        Create the full initial project scaffold inside the tutorial workspace.
        Returns list of relative file paths created.
        """
        self.workspace.create()

        # 1. Project config & documentation
        self.workspace.write_file(".gitignore", DEFAULT_GITIGNORE)
        self.workspace.write_file(".env.example", DEFAULT_ENV_EXAMPLE)
        self.workspace.write_file("pyproject.toml", DEFAULT_PYPROJECT_TOML)
        self.workspace.write_file("README.md", DEFAULT_README_MD)

        # 2. Source package
        self.workspace.write_file("src/__init__.py", '"""Agentic Studio core package."""\n')
        self.workspace.write_file(
            "src/agent.py",
            initial_agent_code or '"""Agent implementation."""\n',
        )

        # 3. Test package
        self.workspace.write_file("tests/__init__.py", '"""Agentic Studio test suite."""\n')
        self.workspace.write_file(
            "tests/test_agent.py",
            initial_test_code or '"""Agent unit tests."""\n',
        )

        created_files = self.workspace.list_files()
        self.validate_scaffold()
        return created_files

    def validate_scaffold(self) -> None:
        """
        Validate that all required tutorial files exist and conform to standards.
        Raises ValidationError if anything is missing or invalid.
        """
        missing_files = [f for f in self.REQUIRED_TUTORIAL_FILES if not self.workspace.file_exists(f)]
        if missing_files:
            raise ValidationError(
                f"Tutorial repository is missing required files: {missing_files}"
            )

        # Verify .gitignore properly ignores .env
        gitignore_content = self.workspace.read_file(".gitignore")
        if ".env" not in gitignore_content.splitlines() and "\n.env\n" not in gitignore_content:
            raise ValidationError(".gitignore must explicitly contain '.env' to prevent secret leakage.")

        # Verify .env.example contains placeholder without real secret
        env_example_content = self.workspace.read_file(".env.example")
        if "sk-" in env_example_content or "AIza" in env_example_content or "gsk_" in env_example_content:
            raise ValidationError(".env.example must only contain placeholders, found potential secret token.")


__all__ = [
    "TutorialRepositoryBuilder",
    "DEFAULT_GITIGNORE",
    "DEFAULT_ENV_EXAMPLE",
    "DEFAULT_PYPROJECT_TOML",
    "DEFAULT_README_MD",
]
