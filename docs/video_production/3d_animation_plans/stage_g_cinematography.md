# Stage G — Cinematography

## 1. Kết quả cần đạt

Ý định đạo diễn hiện có được compile thành camera rigs và lighting rigs có thể chạy trên Blender, nhưng domain vẫn trung lập engine để map sang Unreal sau này. Camera/lighting được kiểm tra trước render, versioned và invalidated độc lập.

## 2. Điều kiện đầu vào

- Stage F cung cấp scene geometry, subject bounds, anchors và frame ranges.
- `ShotType`, `CameraMovement`, `CameraAngle`, `CameraSide`, `TransitionType` và shot graph vẫn là canonical intent.
- Character/action blocking thô đã có để tính framing, path và occlusion.

## 3. Phase 13 — Blender Camera Compiler

### Domain mở rộng

```text
CameraIntent
LensProfile
FocusPlan
FramingConstraint
CameraPath
CameraRigPlan
```

### Backlog

1. Map `STATIC`, `PAN`, `TILT`, `DOLLY`, `TRACK`, `CRANE` sang rig primitives versioned trong Blender adapter.
2. Compile lens, sensor, DOF, focus target, look-at, path/easing và safe framing từ intent; không để Director phát `bpy`.
3. Tính shot start/end frame từ duration/fps và giữ dialogue timing constraints.
4. Validate 180-degree rule, head/look room, subject visibility, camera collision, lens bounds, path continuity và motion speed.
5. Dùng scene proxy để preflight occlusion; sample nhiều frame cho moving camera/actor.
6. Tạo camera preview/playblast nhẹ và manifest đường camera để review trước Cycles.
7. Manual camera override ở Stage N phải có thể pin track revision mà compiler tôn trọng.

Gate nội bộ `VP3D_P13_CAMERA_COMPILER_VERIFIED` yêu cầu static, dialogue coverage và moving-camera fixtures.

## 4. Phase 14 — Lighting System

### Contract

Director phát `LightingIntent(mood, time_of_day, style, emphasis, continuity_key)`. Lighting compiler chọn preset/rig đã versioned, không để model tự đặt đèn không giới hạn.

### Backlog

1. Tạo preset đầu tiên: `CARTOON_DAY`, `CARTOON_NIGHT`, `INTERIOR_SOFT`, `MAGIC_FOREST`, `SUNSET`, `DRAMATIC`, `COMEDY_BRIGHT`.
2. Mỗi preset pin light types, ratios, color policy, world settings, shadow/bounce budget và exposure range.
3. Cho phép bounded adjustment theo subject/environment bounds; mọi override nằm trong `LightRig` typed.
4. Estimate contribution và resource cost; không cho light/sample/bounce vượt render policy.
5. Validate missing key light, clipped exposure, inconsistent color temperature, excessive noise risk và continuity giữa shots.
6. Render low-sample contact sheet/histogram cho reviewer; preset chỉ approved sau visual + technical checks.
7. Giữ intent trung lập để Stage Q map sang Unreal/Lumen.

Gate nội bộ: `VP3D_P14_LIGHTING_SYSTEM_VERIFIED`.

## 5. Test và evidence

- Camera movement quá ngắn, path xuyên geometry, subject ra khỏi frame và camera-side flip phải bị phát hiện.
- Dialogue coverage giữ eyeline/screen direction qua master/over-shoulder/reaction shots.
- Lighting cùng continuity key không drift ngoài tolerance giữa adjacent shots.
- Preset/seed/compiler version giống nhau tạo cùng rig manifest.
- Đổi camera không rebuild asset/rig/audio; đổi light chỉ invalidates preview/render phụ thuộc.

Evidence gồm camera intent/rig manifest, sampled-framing report, collision/occlusion findings, lighting intent/preset hash, histogram/contact sheet và compile receipts.

## 6. Rủi ro

- Occlusion chỉ kiểm ở frame đầu sẽ bỏ sót lỗi động; sampling density phải dựa trên path/action complexity.
- DOF đẹp nhưng gây mất subject focus; focus target validity là blocking check.
- Lighting preset có thể đúng kỹ thuật nhưng sai mood; human review được giữ ở confidence thấp.
