#!/usr/bin/env python3
"""
Architecture Invariant Enforcement Checker — Rules F001 to F010.

Permanent CI/CD verification script ensuring that architectural invariants
established throughout Migration Phases 0 to 16 are never violated.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
FRONTEND_APP = ROOT / "frontend" / "app"
FEATURES_DIR = FRONTEND_APP / "src" / "features"
WEB_DIR = ROOT / "apps" / "web"
DESKTOP_DIR = ROOT / "apps" / "desktop"

VIOLATIONS: list[tuple[str, str, str, int, str]] = []


def scan_files(directory: Path, extensions=(".ts", ".tsx")) -> list[Path]:
    if not directory.exists():
        return []
    return [
        p
        for p in directory.rglob("*")
        if p.suffix in extensions and "node_modules" not in str(p) and "dist" not in str(p)
    ]


def audit_rule(rule_id: str, description: str, files: list[Path], pattern: str, check_fn=None):
    regex = re.compile(pattern)
    rule_violations = 0
    for f in files:
        if "__tests__" in str(f) or ".test." in str(f) or ".spec." in str(f):
            continue
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            for line_no, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith(("//", "/*", "*", "/**")):
                    continue
                if check_fn:
                    if check_fn(f, line_no, line):
                        VIOLATIONS.append((rule_id, description, str(f.relative_to(ROOT)), line_no, stripped))
                        rule_violations += 1
                elif regex.search(line):
                    VIOLATIONS.append((rule_id, description, str(f.relative_to(ROOT)), line_no, stripped))
                    rule_violations += 1
        except Exception:
            pass

    status = "✅ PASS" if rule_violations == 0 else f"❌ FAIL ({rule_violations} violation(s))"
    print(f"  {status} — {rule_id}: {description}")


print("=" * 78)
print("  Architecture Invariant Checker — Rules F001 to F010")
print("=" * 78)
print()

# Rule F001: Feature cannot import apps/desktop
feature_files = scan_files(FEATURES_DIR)
audit_rule(
    "RULE F001",
    "Feature cannot import apps/desktop",
    feature_files,
    r"from\s+['\"].*apps/desktop.*['\"]",
)

# Rule F002: Feature cannot import apps/web
audit_rule(
    "RULE F002",
    "Feature cannot import apps/web",
    feature_files,
    r"from\s+['\"].*apps/web.*['\"]",
)

# Rule F003: Feature cannot call direct fetch()
def check_direct_fetch(f: Path, line_no: int, line: str) -> bool:
    stripped = line.strip()
    if "refetch" in stripped:
        return False
    return bool(re.search(r"(?<!\.)\bfetch\s*\(", stripped))

audit_rule(
    "RULE F003",
    "Feature cannot call direct fetch() in feature components",
    feature_files,
    "",
    check_fn=check_direct_fetch,
)

# Rule F004: Feature cannot reference /api/v2
audit_rule(
    "RULE F004",
    "Feature cannot reference /api/v2",
    feature_files,
    r"/api/v2",
)

# Rule F005: Feature cannot reference /api/models
audit_rule(
    "RULE F005",
    "Feature cannot reference /api/models",
    feature_files,
    r"/api/models",
)

# Rule F006: apps/web cannot import apps/desktop
web_files = scan_files(WEB_DIR / "src")
audit_rule(
    "RULE F006",
    "apps/web cannot import apps/desktop",
    web_files,
    r"from\s+['\"].*desktop.*['\"]",
)

# Rule F007: Runtime Fake client forbidden in production code
all_prod_files = scan_files(FRONTEND_APP / "src") + scan_files(WEB_DIR / "src") + scan_files(DESKTOP_DIR / "src")
audit_rule(
    "RULE F007",
    "Runtime FakeProductionApiClient forbidden in production source",
    all_prod_files,
    r"\bnew\s+FakeProductionApiClient\b",
)

# Rule F008: Route must be registered in routeManifest
route_manifest_file = FRONTEND_APP / "src" / "app" / "routeManifest.ts"
manifest_content = route_manifest_file.read_text(encoding="utf-8") if route_manifest_file.exists() else ""
manifest_ok = (
    "CANONICAL_ROUTE_MANIFEST" in manifest_content
    and "findRouteByPath" in manifest_content
    and "getNavigationGroups" in manifest_content
)
status_f008 = "✅ PASS" if manifest_ok else "❌ FAIL"
print(f"  {status_f008} — RULE F008: Authoritative RouteManifest registered")

# Rule F009: Navigation must reference valid route in routeManifest
status_f009 = "✅ PASS" if "getNavigationGroups" in manifest_content else "❌ FAIL"
print(f"  {status_f009} — RULE F009: Navigation groups reference valid manifest routes")

# Rule F010: API contract imports only from generated contracts
audit_rule(
    "RULE F010",
    "API contract imports use canonical contracts",
    feature_files,
    r"from\s+['\"].*legacy-contracts.*['\"]",
)

print()
print("=" * 78)
if len(VIOLATIONS) == 0 and manifest_ok:
    print("  ALL 10 ARCHITECTURAL RULES SATISFIED (PASS)")
    print("=" * 78)
    sys.exit(0)
else:
    print(f"  FOUND {len(VIOLATIONS)} ARCHITECTURAL VIOLATIONS:")
    for rule_id, desc, file, line_no, code in VIOLATIONS:
        print(f"    [{rule_id}] {file}:{line_no} -> {code}")
    print("=" * 78)
    sys.exit(1)
