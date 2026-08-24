# Docker PostgreSQL Readiness — 2026-08-24

## Verdict

**IMPLEMENTATION COMPLETE — CONTAINER VALIDATION BLOCKED_DOCKER_RUNTIME (tạm thời)**

Hạ tầng Docker PostgreSQL đã triển khai đầy đủ và pass toàn bộ local gates.
Phần xác minh cấp container (start → health → migrate → `pytest -m postgres`
thật) chưa chạy được vì máy chưa có Docker runtime: `docker.exe` không tồn tại
ở PATH lẫn các đường dẫn cài chuẩn (`C:\Program Files\Docker\Docker`,
`%LOCALAPPDATA%\Docker`), và WSL2 chưa cài (`wsl --status` → not installed).
Không fake bất kỳ kết quả nào; các hàng tương ứng được ghi rõ bên dưới.

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
| Container start + healthy poll (`up`) | **BLOCKED_DOCKER_RUNTIME** |
| Ephemeral DB + Alembic to head trong container (`migrate`) | **BLOCKED_DOCKER_RUNTIME** |
| `pytest -m postgres` (~113) trên Docker PG (`test`) | **BLOCKED_DOCKER_RUNTIME** |
| P1 vertical slice + concurrency semantics + multiprocess E2E trên Docker PG | **BLOCKED_DOCKER_RUNTIME** |
| Backend identity proof từ container (`database_backend=postgresql`, version=16) | **BLOCKED_DOCKER_RUNTIME** |

Ghi chú review: blocker đã bắt và sửa trước commit là việc gọi
`check_postgres_backend.py` thiếu `--output` (argparse `required=True`) — nếu
không, mọi lần `test` chết ở bước attestation trước khi pytest chạy.

## Tác động lên T7

- Candidate cũ (`68e35ed`) **hết giá trị**: thay đổi hạ tầng test yêu cầu
  candidate mới. Candidate hiện tại: **`ead8c286986bffd82ddf0b6f1f178e0384946da3`**
  (cây sạch, đã rerun local gates).
- CI certification counter: **0/3** (chưa push lần nào kể từ reset).
- Bước tiếp theo sau khi Docker sẵn sàng: `dev_postgres.py up` → `test` (full
  matrix container) → nếu xanh thì push `ead8c28…` và chạy 3 consecutive CI
  runs same-SHA; nếu container validation lộ bug → fix → clean tree → candidate
  SHA mới lại (counter vẫn 0/3).

## Hướng dẫn kích hoạt lại khi Docker sẵn sàng

```powershell
wsl --install          # + restart máy, mở Docker Desktop lần đầu
docker version         # client + server phải lên
.venv\Scripts\python.exe scripts\dev_postgres.py up      # start + wait healthy
.venv\Scripts\python.exe scripts\dev_postgres.py test    # full container matrix
```

Sau hai lệnh trên, cập nhật các hàng BLOCKED_DOCKER_RUNTIME trong ma trận này
thành kết quả thật rồi mới chuyển sang PHASE J (push).
