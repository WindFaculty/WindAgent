# Phase 9 — rollout và rollback an toàn

Phase 9 đưa multi-agent qua bốn stage tuần tự; không được nhảy cóc:

1. `schema_dual_read` — migrate schema bổ sung và tiếp tục đọc format cũ/mới; không dispatch runtime.
2. `shadow_orchestration` — so sánh fingerprint plan chính/shadow; shadow runner không có tool hoặc runtime dispatcher.
3. `internal_users` — chỉ actor đã xác thực và được allowlist mới dispatch.
4. `full_activation` — mở cho toàn bộ actor.

Thiết lập deployment:

```text
WINDAGENT_MULTI_AGENT_RELEASE_STAGE=schema_dual_read
WINDAGENT_MULTI_AGENT_INTERNAL_ACTORS=staff-1,staff-2
```

`release_actor_id` phải được tầng xác thực tin cậy gắn vào server-side request state. Không dùng HTTP header từ client để chứng minh internal user.

## Migration rehearsal bắt buộc

Trước một release SQLite, chạy trên một bản copy production, không phải file DB đang phục vụ:

```powershell
python scripts/phase9_release_rehearsal.py --database <production-copy.sqlite3> --backup-root <evidence-directory>
```

Rehearsal tạo backup nhất quán bằng SQLite backup API, upgrade trên `upgrade-copy`, downgrade về base trên `downgrade-copy`, rồi restore backup vào copy đó. Nó fingerprint các bảng immutable plan/audit (`task_plan_versions`, DAG nodes/edges, conversation events, turns, route attempts, partial streams) trước/sau.

Khi API khởi động với `WINDAGENT_ENV=production`, migration SQLite yêu cầu `WINDAGENT_RELEASE_BACKUP_ROOT`; backup được tạo trước khi Alembic chạy. Với PostgreSQL, deployment phải cung cấp đường dẫn evidence của backup đã xác minh qua `WINDAGENT_EXTERNAL_BACKUP_EVIDENCE`.

## Rollback

Rollback ứng dụng chỉ được thực hiện khi rehearsal trả `application_rollback_allowed=true`: immutable data phải nguyên vẹn, legacy read tables vẫn còn, và restore trên copy thành công. Rollback giữ schema mới có tính additive/dual-read.

Không chạy `alembic downgrade` trên database production. Downgrade trong rehearsal chỉ ở bản copy; plan immutable và audit không được xóa.

## Theo dõi trong từng stage

`ReleaseTelemetry.snapshot()` cung cấp các tín hiệu phải theo dõi:

- `route_failover_rate`
- `duplicate_tool_executions`
- `orphan_worktree_count`
- `websocket_reconnects`
- `recovery_duration_total_seconds` và `recovery_duration_max_seconds`
- `database_lock_errors`
- `shadow_mismatches`

Không tăng stage khi shadow mismatch, lock error, duplicate tool execution, hoặc orphan worktree chưa được điều tra và xử lý. Lưu receipt rehearsal cùng release evidence trước khi chuyển stage.
