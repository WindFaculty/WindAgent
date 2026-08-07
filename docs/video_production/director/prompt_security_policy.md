# Prompt Security Policy (Phase 11)

> Kế hoạch: `docs/video_production/plans/03_phase_08_11_director_layer.md` §24.4.
> Module: `intelligence/windagent_intelligence/video/prompt_compiler/security.py`.

## 1. Nguyên tắc trust boundary

Prompt compiler là **biên giới tin cậy** giữa dữ liệu nguồn và request gửi tới
provider. Không có nội dung web/model tự do đi thẳng vào browser:

```text
package bibles + shot spec + ledger (trusted)
        ↓
PromptBlockBuilder (chỉ đọc trusted fields)
        ↓
PromptSanitizer (redact + gate)
        ↓
CompiledPrompt → GenerationRequest (đã sanitize, không raw)
```

## 2. Luật cấm / redaction

| Rule | Hành vi | Finding |
|---|---|---|
| Local path / profile (`C:\Users\...`, `/home/...`, `~/...`) | REDACT `[REDACTED]` | `local_path` |
| Secret marker (`api_key=`, `token=`, `password=`, bearer) | REDACT value | `secret_marker` |
| Control / escape Unicode | strip (giữ `\n` `\t`) | `control_unicode` |
| Vượt length/token gate (mặc định 6000 chars/block) | BLOCKING — không compile | `oversized` |

- Finding được ghi **redacted**, không bao giờ log raw (cookie/session không
  vào log, §24.4).
- Blocking finding → compiler raise `ValidationFailureError` — không publish
  request một phần.

## 3. Không đọc instruction từ metadata

Compiler **không bao giờ** đọc EXIF, web page text, alt text hoặc asset
metadata vào prompt. `PromptBlockBuilder` chỉ đọc:

- `style_bible` / `character` / `location` / `prop` bibles;
- `ShotSpecification` (action, camera, composition, duration…);
- continuity ledger (camera side, identity/appearance state).

Test chứng minh: asset metadata chứa `"ignore previous instructions"` không
xuất hiện trong request (§25).

## 4. Allowlist

Chỉ block/field đã định nghĩa trong `PromptBlockType` được phát hành. Field
lạ bị bỏ qua hoặc phát `UNKNOWN_FIELD` (blocking). Compiler không có khái
niệm selector/click/submit — LLM không bao giờ điều khiển browser từ prompt
(§24.4).

## 5. Logging

- Prompt đầy đủ chỉ lưu như artifact mã hoá/theo policy lưu trữ;
- Log chỉ chứa `prompt_hash`, `request_hash`, `block_type`, số finding —
  không chứa nội dung raw hay cookie/session;
- `PromptSecurityFinding.redacted=True` mặc định.

## 6. Length gate

- Mặc định `DEFAULT_MAX_PROMPT_CHARS = 6000` cho mỗi block;
- Vượt gate → `PROMPT_OVERSIZED` (blocking) → compile fail rõ ràng (§29:
  "Prompt quá dài → Block priority, bounded length và explicit compile
  failure");
- `allow_overflow=True` chỉ dùng trong verifier/tests để chứng minh
  fail-closed — production luôn gate ON.

## 7. Contract receipt

`artifacts/video_production/phase_11/prompt_security_receipt.json`:

- local path/secret marker bị redact, prompt không còn raw marker;
- oversized block → blocked;
- metadata độc hại không vào prompt;
- control unicode bị strip;
- mọi golden fixture compile sạch không finding blocking.
