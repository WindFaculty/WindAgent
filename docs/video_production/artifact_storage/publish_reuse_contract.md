# Publish & Reuse Contract (Phase 18, §14.1, §14.4)

**Gate:** `VP18_ARTIFACT_INVALIDATION_VERIFIED` — plan 05 §11–§16
**Modules:** `storage/windagent_storage/video_production/publisher.py`,
`store.py`, `reuse.py`

## 1. Atomic publish pipeline (§14.1)

```text
write temporary
→ hash/size/decode validation
→ metadata record transaction
→ atomic promote
→ publish ArtifactAvailable event
```

`ArtifactPublisher.publish(request)` thực hiện theo thứ tự fail-closed:

1. **Empty payload** → `ValueError` (trước mọi write).
2. **Content file** được publish vào `ContentAddressedStore` TRƯỚC
   (temp write + fsync + atomic rename; idempotent theo content hash).
3. **Validator** (hash/size/decode port) chạy sau khi bytes durable — một
   validator từ chối không bao giờ để record được promote (test
   `test_publish_validator_failure_never_promotes_record`).
4. **Record transaction**: `ArtifactRecordStore.save` (atomic, unique temp
   name) — record chỉ `VALIDATED`/`VALID` sau khi file tồn tại.
5. **`ArtifactAvailableEvent`** được tạo SAU record commit; `EventJournal`
   append-only.

### Crash-safety contract

- Crash giữa content write và record write → **orphan file KHÔNG có VALID
  record** (GC-able, không bao giờ được reference).
- Crash sau record write → record có thể thiếu event; không bao giờ có
  published file thiếu record.
- Không bao giờ: VALID record trỏ file thiếu, hay published file thiếu record.

## 2. ContentAddressedStore (§14.1)

- Key: SHA-256 payload; `publish` atomic + idempotent; `read`/`exists`/
  `list_hashes`.

## 3. ArtifactRecordStore

- Atomic writes (unique temp name + `os.replace`) — concurrent saves không
  corrupt temp file của nhau.
- **History append-only guard**: `save` từ chối nếu history co lại
  (`history would shrink`) — invalidation không bao giờ mất audit.

## 4. Reuse policy (§14.4)

Reuse **chỉ khi** tất cả rule sau thỏa mãn — vi phạm bất kỳ rule nào → `REUSE_BLOCKED` với lý do cụ thể:

1. **Full content key match** — `key_matches(record.artifact_key, expected_key)` (bao gồm version prefix).
2. **File hash/validation còn hợp lệ** — content file tồn tại **VÀ** bytes
   re-hash đúng `content_sha256` (test tamper: sửa file → `REUSE_BLOCKED`;
   **không bao giờ dùng "file exists" làm evidence duy nhất**).
3. **Approval phù hợp** — khi `require_approval=True`, record phải `APPROVED`.
4. **Không stale/revoked** — chỉ `status == VALID` reusable (`STALE`/
   `SUPERSEDED` → blocked).
5. **Policy** — cross-project reuse chỉ khi `allow_cross_project` (per-call
   override được tôn trọng qua single effective-value check); cross-run theo
   `allow_cross_run`.

```text
ArtifactReusePolicy(content_store=..., require_approval=True,
                    allow_cross_project=False, allow_cross_run=True)
  .can_reuse(record, expected_key=..., project_id=...)
  → ReuseDecision(REUSE_ALLOWED | REUSE_BLOCKED, reason)
```

## 5. Kiểm chứng gate

- Cùng canonical input → cùng key → reuse được phép (nếu VALID + approval).
- Đổi reference/prompt/model/parameter → key khác → không reuse.
- File tamper → blocked (hash mismatch, không phải chỉ "file thiếu").
- Stale/superseded → blocked.
- Cross-project → blocked trừ khi policy/override cho phép.
