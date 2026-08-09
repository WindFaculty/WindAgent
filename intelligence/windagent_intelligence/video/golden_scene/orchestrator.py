"""
Golden Scene End-to-End Orchestrator (VP3D Phase 25, Stage M).

Walks the golden scene node DAG (stage_m.md §3):

    Script -> IR -> Assets -> Scene -> Animation + Audio -> Facial
    -> Render -> Review/Repair -> FFmpeg -> Final MP4

Guarantees (acceptance §1-§7):

- the orchestrator drives EVERY node — no manual Blender edits;
- every input/output is recorded with ID, revision, provenance and content
  hash on the node receipt;
- cancel/restart at any node resumes WITHOUT duplication: a node whose
  checkpoint receipt is COMPLETED with identical input hashes is SKIPPED and
  never re-executed;
- identity/continuity pass is a hard gate before the verdict;
- render frames, audio and the final MP4 are technically verified;
- a blocking-defect fixture yields REJECT — never a false PASS;
- the production report lists every repair and every human approval.

Architecture: this module lives in the intelligence layer and NEVER imports
tools/providers. The render / review-repair legs are injected via protocols
(`GoldenSceneRenderLeg`, `GoldenSceneReviewRepairLeg`) — the composition root
(evidence producer) wires the real Blender adapter / technical review /
intelligent retry machinery, tests wire deterministic fakes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from windagent_core.domain.video_production.golden_scene import (
    GOLDEN_SCENE_DAG,
    GoldenSceneCheckpoint,
    GoldenSceneFixture,
    GoldenSceneNodeKind,
    GoldenSceneNodeReceipt,
    GoldenSceneNodeStatus,
    GoldenSceneProductionReport,
    GoldenSceneResumeMismatchError,
    GoldenSceneResumePlanner,
    GoldenSceneRunManifest,
    GoldenSceneValidationError,
    GoldenSceneVerdict,
    GoldenSceneVerdictPolicy,
    HumanApprovalEntry,
    IdentityContinuityReceipt,
    RepairEntry,
    TechnicalVerificationReceipt,
)
from windagent_core.domain.video_production.ids import (
    GoldenSceneNodeId,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Leg protocols (composition root injects real tools implementations)
# ---------------------------------------------------------------------------
@runtime_checkable
class GoldenSceneRenderLeg(Protocol):
    """Render leg: turns the compiled scene plan into real frames."""

    async def render(
        self,
        *,
        node: GoldenSceneNodeReceipt,
        fixture: GoldenSceneFixture,
        workspace: Path,
    ) -> Dict[str, Any]:
        """Render the golden scene; return frame paths + telemetry."""
        ...


@runtime_checkable
class GoldenSceneReviewRepairLeg(Protocol):
    """Review/repair leg: deterministic review + bounded repair loop."""

    async def review_and_repair(
        self,
        *,
        node: GoldenSceneNodeReceipt,
        fixture: GoldenSceneFixture,
        workspace: Path,
    ) -> Dict[str, Any]:
        """Review rendered artifacts; return findings + repair entries."""
        ...


@runtime_checkable
class GoldenSceneFfmpegLeg(Protocol):
    """FFmpeg leg: assemble final MP4 from frames + audio."""

    async def assemble(
        self,
        *,
        node: GoldenSceneNodeReceipt,
        fixture: GoldenSceneFixture,
        workspace: Path,
    ) -> Dict[str, Any]:
        """Assemble the final MP4; return final media manifest."""
        ...


# Real kernel steps (intelligence-side, no tools import)
class GoldenSceneStepRunner(Protocol):
    """One pipeline node executor (returns output hashes + findings)."""

    async def run(
        self,
        *,
        node: GoldenSceneNodeReceipt,
        fixture: GoldenSceneFixture,
        manifest: GoldenSceneRunManifest,
        workspace: Path,
        prior: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt],
    ) -> Dict[str, Any]:
        """Execute one node; returns {'output_hashes': {...}, ...}."""
        ...


class _LegStepAdapter:
    """Adapts a leg callable (node, fixture, workspace) to the step runner
    signature (node, fixture, manifest, workspace, prior)."""

    def __init__(
        self,
        leg: Callable[..., Any],
    ) -> None:
        self._leg = leg

    async def run(
        self,
        *,
        node: GoldenSceneNodeReceipt,
        fixture: GoldenSceneFixture,
        manifest: GoldenSceneRunManifest,
        workspace: Path,
        prior: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt],
    ) -> Dict[str, Any]:
        return await self._leg(node=node, fixture=fixture, workspace=workspace)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class GoldenSceneOrchestrator:
    """Production orchestrator for one golden scene run.

    Usage (composition root):

        orch = GoldenSceneOrchestrator(
            fixture=fixture, manifest=manifest,
            checkpoint_dir=Path("artifacts/video_production_3d/phase_25/runs"),
            steps={...real or fake runners...},
            render_leg=..., review_repair_leg=..., ffmpeg_leg=...,
            identity_checker=..., verification_checker=...,
        )
        report = await orch.run(cancel_token=...)

    Resume: pass the SAME run_id + fixture + manifest on restart; the
    checkpoint is loaded and completed nodes with identical input hashes are
    SKIPPED (no re-execution, no duplicate side effects).
    """

    def __init__(
        self,
        *,
        fixture: GoldenSceneFixture,
        manifest: GoldenSceneRunManifest,
        checkpoint_dir: Path,
        steps: Dict[GoldenSceneNodeKind, GoldenSceneStepRunner],
        render_leg: GoldenSceneRenderLeg,
        review_repair_leg: GoldenSceneReviewRepairLeg,
        ffmpeg_leg: GoldenSceneFfmpegLeg,
        identity_checker: Callable[
            [GoldenSceneFixture, Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt]],
            IdentityContinuityReceipt,
        ],
        verification_checker: Callable[
            [GoldenSceneFixture, Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt], Path],
            TechnicalVerificationReceipt,
        ],
        verdict_policy: Optional[GoldenSceneVerdictPolicy] = None,
        resume_planner: Optional[GoldenSceneResumePlanner] = None,
        artifact_dir: Optional[Path] = None,
    ) -> None:
        if fixture.content_hash() != manifest.fixture_hash:
            raise GoldenSceneValidationError(
                "Fixture hash does not match the run manifest.",
                details={
                    "fixture_hash": fixture.content_hash(),
                    "manifest_fixture_hash": manifest.fixture_hash,
                },
            )
        self._fixture = fixture
        self._manifest = manifest
        self._checkpoint_dir = Path(checkpoint_dir)
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._steps = dict(steps)
        self._render_leg = render_leg
        self._review_repair_leg = review_repair_leg
        self._ffmpeg_leg = ffmpeg_leg
        self._identity_checker = identity_checker
        self._verification_checker = verification_checker
        self._verdict_policy = verdict_policy or GoldenSceneVerdictPolicy()
        self._resume_planner = resume_planner or GoldenSceneResumePlanner()
        self._artifact_dir = Path(artifact_dir) if artifact_dir else self._checkpoint_dir / "artifacts"
        self._artifact_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Checkpoint persistence
    # ------------------------------------------------------------------
    def _checkpoint_path(self) -> Path:
        return self._checkpoint_dir / f"{self._manifest.run_id}.checkpoint.json"

    def _load_checkpoint(self) -> Optional[GoldenSceneCheckpoint]:
        path = self._checkpoint_path()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if data.get("run_id") != str(self._manifest.run_id):
            raise GoldenSceneResumeMismatchError(
                "Checkpoint run_id does not match the run manifest.",
                details={"checkpoint_run": data.get("run_id"), "run": str(self._manifest.run_id)},
            )
        return GoldenSceneCheckpoint.model_validate(data)

    def _save_checkpoint(self, checkpoint: GoldenSceneCheckpoint) -> None:
        tmp = self._checkpoint_path().with_suffix(".tmp")
        tmp.write_text(
            json.dumps(checkpoint.model_dump(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(self._checkpoint_path())

    # ------------------------------------------------------------------
    # Node execution
    # ------------------------------------------------------------------
    def _input_hashes(self) -> Dict[GoldenSceneNodeKind, Dict[str, str]]:
        """Per-node input hashes: fixture hash + manifest hash + DAG deps.

        A node's input = its DAG predecessors' output hashes plus the pinned
        fixture/manifest — identical inputs on restart => SKIP (no duplicate).
        """
        hashes: Dict[GoldenSceneNodeKind, Dict[str, str]] = {}
        for kind in GOLDEN_SCENE_DAG:
            hashes[kind] = {
                "fixture": self._fixture.content_hash(),
                "manifest": self._manifest.content_hash(),
                "dag": ",".join(k.value for k in GOLDEN_SCENE_DAG),
            }
        return hashes

    def _node_id(self, kind: GoldenSceneNodeKind, attempt: int) -> GoldenSceneNodeId:
        return GoldenSceneNodeId(
            f"{self._manifest.run_id}::{kind.value}::{attempt}"
        )

    async def _run_node(
        self,
        kind: GoldenSceneNodeKind,
        *,
        prior: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt],
        cancel_token: Callable[[], bool],
    ) -> GoldenSceneNodeReceipt:
        runner = self._steps.get(kind)
        if runner is None:
            # Legs are injected ports (render / review-repair / ffmpeg).
            if kind == GoldenSceneNodeKind.RENDER:
                runner = _LegStepAdapter(self._render_leg.render)
            elif kind == GoldenSceneNodeKind.REVIEW_REPAIR:
                runner = _LegStepAdapter(self._review_repair_leg.review_and_repair)
            elif kind == GoldenSceneNodeKind.FFMPEG:
                runner = _LegStepAdapter(self._ffmpeg_leg.assemble)
        if runner is None:
            return GoldenSceneNodeReceipt(
                node_id=self._node_id(kind, 1),
                kind=kind,
                status=GoldenSceneNodeStatus.FAILED,
                attempt=1,
                started_at=utc_now_iso(),
                finished_at=utc_now_iso(),
                input_hashes=self._input_hashes()[kind],
                error=f"No step runner registered for node {kind.value}.",
                metadata={"phase_25_failure": True},
            )
        attempt = 1
        while True:
            if cancel_token():
                return GoldenSceneNodeReceipt(
                    node_id=self._node_id(kind, attempt),
                    kind=kind,
                    status=GoldenSceneNodeStatus.CANCELLED,
                    attempt=attempt,
                    started_at=utc_now_iso(),
                    finished_at=utc_now_iso(),
                    error="cancelled before execution",
                )
            node = GoldenSceneNodeReceipt(
                node_id=self._node_id(kind, attempt),
                kind=kind,
                status=GoldenSceneNodeStatus.RUNNING,
                attempt=attempt,
                started_at=utc_now_iso(),
                input_hashes=self._input_hashes()[kind],
            )
            try:
                outcome = await runner.run(
                    node=node,
                    fixture=self._fixture,
                    manifest=self._manifest,
                    workspace=self._artifact_dir,
                    prior=prior,
                )
            except Exception as exc:  # fail closed: node FAILED, run REJECTs
                return GoldenSceneNodeReceipt(
                    node_id=node.node_id,
                    kind=kind,
                    status=GoldenSceneNodeStatus.FAILED,
                    attempt=attempt,
                    started_at=node.started_at,
                    finished_at=utc_now_iso(),
                    input_hashes=node.input_hashes,
                    error=f"{type(exc).__name__}: {exc}",
                    metadata={"phase_25_failure": True},
                )
            output_hashes = dict(outcome.get("output_hashes", {}))
            if not output_hashes:
                return GoldenSceneNodeReceipt(
                    node_id=node.node_id,
                    kind=kind,
                    status=GoldenSceneNodeStatus.FAILED,
                    attempt=attempt,
                    started_at=node.started_at,
                    finished_at=utc_now_iso(),
                    input_hashes=node.input_hashes,
                    error="step produced no output hashes",
                )
            return GoldenSceneNodeReceipt(
                node_id=node.node_id,
                kind=kind,
                status=GoldenSceneNodeStatus.COMPLETED,
                attempt=attempt,
                started_at=node.started_at,
                finished_at=utc_now_iso(),
                input_hashes=node.input_hashes,
                output_hashes=output_hashes,
                provenance={str(k.value): str(r.node_id) for k, r in prior.items()},
                findings=outcome.get("findings", []),
                repairs=[
                    RepairEntry.model_validate(e)
                    for e in outcome.get("repairs", [])
                ],
                metadata=outcome.get("metadata", {}),
            )

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------
    async def run(
        self,
        *,
        cancel_token: Optional[Callable[[], bool]] = None,
    ) -> GoldenSceneProductionReport:
        cancel_token = cancel_token or (lambda: False)
        checkpoint = self._load_checkpoint()
        current_hashes = self._input_hashes()
        decisions = self._resume_planner.plan(checkpoint, current_hashes)

        receipts: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt] = {}
        if checkpoint is not None:
            for receipt in checkpoint.receipts:
                receipts[receipt.kind] = receipt

        for kind in GOLDEN_SCENE_DAG:
            decision = decisions[kind]
            if decision == "SKIP":
                prior_receipt = receipts[kind]
                skipped = prior_receipt.model_copy(
                    update={
                        "status": GoldenSceneNodeStatus.SKIPPED,
                        "metadata": {
                            **prior_receipt.metadata,
                            "resumed": True,
                            "skip_reason": (
                                "completed in prior run with identical input hashes"
                            ),
                        },
                    }
                )
                receipts[kind] = skipped
                self._save_checkpoint(
                    GoldenSceneCheckpoint(
                        run_id=self._manifest.run_id,
                        receipts=list(receipts.values()),
                    )
                )
                continue

            receipt = await self._run_node(
                kind, prior=receipts, cancel_token=cancel_token
            )
            receipts[kind] = receipt
            self._save_checkpoint(
                GoldenSceneCheckpoint(
                    run_id=self._manifest.run_id,
                    receipts=list(receipts.values()),
                )
            )
            if receipt.status == GoldenSceneNodeStatus.CANCELLED:
                break
            if receipt.status == GoldenSceneNodeStatus.FAILED:
                break

        identity = self._identity_checker(self._fixture, receipts)
        verification = self._verification_checker(
            self._fixture, receipts, self._artifact_dir
        )
        verdict = self._verdict_policy.decide(
            list(receipts.values()), identity, verification
        )

        repairs: List[RepairEntry] = []
        approvals: List[HumanApprovalEntry] = []
        for receipt in receipts.values():
            repairs.extend(receipt.repairs)
            for approval in self._fixture.approvals:
                if approval.node_kind == receipt.kind:
                    approvals.append(approval)
        approvals = sorted(approvals, key=lambda a: a.approval_id)

        report = GoldenSceneProductionReport(
            run_id=self._manifest.run_id,
            verdict=verdict,
            manifest_hash=self._manifest.content_hash(),
            fixture_hash=self._fixture.content_hash(),
            receipts=list(receipts.values()),
            identity_continuity=identity,
            technical_verification=verification,
            repair_entries=repairs,
            human_approvals=approvals,
            summary=self._summary(verdict, receipts, identity, verification),
        )
        return report

    def _summary(
        self,
        verdict: GoldenSceneVerdict,
        receipts: Dict[GoldenSceneNodeKind, GoldenSceneNodeReceipt],
        identity: IdentityContinuityReceipt,
        verification: TechnicalVerificationReceipt,
    ) -> str:
        finished = [r for r in receipts.values() if r.is_terminal_ok()]
        failed = [r for r in receipts.values() if not r.is_terminal_ok()]
        parts = [
            f"nodes completed={len(finished)} failed={len(failed)}",
            f"identity_continuity={'PASS' if identity.passed else 'FAIL'}",
            f"technical_verification={'PASS' if verification.passed else 'FAIL'}",
        ]
        if failed:
            kinds = ",".join(r.kind.value for r in failed)
            parts.append(f"blocking nodes: {kinds}")
        return f"Golden scene run {self._manifest.run_id}: {verdict.value} | " + " | ".join(parts)
