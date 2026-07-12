Bạn đang làm việc trực tiếp trong repository:

* Repository: `WindFaculty/WindAgent`
* Local branch được audit: `feat/phase-1-baseline`
* Starting reference theo audit: `9205dfa111301eb65cf1963dde89778e246dae5c`
* Commit message tại ref: `feat(hermes): implement stop run mapping and resource cleanup for Hermes sessions`
* Trạng thái audit trước đó:

  * Khoảng 19 file modified và 21 file untracked.
  * `git diff 9205dfa..HEAD` rỗng vì chưa có commit mới.
  * Focused backend: `33 passed, 1 warning`.
  * Backend và frontend runtime đều đang down.
  * Các module orchestration tồn tại độc lập nhưng chưa được nối vào live path.
  * Live path vẫn chủ yếu là Phase-1 single-agent Hermes bridge.
  * Verdict hiện tại: `partial_foundation_implemented`.
  * Core gates: fail.
  * Rủi ro P0: API key provider đang được lưu plaintext.
  * Không được tuyên bố orchestration đã hoàn thành nếu chưa có black-box runtime evidence.

# NHIỆM VỤ CHÍNH

Đưa WindAgent từ trạng thái `partial_foundation_implemented` sang một vertical slice orchestration chạy thật xuyên suốt:

```text
chat request
→ create conversation turn
→ supervisor spawn
→ build/persist DAG
→ acquire route lock
→ execute run_plan
→ persist incremental/partial state
→ publish events
→ finish/cancel/fail deterministically
→ release lock
→ recover state after restart
```

Phạm vi bắt buộc của lần triển khai này:

1. Bảo toàn và chuẩn hóa toàn bộ worktree hiện tại.
2. Loại bỏ rủi ro API key plaintext.
3. Thêm Alembic/database migration cần thiết.
4. Thêm workspace/path traversal protection.
5. Nối `chat → supervisor → DAG → route lock → run_plan`.
6. Thực thi idempotency, partial persistence và state transitions.
7. Chứng minh vertical slice bằng E2E với fake Hermes.
8. Khởi động backend thật và chạy black-box runtime test.
9. Commit, push và xác minh remote SHA.
10. Viết báo cáo evidence-first, không phóng đại kết quả.

Không thực hiện frontend cosmetics hoặc refactor lớn trước khi vertical slice backend đạt gate.

# NGUYÊN TẮC KHÔNG ĐƯỢC VI PHẠM

## 1. Không làm mất worktree

Tuyệt đối không chạy các lệnh có thể phá hủy thay đổi hiện có như:

```bash
git reset --hard
git clean -fd
git checkout -- .
git restore .
git stash drop
```

Không ghi đè hoặc xóa bất kỳ file modified/untracked nào trước khi đã phân loại và lưu provenance.

## 2. Không commit mù toàn bộ working tree

Không dùng:

```bash
git add .
git add -A
```

trước khi kiểm tra từng file.

Phải phân loại file thành:

* Source orchestration liên quan.
* Test liên quan.
* Migration/schema.
* Frontend liên quan.
* Report/artifact.
* Generated/cache/runtime DB.
* File chứa secret hoặc dữ liệu local.
* Thay đổi không liên quan.

Chỉ stage từng file hoặc từng hunk có chủ đích.

## 3. Không tiết lộ secret

Không in API key, token, encryption key hoặc credential vào:

* Terminal output.
* Test logs.
* Exception.
* HTTP response.
* WebSocket payload.
* Report.
* Artifact.
* Git diff.
* Commit.
* Fixture snapshot.

Mọi secret trong báo cáo phải được thay bằng dạng mask, ví dụ:

```text
sk-****abcd
```

## 4. Không tự nhận test đã chạy

Chỉ báo cáo test pass khi lệnh thực sự đã được chạy và exit code bằng 0.

Phân biệt rõ:

* Unit test.
* Integration test.
* Fake-Hermes E2E.
* Backend black-box runtime.
* Frontend test.
* Real-Hermes integration.

Không dùng unit test để đại diện cho runtime integration.

## 5. Không dừng toàn bộ audit vì một test thất bại

Khi một test thất bại:

1. Ghi lệnh, exit code và lỗi.
2. Xác định các phần còn độc lập.
3. Tiếp tục hoàn thành các phần độc lập.
4. Sau đó quay lại sửa root cause.
5. Không che giấu hoặc xóa evidence thất bại.

Không chạy đồng thời nhiều full backend test suite dùng chung SQLite database.

## 6. Không refactor core trên diện rộng

Ưu tiên tái sử dụng và nối các module hiện có, bao gồm những module tương đương với:

* `dag_scheduler`
* `route_lock_service`
* `worktree_service`
* `supervisor`
* `recovery_service`
* `permission_profile`
* Hermes session bridge
* Provider gateway/router runtime
* Existing event bus/WebSocket infrastructure

Nếu tên hoặc vị trí file khác, phải tìm implementation thực tế trước khi sửa.

# PHASE 0 — PROVENANCE VÀ WORKTREE PRESERVATION

## 0.1. Ghi trạng thái ban đầu

Chạy và lưu toàn bộ output:

```bash
git status --short
git status --porcelain=v2
git branch --show-current
git rev-parse HEAD
git rev-parse --show-toplevel
git worktree list --porcelain
git diff --stat
git diff --name-status
git diff --cached --stat
git ls-files --others --exclude-standard
git log -10 --oneline --decorate
git remote -v
```

Xác minh:

```bash
git cat-file -t 9205dfa111301eb65cf1963dde89778e246dae5c
git merge-base --is-ancestor 9205dfa111301eb65cf1963dde89778e246dae5c HEAD
```

Nếu HEAD không còn bằng `9205dfa`, không reset. Ghi nhận actual HEAD và tiếp tục trên trạng thái thực tế.

## 0.2. Tạo artifact provenance

Tạo thư mục:

```text
artifacts/agent_workspace_orchestration_phase2/<UTC_TIMESTAMP>/
```

Tối thiểu gồm:

```text
commands.log
git_status_before.txt
git_porcelain_v2_before.txt
git_diff_stat_before.txt
tracked_changes_manifest.txt
untracked_files_manifest.txt
worktree_manifest.txt
starting_head.txt
environment.txt
```

Lưu patch local để phòng mất dữ liệu:

```bash
git diff --binary > artifacts/.../tracked_worktree_before.patch
git diff --cached --binary > artifacts/.../staged_worktree_before.patch
```

Không copy nội dung file nghi chứa secret vào artifact. Với file nghi chứa secret, chỉ ghi đường dẫn và trạng thái `REDACTED_SENSITIVE_FILE`.

## 0.3. Phân loại 19 modified và 21 untracked

Kiểm tra từng file và tạo bảng:

| Path | Git state | Category | Relevant | Secret risk | Generated | Action |
| ---- | --------- | -------- | -------: | ----------: | --------: | ------ |

Không được giả định tất cả file untracked đều là source.

Kiểm tra `.gitignore` và bổ sung rule cho:

* Runtime DB.
* SQLite WAL/SHM.
* Cache.
* Temporary worktree.
* Logs.
* Local `.env`.
* Secret material.
* Generated frontend artifacts.
* Python cache.
* Test output không cần version control.

Không ignore source, migration, test hoặc report cần theo dõi.

## 0.4. Secret scan

Tìm kiếm tối thiểu các pattern:

```text
api_key
secret
token
authorization
bearer
sk-
AIza
nvapi-
OPENAI_API_KEY
ANTHROPIC_API_KEY
GOOGLE_API_KEY
NVIDIA_API_KEY
OPENROUTER_API_KEY
```

Phân biệt:

* Field name hợp lệ.
* Placeholder.
* Test dummy.
* Secret thật.
* Plaintext persistence logic.

Không đưa giá trị tìm thấy vào báo cáo.

# PHASE A — SECURITY, MIGRATION VÀ PATH SAFETY

Phase A là gate bắt buộc. Không chạy live provider bằng credential thật trước khi Phase A pass.

## A1. API key encryption at rest

Hiện tại phải coi việc gán trực tiếp dạng sau là không đạt:

```python
provider.api_key = payload.api_key
```

Thiết kế một secret storage abstraction có versioning.

Yêu cầu:

1. Encryption key lấy từ environment hoặc secret store, không lưu trong cùng database.
2. Tên environment variable rõ ràng, ví dụ:

```text
WINDAGENT_SECRET_ENCRYPTION_KEY
```

3. Ciphertext có marker/version, ví dụ:

```text
enc:v1:<encoded-payload>
```

4. Dùng authenticated encryption.
5. Không tự viết thuật toán crypto.
6. Ưu tiên dependency crypto đáng tin cậy đã có trong project.
7. Nếu cần thêm dependency, cập nhật dependency lock/requirements đúng chuẩn dự án.
8. Hỗ trợ:

   * encrypt
   * decrypt
   * detect encrypted value
   * mask
   * key validation
9. Không bao giờ trả API key plaintext qua list/get/update response.
10. API update có thể nhận key mới nhưng response chỉ trả trạng thái và masked metadata.
11. Không log payload chứa API key.
12. Exception phải được redacted.
13. Test sử dụng deterministic test key hoặc fixture key riêng.
14. Production không được silently dùng hardcoded fallback key.
15. Khi encryption key thiếu:

* Không được lưu plaintext.
* Trả lỗi cấu hình rõ ràng cho thao tác cần secret.
* Các endpoint không cần secret vẫn có thể hoạt động khi hợp lý.

## A2. Migration dữ liệu hiện có

Dùng Alembic hoặc migration mechanism thực tế của repository.

Migration phải:

* Không phá dữ liệu.
* Nhận diện `NULL`, empty và already-encrypted values.
* Idempotent khi chạy lại ở mức application migration logic.
* Không ghi plaintext vào migration log.
* Có backup/rollback strategy.
* Không commit database local.
* Không tự động xóa key không giải mã được.
* Ghi lỗi theo provider ID đã mask, không ghi secret.

Nếu việc mã hóa dữ liệu cũ cần encryption key runtime, xây một safe migration command hoặc application migration step được document rõ ràng thay vì nhúng secret vào revision file.

## A3. Response masking

Audit mọi endpoint provider/model.

Bảo đảm API response không chứa:

```text
api_key
raw_secret
authorization header
encryption key
decrypted credential
```

Có thể trả:

```json
{
  "has_api_key": true,
  "api_key_masked": "****abcd"
}
```

Không trả encrypted ciphertext cho frontend.

## A4. Log redaction

Thêm redaction tập trung cho:

* HTTP request logging.
* Provider gateway errors.
* Router execution logs.
* Hermes bridge errors.
* Pydantic validation errors.
* Traceback context.
* Audit artifacts.

Test phải kiểm tra cả plaintext secret và ciphertext không xuất hiện trong user-facing response.

## A5. Workspace/path traversal guard

Tất cả đường dẫn do request, agent, plan hoặc tool cung cấp phải được resolve bên trong workspace root được phép.

Chặn:

* `../`
* Absolute path ngoài root.
* Windows drive escape.
* UNC path.
* Mixed slash.
* URL-encoded traversal.
* Symlink/junction escape.
* Case-normalization issue trên Windows.
* Empty root hoặc ambiguous root.
* Delete/cleanup ngoài managed worktree.

Tạo helper dùng chung thay vì kiểm tra rải rác.

Bổ sung test cho Windows và POSIX semantics ở mức có thể chạy trên CI.

## Phase A acceptance gate

Phase A chỉ pass khi:

* API key mới không xuất hiện plaintext trong DB.
* API key không xuất hiện trong response/log/artifact.
* Missing encryption key không dẫn tới plaintext fallback.
* Migration test pass.
* Traversal test pass.
* Existing provider/model contract không bị phá ngoài thay đổi có chủ đích.
* Focused security tests pass.

Nếu fail, verdict tối thiểu phải là:

```text
rejected_security_gate
```

# PHASE B — ROUTE LOCK VÀ FAILOVER THEO TURN

## B1. Route lock lifecycle

Mỗi conversation turn phải có route decision ổn định.

Khóa phải gắn tối thiểu với:

```text
conversation_id
turn_id
run_id
route_lock_id
selected_provider
selected_model
created_at
released_at
status
version
```

Luồng:

```text
turn accepted
→ acquire route lock
→ persist selected route
→ execute
→ failover theo policy được phép
→ finish/cancel/fail
→ release/finalize lock
```

Không giữ lock chỉ trong process memory nếu cần recovery.

## B2. Concurrency safety

Hai request đồng thời cho cùng conversation không được:

* Cùng sở hữu active turn lock.
* Tạo duplicate run.
* Ghi đè route decision.
* Chạy cùng plan hai lần ngoài chủ đích.

Dùng transaction, unique constraint, compare-and-set hoặc optimistic versioning phù hợp với schema hiện tại.

Không dùng check-then-insert không nguyên tử.

## B3. Same-model failover

Khi provider endpoint lỗi nhưng policy cho phép, thử failover sang route khác vẫn phục vụ cùng logical model hoặc equivalent deployment theo catalog.

Phải ghi:

```text
attempt
provider
model
error_class
retryable
latency
fallback_reason
result
```

Retry/failover phải có cap.

Không retry:

* Authentication failure.
* Invalid request.
* Safety/policy rejection.
* Missing model configuration.
* Non-retryable 4xx.

Không để failover làm thay đổi model giữa turn mà không ghi route transition.

## B4. Route lock tests

Tối thiểu:

* Acquire thành công.
* Duplicate acquire bị chặn.
* Release idempotent.
* Cancel giải phóng/finalize.
* Process restart đọc được persisted lock.
* Stale lock reconciliation.
* Same-model retry thành công.
* Non-retryable error không retry.
* Retry cap được tôn trọng.
* Hai concurrent requests không cùng execute.

# PHASE C — SUPERVISOR SPAWN VÀ CHAT → DAG

## C1. Xác định live entry point

Tìm endpoint thực tế nhận chat/message.

Không tạo endpoint song song nếu endpoint hiện có có thể mở rộng an toàn.

Trace live path hiện tại:

```text
HTTP message request
→ router/controller
→ Hermes/single-agent bridge
→ event bus/WebSocket
→ persistence
```

Ghi call graph trước và sau vào report.

## C2. Supervisor integration

Thay vì mọi message luôn đi thẳng vào single-agent bridge, thêm orchestration decision:

* Single-agent request vẫn có thể dùng fast path.
* Multi-step/multi-agent request tạo supervisor run.
* Supervisor tạo agent instances có ID ổn định.
* Supervisor tạo DAG hoặc execution plan.
* DAG được persist trước khi execution.
* Mỗi node liên kết được với:

  * conversation
  * turn
  * run
  * agent instance
  * parent node
  * dependency
  * status
  * timestamps
  * retry count
  * output/error reference

Không dùng heuristic khó kiểm thử để quyết định multi-agent trong giai đoạn đầu. Có thể dùng explicit request mode hoặc deterministic planner fixture cho E2E.

## C3. State machine

Định nghĩa trạng thái hợp lệ, ví dụ:

```text
created
queued
running
waiting_dependency
waiting_approval
succeeded
failed
cancel_requested
cancelled
recovering
orphaned
```

Kiểm soát transition. Không cho phép:

```text
succeeded → running
cancelled → running
failed → succeeded
```

trừ khi tạo retry attempt/run mới rõ ràng.

## C4. Event contract

Mọi event orchestration phải có envelope nhất quán:

```json
{
  "event_id": "...",
  "sequence": 1,
  "conversation_id": "...",
  "turn_id": "...",
  "run_id": "...",
  "agent_instance_id": "...",
  "event": "...",
  "timestamp": "...",
  "data": {}
}
```

Không bắt buộc `agent_instance_id` cho event cấp conversation, nhưng field/schema phải xử lý rõ.

Event sequence phải hỗ trợ recovery/deduplication sau này.

# PHASE D — RUN_PLAN, IDEMPOTENCY VÀ PARTIAL PERSISTENCE

## D1. Wire run_plan vào live supervisor path

Không chỉ unit-call `run_plan`.

Phải chứng minh request từ HTTP entry point thực sự đi đến:

```text
supervisor.spawn
→ DAG creation
→ run_plan
→ node execution
```

Dùng spy/instrumentation/test assertion để xác nhận.

## D2. concurrency_group

Các node cùng `concurrency_group` phải tuân thủ policy đã định nghĩa.

Xác định rõ semantics:

* Cùng group chạy tuần tự hay bị giới hạn concurrency.
* Khác group được chạy song song đến mức nào.
* Global cap.
* Per-conversation cap.
* Per-provider cap nếu liên quan quota.

Test phải deterministic, không phụ thuộc timing mong manh.

## D3. Idempotency

Mỗi message/turn cần idempotency key.

Các request duplicate phải:

* Trả về run hiện có, hoặc
* Bị reject có chủ đích.

Không tạo duplicate:

* Conversation turn.
* DAG.
* Node run.
* Hermes run.
* Worktree.
* Usage/quota accounting.

Idempotency phải được enforce ở persistence layer, không chỉ dictionary memory.

## D4. Partial persistence

Sau mỗi node hoặc meaningful event:

* Persist status.
* Persist partial output/reference.
* Persist timestamps.
* Persist retry attempt.
* Persist error class đã sanitize.
* Commit transaction hợp lý.

Khi process chết giữa run, recovery phải biết:

* Node nào hoàn tất.
* Node nào đang chạy.
* Node nào chưa chạy.
* Node nào có thể retry.
* Lock nào còn active.
* Hermes run mapping nào còn tồn tại.

## D5. Failure semantics

Phân biệt:

* Node failure.
* Provider failure.
* Hermes failure.
* Planner failure.
* Persistence failure.
* User cancel.
* Process crash.
* Dependency failure.
* Permission denial.

DAG có thể `partial_success` nếu policy cho phép, nhưng phải deterministic và được test.

# SQLITE VÀ TEST ISOLATION

Không tiếp tục bỏ full backend suite chỉ vì SQLite lock mà không sửa test infrastructure.

Thực hiện một trong các chiến lược phù hợp:

* DB tạm riêng theo test session.
* DB riêng theo pytest worker.
* Unique DB path bằng UUID.
* Correct in-memory shared connection.
* WAL và busy timeout cho test contention có chủ đích.
* Explicit connection cleanup.

Không cho hai background suites dùng chung `_DB_PATH`.

Bổ sung test chứng minh:

* Hai test process/session không tranh cùng DB ngoài chủ đích.
* Transaction rollback/cleanup đúng.
* Temporary DB được xóa sau test.
* WAL/SHM không bị commit.

# E2E VỚI FAKE HERMES

Fake Hermes phải deterministic và hỗ trợ ít nhất:

* Start run.
* Stream event.
* Complete run.
* Fail retryable.
* Fail non-retryable.
* Delay.
* Cancel.
* Approval.
* Disconnect/reconnect simulation nếu infrastructure hiện có hỗ trợ.
* Duplicate response/idempotency scenario.

Tạo E2E bắt đầu từ HTTP/WebSocket public interface, không gọi trực tiếp service nội bộ để thay thế E2E.

Kịch bản bắt buộc:

## Scenario 1 — Successful orchestration

```text
create conversation/session
→ send orchestration message
→ supervisor spawned
→ DAG persisted
→ route lock acquired
→ planner node succeeds
→ worker node succeeds
→ partial events received
→ run succeeds
→ lock finalized/released
```

Assert database và event sequence.

## Scenario 2 — Retryable provider failure

```text
first route fails retryably
→ same-model failover
→ second route succeeds
→ one logical turn
→ no duplicate DAG
→ attempts persisted
```

## Scenario 3 — Duplicate request

Gửi cùng idempotency key hai lần.

Assert chỉ có:

* Một turn.
* Một run.
* Một DAG.
* Một logical Hermes execution.

## Scenario 4 — Cancel during execution

```text
run active
→ user cancel
→ Hermes stop requested
→ task cancelled
→ partial state retained
→ run cancelled
→ route lock finalized
```

Không chấp nhận chỉ đổi status mà background execution vẫn tiếp tục.

## Scenario 5 — Process/recovery simulation

Persist run ở trạng thái active, recreate application/service container, chạy recovery.

Assert:

* Completed node không chạy lại.
* Retryable in-flight node được reconcile.
* Stale lock được xử lý.
* Duplicate external run không được tạo.

## Scenario 6 — Secret redaction

Dùng dummy API key có chuỗi dễ nhận diện.

Assert dummy secret không xuất hiện trong:

* DB plaintext query.
* HTTP response.
* WebSocket event.
* Logs.
* Exception.
* Report artifact.

# BLACK-BOX RUNTIME

Sau khi focused tests pass, khởi động backend bằng entry command thực tế của repository.

Không giả định script; đọc README/package config/task runner trước.

Kiểm tra các port audit đã nhắc:

```text
backend: 8765
frontend/dev server: 1420
```

Nếu cấu hình thực tế khác, dùng cấu hình repository và ghi rõ.

Black-box backend test phải dùng HTTP/WebSocket qua socket thật, không dùng TestClient.

Tối thiểu kiểm tra:

```text
health
create session/conversation
send message
observe orchestration events
read persisted run/DAG state qua API phù hợp
cancel hoặc complete
verify final state
```

Ưu tiên fake Hermes server chạy thật trên local socket cho deterministic E2E.

Real Hermes chỉ là supplemental test khi:

* Service được cấu hình.
* Credential an toàn.
* Không ghi secret vào log.
* Không phát sinh chi phí ngoài kiểm soát.

Nếu real Hermes không khả dụng, verdict có thể pass fake-Hermes vertical slice nhưng phải ghi:

```text
real_hermes_integration_unverified
```

Không được ghi `fully production verified`.

# FRONTEND SCOPE

Không thực hiện redesign lớn trong lần này.

Chỉ sửa frontend khi cần để:

* Không bị phá bởi schema mới.
* Truyền/nhận `agent_instance_id`.
* Hiển thị trạng thái orchestration cơ bản.
* Giữ compatibility với single-agent session.

Chạy focused frontend tests cho file bị ảnh hưởng.

Nếu frontend không thay đổi, vẫn chạy typecheck/build hoặc test phù hợp khi môi trường cho phép.

Không xóa `AgentWorkspace` hoặc làm UI browser/inspector toàn phần trong sprint này trừ khi nó trực tiếp block vertical slice.

Các nhóm frontend browser, inspector, i18n và dead workspace cleanup phải được để lại trong roadmap tiếp theo nếu core runtime chưa pass.

# TEST ORDER

Chạy tuần tự, tránh SQLite contention:

1. Static/import/compile checks.
2. Security and migration focused tests.
3. Route-lock tests.
4. Supervisor/DAG tests.
5. Run-plan/idempotency tests.
6. Fake-Hermes E2E.
7. Existing Phase 2–9 focused tests.
8. Full backend test suite với DB isolation đã sửa.
9. Frontend focused tests.
10. Frontend typecheck/build.
11. Backend black-box runtime.
12. Optional real-Hermes smoke test.

Mỗi lệnh phải được append vào:

```text
artifacts/.../commands.log
```

Ghi:

```text
command
working directory
start timestamp
end timestamp
exit code
summary
```

Không chạy hai full test suite đồng thời.

# GIT STRATEGY

## 1. Branch

Xác minh branch hiện tại.

Nếu `feat/phase-1-baseline` chỉ tồn tại local, push branch sau khi có commit sạch và an toàn.

Sau khi checkpoint các standalone orchestration components hiện có, tạo hoặc chuyển sang:

```text
feat/phase-2-runtime-orchestration
```

Không force push.

Không rewrite lịch sử remote.

## 2. Commit structure

Ưu tiên các commit nhỏ, audit được:

```text
chore(orchestration): checkpoint audited standalone foundation
fix(security): encrypt provider credentials and redact secrets
feat(orchestration): wire chat supervisor dag and route lock
feat(orchestration): add idempotent run plan persistence
test(orchestration): add fake hermes vertical slice e2e
docs(orchestration): add phase 2 runtime evidence report
```

Chỉ tạo checkpoint commit đầu tiên nếu:

* Đã phân loại file.
* Không có generated noise.
* Không có secret thật.
* Code liên quan có thể import.
* Commit message không tuyên bố live integration đã hoạt động.

Có thể gộp commit nếu thay đổi phụ thuộc chặt, nhưng không tạo một commit khổng lồ không thể review.

## 3. Push verification

Sau mỗi push cuối:

```bash
git rev-parse HEAD
git status --short
git ls-remote origin refs/heads/feat/phase-2-runtime-orchestration
```

Remote SHA phải bằng local SHA.

Không báo `pushed: yes` nếu chưa xác minh.

# REQUIRED ARTIFACTS

Trong:

```text
artifacts/agent_workspace_orchestration_phase2/<UTC_TIMESTAMP>/
```

phải có tối thiểu:

```text
commands.log
environment.txt
starting_head.txt
final_head.txt
git_status_before.txt
git_status_after.txt
tracked_changes_manifest.txt
untracked_files_manifest.txt
changed_files_final.txt
migration_test.log
security_test.log
route_lock_test.log
supervisor_dag_test.log
run_plan_test.log
fake_hermes_e2e.log
full_backend_test.log
frontend_test.log
frontend_build.log
black_box_runtime.log
runtime_event_trace.jsonl
database_state_summary.json
secret_redaction_audit.txt
vertical_slice_manifest.json
final_verdict.json
```

Không commit artifact dung lượng lớn, runtime DB hoặc secret-bearing logs. Chỉ commit report và artifact nhỏ/an toàn phù hợp policy repository.

# REQUIRED REPORT

Tạo:

```text
reports/agent_workspace_orchestration_phase2_runtime.md
```

Report phải evidence-first và có các phần:

1. Final verdict.
2. Git provenance.
3. Starting and final HEAD.
4. Branch and remote verification.
5. Worktree before/after.
6. File classification.
7. Architecture before.
8. Architecture after.
9. Security implementation.
10. Migration design.
11. Route lock lifecycle.
12. Supervisor and DAG integration.
13. Run-plan integration.
14. Idempotency.
15. Partial persistence.
16. Fake-Hermes E2E evidence.
17. Black-box runtime evidence.
18. Full backend results.
19. Frontend results.
20. Failures and unresolved issues.
21. Remaining roadmap E–I.
22. Production-readiness assessment.
23. Exact acceptance gate table.

Không đưa secret vào report.

# ACCEPTANCE GATES

## Gate 1 — Provenance

Pass khi:

* Worktree ban đầu được ghi nhận.
* Modified/untracked files được phân loại.
* Không mất thay đổi.
* Final commits có thể truy vết.
* Remote SHA bằng local SHA.

## Gate 2 — Security

Pass khi:

* Provider secret được encrypted at rest.
* Không có plaintext fallback.
* Không leak qua API/log/event/artifact.
* Traversal guard pass.
* Migration pass.

## Gate 3 — Runtime wiring

Pass khi public chat/message entry point thực sự gọi:

```text
supervisor
→ DAG
→ route lock
→ run_plan
```

Unit test gọi service trực tiếp không đủ.

## Gate 4 — Persistence and concurrency

Pass khi:

* Idempotency được enforce.
* Duplicate request không duplicate run.
* Partial state survive service recreation.
* Concurrent turn bị serialize hoặc reject đúng policy.
* Lock lifecycle deterministic.

## Gate 5 — Fake-Hermes E2E

Pass khi sáu scenario bắt buộc pass qua public HTTP/WebSocket interface.

## Gate 6 — Black-box runtime

Pass khi backend chạy trên socket thật và một orchestration flow hoàn tất hoặc cancel đúng.

Nếu service không thể khởi động do lỗi code/config thuộc repository, gate fail.

Nếu external real Hermes không khả dụng nhưng fake-Hermes socket runtime pass, ghi rõ giới hạn nhưng không tự động fail Gate 6.

## Gate 7 — Regression

Pass khi:

* Focused tests pass.
* Full backend suite được chạy với DB isolation.
* Không có regression nghiêm trọng trong live single-agent Hermes path.
* Frontend typecheck/build hoặc focused tests pass nếu bị ảnh hưởng.

## Gate 8 — Git completion

Pass khi:

* Commit được tạo.
* Push thành công.
* Remote SHA xác minh.
* Worktree sạch, ngoại trừ thay đổi unrelated đã được ghi nhận từ đầu và cố ý giữ nguyên.

# VERDICT RULES

Chỉ dùng một trong các verdict sau:

## `accepted_phase2_runtime_vertical_slice`

Chỉ được dùng khi:

* Gate 1–8 đều pass.
* Fake-Hermes E2E pass.
* Black-box socket runtime pass.
* Changes committed and pushed.
* Remote SHA verified.

## `partial_phase2_runtime_vertical_slice`

Dùng khi:

* Một phần wiring chạy.
* Một hoặc nhiều core gate fail.
* Không được gọi là accepted.

## `blocked_environment_runtime`

Chỉ dùng khi code/tests cần thiết pass nhưng black-box runtime bị block bởi dependency môi trường thực sự nằm ngoài repository.

Phải có evidence chứng minh đây không phải lỗi code/config của WindAgent.

## `rejected_security_gate`

Dùng khi secret encryption/redaction/traversal chưa đạt.

## `rejected_integration_gate`

Dùng khi modules vẫn chỉ standalone hoặc public live path chưa đi qua orchestration.

## `rejected_regression_gate`

Dùng khi implementation mới phá existing runtime hoặc full regression suite.

Không được dùng verdict accepted nếu chỉ có 33 focused tests hoặc TestClient tests.

# FINAL RESPONSE FORMAT

Kết thúc bằng đúng cấu trúc sau:

```text
FINAL VERDICT:
<one allowed verdict>

PRIMARY CONCLUSION:
<one concise paragraph>

GIT:
repository:
starting branch:
final branch:
starting HEAD:
final HEAD:
commit(s):
pushed:
remote SHA == local:
worktree clean:
unrelated pre-existing changes preserved:

PROVENANCE:
modified files before:
untracked files before:
files classified:
secret-bearing files found:
data loss:
checkpoint created:

SECURITY:
api_key encrypted at rest:
encryption scheme/version:
plaintext fallback:
response masking:
log redaction:
migration:
traversal guard:
security gate:

RUNTIME WIRING:
public entry point:
supervisor invoked:
DAG persisted:
route lock acquired:
run_plan invoked:
partial persistence:
idempotency:
recovery:
runtime gate:

E2E:
fake Hermes:
black-box socket runtime:
real Hermes:
successful orchestration:
retryable failover:
duplicate request:
cancel:
recovery simulation:
secret redaction scenario:

TESTS:
security:
migration:
route lock:
supervisor/DAG:
run_plan:
fake-Hermes E2E:
focused backend:
full backend:
frontend focused:
frontend build/typecheck:
black-box:
failed tests:

ARTIFACTS:
artifact directory:
report:
runtime trace:
final manifest:

CHANGED FILES:
<complete list>

REMAINING RISKS:
<numbered, evidence-based list>

NEXT ROADMAP:
E worktree lifecycle
F WebSocket multiplex and recovery
G normalized frontend state
H browser/inspector/i18n/dead UI cleanup
I chaos and production hardening
```

# EXECUTION PRIORITY

Thứ tự ưu tiên tuyệt đối:

```text
Preserve worktree
→ remove plaintext secret risk
→ migrations/path safety
→ chat-supervisor-DAG-route-lock-run_plan vertical slice
→ idempotency/partial persistence
→ fake-Hermes E2E
→ black-box runtime
→ regression
→ commit/push/report
```

Không ưu tiên UI, code cleanup hoặc architecture redesign trước core vertical slice.

Mục tiêu của lần thực hiện này không phải “có thêm nhiều module”, mà là chứng minh bằng evidence rằng các module orchestration hiện có đã được nối vào một live request path hoạt động end-to-end.
