#!/usr/bin/env python3
"""
Video Workspace Architecture Boundary Linter (Stage I — UI50)

Enforces that the canonical shared app shell (`@windagent/app`) only consumes
public APIs from shared packages (`@windagent/ui`, `@windagent/studio-shell`,
etc.) and does NOT import internal private implementation files.
"""

import sys
import re
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TARGET_COMPONENT = WORKSPACE_ROOT / "frontend" / "app" / "src" / "app" / "App.tsx"

FORBIDDEN_PATTERNS = [
    re.compile(r"import\s+.*\s+from\s+['\"].*components/(screenplay|asset)/.*['\"]"),
    re.compile(r"import\s+.*\s+from\s+['\"].*\.\./(screenplay|asset)/.*['\"]"),
    re.compile(r"import\s+.*\s+from\s+['\"].*internal/.*['\"]"),
]

def main() -> int:
    print("==================================================")
    print("UI50 Architectural Audit: Video Workspace Public API Boundary")
    print("==================================================")
    
    if not TARGET_COMPONENT.is_file():
        print(f"❌ Error: Target file {TARGET_COMPONENT} does not exist.")
        return 1
        
    content = TARGET_COMPONENT.read_text(encoding="utf-8")
    violations = []
    
    for idx, line in enumerate(content.splitlines(), start=1):
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(line):
                violations.append((idx, line.strip()))
                
    if violations:
        print(f"[FAIL] Architecture violation detected in {TARGET_COMPONENT.relative_to(WORKSPACE_ROOT)}:")
        for line_num, line_str in violations:
            print(f"  Line {line_num}: {line_str}")
        return 1
        
    print(f"[OK] Verified: {TARGET_COMPONENT.relative_to(WORKSPACE_ROOT)} imports only clean, public APIs.")
    print("Gate Status: VP3D_UI_VIDEO_WORKSPACE_FOUNDATION_READY = PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
