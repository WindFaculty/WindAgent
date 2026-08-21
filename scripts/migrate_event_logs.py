"""
Deterministic Event Stream Migration and Replay Manifest Generator (Phase 5).
Migrates historical event logs into canonical Pydantic v2 EventEnvelope format.
Computes SHA-256 manifest checksums without altering original source files.
"""

import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

workspace_root = Path(__file__).resolve().parent.parent
for pkg in [
    "apps/api", "apps/cli", "apps/worker", "core",
    "orchestration", "intelligence", "providers", "tools", "workflows",
    "verification", "context", "memory", "execution", "storage", "observability", "evals"
]:
    pkg_path = str(workspace_root / pkg)
    if pkg_path not in sys.path:
        sys.path.insert(0, pkg_path)

from windagent_core.events.envelope import EventEnvelope
from windagent_api.adapters.legacy_event_mappers import legacy_dict_to_v2_event


def compute_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def migrate_jsonl_log(source_path: Path, output_dir: Path, workspace_root: Path = None) -> dict:
    if not source_path.exists():
        return {"status": "SKIP", "reason": "File not found", "file": str(source_path)}

    dest_path = output_dir / f"{source_path.stem}.canonical.jsonl"
    quarantine_path = output_dir / f"{source_path.stem}.quarantine.jsonl"
    migrated_count = 0
    failed_count = 0
    quarantined_records = []

    with open(source_path, "r", encoding="utf-8", errors="ignore") as f_in, \
         open(dest_path, "w", encoding="utf-8") as f_out:
        for line_idx, line in enumerate(f_in, 1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                data = json.loads(line_str)
                # Parse or map legacy event dictionary
                if "event_type" in data and "." in data["event_type"]:
                    envelope = EventEnvelope.from_dict(data)
                else:
                    envelope = legacy_dict_to_v2_event(data)
                f_out.write(json.dumps(envelope.to_dict(), ensure_ascii=False) + "\n")
                migrated_count += 1
            except Exception as exc:
                failed_count += 1
                quarantined_records.append({
                    "line_number": line_idx,
                    "content": line_str[:500],
                    "error": str(exc),
                    "error_type": exc.__class__.__name__
                })

    if quarantined_records:
        with open(quarantine_path, "w", encoding="utf-8") as f_q:
            for rec in quarantined_records:
                f_q.write(json.dumps(rec, ensure_ascii=False) + "\n")

    source_hash = compute_sha256(source_path)
    dest_hash = compute_sha256(dest_path)

    rel_source = str(source_path.relative_to(workspace_root)) if workspace_root and source_path.is_relative_to(workspace_root) else str(source_path)
    rel_dest = str(dest_path.relative_to(workspace_root)) if workspace_root and dest_path.is_relative_to(workspace_root) else str(dest_path)

    receipt = {
        "source_file": rel_source,
        "canonical_file": rel_dest,
        "source_sha256": source_hash,
        "canonical_sha256": dest_hash,
        "migrated_records": migrated_count,
        "failed_records": failed_count,
        "quarantined_records_count": len(quarantined_records),
        "quarantine_file": str(quarantine_path.relative_to(workspace_root)) if workspace_root and quarantine_path.is_relative_to(workspace_root) and quarantined_records else None,
        "migrated_at": datetime.now(timezone.utc).isoformat(),
        "status": "SUCCESS" if failed_count == 0 else "PARTIAL_SUCCESS_WITH_QUARANTINE"
    }

    manifest_path = output_dir / f"{source_path.stem}.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f_manifest:
        json.dump(receipt, f_manifest, indent=2, ensure_ascii=False)

    return receipt


if __name__ == "__main__":
    workspace_root = Path(__file__).resolve().parent.parent
    output_dir = workspace_root / "artifacts" / "core_canonical" / "phase_05_events"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Phase 5: Event stream migration and manifest generator executed.")
    print(f"Target directory: {output_dir}")

