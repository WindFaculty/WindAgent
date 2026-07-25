import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "scaffold_architecture_v2.py"
SPEC = importlib.util.spec_from_file_location("scaffold_architecture_v2", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_pyproject_generation_does_not_read_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(MODULE, "ROOT_DIR", tmp_path)
    package = tmp_path / "core"
    package.mkdir()
    (package / "pyproject.toml").write_text("sentinel", encoding="utf-8")
    info = {
        "path": "core",
        "namespace": "windagent_core",
        "description": "Core",
        "version": "0.3.0",
        "allowed_dependencies": [],
        "external_dependencies": ["pydantic>=2.7"],
    }
    generated = MODULE.generate_package_pyproject("core", info)
    assert generated != "sentinel"
    assert 'name = "windagent_core"' in generated
    assert '"pydantic>=2.7"' in generated


def test_init_generation_does_not_read_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(MODULE, "ROOT_DIR", tmp_path)
    namespace = tmp_path / "core" / "windagent_core"
    namespace.mkdir(parents=True)
    (namespace / "__init__.py").write_text("sentinel", encoding="utf-8")
    generated = MODULE.generate_package_init("core", {
        "path": "core", "namespace": "windagent_core", "description": "Core", "version": "0.3.0"
    })
    assert generated != "sentinel"
    assert '__version__ = "0.3.0"' in generated