"""Unit tests for Agent Runtime Context Assembly Engine (Phase 14)."""

from __future__ import annotations

from windagent.modules.agent_runtime.context.budget import (
    TokenBudgetManager,
)
from windagent.modules.agent_runtime.context.builder import ContextBuilder
from windagent.modules.agent_runtime.context.compaction import (
    ContextCompactor,
)
from windagent.modules.agent_runtime.context.pipeline import (
    STAGE_DEDUPLICATION,
    STAGE_TOKEN_ALLOCATION,
    ContextPipeline,
    ContextPipelineConfig,
)
from windagent.modules.agent_runtime.context.provenance import (
    ContextItem,
    ContextItemProvenance,
    ProvenanceManifest,
    SensitivityLevel,
    SourceType,
)


def test_provenance_and_injection_marker() -> None:
    # Internal content has no injection marker
    prov_internal = ContextItemProvenance(
        source="local_file.py",
        source_type=SourceType.FILE_CONTENT,
        sensitivity=SensitivityLevel.INTERNAL,
        is_external_content=False,
    )
    item_internal = ContextItem(item_id="item_1", content="print('hello')", provenance=prov_internal)
    assert item_internal.injection_marker is None
    assert item_internal.token_count > 0
    assert len(item_internal.content_hash or "") == 64

    # External/browser content automatically gets prompt injection warning
    prov_external = ContextItemProvenance(
        source="https://untrusted.com",
        source_type=SourceType.BROWSER_CONTENT,
        sensitivity=SensitivityLevel.PUBLIC,
        is_external_content=True,
    )
    item_external = ContextItem(item_id="item_2", content="some web text", provenance=prov_external)
    assert item_external.injection_marker is not None
    assert "POTENTIAL PROMPT INJECTION RISK" in item_external.injection_marker


def test_token_budget_profiles_and_large_file_protection() -> None:
    # Task type budget profiles
    manager_bugfix = TokenBudgetManager.for_task_type("bugfix")
    assert manager_bugfix.total_limit == 32000
    assert manager_bugfix.retrieval_context_budget == 12000

    manager_research = TokenBudgetManager.for_task_type("research")
    assert manager_research.total_limit == 128000
    assert manager_research.retrieval_context_budget == 60000

    # Large file protection
    # Budget is 1000 tokens; max single item pct is 25% -> 250 tokens
    budget = TokenBudgetManager(retrieval_context_budget=1000, max_single_item_pct=0.25)

    # 1 item with ~400 tokens (>250 max per item)
    large_content = "x" * 1600  # ~400 tokens
    large_item = ContextItem(
        item_id="large_1",
        content=large_content,
        provenance=ContextItemProvenance(source="large.txt", confidence=1.0),
    )

    # 1 item with ~100 tokens (<250 max)
    normal_content = "y" * 400  # ~100 tokens
    normal_item = ContextItem(
        item_id="normal_1",
        content=normal_content,
        provenance=ContextItemProvenance(source="normal.txt", confidence=1.0),
    )

    fitted, truncated = budget.fit_items([large_item, normal_item])
    # Large item was blocked, normal item was fitted
    assert len(fitted) == 1
    assert fitted[0].item_id == "normal_1"


def test_budget_fitting_priority_by_confidence_and_freshness() -> None:
    budget = TokenBudgetManager(retrieval_context_budget=250, max_single_item_pct=0.5)

    # 3 items, each ~100 tokens (400 chars)
    item_high = ContextItem(
        item_id="high",
        content="a" * 400,
        provenance=ContextItemProvenance(source="a", confidence=0.95, freshness=1.0),
    )
    item_med = ContextItem(
        item_id="med",
        content="b" * 400,
        provenance=ContextItemProvenance(source="b", confidence=0.7, freshness=0.8),
    )
    item_low = ContextItem(
        item_id="low",
        content="c" * 400,
        provenance=ContextItemProvenance(source="c", confidence=0.3, freshness=0.5),
    )

    # Only 2 can fit in 300 tokens budget (budget fits 100 + 100 = 200, 3rd exceeds 300)
    fitted, truncated = budget.fit_items([item_low, item_high, item_med])
    assert len(fitted) == 2
    assert fitted[0].item_id == "high"
    assert fitted[1].item_id == "med"
    assert truncated is True


def test_context_compactor_messages_and_tool_results() -> None:
    compactor = ContextCompactor(artifact_base_uri="artifact://compaction")

    # Message compaction preserving critical keywords
    messages = [
        {"role": "user", "content": "Hello, how are you?"},  # non-critical old
        {"role": "assistant", "content": "Important decision: we will use PostgreSQL."},  # critical keyword "decision"
        {"role": "user", "content": "What about SQLite?"},  # non-critical old
        {"role": "assistant", "content": "Critical invariant: do not use SQLite in production."},  # critical keyword "invariant"
        # 4 recent messages
        {"role": "user", "content": "Recent message 1"},
        {"role": "assistant", "content": "Recent message 2"},
        {"role": "user", "content": "Recent message 3"},
        {"role": "assistant", "content": "Recent message 4"},
    ]

    compacted = compactor.compact_conversation(messages, max_keep_recent=4)
    # Summary message + 2 critical old messages + 4 recent messages = 7 messages
    assert len(compacted) == 7
    assert "[SYSTEM SUMMARY:" in compacted[0]["content"]
    assert "Important decision" in compacted[1]["content"]
    assert "Critical invariant" in compacted[2]["content"]

    # Tool result compaction
    verbose_output = "START " + ("." * 1000) + " END"
    compacted_tool, ref_uri = compactor.compact_tool_result("bash", verbose_output, max_chars=100)
    assert "[TRUNCATED" in compacted_tool
    assert ref_uri.startswith("artifact://compaction/tool_out_")


def test_context_pipeline_and_provenance_manifest() -> None:
    pipeline = ContextPipeline(
        config=ContextPipelineConfig(
            task_type="bugfix",
            enable_deduplication=True,
            enable_compaction=True,
            enable_provenance_manifest=True,
        )
    )

    item1 = ContextItem(
        item_id="f1",
        content="def solve(): return 42",
        provenance=ContextItemProvenance(source="solve.py", source_type=SourceType.FILE_CONTENT),
    )
    # Duplicate item with same content
    item1_dup = ContextItem(
        item_id="f1_dup",
        content="def solve(): return 42",
        provenance=ContextItemProvenance(source="solve_dup.py", source_type=SourceType.FILE_CONTENT),
    )
    item2 = ContextItem(
        item_id="t1",
        content="Execution passed successfully",
        provenance=ContextItemProvenance(source="test_tool", source_type=SourceType.TOOL_OUTPUT),
    )

    res = pipeline.run(
        task_prompt="Fix bug in solve function",
        file_items=[item1, item1_dup],
        tool_output_items=[item2],
    )

    assert res["budget_profile"] == "bugfix"
    # Deduplication removed item1_dup
    assert len(res["items"]) == 2
    assert "manifest" in res

    manifest: ProvenanceManifest = res["manifest"]
    assert manifest.total_items_input == 3
    assert manifest.total_items_output == 2
    assert len(manifest.entries) == 2
    assert STAGE_TOKEN_ALLOCATION in manifest.pipeline_steps
    assert STAGE_DEDUPLICATION in manifest.pipeline_steps


def test_context_builder_assembly() -> None:
    builder = ContextBuilder()

    item = builder.create_context_item(
        item_id="item_10",
        content="class MemoryService: pass",
        source="memory.py",
        source_type="file_content",
    )

    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]

    compacted_msgs, fitted_items, truncated, manifest = builder.assemble_context(
        task_prompt="Review MemoryService",
        messages=messages,
        file_items=[item],
    )

    assert len(compacted_msgs) == 2
    assert len(fitted_items) == 1
    assert truncated is False
    assert manifest is not None
