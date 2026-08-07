# Stage H — Animation

## 1. Kết quả cần đạt

Animation được xây theo ba lớp tăng dần độ phức tạp: clip library/mocap, procedural correction và cuối cùng AI motion. Mọi output đều trở thành `AnimationTrack` versioned, qua retarget/validation trước khi Scene Compiler sử dụng.

## 2. Điều kiện đầu vào

- Character rig/retarget profile Stage D đã verified.
- Scene anchors, navigation zones và interaction points Stage F đã sẵn sàng.
- Shot frame ranges/camera timing Stage G đã khóa revision.
- Audio alignment Stage E có thể cung cấp timing, nhưng animation body cơ bản không phải chờ toàn bộ audio.

## 3. Phase 15 — Animation Layer V1: Library + Mocap

### Backlog

1. Tạo `AnimationIntent`, `AnimationClip`, `AnimationTrack`, `ClipCompatibility` và clip provenance/hash.
2. Xây library tối thiểu: idle, walk, run, jump, sit, stand, talk, laugh, cry, point, wave, pick-up và put-down.
3. Resolve intent theo actor/action/emotion/destination/duration và compatible skeleton; không lookup bằng display name.
4. Retarget clip qua profile Stage D; root motion, fps và units được normalize.
5. Time-warp trong bounded range; ngoài range phải chọn clip khác hoặc yêu cầu plan revision.
6. Blend transition giữa clips và giữ stable frame boundaries.
7. Pin clip revision theo episode để library update không làm thay đổi production đã khóa.

Gate nội bộ: `VP3D_P15_ANIMATION_LIBRARY_VERIFIED`.

## 4. Phase 16 — Procedural Animation

### Backlog

1. Tạo procedural layers cho look-at, head/eye tracking, hand/foot IK, path following, object grab, sitting alignment, turning và idle variation.
2. Mỗi layer khai input constraints, priority và affected bones; không ghi đè keyframe ngoài ownership.
3. Dùng deterministic seed cho variation và path sampling.
4. Validate foot contact/sliding, hand reach, joint limit, collision, balance và transition continuity.
5. Bake derived action cho render; lưu recipe + compiler version để có thể rebuild.
6. Repair chỉ layer lỗi, không bake lại toàn scene nếu input khác không đổi.

Gate nội bộ: `VP3D_P16_PROCEDURAL_ANIMATION_VERIFIED`.

## 5. Phase 17 — AI Motion Adapter

### Contract và pipeline

```text
TextToMotionPort / VideoToMotionPort / MotionGenerationPort
→ raw motion artifact
→ skeleton remap
→ joint/foot/collision validation
→ retarget
→ approved AnimationTrack
```

### Backlog

1. Capability contract cho skeleton, fps, duration, seed, license và output format.
2. Request hash, provider/model/version, prompt hash, seed và cost/provenance cho mọi generation.
3. Quarantine raw output; không import trực tiếp vào production scene.
4. Dùng cùng validation metrics với library/mocap để so sánh công bằng.
5. Fallback hợp lệ là library/procedural hoặc human review, không bypass validation.
6. Retry theo nguyên nhân và budget; output khác seed là candidate mới, không overwrite.

Gate `VP3D_P17_AI_MOTION_VERIFIED` chỉ pass khi một AI/fake adapter output đi qua full safety/retarget/quality chain và không có direct-to-scene path.

## 6. Test matrix

- Clip missing/incompatible, fps/scale sai, duration mismatch và root drift.
- Walk-to-target với obstacle, sit/grab với anchor sai, hand/foot IK collision.
- Hai animation trên actor cùng frame range phải resolve ownership/conflict rõ.
- Restart giữa bake/review không publish partial action.
- Thay facial/audio track không invalidate body clip nếu timing không đổi.
- Malicious metadata trong AI motion không được thực thi.

## 7. Evidence và rủi ro

Evidence gồm clip manifest, retarget receipt, procedural recipe, motion metrics, preview hashes, invalidation report và provider provenance.

Rủi ro lớn nhất là uncanny motion dù metric kỹ thuật pass; Stage K cần visual reviewer và human threshold. AI motion licensing cũng phải được xử lý như asset provenance Stage C.
