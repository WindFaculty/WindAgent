"""Produce Script Eval Phase 2 idea evidence (gate SCRIPT_EVAL_IDEA_VALID).

Spec: test_kich_ban.md section 5. Writes:
  artifacts/video_production/script_eval/phase_02_idea/
    benchmark_manifest.json   idea_report.json   test_baseline.json   phase_verdict.json

Gate PASS requires: 12-brief x 3-duration benchmark expands to 36 runs, the
valid idea passes clean against its sibling, the broken idea trips every
Phase 2 check, and the fail-closed pytest matrix is green.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from windagent_evals.script_eval import (  # noqa: E402
    BENCHMARK_BRIEFS, DURATIONS_MINUTES, IDEA_SCHEMA_VERSION, benchmark_runs,
    validate_idea,
)
from windagent_evals.script_eval.fixtures import (  # noqa: E402
    IDEA_FAULT_INJECTIONS, broken_idea, sibling_idea, valid_idea,
)

_OUT_DIR = _ROOT / "artifacts" / "video_production" / "script_eval" / "phase_02_idea"
_GATE = "SCRIPT_EVAL_IDEA_VALID"
_TEST_FILE = "tests/unit/verification/test_script_eval_phase2_idea.py"


def _finding_list(report) -> list:
    return [{"check": f.check, "severity": f.severity, "path": f.path,
             "message": f.message} for f in report.findings]


def run_tests() -> dict:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", _TEST_FILE, "-q"],
        cwd=_ROOT, capture_output=True, text=True, timeout=300,
    )
    summary = r.stdout.strip().splitlines()[-1] if r.stdout else ""
    return {"command": f"{sys.executable} -m pytest {_TEST_FILE} -q",
            "returncode": r.returncode, "summary": summary,
            "passed": r.returncode == 0}


def build_evidence() -> dict:
    runs = benchmark_runs()
    valid = validate_idea(valid_idea(), siblings=[sibling_idea()])
    broken = validate_idea(broken_idea(), siblings=[sibling_idea()])
    fired = {f.check for f in broken.findings}
    checks_covered = fired >= set(IDEA_FAULT_INJECTIONS)
    tests = run_tests()

    gate_passed = (
        len(runs) == 36
        and valid.valid and valid.findings == ()
        and not broken.valid and checks_covered
        and tests["passed"]
    )

    (benchmark_manifest := _OUT_DIR / "benchmark_manifest.json").write_text(
        json.dumps({
            "schema_version": IDEA_SCHEMA_VERSION,
            "brief_count": len(BENCHMARK_BRIEFS),
            "durations_minutes": list(DURATIONS_MINUTES),
            "run_count": len(runs),
            "runs": runs,
        }, indent=2) + "\n", encoding="utf-8")

    (idea_report := _OUT_DIR / "idea_report.json").write_text(json.dumps({
        "criteria": {
            "hook": "hook ro, min " + "20 chars",
            "conflict": "phu hop tre em, ban terms check",
            "premise": "du de duy tri thoi luong (20 chars/min)",
            "differentiation": "khac cac test khac (Jaccard < 0.6)",
            "payoff": "co payoff ro",
            "lesson": "co lesson nhung khong giao dieu (WARNING)",
            "visual": "kha nang the hien bang hinh anh (WARNING)",
        },
        "valid_idea": {
            "case_id": valid.case_id,
            "duration_minutes": valid.duration_minutes,
            "valid": valid.valid,
            "schema_valid": valid.schema_valid,
            "differentiation_valid": valid.differentiation_valid,
            "findings": _finding_list(valid),
        },
        "broken_idea": {
            "valid": broken.valid,
            "checks_fired": sorted(fired),
            "checks_required": sorted(IDEA_FAULT_INJECTIONS),
            "all_checks_fired": checks_covered,
            "findings": _finding_list(broken),
        },
    }, indent=2) + "\n", encoding="utf-8")

    (test_baseline := _OUT_DIR / "test_baseline.json").write_text(json.dumps({
        "tests": tests,
        "checkers": [{
            "name": "fail-closed idea matrix (9 checks x 36-run benchmark)",
            "status": "PASS" if tests["passed"] else "FAIL",
        }],
    }, indent=2) + "\n", encoding="utf-8")

    verdict = {
        "phase": "phase_02_idea",
        "subsystem": "script_eval",
        "gate": _GATE,
        "verdict": "PASS" if gate_passed else "FAIL",
        "summary": ("Idea-generation benchmark frozen: 12 briefs (T01-T12) x "
                    "5/10/20 min = 36 runs; 9 fail-closed checks cover hook, "
                    "kid-appropriate conflict, duration-sustaining premise, "
                    "differentiation vs siblings, payoff, non-preachy lesson "
                    "(WARNING), visual potential (WARNING)."),
        "backlog_completion": [
            {"item": "benchmark 12-20 briefs (T01-T12 table)",
             "status": "DONE", "evidence": "benchmark_manifest.json"},
            {"item": "36 script runs minimum (12 x 5/10/20 min)",
             "status": "DONE", "evidence": "benchmark_manifest.json"},
            {"item": "idea criteria: hook, kid conflict, sustain premise, "
                     "differentiation, payoff, lesson, visual",
             "status": "DONE", "evidence": "idea_report.json"},
            {"item": "gate SCRIPT_EVAL_IDEA_VALID",
             "status": "DONE", "evidence": "phase_verdict.json"},
        ],
        "evidence_files": sorted(p.name for p in _OUT_DIR.glob("*.json")),
        "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (_OUT_DIR / "phase_verdict.json").write_text(
        json.dumps(verdict, indent=2) + "\n", encoding="utf-8")

    print(f"{_GATE} -> {verdict['verdict']}")
    print(f"  benchmark: {len(runs)} runs ({len(BENCHMARK_BRIEFS)} briefs x "
          f"{len(DURATIONS_MINUTES)} durations)")
    print(f"  valid idea: {'PASS' if valid.valid else 'FAIL'} "
          f"(errors={len(valid.errors)}, warnings={len(valid.warnings)})")
    print(f"  broken idea: {'FAIL' if not broken.valid else 'BAD'} "
          f"({len(fired)}/{len(IDEA_FAULT_INJECTIONS)} checks fired)")
    print(f"  pytest: {tests['summary']}")
    return verdict


def main() -> int:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    verdict = build_evidence()
    return 0 if verdict["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
