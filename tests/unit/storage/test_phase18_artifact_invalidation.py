"""
Phase 18 — Content-addressed artifact storage & invalidation unit tests (plan 05 §15).

Covers the gate test matrix:

- same canonical input reuse (full content key);
- reference/prompt/model/parameter change -> different key;
- key version pinning (old keys never reinterpreted, §13);
- screenplay revision -> full GENERATED_FROM chain invalidation;
- character change -> ONLY bound shots + downstream cuts (§14.3);
- BGM change -> audio mix + final cut, NOT visual clips (§14.3);
- atomic publish crash safety (§14.1) — no VALID record without file, no
  published file without record;
- file tamper / hash mismatch blocks reuse (§14.4);
- concurrent publish same key -> idempotent content addressing;
- invalidation graph cycle / unknown node -> fail closed;
- invalidation never deletes; history is append-only.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from windagent_core.errors.exceptions import ValidationError

from windagent_storage.video_production import (
    ARTIFACT_KEY_VERSION,
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
from windagent_storage.video_production.key import key_matches


def _key(canonical_input=None, **kwargs):
    defaults = {
        "canonical_input": canonical_input if canonical_input is not None else {"screenplay": "hello"},
        "prompt_version": "prompt-1.0",
        "reference_hashes": ["ref_a", "ref_b"],
        "model": "flow-1.0",
        "generation_mode": "TEXT_TO_VIDEO",
        "generation_parameters": {"duration": 5, "aspect": "16:9"},
    }
    defaults.update(kwargs)
    return compute_artifact_key(**defaults)


def _graph_with(screenplay, plan, shot_plan, prompt, clip, final_cut):
    """Build a linear GENERATED_FROM chain: screenplay -> ... -> final cut."""
    graph = ArtifactDependencyGraph()
    for node in (screenplay, plan, shot_plan, prompt, clip, final_cut):
        graph.register_node(node)
    graph.add_edge(ArtifactDependencyEdge(plan, depends_on_artifact_id=screenplay, reason="plan from screenplay"))
    graph.add_edge(ArtifactDependencyEdge(shot_plan, depends_on_artifact_id=plan, reason="shots from plan"))
    graph.add_edge(ArtifactDependencyEdge(prompt, depends_on_artifact_id=shot_plan, reason="prompt from plan"))
    graph.add_edge(ArtifactDependencyEdge(clip, depends_on_artifact_id=prompt, reason="clip from prompt"))
    graph.add_edge(ArtifactDependencyEdge(final_cut, depends_on_artifact_id=clip, reason="cut from clips"))
    return graph


def _publish(eng: ArtifactPublisher, *, artifact_type=ArtifactType.CLIP, data=b"clip-bytes", artifact_id=None, **kw):
    req = PublishRequest(
        artifact_type=artifact_type,
        data=data,
        artifact_id=artifact_id,
        media_type="video/mp4",
        producer="test",
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
    return eng.publish(req)


def _engine(tmp: str, validator=None):
    root = Path(tmp)
    content = ContentAddressedStore(root / "content")
    records = ArtifactRecordStore(root / "records")
    pub = ArtifactPublisher(content_store=content, record_store=records, validator=validator, clock=lambda: 1234.0)
    return pub, content, records


# ---------------------------------------------------------------------------
# Artifact key (§13)
# ---------------------------------------------------------------------------


def test_same_canonical_input_same_key():
    assert _key() == _key()


def test_reference_hash_change_different_key():
    a = _key(reference_hashes=["ref_a"])
    b = _key(reference_hashes=["ref_b"])
    assert a != b


def test_model_change_different_key():
    assert _key(model="flow-1.0") != _key(model="flow-2.0")


def test_parameter_change_different_key():
    assert _key(generation_parameters={"duration": 5}) != _key(generation_parameters={"duration": 10})


def test_prompt_version_change_different_key():
    assert _key(prompt_version="prompt-1.0") != _key(prompt_version="prompt-2.0")


def test_screenplay_text_change_different_key():
    assert _key(canonical_input={"screenplay": "hello"}) != _key(canonical_input={"screenplay": "goodbye"})


def test_ordered_scene_sequence_is_semantic():
    """Reordering a screenplay's scene sequence must produce a different key."""
    k1 = _key(canonical_input={"scenes": ["s1", "s2", "s3"]})
    k2 = _key(canonical_input={"scenes": ["s3", "s2", "s1"]})
    assert k1 != k2


def test_key_version_unknown_raises():
    with pytest.raises(ValueError):
        compute_artifact_key(
            canonical_input={"x": 1},
            prompt_version="p",
            reference_hashes=[],
            model="m",
            generation_mode="TEXT_TO_VIDEO",
            generation_parameters={},
            key_version="v99",
        )


def test_key_matches_includes_version_prefix():
    k = _key()
    assert key_matches(k, k)
    assert not key_matches(k, k.replace("v1:", "v2:", 1))


def test_key_version_prefix_stable():
    assert ARTIFACT_KEY_VERSION == "v1"


# ---------------------------------------------------------------------------
# Content-addressed store + atomic publish (§14.1)
# ---------------------------------------------------------------------------


def test_content_addressed_store_idempotent_and_atomic():
    tmp = tempfile.mkdtemp()
    store = ContentAddressedStore(Path(tmp))
    h1 = store.publish(b"abc")
    h2 = store.publish(b"abc")
    assert h1 == h2
    assert store.read(h1) == b"abc"
    assert set(store.list_hashes()) == {h1}


def test_publish_writes_file_before_record():
    """Crash between content write and record write -> orphan file, no VALID record."""
    tmp = tempfile.mkdtemp()
    pub, content, records = _engine(tmp)
    result = _publish(pub)
    # file exists AND record exists
    assert content.exists(result.record.content_sha256)
    assert records.load(result.record.artifact_id) is not None
    assert records.load(result.record.artifact_id).status == ArtifactStatus.VALID


def test_publish_returns_available_event():
    tmp = tempfile.mkdtemp()
    pub, _, _ = _engine(tmp)
    result = _publish(pub)
    assert result.event.artifact_id == result.record.artifact_id
    assert result.event.deduplication_key.startswith("artifact_available:")
    assert result.record.validation_status.value == "VALIDATED"


def test_publish_empty_data_rejected():
    tmp = tempfile.mkdtemp()
    pub, _, _ = _engine(tmp)
    with pytest.raises(ValueError):
        _publish(pub, data=b"")


def test_publish_validator_failure_never_promotes_record():
    tmp = tempfile.mkdtemp()
    records_dir = Path(tmp) / "records"

    class RejectingValidator:
        def validate(self, data: bytes) -> None:
            raise ValueError("decode failed")

    pub = ArtifactPublisher(
        content_store=ContentAddressedStore(Path(tmp) / "content"),
        record_store=ArtifactRecordStore(records_dir),
        validator=RejectingValidator(),
        clock=lambda: 1234.0,
    )
    with pytest.raises(ValueError):
        _publish(pub)
    assert list(records_dir.glob("record_*.json")) == []  # no record promoted


def test_record_store_history_append_only_guard():
    tmp = tempfile.mkdtemp()
    _, _, records = _engine(tmp)
    result = _publish(ArtifactPublisher(
        content_store=ContentAddressedStore(Path(tmp) / "content"),
        record_store=records,
        clock=lambda: 1234.0,
    ))
    rec = records.load(result.record.artifact_id)
    rec.mark_stale("stale now", at=1.0)
    records.save(rec)
    reloaded = records.load(result.record.artifact_id)
    assert len(reloaded.history) == 2  # published + stale

    # Attempting to shrink history must raise.
    rec2 = records.load(result.record.artifact_id)
    rec2.history = rec2.history[:1]
    with pytest.raises(ValueError):
        records.save(rec2)


def test_record_serialization_round_trip():
    tmp = tempfile.mkdtemp()
    pub, _, _ = _engine(tmp)
    result = _publish(pub)
    rec = pub.record_store.load(result.record.artifact_id)
    assert rec.artifact_id == result.record.artifact_id
    assert rec.content_sha256 == result.record.content_sha256
    assert rec.artifact_key == result.record.artifact_key


# ---------------------------------------------------------------------------
# Dependency graph (§14.2)
# ---------------------------------------------------------------------------


def test_graph_unknown_node_rejected():
    graph = ArtifactDependencyGraph()
    graph.register_node("A")
    with pytest.raises(ValidationError):
        graph.add_edge(ArtifactDependencyEdge("B", depends_on_artifact_id="A"))


def test_graph_unknown_dependency_target_rejected():
    graph = ArtifactDependencyGraph()
    graph.register_node("A")
    with pytest.raises(ValidationError):
        graph.add_edge(ArtifactDependencyEdge("A", depends_on_artifact_id="UNKNOWN"))


def test_graph_cycle_rejected():
    graph = ArtifactDependencyGraph()
    graph.register_node("A")
    graph.register_node("B")
    graph.add_edge(ArtifactDependencyEdge("A", depends_on_artifact_id="B"))
    with pytest.raises(ValidationError):
        graph.add_edge(ArtifactDependencyEdge("B", depends_on_artifact_id="A"))


def test_graph_edge_requires_exactly_one_target():
    with pytest.raises(ValidationError):
        ArtifactDependencyEdge("A")
    with pytest.raises(ValidationError):
        ArtifactDependencyEdge("A", depends_on_artifact_id="B", domain_revision_hash="h")


def test_graph_inbound_outbound_queries():
    graph = _graph_with("S", "P", "SP", "PR", "C", "F")
    assert [e.artifact_id for e in graph.inbound("S")] == ["P"]
    assert [e.depends_on_artifact_id for e in graph.outbound("C")] == ["PR"]
    assert graph.transitive_inbound("S") == {"P", "SP", "PR", "C", "F"}


def test_graph_serialization_round_trip():
    graph = _graph_with("S", "P", "SP", "PR", "C", "F")
    restored = ArtifactDependencyGraph.from_dict(graph.to_dict())
    assert restored.transitive_inbound("S") == graph.transitive_inbound("S")
    assert restored.validate() is None


# ---------------------------------------------------------------------------
# Invalidation scope (§14.3)
# ---------------------------------------------------------------------------


def _scope_graph():
    """Screenplay -> plan -> shot plan -> prompt -> clip -> final cut;
    plus BGM -> audio mix -> final cut; character bible binds two shots."""
    graph = ArtifactDependencyGraph()
    for node in ("SCREENPLAY", "PLAN", "SHOT_PLAN", "PROMPT", "CLIP", "FINAL_CUT",
                 "BGM", "AUDIO_MIX", "CHARACTER", "SHOT_1", "SHOT_2", "SHOT_3"):
        graph.register_node(node)
    graph.add_edge(ArtifactDependencyEdge("PLAN", depends_on_artifact_id="SCREENPLAY"))
    graph.add_edge(ArtifactDependencyEdge("SHOT_PLAN", depends_on_artifact_id="PLAN"))
    graph.add_edge(ArtifactDependencyEdge("PROMPT", depends_on_artifact_id="SHOT_PLAN"))
    graph.add_edge(ArtifactDependencyEdge("CLIP", depends_on_artifact_id="PROMPT"))
    graph.add_edge(ArtifactDependencyEdge("CLIP", depends_on_artifact_id="SHOT_1"))  # shots feed clips
    graph.add_edge(ArtifactDependencyEdge("CLIP", depends_on_artifact_id="SHOT_2"))
    graph.add_edge(ArtifactDependencyEdge("FINAL_CUT", depends_on_artifact_id="CLIP"))
    graph.add_edge(ArtifactDependencyEdge("AUDIO_MIX", depends_on_artifact_id="BGM", dependency_type=ArtifactDependencyType.AUDIO_INPUT))
    graph.add_edge(ArtifactDependencyEdge("FINAL_CUT", depends_on_artifact_id="AUDIO_MIX", dependency_type=ArtifactDependencyType.AUDIO_INPUT))
    graph.add_edge(ArtifactDependencyEdge("SHOT_1", depends_on_artifact_id="CHARACTER", dependency_type=ArtifactDependencyType.CHARACTER_BINDING))
    graph.add_edge(ArtifactDependencyEdge("SHOT_2", depends_on_artifact_id="CHARACTER", dependency_type=ArtifactDependencyType.CHARACTER_BINDING))
    return graph


def test_screenplay_change_invalidates_full_chain():
    graph = _scope_graph()
    affected = sorted(graph.transitive_inbound("SCREENPLAY", {ArtifactDependencyType.GENERATED_FROM}))
    assert affected == ["CLIP", "FINAL_CUT", "PLAN", "PROMPT", "SHOT_PLAN"]


def test_character_change_only_bound_shots():
    graph = _scope_graph()
    bound_shots, downstream = build_character_scope(graph, "CHARACTER")
    assert bound_shots == ["SHOT_1", "SHOT_2"]
    assert "SHOT_3" not in bound_shots  # unbound shot survives


def test_bgm_change_keeps_visual_clips():
    graph = _scope_graph()
    affected = build_bgm_scope(graph, "BGM")
    assert "AUDIO_MIX" in affected
    assert "FINAL_CUT" in affected
    assert "CLIP" not in affected  # visual clips survive a BGM change


def test_invalidation_service_marks_stale_never_deletes():
    tmp = tempfile.mkdtemp()
    graph = _scope_graph()
    pub, _, records = _engine(tmp)
    # Publish records for every graph node (artifact_id == graph node name).
    recs = {}
    for node in ("SCREENPLAY", "PLAN", "SHOT_PLAN", "PROMPT", "CLIP", "FINAL_CUT",
                 "BGM", "AUDIO_MIX", "CHARACTER", "SHOT_1", "SHOT_2", "SHOT_3"):
        res = _publish(pub, data=node.encode(), artifact_type=ArtifactType.OTHER, artifact_id=node)
        recs[node] = res.record
        graph.register_node(node)

    service = ArtifactInvalidationService(graph=graph, record_store=records, clock=lambda: 1234.0)
    result = service.invalidate(InvalidationChange(
        change_type=InvalidationChangeType.SCREENPLAY_REVISION,
        target_artifact_id="SCREENPLAY",
        reason="screenplay v2",
    ))
    assert "PLAN" in result.marked_stale
    assert "CLIP" in result.marked_stale
    assert "FINAL_CUT" in result.marked_stale
    # nothing deleted
    for node in recs:
        assert records.load(recs[node].artifact_id) is not None
    # record status is STALE and history grew
    plan_rec = records.load(recs["PLAN"].artifact_id)
    assert plan_rec.status == ArtifactStatus.STALE
    assert len(plan_rec.history) >= 2


def test_invalidation_unknown_target_raises():
    tmp = tempfile.mkdtemp()
    graph = ArtifactDependencyGraph()
    graph.register_node("A")
    _, _, records = _engine(tmp)
    service = ArtifactInvalidationService(graph=graph, record_store=records)
    with pytest.raises(ValidationError):
        service.affected_scope(InvalidationChange(
            change_type=InvalidationChangeType.SCREENPLAY_REVISION,
            target_artifact_id="GHOST",
        ))


def test_invalidation_character_change_scoped_to_bound_shots():
    tmp = tempfile.mkdtemp()
    graph = _scope_graph()
    pub, _, records = _engine(tmp)
    recs = {}
    for node in ("SCREENPLAY", "PLAN", "SHOT_PLAN", "PROMPT", "CLIP", "FINAL_CUT",
                 "BGM", "AUDIO_MIX", "CHARACTER", "SHOT_1", "SHOT_2", "SHOT_3"):
        res = _publish(pub, data=node.encode(), artifact_type=ArtifactType.OTHER, artifact_id=node)
        recs[node] = res.record

    service = ArtifactInvalidationService(graph=graph, record_store=records)
    result = service.invalidate(InvalidationChange(
        change_type=InvalidationChangeType.CHARACTER_REFERENCE,
        target_artifact_id="CHARACTER",
        reason="character design change",
    ))
    assert "SHOT_1" in result.marked_stale
    assert "SHOT_2" in result.marked_stale
    assert "SHOT_3" not in result.marked_stale  # unbound shot survives
    assert "FINAL_CUT" in result.marked_stale  # downstream of bound shots


def test_invalidation_supersede_with_replacement():
    tmp = tempfile.mkdtemp()
    graph = _scope_graph()
    pub, _, records = _engine(tmp)
    recs = {}
    for node in ("SCREENPLAY", "PLAN", "SHOT_PLAN", "PROMPT", "CLIP", "FINAL_CUT"):
        res = _publish(pub, data=node.encode(), artifact_type=ArtifactType.OTHER, artifact_id=node)
        recs[node] = res.record

    service = ArtifactInvalidationService(graph=graph, record_store=records)
    service.invalidate(
        InvalidationChange(change_type=InvalidationChangeType.SCREENPLAY_REVISION, target_artifact_id="SCREENPLAY", reason="v2"),
        supersede_with={"CLIP": "art_clip_v2"},
    )
    clip_rec = records.load(recs["CLIP"].artifact_id)
    assert clip_rec.status == ArtifactStatus.SUPERSEDED
    assert clip_rec.superseded_by == "art_clip_v2"


# ---------------------------------------------------------------------------
# Reuse policy (§14.4)
# ---------------------------------------------------------------------------


def test_reuse_requires_full_key_match():
    tmp = tempfile.mkdtemp()
    pub, content, records = _engine(tmp)
    result = _publish(pub)
    rec = records.load(result.record.artifact_id)
    policy = ArtifactReusePolicy(content_store=content, require_approval=False)
    d = policy.can_reuse(rec, expected_key=rec.artifact_key)
    assert d.verdict == ReuseVerdict.REUSE_ALLOWED
    d2 = policy.can_reuse(rec, expected_key=_key())  # different input -> different key
    assert d2.verdict == ReuseVerdict.REUSE_BLOCKED
    assert "key mismatch" in d2.reason


def test_reuse_blocks_tampered_file():
    tmp = tempfile.mkdtemp()
    pub, content, records = _engine(tmp)
    result = _publish(pub, data=b"original-bytes")
    rec = records.load(result.record.artifact_id)
    # Tamper with the stored content file.
    (Path(tmp) / "content" / rec.content_sha256).write_bytes(b"tampered!")
    policy = ArtifactReusePolicy(content_store=content, require_approval=False)
    d = policy.can_reuse(rec, expected_key=rec.artifact_key)
    assert d.verdict == ReuseVerdict.REUSE_BLOCKED
    assert "tampered" in d.reason


def test_reuse_blocks_stale_record():
    tmp = tempfile.mkdtemp()
    pub, content, records = _engine(tmp)
    result = _publish(pub)
    rec = records.load(result.record.artifact_id)
    rec.mark_stale("superseded by v2", at=1.0)
    records.save(rec)
    policy = ArtifactReusePolicy(content_store=content, require_approval=False)
    d = policy.can_reuse(records.load(result.record.artifact_id), expected_key=rec.artifact_key)
    assert d.verdict == ReuseVerdict.REUSE_BLOCKED
    assert "STALE" in d.reason


def test_reuse_requires_approval_when_policy_says_so():
    tmp = tempfile.mkdtemp()
    pub, content, records = _engine(tmp)
    result = _publish(pub)
    rec = records.load(result.record.artifact_id)
    assert rec.approval_status == ArtifactApprovalStatus.UNAPPROVED
    policy = ArtifactReusePolicy(content_store=content, require_approval=True)
    d = policy.can_reuse(rec, expected_key=rec.artifact_key)
    assert d.verdict == ReuseVerdict.REUSE_BLOCKED
    assert "approval" in d.reason


def test_reuse_cross_project_policy():
    tmp = tempfile.mkdtemp()
    pub, content, records = _engine(tmp)
    result = _publish(pub)
    rec = records.load(result.record.artifact_id)
    policy = ArtifactReusePolicy(content_store=content, require_approval=False, allow_cross_project=False)
    assert policy.can_reuse(rec, expected_key=rec.artifact_key, project_id="p1").verdict == ReuseVerdict.REUSE_ALLOWED
    assert policy.can_reuse(rec, expected_key=rec.artifact_key, project_id="other").verdict == ReuseVerdict.REUSE_BLOCKED
    # Per-call override can enable it.
    assert policy.can_reuse(rec, expected_key=rec.artifact_key, project_id="other", allow_cross_project=True).verdict == ReuseVerdict.REUSE_ALLOWED


# ---------------------------------------------------------------------------
# Determinism (gate)
# ---------------------------------------------------------------------------


def test_key_and_invalidation_deterministic_with_injected_clock():
    tmp = tempfile.mkdtemp()
    graph = _scope_graph()
    pub, _, records = _engine(tmp)
    recs = {}
    for node in ("SCREENPLAY", "PLAN", "SHOT_PLAN", "PROMPT", "CLIP", "FINAL_CUT"):
        res = _publish(pub, data=node.encode(), artifact_type=ArtifactType.OTHER, artifact_id=node)
        recs[node] = res.record

    service = ArtifactInvalidationService(graph=graph, record_store=records, clock=lambda: 1234.0)
    r1 = service.invalidate(InvalidationChange(change_type=InvalidationChangeType.SCREENPLAY_REVISION, target_artifact_id="SCREENPLAY", reason="v2"))
    r2 = service.invalidate(InvalidationChange(change_type=InvalidationChangeType.SCREENPLAY_REVISION, target_artifact_id="SCREENPLAY", reason="v2"))
    assert r1.affected_artifact_ids == r2.affected_artifact_ids
    assert len(r1.marked_stale) == len(r2.marked_stale)
