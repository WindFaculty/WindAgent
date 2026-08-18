# PHASE 2 — ISOLATED TUTORIAL WORKSPACE REPORT

## Summary

Phase 2 đã hoàn thành toàn bộ hạ tầng sandbox độc lập, trình tạo khung repository deterministic (`TutorialRepositoryBuilder`), trình quản lý checkpoint (`CheckpointManager`), và hệ thống quét bảo mật preflight (`WorkspaceSecretScanner`) cho tutorial workspace theo đúng kế hoạch tại [`ban_ke_hoach_video_02.md`](file:///d:/code_ca_nhan/WindAgent/ban_ke_hoach_video_02.md).

- **Cách ly Sandbox**: Đảm bảo toàn bộ mã nguồn của tutorial (`agentic-studio`) được tạo và thực thi trong thư mục độc lập (ví dụ `.tmp/code_video/video_02/agentic-studio`), không bao giờ nằm trong thư mục nguồn của WindAgent (`src/`, `workflows/`, `tools/`, `frontend/`, `core/`).
- **Tái sử dụng Canonical Tools**: Tái sử dụng `PathSandbox` và `SafeShellRunner` hiện có trong WindAgent.
- **Deterministic Scaffolding**: Trình tạo khung project đảm bảo chuẩn 8 file của Video 02 Definition of Done (`src/__init__.py`, `src/agent.py`, `tests/__init__.py`, `tests/test_agent.py`, `.env.example`, `.gitignore`, `pyproject.toml`, `README.md`).
- **Checkpoint Manager**: Hỗ trợ lưu trữ snapshot bất biến theo từng giai đoạn code (`cp_01_message` -> `cp_09_v0_1`) kèm SHA-256 hash và khôi phục chính xác.
- **Preflight Security Scanner**: Quét tự động toàn bộ file, `.env`, `.env.example`, git history và output lệnh nhằm ngăn chặn triệt để rò rỉ secret (`sk-...`, `AIza...`, `gsk_...`, `nvapi-...`, `Bearer ...`).
- **Gate `CV02_P2_SANDBOX_READY`**: **PASS** (14/14 unit tests passed).

---

## 1. Modules triển khai

```text
tools/
└── windagent_tools/
    └── code_video/
        ├── __init__.py
        └── workspace/
            ├── sandbox.py             # TutorialWorkspace (cách ly + PathSandbox + SafeShellRunner)
            ├── repository_builder.py  # TutorialRepositoryBuilder (khung 8 files + validator)
            ├── checkpoints.py         # CheckpointManager (snapshot SHA256 + restore + verify)
            └── security_scanner.py    # WorkspaceSecretScanner (preflight zero-secret enforcer)

tests/
└── contracts/
    └── test_code_video_workspace.py   # 14 automated tests covering all sandbox requirements
```

---

## 2. Security & Isolation Rules

| Quy tắc | Cơ chế kiểm tra | Kết quả |
|---------|-----------------|---------|
| Cách ly mã nguồn | Chặn đặt workspace trong các thư mục host | PASS |
| Chống Path Traversal | `PathSandbox.resolve_safe_path()` | PASS |
| Safe Shell Execution | `SafeShellRunner` có timeout + redaction | PASS |
| Chuẩn khung 8 files | Kiểm tra sự tồn tại và cú pháp | PASS |
| Bảo vệ .env | Bắt buộc `.gitignore` chứa `.env` | PASS |
| Không lộ API Key | Quét regex phát hiện `sk-`, `AIza`, `gsk_`, `nvapi-`, `Bearer` | PASS |
| Checkpoint Integrity | SHA-256 đối chiếu từng file và toàn bộ workspace | PASS |

---

## 3. Test Suite Receipt

```text
tests/contracts/test_code_video_workspace.py: 14 passed in 0.65s
```

---

## 4. Gate Verdict

```text
CV02_P2_SANDBOX_READY = PASS
```
