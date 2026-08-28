Đây là prompt hoàn chỉnh — sau khi máy khởi động lại và bạn mở session mới, chỉ cần dán cái này:

BỐI CẢNH (tiếp tục phiên trước): repo D:\code_ca_nhan\WindAgent, branch
refactor/architecture-v3-hardening. Tôi đang đóng T7 (test architecture
PRODUCTION_READY) kèm hạ tầng Docker PostgreSQL mới.

TRẠNG THÁI ĐÃ CHỐT:
- HEAD = e24effd83bb883e80ebf0e44292bb3893035ce10, cây sạch = candidate mới.
- Commit ead8c28: compose.yaml (postgres:16-alpine, mirror credentials CI
  test:test/windagent, port mặc định 55432, healthcheck pg_isready) +
  scripts/dev_postgres.py (up/status/url/migrate/test/psql-drop/down;
  poll health qua docker inspect, KHÔNG blind sleep; test = ephemeral DB ->
  Alembic qua windagent_storage.migrations.runner -> attestation
  check_postgres_backend.py --output fail-closed PG16 -> pytest -> drop DB;
  mọi failure GIỮ DB + evidence ở artifacts/ci/dev-postgres/; port
  single-source-of-truth --port > env > .env > 55432) + 32 unit tests +
  .env.example + README. Adversarial review workflow đã chạy: 13 findings
  confirmed đều đã fix (blocker thiếu --output đã s
- Local gates trên candidate: ruff PASS, hygiene 0 violations, unit 1732+1sk,
  component 831+1sk — tất cả PASS.
- reports/docker-postgresql-readiness-2026-08-24.md: verdict trung thực là
  IMPLEMENTATION COMPLETE / CONTAINER VALIDATION BL
  lúc đó WSL2 chưa cài.
- CI certification counter: 0/3, chưa push lần nào.
- Docker Desktop đã cài (client 29.7.2) và đang chạy; tôi VỪA chạy
  `wsl --install --no-distribution` và RESTART MÁY.
  engine thì kiểm tra `wsl --status` trước, đừng đi vòng.

VIỆC CẦN LÀM NGAY BÂY GIỜ (theo đúng thứ tự):
1. Verify runtime: `docker version` (nếu PATH shell chưa có docker thì dùng
   "C:\Program Files\Docker\Docker\resources\bin\do
   trả lời, không được coi client-alone là sẵn sàng.
2. Chạy container validation matrix thật:
   .venv\Scripts\python.exe scripts\dev_postgres.py
   .venv\Scripts\python.exe scripts\dev_postgres.py test
   Kỳ vọng: postgres healthy, alembic head (0019_live_record_domain),
   attestation database_backend=postgresql major=16, ~113 tests -m postgres,
   DB ephemeral bị drop khi pass. Luôn dùng .venv\Scripts\python.exe.
   Nếu tôi muốn dùng host port 12434 thì thêm --por
3. Nếu có bug: root-cause trước khi fix, fix xong rerun gate liên quan,
   commit riêng, clean tree, candidate SHA mới.
4. Khi matrix xanh: cập nhật 5 hàng BLOCKED_DOCKER_RUNTIME trong
   reports/docker-postgresql-readiness-2026-08-24.m
   commit report, clean tree, đó là CANDIDATE_CODE_SHA cuối cùng.
5. PHASE J: push candidate lên origin/refactor/arch
   xác nhận remote SHA == local SHA, rồi theo dõi CI (24 required jobs +
   final-evidence). Yêu cầu 3 consecutive PASS runs TRÊN CÙNG MỘT SHA.
   CI job p1-e2e-postgres + postgres-production-semantics là gate PG chính.
6. PHASE K–M: tải evidence 3 runs về
   artifacts/test-refactor/t7/certification/run_{1,2,3}/ (kèm hashes),
   viết certification_manifest.json phân biệt CANDI
   EVIDENCE_PUBLICATION_SHA, verify hash, rồi FINAL CERTIFICATION REPORT
   với verdict READY hay BLOCKED_EXTERNAL_CI.
7. Nếu CI fail: KHÔNG fix bừa — root-cause analysis trước, phân loại
   (test bug / product bug / flaky / infra), báo tôi trước khi sửa code
   product; fix test bug được phép ngay.

QUY TẮC BẤT BIẾN: không fake kết quả, không SQLite fallback, không chuyển
FAIL thành SKIP, không sleep chờ DB; trung thực tuyệt đối về trạng thái;
bất kỳ thay đổi nào trên tree sau freeze phải tạo candidate SHA mới và reset
counter về 0/3. Trả lời tôi bằng tiếng Việt.

Lưu ý nhỏ: sau restart, terminal/session mới sẽ có  giữ PATH stale), nên bước 1 thường chỉ cần dockerversion trơn.