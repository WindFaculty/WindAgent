Phase 0 — Chốt kiến trúc đích và baseline
Mục tiêu: tránh tiếp tục phát triển hai UI/runtime song song.
Viết ADR xác định các aggregate chính: Conversation, ParentTask, AgentInstance, AgentSession, TaskPlanVersion, TaskNodeRun, RouteLock, ToolExecution, Worktree.
Chốt một đường chạy production duy nhất:
Conversation WS/API
  → Orchestrator
  → immutable plan + DAG
  → AgentInstance/AgentSession
  → route lock + provider execution
  → worker/runtime/tool
  → durable events + recovery
Quyết định MultiAgentWorkspace là UI chính; AgentWorkspacePage chỉ được giữ tạm trong feature flag hoặc thay thế.
Lập mapping dữ liệu từ schema V2 hiện tại sang schema multi-agent.
Đưa toàn bộ test vào cấu hình CI có thư mục tạm ghi được; full suite phải chạy không timeout do môi trường.
Exit gate:
ADR được duyệt.
Không còn hai API contract mâu thuẫn cho workspace.
Có test matrix gắn từng G1.1…G9.7 với test cụ thể.
Phase 1 — Migration, toàn vẹn dữ liệu và security nền tảng
Phạm vi: G1.1, G1.2, G1.3, G2.3, G9.3, G9.4, G9.5.
Thêm Alembic, thay create_tables trong runtime bằng quy trình migration rõ ràng.

Tạo migration baseline và migration chuyển đổi từ dữ liệu V2 hiện có.

Tạo/chuẩn hóa các constraint:
FK và index từ ParentTask/AgentInstance sang Conversation.
unique AgentSession.windagent_session_id.
unique route lock active theo scope.
unique idempotency key cho tool execution.
version/CAS cho các state mutation.

Chuyển task plan sang immutable version:
Bảng task_plan_versions.
Mỗi edit tạo row/version mới.
Run đang chạy pin vào version cũ; plan mới chỉ áp dụng cho run mới hoặc qua replan có chủ đích.

Mã hóa provider secret bằng AES-GCM/KMS key hợp lệ; bỏ fallback key cố định.

API chỉ trả metadata credential, tuyệt đối không trả secret ciphertext hay plaintext.

Dùng một redact_before_persist() ở mọi điểm ghi command, tool argument, event và audit log.

Validate workspace_root bằng resolve() + kiểm tra nằm trong repository root; traversal/symlink escape trả 400.

Bật WAL và busy_timeout cho cả async DatabaseManager, không chỉ sync factory.

Exit gate:
alembic upgrade head tạo DB mới hoàn chỉnh.
alembic downgrade base hoạt động trên DB test.
Upgrade từ DB V2 fixture không mất dữ liệu cần giữ.
Secret trong DB có prefix ciphertext; API GET không lộ key.
workspace_root=../../etc bị từ chối.
8 writer song song không có database is locked.
Phase 2 — Orchestrator và multi-session supervisor chạy thật
Phạm vi: G3.1, G3.2, G3.3 và phần control-plane của G2.1.
Tạo OrchestratorService là điểm vào duy nhất cho conversation.

Khi nhận mục tiêu từ user:
tạo/reuse orchestrator session;
tạo ParentTask;
tạo immutable task plan;
spawn một AgentInstance + AgentSession + AgentRun cho từng node.

Không cho frontend tự chọn agent role để tạo session runtime.

Implement stop theo agent_instance_id: cancel agent B không ảnh hưởng A/C.

Persist runtime locator/Hermes run ID để boot có thể reattach.

Startup gọi reattach cho run còn sống; chạy orphan policy cho run không còn owner.

Exit gate:
Một request tạo hai sub-agent độc lập, có session/run/event tách biệt.
Stop B không làm A/C dừng.
Restart tái tạo supervisor registry từ DB.
Phase 3 — Route lock và same-model failover trên đường chạy thật
Phạm vi: G2.1, G2.2.
Trước mỗi turn, OrchestratorService hoặc worker phải acquire/reuse route lock theo scope: conversation, parent task hoặc agent session.

Persist routing_snapshot vào run/turn, gồm canonical model, binding, policy version và lock ID.

Gọi EndpointExecutionCoordinator thật sự thay vì chỉ giữ nó như library.

Khi 429/5xx/network error:
ghi RouteAttempt;
cooldown binding lỗi;
chỉ chọn binding cùng canonical_model_id;
dừng khi hết endpoint tương đương, không fallback cross-model.

Bổ sung dashboard/audit endpoint read-only cho lock và attempts.

Exit gate:
Inject 429 từ provider A, provider B tiếp tục run.
Canonical model trước/sau failover không đổi.
Có đúng hai RouteAttempt; audit snapshot truy vết được.
Phase 4 — Immutable plan, DAG scheduler, idempotency và CAS
Phạm vi: G4.1, G4.2, G4.3, G9.1, G9.6.
Nối plan execution với scheduler production; không gọi WorkflowEngine chỉ trong test.

Persist node state, dependency state và retry state; không phụ thuộc _active_runs in-memory.

Enforce fan-out/fan-in từ task graph version đã pin.

Thêm concurrency_group vào node/run:
lock bền vững theo group/worktree;
tối đa một coding task dùng cùng worktree;
release lock khi terminal.

Tool idempotency phải xảy ra trước side effect:
reserve ToolExecution bằng unique idempotency key;
chỉ claimant đầu tiên được chạy tool;
retry đọc kết quả đã có hoặc resume theo trạng thái.

Chuẩn hóa state machine: cancel có precedence rõ ràng, completion dùng CAS/version/fencing token.

Retry dùng capped exponential backoff + jitter + max attempts; lưu lần retry kế tiếp để recovery tiếp tục đúng.

Exit gate:
A xong → B/C song song → D chỉ chạy sau khi B/C xong.
Hai node cùng group bị serialize.
Interrupt/retry không chạy tool side effect hai lần.
Stop trước completion luôn kết thúc cancelled.
Phase 5 — Git worktree lifecycle
Phạm vi: G5.1, G5.2, G5.3.
Thay helper tạo thư mục bằng git worktree add thật cho coding agent.

Mỗi coding agent có branch/worktree riêng và workspace_root được lấy từ service, không nhận tùy ý từ client.

Research/browser agent không nhận worktree.

Khi cancel:
stop runtime;
quarantine output nếu cần;
remove worktree;
xóa branch theo policy.

Khi boot:
đối chiếu DB, git worktree list và runtime active;
reattach worktree còn sống;
dọn worktree/branch orphan theo quarantine policy.

Exit gate:
Hai coding agent có hai path và branch khác nhau.
Main worktree không bị sửa trực tiếp.
Cancel dọn đúng worktree/branch.
Crash fixture được reconcile khi restart.
Phase 6 — Conversation WebSocket, audit stream và full recovery
Phạm vi: G6.1, G6.2, G6.3, G6.4, G7.1, G9.2.
Thay socket per-session bằng /ws/conversations/{conversation_id}.

Event envelope bắt buộc có:
conversation_id
agent_instance_id
agent_session_id
sequence monotonic per conversation
event ID/idempotency metadata

Server replay theo cursor conversation; client dùng đúng một socket cho conversation.

Giữ exponential backoff hiện có, thêm test deterministic cho cap/jitter/replay.

Trong stream exception, lưu PartialArtifact ở audit_only; transcript không nhận partial assistant message.

Recovery boot thực hiện theo thứ tự:
leader lease;
reclaim lease/reattach live runtime;
stop runtime orphan;
resume DAG từ persisted node state;
reconcile route locks;
reconcile worktree;
publish pending approvals.

Exit gate:
Một socket nhận event A/B/C, không lẫn event nhờ agent_instance_id.
Kill stream giữa token tạo partial audit artifact nhưng transcript sạch.
Restart giữa DAG tiếp tục node còn dang dở.
Orphan Hermes run nhận stop command.
Phase 7 — Hoàn thiện UI multi-agent, không mock
Phạm vi: G8.1, G8.2, G8.3, G8.4 và phần UI của G7.1.
Mount MultiAgentWorkspace làm workspace chính; gỡ AgentWorkspace.tsx và các import/dead flow.
Chuyển normalized store sang:
conversations[id]
agents[agent_instance_id]
sessions[agent_session_id]
events[agent_instance_id]
taskNodes[plan_version_id]
UI ba cột với nhãn tiếng Việt:
“Agent điều phối”
“Sub-agents”
“Công việc hiện tại”

Current Task dùng compact task view, không phải mock graph.

Inspector hiển thị model, provider/binding, current task, permission profile, tool đang chạy, worktree và route lock.

Browser panel chỉ hiển thị browser session/screenshot live của agent đã chọn; nếu agent không có browser runtime thì hiển thị trạng thái “không có browser”, không mock “Awesome App”.

Bỏ toàn bộ fallback progress/terminal giả trong workspace.

Exit gate:
Chọn A/B đổi terminal, browser, inspector theo đúng agent.
Không còn string/mock component “Awesome App”.
Không còn import AgentWorkspace.
UI test xác nhận events không merge chéo agent.
Phase 8 — E2E, chaos, security verification
Phạm vi: G9.7 và xác minh lại toàn bộ roadmap.
Tạo fake Hermes/provider/runtime có thể điều khiển lỗi và crash. Các E2E bắt buộc:
Orchestrator tạo parent task + DAG.
Spawn sub-agent và event isolation.
Fan-out/fan-in + concurrency group.
Coding worktree isolation và cancel cleanup.
429 failover cùng canonical model.
Partial stream audit-only.
Stop/completion race.
Restart ở giữa DAG, với pending approval và orphan runtime.
Conversation socket reconnect/replay không duplicate.
Secret redaction, API key encryption, workspace traversal.
SQLite WAL với parallel writer.
Exit gate:
Tất cả acceptance test G1.1–G9.7 xanh trong CI.
Không còn test chỉ chứng minh module riêng lẻ cho các feature production-critical.
Báo cáo coverage chỉ ra test nào chứng minh từng hạng mục roadmap.
Phase 9 — Rollout và rollback an toàn
Backup DB trước migration; rehearsal upgrade/downgrade trên bản copy production.

Release bằng feature flag:
schema + dual-read;
shadow orchestration;
internal users;
full activation.

Theo dõi: route failover rate, duplicate tool execution, orphan worktree count, WS reconnect rate, recovery duration, database lock errors.

Rollback application chỉ khi migration có backward-compatible path; dữ liệu immutable plan và audit không được xóa.