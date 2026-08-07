# Stage I — Facial Animation

## 1. Kết quả cần đạt

Dialogue audio và forced-alignment được chuyển thành `FacialAnimationTrack` gồm viseme, emotion, blink, eyebrow, eye và head-motion curves phù hợp với facial rig của `CharacterMaster`. Track có thể rebuild, review và sửa độc lập với body animation.

## 2. Điều kiện đầu vào

- Stage D đã có facial rig profile và mapping controls/blendshapes theo character revision.
- Stage E đã publish dialogue audio, word/phoneme timestamps và confidence.
- Stage H đã khóa body/head ownership rules để facial layer không ghi đè sai bones.
- Shot frame range/fps đã xác định.

## 3. Phase 18 — Lip-sync / Facial Pipeline

### Domain và contract

```text
PhonemeTrack
VisemeMap
VisemeKeyframe
EmotionCurve
GazeTrack
BlinkTrack
FacialAnimationTrack
FacialValidationReceipt
```

Tạo `FacialAnimationCompilerPort`; implementation Blender map semantic controls sang shape keys/bones trong adapter, không để domain chứa tên data-block `bpy`.

### Backlog

1. Chuẩn hóa word/phoneme timing theo fps và shot offset; giữ source alignment hash.
2. Version viseme map theo language + facial rig profile; missing phoneme dùng rule rõ, không bỏ im lặng.
3. Sinh viseme curves có coarticulation, smoothing, minimum hold và bounded amplitude.
4. Map emotion từ dialogue/director intent thành curves; emotion không được phá articulation.
5. Thêm blink, eyebrow, eye target và subtle head motion bằng deterministic seed/policy.
6. Định nghĩa layer ownership: jaw/lips/face do facial track; neck/head có blend policy với body animation.
7. Bake track thành derived action, lưu compiler version, input hashes và frame range.
8. Cho phép repair riêng lip-sync, gaze hoặc emotion; invalidation chỉ chạm affected track + render/final downstream.
9. Tạo preview close-up/playblast trước Cycles final.

## 4. Kiểm thử và quality gates

- Phoneme/viseme ordering monotonic; không keyframe ngoài shot range.
- Audio/animation drift không vượt tolerance đã cấu hình ở đầu, giữa và cuối line.
- Low-confidence alignment hoặc facial rig thiếu controls chuyển `REQUIRES_HUMAN_REVIEW`.
- Silence không tạo mouth movement; plosive/vowel fixtures có shape hợp lệ.
- Hai line liền nhau không gây facial pop; character không nói giữ neutral/subtle idle.
- Body head turn và facial head motion không cộng dồn vượt joint limit.
- Rebuild cùng input/profile/seed cho cùng curve manifest.

Gate nội bộ: `VP3D_P18_FACIAL_PIPELINE_VERIFIED`.

## 5. Evidence

```text
artifacts/video_production_3d/phase_18/
├── alignment_input_manifest.json
├── viseme_map.json
├── facial_track.json
├── curve_validation_report.json
├── sync_metrics.json
├── preview_render_manifest.json
└── phase_verdict.json
```

Fixture tối thiểu gồm tiếng Việt có dấu, khoảng lặng, câu nhanh, emotion change và hai character đối thoại.

## 6. Rủi ro

- Forced aligner không có phoneme tiếng Việt đủ tốt; adapter phải công bố capability/confidence và không giả precision.
- Rig từ nhiều nguồn có shape key semantics khác; mapping thuộc master revision và phải có calibration preview.
- Lip-sync metric có thể pass nhưng nhìn máy móc; visual review/human threshold vẫn bắt buộc cho master character mới.
