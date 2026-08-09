"""VP3D Phase 21 - fault-tolerant render jobs acceptance tests.

Covers the Phase 21 components (ChunkSizeScheduler, RenderJobPlanner,
LeaseRegistry, FramePublishValidator/publish_frame, RenderRecoveryCoordinator,
RetryClassifier) plus the adapter chunk-plan wiring, against the Stage J
§6 test matrix: chunk sizing from measured timing, duplicate dispatch,
lease expiry, stale completion, corrupt/missing/wrong-hash/wrong-dimension
frames, worker kill mid-chunk, changed render profile (no partial reuse),
partial retry from the next valid frame, and cause-classified retries.
"""

from __future__ import annotations

import asyncio
import hashlib
import struct

import pytest

from windagent_core.domain.video_production.production_ir.enums import EngineJobStatus
from windagent_tools.production_engines.blender import (
    CHUNK_PENDING,
    CHUNK_PUBLISHED,
    CHUNK_RENDERING,
    LEASE_ACTIVE,
    LEASE_RELEASED,
    RETRY_CAUSE_BAD_ASSET,
    RETRY_CAUSE_BLENDER_CRASH,
    RETRY_CAUSE_DISK_FULL,
    RETRY_CAUSE_OOM,
    RETRY_CAUSE_TIMEOUT,
    RETRY_CAUSE_UNKNOWN,
    RETRY_CAUSE_USER_CANCEL,
    BlenderCapabilityProbe,
    BlenderEngineAdapter,
    BlenderEngineConfig,
    BlenderGpuProbe,
    ChunkPlanError,
    ChunkSizeScheduler,
    FrameChunk,
    FrameManifest,
    FramePublishError,
    FramePublishValidator,
    LeaseConflictError,
    LeaseRegistry,
    RenderJobPlanner,
    RenderJobPolicy,
    RenderRecoveryCoordinator,
    RetryClassifier,
    StaleWorkerPublishError,
    publish_frame,
)
from tests.unit.tools.test_phase3_blender_adapter import (
    FakeBlenderProcess,
    make_detector,
)
from tests.fixtures.video_production.ir_fixture_builder import build_valid_ir


def _png_bytes(width: int = 1920, height: int = 1080) -> bytes:
    """Minimal PNG-shaped bytes probe_dimensions can parse (IHDR layout)."""
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00" * 8
        + struct.pack(">II", width, height)
        + b"\x00" * 8
    )


def _chunk(
    frame_start: int = 1,
    frame_end: int = 10,
    attempt: int = 0,
    status: str = CHUNK_PENDING,
    **overrides,
) -> FrameChunk:
    defaults = dict(
        chunk_id="ej_001:chunk-000",
        job_id="ej_001",
        episode_id="ep_01",
        scene_id="scn_01",
        shot_id="sht_010",
        scene_hash="scn-hash",
        shot_hash="sht-hash",
        profile_hash="profile-hash",
        frame_start=frame_start,
        frame_end=frame_end,
        blender_version="4.5.3",
        device_class="OPTIX",
        asset_hashes={"hero.glb": "asset-hash"},
    )
    defaults.update(overrides)
    return FrameChunk(**defaults)


def _manifest(tmp_path, chunk: FrameChunk, content_hash: str = "") -> FrameManifest:
    return FrameManifest(
        workspace=tmp_path / "frames",
        frame_range=(chunk.frame_start, chunk.frame_end),
        extension="png",
        expected_dimensions={"width": 1920, "height": 1080},
        content_hash=content_hash,
    )


class TestChunkSizeScheduler:
    def test_sizes_from_measured_time_and_recovery_overhead(self):
        scheduler = ChunkSizeScheduler(recovery_fraction_budget=0.10)
        # 2 s/frame, 120 s overhead, 10% budget: 120/(0.1*2) = 600 -> clamped 256
        frames, exceeds = scheduler.suggest(2.0, 120.0)
        assert frames == 256
        assert exceeds is True
        # overhead small enough: 60 s -> 60/0.2 = 300 -> still clamped
        frames, exceeds = scheduler.suggest(2.0, 60.0)
        assert frames == 256
        # 0.5 s/frame, 10 s overhead -> 10/0.05 = 200 frames
        frames, exceeds = scheduler.suggest(0.5, 10.0)
        assert frames == 200
        assert exceeds is False

    def test_zero_overhead_means_largest_chunk(self):
        frames, exceeds = ChunkSizeScheduler().suggest(1.0, 0.0)
        assert frames == 256
        assert exceeds is False

    def test_min_clamp(self):
        scheduler = ChunkSizeScheduler(max_frames=256)
        # 100 s/frame, 1 s overhead -> 1/(0.1*100) = 0.1 -> clamped to 1
        frames, exceeds = scheduler.suggest(100.0, 1.0)
        assert frames == 1

    def test_fails_closed_on_unmeasured_render(self):
        with pytest.raises(ChunkPlanError):
            ChunkSizeScheduler().suggest(0.0, 10.0)

    def test_plan_chunks_covers_range_contiguously(self):
        ranges = ChunkSizeScheduler().plan_chunks(1, 10, 4)
        assert ranges == ((1, 4), (5, 8), (9, 10))
        flat = [f for s, e in ranges for f in range(s, e + 1)]
        assert flat == list(range(1, 11))

    def test_plan_chunks_fails_closed(self):
        with pytest.raises(ChunkPlanError):
            ChunkSizeScheduler().plan_chunks(5, 4, 4)
        with pytest.raises(ChunkPlanError):
            ChunkSizeScheduler().plan_chunks(1, 4, 0)


class TestRenderJobPlanner:
    def test_job_model_episode_scene_shot_chunks(self):
        planner = RenderJobPlanner()
        job = planner.plan_job(
            job_id="ej_001",
            episode_id="ep_01",
            scene_id="scn_01",
            shot_id="sht_010",
            scene_hash="scn-hash",
            shot_hash="sht-hash",
            profile_hash="profile-hash",
            frame_start=1,
            frame_end=100,
            blender_version="4.5.3",
            device_class="OPTIX",
            chunk_size=25,
        )
        assert len(job.chunks) == 4
        assert job.chunks[0].frame_start == 1
        assert job.chunks[-1].frame_end == 100
        for chunk in job.chunks:
            assert chunk.attempt == 0
            assert chunk.status == CHUNK_PENDING
            assert chunk.content_hash()

    def test_chunk_content_hash_deterministic_and_state_free(self):
        a = _chunk()
        b = _chunk()
        assert a.content_hash() == b.content_hash()
        retried = _chunk(attempt=3, status=CHUNK_RENDERING)
        assert retried.content_hash() == a.content_hash(), (
            "attempt/status are execution state, not content identity"
        )
        moved = _chunk(frame_start=2, frame_end=9)
        assert moved.content_hash() != a.content_hash()

    def test_changed_asset_hash_changes_content_hash(self):
        a = _chunk()
        b = _chunk(asset_hashes={"hero.glb": "other-hash"})
        assert a.content_hash() != b.content_hash()

    def test_chunk_round_trip(self):
        chunk = _chunk(attempt=2, output_hashes={"1": "aa"})
        assert FrameChunk.from_dict(chunk.to_dict()) == chunk

    def test_scheduler_sizes_chunks_from_measured_timing(self):
        planner = RenderJobPlanner()
        job = planner.plan_job(
            job_id="ej_001",
            episode_id="ep_01",
            scene_id="scn_01",
            shot_id="sht_010",
            scene_hash="h",
            shot_hash="h",
            profile_hash="h",
            frame_start=1,
            frame_end=50,
            blender_version="4.5.3",
            device_class="CPU",
            measured_seconds_per_frame=0.5,
            recovery_overhead_seconds=10.0,
        )
        # 10/(0.1*0.5) = 200 -> range of 50 fits one chunk
        assert len(job.chunks) == 1
        assert job.chunks[0].frame_count == 50

    def test_requires_chunk_size_or_measured_timing(self):
        with pytest.raises(ChunkPlanError):
            RenderJobPlanner().plan_job(
                job_id="ej_001",
                episode_id="ep_01",
                scene_id="scn_01",
                shot_id="sht_010",
                scene_hash="h",
                shot_hash="h",
                profile_hash="h",
                frame_start=1,
                frame_end=10,
                blender_version="4.5.3",
                device_class="CPU",
            )


class TestLeaseRegistry:
    def test_acquire_reserves_before_side_effect(self):
        registry = LeaseRegistry()
        lease = registry.acquire("chunk-key", "worker-a", now=100.0)
        assert lease.owner_worker_id == "worker-a"
        assert lease.fencing_token
        assert lease.state == LEASE_ACTIVE
        assert lease.expires_at == 100.0 + 300.0

    def test_duplicate_dispatch_rejected_while_active(self):
        registry = LeaseRegistry()
        registry.acquire("chunk-key", "worker-a", now=100.0)
        with pytest.raises(LeaseConflictError):
            registry.acquire("chunk-key", "worker-b", now=101.0)

    def test_acquire_after_expiry_allows_new_owner(self):
        registry = LeaseRegistry()
        registry.acquire("chunk-key", "worker-a", lease_seconds=10.0, now=100.0)
        registry.expire_stale(now=200.0)
        lease = registry.acquire("chunk-key", "worker-b", now=201.0)
        assert lease.owner_worker_id == "worker-b"

    def test_renew_and_release_require_owner_token(self):
        registry = LeaseRegistry()
        lease = registry.acquire("chunk-key", "worker-a", now=100.0)
        renewed = registry.renew(
            "chunk-key", "worker-a", lease.fencing_token, now=150.0
        )
        assert renewed.expires_at > lease.expires_at
        with pytest.raises(LeaseConflictError):
            registry.renew(
                "chunk-key", "worker-b", lease.fencing_token, now=150.0
            )
        released = registry.release(
            "chunk-key", "worker-a", lease.fencing_token, now=160.0
        )
        assert released.state == LEASE_RELEASED

    def test_transfer_issues_fresh_token_and_fences_stale_worker(self):
        registry = LeaseRegistry()
        old = registry.acquire("chunk-key", "worker-a", now=100.0)
        registry.expire_stale(now=500.0)
        new = registry.transfer("chunk-key", "worker-b", now=501.0)
        assert new.owner_worker_id == "worker-b"
        assert new.fencing_token != old.fencing_token
        assert new.transferred_from == "worker-a"
        # Stale worker with the OLD token is fenced out of every side effect.
        assert (
            registry.validate_fencing(
                "chunk-key", "worker-a", old.fencing_token, now=502.0
            )
            is False
        )
        assert (
            registry.validate_fencing(
                "chunk-key", "worker-b", new.fencing_token, now=502.0
            )
            is True
        )

    def test_transfer_requires_expired_or_released_without_force(self):
        registry = LeaseRegistry()
        registry.acquire("chunk-key", "worker-a", now=100.0)
        with pytest.raises(LeaseConflictError):
            registry.transfer("chunk-key", "worker-b", now=101.0)


class TestFramePublishValidator:
    def test_valid_frame_passes(self, tmp_path):
        path = tmp_path / "frame_0001.png"
        path.write_bytes(_png_bytes())
        dims = FramePublishValidator(
            expected_dimensions={"width": 1920, "height": 1080}
        ).validate(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        assert dims["width"] == 1920
        assert dims["height"] == 1080

    def test_zero_byte_rejected(self, tmp_path):
        path = tmp_path / "empty.png"
        path.write_bytes(b"")
        with pytest.raises(FramePublishError) as exc:
            FramePublishValidator().validate(path)
        assert "0-byte" in str(exc.value)

    def test_undecodable_rejected(self, tmp_path):
        path = tmp_path / "garbage.png"
        path.write_bytes(b"this is not an image at all")
        with pytest.raises(FramePublishError) as exc:
            FramePublishValidator().validate(path)
        assert "undecodable" in str(exc.value)

    def test_wrong_dimensions_rejected(self, tmp_path):
        path = tmp_path / "small.png"
        path.write_bytes(_png_bytes(640, 480))
        with pytest.raises(FramePublishError) as exc:
            FramePublishValidator(
                expected_dimensions={"width": 1920, "height": 1080}
            ).validate(path)
        assert "wrong dimensions" in str(exc.value)

    def test_hash_mismatch_rejected(self, tmp_path):
        path = tmp_path / "frame.png"
        path.write_bytes(_png_bytes())
        with pytest.raises(FramePublishError) as exc:
            FramePublishValidator().validate(path, expected_sha256="deadbeef")
        assert "hash mismatch" in str(exc.value)


class TestPublishFrame:
    def test_publish_is_atomic_and_registered(self, tmp_path):
        registry = LeaseRegistry()
        chunk = _chunk(frame_start=1, frame_end=1)
        lease = registry.acquire(chunk.chunk_id, "worker-a", now=100.0)
        manifest = _manifest(tmp_path, chunk, content_hash=chunk.content_hash())
        manifest.temp_path(1).write_bytes(_png_bytes())
        entry = publish_frame(
            registry=registry,
            chunk=chunk,
            worker_id="worker-a",
            fencing_token=lease.fencing_token,
            frame=1,
            manifest=manifest,
            now=101.0,
        )
        assert entry.frame == 1
        assert manifest.has_frame(1)
        assert manifest.next_frame() is None
        assert not manifest.temp_path(1).exists(), "temp must be atomically renamed"

    def test_stale_worker_cannot_publish_after_transfer(self, tmp_path):
        registry = LeaseRegistry()
        chunk = _chunk(frame_start=1, frame_end=1)
        old_lease = registry.acquire(chunk.chunk_id, "worker-a", now=100.0)
        registry.expire_stale(now=500.0)
        registry.transfer(chunk.chunk_id, "worker-b", now=501.0)
        manifest = _manifest(tmp_path, chunk)
        manifest.temp_path(1).write_bytes(_png_bytes())
        with pytest.raises(StaleWorkerPublishError):
            publish_frame(
                registry=registry,
                chunk=chunk,
                worker_id="worker-a",
                fencing_token=old_lease.fencing_token,
                frame=1,
                manifest=manifest,
                now=502.0,
            )
        assert not manifest.has_frame(1), "stale frame must never be published"

    def test_corrupt_frame_not_completed(self, tmp_path):
        registry = LeaseRegistry()
        chunk = _chunk(frame_start=1, frame_end=1)
        lease = registry.acquire(chunk.chunk_id, "worker-a", now=100.0)
        manifest = _manifest(tmp_path, chunk)
        manifest.temp_path(1).write_bytes(b"garbage")
        with pytest.raises(FramePublishError):
            publish_frame(
                registry=registry,
                chunk=chunk,
                worker_id="worker-a",
                fencing_token=lease.fencing_token,
                frame=1,
                manifest=manifest,
                now=101.0,
            )
        assert not manifest.has_frame(1)
        assert manifest.next_frame() == 1

    def test_wrong_hash_not_completed(self, tmp_path):
        registry = LeaseRegistry()
        chunk = _chunk(frame_start=1, frame_end=1)
        lease = registry.acquire(chunk.chunk_id, "worker-a", now=100.0)
        manifest = _manifest(tmp_path, chunk)
        manifest.temp_path(1).write_bytes(_png_bytes())
        with pytest.raises(FramePublishError):
            publish_frame(
                registry=registry,
                chunk=chunk,
                worker_id="worker-a",
                fencing_token=lease.fencing_token,
                frame=1,
                manifest=manifest,
                expected_sha256="beef",
                now=101.0,
            )
        assert not manifest.has_frame(1)


class TestRenderRecoveryCoordinator:
    def test_worker_killed_mid_chunk_transfers_and_resumes(self, tmp_path):
        registry = LeaseRegistry()
        chunk = _chunk(frame_start=1, frame_end=3, status=CHUNK_RENDERING)
        lease = registry.acquire(chunk.chunk_id, "worker-a", now=100.0)
        manifest = _manifest(tmp_path, chunk, content_hash=chunk.content_hash())
        # worker-a validated frame 1, then died; frame 2 is the next valid one
        manifest.temp_path(1).write_bytes(_png_bytes())
        manifest.finalize_frame(1)

        coordinator = RenderRecoveryCoordinator(registry)
        report = coordinator.reconcile(
            chunk,
            worker_id="worker-a",
            fencing_token=lease.fencing_token,
            successor_worker_id="worker-b",
            is_alive=lambda _: False,
            manifest=manifest,
            now=200.0,
        )
        assert report.crashed is True
        assert report.lease_transferred is True
        assert report.resume_frame == 2
        assert report.revised_chunk is not None
        assert report.revised_chunk.attempt == 1
        # chunk keeps its pinned range; the render resumes at the first gap
        assert report.revised_chunk.frame_start == 1
        assert report.revised_chunk.frame_end == 3
        assert report.revised_chunk.status == CHUNK_RENDERING
        # new owner holds the fresh token; old worker fenced
        new_lease = registry.get(chunk.chunk_id)
        assert new_lease.owner_worker_id == "worker-b"
        assert new_lease.fencing_token != lease.fencing_token
        assert (
            registry.validate_fencing(
                chunk.chunk_id, "worker-a", lease.fencing_token, now=201.0
            )
            is False
        )
        assert (
            registry.validate_fencing(
                chunk.chunk_id, "worker-b", new_lease.fencing_token, now=201.0
            )
            is True
        )

    def test_alive_worker_with_valid_lease_resumes_no_transfer(self, tmp_path):
        registry = LeaseRegistry()
        chunk = _chunk(frame_start=1, frame_end=3, status=CHUNK_RENDERING)
        lease = registry.acquire(chunk.chunk_id, "worker-a", now=100.0)
        manifest = _manifest(tmp_path, chunk, content_hash=chunk.content_hash())
        manifest.temp_path(1).write_bytes(_png_bytes())
        manifest.finalize_frame(1)
        report = RenderRecoveryCoordinator(registry).reconcile(
            chunk,
            worker_id="worker-a",
            fencing_token=lease.fencing_token,
            successor_worker_id="worker-b",
            is_alive=lambda _: True,
            manifest=manifest,
            now=150.0,
        )
        assert report.crashed is False
        assert report.lease_transferred is False
        assert report.resume_frame == 2
        assert report.revised_chunk.attempt == 0

    def test_complete_chunk_is_published(self, tmp_path):
        registry = LeaseRegistry()
        chunk = _chunk(frame_start=1, frame_end=2, status=CHUNK_RENDERING)
        lease = registry.acquire(chunk.chunk_id, "worker-a", now=100.0)
        manifest = _manifest(tmp_path, chunk, content_hash=chunk.content_hash())
        for frame in (1, 2):
            manifest.temp_path(frame).write_bytes(_png_bytes())
            manifest.finalize_frame(frame)
        report = RenderRecoveryCoordinator(registry).reconcile(
            chunk,
            worker_id="worker-a",
            fencing_token=lease.fencing_token,
            successor_worker_id="worker-b",
            is_alive=lambda _: True,
            manifest=manifest,
            now=150.0,
        )
        assert report.resume_frame is None
        assert report.revised_chunk.status == CHUNK_PUBLISHED

    def test_missing_frame_file_is_not_valid_and_resume_picks_it(self, tmp_path):
        registry = LeaseRegistry()
        chunk = _chunk(frame_start=1, frame_end=3, status=CHUNK_RENDERING)
        lease = registry.acquire(chunk.chunk_id, "worker-a", now=100.0)
        manifest = _manifest(tmp_path, chunk, content_hash=chunk.content_hash())
        for frame in (1, 2, 3):
            manifest.temp_path(frame).write_bytes(_png_bytes())
            manifest.finalize_frame(frame)
        # frame 2 file vanishes -> manifest load must drop it -> resume at 2
        manifest.final_path(2).unlink()
        reloaded = _manifest(tmp_path, chunk, content_hash=chunk.content_hash())
        assert not reloaded.has_frame(2)
        report = RenderRecoveryCoordinator(registry).reconcile(
            chunk,
            worker_id="worker-a",
            fencing_token=lease.fencing_token,
            successor_worker_id="worker-b",
            is_alive=lambda _: True,
            manifest=reloaded,
            now=150.0,
        )
        assert report.resume_frame == 2

    def test_changed_input_hashes_invalidate_partial_reuse(self, tmp_path):
        registry = LeaseRegistry()
        chunk = _chunk(frame_start=1, frame_end=3, status=CHUNK_RENDERING)
        lease = registry.acquire(chunk.chunk_id, "worker-a", now=100.0)
        # manifest pinned to a DIFFERENT content hash (changed render profile)
        manifest = _manifest(tmp_path, chunk, content_hash="old-profile-hash")
        manifest.temp_path(1).write_bytes(_png_bytes())
        manifest.finalize_frame(1)
        report = RenderRecoveryCoordinator(registry).reconcile(
            chunk,
            worker_id="worker-a",
            fencing_token=lease.fencing_token,
            successor_worker_id="worker-b",
            is_alive=lambda _: True,
            manifest=manifest,
            now=150.0,
        )
        assert report.resume_frame == chunk.frame_start
        assert report.revised_chunk.output_hashes == {}
        assert "input hashes changed" in report.reason


class TestRetryClassifier:
    def test_oom_retryable_with_replan(self):
        decision = RetryClassifier().classify(
            exit_code=1,
            stderr="CUDA error: out of memory in Cycles kernel",
            chunk_attempt=0,
        )
        assert decision.cause == RETRY_CAUSE_OOM
        assert decision.retryable is True
        assert decision.remaining_attempts == 2
        assert decision.replan is not None
        assert decision.replan.cause == RETRY_CAUSE_OOM
        assert decision.replan.mitigation == "texture_downscale"
        assert decision.replan.chunk_size_factor == 0.5

    def test_blender_crash_retryable_bounded(self):
        decision = RetryClassifier().classify(exit_code=139, stderr="", chunk_attempt=0)
        assert decision.cause == RETRY_CAUSE_BLENDER_CRASH
        assert decision.retryable is True
        assert decision.remaining_attempts == 2
        assert decision.replan is None

    def test_bad_asset_never_retried(self):
        decision = RetryClassifier().classify(
            exit_code=1, stderr="Error: not a blend file: 'scene.blend'", chunk_attempt=0
        )
        assert decision.cause == RETRY_CAUSE_BAD_ASSET
        assert decision.retryable is False
        assert decision.remaining_attempts == 0

    def test_disk_full_never_retried(self):
        decision = RetryClassifier().classify(
            exit_code=1, stderr="No space left on device", chunk_attempt=0
        )
        assert decision.cause == RETRY_CAUSE_DISK_FULL
        assert decision.retryable is False

    def test_timeout_retryable_with_smaller_chunk(self):
        decision = RetryClassifier().classify(timed_out=True, chunk_attempt=0)
        assert decision.cause == RETRY_CAUSE_TIMEOUT
        assert decision.retryable is True
        assert decision.replan.chunk_size_factor == 0.5

    def test_user_cancel_never_retried(self):
        decision = RetryClassifier().classify(canceled=True, chunk_attempt=0)
        assert decision.cause == RETRY_CAUSE_USER_CANCEL
        assert decision.retryable is False

    def test_unknown_cause_no_blind_retry(self):
        decision = RetryClassifier().classify(chunk_attempt=0)
        assert decision.cause == RETRY_CAUSE_UNKNOWN
        assert decision.retryable is False

    def test_attempt_budget_exhausted_stops_retry(self):
        classifier = RetryClassifier()
        decision = classifier.classify(
            exit_code=1, stderr="CUDA error: out of memory", chunk_attempt=2
        )
        assert classifier.should_retry(decision) is False
        decision = classifier.classify(
            exit_code=1, stderr="CUDA error: out of memory", chunk_attempt=1
        )
        assert classifier.should_retry(decision) is True


class TestAdapterChunkPlan:
    def make_adapter(self, tmp_path, fake_process, policy):
        fake_exe = tmp_path / "fake_blender" / "blender.exe"
        fake_exe.parent.mkdir(parents=True, exist_ok=True)
        fake_exe.write_bytes(b"MZ")
        config = BlenderEngineConfig(
            artifact_root=str(tmp_path / "artifacts"),
            state_dir=str(tmp_path / "state"),
            executable_path=str(fake_exe),
            render_job_policy=policy,
            default_timeout_seconds=30.0,
            heartbeat_seconds=0.05,
            cancel_grace_seconds=0.1,
        )
        return BlenderEngineAdapter(
            config=config,
            detector=make_detector(str(fake_exe), fake_process._version),
            capability_probe=BlenderCapabilityProbe(process_port=fake_process),
            gpu_probe=BlenderGpuProbe(),
            process_port=fake_process,
        )

    def test_chunk_plan_in_receipt_metadata(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3")
            policy = RenderJobPolicy(chunk_size=4)
            adapter = self.make_adapter(tmp_path, fake, policy)
            render = build_valid_ir().render_intents[0]
            receipt = await adapter.submit_shot(
                build_valid_ir().shots[0], render
            )
            assert receipt.status == EngineJobStatus.COMPLETED
            plan = receipt.metadata.get("render_job_plan")
            assert plan, "chunk plan must be present when policy is configured"
            start = render.frame_start
            end = receipt.metadata["render_job_plan"][-1]["frame_end"]
            assert end >= start
            for entry in plan:
                assert entry["frame_start"] <= entry["frame_end"]

        asyncio.run(_go())

    def test_resume_from_narrows_first_chunk(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3")
            policy = RenderJobPolicy(chunk_size=4)
            adapter = self.make_adapter(tmp_path, fake, policy)
            render = build_valid_ir().render_intents[0]
            render = render.model_copy(
                update={"metadata": {**render.metadata, "resume_from": 7}}
            )
            receipt = await adapter.submit_shot(build_valid_ir().shots[0], render)
            plan = receipt.metadata["render_job_plan"]
            assert plan[0].get("resume_from") == 7

        asyncio.run(_go())

    def test_no_policy_means_no_plan(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3")
            adapter = self.make_adapter(tmp_path, fake, None)
            receipt = await adapter.submit_shot(
                build_valid_ir().shots[0], build_valid_ir().render_intents[0]
            )
            assert receipt.status == EngineJobStatus.COMPLETED
            assert receipt.metadata.get("render_job_plan") is None

        asyncio.run(_go())
