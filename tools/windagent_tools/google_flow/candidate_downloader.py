"""
Phase 14 — Candidate acquisition (plan 04 §18.3).

For every candidate in a job:

    stable identity within the job
        → download into quarantine
        → hash / MIME / decode / dimension validation
        → save screenshot/result metadata
        → publish into the canonical content-addressed store ATOMICALLY
        → link request hash + Flow project/job

Reuses the existing `AssetValidationService` (ordered validation pipeline:
size → MIME sniff → polyglot/exec/archive rejection → decoder + pixel limit →
EXIF sanitization) and `ContentAddressedStore` (atomic publish, no partial
artifact). A failed or invalid candidate is NEVER published and is surfaced
as `CandidateInvalidError` — the generator never defaults to the first
candidate (§18.3).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from windagent_tools.google_flow.job_record import FlowJobRecord
from windagent_tools.media_assets.errors import MediaValidationError
from windagent_tools.media_assets.store import ContentAddressedStore
from windagent_tools.media_assets.validation import AssetValidationService


class CandidateError(RuntimeError):
    """Base error for candidate acquisition."""


class CandidateInvalidError(CandidateError):
    """Candidate failed validation; it was never published (§18.3)."""


class CandidateFetchError(CandidateError):
    """Candidate bytes could not be fetched (offline port)."""


@runtime_checkable
class CandidateFetcherPort(Protocol):
    """Fetches candidate bytes from a stable URI (fake in tests/offline).

    The real implementation runs through the SSRF-safe downloader
    (`windagent_tools.media_assets.security`) in a later wiring phase; tests
    inject a deterministic fake.
    """

    async def fetch(self, uri: str) -> bytes:
        """Return raw candidate bytes for the URI."""
        ...


@dataclass(frozen=True)
class CandidateAcquisition:
    """One acquired candidate, linked to its job and request."""

    candidate_id: str  # stable identity within the job (§18.3)
    job_id: str
    index: int
    uri: str
    content_hash: str
    mime: str
    width: Optional[int]
    height: Optional[int]
    size_bytes: int
    published: bool  # True → present in the canonical content-addressed store
    quarantine_path: str = ""


class CandidateDownloader:
    """Download → quarantine → validate → atomic publish (§18.3)."""

    def __init__(
        self,
        *,
        quarantine_dir: str,
        store: ContentAddressedStore,
        validator: Optional[AssetValidationService] = None,
        clock: Optional[callable] = None,
    ) -> None:
        self._quarantine_dir = Path(quarantine_dir).resolve()
        self._quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._store = store
        self._validator = validator or AssetValidationService(store)
        self._clock = clock or time.time

    # ------------------------------------------------------------------
    async def acquire(
        self,
        *,
        job: FlowJobRecord,
        candidate_id: str,
        uri: str,
        index: int,
        fetcher: CandidateFetcherPort,
        extension: str = "",
    ) -> CandidateAcquisition:
        """Acquire one candidate; raises `CandidateInvalidError` on failure.

        Nothing is published unless the full ordered validation passes.
        """
        try:
            data = await fetcher.fetch(uri)
        except Exception as exc:  # noqa: BLE001 - fetch failures are typed
            raise CandidateFetchError(
                f"candidate {candidate_id} fetch failed: {exc}"
            ) from exc

        # quarantine BEFORE validation (plan 02 §21.2 order)
        job_dir = self._quarantine_dir / job.generation_id
        job_dir.mkdir(parents=True, exist_ok=True)
        quarantine_file = job_dir / f"{candidate_id}.bin"
        quarantine_file.write_bytes(data)

        try:
            receipt = self._validator.validate(data, extension=extension)
        except MediaValidationError as exc:
            raise CandidateInvalidError(
                f"candidate {candidate_id} failed validation: {exc}"
            ) from exc

        return CandidateAcquisition(
            candidate_id=candidate_id,
            job_id=job.generation_id,
            index=index,
            uri=uri,
            content_hash=receipt.content_hash,
            mime=receipt.sniffed_mime,
            width=receipt.width,
            height=receipt.height,
            size_bytes=receipt.size_bytes,
            published=True,
            quarantine_path=str(quarantine_file),
        )

    # ------------------------------------------------------------------
    def quarantine_files(self, generation_id: str) -> list[str]:
        job_dir = self._quarantine_dir / generation_id
        if not job_dir.is_dir():
            return []
        return sorted(p.name for p in job_dir.iterdir() if p.is_file())


__all__ = [
    "CandidateAcquisition",
    "CandidateDownloader",
    "CandidateError",
    "CandidateFetchError",
    "CandidateFetcherPort",
    "CandidateInvalidError",
]
