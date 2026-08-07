# Flow Candidate Acquisition Contract (Phase 14)

**Gate:** `VP14_FLOW_IMAGE_GENERATION_VERIFIED`
**Plan:** [04_phase_12_16_flow_browser_provider.md](../plans/04_phase_12_16_flow_browser_provider.md) §18.3
**Location:** `tools/windagent_tools/google_flow/candidate_downloader.py`

## 1. Purpose

`CandidateDownloader` acquires every candidate of a completed job (plan 04
§18.3). It reuses the existing `AssetValidationService` ordered validation
pipeline and `ContentAddressedStore` atomic publish — no parallel validation
is introduced.

## 2. Pipeline per candidate (plan 04 §18.3)

```text
stable identity within the job (candidate_id)
    → download into quarantine (CandidateFetcherPort)
    → size limit
    → MIME sniff (magic bytes — extension is never evidence)
    → polyglot / executable / archive / zero-byte rejection
    → decoder + pixel-limit validation
    → EXIF sanitization
    → content hash over the sanitized payload
    → atomic publish into the content-addressed store
    → link request hash + Flow project/job (job.generation_id, candidate_id)
```

## 3. Ports

```python
class CandidateFetcherPort(Protocol):
    async def fetch(self, uri: str) -> bytes: ...
```

The fetcher is injected: tests use a deterministic fake; the real wiring runs
through the SSRF-safe downloader in a later phase. The downloader itself
never performs network I/O.

## 4. Fail-closed rules

- `CandidateInvalidError` for zero-byte, wrong MIME, polyglot, corrupt,
  oversized or unapproved payloads — **nothing is published** and the store
  stays clean.
- A failed candidate is quarantined (for debugging) but never enters the
  canonical store.
- The generator iterates **all** candidate markers — it never defaults to
  the first candidate (§18.3).

## 5. Acquisition record

```python
CandidateAcquisition(
    candidate_id, job_id, index, uri,
    content_hash, mime, width, height, size_bytes,
    published, quarantine_path,
)
```
