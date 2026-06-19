# Phase 0 Closeout — Scope, repo skeleton, protocol

Ngày: 2026-06-18
Trạng thái: COMPLETED
Acceptance criteria: PASS (theo plan §"Acceptance criteria" của Phase 0)

## 1. Phạm vi đã làm

Phase 0 chốt scope MVP, tạo skeleton repo, viết hợp đồng event + workflow
schema. **Chưa viết một dòng code backend/frontend nào** — đúng theo tinh
thần "vertical slice sau, foundation trước" của plan.

## 2. Deliverables

### 2.1 Cấu trúc thư mục (theo plan §0.1)

```
WindAgent/
├── apps/
│   ├── desktop/         # + src/, src-tauri/, README.md
│   └── backend/         # + routers/, services/, schemas/, db/, README.md
├── docs/
│   ├── mvp_scope.md     # Phase 0.2 — đầy đủ
│   ├── event_protocol.md  # Phase 0.3 + §0.4 — đầy đủ
│   ├── api_contract.md  # Stub (fill Phase 1)
│   └── safety_policy.md # Stub (fill Phase 7)
├── models/
│   └── README.md
├── scripts/
│   ├── dev_backend.ps1    # Stub (fill Phase 9)
│   ├── dev_desktop.ps1    # Stub (fill Phase 9)
│   └── healthcheck.ps1    # Stub (fill Phase 9)
├── artifacts/
│   ├── runs/
│   │   ├── .gitkeep
│   │   └── sample_workflow.json  # Phase 0.4 — workflow mẫu
│   └── restructure_audit/        # chứa closeout reports
├── README.md
└── .gitignore
```

Tổng số file tạo mới: 14 (không tính `ban_ke_hoach.md`).

### 2.2 Nội dung docs

| File | Trạng thái | Điểm chính |
|---|---|---|
| `docs/mvp_scope.md` | Đầy đủ | MVP là gì / không làm gì, 2 demo bắt buộc, acceptance criteria tổng thể, 9 rủi ro kỹ thuật đã biết + mitigation, 5 nguyên tắc triển khai |
| `docs/event_protocol.md` | Đầy đủ | Format JSON chuẩn 3 trường, 17 event MVP phân nhóm, chi tiết `data` cho từng event, quy tắc emit, **workflow schema tuần tự + tool whitelist 9 tool + param schema cho từng tool**, ví dụ end-to-end |
| `docs/api_contract.md` | Stub | 11 endpoint preview, 4 TODO cho Phase 1 |
| `docs/safety_policy.md` | Stub | Risk level safe/medium/high, 4 TODO cho Phase 7 |
| `models/README.md` | Đầy đủ | Pull `qwen3:4b-q4`, yêu cầu hệ thống |
| `README.md` (root) | Đầy đủ | Trạng thái phase, demo, cấu trúc, link tới docs |
| `.gitignore` | Đầy đủ | Python, Node/Tauri, IDE, runtime artifacts, SQLite |

### 2.3 Workflow schema mẫu

`artifacts/runs/sample_workflow.json` chứa workflow 2 step `open_app
notepad` → `type_text "Hello from local AI agent."`. Khớp 100% schema
trong `event_protocol.md` §6. Có thể dùng làm fixture test cho Phase 1.

## 3. Acceptance criteria check (theo plan)

- [x] Developer mới mở repo có thể hiểu MVP cần làm gì trong 10 phút.
      Đạt vì `README.md` + `docs/mvp_scope.md` ngắn gọn, có demo + check list.
- [x] Không có module thừa như plugin system, Playwright, multi-agent.
      Đạt — `mvp_scope.md` §3 liệt kê rõ 10 hạng mục defer, repo không
      có code nào cả.
- [x] Tất cả phase sau phải bám theo `docs/mvp_scope.md`.
      Đạt — file có đủ acceptance criteria + nguyên tắc để soi.

## 4. Quyết định thiết kế đã chốt

1. **Workflow schema là tuần tự** (không branching/loop), max 20 step ở
   MVP. Document hóa trong `event_protocol.md` §6.
2. **Tool whitelist 9 tool** được chốt ngay từ Phase 0 để Phase 1+ dùng
   luôn. Document hóa cùng param schema đầy đủ.
3. **17 event** chia 6 nhóm, có chi tiết `data` cho từng event. Phase 1+
   chỉ cần implement theo doc, không phải đoán shape.
4. **Frontend gửi control message qua WebSocket** (`pause`/`resume`/
   `stop`/`permission_*`), backend echo lại cho các client khác. Document
   trong `event_protocol.md` §5.
5. **2 file doc dạng stub** (`api_contract.md`, `safety_policy.md`) được
   tạo sẵn để khớp layout plan, có checklist rõ TODO từng phase.

## 5. Việc KHÔNG làm trong Phase 0 (theo đúng scope)

- Không viết code backend/frontend.
- Không tạo `requirements.txt` / `package.json` (sẽ tạo ở phase tương ứng).
- Không init git (chờ user yêu cầu).
- Không tạo CI/CD config.
- Không commit file binary, model weights.

## 6. Rủi ro còn lại cần theo dõi ở phase sau

| Rủi ro | Lý do chưa giải quyết | Giải quyết ở |
|---|---|---|
| Schema event có thể sai khi implement | Chưa có code thật để test shape | Phase 1 — viết test parse JSON event mẫu |
| Tool whitelist có thể thiếu tool cần thiết | Chưa demo thật | Phase 3 — bổ sung nếu thiếu |
| Workflow max 20 step có thể quá ít | Chưa có use case thật | Phase 10 — review khi hardening |

## 7. Sẵn sàng cho Phase 1

Phase 1 có thể bắt đầu ngay. Mọi thứ cần biết đã có ở:
- `docs/event_protocol.md` — biết emit event gì, shape gì
- `docs/api_contract.md` — biết cần implement endpoint nào
- `artifacts/runs/sample_workflow.json` — biết workflow mẫu trả về gì
- `apps/backend/README.md` — biết layout file backend sẽ tạo

## 8. Lệnh kiểm tra nhanh sau Phase 0

```bash
cd WindAgent
find . -type f -not -name 'ban_ke_hoach.md' | sort
```

Kỳ vọng: 14 file như liệt kê ở §2.1.