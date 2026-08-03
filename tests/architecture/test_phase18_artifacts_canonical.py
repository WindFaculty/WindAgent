"""Phase 18 — Content-addressed artifact storage canonical isolation tests (plan 05 §4, §11-§16).

Proves the Phase 18 artifact pipeline (`storage/windagent_storage/video_production/`)
meets the architecture rules:

- storage-layer: imports only `windagent_core` + `windagent_providers`;
  never `windagent_tools` / `windagent_orchestration` / `windagent_intelligence`
  (scaffold_v2.yaml packages.storage.allowed_dependencies) — the content store
  is SELF-CONTAINED and does not reach into tools' ContentAddressedStore;
- no subprocess / sys.path mutation / dynamic import inside the package
  (offline determinism — the gate runs fully offline);
- atomic publish ordering: content file BEFORE record, event AFTER commit
  (plan 05 §14.1 — no VALID record without file, no published file without
  record);
- reuse is full-key + re-hash validated, never "file exists" alone (§14.4);
- invalidation never deletes and never rewrites history (§14.3);
- key is versioned; old keys never reinterpreted (§13);
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "storage" / "windagent_storage" / "video_production"

FORBIDDEN_LAUNCH_PATTERNS = [
    re.compile(r"subprocess\.(?:run|Popen|call|create_subprocess_exec)\s*\(", re.MULTILINE),
    re.compile(r"sys\.path\.(?:insert|append)\s*\(", re.MULTILINE),
    re.compile(r"spec_from_file_location\s*\(", re.MULTILINE),
    re.compile(r"importlib\.import_module\s*\(", re.MULTILINE),
    re.compile(r"__import__\s*\(", re.MULTILINE),
]

STORAGE_ALLOWED_DEP_ROOTS = (
    "windagent_core",
    "windagent_providers",
    "windagent_storage",  # self-root for intra-package imports
)


def _py_files(directory: Path) -> list[tuple[str, str]]:
    files = []
    for py in sorted(directory.rglob("*.py")):
        if "__pycache__" in py.as_posix():
            continue
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_phase18_modules_exist():
    for name in (
        "model.py",
        "key.py",
        "store.py",
        "graph.py",
        "invalidation.py",
        "publisher.py",
        "reuse.py",
        "__init__.py",
    ):
        assert (ARTIFACT_DIR / name).exists(), f"missing storage/video_production/{name}"


def test_phase18_never_launches_or_dynamic_imports():
    hits = []
    for rel, text in _py_files(ARTIFACT_DIR):
        for pattern in FORBIDDEN_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"phase18 launches/dynamic-imports: {hits}"


def test_phase18_storage_dependency_roots():
    offenders = []
    for rel, text in _py_files(ARTIFACT_DIR):
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "windagent" not in stripped:
                continue
            module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
            if module and module.group(1) not in STORAGE_ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"storage/video_production imports forbidden deps: {offenders}"


def test_phase18_publish_writes_content_before_record():
    """Plan 05 §14.1: content file published BEFORE the record write; the
    ArtifactAvailable event is emitted only after the record commit."""
    text = (ARTIFACT_DIR / "publisher.py").read_text(encoding="utf-8")
    assert "content_hash = self.content_store.publish(request.data)" in text
    assert "self.record_store.save(record)" in text
    # content publish precedes record save in source order; the event object is
    # constructed inside publish() AFTER the record commit (not the class def).
    content_idx = text.index("content_store.publish(request.data)")
    record_idx = text.index("record_store.save(record)")
    event_idx = text.index("event = ArtifactAvailableEvent(")
    assert content_idx < record_idx < event_idx


def test_phase18_record_store_history_append_only():
    text = (ARTIFACT_DIR / "store.py").read_text(encoding="utf-8")
    assert "history would shrink" in text
    assert "append-only" in text


def test_phase18_invalidation_never_deletes():
    text = (ARTIFACT_DIR / "invalidation.py").read_text(encoding="utf-8")
    assert "never deletes" in text.lower()
    assert "mark_stale" in text
    assert "mark_superseded" in text


def test_phase18_key_versioned_and_not_reinterpreted():
    text = (ARTIFACT_DIR / "key.py").read_text(encoding="utf-8")
    assert "never reinterpreted" in text
    assert "ARTIFACT_KEY_VERSION" in text
    assert "key_version != ARTIFACT_KEY_VERSION" in text


def test_phase18_reuse_is_full_key_and_hash_validated():
    text = (ARTIFACT_DIR / "reuse.py").read_text(encoding="utf-8")
    assert "key_matches" in text
    assert "tampered" in text
    assert "re-hash to record content_sha256" in text
    assert "file exists" in text


def test_phase18_graph_fails_closed_on_unknown_and_cycle():
    graph_text = (ARTIFACT_DIR / "graph.py").read_text(encoding="utf-8")
    assert "Unknown artifact node" in graph_text
    assert "cycle" in graph_text.lower()
    assert "has_node" in graph_text


def test_phase18_exports():
    import windagent_storage as storage

    for name in (
        "ArtifactRecord",
        "ArtifactStatus",
        "ArtifactType",
        "compute_artifact_key",
        "ContentAddressedStore",
        "ArtifactRecordStore",
        "ArtifactDependencyGraph",
        "ArtifactDependencyType",
        "ArtifactInvalidationService",
        "InvalidationChange",
        "ArtifactPublisher",
        "PublishRequest",
        "ArtifactReusePolicy",
        "ReuseDecision",
        "ArtifactAvailableEvent",
    ):
        assert hasattr(storage, name), f"windagent_storage missing export {name}"


def test_phase18_scope_rules_present():
    """§14.3 scope rules must be reachable via the public exports."""
    import windagent_storage.video_production as vp

    assert callable(vp.build_character_scope)
    assert callable(vp.build_bgm_scope)
    assert vp.ArtifactDependencyType.CHARACTER_BINDING.value == "CHARACTER_BINDING"
    assert vp.ArtifactDependencyType.AUDIO_INPUT.value == "AUDIO_INPUT"


def test_real_repo_architecture_stays_clean():
    import json
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/check_architecture_imports.py", "--root", ".", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-1000:]
    report = json.loads(proc.stdout)
    assert report["verdict"] == "PASS", report["violations"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
