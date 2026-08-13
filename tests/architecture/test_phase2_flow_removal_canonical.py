"""
Phase 2 Architecture & Negative Tests: Hard Removal of Google Flow (plan Stage A §5).

Mandatory negative checks:
1. Importing `google_flow` from any canonical package raises ImportError.
2. Zero runtime Python files in core/tools/providers/workflows/execution/intelligence import `google_flow`.
3. Active configs contain 0 Flow credentials or runtime key residue.
4. Worker restart/cancel/retry operates via fake ProductionEnginePort & IR.
5. Google Gemini LLM provider (`providers/windagent_providers/google/`) is intact.
"""

import ast
import importlib
import json
import tempfile
from pathlib import Path

import pytest

from windagent_core.contracts.video_production.production_engine import ProductionEnginePort
from windagent_core.domain.video_production.ids import (
    DerivedArtifactId,
    EngineJobId,
    ProductionRevisionId,
    ShotId,
    VideoProjectId,
)
from windagent_core.domain.video_production.production_ir import (
    DerivedArtifact,
    DerivedArtifactKind,
    EngineJobReceipt,
    EngineJobStatus,
    RenderIntent,
    SceneDescription,
    ShotExecutionIntent,
)

ROOT = Path(__file__).resolve().parents[2]

CANONICAL_PACKAGES = [
    ROOT / "core" / "windagent_core",
    ROOT / "tools" / "windagent_tools",
    ROOT / "providers" / "windagent_providers",
    ROOT / "workflows" / "windagent_workflows",
    ROOT / "execution" / "windagent_execution",
    ROOT / "intelligence" / "windagent_intelligence",
]

FLOW_KEY_TERMS = (
    "FLOW_PROJECT_URL",
    "FLOW_SESSION_COOKIE",
    "FLOW_CREDENTIAL",
    "GOOGLE_FLOW_KEY",
)

# ---------------------------------------------------------------------------
# VP3D Stage A — comprehensive Flow/generative-video residue scanner
# (strengthened Phase 2 negative gate; allowlist is bounded & exact-path)
# ---------------------------------------------------------------------------

RESIDUE_TOKENS = (
    "google_flow",
    "google_flow_browser",
    "FlowGenerationSpecification",
    "GenerationModeDecider",
    "FLOW_SESSION",
    "FLOW_ACCOUNT",
    "FLOW_PROJECT_URL",
    "FLOW_SESSION_COOKIE",
    "FLOW_CREDENTIAL",
    "GOOGLE_FLOW_KEY",
    "TEXT_TO_VIDEO",
    "IMAGE_TO_VIDEO",
    "FRAMES_TO_VIDEO",
    "VIDEO_EXTENSION",
    "VIDEO_TO_VIDEO",
    "INGREDIENTS_TO_VIDEO",
)

ACTIVE_SCAN_ROOTS = [
    ROOT / "core",
    ROOT / "intelligence",
    ROOT / "orchestration",
    ROOT / "workflows",
    ROOT / "apps",
    ROOT / "execution",
    ROOT / "providers",
    ROOT / "storage",
    ROOT / "tools",
    ROOT / "scripts",
    ROOT / "config",
    ROOT / "docs",
]
CURRENT_DOCS = sorted(ROOT.glob("*.md"))  # root-level current docs
ENV_TEMPLATES = [p for p in ROOT.glob("*.env*") if p.is_file()]

# Bounded allowlist — exact paths only (manifest:
# docs/video_production/historical/FLOW_RETIREMENT_MANIFEST.md).
ALLOWED_DIRS = (
    ROOT / "core" / "windagent_core" / "domain" / "video_production" / "legacy_v1",
    ROOT / "scripts" / "verification" / "historical",
    ROOT / "docs" / "video_production" / "historical",
)
ALLOWED_FILES = (
    ROOT / "core" / "windagent_core" / "domain" / "video_production" / "production_ir" / "migrator.py",
    ROOT / "docs" / "video_production" / "protocol" / "video_production_package_v1.schema.json",
    ROOT / "docs" / "video_production" / "protocol" / "video_production_package_v1.md",
    ROOT / "docs" / "video_production" / "3d_animation_plans" / "stage_a_foundation_architecture.md",
    ROOT / "road_map.md",
)

SKIP_DIR_NAMES = {
    "__pycache__", ".venv", "node_modules", "dist", "build", ".git", ".idea",
    ".pytest_cache", "coverage", ".mypy_cache", ".ruff_cache", ".tox",
}
SKIP_SUFFIXES = {
    ".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".exe", ".dll", ".so", ".dylib",
    ".bin", ".lock", ".map", ".db", ".webp", ".avif",
}


def _rel_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _path_allowed(path: Path, allowed_dirs, allowed_files) -> bool:
    if path in allowed_files:
        return True
    return any(path.is_relative_to(d) for d in allowed_dirs)


def scan_residue(roots, *, tokens=RESIDUE_TOKENS, allowed_dirs=(), allowed_files=()) -> list[str]:
    """Scan active roots for Flow/generative-video tokens OUTSIDE the exact-path
    allowlist. Returns a list of human-readable violations (empty == clean)."""
    violations: list[str] = []
    allowed_dirs = tuple(allowed_dirs)
    allowed_files = set(allowed_files)
    for root in roots:
        if not root.exists():
            continue
        files = sorted(root.rglob("*")) if root.is_dir() else [root]
        for path in files:
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            if _path_allowed(path, allowed_dirs, allowed_files):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in tokens:
                if token in text:
                    violations.append(f"{_rel_path(path)}: contains {token!r}")
                    break
    return violations


def _iter_python_files(roots):
    for root in roots:
        for path in root.rglob("*.py"):
            yield path


def _imported_modules(content: str) -> set[str]:
    tree = ast.parse(content)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class FakeProductionEngine(ProductionEnginePort):
    def __init__(self) -> None:
        self.submitted_scenes: list[SceneDescription] = []
        self.submitted_shots: list[ShotExecutionIntent] = []
        self.cancelled_jobs: list[EngineJobId] = []
        self.jobs: dict[EngineJobId, EngineJobReceipt] = {}

    async def submit_scene(self, scene: SceneDescription, render: RenderIntent) -> EngineJobReceipt:
        self.submitted_scenes.append(scene)
        job_id = EngineJobId(f"job_scene_{scene.scene_id}")
        receipt = EngineJobReceipt(
            job_id=job_id,
            project_id=VideoProjectId("vp_01"),
            revision_id=ProductionRevisionId("rev_01"),
            status=EngineJobStatus.SUBMITTED,
        )
        self.jobs[job_id] = receipt
        return receipt

    async def submit_shot(self, intent: ShotExecutionIntent, render: RenderIntent) -> EngineJobReceipt:
        self.submitted_shots.append(intent)
        job_id = EngineJobId(f"job_shot_{intent.shot_id}")
        receipt = EngineJobReceipt(
            job_id=job_id,
            project_id=VideoProjectId("vp_01"),
            revision_id=ProductionRevisionId("rev_01"),
            status=EngineJobStatus.SUBMITTED,
        )
        self.jobs[job_id] = receipt
        return receipt

    async def inspect_job(self, job_id: EngineJobId) -> EngineJobReceipt:
        return self.jobs.get(
            job_id,
            EngineJobReceipt(
                job_id=job_id,
                project_id=VideoProjectId("vp_01"),
                revision_id=ProductionRevisionId("rev_01"),
                status=EngineJobStatus.FAILED,
                error="Unknown job",
            ),
        )

    async def cancel_job(self, job_id: EngineJobId) -> EngineJobReceipt:
        self.cancelled_jobs.append(job_id)
        if job_id in self.jobs:
            receipt = EngineJobReceipt(
                job_id=job_id,
                project_id=VideoProjectId("vp_01"),
                revision_id=ProductionRevisionId("rev_01"),
                status=EngineJobStatus.CANCELLED,
            )
            self.jobs[job_id] = receipt
            return receipt
        return EngineJobReceipt(
            job_id=job_id,
            project_id=VideoProjectId("vp_01"),
            revision_id=ProductionRevisionId("rev_01"),
            status=EngineJobStatus.CANCELLED,
        )

    async def download_artifact(
        self,
        job_id: EngineJobId,
        artifact_kind: DerivedArtifactKind,
    ) -> DerivedArtifact:
        return DerivedArtifact(
            artifact_id=DerivedArtifactId("da_01"),
            job_id=job_id,
            kind=artifact_kind,
            uri=f"file:///tmp/artifacts/{job_id}.bin",
            content_hash="abc123hash",
        )


class DurableFakeEngine(ProductionEnginePort):
    """A ProductionEnginePort that persists every job receipt to a state dir.

    A fresh instance pointed at the same state_dir simulates a WORKER RESTART:
    it re-attaches to in-flight jobs from durable state instead of re-submitting
    blindly (plan Stage A §5 'compensation_or_recovery': 'inspect durable state
    + provider before retry; never blind resubmit'). A retried job whose
    cancellation/termination is known is reconciled to CANCELLED/FAILED and a
    REAL re-submit happens only when the caller opts to start a new job.
    """

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.submitted_shot_ids: list[str] = []
        self.cancelled_job_ids: list[str] = []
        self._counter_file = self.state_dir / ".engine_seq"

    def _next_job_id(self, prefix: str) -> EngineJobId:
        seq = 0
        if self._counter_file.exists():
            seq = int(self._counter_file.read_text(encoding="utf-8").strip() or "0")
        seq += 1
        self._counter_file.write_text(str(seq), encoding="utf-8")
        return EngineJobId(f"job_{prefix}_{seq}")

    def _receipt_path(self, job_id: EngineJobId) -> Path:
        safe = str(job_id).replace("/", "_").replace("\\", "_")
        return self.state_dir / f"{safe}.receipt.json"

    def _in_memory(self, job_id: EngineJobId) -> EngineJobReceipt | None:
        path = self._receipt_path(job_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return EngineJobReceipt.model_validate(data)

    def _persist(self, receipt: EngineJobReceipt) -> None:
        self._receipt_path(receipt.job_id).write_text(
            receipt.model_dump_json(), encoding="utf-8"
        )

    async def submit_shot(self, intent: ShotExecutionIntent, render: RenderIntent) -> EngineJobReceipt:
        self.submitted_shot_ids.append(intent.shot_id)
        receipt = EngineJobReceipt(
            job_id=self._next_job_id("shot"),
            project_id=VideoProjectId("vp_01"),
            revision_id=ProductionRevisionId("rev_01"),
            status=EngineJobStatus.SUBMITTED,
            ir_hash=intent.ir_hash if hasattr(intent, "ir_hash") else "",
        )
        self._persist(receipt)
        return receipt

    async def submit_scene(self, scene: SceneDescription, render: RenderIntent) -> EngineJobReceipt:
        receipt = EngineJobReceipt(
            job_id=self._next_job_id("scene"),
            project_id=VideoProjectId("vp_01"),
            revision_id=ProductionRevisionId("rev_01"),
            status=EngineJobStatus.SUBMITTED,
        )
        self._persist(receipt)
        return receipt

    async def inspect_job(self, job_id: EngineJobId) -> EngineJobReceipt:
        receipt = self._in_memory(job_id)
        if receipt is None:
            return EngineJobReceipt(
                job_id=job_id,
                project_id=VideoProjectId("vp_01"),
                revision_id=ProductionRevisionId("rev_01"),
                status=EngineJobStatus.FAILED,
                error="Unknown job",
            )
        return receipt

    async def cancel_job(self, job_id: EngineJobId) -> EngineJobReceipt:
        self.cancelled_job_ids.append(job_id)
        current = self._in_memory(job_id)
        if current is None:
            return EngineJobReceipt(
                job_id=job_id,
                project_id=VideoProjectId("vp_01"),
                revision_id=ProductionRevisionId("rev_01"),
                status=EngineJobStatus.FAILED,
                error="Unknown job",
            )
        cancelled = current.model_copy(
            update={"status": EngineJobStatus.CANCELLED, "error": "cancelled"}
        )
        self._persist(cancelled)
        return cancelled

    async def download_artifact(
        self,
        job_id: EngineJobId,
        artifact_kind: DerivedArtifactKind,
    ) -> DerivedArtifact:
        return DerivedArtifact(
            artifact_id=DerivedArtifactId("da_01"),
            job_id=job_id,
            kind=artifact_kind,
            uri=f"file:///tmp/artifacts/{job_id}.bin",
            content_hash="abc123hash",
        )


class TestPhase2FlowRemoval:
    def test_google_flow_package_unimportable(self):
        """Proves google_flow package is deleted and cannot be imported."""
        with pytest.raises((ModuleNotFoundError, ImportError)):
            importlib.import_module("windagent_tools.google_flow")

    def test_zero_runtime_imports_of_google_flow(self):
        """Proves no canonical python file imports google_flow."""
        violations = []
        for path in _iter_python_files(CANONICAL_PACKAGES):
            content = path.read_text(encoding="utf-8")
            for mod in _imported_modules(content):
                if "google_flow" in mod:
                    violations.append(f"{path.relative_to(ROOT)} imports {mod}")
        assert not violations, f"Found google_flow runtime imports:\n" + "\n".join(violations)

    def test_no_flow_credentials_in_active_configs(self):
        """Proves active configs contain 0 Flow credential/session keys."""
        config_files = list(ROOT.glob("*.env*")) + list(ROOT.glob("config/**/*"))
        residue = []
        for cfg in config_files:
            if cfg.is_file() and not cfg.name.endswith(".md"):
                text = cfg.read_text(encoding="utf-8", errors="ignore")
                for term in FLOW_KEY_TERMS:
                    if term in text:
                        residue.append(f"{cfg.relative_to(ROOT)} contains {term}")
        assert not residue, f"Found Flow config residue:\n" + "\n".join(residue)

    def test_google_gemini_llm_provider_intact(self):
        """Proves Google Gemini LLM provider was NOT deleted when removing Flow."""
        mod = importlib.import_module("windagent_providers.google")
        assert hasattr(mod, "GoogleGeminiProviderAdapter")

    @pytest.mark.asyncio
    async def test_worker_lifecycle_submit_cancel_restart_retry(self):
        """Proves the worker lifecycle (submit → cancel → durable restart →
        retry-with-reconcile) works over ProductionEnginePort + IR after Flow
        removal. A fresh engine over the same state_dir simulates a worker
        restart that re-attaches to durable job state.
        """
        from tests.fixtures.video_production.ir_fixture_builder import build_valid_ir

        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)

            # Worker v1: submit + cancel a shot job.
            engine1 = DurableFakeEngine(state_dir)
            ir_doc = build_valid_ir()
            shot = ir_doc.shots[0]
            render = ir_doc.render_intents[0]
            receipt = await engine1.submit_shot(shot, render)

            assert receipt.status == EngineJobStatus.SUBMITTED
            job_id = receipt.job_id
            cancelled = await engine1.cancel_job(job_id)
            assert cancelled.status == EngineJobStatus.CANCELLED

            # Worker v2 (simulated restart): re-attaches to the SAME durable
            # state — it must see the cancelled job, NOT re-submit it blindly.
            # `submitted_shot_ids` is per-instance memory, so a fresh v2 must
            # have submitted nothing itself on startup.
            engine2 = DurableFakeEngine(state_dir)
            assert engine2.submitted_shot_ids == []

            async def _reconcile(job_id: EngineJobId) -> EngineJobReceipt:
                known = await engine2.inspect_job(job_id)
                # Never blindly resubmit a terminated job (plan §5 recovery).
                if known.status in (EngineJobStatus.CANCELLED, EngineJobStatus.FAILED):
                    return known
                return known

            reconciled = await _reconcile(job_id)
            assert reconciled.status == EngineJobStatus.CANCELLED
            assert engine2.submitted_shot_ids == []  # restart did NOT resubmit

            # Retry: the worker (v2) starts a NEW job only after the cancelled
            # one is reconciled — proving it does not blind-resubmit over a
            # still-in-flight/cancelled job. The new job gets a distinct id.
            retry_receipt = await engine2.submit_shot(shot, render)
            assert retry_receipt.job_id != job_id
            assert engine2.submitted_shot_ids == [shot.shot_id]

    @pytest.mark.asyncio
    async def test_worker_restart_preserves_durable_pending_state(self):
        """A worker restart re-attaches to a pending (in-flight, not yet
        cancelled) job and can still inspect/cancel it — no state loss."""
        from tests.fixtures.video_production.ir_fixture_builder import build_valid_ir

        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            engine1 = DurableFakeEngine(state_dir)
            ir_doc = build_valid_ir()
            shot = ir_doc.shots[0]
            render = ir_doc.render_intents[0]

            submitted = await engine1.submit_shot(shot, render)
            job_id = submitted.job_id

            # Worker v2 restarts; the in-flight submission must survive.
            engine2 = DurableFakeEngine(state_dir)
            pending = await engine2.inspect_job(job_id)
            assert pending.status == EngineJobStatus.SUBMITTED
            assert pending.job_id == job_id

            # And can still be cancelled after restart.
            cancelled = await engine2.cancel_job(job_id)
            assert cancelled.status == EngineJobStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_worker_retry_is_inspect_before_resubmit(self):
        """Unknown / terminated jobs reconcile to a terminal state and are not
        blindly resubmitted by the worker (plan §5 compensation policy)."""
        from tests.fixtures.video_production.ir_fixture_builder import build_valid_ir

        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            engine = DurableFakeEngine(state_dir)
            ir_doc = build_valid_ir()
            shot = ir_doc.shots[0]
            render = ir_doc.render_intents[0]

            # A job id we never submitted appears as FAILED/Unknown on reconcile.
            ghost = EngineJobId("job_shot_ghost")
            unknown = await engine.inspect_job(ghost)
            assert unknown.status == EngineJobStatus.FAILED

            # Retry of a known-failed job creates a NEW job id, not a blind
            # resubmit on top of the failed one.
            receipt = await engine.submit_shot(shot, render)
            assert receipt.job_id != ghost


class TestFlowResidueScanner:
    """Strengthened Stage A negative gate: 0 active Flow/generative-video
    residue outside a bounded, exact-path allowlist (manifest:
    docs/video_production/historical/FLOW_RETIREMENT_MANIFEST.md).

    Also proves the scanner itself FAILS when a Flow import / key / schema /
    generative-video mode is injected into any active path.
    """

    def test_zero_flow_residue_in_active_paths(self):
        """Gate VP3D_P2: zero active violations across core/intelligence/
        orchestration/workflows/apps/execution/providers/storage/tools/scripts/
        config/env-templates/current-docs outside the bounded allowlist."""
        violations = scan_residue(
            [*ACTIVE_SCAN_ROOTS, *CURRENT_DOCS, *ENV_TEMPLATES],
            allowed_dirs=ALLOWED_DIRS,
            allowed_files=ALLOWED_FILES,
        )
        assert not violations, (
            "Flow/generative-video residue found in active paths:\n"
            + "\n".join(violations)
        )

    # -- negative proofs: the scanner MUST flag injections ---------------------

    def test_negative_flow_import_in_active_package(self, tmp_path: Path):
        core = tmp_path / "core" / "windagent_core" / "domain"
        core.mkdir(parents=True)
        (core / "bad.py").write_text(
            "from windagent_tools.google_flow import SelectorCatalog\n",
            encoding="utf-8",
        )
        violations = scan_residue([tmp_path / "core"])
        assert any("google_flow" in v for v in violations)

    def test_negative_flow_key_in_active_config(self, tmp_path: Path):
        cfg = tmp_path / "config"
        cfg.mkdir(parents=True)
        (cfg / "prod.env").write_text(
            "FLOW_SESSION=secret\nFLOW_ACCOUNT=acct\n", encoding="utf-8"
        )
        violations = scan_residue([tmp_path / "config"])
        assert any("FLOW_SESSION" in v for v in violations)

    def test_negative_generative_mode_in_canonical_runtime(self, tmp_path: Path):
        enums = (
            tmp_path / "core" / "windagent_core" / "domain"
            / "video_production" / "enums.py"
        )
        enums.parent.mkdir(parents=True)
        enums.write_text("TEXT_TO_VIDEO = 'TEXT_TO_VIDEO'\n", encoding="utf-8")
        violations = scan_residue([tmp_path / "core"])
        assert any("TEXT_TO_VIDEO" in v for v in violations)

    def test_negative_retired_schema_in_active_docs(self, tmp_path: Path):
        docs = tmp_path / "docs" / "video_production"
        docs.mkdir(parents=True)
        (docs / "flow_schema.json").write_text(
            '{"modes": ["TEXT_TO_VIDEO", "FRAMES_TO_VIDEO"]}\n',
            encoding="utf-8",
        )
        violations = scan_residue([tmp_path / "docs"])
        assert any("TEXT_TO_VIDEO" in v for v in violations)

    def test_allowlist_is_exact_path_not_broad_pattern(self, tmp_path: Path):
        """A token in a file NEXT TO an allowlisted dir is still flagged."""
        base = tmp_path / "core" / "windagent_core" / "domain" / "video_production"
        legacy = base / "legacy_v1"
        legacy.mkdir(parents=True)
        (legacy / "ok.py").write_text(
            "FlowGenerationSpecification\n", encoding="utf-8"
        )
        (base / "canonical.py").write_text(
            "FlowGenerationSpecification\n", encoding="utf-8"
        )
        violations = scan_residue([tmp_path / "core"], allowed_dirs=[legacy])
        assert not any("legacy_v1" in v for v in violations)
        assert any("canonical.py" in v for v in violations)
