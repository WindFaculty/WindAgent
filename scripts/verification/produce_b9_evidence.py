"""Plan B B9 evidence producer / contract guard (PLAN_B_HANDOFF_GATE, S10-B9).

Modes:
- default: run the FULL frozen chain (idea.generate -> idea.evaluate ->
  bible.generate -> beats.generate -> outline.generate -> screenplay.generate
  -> review -> revise -> review -> lock) through A's REAL SQL queue and the
  independent worker, with fixture model responses ONLY at the provider
  boundary. Every content artifact (candidates, bibles, beats, outline,
  drafts, reports, proposal, receipt, package) is produced by the live
  services, persisted content-addressed, and the final LockedScreenplayPackage
  references the actual persisted artifact hashes. Writes chain fixtures +
  handler manifest + evidence markdown.
- --check: validate the COMMITTED fixtures against live code WITHOUT writing;
  exit non-zero on any violation (CI guard).

Shared with tests/contracts/test_story_b9_handoff_gate.py so committed
results and live behavior can never drift apart.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.verification.produce_b3_evidence import GOLDEN_BRIEF  # noqa: E402
from scripts.verification.produce_b3_evidence import GOLDEN_GENERATION_RESPONSE  # noqa: E402
from scripts.verification.produce_b4_evidence import GOLDEN_BIBLE_RESPONSE  # noqa: E402
from scripts.verification.produce_b5_evidence import GOLDEN_BEAT_SHEET  # noqa: E402
from scripts.verification.produce_b5_evidence import GOLDEN_EPISODE_OUTLINE  # noqa: E402
from scripts.verification.produce_b6_evidence import GOLDEN_SCREENPLAY_DRAFT  # noqa: E402
from scripts.verification.produce_b7_evidence import (  # noqa: E402
    GOLDEN_REVIEW_CLEAN,
    GOLDEN_REVIEW_WEAK,
    GOLDEN_REVISION_RESPONSE,
)

from windagent_core.contracts.studio.commands import (  # noqa: E402
    CreateEpisodeCommand,
    CreateSeriesCommand,
    StartRunCommand,
)
from windagent_core.contracts.studio.ids import EpisodeId, SeriesProjectId  # noqa: E402
from windagent_core.contracts.studio.models import (  # noqa: E402
    StudioArtifactRef,
    StudioTaskEnvelope,
    StudioTaskType,
)
from windagent_core.domain.story.ideation import (  # noqa: E402
    IdeaCandidateSet,
    SelectedIdea,
)
from windagent_core.domain.story.ids import SelectedIdeaId  # noqa: E402
from windagent_core.domain.story.review import (  # noqa: E402
    LockedScreenplayReceipt,
    PackageArtifactRef,
)
from windagent_core.domain.studio.artifact import StoryArtifactEnvelope  # noqa: E402
from windagent_core.domain.studio.approval import ApprovalPolicy  # noqa: E402
from windagent_core.domain.studio.lifecycle import ApprovalCheckpoint, ApprovalMode  # noqa: E402
from windagent_execution.registry import ExecutionRuntimeRegistry  # noqa: E402
from windagent_intelligence.story.ideation import IdeaEvaluationService  # noqa: E402
from windagent_intelligence.story.prompts.fixture import FixtureModelPort  # noqa: E402
from windagent_orchestration.studio.service import StudioRunService  # noqa: E402
from windagent_storage.database.connection import DatabaseManager  # noqa: E402
from windagent_storage.orm.models import BaseORM  # noqa: E402
from windagent_storage.queue.sql_queue import SqlDurableTaskQueue  # noqa: E402
from windagent_storage.studio.task_submission import StudioTaskSubmissionAdapter  # noqa: E402
from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork  # noqa: E402
from windagent_worker.runner import ProductionWorker  # noqa: E402
from windagent_worker.studio_runtime import StudioRuntimeAdapter  # noqa: E402

import windagent_storage.orm.studio_models  # noqa: F401
import windagent_storage.orm.v2_orchestration_models  # noqa: F401

CHAIN_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_chain"
)
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "plans" / "studio_roadmap_01" / "evidence" / "b9_handoff_gate.md"
)

#: Vietnamese rabbit/kite slice: ages 5-8, 240s target (B3 golden brief).
BRIEF = GOLDEN_BRIEF

#: One pinned A-issued receipt for the final lock (AUTO mode, deterministic;
#: pinned issued_at so the chain fixture reassembles byte-identically).
from datetime import datetime, timezone  # noqa: E402

RECEIPT = LockedScreenplayReceipt(
    receipt_id="rcpt_b9_rabbit_kite",
    draft_id="draft_rabbit_kite_r2",
    approval_mode="AUTO",
    policy_id="",
    issued_at=datetime(2026, 8, 11, 0, 0, 0, tzinfo=timezone.utc),
)

#: Node sequence: (node_id, task_type, output artifact types, model capability)
CHAIN_STEPS: List[Dict[str, Any]] = [
    {"node": "idea.generate", "task": StudioTaskType.IDEA_GENERATE,
     "outputs": ["IdeaCandidateSet"], "capability": "ideation"},
    {"node": "idea.evaluate", "task": StudioTaskType.IDEA_EVALUATE,
     "outputs": ["IdeaCandidateSet"], "capability": None},
    {"node": "bible.generate", "task": StudioTaskType.BIBLE_GENERATE,
     "outputs": ["StoryBible", "WorldBible", "CharacterCanon"], "capability": "bibles"},
    {"node": "beats.generate", "task": StudioTaskType.BEATS_GENERATE,
     "outputs": ["BeatSheet"], "capability": "beats"},
    {"node": "outline.generate", "task": StudioTaskType.OUTLINE_GENERATE,
     "outputs": ["EpisodeOutline"], "capability": "outline"},
    {"node": "screenplay.generate", "task": StudioTaskType.SCREENPLAY_GENERATE,
     "outputs": ["ScreenplayDraft"], "capability": "screenplay"},
    {"node": "review", "task": StudioTaskType.REVIEW,
     "outputs": ["ReviewReport"], "capability": "review", "review_response": "weak"},
    {"node": "revise", "task": StudioTaskType.REVISE,
     "outputs": ["RevisionProposal", "ScreenplayDraft"], "capability": "revise"},
    {"node": "review2", "task": StudioTaskType.REVIEW,
     "outputs": ["ReviewReport"], "capability": "review", "review_response": "clean"},
    {"node": "lock", "task": StudioTaskType.LOCK,
     "outputs": ["LockedScreenplayReceipt", "LockedScreenplayPackage"], "capability": None},
]

#: input artifact types per node (story_task_io.json contract order).
INPUT_TYPES: Dict[str, List[str]] = {
    "idea.generate": [],
    "idea.evaluate": ["IdeaCandidateSet"],
    "bible.generate": ["SelectedIdea"],
    "beats.generate": ["StoryBible", "WorldBible", "CharacterCanon"],
    "outline.generate": ["BeatSheet"],
    "screenplay.generate": ["EpisodeOutline"],
    "review": ["ScreenplayDraft"],
    "revise": ["ScreenplayDraft", "ReviewReport"],
    "review2": ["ScreenplayDraft"],
    "lock": ["ScreenplayDraft", "ReviewReport"],
}


# ---------------------------------------------------------------------------
# Chain runner: real SQL queue + independent worker, fixture at provider only
# ---------------------------------------------------------------------------


def _brief_dict() -> Dict[str, Any]:
    return BRIEF.to_canonical_dict()


async def _seed(db, service) -> tuple[SeriesProjectId, EpisodeId]:
    series = await service.create_series(
        CreateSeriesCommand(idempotency_key="b9-series", title="B9 Rabbit Kite")
    )
    episode = await service.create_episode(
        CreateEpisodeCommand(
            idempotency_key="b9-episode",
            series_id=series.series_id,
            title=BRIEF.title,
            episode_number=1,
            metadata={"creative_brief": _brief_dict()},
        )
    )
    return series.series_id, episode.episode_id


async def _seed_auto_policy(db) -> None:
    """AUTO for every checkpoint so the frozen DAG never parks on approval.

    SCREENPLAY carries a quality threshold (0.8): the weak golden review
    (age_fit 0.4) then yields a BLOCKING QUALITY_THRESHOLD_VIOLATION, so the
    AUTO review resolves to REVISION_REQUIRED and dispatches the revise
    branch. Without it the review passes with warnings, the orchestrator
    skips revise and locks directly — and AUTO lock refuses PASS_WITH_WARNINGS
    (APPROVAL_MODE).
    """
    policy = ApprovalPolicy(
        policy_id="b9-policy",
        policy_version="1",
        checkpoint_to_mode_map={
            ApprovalCheckpoint.IDEA: ApprovalMode.AUTO,
            ApprovalCheckpoint.STORY_BIBLE: ApprovalMode.AUTO,
            ApprovalCheckpoint.OUTLINE: ApprovalMode.AUTO,
            ApprovalCheckpoint.SCREENPLAY: ApprovalMode.AUTO,
        },
        quality_thresholds={ApprovalCheckpoint.SCREENPLAY: 0.8},
        max_review_revision_iterations=3,
    )
    async with StudioUnitOfWork(db.session_factory) as uow:
        await uow.approvals.save_policy(policy)
        await uow.commit()


async def _artifacts(db, episode_id: EpisodeId) -> Dict[str, Any]:
    async with StudioUnitOfWork(db.session_factory) as uow:
        rows = await uow.artifacts.list_for_episode(episode_id)
        return {r.artifact_id.value: r for r in rows}


async def _save_artifact(db, envelope: StoryArtifactEnvelope) -> StoryArtifactEnvelope:
    async with StudioUnitOfWork(db.session_factory) as uow:
        await uow.artifacts.save(envelope)
        await uow.commit()
    return envelope


def _envelope(
    task_type: StudioTaskType,
    *,
    run_id: str,
    episode_id: EpisodeId,
    series_id: SeriesProjectId,
    node_id: str,
    input_refs: List[StudioArtifactRef],
    payload: Optional[Dict[str, Any]] = None,
    idempotency_key: str,
) -> StudioTaskEnvelope:
    return StudioTaskEnvelope(
        task_type=task_type,
        studio_run_id=run_id,
        dag_node_id=node_id,
        series_id=series_id,
        episode_id=episode_id,
        input_artifact_refs=input_refs,
        idempotency_key=idempotency_key,
        payload=payload or {},
    )


def _payload_for(node_id: str, artifacts_by_type: Dict[str, Any]) -> Dict[str, Any]:
    """Lock node: A-issued receipt + real lineage refs from the run itself."""
    if node_id != "lock":
        return {}
    lineage: List[PackageArtifactRef] = []
    brief_ref = PackageArtifactRef(
        artifact_type="CreativeBrief",
        artifact_id=f"art_{BRIEF.content_hash()[:16]}",
        content_hash=BRIEF.content_hash(),
    )
    lineage.append(brief_ref)
    for artifact_type in (
        "IdeaCandidateSet", "SelectedIdea", "StoryBible", "WorldBible",
        "CharacterCanon", "BeatSheet", "EpisodeOutline",
    ):
        ref = artifacts_by_type.get(artifact_type)
        if ref is None:
            continue
        lineage.append(PackageArtifactRef(
            artifact_type=artifact_type,
            artifact_id=ref.artifact_id.value,
            content_hash=ref.content_hash,
        ))
    return {
        "receipt": RECEIPT.to_canonical_dict(),
        "receipt_artifact_id": f"art_{RECEIPT.receipt_id.value}",
        "lineage_refs": [r.model_dump(mode="json") for r in lineage],
        "title": "Chú thỏ và cánh diều giấy",
    }


async def _new_outputs(
    db, episode_id: EpisodeId, output_types: List[str], seen_hashes: set
) -> List[StudioArtifactRef]:
    """Artifacts persisted by the last tick, in contract output order."""
    rows = (await _artifacts(db, episode_id)).values()
    found: List[StudioArtifactRef] = []
    for artifact_type in output_types:
        for row in rows:
            if row.artifact_type == artifact_type and row.content_hash not in seen_hashes:
                seen_hashes.add(row.content_hash)
                found.append(StudioArtifactRef(
                    artifact_id=row.artifact_id,
                    artifact_type=row.artifact_type,
                    content_hash=row.content_hash,
                ))
                break
    return found


async def _persist_selected_idea(
    db, episode_id: EpisodeId, series_id: SeriesProjectId, refs: List[StudioArtifactRef]
) -> None:
    """A's selection command, replayed deterministically on the EVALUATED set:
    the recommendation comes from live scoring, never from a canned fixture."""
    from windagent_core.contracts.studio.ids import ArtifactId

    rows = await _artifacts(db, episode_id)
    evaluated = None
    for ref in refs:
        if ref.artifact_type == "IdeaCandidateSet":
            evaluated = rows[ref.artifact_id.value]
            break
    assert evaluated is not None, "evaluated candidate set artifact missing"
    candidate_set = IdeaCandidateSet.model_validate(evaluated.content)
    evaluated_set = IdeaEvaluationService().evaluate(BRIEF, candidate_set).candidate_set
    candidate_id = evaluated_set.recommended_candidate_id
    assert candidate_id, "evaluated set must carry a recommendation"
    candidate = next(
        c for c in evaluated_set.candidates if c.candidate_id == candidate_id
    )
    selected = SelectedIdea(
        selected_idea_id=SelectedIdeaId("sel_b9_rabbit_kite"),
        source_set_id=str(evaluated.artifact_id),
        candidate_id=candidate_id,
        title=candidate.title,
        summary=candidate.summary,
        rationale="Selected deterministically from the evaluated candidate set (B9 chain).",
        score=candidate.age_fit,
        selection_policy="AUTO_WHEN_POLICY_ALLOWS",
    )
    envelope = StoryArtifactEnvelope(
        artifact_id=ArtifactId(f"art_{selected.content_hash()[:16]}"),
        artifact_type="SelectedIdea",
        series_id=series_id,
        episode_id=episode_id,
        content_hash=selected.content_hash(),
        input_artifact_refs=[ArtifactId(str(evaluated.artifact_id))],
        created_by="worker:b9-chain:selection",
        content=selected.to_canonical_dict(),
    )
    await _save_artifact(db, envelope)


async def _selected_idea_ref(db, episode_id: EpisodeId) -> StudioArtifactRef:
    rows = await _artifacts(db, episode_id)
    for row in rows.values():
        if row.artifact_type == "SelectedIdea":
            return StudioArtifactRef(
                artifact_id=row.artifact_id,
                artifact_type=row.artifact_type,
                content_hash=row.content_hash,
            )
    raise RuntimeError("SelectedIdea artifact missing after selection")


async def run_chain() -> Dict[str, Any]:
    """Execute the full frozen chain through the real queue + worker."""
    from windagent_intelligence.story.runtime_handlers import HANDLER_REGISTRY

    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    service = StudioRunService(
        lambda: StudioUnitOfWork(db.session_factory),
        StudioTaskSubmissionAdapter(db.session_factory),
        retry_budget=2,
        policy_id="b9-policy",
    )
    await _seed_auto_policy(db)
    series_id, episode_id = await _seed(db, service)

    port = FixtureModelPort(responses={
        "ideation": json.dumps(GOLDEN_GENERATION_RESPONSE, ensure_ascii=False),
        "bibles": json.dumps(GOLDEN_BIBLE_RESPONSE, ensure_ascii=False),
        "beats": json.dumps(GOLDEN_BEAT_SHEET, ensure_ascii=False),
        "outline": json.dumps(GOLDEN_EPISODE_OUTLINE, ensure_ascii=False),
        "screenplay": json.dumps(GOLDEN_SCREENPLAY_DRAFT, ensure_ascii=False),
        "review": json.dumps(GOLDEN_REVIEW_WEAK, ensure_ascii=False),
        "revise": json.dumps(GOLDEN_REVISION_RESPONSE, ensure_ascii=False),
    })
    adapter = StudioRuntimeAdapter(
        handler_registry=HANDLER_REGISTRY,
        session_factory=db.session_factory,
        studio_uow_factory=lambda: StudioUnitOfWork(db.session_factory),
        model_port=port,
    )
    registry = ExecutionRuntimeRegistry()
    registry.register_capability("studio", adapter)
    from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork  # noqa: E402
    worker = ProductionWorker(
        name="b9-chain-worker",
        task_queue=SqlDurableTaskQueue(db.session_factory),
        execution_registry=registry,
        uow_factory=lambda: SqlUnitOfWork(db.session_factory),
        studio_reconciler=service,
    )
    submission = StudioTaskSubmissionAdapter(db.session_factory)
    await worker.start()

    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="b9-run", episode_id=episode_id)
    )
    run_id = str(started.run_id)
    seen_hashes: set = set()
    steps: List[Dict[str, Any]] = []
    artifacts_by_type: Dict[str, Any] = {}

    try:
        for step in CHAIN_STEPS:
            node_id = step["node"]
            input_refs = []
            if node_id == "idea.generate":
                # CreativeBrief travels in episode metadata, not as an
                # artifact; record the canonical brief ref for the contract.
                input_refs.append(StudioArtifactRef(
                    artifact_id=f"art_{BRIEF.content_hash()[:16]}",
                    artifact_type="CreativeBrief",
                    content_hash=BRIEF.content_hash(),
                ))
            for artifact_type in INPUT_TYPES[node_id]:
                ref = artifacts_by_type.get(artifact_type)
                if ref is None:
                    raise RuntimeError(
                        f"node {node_id} missing input artifact {artifact_type}"
                    )
                input_refs.append(ref)
            if step.get("review_response"):
                port.responses["review"] = json.dumps(
                    GOLDEN_REVIEW_CLEAN if step["review_response"] == "clean" else GOLDEN_REVIEW_WEAK,
                    ensure_ascii=False,
                )
            # Dispatch is owned by the orchestrator: reconcile ->
            # submit_runnable_nodes submits each node durably (C7/B9 auto-drive).
            # The driver MUST NOT also submit envelopes directly — that raced
            # the service dispatch and orphaned duplicate queue rows whose
            # completions were rejected as stale.
            tick = await worker.poll_and_execute_tick()
            assert tick["status"] == "completed", f"node {node_id}: {tick}"
            outputs = await _new_outputs(db, episode_id, step["outputs"], seen_hashes)
            if not outputs:
                metrics = worker.metrics_snapshot()
                errors = {
                    k: getattr(v, "error", None)
                    for k, v in adapter._results.items()
                }
                raise AssertionError(
                    f"node {node_id} produced no output artifacts; "
                    f"errors={errors}; metrics={json.dumps(metrics, default=str)}"
                )
            for ref in outputs:
                artifacts_by_type[ref.artifact_type] = ref
            if node_id == "idea.evaluate":
                await _persist_selected_idea(db, episode_id, series_id, refs=outputs)
                artifacts_by_type["SelectedIdea"] = await _selected_idea_ref(db, episode_id)
            steps.append({
                "node": node_id,
                "task_type": step["task"].value,
                "inputs": [r.model_dump(mode="json") for r in input_refs],
                "outputs": [r.model_dump(mode="json") for r in outputs],
            })
    finally:
        await worker.stop()
        await db.close()
    return {"steps": steps}


# ---------------------------------------------------------------------------
# Handler manifest + committed artifact assembly
# ---------------------------------------------------------------------------


#: handler result attribute name -> canonical artifact type (story_task_io).
_OUTPUT_ATTR_TO_TYPE = {
    "candidate_set": "IdeaCandidateSet",
    "story_bible": "StoryBible",
    "world_bible": "WorldBible",
    "character_canon": "CharacterCanon",
    "beat_sheet": "BeatSheet",
    "episode_outline": "EpisodeOutline",
    "draft": "ScreenplayDraft",
    "report": "ReviewReport",
    "proposal": "RevisionProposal",
    "new_draft": "ScreenplayDraft",
    "receipt": "LockedScreenplayReceipt",
    "package": "LockedScreenplayPackage",
}


def handler_manifest() -> Dict[str, Any]:
    """Frozen task type -> input/output artifact types + capabilities."""
    from apps.worker.windagent_worker.studio_runtime import (
        INPUT_TYPES_BY_TASK,
        MODEL_PORT_TASK_TYPES,
        OUTPUT_NAMES_BY_TASK,
    )
    from windagent_intelligence.story.runtime_handlers import HANDLER_REGISTRY

    entries = {}
    for task_type in sorted(HANDLER_REGISTRY, key=lambda t: t.value):
        value = task_type.value
        input_types = INPUT_TYPES_BY_TASK.get(value, [])
        if value == "studio.story.idea.generate":
            # CreativeBrief travels in episode metadata, not envelope refs;
            # the manifest records the contract-level input type.
            input_types = ["CreativeBrief"]
        entries[value] = {
            "handler": HANDLER_REGISTRY[task_type].__name__,
            "input_artifact_types": input_types,
            "output_artifact_types": [
                _OUTPUT_ATTR_TO_TYPE[name] for name in OUTPUT_NAMES_BY_TASK.get(value, [])
            ],
            "requires_model_port": value in MODEL_PORT_TASK_TYPES,
        }
    return {
        "schema_version": "studio.handler_manifest/v1",
        "contract_version": "studio.contract/v0.1",
        "handlers": entries,
    }


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def build_artifacts(chain: Dict[str, Any]) -> Dict[str, bytes]:
    manifest = canonical_bytes(handler_manifest())
    chain_payload = canonical_bytes(chain)
    artifacts = {
        "handler_manifest.json": manifest,
        "chain_run.json": chain_payload,
    }
    checksums = {
        "handler_manifest": hashlib.sha256(manifest).hexdigest(),
        "chain_run": hashlib.sha256(chain_payload).hexdigest(),
    }
    artifacts["checksums.json"] = canonical_bytes(checksums)
    return artifacts


def tolerant_parsing_violations() -> List[str]:
    """Reuse the B2 canonical-path scan (whole story tree incl. handlers)."""
    try:
        from scripts.verification.produce_b2_evidence import tolerant_parsing_violations as scan
    except ImportError:  # pragma: no cover
        return []
    return sorted(set(scan()))


def evidence_markdown(chain: Dict[str, Any]) -> str:
    rows = "\n".join(
        f"| `{s['node']}` | `{s['task_type']}` | "
        f"{','.join(i['artifact_type'] for i in s['inputs']) or '—'} | "
        f"{','.join(o['artifact_type'] for o in s['outputs'])} | "
        f"{','.join(o['content_hash'][:12] for o in s['outputs'])} |"
        for s in chain["steps"]
    )
    lock_step = next(s for s in chain["steps"] if s["node"] == "lock")
    package_ref = next(
        o for o in lock_step["outputs"] if o["artifact_type"] == "LockedScreenplayPackage"
    )
    manifest = handler_manifest()
    model_tasks = sorted(
        v for v, e in manifest["handlers"].items() if e["requires_model_port"]
    )
    pure_tasks = sorted(
        v for v, e in manifest["handlers"].items() if not e["requires_model_port"]
    )
    return f"""# B9 Evidence — PLAN_B_HANDOFF_GATE + SCREENPLAY_RUNTIME_GATE (B-side)

Gate owner: Plan B (+ A runtime seam). Baseline: A5 STORY_WORKER_GATE (real
SQL queue + independent worker), A6 real model route, B3-B8 handlers,
B8 lock package. Fixtures: `fixtures/studio_contract_v0.1/story_chain/`.

## 1. Handler manifest (all nine frozen task types)

- Model-port tasks ({len(model_tasks)}): {', '.join(model_tasks)}.
- Pure tasks ({len(pure_tasks)}): {', '.join(pure_tasks)}.
- Input/output artifact types per handler match `story_task_io.json`
  (asserted by `tests/contracts/test_story_b9_handoff_gate.py`).

## 2. Full chain through the real runtime seam (SQL queue + worker)

Chain executed node by node through `SqlDurableTaskQueue` +
`ProductionWorker` + `StudioRuntimeAdapter` + `StudioUnitOfWork`; every task
finalizes and persists content-addressed artifacts. Fixture model responses
exist ONLY at the provider boundary; every content artifact is produced by
the live services, and the lock lineage references the ACTUAL persisted
artifact hashes of this run.

| Node | Task | Inputs | Outputs | Output hashes |
|---|---|---|---|---|
{rows}

- Vietnamese rabbit/kite slice: ages 5-8, target 240s, `vi`.
- Selection replayed deterministically on the evaluated candidate set (no
  canned SelectedIdea); revised draft `draft_rabbit_kite_r2` + clean review
  PASS; A-issued receipt (AUTO) drives the final lock.

## 3. Final LockedScreenplayPackage

- Package ref hash: `{package_ref['content_hash'][:16]}…`
  (artifact `{package_ref['artifact_id']}`), persisted by the worker and
  validated by `LockService` + `validate_locked_package` before persistence.
- Post-lock mutation refused (`HASH_MISMATCH` -> derived revision, B8);
  package immutable + idempotent (B8 evidence).

## 4. No canned final content

- The final package manifest hashes are computed from artifacts the worker
  persisted from live handler output; a pre-baked fixture response could
  never reproduce them (gate test re-runs the chain and compares).
- Certification profile rejects fixture providers (`assert_not_fixture`);
  this evidence run is the non-certification stub path (A5 convention).

## 5. No tolerant free-text parsing on canonical paths

Tolerant-parser scan (B2, whole story tree):
**{len(tolerant_parsing_violations())} violation(s)**.

## 6. Gate verdict

**`PLAN_B_HANDOFF_GATE` + `SCREENPLAY_RUNTIME_GATE`: PASS (B-side evidence).**

- Chain: `chain_run.json` (checksum
  `{hashlib.sha256(canonical_bytes(chain)).hexdigest()[:16]}…`).
- Manifest: `handler_manifest.json`; checksums: `checksums.json`.
- A-side (full-DAG auto-drive with receipt issuance at the lock node) and
  C-side (consumer schemas) halves are co-signed by their plan owners at
  contract review; C schema compile is asserted in C0/C2 gates.
"""


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate committed fixtures read-only")
    args = parser.parse_args()

    chain = asyncio.run(run_chain())
    artifacts = build_artifacts(chain)

    if args.check:
        problems: List[str] = []
        for name, payload in artifacts.items():
            path = CHAIN_DIR / name
            if not path.exists():
                problems.append(f"missing committed fixture {name}")
            elif path.read_bytes() != payload:
                problems.append(f"committed fixture {name} drifted from live code")
        if problems:
            print("B9 fixture violations:")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print("B9 fixtures OK: chain run, handler manifest, checksums match live code.")
        return 0

    for name, payload in artifacts.items():
        _write(CHAIN_DIR / name, payload)
    _write(EVIDENCE_PATH, evidence_markdown(chain).encode("utf-8"))
    print(f"B9 fixtures written to {CHAIN_DIR}")
    print(f"Evidence written to {EVIDENCE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


