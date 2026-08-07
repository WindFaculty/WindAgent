# Stage F — Scene Construction

## 1. Kết quả cần đạt

Production IR, approved assets, Director plan, shot graph và continuity ledger được compile thành `BlenderScenePlan` typed; trusted compiler mới chuyển plan sang `bpy`. Stage kết thúc khi scene nhiều object có thể build lại deterministic và vượt spatial validation mà không chạy Python do LLM tạo tùy ý.

## 2. Điều kiện đầu vào

- Stages B–D đã verified cho runtime, asset bundle và character master.
- Director/shot graph/continuity hiện có vẫn tạo ID và constraints ổn định.
- Production IR schema khóa coordinate/unit semantics.
- Blender execution tắt auto-run embedded scripts và chỉ chạy script allowlisted theo hash.

## 3. Phase 11 — Scene Compiler

### Package mục tiêu

```text
intelligence/windagent_intelligence/video/scene_planner/
core/windagent_core/domain/video_production/scene/
tools/windagent_tools/production_engines/blender/compiler/
```

### Contract

`SceneCompilerPort.compile(ir, assets, shot_graph, continuity) -> EngineScenePlan`. `BlenderScenePlan` là adapter DTO derived từ plan trung lập; mọi object/track tham chiếu canonical ID và asset revision hash.

### Backlog

1. Định nghĩa typed collections, objects, transforms, character/prop/environment instances, camera/light/animation bindings, frame ranges và render profile.
2. Validate completeness trước compile: asset approval, revision match, frame range, transform units và dependency availability.
3. Sinh plan deterministically: stable ordering, canonical float/JSON representation, compiler version và plan hash.
4. Compiler `bpy` chỉ dùng operation allowlist; không eval/exec text từ model hoặc asset metadata.
5. Save `.blend` bằng temp → reopen/inspect → publish. Inspector đối chiếu object names/IDs, frame range và data-block counts với plan.
6. Ghi mapping IR entity → Blender data-block vào manifest để review/retry/manual override có thể truy vết.
7. Incremental compile theo scene/shot; input hash không đổi thì reuse `.blend`, thay đổi track chỉ rebuild phần phụ thuộc.

Gate nội bộ: `VP3D_P11_SCENE_COMPILER_VERIFIED`.

## 4. Phase 12 — Environment & Set Dressing

### Components

```text
EnvironmentBuilder
SetDressingPlanner
PropPlacementPlanner
SpatialConstraintValidator
```

### Backlog

1. Định nghĩa floor/support surfaces, navigation zones, forbidden volumes, attachment points và interaction anchors.
2. Environment builder resolve asset đã approved hoặc procedural plan đã allowlist; không download trong compile step.
3. Prop placement dùng semantic anchors và constraint solver; random scatter phải có seed/version.
4. Character placement kiểm foot contact, clearance, facing target và reachability với interaction prop.
5. Camera/light placement được giữ như placeholder typed để Stage G compile chi tiết.
6. Spatial validator kiểm mesh penetration, floating object, out-of-bounds, camera-inside-mesh và blocking occluder.
7. Geometry Nodes/procedural assets phải pin node-group hash và không chứa external script không approved.
8. Tạo low-cost preview render/contact sheet để human/automated reviewer duyệt trước animation/render tốn kém.

Gate nội bộ: `VP3D_P12_SET_DRESSING_VERIFIED`.

## 5. Test matrix

- Empty/minimal scene, nhiều character, duplicate ID và missing approved asset.
- Table xuyên tường, character dưới sàn, chair sai chiều, camera trong mesh và prop ngoài reach.
- Cùng seed/input tạo cùng scene plan/hash và equivalent `.blend` manifest.
- Đổi một prop chỉ invalidates scene/shot phụ thuộc.
- Malicious text trong description không trở thành Python/code execution.
- Save/reopen giữ mapping ID, units, transforms và frame range.

## 6. Evidence và bàn giao

Mỗi fixture lưu IR hash, scene plan, compiler version, `.blend` hash, inspection manifest, spatial findings, preview hashes và invalidation receipt. Stage F bàn giao typed scene/collision anchors cho camera, animation, facial và renderer; không bàn giao một `.blend` không có source manifest.

## 7. Rủi ro

- Blender data-block naming không ổn định nếu dựa vào display name; dùng canonical ID/custom property.
- Collision mesh chi tiết làm compile chậm; dùng proxy bounds trước, exact check chỉ cho interaction quan trọng.
- Geometry Nodes phiên bản khác nhau gây drift; pin Blender LTS và node-group artifact hash.
