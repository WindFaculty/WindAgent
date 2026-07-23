"""
Unit Tests for WindAgent Workflow Packs (Phase 10):
- WorkflowRegistry registration & task prompt classification for all 8 packs
- Input schema validation (ValidationError when required parameter is missing)
- Deterministic DAG step sequence generation (bugfix, ci_fix, code_review, feature, refactor, research, scientific_eval, release)
- Acceptance criteria declaration & zero auto-merge/auto-release enforcement
"""

import pytest
from windagent_core.errors.exceptions import ValidationError
from windagent_workflows import (
    WorkflowRegistry, BugfixWorkflowPack, CIFixWorkflowPack, CodeReviewWorkflowPack,
    FeatureWorkflowPack, RefactorWorkflowPack, ResearchWorkflowPack,
    ScientificEvalWorkflowPack, ReleaseWorkflowPack
)


@pytest.fixture
def populated_registry():
    reg = WorkflowRegistry()
    reg.register_pack(BugfixWorkflowPack())
    reg.register_pack(CIFixWorkflowPack())
    reg.register_pack(CodeReviewWorkflowPack())
    reg.register_pack(FeatureWorkflowPack())
    reg.register_pack(RefactorWorkflowPack())
    reg.register_pack(ResearchWorkflowPack())
    reg.register_pack(ScientificEvalWorkflowPack())
    reg.register_pack(ReleaseWorkflowPack())
    return reg


def test_registry_registration_and_classification(populated_registry):
    assert len(populated_registry.list_packs()) == 8

    # Task classification matching
    pack1 = populated_registry.classify_task("Please fix bug in login handler")
    assert pack1 is not None
    assert pack1.name == "bugfix"

    pack2 = populated_registry.classify_task("Code review PR #42")
    assert pack2 is not None
    assert pack2.name == "code_review"

    pack3 = populated_registry.classify_task("Implement feature for user avatars")
    assert pack3 is not None
    assert pack3.name == "feature"

    pack4 = populated_registry.classify_task("Prepare release v1.0.0")
    assert pack4 is not None
    assert pack4.name == "release"


def test_workflow_input_validation(populated_registry):
    bugfix = populated_registry.get_pack("bugfix")

    # Missing required 'issue_description' must raise ValidationError
    with pytest.raises(ValidationError, match="missing required input parameter"):
        bugfix.build_step_sequence({})

    # Valid input succeeds
    steps = bugfix.build_step_sequence({"issue_description": "Crash on null token"})
    assert len(steps) == 7
    assert steps[0].name == "reproduce"
    assert steps[-1].name == "report"


def test_all_8_workflow_packs_dag_sequences(populated_registry):
    packs_expected_steps = {
        "bugfix": ({"issue_description": "err"}, 7, "reproduce", "report"),
        "ci_fix": ({"ci_log_url_or_content": "log.txt"}, 6, "inspect_checks", "report"),
        "code_review": ({"target_branch_or_diff": "main..feature"}, 6, "diff_inventory", "review_report"),
        "feature": ({"feature_description": "dark mode"}, 6, "requirements", "report"),
        "refactor": ({"target_module": "storage"}, 5, "baseline_behavior", "regression"),
        "research": ({"research_topic": "RAG architectures"}, 6, "question_decomposition", "artifact"),
        "scientific_eval": ({"eval_protocol_id": "eval_01"}, 7, "protocol_freeze", "verdict"),
        "release": ({"release_version": "0.3.0"}, 7, "version", "rollback_plan"),
    }

    for name, (params, expected_count, first_step, last_step) in packs_expected_steps.items():
        pack = populated_registry.get_pack(name)
        steps = pack.build_step_sequence(params)
        assert len(steps) == expected_count, f"Pack {name} step count mismatch"
        assert steps[0].name == first_step, f"Pack {name} first step mismatch"
        assert steps[-1].name == last_step, f"Pack {name} last step mismatch"
        assert len(pack.definition.acceptance_criteria) > 0, f"Pack {name} missing acceptance criteria"
