# Asset Normalization Profile (VP3D Phase 7, Stage C)

Mọi asset 3D phải đi qua `AssetNormalizerPort` trước khi Scene Compiler tiêu thụ.
Pipeline canonical:

```text
ingest -> security -> parse -> unit/axis -> mesh -> material/texture
-> poly/VRAM budget -> LOD -> preview render -> approval/cache
```

## 1. Canonical metadata

| Trường | Canonical | Ghi chú |
|---|---|---|
| Unit | `METERS` | Adapter chuyển đổi trục thực tế (CM→0.01, FT→0.3048, IN→0.0254) |
| Up axis | `Z_UP` | Y-up/X-up phải được convert ở adapter/Blender job |
| Color space | `sRGB` / `Linear` / `Raw` | Texture mang metadata color-space |
| LOD | derived artifact | Source không bao giờ bị overwrite; mỗi LOD có hash + quality metrics |

`CanonicalMetadata` (domain): `unit=METERS, up_axis=Z_UP`, `scale_factor` được derive
từ `detected_unit` (fail closed: UNKNOWN ⇒ meters, không rescale ngầm).

## 2. Mesh validation (fail closed)

- Non-manifold edges/vertices (host-side heuristic; engine-side bmesh trong Blender job);
- Degenerate faces (diện tích ≈ 0);
- Missing UV layers, missing textures, unsupported shader extensions
  (`KHR_materials_anisotropy/specular/volume/variants` → blocking);
- Skeleton (armatures) + animation clips được report;
- `TopologyPolicy.MANIFOLD_ONLY / QUAD_DOMINANT` không thỏa → `BLOCKED`;
- 0 triangle với geometry khai báo → `BLOCKED`.

## 3. Material / texture

- PBR material được normalize; texture **content-addressed** (SHA-256), giới hạn
  resolution (`max_texture_resolution`, default 4096) và bit depth (16);
- Oversize → downscale (LANCZOS), không bao giờ upscale; `resolution_capped` + original size ghi lại;
- EXIF/metadata bị strip; color-space metadata bắt buộc;
- Texture không đọc được / URI traversal → `missing` (fail closed, không giữ ngầm).

## 4. Budget & VRAM (trước preview)

- Geometry: `vertex_count × 56 B + triangle_count × 12 B` (pos+normal+uv+tangent, index);
- Texture: `w × h × 4 × (bit_depth/8)`;
- `total > max_vram_bytes` ⇒ `BLOCKED` — **không render mù** (không OOM giữa chừng);
- Polygon > `max_polygons` ⇒ `BLOCKED`.

## 5. LOD policy

| Policy | Levels |
|---|---|
| `NONE` | LOD0 (source) |
| `SINGLE` | LOD0 + LOD1 (ratio 0.5) |
| `MULTI` | LOD0 + LOD1..N (ratios [0.5, 0.2]) |

- Decimation là engine work (Blender `Decimate` modifier, `use_collapse_triangulate`);
- CI dùng `FakeAssetJobRunner` deterministic (cùng input ⇒ cùng hash);
- Mỗi LOD: `content_hash`, `triangle_count`, `vertex_count`, `quality_score = 1-|target-actual|`, `generated_by`.

## 6. Preview profile (deterministic, Stage B)

```text
engine=CYCLES  device=CPU  samples=8  frames=12
resolution=512x288  color_management=Standard  denoise=false
```

- Turntable quanh bounding box, sun + area fill, camera orbit 360°;
- Atomic temp → validated final; cancel-safe giữa frames;
- Blender job script: `tools/.../blender/scripts/execute_asset_job.py` (pure stdlib,
  auto-execution bị tắt trước mọi import).

## 7. Immutable bundle layout

```text
bundle/b_<source_hash[:16]>/
├── manifest.json              (bundle_hash deterministic theo sorted path+sha256)
├── validation_report.json     (canonical metadata, mesh, materials, textures, vram, lods)
├── provenance.json            (source hash, source_type, license, stages)
├── asset.<ext>                (normalized interchange copy)
├── textures/<sha256>.<ext>    (content-addressed)
├── lods/lod_<N>.glb|json      (derived; LOD0 chỉ reference source hash)
└── preview/                   (thumbnail + turntable frames + preview.json)
```

## 8. Sources của pipeline

| Source | Path |
|---|---|
| Domain (DTO, enums, errors) | `core/windagent_core/domain/video_production/asset_normalization/` |
| Port | `core/windagent_core/contracts/video_production/asset_normalizer.py` |
| Host pipeline | `tools/windagent_tools/media_assets/normalization/` |
| Engine job runner (Blender) | `tools/windagent_tools/production_engines/blender/asset_pipeline.py` + `scripts/execute_asset_job.py` |
| CI fakes | `tools/windagent_tools/media_assets/normalization/fakes.py` |
| Wiring | `apps/worker/windagent_worker/composition.py::_register_asset_normalizer` (guard `WINDAGENT_ASSET_NORMALIZER=1`) |

## 9. Known limitations / deferred

- Quad-dominance analysis cần engine-side (Blender job) — host chỉ cảnh báo;
- Interchange `asset.<ext>` hiện là copy của source (normalize thực sự của geometry
  trong Blender job tạo `normalized.blend` — được copy khi chạy real engine);
- Cache idempotency của bundle theo `b_<hash>` (re-publish trả bundle cũ nguyên vẹn).
