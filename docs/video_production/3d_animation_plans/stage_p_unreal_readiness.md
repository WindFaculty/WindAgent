# Stage P — Chuẩn bị Unreal

## 1. Kết quả cần đạt

Chứng minh domain và asset library không phụ thuộc Blender: scene, character, camera, animation, facial, light và render intent có thể export qua contract engine-neutral; USD/glTF/FBX round-trip giữ đúng semantics cần thiết cho Blender và Unreal.

## 2. Điều kiện đầu vào

- Production IR Stage A đã ổn định qua ít nhất golden/multi-minute production.
- Reproducibility manifest Stage O đã pin compiler/tool/version lineage.
- Asset/character/animation library có normalized interchange artifacts.
- Manual override đã được phân loại: phần nào nâng lên IR, phần nào Blender-only.

## 3. Phase 36 — Engine-neutral Export Layer

### Backlog kiến trúc

1. Audit mọi domain/contract/schema/event để tìm `bpy`, Blender data-block, Cycles enum, path `.blend` hoặc Blender-specific coordinate assumptions.
2. Blender-specific types chỉ được phép trong `tools/windagent_tools/production_engines/blender/` và derived artifact metadata.
3. Chuẩn hóa `EngineScenePackage` gồm scene graph, instances, tracks, light/render intents, interchange asset URIs, hashes và extension blocks.
4. Định nghĩa capability negotiation: feature required/optional, unsupported behavior và degradation cần approval.
5. Tách generic engine job lifecycle/cancel/retry/receipt khỏi Blender execution details.
6. Thêm fake second engine adapter trong contract tests để chứng minh port không ngầm yêu cầu Blender.
7. Gắn semantic validation: coordinate system, units, frame/time base, material, skeleton, camera/lens và lighting intent.

Gate nội bộ: `VP3D_P36_ENGINE_NEUTRAL_EXPORT_VERIFIED`.

## 4. Phase 37 — USD/glTF Interchange

### Vai trò format

- glTF: asset interchange ưu tiên cho mesh/material/scene subset.
- FBX: compatibility cho skeletal mesh/animation khi pipeline yêu cầu.
- USD: scene/variant/animation hướng dài hạn giữa engines.
- JSON/Pydantic: source metadata và Production IR; các format 3D không thay thế authority này.

### Backlog

1. Lập capability matrix theo format cho mesh, PBR material, textures, skeleton, morph targets, animation, camera, lights, variants và custom metadata.
2. Tạo exporter/importer adapters versioned; mỗi conversion có source/output hashes và loss report.
3. Round-trip fixture `IR → Blender → interchange → inspect` và độc lập `IR → interchange → inspect` khi có thể.
4. Validate units/axis/handedness, transforms, bone hierarchy, animation timing, material/texture binding và camera lens.
5. Unsupported/lossy field phải nằm trong explicit extension/degradation report; không drop silent.
6. Asset library lưu canonical interchange bundle để không phải migrate toàn bộ khi Unreal xuất hiện.

Gate nội bộ: `VP3D_P37_INTERCHANGE_VERIFIED`.

## 5. Test matrix và evidence

- Static/skinned mesh, morph target, multi-material, texture color space, animation clip, camera track và light intent.
- Nested transforms, negative scale, unit/axis conversion và Unicode IDs.
- Round-trip semantic tolerance và deterministic manifest.
- Feature unsupported tạo `BLOCKED` hoặc approved degradation, không success giả.
- Không importer nào thực thi embedded script/add-on.

Evidence gồm Blender leak audit, engine capability schema, fake-adapter contract receipt, format capability/loss matrix, round-trip manifests và preview comparisons.

## 6. Rủi ro

- Không một format nào giữ mọi semantics Blender/Unreal; Production IR + explicit extensions vẫn là authority.
- USD support khác nhau theo engine/version; pin versions và contract test thay vì tin tên format.
- Material/facial rig thường lossy nhất; cần golden asset fixtures trước Stage Q.
