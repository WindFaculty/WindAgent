# Support Matrix — Release 0.1

> Kế hoạch 07 §21. Ma trận tối thiểu chứng nhận theo support policy đã công bố.
> Candidate: `1753831c752343aa89419e807aa57058266ff75c` · Verdict: `PASSED`

## Nguyên tắc

- Chỉ mục nào có cột **Certified** = **Yes** được trình bày là supported.
- Combination chưa test phải ghi ở **Known gaps**, không trình bày là supported.
- Ma trận này được mirror vào `artifacts/video_production/final/test_matrix.json`
  (platform_matrix) và cross-check bởi lane `EVIDENCE_VALIDATION`.

## Platform / database matrix

| Dimension | Value | Certified | Evidence |
|---|---|---|---|
| Python | `3.11` (pyproject `requires-python`) | Yes | `uv.lock` frozen; `test_matrix.json#platform_matrix.python` |
| OS (desktop/browser flow target) | Windows 11 (win32) | Yes | `test_matrix.json#platform_matrix.os`; CI attestation |
| CI platform (unit/build) | GitHub Actions `ci.yaml` (delegated) | Yes | `scripts/check_*.py` run locally = same scripts; CI job green required at §20.1 |
| Database — SQLite | upgrade/rollback/idempotent/data-preservation rehearsal | Yes | `migration_rehearsal_receipt.json` |
| Database — PostgreSQL | `MIGRATION_REHEARSAL` lane SQLite + CI Postgres job (delegated) | Partial | `migration_and_rollback.md`; CI lane runs Postgres in CI |
| Web toolchain | `apps/web` 0.3.0, Node (package-lock frozen) | Yes | `build_hash_manifest.json`; `CI_WEB_DESKTOP_PRESENCE` |
| Desktop toolchain | `apps/desktop` 0.6.0 (independent track) | Yes* | see REL-002 divergence note below |
| FFmpeg / ffprobe | 8.x (ffmpeg 8.1.2 observed) | Yes | `CI_FFMPEG_FIXTURES` real render+probe |
| Headed browser/runtime | Chrome installed on target | Yes (mock-level) | `RELEASE_E2E_MOCK`; phase 24 mock PoC |

\* Desktop version diverges from the product version (`0.6.0` vs `0.3.0`). This is a
documented known limitation — finding **REL-002**, `release_decision: acceptable-for-0.1`.

## Release 0.1 controlled scope (plan §25)

| Claim | Value |
|---|---|
| Flow accounts | 1 |
| Video length | 30–45 s |
| Characters / shots | ≤ 2 characters / ≤ 7 shots |
| Concurrency | 1 |
| Approval / cost / retry | bounded |
| TTS / FFmpeg | simple graphs |
| Resume / human takeover | basic |
| CI | mock PR CI + controlled live smoke/E2E |

## Not supported (deferred to roadmap)

- Multi-account sessions
- > 7 shots / complex FFmpeg or TTS graphs
- Concurrency > 1
- Unattended recovery / unattended CAPTCHA bypass
- PostgreSQL production deployment beyond the CI matrix lane

## Known gaps (explicitly not certified)

1. **Real-credit Flow E2E** — not executed offline; gated by approval
   (REL-001, release condition). Certified only at mock level.
2. **PostgreSQL live instance** — only CI-matrix coverage; no local PG rehearsal
   beyond the migration lane's SQLite backend.
3. **Cross-platform (Linux/macOS)** — not certified for Release 0.1.

## Validation mapping

| §21 dimension | Lane/artifact |
|---|---|
| Python versions in `pyproject` | `CI_VERSION_CONSISTENCY` |
| Windows desktop/browser | `CI_WEB_DESKTOP_PRESENCE` + attestation |
| CI platform | `ci_run_manifest.json` all lanes |
| SQLite + PostgreSQL | `MIGRATION_REHEARSAL` / CI PG job |
| web/desktop Node toolchain | `build_hash_manifest.json` lockfiles |
| FFmpeg version/profile | `CI_FFMPEG_FIXTURES` |
| Headed browser/runtime | `release_e2e_receipt.json` mock |

Chủ sở hữu ma trận: `release-owner`. Cập nhật ma trận khi có combination mới được
chứng nhận; combination chưa chứng nhận bắt buộc nằm trong Known gaps.
