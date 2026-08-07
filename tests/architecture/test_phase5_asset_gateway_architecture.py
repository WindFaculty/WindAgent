"""
Architecture tests for the VP3D Phase 5 Universal Asset Gateway.

Mandatory checks (Stage C Phase 5):
1. ``core`` never imports the gateway implementation packages
   (``windagent_providers`` / ``windagent_tools``) from the asset resolution
   domain or the port contract.
2. The gateway adapters live in ``providers/windagent_providers/assets/`` and
   only import ``windagent_core`` (per architecture scaffold_v2:
   providers.allowed_dependencies = ["windagent_core"]).
3. The ``AssetResolverPort`` contract leaks no provider SDK, network transport
   or credential identifiers.
4. No credential values or secret-key patterns in gateway requests/adapters.
5. The Director surface never calls providers directly — the port is the only
   channel (checked structurally: no network SDK import in the port).
"""

import ast
import re
from pathlib import Path

import pytest

from windagent_core.contracts.video_production.asset_resolver import AssetResolverPort

ROOT = Path(__file__).resolve().parents[2]

ASSETS_PKG = ROOT / "providers" / "windagent_providers" / "assets"
ASSET_RESOLUTION_DIR = (
    ROOT / "core" / "windagent_core" / "domain" / "video_production" / "asset_resolution"
)
PORT_FILE = ROOT / "core" / "windagent_core" / "contracts" / "video_production" / "asset_resolver.py"

FORBIDDEN_CORE_IMPORTS = (
    "windagent_providers",
    "windagent_tools",
    "windagent_intelligence",
    "windagent_storage",
    "windagent_workflows",
    "third_party",
)

FORBIDDEN_PROVIDER_IMPORTS = (
    "windagent_tools",
    "windagent_intelligence",
    "windagent_orchestration",
    "windagent_storage",
    "apps",
)

SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[a-zA-Z0-9_-]{8,}"),
    re.compile(r"(Bearer\s+)([a-zA-Z0-9_\-\.]{6,})"),
    re.compile(r"AIzaSy[a-zA-Z0-9_-]{20,}"),
)


def _iter_python_files(root: Path):
    return [p for p in root.rglob("*.py") if "__pycache__" not in str(p)]


def _imported_roots(content: str) -> set[str]:
    tree = ast.parse(content)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _identifiers(content: str) -> set[str]:
    """Lowercase identifiers (imports, classes, function/field names)."""
    tree = ast.parse(content)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.lower())
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.lower())
            for alias in node.names:
                found.add(alias.name.lower())
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            found.add(node.name.lower())
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.add(node.target.id.lower())
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    found.add(tgt.id.lower())
    return found


class TestAssetResolutionBoundary:
    def test_core_never_imports_gateway_implementations(self):
        violations = []
        for path in _iter_python_files(ASSET_RESOLUTION_DIR) + [PORT_FILE]:
            content = path.read_text(encoding="utf-8")
            for mod in _imported_roots(content):
                if mod in FORBIDDEN_CORE_IMPORTS:
                    violations.append(f"{path.relative_to(ROOT)} imports {mod}")
        assert not violations, "core imports gateway implementation:\n" + "\n".join(violations)

    def test_gateway_adapters_only_import_core(self):
        violations = []
        for path in _iter_python_files(ASSETS_PKG):
            content = path.read_text(encoding="utf-8")
            for mod in _imported_roots(content):
                if mod in FORBIDDEN_PROVIDER_IMPORTS:
                    violations.append(f"{path.relative_to(ROOT)} imports {mod}")
        assert not violations, "providers/assets imports disallowed package:\n" + "\n".join(violations)

    def test_port_leaks_no_provider_sdk_or_credential(self):
        content = PORT_FILE.read_text(encoding="utf-8")
        # Identifier-level check: the port may NAME providers in prose but must
        # never import or reference their SDK objects/transports.
        identifiers = _identifiers(content)
        for forbidden in ("httpx", "requests", "urllib", "bpy", "unreal", "transport"):
            assert forbidden not in identifiers, f"port leaks {forbidden}"
        imported = _imported_roots(content)
        for forbidden in ("windagent_providers", "windagent_tools"):
            assert forbidden not in imported, f"port imports {forbidden}"
        for pattern in SECRET_VALUE_PATTERNS:
            assert not pattern.search(content), f"port contains secret pattern {pattern}"

    def test_adapters_store_no_secret_values(self):
        hits = []
        for path in _iter_python_files(ASSETS_PKG):
            content = path.read_text(encoding="utf-8")
            for pattern in SECRET_VALUE_PATTERNS:
                for match in pattern.finditer(content):
                    line_no = content[: match.start()].count("\n") + 1
                    hits.append(f"{path.relative_to(ROOT)}:{line_no}")
        assert not hits, f"secret values in gateway adapters: {hits}"

    def test_adapters_reference_secrets_only_by_reference(self):
        """Secret-bearing config fields must be *_ref references, never raw."""
        mesh_api = (ASSETS_PKG / "mesh_api.py").read_text(encoding="utf-8")
        mesh_mcp = (ASSETS_PKG / "mesh_mcp.py").read_text(encoding="utf-8")
        assert "api_key_ref" in mesh_api
        assert "client_ref" in mesh_mcp
        # No field is ever named just api_key (without _ref) inside adapters.
        for path in _iter_python_files(ASSETS_PKG):
            content = path.read_text(encoding="utf-8")
            for line_no, line in enumerate(content.splitlines(), start=1):
                if re.search(r"\bapi_key\b(?!_ref)", line):
                    pytest.fail(
                        f"{path.relative_to(ROOT)}:{line_no} uses raw api_key field"
                    )

    def test_resolver_port_implemented_by_gateway(self):
        from windagent_providers.assets.resolver import AssetResolver

        assert issubclass(AssetResolver, AssetResolverPort)
        for method in ("discover", "acquire", "capabilities"):
            assert callable(getattr(AssetResolver, method)), f"missing {method}"

    def test_adapter_surface_never_mentions_transport_sdks(self):
        for path in _iter_python_files(ASSETS_PKG):
            if path.name in {"internet.py", "mesh_api.py", "mesh_mcp.py"}:
                continue  # transport seams live here by design
            content = path.read_text(encoding="utf-8")
            for forbidden in ("httpx", "requests", "urllib"):
                assert forbidden not in content, (
                    f"{path.relative_to(ROOT)} leaks transport SDK {forbidden}"
                )
