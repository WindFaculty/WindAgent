"""
Repository root locator for WindAgent Architecture V2.

Provides fail-closed root detection used by architecture-check and other tools.

Phase 3: Root detection uses only stable markers:
- pyproject.toml with [tool.uv.workspace]
- configs/architecture/scaffold_v2.yaml
- .git directory or explicit repository marker
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

REQUIRED_ROOT_MARKERS = [
    "pyproject.toml",
    "configs/architecture/scaffold_v2.yaml",
]

# Optional but preferred markers for additional validation
OPTIONAL_ROOT_MARKERS = [
    ".git",
]


def find_repository_root(start: Optional[Path] = None) -> Path:
    """
    Find the repository root by walking up from start directory.

    Root is only valid if it contains ALL required markers:
    - pyproject.toml (with [tool.uv.workspace] section)
    - configs/architecture/scaffold_v2.yaml

    Optional markers (.git) provide additional validation but are not required.

    Args:
        start: Starting directory (defaults to current working directory)

    Returns:
        Path to repository root

    Raises:
        FileNotFoundError: If no valid repository root found
        ValueError: If root found but missing required markers
    """
    if start is None:
        start = Path.cwd()

    current = start.resolve()

    while current != current.parent:
        if _is_valid_root(current):
            return current
        current = current.parent

    raise FileNotFoundError(
        f"Repository root not found from {start}. "
        f"Required markers: {', '.join(REQUIRED_ROOT_MARKERS)}"
    )


def _is_valid_root(path: Path) -> bool:
    """Check if path contains all required root markers."""
    # Check basic files exist
    for marker in REQUIRED_ROOT_MARKERS:
        if not (path / marker).exists():
            return False

    # Check pyproject.toml has [tool.uv.workspace]
    pyproject = path / "pyproject.toml"
    try:
        import tomllib
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        if "tool" not in data or "uv" not in data["tool"] or "workspace" not in data["tool"]["uv"]:
            return False
    except Exception:
        return False

    return True


def is_repository_root(path: Path) -> bool:
    """Quick check if a path is a valid repository root."""
    try:
        return _is_valid_root(path.resolve())
    except Exception:
        return False


if __name__ == "__main__":
    import sys
    try:
        root = find_repository_root()
        print(str(root))
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
