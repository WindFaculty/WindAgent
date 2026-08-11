"""C7 — REAL_VERTICAL_SLICE_GATE evidence producer.

Drives the real happy-path vertical slice (S15) against live API + worker
processes with a real local model, then writes:

- ``artifacts/studio_roadmap_01/c7/evidence.json`` — full correlation report.
- ``artifacts/studio_roadmap_01/c7/REAL_VERTICAL_SLICE_GATE_VERDICT.md``.

Usage:
    python scripts/studio_roadmap/produce_c7_evidence.py [--api http://127.0.0.1:8000] [--db sqlite+aiosqlite:///windagent_cert.db] [--seed-only]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.studio_roadmap.c7_slice_harness import (  # noqa: E402
    CANONICAL_MODEL,
    PROVIDER_MODEL,
    assert_report,
    run_slice,
    seed_runtime,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "c7"

SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*[\"'][^\"']{8,}[\"']", re.I),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}"),
]


def _redaction_safe(obj) -> bool:
    blob = json.dumps(obj, ensure_ascii=False)
    return not any(p.search(blob) for p in SECRET_PATTERNS)


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _versions() -> dict:
    return {
        "integration_sha": _git_sha(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "ollama_model": PROVIDER_MODEL,
        "canonical_model": CANONICAL_MODEL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=os.getenv("WINDAGENT_API_BASE", "http://127.0.0.1:8000"))
    parser.add_argument("--db", default=os.getenv("WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///windagent_cert.db"))
    parser.add_argument("--seed-only", action="store_true")
    args = parser.parse_args()

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    seeded = asyncio.run(seed_runtime(args.db))
    print(json.dumps({"seed": seeded}, indent=2))

    if args.seed_only:
        return 0

    report = run_slice(args.api)
    assert_report(report)

    evidence = {
        "contract": "studio.contract/v0.1",
        "gate": "REAL_VERTICAL_SLICE_GATE",
        "verdict": "PASS",
        **report,
        "versions": _versions(),
        "redaction_safe": _redaction_safe(report),
    }
    (EVIDENCE_DIR / "evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_verdict(evidence)
    print(json.dumps({"verdict": "PASS", "checks": evidence["checks_total"], "passed": evidence["checks_passed"]}, indent=2))
    return 0


def _write_verdict(evidence: dict) -> None:
    checks = evidence["checks"]
    lines = [
        "# REAL_VERTICAL_SLICE_GATE — C7 verdict",
        "",
        "- Contract: studio.contract/v0.1",
        "- Gate: REAL_VERTICAL_SLICE_GATE",
        "- Verdict: **PASS**",
        f"- Integration SHA: `{evidence['versions']['integration_sha']}`",
        "",
        "## Checks",
        "",
    ]
    for name, c in sorted(checks.items()):
        lines.append(f"- {'PASS' if c['pass'] else 'FAIL'} — {name}: {c['detail']}")
    lines += [
        "",
        "## Scope",
        "",
        "- Real processes: DB-backed API + independent worker, "
        "`WINDAGENT_FAKE_RUNTIME` unset, no mock/emergency fallback.",
        f"- Real provider route: canonical `{evidence['versions']['canonical_model']}` -> "
        f"local Ollama `{evidence['versions']['ollama_model']}` "
        "(OpenAI-compatible endpoint, real inference, durable route lock + execution coordinator).",
        f"- Namespace: series `{evidence['series_id']}`, episode `{evidence['episode_id']}`, "
        f"final run `{evidence['run_id']}`.",
        f"- Revision chain: {evidence['revision_chain']}",
        f"- Attempts: {json.dumps(evidence['attempts'], ensure_ascii=False)[:400]}",
        f"- Episode state: {evidence['episode_state']}; run status: {evidence['run_status']}",
        f"- Artifact counts: {json.dumps(evidence['artifact_counts'])}",
        f"- Event timeline: {len(evidence['event_types'])} events "
        f"({json.dumps(evidence['event_types'], ensure_ascii=False)[:300]}...)",
        f"- Redaction scan: {'clean' if evidence['redaction_safe'] else 'FAILED'}",
        "",
        "Evidence JSON: `artifacts/studio_roadmap_01/c7/evidence.json`",
        f"Generated: {evidence['versions']['generated_at']}",
        "",
    ]
    (EVIDENCE_DIR / "REAL_VERTICAL_SLICE_GATE_VERDICT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
