# ADR-FE-003: Semantic Boundaries for File vs Artifact vs Asset

- **Status**: ACCEPTED
- **Date**: 2026-08-14
- **Phase**: Phase 1 (Canonical Domain Vocabulary)
- **Deciders**: Architecture Council, Storage & Asset Team

---

## Context and Problem Statement
The terms "File", "Artifact", and "Asset" have often been conflated in `v2_files.py`, `v2_artifacts.py`, and `v2_assets.py`. A screenplay JSON file could simultaneously be treated as a generic uploaded file, a step artifact, or an approved asset.

## Decision
We enforce three unambiguous semantic categories:

1. **`File` (`file_*`)**:
   - **Semantic**: A raw filesystem or workspace byte stream without formal pipeline schema guarantees.
   - **Examples**: User uploaded `.txt` notes, raw reference `.pdf`, logs, scratch scripts.
   - **Lifecycle**: Mutable, workspace-scoped, may be deleted or modified freely.

2. **`Artifact` (`art_*`)**:
   - **Semantic**: An immutable, structured output produced by a specific pipeline step or agent task.
   - **Examples**: Screenplay JSON, Scene Beat Sheet, Story Bible JSON, Audio Stem, Video Render Chunk.
   - **Lifecycle**: Immutable, cryptographically hash-addressed or deterministic version-stamped, linked directly to a `Run` or `Task`.

3. **`Asset` (`ast_*`)**:
   - **Semantic**: A curated, approved, versioned production entity that can be cataloged, reviewed, and reused across projects.
   - **Examples**: Approved Character 3D Mesh, Voice Model Preset, Master Color Grading LUT, Certified Production Video.
   - **Lifecycle**: Curated, review-gated, tagged with metadata and licensing.

## Matrix Comparison
| Attribute | File | Artifact | Asset |
|---|---|---|---|
| Mutability | Mutable | **Immutable** | Versioned / Supervised |
| Schema Enforcement | None (Binary/Raw) | Strict (JSON Schema) | High (Metadata + Content) |
| Producer | User / System | Pipeline / Agent Run | Human Review / Approval |
| Reusability | Local | Run-specific | Global / Multi-Project |
| ID Prefix | `file_` | `art_` | `ast_` |

## Consequences
- **Positive**: Eliminates confusion in UI tabs (`Files` vs `Asset Library` vs `Artifact Inspector`).
- **Enforcement**: Artifacts cannot be edited in-place; changes generate new Artifacts or Revisions.
