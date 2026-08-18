# Phase 4 Report — Script → Video Plan Compiler (Video 02)

## 1. Mục tiêu và Tổng quan

Phase 4 hoàn thành việc xây dựng bộ biên dịch **`CodeVideoScriptCompiler`**, chuyển đổi kịch bản Video 02 thành kế hoạch sản xuất video máy đọc được (machine-readable Intermediate Representation - IR) với thời lượng chuẩn xác tuyệt đối **16:15.000 (975,000 ms)** trải dài qua 19 phân cảnh liên tục (S01 đến S19).

---

## 2. Bản đồ 19 Scenes (Scene Map)

| Scene | Timecode | Start (ms) | End (ms) | Thời lượng | Visual Mode | Tiêu đề |
|---|---|---|---|---|---|---|
| **S01** | 00:00–00:25 | 0 | 25,000 | 25s | `SPLIT` | Cold Open — Live Agent Execution |
| **S02** | 00:25–00:50 | 25,000 | 50,000 | 25s | `TITLE_CARD` | Hook — Viết AI Agent Đầu Tiên Bằng Python |
| **S03** | 00:50–01:25 | 50,000 | 85,000 | 35s | `DIAGRAM` | Video 01 Recap — Nền tảng Agent Architecture |
| **S04** | 01:25–02:10 | 85,000 | 130,000 | 45s | `ARCHITECTURE` | Architecture v0.1 — User -> Agent -> LLM -> Answer |
| **S05** | 02:10–02:45 | 130,000 | 165,000 | 35s | `FULL_TERMINAL` | Create Repository — Project Scaffolding |
| **S06** | 02:45–03:40 | 165,000 | 220,000 | 55s | `CODE_STUDIO` | Message — Immutable Conversation Representation |
| **S07** | 03:40–04:35 | 220,000 | 275,000 | 55s | `CODE_STUDIO` | AgentConfig — Hyperparameters & System Prompt |
| **S08** | 04:35–06:00 | 275,000 | 360,000 | 85s | `CODE_STUDIO` | LLMClient — Domain Abstraction Protocol |
| **S09** | 06:00–06:50 | 360,000 | 410,000 | 50s | `CODE_STUDIO` | Fake LLM — Deterministic Offline Testing Client |
| **S10** | 06:50–08:25 | 410,000 | 505,000 | 95s | `CODE_STUDIO` | Agent — Orchestration Core Class |
| **S11** | 08:25–09:00 | 505,000 | 540,000 | 35s | `DIAGRAM` | Is This An Agent? — Concept Deep Dive |
| **S12** | 09:00–10:15 | 540,000 | 615,000 | 75s | `CODE_STUDIO` | Real Provider — Infrastructure Layer Adapter |
| **S13** | 10:15–11:05 | 615,000 | 665,000 | 50s | `CODE_STUDIO` | API Key — Environment Configuration & Security |
| **S14** | 11:05–12:00 | 665,000 | 720,000 | 55s | `FULL_TERMINAL` | First Run — Terminal Execution Replay |
| **S15** | 12:00–13:20 | 720,000 | 800,000 | 80s | `CODE_STUDIO` | Tests — Pytest Suite (2 passed) |
| **S16** | 13:20–14:10 | 800,000 | 850,000 | 50s | `CHECKLIST` | Not Yet — Feature Boundaries & Scope |
| **S17** | 14:10–15:00 | 850,000 | 900,000 | 50s | `ARCHITECTURE` | Architecture Review — Domain / Infrastructure Separation |
| **S18** | 15:00–15:35 | 900,000 | 935,000 | 35s | `FULL_TERMINAL` | Git Milestone — Commit & Release Tagging |
| **S19** | 15:35–16:15 | 935,000 | 975,000 | 40s | `OUTRO` | Video 03 Teaser & Outro — Tool Calling Preview |

---

## 3. Các artifact đầu ra đã xuất khẩu

- **`artifacts/code_video/video_02/plans/video_02_plan.yaml`**: Bản kế hoạch YAML đầy đủ các action và expected states.
- **`artifacts/code_video/video_02/plans/video_02_plan.json`**: Bản kế hoạch JSON phục vụ React / frontend renderer tiêu thụ.
- **`artifacts/code_video/video_02/plans/video_02_cue_sheet.csv`**: Bảng voice cue sheet 19 dòng chuẩn mốc thời gian phục vụ người dùng lồng tiếng sau.

---

## 4. Kết luận Gate

Gate **`CV02_P4_PLAN_COMPILER_VERIFIED`** đạt trạng thái **PASS**.
Toàn bộ timeline và contract của Video 02 đã được đóng băng và sẵn sàng cho **Phase 5: Code Studio Renderer**.
