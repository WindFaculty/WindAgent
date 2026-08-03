"""
Phase 15 — Video candidate acquisition (plan 04 §23.3).

For every video candidate in a job:

    stable identity within the job
        → download into quarantine
        → hash / MIME sniff / payload classification
        → technical inspection (video stream, duration, resolution, fps)
        → publish into the canonical content-addressed store ATOMICALLY
        → link request hash + Flow project/job

Reuses the canonical `ContentAddressedStore` (atomic publish, no partial
artifact) and `classify_payload` (zero-byte / polyglot / exec / archive /
SVG rejection). The video-specific stream validation runs through the
`VideoInspectorPort` + `VideoInspectionPolicy` (plan 04 §23.3). A failed or
invalid candidate is NEVER published and is surfaced as
`VideoCandidateInvalidError` — and the job is NEVER marked COMPLETED with an
invalid candidate set.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from windagent_tools.google_flow.job_record import FlowJobRecord
from windagent_tools.google_flow.video_inspection import (
    VideoInspection,
    VideoInspectionError,
    VideoInspectionPolicy,
    VideoInspectorPort,
)
from windagent_tools.media_assets.security import classify_payload
from windagent_tools.media_assets.store import ContentAddressedStore

VIDEO_MIME_PREFIXES = ("video/",)


class VideoCandidateError(RuntimeError):
    """Base error for video candidate acquisition."""


class VideoCandidateInvalidError(VideoCandidateError):
    """Candidate failed validation; it was never published (§23.3)."""


class VideoCandidateFetchError(VideoCandidateError):
    """Candidate bytes could not be fetched (offline port)."""


@runtime_checkable
class VideoFetcherPort(Protocol):
    """Fetches candidate bytes from a stable URI (fake in tests/offline).

    Mirrors `CandidateFetcherPort` from the image pipeline; the real
    implementation runs through the SSRF-safe downloader in a later wiring
    phase.
    """

    async def fetch(self, uri: str) -> bytes:
        """Return raw candidate bytes for the URI."""
        ...


@dataclass(frozen=True)
class VideoCandidateAcquisition:
    """One acquired video candidate, linked to its job and request."""

    candidate_id: str  # stable identity within the job (§23.3)
    job_id: str
    index: int
    uri: str
    content_hash: str
    mime: str
    size_bytes: int
    published: bool  # True → present in the canonical content-addressed store
    inspection: VideoInspection
    quarantine_path: str = ""


class VideoCandidateDownloader:
    """Download → quarantine → inspect → validate → atomic publish (§23.3)."""

    def __init__(
        self,
        *,
        quarantine_dir: str,
        store: ContentAddressedStore,
        inspector: VideoInspectorPort,
        policy: Optional[VideoInspectionPolicy] = None,
        clock: Optional[callable] = None,
    ) -> None:
        self._quarantine_dir = Path(quarantine_dir).resolve()
        self._quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._store = store
        self._inspector = inspector
        self._policy = policy or VideoInspectionPolicy()
        self._clock = clock or time.time

    # ------------------------------------------------------------------
    async def acquire(
        self,
        *,
        job: FlowJobRecord,
        candidate_id: str,
        uri: str,
        index: int,
        fetcher: VideoFetcherPort,
    ) -> VideoCandidateAcquisition:
        """Acquire one candidate; raises `VideoCandidateInvalidError` on
        failure. Nothing is published unless every check passes (§23.3)."""
        try:
            data = await fetcher.fetch(uri)
        except Exception as exc:  # noqa: BLE001 - fetch failures are typed
            raise VideoCandidateFetchError(
                f"candidate {candidate_id} fetch failed: {exc}"
            ) from exc

        # quarantine BEFORE validation (plan 02 §21.2 order)
        job_dir = self._quarantine_dir / job.generation_id
        job_dir.mkdir(parents=True, exist_ok=True)
        quarantine_file = job_dir / f"{candidate_id}.bin"
        quarantine_file.write_bytes(data)

        try:
            receipt = self._acquire_validate(job, candidate_id, uri, index, data)
        except VideoCandidateInvalidError:
            raise
        except VideoInspectionError as exc:
            raise VideoCandidateInvalidError(
                f"candidate {candidate_id} technical validation failed: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - policy/sniff failures typed
            raise VideoCandidateInvalidError(
                f"candidate {candidate_id} failed validation: {exc}"
            ) from exc

        return VideoCandidateAcquisition(
            candidate_id=candidate_id,
            job_id=job.generation_id,
            index=index,
            uri=uri,
            content_hash=receipt["content_hash"],
            mime=receipt["mime"],
            size_bytes=receipt["size_bytes"],
            published=True,
            inspection=receipt["inspection"],
            quarantine_path=str(quarantine_file),
        )

    # ------------------------------------------------------------------
    def _acquire_validate(
        self,
        job: FlowJobRecord,
        candidate_id: str,
        uri: str,
        index: int,
        data: bytes,
    ) -> dict:
        """Ordered validation: sniff/classify → inspect → policy → publish."""
        fingerprint = classify_payload(data)
        if fingerprint.is_zero_byte:
            raise VideoCandidateInvalidError("zero-byte candidate rejected")
        if fingerprint.is_executable:
            raise VideoCandidateInvalidError("executable payload rejected")
        if fingerprint.is_archive:
            raise VideoCandidateInvalidError("archive payload rejected")
        if fingerprint.is_svg:
            raise VideoCandidateInvalidError("SVG payload rejected")
        if fingerprint.looks_polyglot:
            raise VideoCandidateInvalidError("polyglot payload rejected")

        mime = fingerprint.sniffed_mime or "application/octet-stream"
        if not mime.startswith(VIDEO_MIME_PREFIXES):
            # sniff_mime only knows image signatures; fall back to the
            # inspector when the payload is not a known image/exec/archive.
            if mime.startswith("image/"):
                raise VideoCandidateInvalidError(
                    f"candidate is an image ({mime}), expected video"
                )
            if mime != "application/octet-stream":
                raise VideoCandidateInvalidError(
                    f"candidate MIME {mime!r} is not video"
                )

        inspection = self._inspector.inspect(data)
        violations = self._policy.violations(inspection)
        if violations:
            raise VideoCandidateInvalidError(
                "candidate failed video policy: " + "; ".join(violations)
            )

        content_hash = ContentAddressedStore.content_hash(data)
        self._store.publish(data)
        return {
            "content_hash": content_hash,
            "mime": mime,
            "size_bytes": len(data),
            "inspection": inspection,
        }

    # ------------------------------------------------------------------
    def quarantine_files(self, generation_id: str) -> list[str]:
        job_dir = self._quarantine_dir / generation_id
        if not job_dir.is_dir():
            return []
        return sorted(p.name for p in job_dir.iterdir() if p.is_file())


__all__ = [
    "VideoCandidateAcquisition",
    "VideoCandidateDownloader",
    "VideoCandidateError",
    "VideoCandidateFetchError",
    "VideoCandidateInvalidError",
    "VideoFetcherPort",
]
