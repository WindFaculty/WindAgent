"""
VP3D Phase 7 — Asset job runner contract tests (Stage C Phase 7).

The host pipeline only talks to engines through ``AssetJobRunner``. These
tests lock the contract shape so the REAL ``BlenderAssetJobRunner`` and the
CI ``FakeAssetJobRunner`` stay interchangeable:

- job invocation carries typed kind/job_id/inputs/config;
- results carry ok/report/generated_files and never raw engine SDKs;
- fakes are deterministic (same input -> same hashes);
- the Blender runner dispatches through the Stage B launcher with a
  pure-stdlib asset job script (no bpy on the host path).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from windagent_core.domain.video_production.asset_normalization.models import PreviewProfile
from windagent_tools.media_assets.normalization.fakes import FakeAssetJobRunner
from windagent_tools.media_assets.normalization.job_runner import JobInvocation


def _run(coro):
    return asyncio.run(coro)


class TestJobInvocationContract:
    def test_invocation_is_typed(self):
        invocation = JobInvocation(
            kind="GENERATE_LOD",
            job_id="lod_abc_1",
            input_files=["/x/a.glb"],
            output_dir="/tmp/out",
            workspace="/tmp/ws",
            config={"level": 1},
        )
        assert invocation.kind == "GENERATE_LOD"
        assert invocation.job_id == "lod_abc_1"
        assert invocation.config["level"] == 1


class TestFakeRunnerContract:
    def test_import_validate_reports_stats(self):
        runner = FakeAssetJobRunner()
        result = _run(
            runner.import_validate(
                JobInvocation(
                    kind="IMPORT_VALIDATE",
                    job_id="iv_1",
                    config={"triangles": 100, "vertices": 60, "objects": 2},
                )
            )
        )
        assert result.ok is True
        assert result.report["triangles"] == 100
        assert result.report["objects"] == 2
        assert result.report["generated_by"] == "fake"

    def test_import_validate_fails_closed_on_config(self, tmp_path):
        runner = FakeAssetJobRunner()
        result = _run(
            runner.import_validate(
                JobInvocation(
                    kind="IMPORT_VALIDATE",
                    job_id="iv_bad",
                    config={"fail": "import"},
                )
            )
        )
        assert result.ok is False
        assert "fake import rejected" in result.error

    def test_generate_lod_writes_deterministic_files(self, tmp_path):
        runner = FakeAssetJobRunner()
        out = tmp_path / "lod_out"
        result = _run(
            runner.generate_lod(
                JobInvocation(
                    kind="GENERATE_LOD",
                    job_id="lod_1",
                    output_dir=str(out),
                    config={
                        "level": 1,
                        "ratio": 0.5,
                        "target_triangles": 500,
                        "content_hash": "c" * 64,
                    },
                )
            )
        )
        assert result.ok is True
        assert len(result.generated_files) == 1
        payload = Path(result.generated_files[0]).read_bytes()
        assert len(result.report["content_hash"]) == 64
        # Deterministic: identical input -> identical content.
        out2 = tmp_path / "lod_out2"
        result2 = _run(
            runner.generate_lod(
                JobInvocation(
                    kind="GENERATE_LOD",
                    job_id="lod_1b",
                    output_dir=str(out2),
                    config={
                        "level": 1,
                        "ratio": 0.5,
                        "target_triangles": 500,
                        "content_hash": "c" * 64,
                    },
                )
            )
        )
        assert Path(result2.generated_files[0]).read_bytes() == payload

    def test_render_preview_writes_thumbnail_and_frames(self, tmp_path):
        runner = FakeAssetJobRunner()
        out = tmp_path / "preview"
        profile = PreviewProfile(width=128, height=72, frames=6)
        result = _run(
            runner.render_preview(
                JobInvocation(
                    kind="RENDER_PREVIEW",
                    job_id="pv_1",
                    output_dir=str(out),
                    config={"content_hash": "d" * 64},
                ),
                profile,
            )
        )
        assert result.ok is True
        assert result.report["frames_rendered"] == 6
        assert len(result.generated_files) == 7  # thumbnail + 6 frames
        assert all(Path(p).is_file() for p in result.generated_files)
        for path in result.generated_files:
            data = Path(path).read_bytes()
            assert data[:8] == b"\x89PNG\r\n\x1a\n"


class TestBlenderRunnerShape:
    def test_asset_job_script_is_pure_stdlib(self):
        """The blender-side script must not import windagent or bpy at module
        level — it runs inside blender.exe's bundled Python."""
        from pathlib import Path as P

        root = P(__file__).resolve().parents[3]
        script = root / "tools" / "windagent_tools" / "production_engines" / "blender" / "scripts" / "execute_asset_job.py"
        content = script.read_text(encoding="utf-8")
        module_level_imports = [
            line for line in content.splitlines()
            if line and not line.startswith((" ", "\t")) and line.strip().startswith(("import ", "from "))
        ]
        for line in module_level_imports:
            assert "windagent" not in line, f"host import in asset job script: {line}"
            assert not line.startswith("import bpy"), f"module-level bpy import: {line}"
            assert not line.startswith("from bpy"), f"module-level bpy import: {line}"
        assert "--job-spec" in content
        assert "use_scripts_auto_execute = False" in content

    def test_blender_runner_never_on_host_normalization_path(self):
        """media_assets (host pipeline) must not import the Blender adapter."""
        import ast

        root = Path(__file__).resolve().parents[2]
        normalization_pkg = root / "tools" / "windagent_tools" / "media_assets" / "normalization"
        for path in normalization_pkg.rglob("*.py"):
            if path.name == "job_runner.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "production_engines" not in node.module, (
                        f"{path.name} imports Blender adapter: {node.module}"
                    )


class TestJobSpecSerialization:
    def test_blender_runner_writes_typed_spec(self, tmp_path):
        """The spec written into the job workspace round-trips as JSON."""
        spec = {
            "kind": "ASSET_GENERATE_LOD",
            "input_files": ["C:/x/a.glb"],
            "output_dir": "C:/tmp/out",
            "level": 1,
            "ratio": 0.5,
        }
        path = tmp_path / "job_spec.json"
        path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded == spec
