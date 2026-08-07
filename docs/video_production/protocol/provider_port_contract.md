# Provider Port Contract — Video Production Protocol

Source: `core/windagent_core/contracts/video_production/`

Ports are implementation-independent `Protocol` classes. They contain **no**
provider implementation details: no selectors, cookies, browser session
objects, or engine SDK calls. Those belong in the provider adapter layer
(`providers/`, engine adapters).

## Ports

| Port | Responsibility |
|---|---|
| `PreproductionPort` | Project creation, screenplay generation, cinematic planning, character/location extraction |
| `VideoDirectionPort` | Cinematic plan creation and shot-plan locking from an immutable package |
| `MediaGenerationProviderPort` | Image/video generation, video extension, job inspection, result download |
| `AssetStoragePort` | Content-addressed asset storage keyed by hash |
| `QualityReviewPort` | Multi-dimensional candidate review |

## MediaGenerationProviderPort semantics

```python
@runtime_checkable
class MediaGenerationProviderPort(Protocol):
    async def generate_image(request) -> GenerationCandidate
    async def generate_video(request) -> GenerationCandidate
    async def extend_video(request, source_asset_id, extension_seconds) -> GenerationCandidate
    async def inspect_job(request) -> GenerationCandidate
    async def download_result(request) -> ReferenceAsset
```

- Requests carry `request_hash`, `prompt_version`, `reference_hashes`,
  `provider`, and `parameters` so every candidate is traceable.
- Job inspection and download are keyed by the request, never by browser
  coordinates or selectors.

## Fake conformance

A fake provider implements the same async method names and is runtime-checkable:

```python
assert isinstance(fake, MediaGenerationProviderPort)  # True
```

## Provenance requirements

- Assets always carry a content hash.
- Internet-sourced assets carry an `AssetAcquisitionRecord`
  (`source_type`, `source_url`, `license_state`, `acquired_at`).
- Generated candidates trace back to request hash, prompt version, reference
  hashes, provider, and parameters.

## Ports and the Director

The Director consumes an immutable `VideoProductionPackage` and returns a
`CinematicPlan`. It never mutates the locked screenplay and never submits
generations itself (road_map.md Phase 8).
