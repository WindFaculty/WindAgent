# Models

Thư mục này **không chứa** model weights trong repo. Tất cả model local
được pull qua Ollama và lưu ở `%USERPROFILE%\.ollama\models`.

## Model MVP

| Model | Vai trò | Lệnh pull |
|---|---|---|
| qwen3:4b-q4 | Planner (workflow generator) | `ollama pull qwen3:4b-q4` |

## Yêu cầu hệ thống tối thiểu

- RAM: 8 GB trống (Qwen3 4B Q4 chiếm ~3 GB)
- Disk: 5 GB trống cho model cache
- GPU: không bắt buộc, CPU chạy được nhưng chậm hơn

## Kiểm tra model đã sẵn sàng

```powershell
ollama list
ollama show qwen3:4b-q4
```

Nếu `ollama list` trả về danh sách rỗng, chạy `ollama pull qwen3:4b-q4`
trước khi chạy backend.

## Lưu ý

- Repo này không commit model weights. Nếu cần phân phối model offline,
  dùng `ollama cp` hoặc `scripts/healthcheck.ps1` để báo user thiếu gì.
- Phase sau (post-MVP) sẽ thêm Qwen2.5-VL cho GUI grounding, không thuộc
  scope MVP.