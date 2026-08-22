# Prompt — Phase 16 Certification Repair Round 2

Tiếp tục dự án **WindAgent — Architecture V3 Optimization & Hardening**.

Mục tiêu của round này **không phải refactor kiến trúc thêm**. Implementation hiện đã ở trạng thái tốt. Nhiệm vụ duy nhất là sửa **certification authority + evidence quality** để Phase 16 chỉ PASS khi toàn bộ requirement trong `ban_ke_hoach_v1.md` thực sự được kiểm chứng.

## 0. Baseline

Implementation candidate hiện tại:

```text
e481f33f502a551051bd30c43b5d5b9ae39cd892
```

Evidence commit hiện tại:

```text
8fb3d4e65aa1889af2e5e6b9778b72c7966b6e31
```

Evidence hiện tuyên bố:

```text
ARCHITECTURE_V3_OPTIMIZED_AND_CERTIFIED
```

nhưng independent review kết luận:

```text
IMPLEMENTATION_CANDIDATE = STRONG
CERTIFICATION_AUTHORITY = INCOMPLETE
PHASE_16 = CERTIFICATION_REPAIR_REQUIRED
```

Không rollback implementation tốt hiện tại.

Không mở thêm feature.

Không redesign.

Không sửa architecture checker chỉ để làm xanh.

Không giảm gate.

Không hard-code PASS.

---

# 1. Vai trò

Codex là:

```text
Lead reviewer
Certification authority reviewer
Planner
Independent verifier
```

OpenCode worker thực hiện các patch nhỏ nếu skill khả dụng.

Codex phải:

1. đọc requirement;
2. inspect current code;
3. xác định root cause;
4. giao patch nhỏ cho worker;
5. review diff;
6. chạy verification độc lập;
7. reject mọi patch làm test/gate yếu đi.

Không cho worker tự tuyên bố Phase 16 PASS.

---

# 2. Source of truth

Đọc trước:

```text
ban_ke_hoach_v1.md

scripts/certify_architecture_v3_final.py
scripts/check_architecture_v3.py

tests/architecture/test_architecture_v3_phase16.py
tests/contracts/test_v3_vertical_lifecycle_real.py
tests/regression/test_security_fail_closed.py

.github/workflows/ci.yaml

pyproject.toml
package.json
apps/web/package.json
apps/desktop/package.json
```

Đọc evidence hiện tại:

```text
artifacts/architecture_v3/phase_16/
├── CERTIFICATION_VERDICT.md
├── phase_16_verdict.json
├── phase_16_certification_report.json
├── gate_matrix.json
├── gate_evidence.json
└── blockers.json
```

Không chỉnh evidence trước khi sửa certification logic.

---

# 3. Xác nhận baseline

Chạy:

```bash
git rev-parse HEAD
git branch --show-current
git status --short
git log -5 --oneline
```

Nếu HEAD đang ở evidence commit:

```text
8fb3d4e...
```

hãy xác định implementation parent:

```text
e481f33...
```

Không sửa trực tiếp evidence commit như implementation candidate.

Tạo repair từ code hiện tại theo workflow đang dùng trong repo.

---

# 4. Blocker A — sửa G12 hard-coded PASS

Hiện `scripts/certify_architecture_v3_final.py` có logic tương đương:

```python
gate_results["G12_DOCS"] = "PASS"
```

Đây là false certification.

Phải thay bằng executable evidence.

## G12 phải chứng minh tối thiểu

* Architecture V3 naming consistency.
* Không còn canonical docs quảng bá Architecture V2 là current architecture.
* Version references quan trọng không conflict.
* Required architecture docs/artifacts tồn tại.
* Không có stale final verdict mâu thuẫn với candidate hiện tại.
* Phase 0–15 evidence không bị thiếu.
* Phase 16 evidence producer duy nhất là certification script.

Có thể xây dedicated function:

```python
run_docs_consistency_checks()
```

Trả:

```text
PASS / FAIL
evidence
violations
```

Không được:

```python
return True
```

không có check.

Nếu docs không nhất quán:

```text
G12_DOCS = FAIL
```

---

# 5. Blocker B — sửa G9 API Isolation

Hiện G9 gần như chỉ kiểm tra:

```text
apps/api/.../composition/container.py exists
```

Điều đó không đủ.

G9 phải có executable architecture test chứng minh:

```text
API process
    ↓
application services
    ↓
ports

API MUST NOT:
- directly execute tools
- directly own Worker pipeline
- instantiate ProductionWorker
- execute task-runtime adapters trực tiếp
- own durable task claiming
- bypass application boundary
```

## Cách làm

Ưu tiên static architecture test + dependency/caller test.

Ví dụ dedicated test:

```text
tests/architecture/test_phase16_api_isolation.py
```

hoặc mở rộng suite hiện có.

Phải scan production API package.

Không dùng:

```text
file exists => PASS
```

Certification script phải chạy dedicated test này.

G9 chỉ PASS khi test exit code = 0.

---

# 6. Blocker C — sửa G10 Worker Pipeline

Hiện G10 dùng một nhóm integration tests không trực tiếp chứng minh full worker lifecycle.

G10 cần executable evidence cho:

```text
claim
→ lease
→ fencing
→ prepare
→ execute
→ validate
→ finalize
→ persist result
→ event/outbox
→ reconcile
→ release lease
```

Tìm các test hiện có trước.

Không viết duplicate test nếu repo đã có coverage tốt.

Có thể gom các suite hiện hữu thành canonical worker verification command.

Ví dụ:

```text
worker recovery
transactional finalization
lease/fencing
queue
outbox
pipeline
```

Certification script phải chạy chúng.

Không dùng:

```python
G10 = ok_generic_integration
```

nếu suite không chứng minh đúng Worker pipeline.

---

# 7. Blocker D — G13 phải phản ánh full Phase 16 matrix

Đây là blocker quan trọng nhất.

`ban_ke_hoach_v1.md` yêu cầu:

```text
architecture checker
ruff
pytest unit
pytest architecture
pytest contract
SQLite integration
PostgreSQL integration
API smoke
Worker recovery
queue/fencing tests
outbox tests
WebSocket replay
web tests
desktop tests
typecheck
build
```

Certification script phải có explicit entry cho từng mục.

Không được chỉ:

```python
all(suite_results.values())
```

trong khi thiếu suite bắt buộc.

## Tạo canonical matrix

Ví dụ:

```python
required_matrix = {
    "architecture_checker": ...,
    "ruff": ...,
    "pytest_unit": ...,
    "pytest_architecture": ...,
    "pytest_contract": ...,
    "sqlite_integration": ...,
    "postgres_integration": ...,
    "api_smoke": ...,
    "worker_recovery": ...,
    "queue_fencing": ...,
    "outbox": ...,
    "websocket_replay": ...,
    "web_tests": ...,
    "desktop_tests": ...,
    "typecheck": ...,
    "build": ...,
}
```

Sau đó:

```text
G13 PASS
```

chỉ khi **tất cả required matrix entry PASS**.

Nếu một entry không thể chạy:

```text
BLOCKED
```

không được coi là PASS.

---

# 8. PostgreSQL là hard gate

Không dùng SQLite thay PostgreSQL.

Tìm canonical PostgreSQL profile từ:

```text
docker-compose
CI
test fixtures
environment docs
pyproject markers
```

Nếu có Docker/Postgres:

chạy PostgreSQL integration thực.

Nếu môi trường hiện tại không có Postgres và không thể provision:

```text
POSTGRES_INTEGRATION = BLOCKED_ENVIRONMENT
PHASE_16 = BLOCKED
```

Không mock PostgreSQL.

Không skip rồi PASS.

Evidence phải ghi:

```text
engine
version
connection/profile
tests
exit code
```

Không ghi password.

---

# 9. Web + Desktop verification

Certification phải chạy chính xác command của repo.

Đừng đoán.

Đọc:

```text
package.json
apps/web/package.json
apps/desktop/package.json
.github/workflows/ci.yaml
```

Tìm canonical commands cho:

```text
web tests
desktop tests
typecheck
web build
desktop build
```

Nếu command dùng npm:

chạy command thật.

Nếu dùng pnpm/yarn:

dùng đúng package manager của repo.

Evidence phải chứa:

```text
command
exit_code
status
```

---

# 10. API smoke

Thêm hoặc sử dụng test hiện có chứng minh API V3 boot được và canonical endpoints hoạt động.

Tối thiểu:

```text
health
series create/read
episode create/read
run submit
```

Không cần chạy full vertical lại nếu contract suite đã làm, nhưng API smoke phải có gate riêng.

Không chỉ import FastAPI app.

---

# 11. Worker recovery / queue / fencing / outbox riêng biệt

Đừng gom tất cả thành một generic pytest integration.

Certification report cần nhìn thấy rõ:

```text
worker_recovery = PASS
queue_fencing = PASS
outbox = PASS
```

Mỗi entry phải map tới executable tests.

Ví dụ:

```text
worker restart
worker killed
lease expiry
lease takeover
stale result rejection
duplicate command
outbox atomic persistence
outbox replay/dedup
```

---

# 12. WebSocket replay

G8 hiện khá tốt, giữ lại.

Nhưng certification matrix phải có explicit:

```text
websocket_replay = PASS
```

với:

```text
disconnect
after_sequence
SQL replay
catch-up
live continuation
duplicate suppression
sequence ordering
```

Không dùng proxy từ architecture checker.

---

# 13. Vertical E2E phải được đưa vào certification

Hiện certification chạy:

```text
test_phase16_e2e_certification.py
```

nhưng phải chạy thêm:

```text
tests/contracts/test_v3_vertical_lifecycle_real.py
```

Đây là vertical quan trọng.

Thêm nó thành dedicated suite:

```text
v3_vertical_real
```

Nếu fail:

```text
G13 FAIL
```

---

# 14. Sửa claim về Model Router

Trong:

```text
tests/contracts/test_v3_vertical_lifecycle_real.py
```

hiện `FixtureModelPort` được inject trực tiếp vào `StudioRuntimeAdapter`.

Vì vậy không được claim:

```text
production Model Router invoked
real provider routing proven
```

trừ khi test thật sự đi qua router.

Có hai lựa chọn.

## Option A — thêm router integration thật

Canonical path:

```text
Story Handler
→ ModelExecutionPort
→ Router
→ routing rule
→ selected model/provider
→ deterministic provider adapter
→ fake transport
```

Không network thật.

Nếu làm được với patch nhỏ, thực hiện.

## Option B — đổi claim cho đúng

Nếu integration router riêng đã có suite khác:

vertical test chỉ claim:

```text
ModelExecutionPort invoked
deterministic model fixture used
```

Và certification kết hợp:

```text
vertical E2E PASS
+
provider routing integration PASS
```

để chứng minh tổng thể.

Không overclaim.

---

# 15. Sửa lock immutability test

Hiện test dùng wrong hash sau lock.

Wrong hash vốn invalid ngay cả trước lock, nên chưa chứng minh domain immutability.

Phải test operation:

```text
valid before lock
invalid because locked
```

Tìm canonical mutation:

```text
derive revision
rewrite screenplay
update screenplay
create revision
```

Sau lock:

```text
perform valid-form mutation
```

Expected:

```text
rejected specifically due locked state
no new revision
revision count unchanged
locked hash unchanged
episode state unchanged
artifact state unchanged
```

Không chỉ test stale hash/CAS mismatch.

---

# 16. Provider rate-limit failure injection

Roadmap yêu cầu:

```text
provider timeout
provider rate limit
```

Hiện rate limit test dùng:

```text
FakeRuntimeAdapter(rate_limit)
```

ở execution runtime boundary.

Nó chứng minh worker failure handling, nhưng không chứng minh provider router policy.

Tìm existing provider routing tests.

Nếu có canonical provider-router retry/fallback suite:

thêm explicit failure injection:

```text
provider returns HTTP 429
→ classify RATE_LIMIT
→ apply retry/fallback policy
→ correct retry budget
→ no secret leak
→ deterministic final outcome
```

Không network thật.

Dùng fake provider transport ở provider boundary.

Nếu policy thực tế không fallback mà terminal fail:

assert đúng policy.

Không ép behavior mới chỉ vì test.

---

# 17. Provider timeout cũng kiểm tra tương tự

Đảm bảo timeout test ở đúng boundary.

Phân biệt:

```text
execution runtime timeout
```

và:

```text
LLM provider timeout
```

Nếu roadmap nói provider timeout, test phải chứng minh provider/router semantics.

---

# 18. Security S3 tighten nếu sửa nhẹ được

Không phải primary blocker, nhưng nếu patch nhỏ:

Missing encryption key nên deterministically:

```text
request fails
vendor row absent
credential row absent
endpoint row absent
plaintext absent
```

Không nên chấp nhận trạng thái:

```text
row exists but encrypted
```

sau fail-closed request.

Nếu behavior hiện tại transaction rollback chuẩn, tighten test.

Không rewrite security module nếu không cần.

---

# 19. Certification artifact scope

Evidence commit cuối nên chỉ chứa generated certification evidence.

Tránh regenerate:

```text
artifacts/architecture_v3/phase_01/*
```

trừ khi certification protocol bắt buộc.

Phase 16 evidence commit lý tưởng:

```text
artifacts/architecture_v3/phase_16/**
```

Nếu checker tạo temporary artifacts:

restore/remove trước evidence commit nếu chúng không thuộc Phase 16.

---

# 20. Source authority workflow

Sau khi sửa code:

```bash
git status --short
```

Review toàn diff.

Chạy focused tests.

Sau đó tạo **implementation candidate commit mới**.

Ví dụ:

```text
fix(phase16): make final certification evidence complete
```

Ghi:

```bash
git rev-parse HEAD
git rev-parse HEAD^{tree}
git status --porcelain
```

Worktree phải clean trước certification.

Đây là candidate mới.

Không certification lại:

```text
e481f33...
```

nếu code certification/tests đã thay đổi.

---

# 21. Chạy certification từ clean candidate

Chỉ sau implementation commit:

```bash
uv run python scripts/certify_architecture_v3_final.py
```

Certification script phải tự chạy full matrix.

Không chạy vài test thủ công rồi chỉnh JSON thành PASS.

Artifact phải ghi exact:

```text
candidate_sha
tree_sha
branch
environment
commands
exit codes
gate evidence
test matrix
blockers
```

---

# 22. Required failure injection matrix

Evidence cuối phải bao gồm:

```text
API restart
Worker restart
worker killed during execution
DB transient failure
lease expiration
late result
duplicate command
duplicate event
WebSocket disconnect/reconnect
provider timeout
provider rate limit
```

Mỗi item phải:

```text
PASS / FAIL / BLOCKED
```

và map tới executable command/test.

---

# 23. Gate semantics

Hard gates:

```text
G0-G14
```

Không gate nào được:

```text
assumed PASS
informational PASS
file-exists-only PASS
proxy PASS không chứng minh semantics
```

Đặc biệt review:

```text
G9
G10
G11
G12
G13
```

vì đây là các gate dễ bị proxy.

---

# 24. G11 Truthful UI

Hiện G11 dựa phần lớn vào architecture checker.

Kiểm tra roadmap requirement của G11.

Nếu G11 thực sự yêu cầu:

```text
no fake health
no fake latency
no fake provider success
no fake connection status
```

hãy map nó tới actual frontend/API tests hoặc static scan có ý nghĩa.

Nếu architecture checker đã có dedicated rule đúng semantics:

ghi cụ thể rule name/count.

Không chỉ:

```text
architecture_clean = true
```

nếu không biết nó chứng minh gì.

---

# 25. Không được làm

Không:

```text
rewrite Architecture V3
change durable queue design
change UoW design nếu không cần
redesign UI
Blender changes
video feature
cleanup unrelated files
mass formatting
large rename
dependency upgrades
test skips
xfail blocker
hard-code PASS
reduce assertions
change roadmap requirements
```

Không push/merge trừ khi có explicit instruction.

---

# 26. Recommended execution order

Thực hiện đúng thứ tự:

```text
1. Baseline inspect
2. Repair certification script structure
3. G12 executable check
4. G9 real API isolation test
5. G10 worker pipeline evidence
6. Build complete G13 matrix
7. Add PostgreSQL gate
8. Add web/desktop/typecheck/build
9. Add API smoke
10. Add explicit worker/queue/outbox matrix
11. Add real vertical E2E to certification
12. Fix router claim/integration
13. Fix post-lock mutation test
14. Fix provider timeout/rate-limit boundary
15. Run focused suites
16. Run full matrix
17. Commit implementation candidate
18. Verify clean checkout
19. Run certification
20. Generate evidence-only commit
```

---

# 27. Definition of Done

Phase 16 chỉ DONE khi:

```text
[PASS] clean implementation candidate
[PASS] architecture checker zero violations
[PASS] Ruff E4,E7,E9,F = 0

[PASS] unit
[PASS] architecture
[PASS] contracts
[PASS] SQLite integration
[PASS] PostgreSQL integration

[PASS] API smoke
[PASS] Worker recovery
[PASS] queue/fencing
[PASS] outbox
[PASS] WebSocket replay

[PASS] web tests
[PASS] desktop tests
[PASS] typecheck
[PASS] builds

[PASS] V3 vertical real
[PASS] provider routing integration
[PASS] post-lock real immutability
[PASS] provider timeout FI
[PASS] provider rate limit FI

[PASS] G0
[PASS] G1
[PASS] G2
[PASS] G3
[PASS] G4
[PASS] G5
[PASS] G6
[PASS] G7
[PASS] G8
[PASS] G9
[PASS] G10
[PASS] G11
[PASS] G12
[PASS] G13
[PASS] G14

[PASS] evidence references exact candidate SHA
[PASS] no hard-coded PASS
[PASS] no missing required matrix entry
[PASS] no blockers
```

---

# 28. Final verdict rule

Chỉ được emit:

```text
ARCHITECTURE_V3_OPTIMIZED_AND_CERTIFIED
```

nếu **100% hard gate + full roadmap matrix PASS**.

Nếu PostgreSQL hoặc bất kỳ required suite nào chưa chạy:

```text
PHASE_16_BLOCKED
```

Nếu test fail:

```text
CERTIFICATION_FAILED
```

Không dùng partial PASS.

---

# 29. Final report format

Trả kết quả:

```text
PHASE_16_CERTIFICATION_REPAIR
=============================

BASELINE
- starting SHA:
- implementation parent:
- branch:
- worktree:

CERTIFICATION BUGS FOUND
1.
2.
3.

CERTIFICATION CHANGES
1.
2.
3.

G9 API ISOLATION
- command:
- evidence:
- result:

G10 WORKER PIPELINE
- command:
- stages covered:
- result:

G11 TRUTHFUL UI
- evidence:
- result:

G12 DOCS
- checks:
- result:

G13 FULL MATRIX
- architecture checker:
- ruff:
- unit:
- architecture:
- contract:
- sqlite:
- postgres:
- api smoke:
- worker recovery:
- queue/fencing:
- outbox:
- websocket:
- web:
- desktop:
- typecheck:
- build:

VERTICAL E2E
- API:
- queue:
- worker:
- model port:
- router:
- provider:
- persistence:
- review:
- lock:
- restart:
- result:

FAILURE INJECTION
- API restart:
- Worker restart:
- worker kill:
- DB transient:
- lease expiration:
- late result:
- duplicate command:
- duplicate event:
- WS reconnect:
- provider timeout:
- provider rate limit:

SECURITY
- S1:
- S2:
- S3:
- S4:
- S5:
- S6:
- S7:
- S8:

IMPLEMENTATION CANDIDATE
- sha:
- tree:
- clean:

CERTIFICATION
- certification candidate_sha:
- all gates:
- blockers:

EVIDENCE COMMIT
- sha:
- files:
- executable code changed: YES/NO

FINAL VERDICT:
...
```

Bắt đầu bằng việc **audit `scripts/certify_architecture_v3_final.py` so với Phase 16 matrix trong `ban_ke_hoach_v1.md`**, lập danh sách requirement nào hiện chưa được executable certification cover, rồi mới sửa code.
