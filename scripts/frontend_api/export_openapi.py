"""
Export FastAPI OpenAPI specification to JSON artifact.
"""

import json
from pathlib import Path
from windagent_api.main import app

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = WORKSPACE_ROOT / "artifacts" / "frontend_restructure" / "openapi"
OUTPUT_FILE = OUTPUT_DIR / "openapi-v3.json"

def export_openapi() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    
    print(f"[OpenAPI Export] Successfully exported OpenAPI v3 specification to: {OUTPUT_FILE}")
    print(f"  Total Paths: {len(schema.get('paths', {}))}")
    return schema

if __name__ == "__main__":
    export_openapi()
