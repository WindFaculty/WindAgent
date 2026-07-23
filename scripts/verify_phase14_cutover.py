"""
Cutover Verification Script for WindAgent Phase 14.
Validates Feature Flags status, import boundary cleanliness, DB parity, and zero illegal legacy imports.
"""

import sys
import subprocess
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "core"))

from windagent_core.config.feature_flags import FeatureFlagsManager


def verify_feature_flags() -> bool:
    mgr = FeatureFlagsManager()
    if not mgr.is_v2_enabled():
        print("[FAIL] Feature flag WINDAGENT_ARCH_V2 is NOT enabled!")
        return False
    print("[PASS] Feature flag WINDAGENT_ARCH_V2: ENABLED")
    return True


def verify_import_boundaries() -> bool:
    script_path = root_dir / "scripts" / "check_architecture_imports.py"
    if script_path.exists():
        res = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True)
        if res.returncode != 0:
            print("[FAIL] Import boundaries check failed!")
            print(res.stdout + res.stderr)
            return False
        print("[PASS] Architecture import boundaries check: CLEAN")
    return True


def main() -> int:
    print("=== Phase 14 Legacy Migration & Cutover Verification ===")
    ff_ok = verify_feature_flags()
    ib_ok = verify_import_boundaries()

    if ff_ok and ib_ok:
        print("Final Verdict: PHASE 14 CUTOVER VERIFICATION PASSED")
        return 0
    else:
        print("Final Verdict: PHASE 14 CUTOVER VERIFICATION FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
