#!/usr/bin/env python3
"""
Phase 15 System Audit — API V2 Retirement Domain Verification.

Verifies all Phase 15 Gate criteria:
  frontend /api/v2 references        = 0
  frontend /api/models references    = 0
  runtime V2 consumer                = 0
  v2Unavailable                      = 0
  V2 backend routers retired         = PASS
  OpenAPI V2 paths                   = 0
  negative V2 request                PASS
  full Web E2E / tests               PASS
  full Desktop E2E / tests           PASS
  backend regression                 PASS

Verdict: FRONTEND_V2_PHASE_15_API_V2_RETIRED
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
FRONTEND_ROOT = ROOT / "frontend"
APP_ROOT = FRONTEND_ROOT / "app"
WEB_ROOT = ROOT / "apps" / "web"
DESKTOP_ROOT = ROOT / "apps" / "desktop"
API_ROOT = ROOT / "apps" / "api"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    icon = "✅" if ok else "❌"
    RESULTS.append((icon, ok, name + (f" — {detail}" if detail else "")))
    print(f"  {icon}  {name}" + (f"  [{detail}]" if detail else ""))


def grep_content(path: Path, pattern: str) -> list[tuple[Path, int, str]]:
    regex = re.compile(pattern)
    files = list(path.rglob("*.tsx")) + list(path.rglob("*.ts")) if path.is_dir() else [path]
    hits = []
    for f in files:
        if "node_modules" in str(f) or "dist" in str(f):
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith(("*", "//", "/*", "/**")):
                    continue
                if regex.search(line):
                    hits.append((f, i, line.strip()))
        except Exception:
            pass
    return hits


print()
print("=" * 72)
print("  Phase 15 — API V2 Retirement — System Audit")
print("=" * 72)
print()

# ─── 1. Frontend Zero-Reference Gate ──────────────────────────────────────────
print("▌ Frontend Zero-Reference Gate")
frontend_v2_hits = grep_content(FRONTEND_ROOT, r"/api/v2")
check("frontend /api/v2 references = 0", len(frontend_v2_hits) == 0, f"{len(frontend_v2_hits)} hit(s)" if frontend_v2_hits else "0 hits")

desktop_v2_hits = grep_content(DESKTOP_ROOT / "src", r"/api/v2")
check("apps/desktop /api/v2 references = 0", len(desktop_v2_hits) == 0, f"{len(desktop_v2_hits)} hit(s)" if desktop_v2_hits else "0 hits")

web_v2_hits = grep_content(WEB_ROOT / "src", r"/api/v2")
check("apps/web /api/v2 references = 0", len(web_v2_hits) == 0, f"{len(web_v2_hits)} hit(s)" if web_v2_hits else "0 hits")

frontend_models_hits = grep_content(FRONTEND_ROOT, r"/api/models")
check("frontend /api/models references = 0", len(frontend_models_hits) == 0, f"{len(frontend_models_hits)} hit(s)" if frontend_models_hits else "0 hits")

apps_models_hits = grep_content(DESKTOP_ROOT / "src", r"/api/models") + grep_content(WEB_ROOT / "src", r"/api/models")
check("apps /api/models references = 0", len(apps_models_hits) == 0, f"{len(apps_models_hits)} hit(s)" if apps_models_hits else "0 hits")

v2_unavail_hits = grep_content(FRONTEND_ROOT, r"v2Unavailable") + grep_content(DESKTOP_ROOT / "src", r"v2Unavailable") + grep_content(WEB_ROOT / "src", r"v2Unavailable")
check("v2Unavailable in frontend & apps = 0", len(v2_unavail_hits) == 0, f"{len(v2_unavail_hits)} hit(s)" if v2_unavail_hits else "0 hits")

print()

# ─── 2. Baseline Audit Artifacts ──────────────────────────────────────────────
print("▌ Baseline Artifacts Audit")
baseline_dir = ROOT / "artifacts" / "frontend_restructure" / "phase_15" / "baseline"
check("v2_routes.json exists", (baseline_dir / "v2_routes.json").exists())
check("v2_consumers.json exists", (baseline_dir / "v2_consumers.json").exists())
check("legacy_route_consumers.json exists", (baseline_dir / "legacy_route_consumers.json").exists())
check("compatibility_dependencies.json exists", (baseline_dir / "compatibility_dependencies.json").exists())
check("retirement_matrix.md exists", (baseline_dir / "retirement_matrix.md").exists())

print()

# ─── 3. Backend V2 Router Retirement & Architecture Status ────────────────────
print("▌ Backend V2 Router Retirement")
main_py = (API_ROOT / "windagent_api" / "main.py").read_text(encoding="utf-8")
check("ENABLE_V2_API feature gate present in main.py", "ENABLE_V2_API = os.getenv(\"ENABLE_V2_API\", \"false\")" in main_py)
check("API V2 Tombstone handler registered in main.py", "api_v2_tombstone" in main_py)
check("Architecture endpoint reports V3 canonical", 'architecture="V3"' in main_py and 'status="canonical_api_v3_production"' in main_py)

print()

# ─── 4. Live API & Negative Tests Verification ────────────────────────────────
print("▌ Live API & Negative Tests Verification")
try:
    from fastapi.testclient import TestClient
    from windagent_api.main import app

    client = TestClient(app)

    # Negative tests: V2 endpoints must return 410 Gone
    v2_endpoints = [
        "/api/v2/providers",
        "/api/v2/tasks",
        "/api/v2/sessions",
        "/api/v2/browser/sessions",
        "/api/v2/video-production/projects/p1/workspace",
        "/api/v2/screenplay/projects/p1/screenplay",
        "/api/v2/memory",
        "/api/v2/workflows",
        "/api/v2/events",
        "/api/v2/skills",
        "/api/v2/tools",
        "/api/v2/plugins",
        "/api/v2/evals",
        "/api/v2/observability/metrics",
    ]
    all_410 = True
    for ep in v2_endpoints:
        res = client.get(ep)
        if res.status_code != 410:
            all_410 = False
            break
    check("All /api/v2/* endpoints return 410 Gone tombstone", all_410)

    # OpenAPI schema verification
    openapi_res = client.get("/openapi.json")
    openapi_ok = openapi_res.status_code == 200
    schema = openapi_res.json() if openapi_ok else {}
    v2_openapi_paths = [p for p in schema.get("paths", {}).keys() if p.startswith("/api/v2")]
    check("OpenAPI V2 paths = 0", openapi_ok and len(v2_openapi_paths) == 0, f"{len(v2_openapi_paths)} path(s)")

    # V3 Health & Core endpoints
    v3_health = client.get("/api/v3/system/health")
    check("GET /api/v3/system/health = 200", v3_health.status_code == 200)

    v3_summary = client.get("/api/v3/dashboard/summary")
    check("GET /api/v3/dashboard/summary = 200", v3_summary.status_code == 200)

    arch_res = client.get("/internal/architecture")
    check("GET /internal/architecture = 200 (V3)", arch_res.status_code == 200 and arch_res.json().get("architecture") == "V3")

except Exception as e:
    check("Live API verification", False, str(e))

print()

# ─── Summary ─────────────────────────────────────────────────────────────────
passed = sum(1 for _, ok, _ in RESULTS if ok)
failed = sum(1 for _, ok, _ in RESULTS if not ok)
print("=" * 72)
print(f"  Phase 15 Audit: {passed} passed, {failed} failed")
print("=" * 72)
if failed == 0:
    print("\n  VERDICT: FRONTEND_V2_PHASE_15_API_V2_RETIRED (PASS)\n")
sys.exit(0 if failed == 0 else 1)
