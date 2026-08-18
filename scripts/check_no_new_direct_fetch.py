"""
CI Architecture Rule Checker: Ensure NO new direct fetch violations are introduced.
Compares current repository state against the Phase 0 baseline snapshot.
"""

import json
import re
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = WORKSPACE_ROOT / "artifacts" / "frontend_restructure" / "phase_00" / "direct_fetch_inventory.json"
DELTA_FILE = WORKSPACE_ROOT / "artifacts" / "frontend_restructure" / "phase_03" / "direct_fetch_delta.json"

ALLOWED_PATHS = [
    "frontend/packages/api-client/src/transport.ts"
]

def check_direct_fetches() -> bool:
    baseline_entries = []
    if BASELINE_FILE.exists():
        with open(BASELINE_FILE, "r", encoding="utf-8") as f:
            baseline_entries = json.load(f)

    baseline_set = {(e["file"], e["line"]) for e in baseline_entries}

    fetch_pattern = re.compile(r'(?:fetch\s*\(\s*[\'"`]([^\'"`]+)[\'"`]|axios\.[a-z]+\s*\(\s*[\'"`]([^\'"`]+)[\'"`])')
    
    current_fetches = []
    scan_roots = [
        WORKSPACE_ROOT / "apps" / "desktop",
        WORKSPACE_ROOT / "apps" / "web",
        WORKSPACE_ROOT / "frontend"
    ]

    for root_dir in scan_roots:
        if not root_dir.exists():
            continue
        for p in root_dir.rglob("*"):
            if p.is_file() and p.suffix in [".ts", ".tsx", ".js", ".jsx"]:
                rel_path = str(p.relative_to(WORKSPACE_ROOT)).replace("\\", "/")
                if any(ignored in rel_path for ignored in ["node_modules", "dist", "coverage", ".test.", "__tests__"]):
                    continue
                if any(allowed in rel_path for allowed in ALLOWED_PATHS):
                    continue

                try:
                    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                    for line_no, line in enumerate(lines, 1):
                        for m in fetch_pattern.finditer(line):
                            url = m.group(1) or m.group(2)
                            current_fetches.append({
                                "file": rel_path,
                                "line": line_no,
                                "url": url,
                                "snippet": line.strip()
                            })
                except Exception:
                    pass

    # Find new violations
    new_violations = []
    for cf in current_fetches:
        if (cf["file"], cf["line"]) not in baseline_set:
            new_violations.append(cf)

    DELTA_FILE.parent.mkdir(parents=True, exist_ok=True)
    delta_report = {
        "baseline_direct_fetch_count": len(baseline_entries),
        "current_direct_fetch_count": len(current_fetches),
        "new_violations_count": len(new_violations),
        "new_violations": new_violations,
        "status": "PASS" if len(new_violations) == 0 else "FAIL"
    }

    with open(DELTA_FILE, "w", encoding="utf-8") as f:
        json.dump(delta_report, f, indent=2)

    print(f"[Direct Fetch Audit] Baseline: {len(baseline_entries)} | Current: {len(current_fetches)} | New Violations: {len(new_violations)}")
    if new_violations:
        print("[ERROR] New direct fetch violations detected:")
        for nv in new_violations:
            print(f"  - {nv['file']}:{nv['line']} -> {nv['url']}")
        return False

    print("[Direct Fetch Audit] PASS: Zero new direct fetch violations introduced.")
    return True

if __name__ == "__main__":
    success = check_direct_fetches()
    sys.exit(0 if success else 1)
