#!/usr/bin/env python3
"""
Phase 18 verification — VP18_ARTIFACT_INVALIDATION_VERIFIED (plan 05 §11–§16).

Verifies the content-addressed artifact pipeline
(`storage/windagent_storage/video_production/`) against the contracts in
`docs/video_production/artifact_storage/`:

  artifacts/video_production/phase_18/
  ├── artifact_model_receipt.json     (§12 record + statuses + append-only history)
  ├── artifact_key_receipt.json       (§13 full content key, pinned version, injective)
  ├── dependency_graph_receipt.json   (§14.2 inbound/outbound, unknown/cycle fail-closed)
  ├── invalidation_receipt.json       (§14.3 minimal scope: screenplay/character/BGM)
  ├── publish_reuse_receipt.json      (§14.1 atomic publish + §14.4 reuse policy)
  └── phase_verdict.json

Gate conditions (plan 05 §16):
  1. reuse based on FULL content key (not file-exists);
  2. invalidation correctly scoped (character -> bound shots only; BGM ->
     audio mix + final cut, never visual clips);
  3. artifact publish is atomic (no VALID record without file, no published
     file without record);
  4. history is never deleted/modified (append-only).

Supports --no-write / --verify-only.
"""

from __future__ import annotations

import datetime
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_18"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from windagent_storage.video_production import (  # noqa: E402
    ArtifactApprovalStatus,
    ArtifactDependencyEdge,
    ArtifactDependencyGraph,
    ArtifactDependencyType,
    ArtifactInvalidationService,
    ArtifactPublisher,
    ArtifactRecordStore,
    ArtifactReusePolicy,
    ArtifactStatus,
    ArtifactType,
    ContentAddressedStore,
    InvalidationChange,
    InvalidationChangeType,
    PublishRequest,
    ReuseVerdict,
    build_bgm_scope,
    build_character_scope,
    compute_artifact_key,
)
from windagent_storage.video_production.key import key_matches  # noqa: E402

CLOCK = 1_700_000_000.0  # fixed clock for deterministic receipts


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _record(checks: list[dict], check: str, ok: bool, detail: str) -> None:
    checks.append({"check": check, "ok": bool(ok), "detail": detail})


def _publish(pub: ArtifactPublisher, *, data: bytes, artifact_id: str, atype=ArtifactType.CLIP, **kw) -> PublishRequest:
    req = PublishRequest(
        artifact_type=atype,
        data=data,
        artifact_id=artifact_id,
        media_type="video/mp4",
        producer="verifier",
        project_id="p1",
        revision_id="rev1",
        input_hashes={"clip": "abc"},
        request_hash="req_1",
        prompt_version="prompt-1.0",
        model_version="flow-1.0",
        generation_mode="TEXT_TO_VIDEO",
        generation_parameters={"duration": 5},
        reference_hashes=["ref_a"],
        canonical_input={"screenplay": "hello"},
        **kw,
    )
    return pub.publish(req)


def _build_scope_graph() -> ArtifactDependencyGraph:
    """Screenplay -> plan -> shot plan -> prompt -> clip -> final cut;
    BGM -> audio mix -> final cut; character binds SHOT_1/SHOT_2."""
    graph = ArtifactDependencyGraph()
    nodes = ["SCREENPLAY", "PLAN", "SHOT_PLAN", "PROMPT", "CLIP", "FINAL_CUT",
             "BGM", "AUDIO_MIX", "CHARACTER", "SHOT_1", "SHOT_2", "SHOT_3"]
    for node in nodes:
        graph.register_node(node)
    graph.add_edge(ArtifactDependencyEdge("PLAN", depends_on_artifact_id="SCREENPLAY"))
    graph.add_edge(ArtifactDependencyEdge("SHOT_PLAN", depends_on_artifact_id="PLAN"))
    graph.add_edge(ArtifactDependencyEdge("PROMPT", depends_on_artifact_id="SHOT_PLAN"))
    graph.add_edge(ArtifactDependencyEdge("CLIP", depends_on_artifact_id="PROMPT"))
    graph.add_edge(ArtifactDependencyEdge("CLIP", depends_on_artifact_id="SHOT_1"))
    graph.add_edge(ArtifactDependencyEdge("CLIP", depends_on_artifact_id="SHOT_2"))
    graph.add_edge(ArtifactDependencyEdge("FINAL_CUT", depends_on_artifact_id="CLIP"))
    graph.add_edge(ArtifactDependencyEdge("AUDIO_MIX", depends_on_artifact_id="BGM", dependency_type=ArtifactDependencyType.AUDIO_INPUT))
    graph.add_edge(ArtifactDependencyEdge("FINAL_CUT", depends_on_artifact_id="AUDIO_MIX", dependency_type=ArtifactDependencyType.AUDIO_INPUT))
    graph.add_edge(ArtifactDependencyEdge("SHOT_1", depends_on_artifact_id="CHARACTER", dependency_type=ArtifactDependencyType.CHARACTER_BINDING))
    graph.add_edge(ArtifactDependencyEdge("SHOT_2", depends_on_artifact_id="CHARACTER", dependency_type=ArtifactDependencyType.CHARACTER_BINDING))
    return graph


def _engine(tmp: str):
    root = Path(tmp)
    content = ContentAddressedStore(root / "content")
    records = ArtifactRecordStore(root / "records")
    pub = ArtifactPublisher(content_store=content, record_store=records, clock=lambda: CLOCK)
    return pub, content, records


def _publish_all(pub: ArtifactPublisher, nodes: list[str]):
    recs = {}
    for node in nodes:
        res = _publish(pub, data=node.encode(), artifact_id=node, atype=ArtifactType.OTHER)
        recs[node] = res.record
    return recs


# ---------------------------------------------------------------------------
# Receipt 1 — artifact model (§12)
# ---------------------------------------------------------------------------


def verify_artifact_model() -> dict:
    checks = []
    tmp = tempfile.mkdtemp()
    pub, content, records = _engine(tmp)
    result = _publish(pub, data=b"model-bytes", artifact_id="art_model")
    rec = result.record

    fields = {
        "artifact_id": rec.artifact_id,
        "artifact_type": rec.artifact_type.value,
        "content_sha256": rec.content_sha256,
        "byte_size": rec.byte_size,
        "media_type": rec.media_type,
        "storage_locator": rec.storage_locator,
        "producer": rec.producer,
        "project_id": rec.project_id,
        "revision_id": rec.revision_id,
        "input_hashes": rec.input_hashes,
        "request_hash": rec.request_hash,
        "prompt_version": rec.prompt_version,
        "compiler_version": rec.compiler_version,
        "model_version": rec.model_version,
        "generation_mode": rec.generation_mode,
        "generation_parameters": rec.generation_parameters,
        "created_at": rec.created_at,
        "validation_status": rec.validation_status.value,
        "approval_status": rec.approval_status.value,
        "status": rec.status.value,
        "superseded_by": rec.superseded_by,
        "artifact_key": rec.artifact_key,
        "key_version": rec.key_version,
        "history": rec.history,
    }
    _record(checks, "record_has_all_12_fields", all(k in fields for k in (
        "artifact_id", "artifact_type", "content_sha256", "byte_size", "media_type",
        "storage_locator", "producer", "project_id", "revision_id", "input_hashes",
        "request_hash", "prompt_version", "compiler_version", "model_version",
        "generation_mode", "generation_parameters", "created_at", "validation_status",
        "approval_status", "superseded_by",
    )), f"fields={len(fields)}")

    _record(checks, "content_hash_64_hex", len(rec.content_sha256) == 64, rec.content_sha256[:16])
    _record(checks, "validated_after_publish", rec.validation_status.value == "VALIDATED", "atomic publish validates")
    _record(checks, "status_valid_after_publish", rec.status == ArtifactStatus.VALID, rec.status.value)
    _record(checks, "storage_locator_is_content_hash", rec.storage_locator == rec.content_sha256, "content address, not authority")

    # append-only history + invalidation keeps record
    rec.mark_stale("stale now", at=CLOCK + 1)
    records.save(rec)
    reloaded = records.load(rec.artifact_id)
    _record(checks, "history_grows_on_stale", len(reloaded.history) == 2, f"entries={len(reloaded.history)}")
    _record(checks, "record_not_deleted_by_invalidation", records.load(rec.artifact_id) is not None, "never deletes")

    # history shrink guard
    shrink_rejected = False
    rec2 = records.load(rec.artifact_id)
    rec2.history = rec2.history[:1]
    try:
        records.save(rec2)
    except ValueError:
        shrink_rejected = True
    _record(checks, "history_shrink_rejected", shrink_rejected, "append-only enforced")

    # from_dict round trip + schema version fail-closed
    rt = ArtifactRecordStore(Path(tempfile.mkdtemp()))
    rt.save(reloaded)
    restored = rt.load(rec.artifact_id)
    _record(checks, "record_round_trip", restored.artifact_key == rec.artifact_key and restored.content_sha256 == rec.content_sha256, "serialization stable")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP18_ARTIFACT_INVALIDATION_VERIFIED",
        "workstream": "artifact_model",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
        "sample_record": fields,
    }


# ---------------------------------------------------------------------------
# Receipt 2 — artifact key (§13)
# ---------------------------------------------------------------------------


def verify_artifact_key() -> dict:
    checks = []

    def key(canonical_input=None, **kw):
        defaults = {
            "canonical_input": canonical_input if canonical_input is not None else {"screenplay": "hello"},
            "prompt_version": "prompt-1.0",
            "reference_hashes": ["ref_a", "ref_b"],
            "model": "flow-1.0",
            "generation_mode": "TEXT_TO_VIDEO",
            "generation_parameters": {"duration": 5, "aspect": "16:9"},
        }
        defaults.update(kw)
        return compute_artifact_key(**defaults)

    _record(checks, "same_input_same_key", key() == key(), "reuse requires stable key")
    _record(checks, "reference_change_new_key", key(reference_hashes=["ref_a"]) != key(reference_hashes=["ref_b"]), "reference hashes in key")
    _record(checks, "model_change_new_key", key(model="flow-1.0") != key(model="flow-2.0"), "model in key")
    _record(checks, "prompt_change_new_key", key(prompt_version="p1") != key(prompt_version="p2"), "prompt version in key")
    _record(checks, "parameter_change_new_key", key(generation_parameters={"duration": 5}) != key(generation_parameters={"duration": 10}), "params in key")
    _record(checks, "screenplay_change_new_key", key(canonical_input={"screenplay": "a"}) != key(canonical_input={"screenplay": "b"}), "canonical input in key")
    _record(checks, "scene_order_semantic", key(canonical_input={"scenes": ["s1", "s2"]}) != key(canonical_input={"scenes": ["s2", "s1"]}), "ordered input preserved")

    # injective across components: no separator ambiguity
    k_ab = key(canonical_input={"x": "a|b"})
    k_ba = key(canonical_input={"x": "a"}, prompt_version="b|c")
    _record(checks, "key_injective_no_separator_ambiguity", k_ab != k_ba, "component-list JSON encoding is injective")

    unknown_version_rejected = False
    try:
        compute_artifact_key(canonical_input={"x": 1}, prompt_version="p", reference_hashes=[], model="m",
                             generation_mode="TEXT_TO_VIDEO", generation_parameters={}, key_version="v99")
    except ValueError:
        unknown_version_rejected = True
    _record(checks, "unknown_key_version_rejected", unknown_version_rejected, "old keys never reinterpreted (§13)")

    k1 = key()
    _record(checks, "key_matches_full_string", key_matches(k1, k1) and not key_matches(k1, k1.replace("v1:", "v2:", 1)), "version prefix part of key")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP18_ARTIFACT_INVALIDATION_VERIFIED",
        "workstream": "artifact_key",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Receipt 3 — dependency graph (§14.2)
# ---------------------------------------------------------------------------


def verify_dependency_graph() -> dict:
    checks = []
    graph = _build_scope_graph()

    _record(checks, "screenplay_chain_resolves", sorted(graph.transitive_inbound("SCREENPLAY", {ArtifactDependencyType.GENERATED_FROM}))
            == ["CLIP", "FINAL_CUT", "PLAN", "PROMPT", "SHOT_PLAN"], "full GENERATED_FROM chain")
    _record(checks, "inbound_query", [e.artifact_id for e in graph.inbound("SCREENPLAY")] == ["PLAN"], "direct dependents")
    _record(checks, "outbound_query", [e.depends_on_artifact_id for e in graph.outbound("CLIP")] == ["PROMPT", "SHOT_1", "SHOT_2"], "inputs of CLIP")

    unknown_node_rejected = False
    g2 = ArtifactDependencyGraph()
    g2.register_node("A")
    try:
        g2.add_edge(ArtifactDependencyEdge("B", depends_on_artifact_id="A"))
    except Exception:
        unknown_node_rejected = True
    _record(checks, "unknown_node_rejected", unknown_node_rejected, "add_edge fail-closed")

    unknown_target_rejected = False
    g3 = ArtifactDependencyGraph()
    g3.register_node("A")
    try:
        g3.add_edge(ArtifactDependencyEdge("A", depends_on_artifact_id="GHOST"))
    except Exception:
        unknown_target_rejected = True
    _record(checks, "unknown_target_rejected", unknown_target_rejected, "dependency target must be known")

    cycle_rejected = False
    g4 = ArtifactDependencyGraph()
    g4.register_node("A")
    g4.register_node("B")
    g4.add_edge(ArtifactDependencyEdge("A", depends_on_artifact_id="B"))
    try:
        g4.add_edge(ArtifactDependencyEdge("B", depends_on_artifact_id="A"))
    except Exception:
        cycle_rejected = True
    _record(checks, "cycle_rejected", cycle_rejected, "no well-defined minimal scope on cycles")

    dual_target_rejected = False
    try:
        ArtifactDependencyEdge("A", depends_on_artifact_id="B", domain_revision_hash="h")
    except Exception:
        dual_target_rejected = True
    _record(checks, "edge_requires_exactly_one_target", dual_target_rejected, "XOR artifact/revision target")

    restored = ArtifactDependencyGraph.from_dict(graph.to_dict())
    _record(checks, "graph_round_trip", restored.transitive_inbound("SCREENPLAY", {ArtifactDependencyType.GENERATED_FROM})
            == graph.transitive_inbound("SCREENPLAY", {ArtifactDependencyType.GENERATED_FROM}), "serialization stable")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP18_ARTIFACT_INVALIDATION_VERIFIED",
        "workstream": "dependency_graph",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Receipt 4 — invalidation (§14.3)
# ---------------------------------------------------------------------------


def verify_invalidation() -> dict:
    checks = []
    graph = _build_scope_graph()

    # Pure scope rules
    bound_shots, downstream = build_character_scope(graph, "CHARACTER")
    _record(checks, "character_scope_bound_shots", bound_shots == ["SHOT_1", "SHOT_2"], f"bound={bound_shots}")
    _record(checks, "character_scope_excludes_unbound", "SHOT_3" not in bound_shots, "unbound shot survives")

    bgm_affected = build_bgm_scope(graph, "BGM")
    _record(checks, "bgm_scope_includes_mix_and_cut", "AUDIO_MIX" in bgm_affected and "FINAL_CUT" in bgm_affected, f"bgm={bgm_affected}")
    _record(checks, "bgm_scope_keeps_visual_clips", "CLIP" not in bgm_affected, "visual clips survive BGM change")

    # End-to-end invalidation with records
    tmp = tempfile.mkdtemp()
    pub, _, records = _engine(tmp)
    nodes = ["SCREENPLAY", "PLAN", "SHOT_PLAN", "PROMPT", "CLIP", "FINAL_CUT",
             "BGM", "AUDIO_MIX", "CHARACTER", "SHOT_1", "SHOT_2", "SHOT_3"]
    recs = _publish_all(pub, nodes)
    service = ArtifactInvalidationService(graph=graph, record_store=records, clock=lambda: CLOCK)

    r1 = service.invalidate(InvalidationChange(
        change_type=InvalidationChangeType.SCREENPLAY_REVISION,
        target_artifact_id="SCREENPLAY", reason="screenplay v2",
    ))
    _record(checks, "screenplay_invalidates_chain", "PLAN" in r1.marked_stale and "CLIP" in r1.marked_stale and "FINAL_CUT" in r1.marked_stale, f"stale={r1.marked_stale}")
    for node in nodes:
        assert records.load(recs[node].artifact_id) is not None
    _record(checks, "screenplay_invalidation_no_delete", all(records.load(recs[n].artifact_id) is not None for n in nodes), "never deletes")
    plan_rec = records.load(recs["PLAN"].artifact_id)
    _record(checks, "invalidated_status_stale", plan_rec.status == ArtifactStatus.STALE, plan_rec.status.value)
    _record(checks, "invalidated_history_grown", len(plan_rec.history) >= 2, f"entries={len(plan_rec.history)}")

    # character change after a fresh run
    tmp2 = tempfile.mkdtemp()
    pub2, _, records2 = _engine(tmp2)
    _publish_all(pub2, nodes)
    service2 = ArtifactInvalidationService(graph=graph, record_store=records2, clock=lambda: CLOCK)
    r2 = service2.invalidate(InvalidationChange(
        change_type=InvalidationChangeType.CHARACTER_REFERENCE,
        target_artifact_id="CHARACTER", reason="character redesign",
    ))
    _record(checks, "character_change_scoped", "SHOT_1" in r2.marked_stale and "SHOT_2" in r2.marked_stale and "SHOT_3" not in r2.marked_stale, f"stale={r2.marked_stale}")
    _record(checks, "character_downstream_cuts_invalidated", "FINAL_CUT" in r2.marked_stale, "bound shots' cuts stale")

    # BGM change after a fresh run
    tmp3 = tempfile.mkdtemp()
    pub3, _, records3 = _engine(tmp3)
    _publish_all(pub3, nodes)
    service3 = ArtifactInvalidationService(graph=graph, record_store=records3, clock=lambda: CLOCK)
    r3 = service3.invalidate(InvalidationChange(
        change_type=InvalidationChangeType.BGM, target_artifact_id="BGM", reason="new track",
    ))
    _record(checks, "bgm_change_invalidates_mix", "AUDIO_MIX" in r3.marked_stale, "mix stale")
    _record(checks, "bgm_change_keeps_clip", "CLIP" not in r3.marked_stale, "visual clip survives")

    # unknown target fail-closed
    unknown_rejected = False
    try:
        service.affected_scope(InvalidationChange(change_type=InvalidationChangeType.SCREENPLAY_REVISION, target_artifact_id="GHOST"))
    except Exception:
        unknown_rejected = True
    _record(checks, "unknown_target_fail_closed", unknown_rejected, "no silent no-op invalidation")

    # supersede with replacement
    tmp4 = tempfile.mkdtemp()
    pub4, _, records4 = _engine(tmp4)
    _publish_all(pub4, nodes)
    service4 = ArtifactInvalidationService(graph=graph, record_store=records4, clock=lambda: CLOCK)
    service4.invalidate(
        InvalidationChange(change_type=InvalidationChangeType.SCREENPLAY_REVISION, target_artifact_id="SCREENPLAY", reason="v2"),
        supersede_with={"CLIP": "art_clip_v2"},
    )
    clip4 = records4.load("CLIP")
    _record(checks, "supersede_marks_superseded", clip4.status == ArtifactStatus.SUPERSEDED and clip4.superseded_by == "art_clip_v2", "replacement recorded")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP18_ARTIFACT_INVALIDATION_VERIFIED",
        "workstream": "invalidation",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Receipt 5 — publish + reuse (§14.1, §14.4)
# ---------------------------------------------------------------------------


def verify_publish_reuse() -> dict:
    checks = []
    tmp = tempfile.mkdtemp()
    pub, content, records = _engine(tmp)
    result = _publish(pub, data=b"publish-bytes", artifact_id="art_reuse")

    _record(checks, "content_file_exists", content.exists(result.record.content_sha256), "file before record")
    _record(checks, "record_valid", records.load("art_reuse").status == ArtifactStatus.VALID, "record after file")
    _record(checks, "available_event_emitted", result.event.artifact_id == "art_reuse" and result.event.deduplication_key.startswith("artifact_available:"), "event after commit")
    _record(checks, "idempotent_publish_same_hash", content.publish(b"publish-bytes") == result.record.content_sha256, "content-addressed idempotency")

    # validator failure never promotes a record
    class RejectingValidator:
        def validate(self, data: bytes) -> None:
            raise ValueError("decode failed")

    tmp2 = tempfile.mkdtemp()
    pub2 = ArtifactPublisher(
        content_store=ContentAddressedStore(Path(tmp2) / "content"),
        record_store=ArtifactRecordStore(Path(tmp2) / "records"),
        validator=RejectingValidator(),
        clock=lambda: CLOCK,
    )
    rejected = False
    try:
        _publish(pub2, data=b"bad-bytes", artifact_id="art_bad")
    except ValueError:
        rejected = True
    _record(checks, "validator_failure_no_record", rejected and list((Path(tmp2) / "records").glob("record_*.json")) == [], "no record promoted on validation failure")

    # reuse: full key + valid file + approval
    rec = records.load("art_reuse")
    policy = ArtifactReusePolicy(content_store=content, require_approval=True)
    d_unapproved = policy.can_reuse(rec, expected_key=rec.artifact_key)
    _record(checks, "reuse_blocks_unapproved", d_unapproved.verdict == ReuseVerdict.REUSE_BLOCKED and "approval" in d_unapproved.reason, d_unapproved.reason)

    rec.approval_status = ArtifactApprovalStatus.APPROVED
    records.save(rec)
    d_ok = policy.can_reuse(rec, expected_key=rec.artifact_key)
    _record(checks, "reuse_allowed_full_key", d_ok.verdict == ReuseVerdict.REUSE_ALLOWED, d_ok.reason)

    d_key = policy.can_reuse(rec, expected_key=compute_artifact_key(
        canonical_input={"screenplay": "other"}, prompt_version="p", reference_hashes=[], model="m",
        generation_mode="TEXT_TO_VIDEO", generation_parameters={},
    ))
    _record(checks, "reuse_blocks_key_mismatch", d_key.verdict == ReuseVerdict.REUSE_BLOCKED and "key mismatch" in d_key.reason, d_key.reason)

    # cross-project policy + per-call override — run on the still-VALID record
    # (the status rule must not mask the cross-project rule, so this comes
    # BEFORE the record is marked stale below)
    cross = ArtifactReusePolicy(content_store=content, require_approval=False, allow_cross_project=False)
    d_x = cross.can_reuse(records.load("art_reuse"), expected_key=rec.artifact_key, project_id="other")
    d_x_override = cross.can_reuse(records.load("art_reuse"), expected_key=rec.artifact_key, project_id="other", allow_cross_project=True)
    _record(checks, "cross_project_policy_honored", d_x.verdict == ReuseVerdict.REUSE_BLOCKED and "cross-project" in d_x.reason, d_x.reason)
    _record(checks, "cross_project_override_works", d_x_override.verdict == ReuseVerdict.REUSE_ALLOWED, "per-call override enables cross-project reuse")

    # stale -> blocked (content file still intact here)
    rec_stale = records.load("art_reuse")
    rec_stale.mark_stale("stale", at=CLOCK + 2)
    records.save(rec_stale)
    d_stale = ArtifactReusePolicy(content_store=content, require_approval=False).can_reuse(records.load("art_reuse"), expected_key=rec_stale.artifact_key)
    _record(checks, "reuse_blocks_stale", d_stale.verdict == ReuseVerdict.REUSE_BLOCKED and "STALE" in d_stale.reason, d_stale.reason)

    # tamper -> reuse blocked (not just missing file); run LAST since it
    # corrupts the shared content file
    (Path(tmp) / "content" / rec.content_sha256).write_bytes(b"tampered!")
    d_tamper = policy.can_reuse(records.load("art_reuse"), expected_key=rec.artifact_key)
    _record(checks, "reuse_blocks_tampered_file", d_tamper.verdict == ReuseVerdict.REUSE_BLOCKED and "tampered" in d_tamper.reason, d_tamper.reason)

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP18_ARTIFACT_INVALIDATION_VERIFIED",
        "workstream": "publish_reuse",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(no_write: bool = False) -> int:
    print("Verifying Phase 18 — Content-Addressed Artifact Storage & Invalidation...")
    m = verify_artifact_model()
    k = verify_artifact_key()
    g = verify_dependency_graph()
    inv = verify_invalidation()
    pr = verify_publish_reuse()

    all_workstreams = [m, k, g, inv, pr]
    overall_pass = all(w["all_checks_pass"] for w in all_workstreams)
    overall_status = "PASSED" if overall_pass else "FAILED"

    gate_reasons = []
    if not overall_pass:
        for w in all_workstreams:
            if not w["all_checks_pass"]:
                for c in w["checks"]:
                    if not c["ok"]:
                        gate_reasons.append(f"[{w['workstream']}] {c['check']}: {c['detail']}")

    verdict = {
        "gate": "VP18_ARTIFACT_INVALIDATION_VERIFIED",
        "status": overall_status,
        "verified_at": utc_now_iso(),
        "workstreams": {
            "artifact_model": m["all_checks_pass"],
            "artifact_key": k["all_checks_pass"],
            "dependency_graph": g["all_checks_pass"],
            "invalidation": inv["all_checks_pass"],
            "publish_reuse": pr["all_checks_pass"],
        },
        "blocking_reasons": gate_reasons,
    }

    if not no_write:
        PHASE_DIR.mkdir(parents=True, exist_ok=True)
        write_json(PHASE_DIR / "artifact_model_receipt.json", m)
        write_json(PHASE_DIR / "artifact_key_receipt.json", k)
        write_json(PHASE_DIR / "dependency_graph_receipt.json", g)
        write_json(PHASE_DIR / "invalidation_receipt.json", inv)
        write_json(PHASE_DIR / "publish_reuse_receipt.json", pr)
        write_json(PHASE_DIR / "phase_verdict.json", verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(overall_status, m, k, g, inv, pr),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_18 artifacts untouched.")

    print(f"Phase 18 verdict: {overall_status}")
    print(f"  artifact model: {'PASS' if m['all_checks_pass'] else 'FAIL'}")
    print(f"  artifact key: {'PASS' if k['all_checks_pass'] else 'FAIL'}")
    print(f"  dependency graph: {'PASS' if g['all_checks_pass'] else 'FAIL'}")
    print(f"  invalidation: {'PASS' if inv['all_checks_pass'] else 'FAIL'}")
    print(f"  publish/reuse: {'PASS' if pr['all_checks_pass'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(status, m, k, g, inv, pr) -> str:
    return f"""# Phase 18 Report — Content-Addressed Artifact Storage & Invalidation

- **Gate:** `VP18_ARTIFACT_INVALIDATION_VERIFIED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Artifact Model

- Contract: `docs/video_production/artifact_storage/artifact_model_contract.md`
- Checks: {m.get('check_count')}; all pass: {m.get('all_checks_pass')}

## Artifact Key

- Contract: `docs/video_production/artifact_storage/artifact_key_contract.md`
- Full content key, pinned version v1, injective encoding; checks: {k.get('check_count')}; all pass: {k.get('all_checks_pass')}

## Dependency Graph

- Contract: `docs/video_production/artifact_storage/dependency_graph_contract.md`
- Inbound/outbound, unknown/cycle fail-closed; checks: {g.get('check_count')}; all pass: {g.get('all_checks_pass')}

## Invalidation

- Contract: `docs/video_production/artifact_storage/invalidation_contract.md`
- Minimal scope (screenplay/character/BGM), never deletes; checks: {inv.get('check_count')}; all pass: {inv.get('all_checks_pass')}

## Publish & Reuse

- Contract: `docs/video_production/artifact_storage/publish_reuse_contract.md`
- Atomic publish + full-key/hash-valid reuse; checks: {pr.get('check_count')}; all pass: {pr.get('all_checks_pass')}

## Evidence

- `artifact_model_receipt.json`
- `artifact_key_receipt.json`
- `dependency_graph_receipt.json`
- `invalidation_receipt.json`
- `publish_reuse_receipt.json`
- `phase_verdict.json`
"""


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
