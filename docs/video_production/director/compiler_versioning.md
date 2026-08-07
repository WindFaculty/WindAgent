# Compiler Versioning & Reproducibility (Phase 11)

> Kế hoạch: `docs/video_production/plans/03_phase_08_11_director_layer.md` §24.2, §24.5.
> Module: `intelligence/windagent_intelligence/video/prompt_compiler/`.

## 1. Phiên bản

| Version | Giá trị v1.0.0 | Thay đổi khi |
|---|---|---|
| `compiler_version` | `1.0.0` | thuật toán compile thay đổi |
| `prompt_template_version` | `1.0.0` | thứ tự/format block thay đổi |

Cả hai đều nằm trong `request_hash` — đổi compiler hoặc template tự động tạo
request hash mới (không cần đổi input nội dung).

## 2. Prompt hash

```text
prompt_hash = SHA256(
    prompt_template_version
    + blocks (canonical: block_type/order/content/required, sort_keys)
)
```

- Cùng input → cùng prompt hash.
- Đổi bất kỳ block nào (kể cả optional bị drop) → prompt hash mới.

## 3. Request hash (§24.5)

```text
request_hash = SHA256(
    project_id + revision_id + shot_id
    + generation_mode
    + compiler_version
    + prompt_template_version
    + prompt_hash
    + reference_hashes (sorted, de-duped)
    + parameters (duration, frame rate, aspect ratio, mode, retry)
    + model_capability_constraints
)
```

**Cùng input → cùng request hash.** Thay đổi một trong các yếu tố sau đều tạo
hash mới:

- reference (asset hash thay đổi → `reference_hashes` đổi);
- prompt version / compiler version;
- generation parameters (duration, mode, aspect ratio…).

## 4. Determinism

Toàn bộ pipeline Phase 11 deterministic:

- `StableIdFactory` sinh mọi ID từ SHA-256 seed (không uuid/random);
- `package.content_hash()` loại provenance/approvals/generation_records/
  final_deliverable và strip `acquired_at` → ổn định giữa các lần build;
- binding hash và request hash không phụ thuộc timestamp;
- không gọi provider/network.

Verifier chứng minh bằng cách chạy compiler 2 lần và so khớp `request_hash`
byte-identical.

## 5. Hash thay đổi → invalidation (§24.5 → Phase 18)

| Input thay đổi | Hash đổi | Shot ảnh hưởng |
|---|---|---|
| character reference hash | `reference_hashes` đổi | chỉ shot bind asset đó |
| prompt template version | `prompt_hash` + `request_hash` đổi | toàn bộ shot |
| generation parameters | `request_hash` đổi | shot đó |
| screenplay → plan → graph | `source_plan_hash`/`graph_hash` đổi | toàn bộ |

## 6. Contract receipt

`artifacts/video_production/phase_11/prompt_hash_receipt.json`:

- stable hash: cùng input chạy 2 lần → cùng `request_hash`;
- đổi reference / compiler version / parameters → hash mới;
- mọi request hash + prompt hash 64-char và duy nhất theo shot/mode.
