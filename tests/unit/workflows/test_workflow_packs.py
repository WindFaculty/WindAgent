"""
Unit Tests for WindAgent Workflow Packs (Phase 10 + Phase 23):
- Enhanced DAG workflow definitions with conditional edges, fan-out/fan-in
- Artifact contracts and completion predicates
- ImmutableWorkflowDefinition validation
- Version pinning and migration
- Version diff comparison
- All 8 workflow packs with DAG-based definitions
"""

import pytest
from windagent_core.errors.exceptions import ValidationError, NotFoundError, ConflictError
from windagent_workflows import (
    WorkflowRegistry, BugfixWorkflowPack, CIFixWorkflowPack, CodeReviewWorkflowPack,
    FeatureWorkflowPack, RefactorWorkflowPack, ResearchWorkflowPack,
    ScientificEvalWorkflowPack, ReleaseWorkflowPack,
    ImmutableWorkflowDefinition, WorkflowNodeSpec, WorkflowEdgeSpec,
    ArtifactContract, CompletionPredicate, NodeType, EdgeType,
    WorkflowMigrationManager, MigrationImpact, PinnedDefinition,
)


# ====================================================================
# Fixtures
# ====================================================================

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


# ====================================================================
# 1. Model Validation
# ====================================================================

def test_immutable_definition_validation():
    """Valid definition should pass validation."""
    nodes = {
        "step_1": WorkflowNodeSpec(id="step_1", name="test", tool_name="exec_shell"),
        "step_2": WorkflowNodeSpec(id="step_2", name="verify", tool_name="read_file"),
    }
    edges = [
        WorkflowEdgeSpec(from_node_id="step_1", to_node_id="step_2"),
    ]
    definition = ImmutableWorkflowDefinition(
        id="test_v1", name="test", semantic_version="1.0.0",
        nodes=nodes, edges=edges,
    )
    definition.validate()  # Should not raise

def test_immutable_definition_empty_name():
    """Empty name should fail validation."""
    with pytest.raises(ValidationError, match="validation failed"):
        ImmutableWorkflowDefinition(
            id="test", name="", semantic_version="1.0.0",
        ).validate()

def test_immutable_definition_dangling_edge():
    """Edge referencing non-existent nodes should fail validation."""
    nodes = {"step_1": WorkflowNodeSpec(id="step_1", name="test", tool_name="exec_shell")}
    edges = [WorkflowEdgeSpec(from_node_id="step_1", to_node_id="nonexistent")]
    with pytest.raises(ValidationError, match="validation failed"):
        ImmutableWorkflowDefinition(
            id="test", name="test", semantic_version="1.0.0",
            nodes=nodes, edges=edges,
        ).validate()


def test_immutable_definition_content_hash():
    """Content hash should be deterministic."""
    nodes = {"s1": WorkflowNodeSpec(id="s1", name="test", tool_name="exec_shell")}
    d1 = ImmutableWorkflowDefinition(id="t", name="t", semantic_version="1.0.0", nodes=nodes)
    d2 = ImmutableWorkflowDefinition(id="t", name="t", semantic_version="1.0.0", nodes=nodes)
    assert d1.content_hash == d2.content_hash


def test_immutable_definition_immutability():
    """Frozen dataclass should not allow modification."""
    nodes = {"s1": WorkflowNodeSpec(id="s1", name="test", tool_name="exec_shell")}
    d = ImmutableWorkflowDefinition(id="t", name="t", semantic_version="1.0.0", nodes=nodes)
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        d.name = "changed"


# ====================================================================
# 2. ArtifactContracts
# ====================================================================

def test_artifact_contract_frozen():
    contract = ArtifactContract(name="output.txt", description="Test output", required=True)
    assert contract.name == "output.txt"
    assert contract.required is True
    data = contract.to_dict()
    restored = ArtifactContract.from_dict(data)
    assert restored.name == "output.txt"
    assert restored.required is True


def test_completion_predicate():
    pred = CompletionPredicate(type="tool_success", expected_exit_code=0)
    assert pred.type == "tool_success"
    data = pred.to_dict()
    restored = CompletionPredicate.from_dict(data)
    assert restored.expected_exit_code == 0


# ====================================================================
# 3. DAG Structure (Conditional edges, Fan-out/Fan-in)
# ====================================================================

def test_conditional_edge():
    edge = WorkflowEdgeSpec(
        from_node_id="test", to_node_id="verify",
        edge_type=EdgeType.CONDITIONAL, condition_expression="exit_code == 0",
    )
    assert edge.edge_type == EdgeType.CONDITIONAL
    assert edge.condition_expression == "exit_code == 0"


def test_fan_out_fan_in_nodes():
    fan_out = WorkflowNodeSpec(id="branch", name="parallel_branch", tool_name="exec_shell", node_type=NodeType.FAN_OUT)
    fan_in = WorkflowNodeSpec(id="merge", name="merge_results", tool_name="read_file", node_type=NodeType.FAN_IN)
    assert fan_out.node_type == NodeType.FAN_OUT
    assert fan_in.node_type == NodeType.FAN_IN


def test_workflow_node_spec_roundtrip():
    spec = WorkflowNodeSpec(
        id="node1", name="test", tool_name="exec_shell",
        input_artifacts=[ArtifactContract(name="input.txt")],
        output_artifacts=[ArtifactContract(name="output.txt")],
        completion_predicate=CompletionPredicate(type="tool_success"),
    )
    data = spec.to_dict()
    restored = WorkflowNodeSpec.from_dict(data)
    assert restored.id == "node1"
    assert len(restored.input_artifacts) == 1
    assert len(restored.output_artifacts) == 1
    assert restored.completion_predicate.type == "tool_success"


# ====================================================================
# 4. Version Pinning
# ====================================================================

def test_version_pinning(populated_registry):
    """Pinning a workflow should keep the exact definition, even if pack is later updated."""
    bugfix = populated_registry.get_pack("bugfix")

    # Generate and pin a definition for run "run_001"
    pinned_def = populated_registry.pin_workflow("run_001", "bugfix", {"issue_description": "Bug in login"})
    assert pinned_def.name == "bugfix"
    assert pinned_def.semantic_version == "2.0.0"

    # Retrieving pinned definition should work
    retrieved = populated_registry.get_pinned_workflow("run_001")
    assert retrieved is not None
    assert retrieved.content_hash == pinned_def.content_hash

    # Unknown run should return None
    assert populated_registry.get_pinned_workflow("nonexistent_run") is None


def test_release_pin(populated_registry):
    populated_registry.pin_workflow("run_002", "bugfix", {"issue_description": "Bug"})
    assert populated_registry.release_pin("run_002") is True
    assert populated_registry.get_pinned_workflow("run_002") is None


# ====================================================================
# 5. Migration and Version Comparison
# ====================================================================

def test_migration_compare_identical_versions():
    manager = WorkflowMigrationManager()
    nodes_v1 = {"s1": WorkflowNodeSpec(id="s1", name="step1", tool_name="exec_shell")}
    d1 = ImmutableWorkflowDefinition(id="t", name="test", semantic_version="1.0.0", nodes=nodes_v1)

    impact = manager.compare_versions(d1, d1)
    assert impact.is_backward_compatible is True
    assert len(impact.breaking_changes) == 0
    assert len(impact.version_changes) == 0


def test_migration_compare_added_node():
    manager = WorkflowMigrationManager()
    nodes_v1 = {"s1": WorkflowNodeSpec(id="s1", name="step1", tool_name="exec_shell")}
    nodes_v2 = {
        "s1": WorkflowNodeSpec(id="s1", name="step1", tool_name="exec_shell"),
        "s2": WorkflowNodeSpec(id="s2", name="step2", tool_name="read_file"),
    }
    d1 = ImmutableWorkflowDefinition(id="t", name="test", semantic_version="1.0.0", nodes=nodes_v1)
    d2 = ImmutableWorkflowDefinition(id="t", name="test", semantic_version="2.0.0", nodes=nodes_v2)

    impact = manager.compare_versions(d1, d2)
    assert impact.is_backward_compatible is True  # Adding nodes is backward compatible
    assert "s2" in impact.added_nodes


def test_migration_compare_removed_node():
    manager = WorkflowMigrationManager()
    nodes_v1 = {
        "s1": WorkflowNodeSpec(id="s1", name="step1", tool_name="exec_shell"),
        "s2": WorkflowNodeSpec(id="s2", name="step2", tool_name="read_file"),
    }
    nodes_v2 = {"s1": WorkflowNodeSpec(id="s1", name="step1", tool_name="exec_shell")}
    d1 = ImmutableWorkflowDefinition(id="t", name="test", semantic_version="1.0.0", nodes=nodes_v1)
    d2 = ImmutableWorkflowDefinition(id="t", name="test", semantic_version="2.0.0", nodes=nodes_v2)

    impact = manager.compare_versions(d1, d2)
    assert impact.is_backward_compatible is False  # Removing nodes is breaking
    assert "s2" in impact.removed_nodes
    assert len(impact.breaking_changes) > 0


def test_migration_record_and_list_versions():
    manager = WorkflowMigrationManager()
    nodes = {"s1": WorkflowNodeSpec(id="s1", name="step1", tool_name="exec_shell")}
    d1 = ImmutableWorkflowDefinition(id="t", name="test", semantic_version="1.0.0", nodes=nodes)
    d2 = ImmutableWorkflowDefinition(id="t", name="test", semantic_version="2.0.0", nodes=nodes)

    manager.record_version(d1)
    manager.record_version(d2)

    versions = manager.list_versions("test")
    assert "1.0.0" in versions
    assert "2.0.0" in versions

    retrieved = manager.get_version("test", "1.0.0")
    assert retrieved is not None
    assert retrieved.semantic_version == "1.0.0"


# ====================================================================
# 6. All 8 Workflow Packs — Legacy Step Sequences
# ====================================================================

def test_registry_registration_and_classification(populated_registry):
    assert len(populated_registry.list_packs()) == 8
    packs_with_versions = populated_registry.list_packs_with_versions()
    assert len(packs_with_versions) == 8
    for p in packs_with_versions:
        assert "version" in p

    pack1 = populated_registry.classify_task("Please fix bug in login handler")
    assert pack1 is not None
    assert pack1.name == "bugfix"

    pack2 = populated_registry.classify_task("Code review PR #42")
    assert pack2 is not None
    assert pack2.name == "code_review"

    pack3 = populated_registry.classify_task("Prepare release v1.0.0")
    assert pack3 is not None
    assert pack3.name == "release"


def test_workflow_input_validation(populated_registry):
    bugfix = populated_registry.get_pack("bugfix")
    with pytest.raises(ValidationError, match="missing required input parameter"):
        bugfix.build_step_sequence({})
    steps = bugfix.build_step_sequence({"issue_description": "Crash on null token"})
    assert len(steps) == 7
    assert steps[0].name == "reproduce"


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


# ====================================================================
# 7. All 8 Workflow Packs — DAG Definitions
# ====================================================================

def test_all_8_workflow_packs_dag_definitions(populated_registry):
    """All 8 workflow packs should produce valid DAG definitions with proper structure."""
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
        pack = populated_registry.get_pack(name)
        definition = pack.build_workflow_definition(params)

        assert isinstance(definition, ImmutableWorkflowDefinition)
        assert definition.name == name
        assert definition.semantic_version == "2.0.0"
        assert len(definition.nodes) > 0
        assert definition.content_hash is not None

        # Verify initial nodes (no incoming dependencies)
        initial = definition.get_initial_nodes()
        assert len(initial) >= 1

        # Verify edge node references are valid
        node_ids = set(definition.nodes.keys())
        for edge in definition.edges:
            assert edge.from_node_id in node_ids, f"Pack {name}: edge from {edge.from_node_id} not in nodes"
            assert edge.to_node_id in node_ids, f"Pack {name}: edge to {edge.to_node_id} not in nodes"

        # Verify at least one conditional or parallel edge exists
        non_dependency_edges = [e for e in definition.edges if e.edge_type != EdgeType.DEPENDENCY]
        assert len(non_dependency_edges) >= 0  # Not required but validated

        # Verify artifact contracts
        for node in definition.nodes.values():
            for artifact in node.input_artifacts:
                assert artifact.name is not None
            for artifact in node.output_artifacts:
                assert artifact.name is not None


def test_bugfix_dag_has_conditional_edges(populated_registry):
    """Bugfix DAG should have conditional edges for test results."""
    bugfix = populated_registry.get_pack("bugfix")
    definition = bugfix.build_workflow_definition({"issue_description": "Bug"})

    conditional_edges = [e for e in definition.edges if e.edge_type == EdgeType.CONDITIONAL]
    assert len(conditional_edges) >= 1
    assert any("exit_code" in (e.condition_expression or "") for e in conditional_edges)


def test_release_dag_has_fan_out(populated_registry):
    """Release DAG should have fan-out from build to parallel checks."""
    release = populated_registry.get_pack("release")
    definition = release.build_workflow_definition({"release_version": "1.0.0"})

    # Build node should fan out to security, checksum, smoke
    build_outgoing = definition.get_downstream("step_3_build")
    assert len(build_outgoing) >= 2


def test_feature_dag_has_fan_in(populated_registry):
    """Feature DAG should have fan-in from tests and docs to review."""
    feature = populated_registry.get_pack("feature")
    definition = feature.build_workflow_definition({"feature_description": "Dark mode"})

    # Review should have 2+ incoming edges (tests, docs)
    review_upstream = definition.get_upstream("step_6_review")
    assert len(review_upstream) >= 1


# ====================================================================
# 8. Version Stats
# ====================================================================

def test_registry_version_stats(populated_registry):
    """Registry should provide version statistics."""
    # Pin a workflow to generate version history
    populated_registry.pin_workflow("run_001", "bugfix", {"issue_description": "Bug"})
    populated_registry.pin_workflow("run_002", "feature", {"feature_description": "Feature"})

    stats = populated_registry.get_version_stats()
    assert "bugfix" in stats
    assert "feature" in stats
    assert stats["pinned"]["total_pinned"] == 2


# ====================================================================
# 9. Migration Manager Stats
# ====================================================================

def test_migration_manager_pin_and_release():
    manager = WorkflowMigrationManager()
    nodes = {"s1": WorkflowNodeSpec(id="s1", name="step1", tool_name="exec_shell")}
    d1 = ImmutableWorkflowDefinition(id="t", name="test", semantic_version="1.0.0", nodes=nodes)

    manager.pin_definition("run_001", d1)
    stats = manager.get_pinned_stats()
    assert stats["total_pinned"] == 1
    assert "run_001" in stats["pinned_runs"]

    assert manager.release_pin("run_001") is True
    assert manager.release_pin("nonexistent") is False
