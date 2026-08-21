"""Phase 12 Architecture Tests: Versioning, Documentation, and Naming Cutover.

Validates Gate G12_DOCS and Phase 12 roadmap deliverables:
1. Root and App READMEs declare Architecture V3 and canonical /api/v3/* routes.
2. Workspace pyproject.toml manifests declare Architecture V3.
3. Canonical docs in docs/ reflect Architecture V3 contracts and protocols.
4. Core version constants reflect ARCHITECTURE_GENERATION="v3" and API_VERSION="v3".
5. OrchestrationContainer is the primary container with OrchestrationV2Container alias.
6. Developer and healthcheck scripts declare Architecture V3.
7. Gate G12_DOCS compliance: zero active production documents assert V2 as canonical authority.
"""

from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def test_root_and_app_readmes_declare_v3_canonical():
    """Root and application READMEs must declare Architecture V3 and /api/v3/* canonical."""
    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Architecture V3 modular" in root_readme
    assert "Canonical Architecture V3 packages" in root_readme
    assert "Canonical API: `/api/v3/*`" in root_readme
    assert "Realtime WebSocket: `/ws`" in root_readme
    assert "410 Gone" in root_readme
    assert "[API V3 contract](docs/api_contract.md)" in root_readme

    api_readme = (ROOT / "apps" / "api" / "README.md").read_text(encoding="utf-8")
    assert "Architecture V3" in api_readme
    assert "/api/v3/*" in api_readme
    assert "/ws" in api_readme
    assert "410 Gone" in api_readme

    worker_readme = (ROOT / "apps" / "worker" / "README.md").read_text(encoding="utf-8")
    assert "Architecture V3" in worker_readme

    desktop_readme = (ROOT / "apps" / "desktop" / "README.md").read_text(encoding="utf-8")
    assert "Architecture V3" in desktop_readme

    cli_readme = (ROOT / "apps" / "cli" / "README.md").read_text(encoding="utf-8")
    assert "Architecture V3" in cli_readme


def test_pyproject_descriptions_declare_v3_canonical():
    """All key pyproject.toml manifests must declare Architecture V3."""
    root_pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "Architecture V3" in root_pyproject["project"]["description"]

    api_pyproject = tomllib.loads((ROOT / "apps" / "api" / "pyproject.toml").read_text(encoding="utf-8"))
    assert "Architecture V3" in api_pyproject["project"]["description"]

    worker_pyproject = tomllib.loads((ROOT / "apps" / "worker" / "pyproject.toml").read_text(encoding="utf-8"))
    assert "Architecture V3" in worker_pyproject["project"]["description"]

    cli_pyproject = tomllib.loads((ROOT / "apps" / "cli" / "pyproject.toml").read_text(encoding="utf-8"))
    assert "Architecture V3" in cli_pyproject["project"]["description"]

    providers_pyproject = tomllib.loads((ROOT / "providers" / "pyproject.toml").read_text(encoding="utf-8"))
    assert "Architecture V3" in providers_pyproject["project"]["description"]


def test_canonical_docs_declare_v3_canonical():
    """Contracts and protocol documents in docs/ must declare Architecture V3."""
    api_contract = (ROOT / "docs" / "api_contract.md").read_text(encoding="utf-8")
    assert "# WindAgent Architecture V3 API Contract" in api_contract
    assert "/api/v3/" in api_contract
    assert "/ws" in api_contract
    assert "410 Gone" in api_contract

    event_protocol = (ROOT / "docs" / "event_protocol.md").read_text(encoding="utf-8")
    assert "# Event Protocol (Architecture V3)" in event_protocol
    assert "WindAgent Architecture V3" in event_protocol

    model_registry = (ROOT / "docs" / "model_provider_registry.md").read_text(encoding="utf-8")
    assert "/api/v3/providers" in model_registry

    docs_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "hợp đồng API kiến trúc V3" in docs_index
    assert "định dạng và quy tắc sự kiện V3" in docs_index


def test_canonical_version_constants_are_v3():
    """Core version authority must expose ARCHITECTURE_GENERATION='v3' and API_VERSION='v3'."""
    from windagent_core.version import (
        PRODUCT_VERSION,
        ARCHITECTURE_GENERATION,
        API_VERSION,
        PROVIDER_PROTOCOL_VERSION,
        ARTIFACT_PROTOCOL_VERSION,
        get_version_info,
    )

    assert PRODUCT_VERSION == "0.3.0"
    assert ARCHITECTURE_GENERATION == "v3"
    assert API_VERSION == "v3"
    assert PROVIDER_PROTOCOL_VERSION == "1.0.0"
    assert ARTIFACT_PROTOCOL_VERSION == "1.0.0"

    info = get_version_info()
    assert info["architecture_generation"] == "v3"
    assert info["api_version"] == "v3"


def test_orchestration_container_naming_cutover():
    """OrchestrationContainer is the primary class; OrchestrationV2Container is backward alias."""
    from windagent_orchestration import OrchestrationContainer, OrchestrationV2Container
    from windagent_orchestration.composition import (
        OrchestrationContainer as CompContainer,
        OrchestrationV2Container as CompV2Container,
    )

    assert OrchestrationContainer is CompContainer
    assert OrchestrationV2Container is OrchestrationContainer
    assert CompV2Container is CompContainer

    # Verify Worker composition wires OrchestrationContainer
    worker_core = (ROOT / "apps" / "worker" / "windagent_worker" / "composition" / "core.py").read_text(encoding="utf-8")
    assert "OrchestrationContainer" in worker_core
    assert "orchestration_container: OrchestrationContainer" in worker_core


def test_scripts_and_tools_declare_v3():
    """Developer scripts and import checker must declare Architecture V3."""
    dev_api = (ROOT / "scripts" / "dev_api.ps1").read_text(encoding="utf-8")
    assert "Architecture V3 API" in dev_api

    healthcheck = (ROOT / "scripts" / "healthcheck.ps1").read_text(encoding="utf-8")
    assert "Architecture V3 API" in healthcheck

    checker = (ROOT / "scripts" / "check_architecture_imports.py").read_text(encoding="utf-8")
    assert "Architecture V3 policy checker" in checker


def test_gate_g12_docs_compliance():
    """Gate G12_DOCS: Canonical documentation consistently reflects Architecture V3."""
    canonical_doc_files = [
        ROOT / "README.md",
        ROOT / "apps" / "api" / "README.md",
        ROOT / "apps" / "worker" / "README.md",
        ROOT / "apps" / "desktop" / "README.md",
        ROOT / "apps" / "cli" / "README.md",
        ROOT / "docs" / "api_contract.md",
        ROOT / "docs" / "event_protocol.md",
        ROOT / "docs" / "model_provider_registry.md",
        ROOT / "docs" / "README.md",
    ]

    for doc_path in canonical_doc_files:
        assert doc_path.exists(), f"Doc file missing: {doc_path}"
        content = doc_path.read_text(encoding="utf-8")
        # Ensure active canonical documentation is not claiming V2 is the active business API
        assert "/api/v2/*` (business API)" not in content
        assert "hợp đồng API kiến trúc V2" not in content
