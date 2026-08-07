# Stage D — Character System

## 1. Kết quả cần đạt

WindAgent quản lý một `CharacterMaster` versioned để duy trì mesh, skeleton, facial rig, material, tỷ lệ, voice và animation compatibility xuyên suốt shot/episode. Nhân vật không được regenerate theo từng shot.

## 2. Điều kiện đầu vào

- Asset gateway và normalization bundle của Stage C đã verified.
- Production IR dùng `CharacterMasterId`/`CharacterInstance`, không dùng display name làm khóa.
- Blender runtime có thể import asset và render preview deterministic.
- Có policy riêng cho likeness, voice rights và asset licensing.

## 3. Phase 8 — Character Master Asset

### Domain và storage

Tạo model immutable:

```text
CharacterMaster
CharacterMasterRevision
CharacterGeometryProfile
CharacterMaterialProfile
CharacterProportionProfile
FacialRigProfile
AnimationProfile
StyleFingerprint
```

`CharacterInstance` trong scene chỉ tham chiếu master revision và override được cho phép như costume/pose; không sao chép hoặc âm thầm mutate master.

### Backlog

1. Chuyển `CharacterBible` hiện có thành input sáng tạo; mapping rõ sang master asset đã duyệt.
2. Định nghĩa lifecycle `DRAFT → NORMALIZED → RIGGED → VALIDATED → APPROVED → RETIRED`.
3. Lưu canonical mesh, skeleton, facial rig, materials/textures, proportions, voice profile, style fingerprint và approved animation sets.
4. Tạo preview suite: turntable, neutral pose, silhouette, material check và face close-up.
5. So sánh revision mới với revision đã duyệt: topology, skeleton names, proportions, palette và facial controls.
6. Asset reuse lookup theo `CharacterMasterId`, style/compatibility và approval state; generation chỉ xảy ra khi không có compatible master hoặc user yêu cầu revision mới.
7. Thay master revision chỉ invalidate scene/shot phụ thuộc; episode đã khóa tiếp tục pin revision cũ.

## 4. Phase 9 — Rigging & Retargeting

### Model

```text
SkeletonProfile
RigProfile
RetargetProfile
AnimationCompatibilityProfile
RigValidationReceipt
```

### Backlog

1. Detect skeleton/bone hierarchy và chuẩn hóa semantic bone map; không phụ thuộc tên bone của một provider.
2. Validate rest pose, scale, root bone, parenting, weights, joint limits và facial controls.
3. Xây retarget mapping versioned giữa source animation skeleton và target character skeleton.
4. Chạy animation suite: idle, walk, run, sit, stand, turn, point, grab, talk và facial neutral.
5. Đo foot sliding, limb stretch, mesh penetration, root drift và pose discontinuity.
6. Tạo compatibility verdict theo clip/profile; clip fail không được đưa vào library approved.
7. Hỗ trợ manual correction dưới dạng derived rig revision có manifest, không sửa file nguồn không dấu vết.

### Gate

`VP3D_P9_CHARACTER_RIG_VERIFIED` yêu cầu ít nhất hai character master khác topology retarget cùng bộ clip tối thiểu, qua preview render và continuity check.

## 5. Kiểm thử và evidence

- Stable ID qua đổi tên nhân vật.
- Hai episode pin cùng master revision cho kết quả identity ổn định.
- Revision mới không làm artifact episode cũ thay đổi.
- Bone thiếu, weight lỗi, scale sai, facial rig không tương thích và asset chưa approved đều fail-closed.
- Retarget chạy lại cùng input tạo cùng action manifest/hash trong cùng Blender profile.
- Voice profile liên kết bằng ID và rights state, không lộ secret/provider credential.

Evidence bổ sung gồm `character_master_manifest.json`, `rig_profile.json`, `retarget_matrix.json`, preview hashes, validation metrics và approval receipt.

## 6. Rủi ro

- Auto-rig có thể cho kết quả nhìn được nhưng không production-ready; gate dựa trên deformation metrics và visual review, không chỉ import thành công.
- Facial topology thay đổi làm lip-sync mapping mất hiệu lực; thay đổi này phải invalidate facial profile.
- Reuse sai style có thể giữ identity nhưng phá art direction; style fingerprint và human approval là bắt buộc.
