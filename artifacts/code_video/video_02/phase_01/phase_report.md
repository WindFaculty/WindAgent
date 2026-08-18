# PHASE 1 — CODE VIDEO CONTRACT & IR REPORT

## Summary

Phase 1 đã hoàn thành toàn bộ định nghĩa Intermediate Representation (IR), schema contracts, validation rules, workflow definitions, và bộ test suite toàn diện cho Code Video pipeline theo đúng đặc tả tại [`ban_ke_hoach_video_02.md`](file:///d:/code_ca_nhan/WindAgent/ban_ke_hoach_video_02.md).

- **IR Dataclasses**: `CodeVideoPlan`, `Scene`, `Action`, `ExpectedState`, `Annotation`, `OutputPolicy`, `Resolution`.
- **Enums**: `ActionType` (18 semantic actions), `VisualMode` (9 stage layout modes).
- **Semantic Actions Only**: Cấm tuyệt đối tọa độ pixel (`x`, `y`, `pixel_x`, `click_x`...) trong Action parameters.
- **Integer Milliseconds**: Mọi mốc thời gian (`start_ms`, `end_ms`, `duration_ms`) dùng số nguyên milliseconds để tránh sai số dấu phẩy động.
- **Audio Scope**: Giữ nguyên `EXCLUDED` cho Video 02, cấm các trường `audio_path`, `tts_model`, `voice_id` trong khi hỗ trợ `voice_cue_id` để xuất cue sheet CSV phục vụ lồng tiếng thủ công về sau.
- **Workflow Steps**: 9 bước durable (`COMPILE_PLAN` → `BUILD_WORKSPACE` → `VERIFY_TUTORIAL` → `RENDER_STUDIO` → `RUN_REPLAY` → `CAPTURE_TAKES` → `RENDER_GRAPHICS` → `ASSEMBLE_MASTER` → `FINAL_QC`).
- **Gate `CV02_P1_PLAN_CONTRACT_VERIFIED`**: **PASS** (16/16 unit tests passed).

---

## 1. Modules triển khai

```text
workflows/
└── windagent_workflows/
    └── code_video/
        ├── __init__.py
        ├── contracts.py       # Dataclasses, Enums, Validators, JSON/YAML/Dict serializers, Cue Sheet CSV generator
        └── definition.py      # 9 workflow step definitions, DAG nodes, step contracts

tools/
└── windagent_tools/
    └── code_video/
        └── __init__.py        # Tool layer initialization

tests/
└── contracts/
    └── test_code_video_contracts.py  # 16 automated tests covering all IR rules
```

---

## 2. Validation & Security Rules

| Quy tắc | Cơ chế kiểm tra | Kết quả |
|---------|-----------------|---------|
| Schema Roundtrip | Dict ↔ JSON ↔ YAML ↔ Dataclass | PASS |
| Integer Milliseconds | Chặn float, boolean, số âm ở constructor | PASS |
| Scene Duration Consistency | `duration_ms == end_ms - start_ms` | PASS |
| Overlapping & Gaps | Kiểm tra timeline liên tục trong `validate()` | PASS |
| Action Bounds | `action.start_ms >= scene.start_ms` & `action.end_ms <= scene.end_ms` | PASS |
| Unique Identifiers | Chặn duplicate `scene_id` và `action_id` | PASS |
| Semantic Actions | Chặn các key `x`, `y`, `pixel_x`, `click_x`... | PASS |
| Source Hash | Bắt buộc `source_hash` không được rỗng | PASS |
| Audio Excluded | Chặn `audio_path`, `tts_model`, `voice_id` | PASS |
| Voice Cue Sheet | Xuất CSV chuẩn `MM:SS.mmm` | PASS |

---

## 3. Test Suite Receipt

```text
tests/contracts/test_code_video_contracts.py: 16 passed in 0.85s
```

---

## 4. Gate Verdict

```text
CV02_P1_PLAN_CONTRACT_VERIFIED = PASS
```
