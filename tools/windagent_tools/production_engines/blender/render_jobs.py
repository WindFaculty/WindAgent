"""VP3D Phase 21 - fault-tolerant render jobs for Cycles production renders.

Engine-neutral job/recovery kernel at the Blender adapter boundary (no ``bpy``
import, mirroring Phase 19 ``rendering`` and Phase 20 ``vram_budget``):

```text
episode -> scene -> shot -> frame chunk
```

Every chunk pins scene/shot/profile/asset hashes, frame start/end,
Blender/GPU, attempt and output hashes.  Components:

```text
ChunkSizeScheduler          -> chunk size from measured render time + recovery
                               overhead (overhead-fraction budget formula)
RenderJobPlanner            -> episode/scene/shot -> frame chunk plan
LeaseRegistry               -> idempotency-key reservation BEFORE any side
                               effect; one worker owns a chunk via a fencing
                               token; lease expiry + owner transfer fence stale
                               workers out of every later publish
FramePublishValidator       -> atomic publish; 0-byte / undecodable / wrong
                               dimension / wrong hash are NEVER completed
RenderRecoveryCoordinator   -> crash reconcile (PID + lease + frame manifest),
                               resume from the next valid frame; partial reuse
                               only when ALL input hashes still match
RetryClassifier             -> OOM / Blender crash / bad asset / timeout /
                               disk full / user cancel; OOM triggers a replan
                               (Phase 20 mitigation + smaller chunk), a
                               deterministic bad asset is never retried
```

Job model: one ``RenderJob`` per shot, one ``FrameChunk`` per contiguous frame
range, one ``ChunkLease`` per chunk.  All models are immutable frozen
dataclasses with deterministic ``content_hash()``; services never mutate
state in place.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from windagent_tools.production_engines.blender.vram_budget import MITIGATION_ORDER
from windagent_tools.production_engines.blender.scene.frames import (
    FrameEntry,
    FrameManifest,
    probe_dimensions,
    sha256_file,
)

RENDER_JOB_SCHEMA_VERSION = "render-jobs-1.0.0"

# Chunk lifecycle states.
CHUNK_PENDING = "PENDING"
CHUNK_RESERVED = "RESERVED"
CHUNK_RENDERING = "RENDERING"
CHUNK_PUBLISHED = "PUBLISHED"
CHUNK_FAILED = "FAILED"
CHUNK_CANCELED = "CANCELED"
CHUNK_STATES = (
    CHUNK_PENDING,
    CHUNK_RESERVED,
    CHUNK_RENDERING,
    CHUNK_PUBLISHED,
    CHUNK_FAILED,
    CHUNK_CANCELED,
)

# Lease lifecycle states.
LEASE_ACTIVE = "ACTIVE"
LEASE_EXPIRED = "EXPIRED"
LEASE_RELEASED = "RELEASED"
LEASE_STATES = (LEASE_ACTIVE, LEASE_EXPIRED, LEASE_RELEASED)

# Retry causes (Phase 21 backlog item 6).
RETRY_CAUSE_OOM = "OOM"
RETRY_CAUSE_BLENDER_CRASH = "BLENDER_CRASH"
RETRY_CAUSE_BAD_ASSET = "BAD_ASSET"
RETRY_CAUSE_TIMEOUT = "TIMEOUT"
RETRY_CAUSE_DISK_FULL = "DISK_FULL"
RETRY_CAUSE_USER_CANCEL = "USER_CANCEL"
RETRY_CAUSE_UNKNOWN = "UNKNOWN"
RETRY_CAUSES = (
    RETRY_CAUSE_OOM,
    RETRY_CAUSE_BLENDER_CRASH,
    RETRY_CAUSE_BAD_ASSET,
    RETRY_CAUSE_TIMEOUT,
    RETRY_CAUSE_DISK_FULL,
    RETRY_CAUSE_USER_CANCEL,
    RETRY_CAUSE_UNKNOWN,
)

DEFAULT_LEASE_SECONDS = 300.0
DEFAULT_RECOVERY_FRACTION_BUDGET = 0.10
DEFAULT_MIN_CHUNK_FRAMES = 1
DEFAULT_MAX_CHUNK_FRAMES = 256
OOM_REPLAN_CHUNK_FACTOR = 0.5

# Failure marker tables (deterministic classification, backlog item 6).
OOM_MARKERS = (
    "out of memory",
    "out-of-memory",
    "cuda error: out of memory",
    "memory exhausted",
    "bad_alloc",
)
DISK_FULL_MARKERS = (
    "no space left on device",
    "disk full",
    "errno 28",
)
BAD_ASSET_MARKERS = (
    "not a blend file",
    "cannot be opened",
    "failed to open",
    "invalid blend",
    "error parsing",
    "asset not found",
    "missing asset",
    "unable to load",
)
CRASH_MARKERS = (
    "segmentation fault",
    "segfault",
    "aborted",
    "fatal error",
    "crash",
)
CANCEL_MARKERS = (
    "cancel",
    "cancelled",
    "canceled",
)

# Max attempts per retry cause (bounded, never infinite).
MAX_ATTEMPTS_BY_CAUSE: Dict[str, int] = {
    RETRY_CAUSE_OOM: 2,
    RETRY_CAUSE_BLENDER_CRASH: 2,
    RETRY_CAUSE_TIMEOUT: 2,
    RETRY_CAUSE_BAD_ASSET: 0,
    RETRY_CAUSE_DISK_FULL: 0,
    RETRY_CAUSE_USER_CANCEL: 0,
    RETRY_CAUSE_UNKNOWN: 0,
}


class ChunkPlanError(ValueError):
    """A chunk plan cannot be built from the given inputs."""


class LeaseConflictError(RuntimeError):
    """The idempotency key is already owned by another active lease."""


class StaleWorkerPublishError(RuntimeError):
    """A worker whose lease was transferred tried to publish a frame."""


class FramePublishError(ValueError):
    """A frame failed publish validation (empty/undecodable/wrong dims/hash)."""


def _canonical_hash(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalise_hashes(value: Any) -> Dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): str(item)
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        if str(key) and str(item)
    }


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Job / chunk models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrameChunk:
    """One contiguous frame range of a render job, fully pinned.

    ``content_hash`` covers every input that determines the rendered output:
    scene/shot/profile/asset hashes, frame range, Blender and GPU class.
    Attempt, status and output hashes are execution state, NOT content, so a
    retry of the same input keeps the same content hash (cache/reuse identity).
    """

    chunk_id: str
    job_id: str
    episode_id: str
    scene_id: str
    shot_id: str
    scene_hash: str
    shot_hash: str
    profile_hash: str
    frame_start: int
    frame_end: int
    blender_version: str
    device_class: str
    asset_hashes: Dict[str, str] = field(default_factory=dict)
    attempt: int = 0
    status: str = CHUNK_PENDING
    output_hashes: Dict[str, str] = field(default_factory=dict)
    schema_version: str = RENDER_JOB_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "chunk_id": self.chunk_id,
            "job_id": self.job_id,
            "episode_id": self.episode_id,
            "scene_id": self.scene_id,
            "shot_id": self.shot_id,
            "scene_hash": self.scene_hash,
            "shot_hash": self.shot_hash,
            "profile_hash": self.profile_hash,
            "frame_start": self.frame_start,
            "frame_end": self.frame_end,
            "blender_version": self.blender_version,
            "device_class": self.device_class,
            "asset_hashes": dict(self.asset_hashes),
            "attempt": self.attempt,
            "status": self.status,
            "output_hashes": dict(self.output_hashes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FrameChunk":
        return cls(
            schema_version=str(
                data.get("schema_version", RENDER_JOB_SCHEMA_VERSION)
            ),
            chunk_id=str(data.get("chunk_id", "")),
            job_id=str(data.get("job_id", "")),
            episode_id=str(data.get("episode_id", "")),
            scene_id=str(data.get("scene_id", "")),
            shot_id=str(data.get("shot_id", "")),
            scene_hash=str(data.get("scene_hash", "")),
            shot_hash=str(data.get("shot_hash", "")),
            profile_hash=str(data.get("profile_hash", "")),
            frame_start=int(data.get("frame_start", 0)),
            frame_end=int(data.get("frame_end", 0)),
            blender_version=str(data.get("blender_version", "")),
            device_class=str(data.get("device_class", "")),
            asset_hashes=_normalise_hashes(data.get("asset_hashes")),
            attempt=int(data.get("attempt", 0)),
            status=str(data.get("status", CHUNK_PENDING)),
            output_hashes=_normalise_hashes(data.get("output_hashes")),
        )

    def content_hash(self) -> str:
        """Deterministic identity over every input that shapes the output."""
        return _canonical_hash(
            {
                "scene_hash": self.scene_hash,
                "shot_hash": self.shot_hash,
                "profile_hash": self.profile_hash,
                "asset_hashes": dict(self.asset_hashes),
                "frame_start": self.frame_start,
                "frame_end": self.frame_end,
                "blender_version": self.blender_version,
                "device_class": self.device_class,
            }
        )

    @property
    def frame_count(self) -> int:
        return self.frame_end - self.frame_start + 1


@dataclass(frozen=True)
class RenderJob:
    """episode -> scene -> shot -> chunks; one job per shot."""

    job_id: str
    episode_id: str
    scene_id: str
    shot_id: str
    chunks: Tuple[FrameChunk, ...]
    schema_version: str = RENDER_JOB_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "episode_id": self.episode_id,
            "scene_id": self.scene_id,
            "shot_id": self.shot_id,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RenderJob":
        return cls(
            schema_version=str(
                data.get("schema_version", RENDER_JOB_SCHEMA_VERSION)
            ),
            job_id=str(data.get("job_id", "")),
            episode_id=str(data.get("episode_id", "")),
            scene_id=str(data.get("scene_id", "")),
            shot_id=str(data.get("shot_id", "")),
            chunks=tuple(
                FrameChunk.from_dict(item)
                for item in data.get("chunks", []) or []
                if isinstance(item, Mapping)
            ),
        )


# ---------------------------------------------------------------------------
# Chunk scheduling (backlog item 1)
# ---------------------------------------------------------------------------


class ChunkSizeScheduler:
    """Pick chunk size from MEASURED render time and recovery overhead.

    A chunk that fails costs ``recovery_overhead_seconds`` (requeue, lease
    transfer, process restart).  To keep that overhead under a fraction of the
    chunk's own render time:

        frames >= recovery_overhead / (budget * seconds_per_frame)

    The result is clamped to [min_frames, max_frames]; when the clamp wins the
    budget is exceeded and the planner reports it via ``exceeds_budget``.
    """

    def __init__(
        self,
        recovery_fraction_budget: float = DEFAULT_RECOVERY_FRACTION_BUDGET,
        min_frames: int = DEFAULT_MIN_CHUNK_FRAMES,
        max_frames: int = DEFAULT_MAX_CHUNK_FRAMES,
    ) -> None:
        if recovery_fraction_budget <= 0.0 or recovery_fraction_budget > 1.0:
            raise ChunkPlanError("recovery_fraction_budget must be in (0, 1]")
        if min_frames < 1:
            raise ChunkPlanError("min_frames must be >= 1")
        if max_frames < min_frames:
            raise ChunkPlanError("max_frames must be >= min_frames")
        self._budget = recovery_fraction_budget
        self._min = min_frames
        self._max = max_frames

    @property
    def min_frames(self) -> int:
        return self._min

    @property
    def max_frames(self) -> int:
        return self._max

    @property
    def recovery_fraction_budget(self) -> float:
        return self._budget

    def suggest(
        self,
        measured_seconds_per_frame: float,
        recovery_overhead_seconds: float,
    ) -> Tuple[int, bool]:
        """Return (chunk_frames, exceeds_budget). Fail closed on bad input."""
        if measured_seconds_per_frame <= 0.0:
            raise ChunkPlanError(
                "measured_seconds_per_frame must be positive; a chunk size "
                "cannot be derived from an unmeasured render"
            )
        if recovery_overhead_seconds < 0.0:
            raise ChunkPlanError("recovery_overhead_seconds must be >= 0")
        if recovery_overhead_seconds == 0.0:
            return self._max, False
        frames = math.ceil(
            recovery_overhead_seconds
            / (self._budget * measured_seconds_per_frame)
        )
        exceeds = frames > self._max
        return max(self._min, min(self._max, frames)), exceeds

    def plan_chunks(
        self, frame_start: int, frame_end: int, chunk_size: int
    ) -> Tuple[Tuple[int, int], ...]:
        """Split [frame_start, frame_end] into contiguous chunk ranges."""
        if frame_start > frame_end:
            raise ChunkPlanError(
                f"frame_start {frame_start} must be <= frame_end {frame_end}"
            )
        if chunk_size < 1:
            raise ChunkPlanError("chunk_size must be >= 1")
        ranges: List[Tuple[int, int]] = []
        cursor = frame_start
        while cursor <= frame_end:
            stop = min(cursor + chunk_size - 1, frame_end)
            ranges.append((cursor, stop))
            cursor = stop + 1
        return tuple(ranges)


class RenderJobPlanner:
    """Build the shot-level job model: episode -> scene -> shot -> chunks."""

    def __init__(self, scheduler: Optional[ChunkSizeScheduler] = None) -> None:
        self._scheduler = scheduler or ChunkSizeScheduler()

    @property
    def scheduler(self) -> ChunkSizeScheduler:
        return self._scheduler

    def plan_job(
        self,
        *,
        job_id: str,
        episode_id: str,
        scene_id: str,
        shot_id: str,
        scene_hash: str,
        shot_hash: str,
        profile_hash: str,
        asset_hashes: Optional[Mapping[str, str]] = None,
        frame_start: int,
        frame_end: int,
        blender_version: str,
        device_class: str,
        chunk_size: Optional[int] = None,
        measured_seconds_per_frame: Optional[float] = None,
        recovery_overhead_seconds: float = 0.0,
    ) -> RenderJob:
        """Plan chunks; chunk_size wins, else measured timing sizes it."""
        if chunk_size is None:
            if measured_seconds_per_frame is None:
                raise ChunkPlanError(
                    "chunk_size or measured_seconds_per_frame is required"
                )
            chunk_size, _ = self._scheduler.suggest(
                measured_seconds_per_frame, recovery_overhead_seconds
            )
        ranges = self._scheduler.plan_chunks(frame_start, frame_end, chunk_size)
        chunks = tuple(
            FrameChunk(
                chunk_id=f"{job_id}:chunk-{index:03d}",
                job_id=job_id,
                episode_id=episode_id,
                scene_id=scene_id,
                shot_id=shot_id,
                scene_hash=scene_hash,
                shot_hash=shot_hash,
                profile_hash=profile_hash,
                asset_hashes=_normalise_hashes(asset_hashes),
                frame_start=start,
                frame_end=stop,
                blender_version=blender_version,
                device_class=device_class,
            )
            for index, (start, stop) in enumerate(ranges)
        )
        return RenderJob(
            job_id=job_id,
            episode_id=episode_id,
            scene_id=scene_id,
            shot_id=shot_id,
            chunks=chunks,
        )


@dataclass(frozen=True)
class RenderJobPolicy:
    """Adapter-facing Phase 21 policy: chunk planning + lease duration.

    ``chunk_size`` overrides the scheduler; when both it and measured timing
    are unavailable the adapter plans ONE chunk covering the whole range
    (an unmeasured render cannot be sized - honest single-chunk default).
    """

    chunk_size: Optional[int] = None
    lease_seconds: float = DEFAULT_LEASE_SECONDS
    scheduler: ChunkSizeScheduler = field(default_factory=ChunkSizeScheduler)


# ---------------------------------------------------------------------------
# Lease / fencing ownership (backlog items 2 and 5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkLease:
    """Ownership of one chunk by exactly one worker.

    ``fencing_token`` is unforgeable ownership proof: every side effect
    (publish, renew, release) must present it.  Transferring a lease replaces
    the token, so a stale worker holding the old token is fenced out of every
    later publish (backlog item 5).
    """

    idempotency_key: str
    owner_worker_id: str
    fencing_token: str
    acquired_at: float
    expires_at: float
    state: str = LEASE_ACTIVE
    transferred_from: str = ""

    def to_dict(self) -> dict:
        return {
            "idempotency_key": self.idempotency_key,
            "owner_worker_id": self.owner_worker_id,
            "fencing_token": self.fencing_token,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "state": self.state,
            "transferred_from": self.transferred_from,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ChunkLease":
        return cls(
            idempotency_key=str(data.get("idempotency_key", "")),
            owner_worker_id=str(data.get("owner_worker_id", "")),
            fencing_token=str(data.get("fencing_token", "")),
            acquired_at=float(data.get("acquired_at", 0.0)),
            expires_at=float(data.get("expires_at", 0.0)),
            state=str(data.get("state", LEASE_ACTIVE)),
            transferred_from=str(data.get("transferred_from", "")),
        )

    def is_expired(self, now: float) -> bool:
        return now >= self.expires_at


class LeaseRegistry:
    """In-memory lease store keyed by idempotency key.

    ``acquire`` RESERVES the idempotency key before any side effect: a second
    dispatch for the same key while the first lease is active is rejected
    (duplicate-dispatch protection).  Tokens are random; every mutation
    validates owner + token.
    """

    def __init__(self) -> None:
        self._leases: Dict[str, ChunkLease] = {}

    def to_dict(self) -> dict:
        return {
            "leases": [lease.to_dict() for lease in self._leases.values()]
        }

    def get(self, idempotency_key: str) -> Optional[ChunkLease]:
        return self._leases.get(str(idempotency_key))

    def acquire(
        self,
        idempotency_key: str,
        worker_id: str,
        *,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        now: Optional[float] = None,
    ) -> ChunkLease:
        key = str(idempotency_key)
        if not key:
            raise LeaseConflictError("idempotency key must not be empty")
        now = _now() if now is None else now
        existing = self._leases.get(key)
        if existing is not None and existing.state == LEASE_ACTIVE and not existing.is_expired(now):
            raise LeaseConflictError(
                f"idempotency key {key} already owned by worker "
                f"{existing.owner_worker_id} (duplicate dispatch rejected)"
            )
        lease = ChunkLease(
            idempotency_key=key,
            owner_worker_id=str(worker_id),
            fencing_token=secrets.token_hex(16),
            acquired_at=now,
            expires_at=now + lease_seconds,
        )
        self._leases[key] = lease
        return lease

    def renew(
        self,
        idempotency_key: str,
        worker_id: str,
        fencing_token: str,
        *,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        now: Optional[float] = None,
    ) -> ChunkLease:
        now = _now() if now is None else now
        lease = self._require_owned(idempotency_key, worker_id, fencing_token, now)
        renewed = replace(lease, expires_at=now + lease_seconds)
        self._leases[lease.idempotency_key] = renewed
        return renewed

    def release(
        self,
        idempotency_key: str,
        worker_id: str,
        fencing_token: str,
        *,
        now: Optional[float] = None,
    ) -> ChunkLease:
        now = _now() if now is None else now
        lease = self._require_owned(idempotency_key, worker_id, fencing_token, now)
        released = replace(lease, state=LEASE_RELEASED)
        self._leases[lease.idempotency_key] = released
        return released

    def expire_stale(self, *, now: Optional[float] = None) -> int:
        """Mark ACTIVE leases past their expiry as EXPIRED; return count."""
        now = _now() if now is None else now
        expired = 0
        for key, lease in self._leases.items():
            if lease.state == LEASE_ACTIVE and lease.is_expired(now):
                self._leases[key] = replace(lease, state=LEASE_EXPIRED)
                expired += 1
        return expired

    def transfer(
        self,
        idempotency_key: str,
        new_worker_id: str,
        *,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        now: Optional[float] = None,
        force: bool = False,
    ) -> ChunkLease:
        """Hand ownership to a new worker with a FRESH fencing token.

        The old token stops matching immediately (``validate_fencing`` uses
        the current token), so the stale worker can no longer publish.  Only
        EXPIRED/RELEASED leases transfer by default; ``force`` allows a live
        takeover after a crash reconcile decision.
        """
        now = _now() if now is None else now
        key = str(idempotency_key)
        existing = self._leases.get(key)
        if existing is None:
            raise LeaseConflictError(f"no lease exists for key {key}")
        if not force and existing.state not in (LEASE_EXPIRED, LEASE_RELEASED):
            raise LeaseConflictError(
                f"lease {key} is {existing.state}; only EXPIRED/RELEASED "
                "leases can transfer without force"
            )
        lease = ChunkLease(
            idempotency_key=key,
            owner_worker_id=str(new_worker_id),
            fencing_token=secrets.token_hex(16),
            acquired_at=now,
            expires_at=now + lease_seconds,
            transferred_from=existing.owner_worker_id,
        )
        self._leases[key] = lease
        return lease

    def validate_fencing(
        self,
        idempotency_key: str,
        worker_id: str,
        fencing_token: str,
        *,
        now: Optional[float] = None,
    ) -> bool:
        """True only for the CURRENT owner holding the CURRENT token."""
        now = _now() if now is None else now
        lease = self._leases.get(str(idempotency_key))
        if lease is None:
            return False
        if lease.state != LEASE_ACTIVE or lease.is_expired(now):
            return False
        return (
            lease.owner_worker_id == str(worker_id)
            and lease.fencing_token == str(fencing_token)
        )

    def _require_owned(
        self,
        idempotency_key: str,
        worker_id: str,
        fencing_token: str,
        now: float,
    ) -> ChunkLease:
        if not self.validate_fencing(
            idempotency_key, worker_id, fencing_token, now=now
        ):
            raise LeaseConflictError(
                f"worker {worker_id} does not own lease {idempotency_key} "
                "(stale or transferred lease)"
            )
        lease = self._leases[str(idempotency_key)]
        assert lease is not None
        return lease


# ---------------------------------------------------------------------------
# Atomic frame publish validation (backlog item 3, fenced by item 5)
# ---------------------------------------------------------------------------


class FramePublishValidator:
    """Validate a candidate frame BEFORE it becomes final.

    0-byte, undecodable, wrong-dimension and wrong-hash frames raise
    ``FramePublishError`` and are never registered as completed.
    """

    def __init__(
        self, expected_dimensions: Optional[Mapping[str, int]] = None
    ) -> None:
        self._expected_dimensions = dict(expected_dimensions or {})

    @property
    def expected_dimensions(self) -> Dict[str, int]:
        return dict(self._expected_dimensions)

    def validate(self, path, expected_sha256: str = "") -> Dict[str, int]:
        """Return probed dimensions; raise FramePublishError on any defect."""
        if not path.is_file():
            raise FramePublishError(f"frame file missing: {path}")
        if path.stat().st_size == 0:
            raise FramePublishError(f"0-byte frame rejected: {path}")
        dims = probe_dimensions(path)
        if not dims:
            raise FramePublishError(f"undecodable frame rejected: {path}")
        if self._expected_dimensions:
            width = dims.get("width", 0)
            height = dims.get("height", 0)
            if width and height:
                if (
                    width != self._expected_dimensions.get("width", 0)
                    or height != self._expected_dimensions.get("height", 0)
                ):
                    raise FramePublishError(
                        f"wrong dimensions {width}x{height}, expected "
                        f"{self._expected_dimensions.get('width')}x"
                        f"{self._expected_dimensions.get('height')}"
                    )
        if expected_sha256 and sha256_file(path) != expected_sha256:
            raise FramePublishError(
                f"hash mismatch for {path.name}: expected {expected_sha256}"
            )
        return dims


def publish_frame(
    *,
    registry: LeaseRegistry,
    chunk: FrameChunk,
    worker_id: str,
    fencing_token: str,
    frame: int,
    manifest: FrameManifest,
    expected_sha256: str = "",
    validator: Optional[FramePublishValidator] = None,
    now: Optional[float] = None,
) -> FrameEntry:
    """Fenced, validated, atomic frame publish.

    Order: fencing check (stale worker dies here) -> validation on the temp
    file -> atomic rename + manifest registration via ``FrameManifest``.
    Nothing is published when any check fails.
    """
    now = _now() if now is None else now
    if not registry.validate_fencing(
        chunk.chunk_id, worker_id, fencing_token, now=now
    ):
        raise StaleWorkerPublishError(
            f"worker {worker_id} lost the lease on chunk {chunk.chunk_id}; "
            "its frames must not be published"
        )
    validator = validator or FramePublishValidator()
    temp = manifest.temp_path(frame)
    validator.validate(temp, expected_sha256=expected_sha256)
    entry = manifest.finalize_frame(frame)
    if entry is None:
        raise FramePublishError(f"frame {frame} failed atomic finalization")
    if expected_sha256 and entry.sha256 != expected_sha256:
        raise FramePublishError(
            f"frame {frame} hash drifted after finalization "
            f"({entry.sha256} != {expected_sha256})"
        )
    return entry


# ---------------------------------------------------------------------------
# Crash reconcile / resume (backlog item 4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecoveryReport:
    """Outcome of one crash-reconcile pass over a chunk."""

    chunk_id: str
    crashed: bool
    lease_transferred: bool
    resume_frame: Optional[int]
    revised_chunk: Optional[FrameChunk]
    reason: str

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "crashed": self.crashed,
            "lease_transferred": self.lease_transferred,
            "resume_frame": self.resume_frame,
            "revised_chunk": (
                self.revised_chunk.to_dict()
                if self.revised_chunk is not None
                else None
            ),
            "reason": self.reason,
        }


class RenderRecoveryCoordinator:
    """Reconcile worker PID / lease / frame manifest after a crash or restart.

    Rules:

    - worker alive + lease valid  -> no transfer; resume from next valid frame
    - worker dead OR lease expired-> crash: lease transfers to the successor
      worker (fresh fencing token), chunk attempt +1, resume from next valid
      frame (``FrameManifest.next_frame`` = first gap, backlog item 4)
    - partial reuse is only allowed when ALL input hashes still match: the
      frame manifest pins the chunk ``content_hash``; a changed profile / scene
      / asset hash invalidates every published frame and the chunk restarts
      from its own frame_start (test matrix: changed render profile)
    """

    def __init__(
        self,
        registry: LeaseRegistry,
        *,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
    ) -> None:
        self._registry = registry
        self._lease_seconds = lease_seconds

    def reconcile(
        self,
        chunk: FrameChunk,
        *,
        worker_id: str,
        fencing_token: str,
        successor_worker_id: str,
        is_alive: Callable[[str], bool],
        manifest: FrameManifest,
        now: Optional[float] = None,
    ) -> RecoveryReport:
        now = _now() if now is None else now
        lease = self._registry.get(chunk.chunk_id)

        # Input-hash gate: partial reuse requires identical input hashes.
        if manifest.content_hash and manifest.content_hash != chunk.content_hash():
            return RecoveryReport(
                chunk_id=chunk.chunk_id,
                crashed=False,
                lease_transferred=False,
                resume_frame=chunk.frame_start,
                revised_chunk=replace(
                    chunk,
                    attempt=chunk.attempt + 1,
                    status=CHUNK_RENDERING,
                    output_hashes={},
                ),
                reason=(
                    "input hashes changed (profile/scene/asset); published "
                    "frames invalidated, chunk restarts from frame_start"
                ),
            )

        resume_frame = manifest.next_frame()
        if resume_frame is None:
            return RecoveryReport(
                chunk_id=chunk.chunk_id,
                crashed=False,
                lease_transferred=False,
                resume_frame=None,
                revised_chunk=replace(chunk, status=CHUNK_PUBLISHED),
                reason="all frames validated; chunk is complete",
            )

        alive = False
        try:
            alive = bool(is_alive(worker_id))
        except Exception:  # pragma: no cover - injected liveness probe
            alive = False

        lease_active = (
            lease is not None
            and lease.state == LEASE_ACTIVE
            and not lease.is_expired(now)
            and lease.owner_worker_id == worker_id
            and lease.fencing_token == fencing_token
        )

        if alive and lease_active:
            return RecoveryReport(
                chunk_id=chunk.chunk_id,
                crashed=False,
                lease_transferred=False,
                resume_frame=resume_frame,
                revised_chunk=chunk,
                reason=(
                    f"worker {worker_id} alive with valid lease; resume from "
                    f"frame {resume_frame}"
                ),
            )

        # Crash path: worker dead or lease stale -> transfer + attempt +1.
        successor = self._registry.transfer(
            chunk.chunk_id,
            successor_worker_id,
            lease_seconds=self._lease_seconds,
            now=now,
            force=True,
        )
        return RecoveryReport(
            chunk_id=chunk.chunk_id,
            crashed=True,
            lease_transferred=True,
            resume_frame=resume_frame,
            revised_chunk=replace(
                chunk,
                attempt=chunk.attempt + 1,
                status=CHUNK_RENDERING,
                output_hashes={},
            ),
            reason=(
                f"worker {worker_id} {'dead' if not alive else 'lost lease'}; "
                f"lease transferred to {successor_worker_id} (token "
                f"{successor.fencing_token[:8]}...); resume from frame "
                f"{resume_frame}"
            ),
        )


# ---------------------------------------------------------------------------
# Retry classification (backlog items 6 and 7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplanAction:
    """Mitigation/replan hint attached to a retryable failure."""

    cause: str
    mitigation: str
    chunk_size_factor: float
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "cause": self.cause,
            "mitigation": self.mitigation,
            "chunk_size_factor": self.chunk_size_factor,
            "note": self.note,
        }


@dataclass(frozen=True)
class RetryDecision:
    """Classification of one failed chunk attempt."""

    cause: str
    retryable: bool
    remaining_attempts: int
    replan: Optional[ReplanAction]
    reason: str

    def to_dict(self) -> dict:
        return {
            "cause": self.cause,
            "retryable": self.retryable,
            "remaining_attempts": self.remaining_attempts,
            "replan": self.replan.to_dict() if self.replan is not None else None,
            "reason": self.reason,
        }


def _contains_any(text: str, markers: Tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


class RetryClassifier:
    """Classify a failed render into a retry cause + bounded policy.

    OOM -> retryable, replan (Phase 20 mitigation first step + smaller chunk);
    Blender crash -> retryable, bounded; timeout -> retryable, smaller chunk;
    deterministic bad asset / disk full / user cancel -> NOT retryable
    (backlog item 7: no useless retries).
    """

    def __init__(
        self,
        max_attempts_by_cause: Optional[Mapping[str, int]] = None,
    ) -> None:
        self._max_attempts = dict(
            max_attempts_by_cause or MAX_ATTEMPTS_BY_CAUSE
        )

    @property
    def max_attempts_by_cause(self) -> Dict[str, int]:
        return dict(self._max_attempts)

    def classify(
        self,
        *,
        exit_code: Optional[int] = None,
        stderr: str = "",
        error: str = "",
        timed_out: bool = False,
        canceled: bool = False,
        chunk_attempt: int = 0,
    ) -> RetryDecision:
        blob = f"{stderr}\n{error}"
        if canceled or _contains_any(blob, CANCEL_MARKERS):
            return self._decision(
                RETRY_CAUSE_USER_CANCEL, chunk_attempt, "user canceled the render"
            )
        if timed_out:
            return RetryDecision(
                cause=RETRY_CAUSE_TIMEOUT,
                retryable=True,
                remaining_attempts=max(
                    0, self._max_attempts.get(RETRY_CAUSE_TIMEOUT, 0) - chunk_attempt
                ),
                replan=ReplanAction(
                    cause=RETRY_CAUSE_TIMEOUT,
                    mitigation="smaller_chunk",
                    chunk_size_factor=OOM_REPLAN_CHUNK_FACTOR,
                    note="timeout suggests per-frame cost under-estimation; halve chunk size",
                ),
                reason="render exceeded the timeout budget",
            )
        if _contains_any(blob, OOM_MARKERS):
            return RetryDecision(
                cause=RETRY_CAUSE_OOM,
                retryable=True,
                remaining_attempts=max(
                    0, self._max_attempts.get(RETRY_CAUSE_OOM, 0) - chunk_attempt
                ),
                replan=ReplanAction(
                    cause=RETRY_CAUSE_OOM,
                    mitigation=str(MITIGATION_ORDER[0]),
                    chunk_size_factor=OOM_REPLAN_CHUNK_FACTOR,
                    note=(
                        f"OOM triggers mitigation/replan: run Phase 20 "
                        f"{MITIGATION_ORDER[0]} on the derived scene and halve "
                        "the chunk size"
                    ),
                ),
                reason="out-of-memory failure detected in render output",
            )
        if _contains_any(blob, DISK_FULL_MARKERS):
            return self._decision(
                RETRY_CAUSE_DISK_FULL,
                chunk_attempt,
                "no storage space; operator must free disk before retry",
            )
        if _contains_any(blob, BAD_ASSET_MARKERS):
            return self._decision(
                RETRY_CAUSE_BAD_ASSET,
                chunk_attempt,
                "deterministic bad asset (blend/scene/asset unreadable); retrying cannot help",
            )
        if exit_code not in (None, 0) or _contains_any(blob, CRASH_MARKERS):
            return RetryDecision(
                cause=RETRY_CAUSE_BLENDER_CRASH,
                retryable=True,
                remaining_attempts=max(
                    0,
                    self._max_attempts.get(RETRY_CAUSE_BLENDER_CRASH, 0)
                    - chunk_attempt,
                ),
                replan=None,
                reason=(
                    f"blender process crashed (exit {exit_code}) without a "
                    "deterministic defect marker"
                ),
            )
        return self._decision(
            RETRY_CAUSE_UNKNOWN,
            chunk_attempt,
            "unclassified failure; no blind retry without a cause",
        )

    def _decision(
        self, cause: str, chunk_attempt: int, reason: str
    ) -> RetryDecision:
        max_attempts = self._max_attempts.get(cause, 0)
        return RetryDecision(
            cause=cause,
            retryable=max_attempts > 0,
            remaining_attempts=max(0, max_attempts - chunk_attempt),
            replan=None,
            reason=reason,
        )

    def should_retry(self, decision: RetryDecision) -> bool:
        return decision.retryable and decision.remaining_attempts > 0


__all__ = [
    "RENDER_JOB_SCHEMA_VERSION",
    "CHUNK_PENDING",
    "CHUNK_RESERVED",
    "CHUNK_RENDERING",
    "CHUNK_PUBLISHED",
    "CHUNK_FAILED",
    "CHUNK_CANCELED",
    "LEASE_ACTIVE",
    "LEASE_EXPIRED",
    "LEASE_RELEASED",
    "RETRY_CAUSE_OOM",
    "RETRY_CAUSE_BLENDER_CRASH",
    "RETRY_CAUSE_BAD_ASSET",
    "RETRY_CAUSE_TIMEOUT",
    "RETRY_CAUSE_DISK_FULL",
    "RETRY_CAUSE_USER_CANCEL",
    "RETRY_CAUSE_UNKNOWN",
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_RECOVERY_FRACTION_BUDGET",
    "OOM_REPLAN_CHUNK_FACTOR",
    "ChunkPlanError",
    "LeaseConflictError",
    "StaleWorkerPublishError",
    "FramePublishError",
    "FrameChunk",
    "RenderJob",
    "ChunkSizeScheduler",
    "RenderJobPlanner",
    "RenderJobPolicy",
    "ChunkLease",
    "LeaseRegistry",
    "FramePublishValidator",
    "publish_frame",
    "RecoveryReport",
    "RenderRecoveryCoordinator",
    "ReplanAction",
    "RetryDecision",
    "RetryClassifier",
]
