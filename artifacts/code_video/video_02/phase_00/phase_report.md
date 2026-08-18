# PHASE 0 — FREEZE BASELINE & VIDEO 02 SOURCE

## Summary

Phase 0 đã khóa toàn bộ input trước khi viết code.

- Branch `feature/code-video-video02` được tạo từ baseline `0e2fa7a89c4e0c0875fab963bbe8278f4153783a`.
- Working tree được dọn sạch bằng commit cleanup hiện có trước đó.
- Video 02 source được đóng băng tại `artifacts/code_video/video_02/source/`.
- Script hash được cố định.
- Gate `CV02_P0_BASELINE_FROZEN` = **PASS**.

## Artifacts tạo mới

```text
artifacts/code_video/video_02/
├── source/
│   ├── script.md           # Video 02 script derive từ ban_ke_hoach_video_02.md
│   ├── script.sha256       # b2c9d46fd74cccc5f48de8509ceef41aec2dfb8db63a78c733a3d961ec1bec6c
│   └── baseline.json
├── plans/                  # Phase 4 output (empty — reserved)
├── checkpoints/            # Phase 3 golden checkpoints (empty — reserved)
├── takes/                  # Phase 7-9 takes (empty — reserved)
├── graphics/               # Phase 8 diagrams/title cards (empty — reserved)
├── timeline/               # Phase 10 timeline (empty — reserved)
├── reports/                # Phase 11 QC (empty — reserved)
├── final/                  # video_02_visual_master*.mp4 (empty — reserved)
└── phase_00/
    ├── input_manifest.json
    ├── implementation_manifest.json
    ├── test_receipt.json
    ├── architecture_report.json
    ├── phase_report.md
    └── phase_verdict.json
```

## Baseline

| Field | Value |
|-------|-------|
| baseline_sha | `0e2fa7a89c4e0c0875fab963bbe8278f4153783a` |
| branch | `feature/code-video-video02` |
| audio_scope | `EXCLUDED` |
| tool_calling_scope | `OUT_OF_SCOPE` |
| target_duration | `00:16:15.000` = 975 seconds |
| milestone | `v0.1` |
| tutorial_project | `agentic-studio` |
| script.sha256 | `b2c9d46fd74cccc5f48de8509ceef41aec2dfb8db63a78c733a3d961ec1bec6c` |

## Verification

Mọi điều kiện gate đều PASS:

1. baseline SHA đúng — git merge-base chứng minh branch bắt nguồn từ baseline.
2. script hash cố định — SHA256 khớp file `script.md`.
3. duration 975 giây.
4. audio `EXCLUDED`.
5. Tool Calling `OUT_OF_SCOPE`.
6. repository sạch trước implementation — 0 tracked modifications.

## Next

Phase 1 — Code Video Contract & IR: định nghĩa `CodeVideoPlan`, `Scene`, `Action` dựa trên `source/script.md`.

## Verdict

```text
CV02_P0_BASELINE_FROZEN = PASS
```