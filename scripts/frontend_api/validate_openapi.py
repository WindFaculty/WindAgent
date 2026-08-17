"""
Validate OpenAPI specification quality, operation ID uniqueness, and response completeness.
"""

import json
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
OPENAPI_FILE = WORKSPACE_ROOT / "artifacts" / "frontend_restructure" / "openapi" / "openapi-v3.json"

def validate_openapi() -> bool:
    if not OPENAPI_FILE.exists():
        from scripts.frontend_api.export_openapi import export_openapi
        export_openapi()

    with open(OPENAPI_FILE, "r", encoding="utf-8") as f:
        schema = json.load(f)

    paths = schema.get("paths", {})
    operation_ids = {}
    duplicates = []
    missing_responses = []

    for path, path_item in paths.items():
        for method, op in path_item.items():
            if method.lower() not in ["get", "post", "put", "patch", "delete", "options", "head"]:
                continue
            op_id = op.get("operationId") or op.get("operation_id")
            if not op_id:
                print(f"[WARN] Missing operation_id for {method.upper()} {path}")
                continue

            if op_id in operation_ids:
                duplicates.append((op_id, operation_ids[op_id], f"{method.upper()} {path}"))
            else:
                operation_ids[op_id] = f"{method.upper()} {path}"

            if not op.get("responses"):
                missing_responses.append(f"{method.upper()} {path}")

    print(f"[OpenAPI Validation] Audited {len(operation_ids)} operations across {len(paths)} paths.")
    
    if duplicates:
        print(f"[ERROR] Found {len(duplicates)} duplicate operation_ids:")
        for op_id, p1, p2 in duplicates:
            print(f"  - {op_id}: {p1} vs {p2}")
        return False

    if missing_responses:
        print(f"[ERROR] Found {len(missing_responses)} operations with missing responses:")
        for mr in missing_responses:
            print(f"  - {mr}")
        return False

    print("[OpenAPI Validation] Validation PASS (0 duplicates, 0 missing responses).")
    return True

if __name__ == "__main__":
    success = validate_openapi()
    sys.exit(0 if success else 1)
