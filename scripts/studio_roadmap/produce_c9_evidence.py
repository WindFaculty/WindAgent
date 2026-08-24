"""Produce the C9 one-SHA final certification bundle.

The final gate is fail-closed: dirty source, absent/non-PASS C7 or C8,
mixed integration SHAs, missing reviewer sign-off, stale checksums, an unsafe
production scan, or an unclassified regression prevents promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "c9"
RAW_DIR = REPO_ROOT / ".tmp" / "studio-c9"
CONTRACT = "studio.contract/v0.1"

sys.path.insert(0, str(REPO_ROOT))

from scripts.studio_roadmap.certification_launcher import configure_utf8_stdio  # noqa: E402
from scripts.studio_roadmap.produce_c6_evidence import KNOWN_FAILURES  # noqa: E402


@dataclass(frozen=True)
class GateSource:
    order: int
    gate: str
    owner: str
    path: str


GATE_SOURCES: tuple[GateSource, ...] = (
    GateSource(0, "PARALLEL_BOOTSTRAP_GATE", "A+B+C+integration", "docs/plans/studio_roadmap_01/evidence/a0_bootstrap_manifest.json"),
    GateSource(1, "STUDIO_ARCHITECTURE_GATE", "A", "docs/plans/studio_roadmap_01/evidence/a1_boundary_repair.md"),
    GateSource(2, "STUDIO_DOMAIN_INTEGRATION_GATE", "A; B/C", "docs/plans/studio_roadmap_01/evidence/a2_domain_integration.md"),
    GateSource(3, "STORY_ARTIFACT_CONTRACT_GATE", "B; A/C", "docs/plans/studio_roadmap_01/evidence/b1_artifact_contract_gate.md"),
    GateSource(4, "STUDIO_PERSISTENCE_GATE", "A", "artifacts/studio_roadmap_01/a3/evidence.json"),
    GateSource(5, "DURABLE_ORCHESTRATION_GATE", "A", "artifacts/studio_roadmap_01/a4/evidence.json"),
    GateSource(6, "STRUCTURED_MODEL_GATE", "B", "docs/plans/studio_roadmap_01/evidence/b2_prompt_catalog_gate.md"),
    GateSource(7, "IDEA_GATE", "B+A", "docs/plans/studio_roadmap_01/evidence/b3_idea_gate.md"),
    GateSource(8, "STORY_BIBLE_GATE", "B", "docs/plans/studio_roadmap_01/evidence/b4_bible_gate.md"),
    GateSource(9, "OUTLINE_GATE", "B", "docs/plans/studio_roadmap_01/evidence/b5_outline_gate.md"),
    GateSource(10, "STORY_WORKER_GATE", "A+B", "artifacts/studio_roadmap_01/a5/evidence.json"),
    GateSource(11, "REAL_MODEL_RUNTIME_GATE", "A+B", "artifacts/studio_roadmap_01/a6/evidence.json"),
    GateSource(12, "SCREENPLAY_DRAFT_GATE", "B", "docs/plans/studio_roadmap_01/evidence/b6_screenplay_draft_gate.md"),
    GateSource(13, "STORY_REVIEW_GATE", "B", "docs/plans/studio_roadmap_01/evidence/b7_review_gate.md"),
    GateSource(14, "SCREENPLAY_RUNTIME_GATE", "A+B", "artifacts/studio_roadmap_01/a7/evidence.json"),
    GateSource(15, "LOCKED_SCREENPLAY_GATE", "A+B", "docs/plans/studio_roadmap_01/evidence/b8_lock_gate.md"),
    GateSource(16, "STUDIO_API_GATE", "C+A", "artifacts/studio_roadmap_01/c1/evidence.json"),
    GateSource(17, "STUDIO_CLIENT_STATE_GATE", "C", "artifacts/studio_roadmap_01/c2/evidence.json"),
    GateSource(18, "STUDIO_DESKTOP_SHELL_GATE", "C", "artifacts/studio_roadmap_01/c3/evidence.json"),
    GateSource(19, "STORY_UI_GATE", "C+B", "artifacts/studio_roadmap_01/c4/evidence.json"),
    GateSource(20, "API_UI_INTEGRATION_GATE", "C+A+B", "artifacts/studio_roadmap_01/c5/evidence.json"),
    GateSource(21, "PLAN_A_HANDOFF_GATE", "A", "artifacts/studio_roadmap_01/a7/evidence.json"),
    GateSource(22, "PLAN_B_HANDOFF_GATE", "B", "docs/plans/studio_roadmap_01/evidence/b9_handoff_gate.md"),
    GateSource(23, "RELEASE_CANDIDATE_GATE", "C/integration", "artifacts/studio_roadmap_01/c6/evidence.json"),
    GateSource(24, "REAL_VERTICAL_SLICE_GATE", "C integration", "artifacts/studio_roadmap_01/c7/evidence.json"),
    GateSource(25, "RECOVERY_VERTICAL_SLICE_GATE", "C integration", "artifacts/studio_roadmap_01/c8/evidence.json"),
)

SAME_SHA_GATES = {"REAL_VERTICAL_SLICE_GATE", "RECOVERY_VERTICAL_SLICE_GATE"}
CRITICAL_FAILURE_PREFIXES = ("tests/architecture/",)
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}", re.I),
    re.compile(r"(api[_-]?key|password|secret)\s*[:=]\s*['\"][^'\"]{8,}", re.I),
)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=20
    )
    return result.stdout.rstrip() if result.returncode == 0 else ""


def _head_sha() -> str:
    return _git("rev-parse", "HEAD") or "unknown"


def _dirty_paths() -> List[str]:
    return [line[3:] for line in _git("status", "--porcelain=v1").splitlines() if line]


def _source_dirty_paths(paths: List[str]) -> List[str]:
    allowed = (
        "artifacts/studio_roadmap_01/c7/",
        "artifacts/studio_roadmap_01/c8/",
        "artifacts/studio_roadmap_01/c9/",
    )
    return [path for path in paths if not path.replace("\\", "/").startswith(allowed)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _redaction_safe(value: Any) -> bool:
    blob = json.dumps(value, ensure_ascii=False)
    return not any(pattern.search(blob) for pattern in SECRET_PATTERNS)


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def evidence_sha(data: Dict[str, Any]) -> str:
    return str(
        data.get("integration_sha")
        or (data.get("versions") or {}).get("integration_sha")
        or (data.get("git") or {}).get("head_sha")
        or ""
    )


def evidence_verdict(path: Path, expected_gate: str) -> Dict[str, Any]:
    """Read JSON/Markdown upstream evidence without trusting its filename."""

    if not path.exists():
        return {"result": "BLOCKED", "reason": "evidence_missing"}
    checksum = sha256_file(path)
    if path.suffix.lower() == ".json":
        data = _load_json(path)
        gate = str(data.get("gate") or "")
        result = str(data.get("verdict") or data.get("result") or "").upper()
        if expected_gate == "PARALLEL_BOOTSTRAP_GATE":
            # Bootstrap manifest predates the common evidence envelope.
            result = "PASS" if data and "NEEDS_DECISION" not in json.dumps(data) else "FAIL"
        elif gate and gate != expected_gate and not (
            expected_gate == "SCREENPLAY_RUNTIME_GATE" and gate == "PLAN_A_HANDOFF_GATE"
        ):
            return {
                "result": "FAIL",
                "reason": f"gate_mismatch:{gate}",
                "sha256": checksum,
                "source_sha": evidence_sha(data),
            }
        if result not in {"PASS", "FAIL", "BLOCKED"}:
            result = "FAIL"
        contract = data.get("contract")
        if expected_gate in SAME_SHA_GATES and result == "PASS":
            if contract != CONTRACT:
                result = "FAIL"
            if data.get("redaction_safe") is not True:
                result = "FAIL"
        return {
            "result": result,
            "reason": "upstream_evidence",
            "sha256": checksum,
            "source_sha": evidence_sha(data),
            "contract": contract,
        }

    text = path.read_text(encoding="utf-8", errors="replace")
    normalized = text.upper()
    gate_present = expected_gate in normalized
    pass_pattern = re.compile(rf"{re.escape(expected_gate)}[^\n]{{0,80}}PASS", re.I)
    result = "PASS" if gate_present and pass_pattern.search(text) else "FAIL"
    return {
        "result": result,
        "reason": "upstream_markdown_evidence",
        "sha256": checksum,
        "source_sha": "historical-checksummed",
        "contract": CONTRACT if "STUDIO.CONTRACT/V0.1" in normalized else None,
    }


def build_gate_table(head_sha: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for source in GATE_SOURCES:
        path = REPO_ROOT / source.path
        observed = evidence_verdict(path, source.gate)
        limitation = ""
        if source.gate in SAME_SHA_GATES and observed.get("source_sha") != head_sha:
            observed["result"] = "BLOCKED"
            limitation = "certification evidence is absent or belongs to another integration SHA"
        elif observed.get("source_sha") not in ("", head_sha, "historical-checksummed"):
            limitation = "historic evidence; accepted only with recorded checksum and fresh C9 matrix"
        rows.append(
            {
                "order": source.order,
                "gate": source.gate,
                "owner": source.owner,
                "result": observed["result"],
                "evidence": source.path,
                "evidence_sha256": observed.get("sha256"),
                "source_sha": observed.get("source_sha"),
                "limitation": limitation or observed.get("reason", ""),
            }
        )
    return rows


def preflight(*, reviewer: str) -> Dict[str, Any]:
    head = _head_sha()
    dirty = _dirty_paths()
    source_dirty = _source_dirty_paths(dirty)
    gates = build_gate_table(head)
    blockers: List[str] = []
    if source_dirty:
        blockers.append("source_worktree_dirty")
    if not reviewer.strip():
        blockers.append("reviewer_signoff_missing")
    for row in gates:
        if row["result"] != "PASS":
            blockers.append(f"upstream_gate_not_pass:{row['gate']}")
    c7_c8_shas = {
        row.get("source_sha")
        for row in gates
        if row["gate"] in SAME_SHA_GATES and row.get("source_sha")
    }
    if c7_c8_shas != {head}:
        blockers.append("real_slice_evidence_mixed_or_stale_sha")
    return {
        "head_sha": head,
        "branch": _git("branch", "--show-current"),
        "source_worktree_clean": not source_dirty,
        "dirty_paths": dirty,
        "source_dirty_paths": source_dirty,
        "reviewer": reviewer.strip(),
        "gate_table": gates,
        "blockers": sorted(set(blockers)),
    }


def _run(name: str, command: List[str], cwd: Path = REPO_ROOT) -> Dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    temp_dir = RAW_DIR / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update({"TMP": str(temp_dir), "TEMP": str(temp_dir)})
    started = datetime.now(timezone.utc)
    before = time.monotonic()
    result = subprocess.run(
        command, cwd=cwd, env=environment, capture_output=True, text=True
    )
    finished = datetime.now(timezone.utc)
    raw = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    log_path = RAW_DIR / f"{name}.log"
    log_path.write_text(raw, encoding="utf-8")
    return {
        "command": " ".join(str(part) for part in command),
        "exit_code": result.returncode,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": round(time.monotonic() - before, 3),
        "tail": "\n".join(raw.splitlines()[-3:]),
        "raw_log": log_path.relative_to(REPO_ROOT).as_posix(),
        "raw_log_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    }


def _pytest_failures(junit_path: Path) -> List[str]:
    if not junit_path.exists() or not junit_path.stat().st_size:
        return ["junit_missing"]
    tree = ET.parse(junit_path)
    failed: List[str] = []
    for case in tree.iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        classname = case.attrib.get("classname", "").replace(".", "/")
        if "/Test" in classname:
            classname = classname.split("/Test", 1)[0]
        if classname and not classname.endswith(".py"):
            classname += ".py"
        failed.append(f"{classname}::{case.attrib.get('name', '')}")
    return sorted(failed)


def _production_scan() -> Dict[str, Any]:
    patterns = {
        "fixture_runtime": re.compile(r"\b(FixtureModelPort|FakeStudioOrchestrator|FakeStudioClient)\b"),
        "sample_identity": re.compile(r"\b(proj_legacy_[0-9]+|rev_legacy_[0-9]+|sample[_-]episode)\b", re.I),
        "literal_secret": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        "mock_fallback": re.compile(r"fallback\s*[:=]\s*['\"]?(mock|fake|fixture)", re.I),
    }
    roots = [
        REPO_ROOT / "apps",
        REPO_ROOT / "core",
        REPO_ROOT / "orchestration",
        REPO_ROOT / "providers",
        REPO_ROOT / "storage",
        REPO_ROOT / "intelligence",
    ]
    allowed_fixture_guards = {
        "intelligence/windagent_intelligence/story/prompts/fixture.py",
        "intelligence/windagent_intelligence/story/prompts/__init__.py",
    }
    hits: Dict[str, List[str]] = {name: [] for name in patterns}
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".ts", ".tsx", ".js"}:
                continue
            if any(part in {"tests", "test", "node_modules", "dist", "target", "__pycache__"} for part in path.parts):
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            relative = path.relative_to(REPO_ROOT).as_posix()
            for name, pattern in patterns.items():
                match = pattern.search(content)
                if match:
                    if name == "fixture_runtime" and relative in allowed_fixture_guards:
                        # B2's isolated fixture definition and its fail-closed
                        # guard export are test infrastructure, not composition.
                        continue
                    line = content.count("\n", 0, match.start()) + 1
                    hits[name].append(f"{relative}:{line}")
    bundle_hits: Dict[str, List[str]] = {name: [] for name in patterns}
    for root in (REPO_ROOT / "apps" / "desktop" / "dist", REPO_ROOT / "apps" / "web" / "dist"):
        if not root.exists():
            bundle_hits.setdefault("missing_bundle", []).append(root.relative_to(REPO_ROOT).as_posix())
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".js", ".html", ".json"}:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            relative = path.relative_to(REPO_ROOT).as_posix()
            for name, pattern in patterns.items():
                match = pattern.search(content)
                if match:
                    bundle_hits[name].append(f"{relative}:{content.count(chr(10), 0, match.start()) + 1}")
    return {
        "source_hits": hits,
        "bundle_hits": bundle_hits,
        "allowed_fixture_guards": sorted(allowed_fixture_guards),
        "clean": not any(hits.values()) and not any(bundle_hits.values()),
    }


def _matrix() -> Dict[str, Any]:
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    junit = RAW_DIR / "full_pytest.xml"
    commands = {
        "deterministic_checkers": ([sys.executable, "scripts/studio_roadmap/run_ci_checkers.py"], REPO_ROOT),
        "python_full": ([sys.executable, "-m", "pytest", "-q", "--tb=no", f"--junitxml={junit.as_posix()}"], REPO_ROOT),
        "v2_regression": (
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/unit/api/test_api_v2.py",
                "tests/unit/api/test_v2_production_events_replay.py",
                "tests/unit/api/test_v2_production_workspace_api.py",
            ],
            REPO_ROOT,
        ),
        "vp3d_regression": (
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/architecture/test_phase03_video_production_architecture.py",
                "tests/architecture/test_phase08_director_canonical.py",
                "tests/architecture/test_phase3_blender_architecture.py",
                "tests/unit/core/test_phase03_video_production_contracts.py",
                "tests/unit/core/test_phase03_video_production_domain.py",
                "tests/unit/core/test_phase03_video_production_events.py",
                "tests/unit/intelligence/test_phase08_director.py",
                "tests/unit/storage/test_video_production_repositories.py",
                "tests/unit/tools/test_phase3_blender_adapter.py",
                "tests/unit/tools/test_phase3_blender_runtime.py",
                "tests/unit/tools/test_phase4_blender_scene.py",
            ],
            REPO_ROOT,
        ),
        "desktop_tests": ([npm, "test"], REPO_ROOT / "apps" / "desktop"),
        "desktop_build": ([npm, "run", "build"], REPO_ROOT / "apps" / "desktop"),
        "tauri_release": (
            [npm, "run", "tauri", "--", "build", "--no-bundle"],
            REPO_ROOT / "apps" / "desktop",
        ),
        "web_tests": ([npm, "test"], REPO_ROOT / "apps" / "web"),
        "web_build": ([npm, "run", "build"], REPO_ROOT / "apps" / "web"),
    }
    results = {name: _run(name, command, cwd) for name, (command, cwd) in commands.items()}
    failures = _pytest_failures(junit)
    results["python_full"]["failed"] = failures
    results["python_full"]["known_outside_acceptance"] = sorted(set(failures) & KNOWN_FAILURES)
    results["python_full"]["unknown"] = sorted(set(failures) - KNOWN_FAILURES)
    results["python_full"]["critical"] = [
        failure for failure in failures if failure.startswith(CRITICAL_FAILURE_PREFIXES)
    ]
    results["production_scan"] = _production_scan()
    return results


def _matrix_checks(matrix: Dict[str, Any]) -> Dict[str, bool]:
    python_full = matrix["python_full"]
    return {
        "deterministic_checkers_green": matrix["deterministic_checkers"]["exit_code"] == 0,
        "python_no_unknown_regression": not python_full["unknown"],
        "python_no_architecture_failure": not python_full["critical"],
        "v2_regression_green": matrix["v2_regression"]["exit_code"] == 0,
        "vp3d_regression_green": matrix["vp3d_regression"]["exit_code"] == 0,
        "desktop_tests_green": matrix["desktop_tests"]["exit_code"] == 0,
        "desktop_build_green": matrix["desktop_build"]["exit_code"] == 0,
        "tauri_release_green": matrix["tauri_release"]["exit_code"] == 0,
        "web_tests_green": matrix["web_tests"]["exit_code"] == 0,
        "web_build_green": matrix["web_build"]["exit_code"] == 0,
        "production_fake_secret_scan_clean": matrix["production_scan"]["clean"],
        "committed_evidence_redaction_clean": _redaction_safe(matrix),
    }


def _write_master_table(rows: Iterable[Dict[str, Any]], final_result: str) -> str:
    lines = [
        "# Roadmap 1 master certification table",
        "",
        "| Order | Gate | Owner | Result | Evidence | Limitation |",
        "|---:|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['order']} | `{row['gate']}` | {row['owner']} | **{row['result']}** | "
            f"`{row['evidence']}` | {row.get('limitation') or 'None'} |"
        )
    lines.append(
        f"| 26 | `FINAL_CERTIFICATION_GATE` | Integration owner | **{final_result}** | "
        "`artifacts/studio_roadmap_01/c9/evidence.json` | One-SHA final decision |"
    )
    lines.append("")
    return "\n".join(lines)


def _write_outputs(evidence: Dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    evidence_path = ARTIFACT_DIR / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    table_text = _write_master_table(evidence["master_gate_table"], evidence["verdict"])
    table_path = ARTIFACT_DIR / "MASTER_GATE_TABLE.md"
    table_path.write_text(table_text, encoding="utf-8")
    verdict_path = ARTIFACT_DIR / "FINAL_CERTIFICATION_GATE_VERDICT.md"
    verdict_lines = [
        "# FINAL_CERTIFICATION_GATE — C9 verdict",
        "",
        f"- Verdict: **{evidence['verdict']}**",
        f"- Contract: {evidence['contract']}",
        f"- Integration SHA: `{evidence['integration_sha']}`",
        f"- Reviewer: {evidence['reviewer'] or 'MISSING'}",
        "",
    ]
    if evidence.get("blockers"):
        verdict_lines += ["## Blockers", "", *[f"- {item}" for item in evidence["blockers"]], ""]
    if evidence.get("checks"):
        verdict_lines += [
            "## Fresh matrix",
            "",
            *[f"- {'PASS' if ok else 'FAIL'} — {name}" for name, ok in evidence["checks"].items()],
            "",
        ]
    verdict_lines += [
        "Master table: `artifacts/studio_roadmap_01/c9/MASTER_GATE_TABLE.md`",
        "Bundle index: `artifacts/studio_roadmap_01/c9/bundle_index.json`",
        f"Generated: {evidence['generated_at']}",
        "",
    ]
    verdict_path.write_text("\n".join(verdict_lines), encoding="utf-8")

    indexed = {
        row["evidence"] for row in evidence["master_gate_table"] if (REPO_ROOT / row["evidence"]).exists()
    }
    indexed.update(
        {
            evidence_path.relative_to(REPO_ROOT).as_posix(),
            table_path.relative_to(REPO_ROOT).as_posix(),
            verdict_path.relative_to(REPO_ROOT).as_posix(),
        }
    )
    files = [
        {"path": rel, "sha256": sha256_file(REPO_ROOT / rel), "size_bytes": (REPO_ROOT / rel).stat().st_size}
        for rel in sorted(indexed)
    ]
    index = {
        "schema": "windagent.certification-bundle/v1",
        "integration_sha": evidence["integration_sha"],
        "contract": evidence["contract"],
        "verdict": evidence["verdict"],
        "reviewer_signoff": evidence["reviewer"],
        "signed_at": evidence["generated_at"],
        "signature_method": "reviewer attestation + SHA-256 file manifest",
        "files": files,
    }
    index_path = ARTIFACT_DIR / "bundle_index.json"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    (ARTIFACT_DIR / "bundle_index.sha256").write_text(
        f"{sha256_file(index_path)}  bundle_index.json\n", encoding="utf-8"
    )


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer", default=os.getenv("WINDAGENT_CERT_REVIEWER", ""))
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    pre = preflight(reviewer=args.reviewer)
    evidence: Dict[str, Any] = {
        "phase": "C9",
        "gate": "FINAL_CERTIFICATION_GATE",
        "contract": CONTRACT,
        "integration_sha": pre["head_sha"],
        "reviewer": pre["reviewer"],
        "generated_at": started.isoformat(),
        "preflight": {key: value for key, value in pre.items() if key != "gate_table"},
        "master_gate_table": pre["gate_table"],
        "checks": {},
        "blockers": list(pre["blockers"]),
    }
    if pre["blockers"] or args.preflight_only:
        if args.preflight_only and not evidence["blockers"]:
            evidence["blockers"].append("preflight_only_requested")
        evidence["verdict"] = "BLOCKED"
        _write_outputs(evidence)
        print(json.dumps({"verdict": "BLOCKED", "blockers": evidence["blockers"]}))
        return 2

    matrix = _matrix()
    checks = _matrix_checks(matrix)
    evidence["matrix"] = matrix
    evidence["checks"] = checks
    evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
    evidence["verdict"] = "PASS" if all(checks.values()) else "FAIL"
    if evidence["verdict"] != "PASS":
        evidence["blockers"] = [name for name, passed in checks.items() if not passed]
    else:
        evidence["master_gate_table"] = [
            {**row, "limitation": row["limitation"] or "fresh C9 matrix passed at integration SHA"}
            for row in evidence["master_gate_table"]
        ]
    _write_outputs(evidence)
    print(json.dumps({"verdict": evidence["verdict"], "checks": checks}))
    return 0 if evidence["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
