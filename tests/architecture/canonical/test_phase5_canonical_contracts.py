"""Phase 5 tests: canonical contract ownership unified.

Verifies:
1. Old core package paths are gone (windagent_core.providers, windagent_core.tools).
2. Canonical contracts import from windagent_core.contracts.providers / .tools.
3. Duplicate-model scanner exits non-zero on a fixture containing a duplicate
   canonical model, and zero on the real tree.
4. ToolInvocation/ToolResult single canonical definition (dataclass shape).
5. Provider capability schemas owned by core contracts.
"""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCANNER = ROOT / "scripts" / "check_duplicate_canonical_models.py"


def test_old_core_packages_removed():
    assert not (ROOT / "core" / "windagent_core" / "providers").exists()
    assert not (ROOT / "core" / "windagent_core" / "tools").exists()


def test_canonical_provider_contracts_importable():
    from windagent_core.contracts.providers import (
        ProviderRequest,
        ProviderResponse,
        ProviderCapabilities,
    )

    ProviderRequest(prompt="hi")
    res = ProviderResponse(content="ok")
    assert res.usage.total_tokens == 0
    assert ProviderCapabilities().supports_chat is True


def test_canonical_tool_contracts_importable():
    from windagent_core.contracts.tools import (
        ToolInvocation,
        ToolResult,
    )
    from windagent_core.domain.types import ToolCallId

    inv = ToolInvocation(id=ToolCallId.generate(), tool_name="read_file", params={"path": "x"})
    assert inv.arguments == {"path": "x"}
    res = ToolResult(call_id=inv.id, success=True, data="ok")
    assert res.success is True


def test_toolinvocation_single_definition():
    """domain.models must not re-define ToolInvocation/ToolResult."""
    import windagent_core.domain.models as dm

    assert not hasattr(dm, "ToolInvocation")
    assert not hasattr(dm, "ToolResult")


def test_scanner_passes_on_real_tree():
    res = subprocess.run(
        [sys.executable, str(SCANNER)], capture_output=True, text=True, cwd=ROOT
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_scanner_detects_duplicate_fixture(tmp_path, monkeypatch):
    """Fixture with a duplicate ProviderRequest must make scanner exit non-zero."""
    dup_dir = tmp_path / "providers" / "windagent_providers" / "fake"
    dup_dir.mkdir(parents=True)
    (dup_dir / "dup.py").write_text(
        "from pydantic import BaseModel\n\n"
        "class ProviderRequest(BaseModel):\n"
        "    prompt: str = ''\n"
    )
    # Point scanner root at a tree that mirrors the real layout plus the duplicate.
    import scripts.check_duplicate_canonical_models as scanner

    canonical_rel = scanner.CANONICAL_MODELS["ProviderRequest"]
    real_canonical = ROOT / canonical_rel
    mirror = tmp_path / canonical_rel
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(real_canonical.read_text(encoding="utf-8"))

    violations, _sigs, scanned = scanner.scan(tmp_path)
    assert any("ProviderRequest" in v[2] for v in violations), violations
