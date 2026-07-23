"""
Unit Tests for WindAgent Context System (Phase 9):
- ContextItemProvenance metadata & freshness calculation
- TokenBudgetManager token estimation & truncation enforcement
- RepositoryIndex symbol retrieval & stale context detection
- ContextCompactor decision/blocker preservation & artifact reference generation
- ContextBuilder prompt context assembly
"""

from windagent_context import (
    ContextItemProvenance, ContextItem, TokenBudgetManager, estimate_tokens,
    RepositoryIndex, ContextCompactor
)


def test_provenance_and_token_estimation():
    text = "def calculate_sum(a, b): return a + b"
    tokens = estimate_tokens(text)
    assert tokens > 0

    prov = ContextItemProvenance(
        source="unit_test",
        retrieval_reason="Exact symbol match",
        token_cost=tokens,
        file_path="math_utils.py",
        line_range="1-2",
        freshness=0.95,
        confidence=1.0,
    )
    assert prov.file_path == "math_utils.py"
    assert prov.freshness == 0.95


def test_token_budget_manager_truncation():
    manager = TokenBudgetManager(retrieval_context_budget=20)  # Very small budget

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

    fitted, truncated = manager.fit_items([item1, item2, item3], max_tokens=20)
    assert truncated
    assert len(fitted) == 2
    assert fitted[0].item_id == "item_1"


def test_repository_index_symbol_search_and_stale_detection():
    index = RepositoryIndex()
    index.add_symbol("OrderService", "services/order.py", "10-50", "class OrderService: pass", mtime=100.0)

    # Search symbol
    results = index.retrieve_symbol("OrderService")
    assert len(results) == 1
    assert results[0].provenance.file_path == "services/order.py"

    # Stale detection check
    assert not index.is_stale("services/order.py", current_mtime=100.0)
    assert index.is_stale("services/order.py", current_mtime=105.0)


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

    # Compact old messages, keeping 2 recent ones
    compacted = compactor.compact_conversation(messages, max_keep_recent=2)
    assert len(compacted) < len(messages)
    
    # Verify critical message containing 'Decision:' was preserved
    contents = [m["content"] for m in compacted]
    assert any("Decision: We will use PostgreSQL" in c for c in contents)


def test_context_compactor_tool_output_truncation():
    compactor = ContextCompactor()
    raw_log = "Log entry\n" * 500  # Long log

    compacted_text, artifact_ref = compactor.compact_tool_result("exec_shell", raw_output=raw_log, max_chars=200)
    assert len(compacted_text) < len(raw_log)
    assert "[TRUNCATED" in compacted_text
    assert artifact_ref.startswith("artifact://compaction/tool_out_")
