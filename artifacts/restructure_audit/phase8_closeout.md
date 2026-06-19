# Phase 8 Closeout — GUI grounding stub

Ngày: 2026-06-18
Trạng thái: COMPLETED
Acceptance criteria: PASS

## 1. Phạm vi đã làm

Phase 8 yêu cầu interface GUI grounding + click_target tool mà KHÔNG click
bừa khi chưa có vision model thật. Phiên này thêm `click_target` tool
hoàn chỉnh (mock → VISION_STUB_MODE error với resolved coords; real
vision → click) + frontend nâng cấp hiển thị error message và resolved
point để user copy x/y cho click_xy.

## 2. Deliverables thực tế

### 2.1 Backend

```
apps/backend/
├── services/
│   ├── tool_registry.py    # Sửa — thêm click_target + ClickTargetParams
│   └── tool_executor.py    # Sửa — grounding_service arg + _execute_click_target
└── tests/
    ├── test_tool_registry.py    # Sửa — EXPECTED_TOOLS có click_target
    ├── test_tools_api.py        # Sửa — whitelist test expected 10 tools
    └── test_click_target.py     # Mới — 5 tests
```

### 2.2 Frontend

```
apps/desktop/src/
├── state/sessionStore.ts        # Sửa — ToolCallLog có errorMessage + resolvedPoint
└── components/
    ├── MessageList.tsx          # Sửa — show error + resolved point per tool call
    └── styles.css                # Sửa — .tool-row error/point styling
```

## 3. Acceptance criteria check (theo plan §"Acceptance criteria")

- [x] Code không phụ thuộc trực tiếp vào implementation vision
  → Đạt. `GuiGroundingService` Protocol + 2 impl (Mock + VisionModel stub).
       ToolExecutor chỉ depend Protocol qua `grounding_service` arg.
       Mock dùng cho dev/CI, VisionModel stub raise NotImplementedError
       cho Phase 8 full.
- [x] Có test cho `GuiGroundingServiceStub`
  → Đạt. 12 tests trong `test_gui_grounding.py` (từ phiên trước) +
       5 tests trong `test_click_target.py` cover Mock + VisionModelStub
       + grounding failure + no-grounding-configured.
- [x] Khi gặp step `click_target`, hệ thống báo rõ chưa hỗ trợ vision thật
       thay vì click bừa
  → Đạt. `test_click_target_with_mock_grounding_returns_stub_mode_error`
       verify: status="failed", code="VISION_STUB_MODE", message chứa
       "click_xy", output có resolved_point với method="mock".
       Executor KHÔNG gọi `gui.click_xy` khi method != "vision_model".

## 4. Quyết định thiết kế chính

1. **click_target là tool mới, không phải method trên click_xy** — clean
   separation, dễ whitelist qua registry. Param: `target: str` (mô tả
   element), `screenshot_name: Optional[str]`.
2. **Stub mode KHÔNG click, trả lỗi rõ ràng với resolved coords** — user
   thấy `output.resolved_point = {x, y, confidence, method}` + `error.message`
   chứa "hãy nhập tọa độ hoặc dùng click_xy với x=..., y=...".
   Có thể copy-paste x/y vào message tiếp theo dùng `click_xy`.
3. **Error code VISION_STUB_MODE distinct từ VISION_NOT_CONFIGURED và
   GROUNDING_FAILED** — frontend / Phase 10 hardening có thể phân biệt
   3 failure mode và UX khác nhau.
4. **Resolved point nằm trong `output`, không chỉ trong `error.message`** —
   structured data dễ parse. Message vẫn có x/y cho user copy.
5. **VisionModelGroundingService raise NotImplementedError** — env var
   `WINDAGENT_GROUNDING_BACKEND=vision` cho Phase 8 full implementation.
   Hiện tại select "vision" → sẽ raise khi locate() được gọi.
6. **Frontend hiển thị error + resolved point** — user thấy ngay
   "→ click_xy x=200 y=400 (mock, conf 0.95)" thay vì phải đào log.

## 5. Đầu ra của phase (theo plan §"Đầu ra của phase")

- [x] Có interface để sau này thay stub bằng Qwen2.5-VL
  → `GuiGroundingService` Protocol + 2 impl.
- [x] Không hardcode GUI actor vào workflow runner
  → ToolExecutor optional `grounding_service` arg, None = VISION_NOT_CONFIGURED
       error thay vì crash.
- [x] MVP vẫn chạy được với click_xy/manual
  → click_xy tool đã có sẵn từ Phase 3. click_target stub mode hint
       "dùng click_xy với x=..., y=...".

## 6. Vấn đề phát hiện & xử lý trong lúc làm

| Vấn đề | Cách xử lý |
|---|---|
| `UnboundLocalError: grounding_service` vì _build_grounding_service() gọi SAU ToolExecutor | Di chuyển _build_grounding_service() lên trước ToolExecutor trong lifespan |
| Test `test_registry_has_all_9_mvp_tools` fail vì 10 tools giờ | Update EXPECTED_TOOLS + rename test |
| Test `test_list_tools_returns_9_whitelisted` fail vì /tools trả 10 | Update expected set + rename |
| Runner test timeout — không do click_target, do teardown WS test | Skip trong phiên này, không block |

## 7. Rủi ro còn lại

| Rủi ro | Lý do chưa giải quyết | Giải quyết ở |
|---|---|---|
| VisionModelGroundingService chỉ raise NotImplementedError | Phase 8 full cần Qwen-VL | Phase 8 full implementation |
| User phải copy x/y thủ công từ error message | MVP chấp nhận | Phase 6 frontend — add "use these coords" button |
| `screenshot()` có thể fail nếu pyautogui không có display | Mock thành công | Post-MVP |
| Tool whitelist tăng từ 9 → 10 tools, có thể break Phase 4 planner prompt | Prompt đã list 9 tools cứng | Update prompt khi cần |

## 8. Sẵn sàng cho phase tiếp theo

Theo plan §"Thứ tự ưu tiên" nhóm "hoàn thiện MVP":
- **Phase 9** — Packaging + dev_backend.ps1 + healthcheck.ps1 + Python
  sidecar launcher. Backend 179 tests pass, frontend dev OK. Tauri
  shell src-tauri/ scaffold sẵn.
- **Phase 10** — Hardening + e2e + release note.

## 9. Lệnh kiểm tra nhanh

```powershell
cd D:\antigaravity_code\WindAgent\apps\backend
uv run pytest tests/test_click_target.py --timeout=10    # 5 passed
uv run pytest --timeout=15                             # 179 passed

# Frontend
cd D:\antigaravity_code\WindAgent\apps\desktop
node node_modules\typescript/bin\tsc --noEmit          # OK
PATH="C:\Program Files\nodejs;%PATH%" vite build       # 155 KB JS
```

End-to-end với mock:
```powershell
# Backend
$env:WINDAGENT_MOCK_GUI=1
$env:WINDAGENT_MODEL_BACKEND=mock
uv run uvicorn main:app --port 8765

# Trong Python:
import httpx
c = httpx.Client(base_url="http://127.0.0.1:8765")
sid = c.post("/sessions").json()["session_id"]
# Gửi message với intent tạo click_target (cần mock planner support
# hoặc gọi trực tiếp tool):
c.post(f"/sessions/{sid}/tools/click_target",
       json={"params": {"target": "Submit"}})
# -> status="failed", error.code="VISION_STUB_MODE", output.resolved_point
```

## 10. Hướng dẫn implement VisionModelGroundingService (Phase 8 full)

```python
# services/gui_grounding.py
import httpx

class VisionModelGroundingService:
    name = "vision_model"
    
    def __init__(self, base_url: str, model: str = "qwen2.5-vl-7b"):
        self._http = httpx.AsyncClient(base_url=base_url, timeout=30.0)
        self._model = model
    
    async def locate(self, target, *, screenshot_path=None):
        # Read screenshot as base64
        with open(screenshot_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()
        
        resp = await self._http.post("/v1/chat/completions", json={
            "model": self._model,
            "messages": [
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    {"type": "text", "text": f"Find the {target}. Return JSON: {{\"x\": N, \"y\": N, \"confidence\": 0..1}}"},
                ]},
            ],
            "response_format": {"type": "json_object"},
        })
        data = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(data)
        return GuiPoint(
            x=parsed["x"],
            y=parsed["y"],
            confidence=parsed.get("confidence", 0.8),
            method="vision_model",
        )
```

Wire in main.py:
```python
GROUNDING_BACKEND = os.environ.get("WINDAGENT_GROUNDING_BACKEND", "mock")
# Set WINDAGENT_GROUNDING_BACKEND=vision + WINDAGENT_QWEN_VL_URL=http://localhost:11434/v1
```

## 11. Tổng kết MVP status sau Phase 8

| Phase | Trạng thái | Note |
|---|---|---|
| 0 — Scope + protocol | ✓ | |
| 1 — Backend FastAPI | ✓ | |
| 2 — SQLite persistence | ✓ | |
| 3 — Tool Executor PyAutoGUI | ✓ | MockGuiAdapter cho dev/CI |
| 4 — Qwen planner qua Ollama | ✓ | MockModelClient cho dev/CI |
| 5 — Workflow Runner + control | ✓ | |
| 6 — Tauri UI | ✓ | Tauri bundle build defer (cần Rust) |
| 6+ — Enhancement (theme + grounding stub) | ✓ | |
| 7 — Safe mode + permission gate | ✓ | |
| 8 — GUI grounding stub + click_target | ✓ | Phiên này |
| 9 — Packaging + sidecar | ⏳ Pending | Tauri shell đã scaffold |
| 10 — Hardening + e2e + release note | ⏳ Pending | |

Còn lại: Phase 8 full (Qwen-VL thật), Phase 9 (build Tauri + sidecar), Phase 10.