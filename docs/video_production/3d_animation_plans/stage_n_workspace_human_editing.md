# Stage N — Workspace / Human Editing

## 1. Kết quả cần đạt

Người dùng có thể mở và sửa `.blend` dẫn xuất mà không phá authority của Production IR, đồng thời quản lý/reuse library asset qua nhiều episode. Mọi manual edit có manifest, scope và invalidation rõ; regeneration không được âm thầm ghi đè.

## 2. Điều kiện đầu vào

- Phase 25 golden scene đã pass để workspace thao tác trên pipeline thật.
- Scene compiler ghi mapping IR entity ↔ Blender data-block.
- Artifact storage hỗ trợ revision, lock, derived lineage và approval.
- Web/Desktop dùng API/event runtime hiện có, không tạo backend riêng.

## 3. Phase 31 — Blender Manual Override

### Model

```text
ManualOverrideManifest
ManualOverrideEntry
OverrideScope
OverrideConflict
OverrideApproval
```

Scope tối thiểu: camera, light, transform, material, character pose, animation curve và scene object. Entry ghi base IR/scene hash, Blender version, affected entity/data-block, before/after fingerprint, author, time, reason và lock state.

### Backlog

1. Export editable `.blend` kèm manifest/mapping và hướng dẫn không đổi canonical IDs.
2. Khi import lại, inspector diff against base derived artifact; unknown/new script/add-on/data-block bị quarantine.
3. Phân loại `SAFE_OVERRIDE`, `CONFLICT`, `UNSUPPORTED`, `SECURITY_BLOCKED`.
4. User chọn pin override, convert thành IR revision hoặc discard; hệ thống không tự chọn với conflict.
5. Scene compiler kiểm override manifest trước regenerate và báo chính xác entry sẽ bị invalidated.
6. UI hiển thị base/current hash, affected shots, downstream render cost và approval state.
7. Audit mọi open/export/import/approve/reject; không cần theo dõi thao tác bên trong Blender theo thời gian thực ở bản đầu.

Gate nội bộ: `VP3D_P31_MANUAL_OVERRIDE_VERIFIED`.

## 4. Phase 32 — Asset Library & Episode Reuse

### Library taxonomy

```text
characters, environments, props, animations, voices,
materials, lighting, camera_rigs, facial_profiles
```

### Backlog

1. Metadata/index theo stable ID, semantic tags, style fingerprint, compatibility, license, approval và revision.
2. Search/resolve trả exact revision và compatibility reasons; không chỉ fuzzy match.
3. Reuse policy ưu tiên approved asset, nhưng chặn reuse khi style/license/rig/engine profile không phù hợp.
4. Episode pin asset revisions; library update không mutate episode cũ.
5. Dependency graph cho biết asset được dùng ở project/episode/shot nào trước retire/delete.
6. Preview/contact sheet và quality history giúp human chọn revision.
7. Đo reuse rate, avoided generation/normalization time, cache size và hit/miss reasons.
8. Retention/archive/delete tôn trọng license, audit và derived artifact dependencies.

Gate nội bộ: `VP3D_P32_EPISODE_REUSE_VERIFIED`.

## 5. UI và API tối thiểu

- Scene/shot inspector với derived `.blend`, hashes và compile status.
- Override diff/conflict/approval view.
- Asset library browser, preview, compatibility và provenance panel.
- Dependency/usage view trước retire.
- Rebuild impact preview và explicit confirmation.
- Realtime job/review state dùng event stream hiện tại.

## 6. Test matrix và evidence

- Camera/light/pose edit round-trip; unsupported topology/script change bị quarantine.
- Regenerate khi có pinned override không overwrite.
- Base hash mismatch tạo conflict, không auto-merge.
- Hai episode pin cùng master; update library không đổi episode cũ.
- Asset hết quyền sử dụng bị chặn cho episode mới nhưng historical artifact vẫn audit được.
- UI/API không cho client tự đánh dấu approved hoặc sửa hash.

Evidence gồm override diff fixtures, approval receipts, regeneration conflict tests, library reuse matrix, dependency report và UI/API integration receipts.

## 7. Rủi ro

- Diff `.blend` không ổn định ở byte level; so semantic manifest/data-block fingerprints, không chỉ file hash.
- Manual edit có thể tạo dependency ẩn; inspector cần conservative conflict khi không hiểu thay đổi.
- Library tăng nhanh; dedupe theo content hash nhưng vẫn giữ metadata/provenance của từng source.
