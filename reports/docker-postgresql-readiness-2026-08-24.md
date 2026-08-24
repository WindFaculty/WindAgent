# Docker PostgreSQL Readiness — 2026-08-24

## Verdict

**IMPLEMENTATION COMPLETE — CONTAINER VALIDATION GREEN**

Hạ tầng Docker PostgreSQL đã triển khai đầy đủ và pass toàn bộ local gates.
Phần xác minh cấp container (start → health → migrate → `pytest -m postgres`
thật) đã chạy THÀNH CÔNG trên máy này sau khi cài WSL2 + Docker Desktop
(engine 29.7.2, backend WSL2): container `windagent-postgres`
(postgres:16-alpine) healthy, Alembic lên đúng head `0019_live_record_domain`,
attestation fail-closed xác nhận `database_backend=postgresql
postgres_version=16`, và 112 tests `-m postgres` PASS (1 skipped giữ nguyên
nguyên nhân skip cũ) trên ephemeral DB đã tự drop khi đạt. Không fake bất kỳ
kết quả nào.

Trên đường tới trạng thái GREEN này, việc chạy thật lần đầu đã phát hiện và
sửa ba lỗi (chi tiết ở phần "Fix sau `ead8c28`"): hai bug test trong ma trận
PG, một bug SẢN PHẨM trong health check `schema_migration`, và một test E2E
two-process chưa từng chạy tới hoàn thành.

## Deliverables (commit `ead8c28`)

| File | Nội dung |
| --- | --- |
| `compose.yaml` | postgres:**16-alpine**, credentials mirror CI (`test:test`/`windagent`), port mặc định **55432** (override qua `WINDAGENT_POSTGRES_PORT`), healthcheck **pg_isready** (không dùng sleep), named volume `windagent-postgres-data` cho dev |
| `scripts/dev_postgres.py` | Wrapper stdlib-only: `up/status/url/migrate/test/psql-drop/down`. Readiness poll `docker inspect` (không blind sleep). `test` = ephemeral DB → Alembic qua runner canonical (`windagent_storage.migrations.runner`) → attestation PG16 fail-closed (`check_postgres_backend.py --output`, đúng shape CI) → pytest → drop DB. Mọi failure GIỮ database + evidence tại `artifacts/ci/dev-postgres/` |
| `tests/unit/scripts/test_dev_postgres.py` | 32 unit tests pure helpers, gồm regression-lock shape lệnh attestation (`--output`) |
| `.env.example` | Placeholders only; nêu rõ scope: CHỈ docker compose đọc `.env` |
| `README.md` | Section "PostgreSQL via Docker" |

Quyết định thiết kế đã áp:

- **Port single-source-of-truth**: `--port` > shell env > `.env` > 55432;
  giá trị resolve được inject vào subprocess `docker compose`, nên mapping
  publish không thể lệch khỏi URL wrapper dial. Container chạy sẵn sai port
  sẽ bị `--force-recreate`.
- **Migrations programmatic-only** qua `windagent_storage.migrations.runner`
  (`alembic_upgrade_head` + verify `alembic_current == alembic_heads`);
  không hardcode revision.
- **Backend identity gate** chạy TRƯỚC pytest, mirror CI: env
  `WINDAGENT_TEST_POSTGRES_URL` + `WINDAGENT_DATABASE_URL` (scheme
  `postgresql+asyncpg://`), expect server major 16, fail-closed exit ≠ 0.
- **Test isolation**: DB ephemeral per run (`windagent_test_<utc>_<pid>`),
  drop khi pass, GIỮ khi fail kèm hint `psql-drop`; volume dev không bao giờ
  được test/cert tái sử dụng.
- CI giữ nguyên service containers (`§27`); recording stack Windows-native
  (Tauri/WGC/WASAPI/NVENC) không dockerize.
- Testcontainers: đánh giá, KHÔNG thêm (wrapper stdlib đủ; thêm dependency
  mới trước freeze là rủi ro không cần thiết).

## Validation matrix (candidate `ead8c286986bffd82ddf0b6f1f178e0384946da3`)

| Hàng | Kết quả |
| --- | --- |
| `ruff check .` | PASS |
| Hygiene `check_test_architecture.py` | PASS — 0 violations |
| compose.yaml syntax + contract (image pin 16-alpine, pg_isready healthcheck, port map, volume) | PASS (PyYAML assertions) |
| Unit suite `tests/unit` | PASS — 1732 passed, 1 skipped (= 1700 baseline + 32 mới) |
| Component suite `tests/component` | PASS — 831 passed, 1 skipped (khớp baseline) |
| Wrapper smoke: `--help`, fail-closed khi thiếu docker (exit 1 + message cài đặt), attestation fail-closed khi thiếu URL (exit 1, không phải argparse rc=2) | PASS |
| Secret scan 5 file mới (11 patterns) | PASS — 0 match |
| Adversarial review workflow (18 agents, 4 chiều × verify) | PASS sau fix — 14 findings thô, 13 confirmed (1 blocker + 5 major + 7 minor), tất cả đã sửa; 1 refuted |
| Container start + healthy poll (`up`) | **PASS** — `windagent-postgres` postgres:16-alpine healthy (poll `docker inspect`, không sleep mù) |
| Ephemeral DB + Alembic to head trong container (`migrate`) | **PASS** — head `0019_live_record_domain`, verify `alembic_current == alembic_heads` |
| `pytest -m postgres` (~113) trên Docker PG (`test`) | **PASS** — 112 passed, 1 skipped, 22.98s; ephemeral DB tự drop khi đạt |
| P1 vertical slice + concurrency semantics + multiprocess E2E trên Docker PG | **PASS** — gồm `test_p1_e2e_acceptance`, idempotency/atomicity/CAS, real-asset persistence, `test_v3_vertical_lifecycle_real`; multiprocess E2E hai tiến trình chạy thật trên SQLite tier (7 passed) sau khi sửa test (xem phần Fix) |
| Backend identity proof từ container (`database_backend=postgresql`, version=16) | **PASS** — `postgres_backend.json`: `database_backend=postgresql`, `postgres_version=16` (PostgreSQL 16.15, alpine) |

Evidence run cuối: `artifacts/ci/dev-postgres/20260824_202556_windagent_test_20260824_202556_14468/`
(`run.json`, `postgres_backend.json`, `pytest.log`; duration tổng 24.0s).

## Fix sau `ead8c28` (phát hiện nhờ chạy thật lần đầu)

1. `f6db4e3` — **bug test ma trận PG**: hai test không sống sót qua ephemeral
   DB dùng chung (state-machine rank đi ngược gây 409
   INVALID_CHARACTER_STATUS_TRANSITION — sản phẩm ĐÚNG; và requirement pool
   cạn OPEN do test trước đã hoàn thành hết). Phân loại: LỖI TEST.
2. `4e6ad7e` — **bug SẢN PHẨM**: health check `schema_migration` truy vấn bảng
   legacy `migration_history` và kỳ vọng head `002_legacy_data` trong khi hệ
   canonical là Alembic (`alembic_version`, head `0019_live_record_domain`) →
   `/health/ready` trả 503 vĩnh viễn trên DB mới-migrate. Checker giờ đọc
   `alembic_version` fail-closed (rỗng/đa-head/lệch → DOWN), expected head được
   inject từ composition roots qua `alembic_heads()` — không hardcode. Đây là
   lỗi mà mọi readiness probe triển khai thật sẽ gặp.
3. `2e662aa` — **bug test E2E two-process** (`test_api_worker_durability`,
   sinh tại `f973efc`, chưa từng chạy tới hoàn thành): ROOT tính sai thành
   `tests/` khiến readiness không bao giờ lên; và với `WINDAGENT_FAKE_RUNTIME=1`
   worker attestation không bao giờ story-eligible nên start gate
   START_BLOCKED mãi mãi (thiết kế fail-closed ĐÚNG của sản phẩm). Test nay
   compose stack studio THẬT: seed provider + credential qua public API,
   sync-models qua provider stand-in cục bộ (chỉ external HTTP transport được
   kiểm soát), resolve durable canonical id từ registry, worker khởi động SAU
   khi catalog tồn tại. Phân loại: LỖI TEST.

Ghi chú review: blocker đã bắt và sửa trước commit là việc gọi
`check_postgres_backend.py` thiếu `--output` (argparse `required=True`) — nếu
không, mọi lần `test` chết ở bước attestation trước khi pytest chạy.

## Tác động lên T7

- Candidate cũ (`ead8c28`) **hết giá trị**: các fix trên yêu cầu candidate mới.
  CANDIDATE_CODE_SHA hiện tại: **`8457f05`**
  (commit cuối cùng của mã/test; commit docs có thể đứng trên nó).
  Ghi chú PHASE J lần 1: push đầu tiên (`67b1f840`) thất bại ở mức
  workflow — toàn bộ `ci.yaml` bị GitHub từ chối parse vì job-level `env:`
  dùng `${{ runner.temp }}` (context `runner` không tồn tại ở đó; lỗi này
  tồn tại từ trước, mọi run trước đây trên nhánh đều 0 job). Đã sửa tại
  `8457f05` bằng cách publish TMPDIR/TEMP qua `$GITHUB_ENV` từ step đầu.
- CI certification counter: **0/3** (chưa có run PASS nào kể từ reset).
- Bước tiếp theo: push `8457f05…` lên
  `origin/refactor/architecture-v3-hardening`, xác minh remote SHA == local,
  theo dõi 24 job bắt buộc + final-evidence, yêu cầu 3 consecutive PASS cùng
  SHA (cổng chính: `p1-e2e-postgres`, `postgres-production-semantics`).
