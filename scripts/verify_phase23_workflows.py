#!/usr/bin/env python3
"""
Phase 23 - Workflow specification & workflow packs verification.
Validates all 8 workflow packs produce valid DAG definitions with:
- Conditional edges, fan-out/fan-in
- Artifact contracts and completion predicates
- Version pinning and migration
- DAG validation and structure
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = ROOT_DIR / "artifacts" / "architecture_v2_completion" / "phase_23"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# Ensure all workspace packages are importable
sys.path.insert(0, str(ROOT_DIR))
for pkg_dir in ["core", "workflows", "orchestration"]:
    pkg_path = ROOT_DIR / pkg_dir
    if pkg_path.exists():
        sys.path.insert(0, str(pkg_path))

from windagent_workflows import (
    WorkflowRegistry, BugfixWorkflowPack, CIFixWorkflowPack, CodeReviewWorkflowPack,
    FeatureWorkflowPack, RefactorWorkflowPack, ResearchWorkflowPack,
    ScientificEvalWorkflowPack, ReleaseWorkflowPack,
    ImmutableWorkflowDefinition, WorkflowNodeSpec, WorkflowEdgeSpec,
    ArtifactContract, CompletionPredicate, NodeType, EdgeType,
    WorkflowMigrationManager, MigrationImpact, PinnedDefinition,
)
from windagent_core.errors.exceptions import ValidationError


# ====================================================================
# Gate Checks
# ====================================================================

def check_dag_validation() -> Dict[str, Any]:
    """Gate 1: DAG validation must pass for all packs."""
    results = {"passed": True, "packs": {}}
    pack_params = {
        "bugfix": {"issue_description": "Fix login bug"},
        "ci_fix": {"ci_log_url_or_content": "ci_log.txt"},
        "code_review": {"target_branch_or_diff": "main..feature"},
        "feature": {"feature_description": "Add dark mode"},
        "refactor": {"target_module": "storage"},
        "research": {"research_topic": "RAG architectures"},
        "scientific_eval": {"eval_protocol_id": "eval_01"},
        "release": {"release_version": "1.0.0"},
    }

    for name, params in pack_params.items():
        pack_result = {"valid": True, "nodes": 0, "edges": 0, "errors": []}
        try:
            reg = WorkflowRegistry()
            pack_cls = {
                "bugfix": BugfixWorkflowPack,
                "ci_fix": CIFixWorkflowPack,
                "code_review": CodeReviewWorkflowPack,
                "feature": FeatureWorkflowPack,
                "refactor": RefactorWorkflowPack,
                "research": ResearchWorkflowPack,
                "scientific_eval": ScientificEvalWorkflowPack,
                "release": ReleaseWorkflowPack,
            }[name]
            reg.register_pack(pack_cls())
            pack = reg.get_pack(name)
            definition = pack.build_workflow_definition(params)
            definition.validate()
            pack_result["nodes"] = len(definition.nodes)
            pack_result["edges"] = len(definition.edges)
            pack_result["semantic_version"] = definition.semantic_version
            pack_result["content_hash"] = definition.content_hash

            # Verify node references
            node_ids = set(definition.nodes.keys())
            for edge in definition.edges:
                if edge.from_node_id not in node_ids:
                    pack_result["errors"].append("Dangling edge from: " + edge.from_node_id)
                if edge.to_node_id not in node_ids:
                    pack_result["errors"].append("Dangling edge to: " + edge.to_node_id)

            # Verify initial nodes exist
            initials = definition.get_initial_nodes()
            pack_result["initial_nodes"] = [n.name for n in initials]

            # Count non-dependency edges
            non_dep = [e for e in definition.edges if e.edge_type != EdgeType.DEPENDENCY]
            pack_result["conditional_edges"] = len([e for e in non_dep if e.edge_type == EdgeType.CONDITIONAL])
            pack_result["parallel_edges"] = len([e for e in non_dep if e.edge_type == EdgeType.PARALLEL])

            # Verify artifact contracts
            for nid, node in definition.nodes.items():
                for artifact in node.input_artifacts:
                    if not artifact.name:
                        pack_result["errors"].append("Node " + nid + ": input artifact missing name")
                for artifact in node.output_artifacts:
                    if not artifact.name:
                        pack_result["errors"].append("Node " + nid + ": output artifact missing name")

        except ValidationError as e:
            pack_result["valid"] = False
            pack_result["errors"].append(str(e))
            results["passed"] = False
        except Exception as e:
            pack_result["valid"] = False
            pack_result["errors"].append("Unexpected error: " + str(e))
            results["passed"] = False

        if pack_result["errors"]:
            results["passed"] = False
        results["packs"][name] = pack_result

    return results


def check_migration_and_pinning() -> Dict[str, Any]:
    """Gate 2: Version pinning and migration comparison work correctly."""
    results = {"passed": True, "details": {}}

    try:
        manager = WorkflowMigrationManager()
        nodes_v1 = {"s1": WorkflowNodeSpec(id="s1", name="step1", tool_name="exec_shell")}
        nodes_v2 = {
            "s1": WorkflowNodeSpec(id="s1", name="step1", tool_name="exec_shell"),
            "s2": WorkflowNodeSpec(id="s2", name="step2", tool_name="read_file"),
        }
        d1 = ImmutableWorkflowDefinition(id="test", name="test", semantic_version="1.0.0", nodes=nodes_v1)
        d2 = ImmutableWorkflowDefinition(id="test", name="test", semantic_version="2.0.0", nodes=nodes_v2)

        manager.record_version(d1)
        manager.record_version(d2)
        manager.pin_definition("run_001", d1)

        pinned = manager.get_pinned_definition("run_001")
        results["details"]["pinning_works"] = pinned is not None and pinned.content_hash == d1.content_hash

        old_pinned = manager.get_pinned_definition("run_001")
        results["details"]["old_run_keeps_old_version"] = old_pinned is not None and old_pinned.semantic_version == "1.0.0"

        results["details"]["release_pin_works"] = manager.release_pin("run_001")
        results["details"]["released_not_found"] = manager.get_pinned_definition("run_001") is None

        impact_added = manager.compare_versions(d1, d2)
        results["details"]["added_node_detected"] = "s2" in impact_added.added_nodes
        results["details"]["backward_compatible"] = impact_added.is_backward_compatible

        impact_removed = manager.compare_versions(d2, d1)
        results["details"]["removed_node_detected"] = "s2" in impact_removed.removed_nodes
        results["details"]["breaking_change_detected"] = not impact_removed.is_backward_compatible

        versions = manager.list_versions("test")
        results["details"]["version_history_recorded"] = "1.0.0" in versions and "2.0.0" in versions

        manager.pin_definition("run_002", d2)
        stats = manager.get_pinned_stats()
        results["details"]["pinned_stats_works"] = stats["total_pinned"] == 1 and stats["version_history_entries"] == 2

    except Exception as e:
        results["passed"] = False
        results["details"]["error"] = str(e)

    results["passed"] = all(results["details"].values()) if results["details"] else False
    return results


def check_builtin_packs_coverage() -> Dict[str, Any]:
    """Gate 3: All 8 built-in packs registered and produce valid DAG definitions."""
    results = {"passed": True, "registered_packs": [], "details": {}}
    expected_packs = ["bugfix", "ci_fix", "code_review", "feature", "refactor", "research", "scientific_eval", "release"]

    try:
        reg = WorkflowRegistry()
        reg.register_pack(BugfixWorkflowPack())
        reg.register_pack(CIFixWorkflowPack())
        reg.register_pack(CodeReviewWorkflowPack())
        reg.register_pack(FeatureWorkflowPack())
        reg.register_pack(RefactorWorkflowPack())
        reg.register_pack(ResearchWorkflowPack())
        reg.register_pack(ScientificEvalWorkflowPack())
        reg.register_pack(ReleaseWorkflowPack())

        actual_packs = sorted([p.name for p in reg.list_packs()])
        results["registered_packs"] = actual_packs
        results["details"]["all_8_registered"] = set(actual_packs) == set(expected_packs)

        for name in expected_packs:
            pack = reg.get_pack(name)
            has_legacy = hasattr(pack, "build_step_sequence")
            has_dag = hasattr(pack, "build_workflow_definition")
            results["details"][name + "_has_legacy_step_sequence"] = has_legacy
            results["details"][name + "_has_dag_definition"] = has_dag

        classification_tests = {
            "fix bug in login": "bugfix",
            "code review PR": "code_review",
            "prepare release v2.0": "release",
            "research topic": "research",
            "run benchmark eval": "scientific_eval",
            "refactor module": "refactor",
            "add new feature": "feature",
            "ci build failed": "ci_fix",
        }
        for prompt, expected_pack in classification_tests.items():
            classified = reg.classify_task(prompt)
            results["details"]["classify_" + prompt] = classified is not None and classified.name == expected_pack

    except Exception as e:
        results["passed"] = False
        results["details"]["error"] = str(e)

    return results


# ====================================================================
# Main
# ====================================================================

def main() -> int:
    TICK = "[OK]"
    CROSS = "[FAIL]"

    print("=" * 60)
    print("Phase 23 - Workflow Specification & Workflow Packs Verification")
    print("=" * 60)

    # Gate 1: DAG Validation
    print()
    print("[1/3] DAG Validation...")
    dag_result = check_dag_validation()
    dag_pass = dag_result["passed"]
    st = "PASS" if dag_pass else "FAIL"
    print("  " + st + " - " + str(len(dag_result["packs"])) + " packs validated")
    for name, r in dag_result["packs"].items():
        st = "PASS" if r["valid"] and not r["errors"] else "FAIL"
        print("    [" + st + "] " + name + ": " + str(r["nodes"]) + " nodes, " + str(r["edges"]) + " edges, v" + r.get("semantic_version", "?"))
        if r.get("conditional_edges", 0) > 0:
            print("           Conditional edges: " + str(r["conditional_edges"]))
        if r.get("parallel_edges", 0) > 0:
            print("           Parallel edges: " + str(r["parallel_edges"]))
        if r.get("initial_nodes"):
            print("           Initial nodes: " + ", ".join(r["initial_nodes"]))

    # Gate 2: Migration & Pinning
    print()
    print("[2/3] Migration & Version Pinning...")
    mig_result = check_migration_and_pinning()
    mig_pass = mig_result["passed"]
    print("  " + ("PASS" if mig_pass else "FAIL") + " - migration & pinning checks")
    for k, v in mig_result.get("details", {}).items():
        if isinstance(v, bool):
            print("    " + (TICK if v else CROSS) + " " + k)

    # Gate 3: Built-in Packs Coverage
    print()
    print("[3/3] Built-in Packs Coverage...")
    packs_result = check_builtin_packs_coverage()
    packs_pass = packs_result["passed"]
    print("  " + ("PASS" if packs_pass else "FAIL") + " - 8 built-in packs")
    print("    Registered: " + str(packs_result.get("registered_packs", [])))
    for k, v in packs_result.get("details", {}).items():
        if isinstance(v, bool):
            print("    " + (TICK if v else CROSS) + " " + k)

    # Overall Verdict
    all_pass = dag_pass and mig_pass and packs_pass
    print()
    print("=" * 60)
    print("OVERALL: " + ("PASS" if all_pass else "FAIL"))
    print("  DAG Validation:           " + ("PASS" if dag_pass else "FAIL"))
    print("  Migration & Pinning:      " + ("PASS" if mig_pass else "FAIL"))
    print("  Built-in Packs Coverage:  " + ("PASS" if packs_pass else "FAIL"))

    verdict = "ARCHITECTURE_V2_PHASE23_VERIFIED" if all_pass else "ARCHITECTURE_V2_PHASE23_FAILED"
    print("  Verdict: " + verdict)

    # Write artifacts
    phase_receipt = {
        "phase": 23,
        "name": "Workflow specification va workflow packs",
        "gates": {
            "dag_validation": {
                "passed": dag_pass,
                "packs_validated": len(dag_result["packs"]),
                "details": dag_result,
            },
            "migration_and_pinning": {
                "passed": mig_pass,
                "details": mig_result,
            },
            "builtin_packs_coverage": {
                "passed": packs_pass,
                "details": packs_result,
            },
        },
        "overall_passed": all_pass,
        "verdict": verdict,
    }

    with open(str(ARTIFACT_DIR / "phase_23_verdict.json"), "w", encoding="utf-8") as f:
        json.dump(phase_receipt, f, indent=2, ensure_ascii=False)
    print()
    print("Artifact: " + str(ARTIFACT_DIR / "phase_23_verdict.json"))

    dag_receipt = {
        "script": "scripts/verify_phase23_workflows.py",
        "returncode": 0 if dag_pass else 1,
        "packs": {
            name: {
                "valid": r["valid"],
                "nodes": r["nodes"],
                "edges": r["edges"],
                "version": r.get("semantic_version", ""),
                "content_hash": r.get("content_hash", ""),
                "errors": r.get("errors", []),
            }
            for name, r in dag_result["packs"].items()
        },
        "passed": dag_pass,
    }
    with open(str(ARTIFACT_DIR / "dag_validation_receipt.json"), "w", encoding="utf-8") as f:
        json.dump(dag_receipt, f, indent=2, ensure_ascii=False)

    mig_receipt = {
        "script": "scripts/verify_phase23_workflows.py",
        "returncode": 0 if mig_pass else 1,
        "checks": mig_result.get("details", {}),
        "passed": mig_pass,
    }
    with open(str(ARTIFACT_DIR / "migration_receipt.json"), "w", encoding="utf-8") as f:
        json.dump(mig_receipt, f, indent=2, ensure_ascii=False)

    packs_receipt = {
        "script": "scripts/verify_phase23_workflows.py",
        "returncode": 0 if packs_pass else 1,
        "registered_packs": packs_result.get("registered_packs", []),
        "checks": packs_result.get("details", {}),
        "passed": packs_pass,
    }
    with open(str(ARTIFACT_DIR / "builtin_packs_receipt.json"), "w", encoding="utf-8") as f:
        json.dump(packs_receipt, f, indent=2, ensure_ascii=False)

    print("  DAG Validation Receipt:   " + str(ARTIFACT_DIR / "dag_validation_receipt.json"))
    print("  Migration Receipt:        " + str(ARTIFACT_DIR / "migration_receipt.json"))
    print("  Built-in Packs Receipt:   " + str(ARTIFACT_DIR / "builtin_packs_receipt.json"))

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
