"""
Unit tests for Provider Routing V3 Canonical Model Registry and Equivalence Classifier.
Adheres strictly to ban_ke_hoach.md §PHASE 6 requirements.
"""

import pytest
from windagent_providers.base.contracts import DiscoveredModel
from windagent_providers.registry.model_normalizer import normalize_model_id
from windagent_providers.registry.equivalence import classify_equivalence, EquivalenceLevel
from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService


def test_same_model_via_two_endpoints_exact_revision():
    norm_openai = normalize_model_id("gpt-4o-2024-05-13", default_vendor="openai")
    norm_openrouter = normalize_model_id("openai/gpt-4o-2024-05-13", default_vendor="openrouter")

    assessment = classify_equivalence(norm_openai, norm_openrouter)
    assert assessment.level == EquivalenceLevel.EXACT_REVISION
    assert assessment.confidence == 1.0
    assert assessment.is_failover_eligible is True


def test_different_revisions_not_marked_exact():
    norm_rev1 = normalize_model_id("claude-3-5-sonnet-20240620", default_vendor="anthropic")
    norm_rev2 = normalize_model_id("claude-3-5-sonnet-20241022", default_vendor="anthropic")

    assessment = classify_equivalence(norm_rev1, norm_rev2)
    assert assessment.level == EquivalenceLevel.EXACT_FAMILY_FLOATING_REVISION
    assert assessment.is_failover_eligible is False  # Cannot auto-failover across different revisions!


def test_discovery_rerun_idempotency_and_no_duplicates():
    registry = CanonicalModelRegistryService()

    disc_models = [
        DiscoveredModel(raw_model_id="gpt-4o-2024-05-13", canonical_name="gpt-4o-2024-05-13", provider_id="openai")
    ]

    # First run
    bnd_1 = registry.register_discovery_snapshot(endpoint_id="ep-openai-1", discovered_models=disc_models)
    assert len(bnd_1) == 1
    binding_id_1 = bnd_1[0].id

    # Second run (rerun)
    bnd_2 = registry.register_discovery_snapshot(endpoint_id="ep-openai-1", discovered_models=disc_models)
    assert len(bnd_2) == 1
    assert bnd_2[0].id == binding_id_1  # Reused same binding record, no duplicate created!


def test_failover_candidate_query_only_exact_revision():
    registry = CanonicalModelRegistryService()

    # Register endpoint 1 (OpenAI)
    disc_ep1 = [DiscoveredModel(raw_model_id="gpt-4o-2024-05-13", canonical_name="gpt-4o-2024-05-13", provider_id="openai")]
    b1 = registry.register_discovery_snapshot(endpoint_id="ep-openai-1", discovered_models=disc_ep1)[0]

    # Register endpoint 2 (OpenRouter with same model revision)
    disc_ep2 = [DiscoveredModel(raw_model_id="openai/gpt-4o-2024-05-13", canonical_name="gpt-4o-2024-05-13", provider_id="openrouter")]
    b2 = registry.register_discovery_snapshot(endpoint_id="ep-openrouter-1", discovered_models=disc_ep2)[0]

    canonical_id = b1.canonical_model_id

    # Query exact failover endpoints
    failovers = registry.get_exact_equivalent_endpoints(canonical_id)
    assert len(failovers) == 2
    ep_ids = [f.endpoint_id for f in failovers]
    assert "ep-openai-1" in ep_ids
    assert "ep-openrouter-1" in ep_ids


def test_manual_merge_and_split_audit_trail():
    registry = CanonicalModelRegistryService()

    # Create two canonical models via discovery
    d1 = [DiscoveredModel(raw_model_id="model-a-v1", canonical_name="model-a-v1", provider_id="openai")]
    d2 = [DiscoveredModel(raw_model_id="model-b-v1", canonical_name="model-b-v1", provider_id="anthropic")]

    b1 = registry.register_discovery_snapshot("ep-1", d1)[0]
    b2 = registry.register_discovery_snapshot("ep-2", d2)[0]

    c1_id = b1.canonical_model_id
    c2_id = b2.canonical_model_id

    # Test merge
    merged_ok = registry.merge_canonical_models(source_canonical_id=c1_id, target_canonical_id=c2_id, actor="admin@windagent.ai")
    assert merged_ok is True
    assert b1.canonical_model_id == c2_id

    # Test split
    split_b = registry.split_binding(binding_id=b2.id, new_canonical_name="model-b-standalone", actor="admin@windagent.ai")
    assert split_b is not None
    assert split_b.canonical_model_id != c2_id

    # Audit trail check
    trails = registry.get_audit_trails()
    assert len(trails) == 2
    assert trails[0].action == "merge"
    assert trails[1].action == "split"
    assert trails[0].actor == "admin@windagent.ai"
