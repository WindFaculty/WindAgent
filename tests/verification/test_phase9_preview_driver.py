"""Phase 9 real-preview driver coverage (compile/import + decision logic).

The preview scripts are REAL Blender executables (run headless, not under
pytest); gate authority = the real render, executed separately. This test keeps
the changed paths green under the pytest harness and locks the fail-closed
`preview_valid` decision (alpha/beta must differ in topology AND both rigs must
validate) so it cannot silently regress.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "verification"


def _load(name: str):
    path = _SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_preview_scripts_import_cleanly():
    host = _load("produce_phase9_preview")
    assert host.GATE == "VP3D_P9_CHARACTER_RIG_VERIFIED"
    # blender_rig_preview is Blender-internal (imports bmesh); not host-importable.
    assert (_SCRIPTS / "blender_rig_preview.py").is_file()


def _ok(names: list) -> dict:
    return {
        "has_root": True, "parenting_ok": True, "all_vertices_skinned": True,
        "topology_signature": {"names": names},
    }


def test_preview_valid_ok_when_both_rigs_pass():
    pv = _load("produce_phase9_preview").preview_valid
    report = {"topologies": {"alpha": _ok(["a", "b"]), "beta": _ok(["c", "d"])}}
    assert pv(report, 0) is True


def test_preview_valid_fails_when_topology_not_distinct():
    pv = _load("produce_phase9_preview").preview_valid
    report = {"topologies": {"alpha": _ok(["a"]), "beta": _ok(["a"])}}
    assert pv(report, 0) is False


def test_preview_valid_fails_closed_on_unskinned_rig():
    pv = _load("produce_phase9_preview").preview_valid
    report = {
        "topologies": {
            "alpha": _ok(["a"]),
            "beta": dict(_ok(["b"]), all_vertices_skinned=False),
        }
    }
    assert pv(report, 0) is False


def test_preview_valid_fails_closed_on_blender_error():
    pv = _load("produce_phase9_preview").preview_valid
    report = {"topologies": {"alpha": _ok(["a"]), "beta": _ok(["b"])}}
    assert pv(report, 1) is False
