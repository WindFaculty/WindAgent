# Kế hoạch triển khai WindAgent 3D Animation theo Stage

## 1. Phạm vi và nguồn chuẩn

Bộ tài liệu này là kế hoạch triển khai cho chương trình WindAgent 3D Animation (VP3D), 17 Stage bao phủ toàn bộ Phase 0–40. Trước đây phân rã từ `road_map.md` (bản 3D animation roadmap cũ); hiện tại `road_map.md` đã chuyển thành Studio Roadmap 1, nên thư mục này là authority về thứ tự thực thi, đầu ra, kiểm thử và điều kiện đóng gate của chương trình 3D.

Nếu roadmap thay đổi làm mâu thuẫn với một kế hoạch Stage, phải cập nhật kế hoạch đó trước khi triển khai code. Các kế hoạch Flow cũ trong `docs/video_production/plans/` chỉ là hồ sơ của kiến trúc trước và không được dùng để điều phối chương trình 3D mới.

## 2. Danh mục kế hoạch

| Stage | Phase | Kế hoạch | Kết quả chính |
|---|---:|---|---|
| A | 0–2 | [Stage A](stage_a_foundation_architecture.md) | Baseline, Production IR trung lập engine, loại bỏ Flow |
| B | 3–4 | [Stage B](stage_b_blender_runtime.md) | Blender headless và deterministic render kernel |
| C | 5–7 | [Stage C](stage_c_asset_production.md) | Asset gateway, provenance, normalization |
| D | 8–9 | [Stage D](stage_d_character_system.md) | Character master, rig và retarget |
| E | 10 | [Stage E](stage_e_concurrent_audio.md) | Audio/TTS chạy song song và giữ voice identity |
| F | 11–12 | [Stage F](stage_f_scene_construction.md) | Typed scene compiler và set dressing |
| G | 13–14 | [Stage G](stage_g_cinematography.md) | Camera compiler và lighting preset |
| H | 15–17 | [Stage H](stage_h_animation.md) | Library, procedural và AI motion adapter |
| I | 18 | [Stage I](stage_i_facial_animation.md) | Lip-sync và facial animation track |
| J | 19–21 | [Stage J](stage_j_rendering.md) | Cycles renderer, VRAM budget, render recovery |
| K | 22–23 | [Stage K](stage_k_quality_review.md) | Review 3D và retry theo nguyên nhân |
| L | 24 | [Stage L](stage_l_postproduction.md) | FFmpeg assembly có thể tái tạo |
| M | 25–30 | [Stage M](stage_m_end_to_end.md) | E2E 30 giây đến acceptance 20 phút |
| N | 31–32 | [Stage N](stage_n_workspace_human_editing.md) | Manual override và asset reuse theo episode |
| O | 33–35 | [Stage O](stage_o_production_hardening.md) | Add-on governance, reproducibility, Flow purge |
| P | 36–37 | [Stage P](stage_p_unreal_readiness.md) | Export layer trung lập engine và interchange |
| Q | 38–40 | [Stage Q](stage_q_unreal_engine.md) | Unreal PoC, asset pipeline và renderer chính |

## 3. Quy ước thực thi chung

### Trạng thái

Mỗi Phase chỉ dùng một trong các trạng thái:

```text
NOT_STARTED
IN_PROGRESS
BLOCKED
READY_FOR_GATE
VERIFIED
```

`VERIFIED` chỉ được ghi khi mọi acceptance criterion bắt buộc có evidence kiểm chứng. Test xanh nhưng thiếu artifact, sai SHA hoặc bỏ qua negative test vẫn là `BLOCKED`.

### Nhánh, commit và phạm vi

- Mỗi Stage dùng branch riêng từ SHA đã được xác minh của Stage trước.
- Stage có nhiều Phase nên giữ commit boundary theo Phase; không trộn xóa Flow, migration schema và Blender runtime trong cùng commit.
- Không sửa ngầm artifact đã khóa. Thay đổi input phải tạo revision mới và kích hoạt invalidation có chủ đích.
- Không chạm các thay đổi chưa commit không thuộc Stage đang thực hiện.
- Unreal không được đưa vào dependency runtime trước Stage Q; `bpy` chỉ được import bên trong Blender adapter.

### Evidence tối thiểu

Mỗi Phase tạo thư mục:

```text
artifacts/video_production_3d/phase_<NN>/
├── input_manifest.json
├── implementation_manifest.json
├── test_receipt.json
├── architecture_report.json
├── risk_register.json
├── phase_report.md
└── phase_verdict.json
```

Phase có chạy process/tool bên ngoài phải bổ sung command receipt, stdout/stderr đã redact, version, input hash và output hash. Phase benchmark phải lưu raw measurements, không chỉ lưu kết luận.

### Definition of Done chung

Một Phase chỉ được đóng khi:

- code, schema, migration và tài liệu liên quan đồng bộ;
- unit, integration, architecture và negative tests bắt buộc đều pass;
- output truy vết được về revision, input, tool version và SHA;
- retry/cancel/recovery không tạo side effect trùng;
- security check fail-closed;
- gate được derive tự động từ evidence, không nhập `PASS` thủ công;
- known limitations và quyết định hoãn được ghi rõ.

## 4. Dependency và luồng song song

Critical path đến golden scene:

```text
A → B → C → D → F → G → H → I → J → K → L → M/P25
                └──────── E ────────┘
```

Sau khi screenplay được khóa, Stage E có thể chạy song song với asset, environment và animation preparation. Stage N nên bắt đầu sau golden scene; Stage O phải hoàn tất trước controlled release. Stage P và Q chỉ bắt đầu sau khi Production IR, asset interchange và reproducibility đã ổn định.

## 5. Nguyên tắc hiệu năng

Target `20 phút, 1080p, 24 fps, Cycles, RTX 5060 8 GB, dưới 3 giờ` là benchmark gate, không phải giả định. Mọi Stage từ C đến M phải thu thập các tín hiệu có ảnh hưởng đến throughput: polycount, texture memory, shader complexity, samples, denoise, cache hit, render time/frame, peak VRAM và thời gian theo shot.

Không tự đổi Cycles sang Eevee để đạt gate. Nếu Phase 30 không đạt, verdict hợp lệ là `DEGRADED` hoặc `BLOCKED_BY_RENDER_THROUGHPUT`, kèm số đo và các lựa chọn cần người dùng quyết định.
