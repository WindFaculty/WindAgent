"""Produce Script Eval Phase 1 contract evidence (gate SCRIPT_EVAL_CONTRACT_VALID).

Spec: test_kich_ban.md section 4. Writes:
  artifacts/video_production/script_eval/phase_01_contract/
    contract_schema.json   contract_report.json   test_baseline.json   phase_verdict.json

Gate PASS requires: valid fixture passes clean, broken fixture trips every
contract check, and the fail-closed pytest matrix is green.
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
    DURATION_TOLERANCE, EMOTIONAL_STATE, REQUIRED, SCRIPT_SCHEMA_VERSION,
    TIME_OF_DAY, validate_script,
)
from windagent_evals.script_eval.fixtures import (  # noqa: E402
    FAULT_INJECTIONS, broken_production_script, valid_production_script,
)

_OUT_DIR = _ROOT / "artifacts" / "video_production" / "script_eval" / "phase_01_contract"
_GATE = "SCRIPT_EVAL_CONTRACT_VALID"
_TEST_FILE = "tests/unit/verification/test_script_eval_phase1_contract.py"


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
    valid = validate_script(valid_production_script())
    broken = validate_script(broken_production_script())
    fired = {f.check for f in broken.findings}
    checks_covered = fired >= set(FAULT_INJECTIONS)
    tests = run_tests()

    gate_passed = (
        valid.valid and valid.findings == ()
        and not broken.valid and checks_covered
        and tests["passed"]
    )

    (contract_schema := _OUT_DIR / "contract_schema.json").write_text(json.dumps({
        "schema_version": SCRIPT_SCHEMA_VERSION,
        "required_fields": REQUIRED,
        "enums": {"time_of_day": sorted(TIME_OF_DAY),
                  "emotional_state": sorted(EMOTIONAL_STATE)},
        "duration_tolerance": DURATION_TOLERANCE,
        "notes": "invalid_type check extends the plan list; empty dialogue/"
                 "objective and duration mismatch are WARNINGs (wordless "
                 "episodes T12 and Phase 8 duration gate)",}, indent=2) + "\n", encoding="utf-8")

    (contract_report := _OUT_DIR / "contract_report.json").write_text(json.dumps({
        "valid_fixture": {
            "schema_valid": valid.schema_valid,
            "reference_integrity": valid.reference_integrity,
            "valid": valid.valid,
            "scene_count": valid.scene_count,
            "character_count": valid.character_count,
            "target_seconds": valid.target_seconds,
            "estimated_seconds": valid.estimated_seconds,
            "duration_delta_pct": valid.duration_delta_pct,
            "findings": _finding_list(valid),
        },
        "broken_fixture": {
            "schema_valid": broken.schema_valid,
            "reference_integrity": broken.reference_integrity,
            "valid": broken.valid,
            "checks_fired": sorted(fired),
            "checks_required": sorted(FAULT_INJECTIONS),
            "all_checks_fired": checks_covered,
            "findings": _finding_list(broken),
        },
    }, indent=2) + "\n", encoding="utf-8")

    (test_baseline := _OUT_DIR / "test_baseline.json").write_text(json.dumps({
        "tests": tests,
        "checkers": [{
            "name": "fail-closed contract matrix",
            "status": "PASS" if tests["passed"] else "FAIL",
        }],
    }, indent=2) + "\n", encoding="utf-8")

    verdict = {
        "phase": "phase_01_contract",
        "subsystem": "script_eval",
        "gate": _GATE,
        "verdict": "PASS" if gate_passed else "FAIL",
        "summary": ("Production-script contract defined (schema v1.0.0) with "
                    "13 fail-closed checks; valid fixture passes clean, broken "
                    "fixture trips every check; WARNING policy for wordless "
                    "episodes and duration drift documented."),
        "backlog_completion": [
            {"item": "production script schema (project/world/characters/story/scenes/ending)",
             "status": "DONE", "evidence": "contract_schema.json"},
            {"item": "automated checks: missing field, duplicate ids, unknown "
                     "character/location, negative/zero duration, scene ordering, "
                     "broken references, invalid enum, empty dialogue/objective, "
                     "duration mismatch, invalid type",
             "status": "DONE", "evidence": "contract_report.json + test_baseline.json"},
            {"item": "gate: schema validity 100% + reference integrity 100%, "
                     "hard fail on dangling reference",
             "status": "DONE", "evidence": "phase_verdict.json"},
        ],
        "evidence_files": sorted(p.name for p in _OUT_DIR.glob("*.json")),
        "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (_OUT_DIR / "phase_verdict.json").write_text(
        json.dumps(verdict, indent=2) + "\n", encoding="utf-8")

    print(f"{_GATE} -> {verdict['verdict']}")
    print(f"  valid fixture: {'PASS' if valid.valid else 'FAIL'} "
          f"(errors={len(valid.errors)}, warnings={len(valid.warnings)})")
    print(f"  broken fixture: {'FAIL' if not broken.valid else 'BAD'} "
          f"({len(fired)}/{len(FAULT_INJECTIONS)} checks fired)")
    print(f"  pytest: {tests['summary']}")
    return verdict


def main() -> int:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    verdict = build_evidence()
    return 0 if verdict["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
