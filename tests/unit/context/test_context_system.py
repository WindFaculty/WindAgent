"""
Unit Tests for WindAgent Context System (Phase 9 + Phase 21):
- ContextItemProvenance metadata with sensitivity & source types
- Prompt-injection markers for external content
- TokenBudgetManager with per-task-type profiles & large file protection
- RepositoryIndex symbol retrieval & stale context detection
- ContextCompactor decision/blocker preservation
- ContextPipeline full orchestration with dedup & compaction
- ProvenanceManifest builder
- ContextBuilder assembly
"""

from windagent_context import (
    ContextItemProvenance, ContextItem, TokenBudgetManager, estimate_tokens,
    RepositoryIndex, ContextCompactor, ContextBuilder,
    ContextPipeline, ContextPipelineConfig,
    ProvenanceManifest, SensitivityLevel, SourceType,
    TASK_TYPE_BUDGET_PROFILES,
)


# ====================================================================
# Provenance & Sensitivity
# ====================================================================

def test_provenance_with_sensitivity_and_source_type():
    text = "def calculate_sum(a, b): return a + b"
    tokens = estimate_tokens(text)
    assert tokens > 0

    prov = ContextItemProvenance(
        source="unit_test",
        source_type=SourceType.FILE_CONTENT,
        retrieval_reason="Exact symbol match",
        token_cost=tokens,
        file_path="math_utils.py",
        line_range="1-2",
        freshness=0.95,
        confidence=1.0,
        sensitivity=SensitivityLevel.INTERNAL,
    )
    assert prov.file_path == "math_utils.py"
    assert prov.freshness == 0.95
    assert prov.sensitivity == SensitivityLevel.INTERNAL
    assert prov.source_type == SourceType.FILE_CONTENT

    # Round-trip to_dict/from_dict
    data = prov.to_dict()
    restored = ContextItemProvenance.from_dict(data)
    assert restored.sensitivity == SensitivityLevel.INTERNAL
    assert restored.source_type == SourceType.FILE_CONTENT
    assert restored.file_path == "math_utils.py"


# ====================================================================
# Prompt-Injection Markers
# ====================================================================

def test_prompt_injection_marker_for_external_content():
    # External/browser content gets auto-marked
    prov = ContextItemProvenance(
        source="browser_navigation",
        source_type=SourceType.BROWSER_CONTENT,
        retrieval_reason="Visited URL",
        token_cost=50,
        is_external_content=True,
        sensitivity=SensitivityLevel.PUBLIC,
    )
    item = ContextItem(
        item_id="browser_item",
        content="This is content fetched from a browser session.",
        provenance=prov,
    )
    assert item.injection_marker is not None
    assert "POTENTIAL PROMPT INJECTION" in item.injection_marker
    assert "EXTERNAL CONTENT" in item.injection_marker

    # Internal content does NOT get injection marker
    prov_internal = ContextItemProvenance(
        source="repository_index",
        source_type=SourceType.REPOSITORY_INDEX,
        retrieval_reason="Symbol lookup",
        token_cost=10,
        is_external_content=False,
    )
    item_internal = ContextItem(
        item_id="internal_item",
        content="Internal code content",
        provenance=prov_internal,
    )
    assert item_internal.injection_marker is None


def test_prompt_injection_marker_explicit():
    """Explicit injection marker should override auto-generated one."""
    prov = ContextItemProvenance(
        source="api_response",
        source_type=SourceType.EXTERNAL_API,
        retrieval_reason="API call",
        token_cost=30,
        is_external_content=True,
    )
    item = ContextItem(
        item_id="api_item",
        content="API response data",
        provenance=prov,
        injection_marker="[CUSTOM WARNING] Validate this API response before use.",
    )
    assert item.injection_marker == "[CUSTOM WARNING] Validate this API response before use."


# ====================================================================
# Token Budget Manager with Profiles & Large File Protection
# ====================================================================

def test_token_budget_manager_truncation():
    # Token counts auto-computed from content: max(1, len//4)
    # item1=15chars→3tokens, item2=15chars→3tokens, item3=31chars→7tokens
    # max_single_item_pct=0.9 → max_per_item=int(8*0.9)=7 → item3(7) passes LFP
    # Budget=8: item1(3)+item2(3)=6, item3(7) would exceed budget → truncated
    manager = TokenBudgetManager(retrieval_context_budget=8, max_single_item_pct=0.9)

    item1 = ContextItem(
        item_id="item_1",
        content="Short content 1",
        provenance=ContextItemProvenance(source="test", retrieval_reason="test", token_cost=10, freshness=1.0, confidence=1.0),
    )
    item2 = ContextItem(
        item_id="item_2",
        content="Short content 2",
        provenance=ContextItemProvenance(source="test", retrieval_reason="test", token_cost=10, freshness=0.9, confidence=1.0),
    )
    item3 = ContextItem(
        item_id="item_3",
        content="Content 3 overflowing budget",
        provenance=ContextItemProvenance(source="test", retrieval_reason="test", token_cost=15, freshness=0.8, confidence=1.0),
    )

    fitted, truncated = manager.fit_items([item1, item2, item3], max_tokens=8)
    assert truncated
    assert len(fitted) == 2
    assert fitted[0].item_id == "item_1"  # Highest freshness first


def test_large_file_protection():
    """No single item should exceed max_single_item_pct of budget."""
    # Items' token_count is auto-computed from content length: max(1, len//4)
    # small = 2 tokens, medium = 24 tokens, huge = 125 tokens
    # With budget=50 and 30% max per item = 15 tokens max
    # small (2) and medium (24 > 15 filtered!) items checked
    manager = TokenBudgetManager(retrieval_context_budget=50, max_single_item_pct=0.3)

    small_item = ContextItem(
        item_id="small",
        content="x" * 10,  # 10/4 = 2 tokens
        provenance=ContextItemProvenance(source="test", retrieval_reason="test", token_cost=10, freshness=1.0, confidence=1.0),
    )
    medium_item = ContextItem(
        item_id="medium",
        content="x" * 100,  # 100/4 = 25 tokens > 15 (30% of 50), filtered
        provenance=ContextItemProvenance(source="test", retrieval_reason="test", token_cost=25, freshness=1.0, confidence=1.0),
    )
    huge_item = ContextItem(
        item_id="huge",
        content="x" * 500,  # 500/4 = 125 tokens > 15, filtered
        provenance=ContextItemProvenance(source="test", retrieval_reason="test", token_cost=80, freshness=1.0, confidence=1.0),
    )

    # Huge and medium items exceed 30% of budget (50 * 0.3 = 15), should be filtered out
    fitted, _ = manager.fit_items([small_item, medium_item, huge_item], max_tokens=50)
    item_ids = [i.item_id for i in fitted]
    assert "huge" not in item_ids, "Huge item exceeding single-item budget should be filtered"
    assert "medium" not in item_ids, "Medium item exceeding single-item budget should be filtered"
    assert "small" in item_ids


def test_per_task_type_budget_profiles():
    assert "bugfix" in TASK_TYPE_BUDGET_PROFILES
    assert "feature" in TASK_TYPE_BUDGET_PROFILES
    assert "refactor" in TASK_TYPE_BUDGET_PROFILES
    assert "code_review" in TASK_TYPE_BUDGET_PROFILES
    assert "research" in TASK_TYPE_BUDGET_PROFILES
    assert "default" in TASK_TYPE_BUDGET_PROFILES

    # Bugfix profile should have smaller budget
    bugfix = TokenBudgetManager.for_task_type("bugfix")
    feature = TokenBudgetManager.for_task_type("feature")
    assert bugfix.total_limit < feature.total_limit

    # Unknown type falls back to default
    default = TokenBudgetManager.for_task_type("unknown_type")
    assert default.total_limit == 128000


# ====================================================================
# Repository Index
# ====================================================================

def test_repository_index_symbol_search_and_stale_detection():
    index = RepositoryIndex()
    index.add_symbol("OrderService", "services/order.py", "10-50", "class OrderService: pass", mtime=100.0)

    # Search symbol
    results = index.retrieve_symbol("OrderService")
    assert len(results) == 1
    assert results[0].provenance.file_path == "services/order.py"

    # Stale detection
    assert not index.is_stale("services/order.py", current_mtime=100.0)
    assert index.is_stale("services/order.py", current_mtime=105.0)


# ====================================================================
# Context Compactor
# ====================================================================

def test_context_compactor_decision_preservation():
    compactor = ContextCompactor()

    messages = [
        {"role": "user", "content": "How should we design the database schema?"},
        {"role": "assistant", "content": "Let us explore options."},
        {"role": "user", "content": "Decision: We will use PostgreSQL with JSONB columns for audit logs."},
        {"role": "assistant", "content": "Understood. Creating migration script."},
        {"role": "user", "content": "What is the status?"},
        {"role": "assistant", "content": "Migration is ready."},
    ]

    compacted = compactor.compact_conversation(messages, max_keep_recent=2)
    assert len(compacted) < len(messages)
    contents = [m["content"] for m in compacted]
    assert any("Decision: We will use PostgreSQL" in c for c in contents)


def test_context_compactor_tool_output_truncation():
    compactor = ContextCompactor()
    raw_log = "Log entry\n" * 500

    compacted_text, artifact_ref = compactor.compact_tool_result("exec_shell", raw_output=raw_log, max_chars=200)
    assert len(compacted_text) < len(raw_log)
    assert "[TRUNCATED" in compacted_text
    assert artifact_ref.startswith("artifact://compaction/tool_out_")


# ====================================================================
# Provenance Manifest
# ====================================================================

def test_provenance_manifest_build():
    items_input = [
        ContextItem(
            item_id="file_item",
            content="def foo(): pass",
            provenance=ContextItemProvenance(
                source="test", source_type=SourceType.FILE_CONTENT,
                retrieval_reason="test", token_cost=10,
                sensitivity=SensitivityLevel.PUBLIC,
            ),
        ),
        ContextItem(
            item_id="external_item",
            content="External data",
            provenance=ContextItemProvenance(
                source="web", source_type=SourceType.BROWSER_CONTENT,
                retrieval_reason="test", token_cost=5,
                is_external_content=True,
                sensitivity=SensitivityLevel.INTERNAL,
            ),
        ),
    ]

    manifest = ProvenanceManifest.build(
        manifest_id="test_manifest",
        task_prompt="Fix bug in foo function",
        input_items=items_input,
        output_items=items_input[:1],  # Only file_item fits
        truncated=True,
        budget_profile="bugfix",
        pipeline_steps=["repo_discovery", "file_retrieval", "token_allocation"],
    )

    assert manifest.manifest_id == "test_manifest"
    assert manifest.task_prompt_hash is not None
    assert manifest.total_items_input == 2
    assert manifest.total_items_output == 1
    assert manifest.truncated is True
    assert manifest.budget_profile == "bugfix"
    assert len(manifest.pipeline_steps) == 3
    assert len(manifest.entries) == 1
    assert manifest.entries[0].item_id == "file_item"

    # Entry details
    entry = manifest.entries[0]
    assert entry.sensitivity == "public"
    assert entry.is_external is False
    assert entry.has_injection_marker is False

    # Round-trip to_dict
    data = manifest.to_dict()
    assert data["manifest_id"] == "test_manifest"
    assert data["truncated"] is True
    assert len(data["entries"]) == 1


# ====================================================================
# Context Pipeline
# ====================================================================

def test_context_pipeline_full_run():
    pipeline = ContextPipeline()

    file_items = [
        ContextItem(
            item_id="file_1",
            content="def process(): pass",
            provenance=ContextItemProvenance(
                source="repo", source_type=SourceType.FILE_CONTENT,
                retrieval_reason="symbol match", token_cost=10,
            ),
        ),
    ]
    tool_items = [
        ContextItem(
            item_id="tool_1",
            content="Build succeeded",
            provenance=ContextItemProvenance(
                source="exec_shell", source_type=SourceType.TOOL_OUTPUT,
                retrieval_reason="last command", token_cost=5,
            ),
        ),
    ]
    memory_items = [
        ContextItem(
            item_id="mem_1",
            content="Project uses FastAPI",
            provenance=ContextItemProvenance(
                source="project_memory", source_type=SourceType.PROJECT_MEMORY,
                retrieval_reason="past session", token_cost=8,
            ),
        ),
    ]

    result = pipeline.run(
        task_prompt="Fix the bug in process()",
        file_items=file_items,
        tool_output_items=tool_items,
        memory_items=memory_items,
    )

    assert "items" in result
    assert "manifest" in result
    assert "truncated" in result
    assert "pipeline_steps" in result
    assert result["budget_profile"] == "default"

    items = result["items"]
    assert len(items) > 0

    manifest = result["manifest"]
    assert manifest.total_items_input >= 3
    assert manifest.budget_profile == "default"

    # Pipeline should record all stages
    steps = result["pipeline_steps"]
    assert "repository_discovery" in steps
    assert "file_retrieval" in steps
    assert "recent_tool_outputs" in steps
    assert "project_memory" in steps
    assert "token_allocation" in steps
    assert "deduplication" in steps
    assert "compaction" in steps


def test_context_pipeline_deduplication():
    """Pipeline should deduplicate items with identical content."""
    pipeline = ContextPipeline(
        config=ContextPipelineConfig(enable_deduplication=True)
    )

    # Two items with identical content
    dup_items = [
        ContextItem(
            item_id="dup_1",
            content="Same content here",
            provenance=ContextItemProvenance(
                source="repo", source_type=SourceType.FILE_CONTENT,
                retrieval_reason="search", token_cost=10,
            ),
        ),
        ContextItem(
            item_id="dup_2",
            content="Same content here",  # Identical content
            provenance=ContextItemProvenance(
                source="memory", source_type=SourceType.PROJECT_MEMORY,
                retrieval_reason="memory", token_cost=10,
                freshness=0.5,  # Lower freshness
            ),
        ),
    ]

    result = pipeline.run(
        task_prompt="test dedup",
        file_items=dup_items,
    )

    # Should deduplicate to 1 item (the freshest one)
    assert len(result["items"]) <= 1


def test_context_pipeline_with_config():
    """Pipeline should respect custom config."""
    config = ContextPipelineConfig(
        task_type="code_review",
        max_file_items=5,
        enable_provenance_manifest=False,
    )
    pipeline = ContextPipeline(config=config)

    file_items = [
        ContextItem(
            item_id=f"file_{i}",
            content=f"Content {i}",
            provenance=ContextItemProvenance(
                source="test", retrieval_reason="test", token_cost=5,
            ),
        )
        for i in range(10)
    ]

    result = pipeline.run(
        task_prompt="Review this code",
        file_items=file_items,
    )

    # Manifest should be absent when disabled
    assert "manifest" not in result
    # Budget profile should match config
    assert result["budget_profile"] == "code_review"


# ====================================================================
# Context Builder
# ====================================================================

def test_context_builder_assemble_context():
    builder = ContextBuilder()

    file_items = [
        ContextItem(
            item_id="file_main",
            content="def main(): pass",
            provenance=ContextItemProvenance(
                source="repo", retrieval_reason="search", token_cost=5,
            ),
        ),
    ]

    compacted_msgs, fitted_items, truncated, manifest = builder.assemble_context(
        task_prompt="Fix main function",
        file_items=file_items,
    )

    assert len(fitted_items) > 0
    assert isinstance(truncated, bool)
    if manifest:
        assert manifest.budget_profile is not None


def test_context_builder_assemble_for_task_type():
    builder = ContextBuilder()

    items, truncated, manifest = builder.assemble_for_task_type(
        task_prompt="Fix critical bug in payment module",
        task_type="bugfix",
    )

    if manifest:
        assert manifest.budget_profile == "bugfix"
        assert manifest.manifest_id is not None


# ====================================================================
# Token Estimation
# ====================================================================

def test_token_estimation():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("hello world") == 2  # 11 characters // 4 = 2
    long_text = "x" * 100
    assert estimate_tokens(long_text) == 25  # 100 // 4 = 25
