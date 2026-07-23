"""
Unit tests for Provider Routing V3 Contracts, Error Taxonomy, Secret Redaction, and Import Boundaries.
Adheres strictly to ban_ke_hoach.md §PHASE 1 requirements.
"""

import sys
import pytest
from datetime import datetime, timezone

from windagent_providers.base.contracts import (
    CacheDirective, ConnectionTestResult, DiscoveredModel, FinishReason,
    ModelDescriptor, ProtocolDetectionResult, ProviderCapabilities, ProviderHealth,
    ProviderRequest, ProviderResponse, ProviderStreamEvent, ProviderUsage, QuotaState,
    RateLimitState
)
from windagent_providers.base.errors import (
    AuthenticationFailure, CancellationFailure, ContentPolicyFailure, ContextOverflowFailure,
    InvalidRequestFailure, MalformedResponseFailure, ModelNotFoundFailure, NetworkFailure,
    PermissionFailure, ProtocolMismatchFailure, ProviderFailure, ProviderUnavailableFailure,
    QuotaExhaustedFailure, RateLimitFailure, SameModelEndpointExhausted, TimeoutFailure
)
from windagent_providers.base.ports import (
    CachePort, CanonicalModelRegistryPort, EndpointRegistryPort, EndpointStatePort,
    QuotaStatePort, RouteAttemptPort, RouteLockPort, UsageLedgerPort
)
from windagent_providers.base.secret_redaction import redact_dict, redact_text
from windagent_providers.base.capabilities import ModelCapability, ModelCapabilityProfile


def test_provider_request_defaults_and_construction():
    request = ProviderRequest(
        messages=[{"role": "user", "content": "Hello World"}],
        system_instruction="You are a helpful assistant.",
        temperature=0.7,
        max_output_tokens=1000,
        tools=[{"type": "function", "function": {"name": "test_tool"}}],
        image_parts=[{"type": "image_url", "url": "https://example.com/image.png"}],
        request_id="req-12345",
        timeout_seconds=45.0,
    )
    assert request.messages[0]["content"] == "Hello World"
    assert request.system_instruction == "You are a helpful assistant."
    assert request.temperature == 0.7
    assert request.max_output_tokens == 1000
    assert len(request.tools) == 1
    assert len(request.image_parts) == 1
    assert request.request_id == "req-12345"
    assert request.timeout_seconds == 45.0


def test_provider_response_normalization_and_metadata_redaction():
    response = ProviderResponse(
        canonical_model_id="gpt-4o",
        provider_model_id="gpt-4o-2024-05-13",
        endpoint_id="ep-openai-primary",
        text="Sample output text",
        finish_reason=FinishReason.STOP.value,
        usage=ProviderUsage(prompt_tokens=10, completion_tokens=20, cached_tokens=5),
        total_latency_ms=125.5,
        raw_metadata={
            "headers": {"authorization": "Bearer sk-proj-1234567890abcdef12345678"},
            "api_key": "sk-12345678901234567890",
            "normal_key": "value"
        }
    )
    assert response.canonical_model_id == "gpt-4o"
    assert response.text == "Sample output text"
    assert response.usage.prompt_tokens == 10
    assert response.usage.completion_tokens == 20
    assert response.usage.cached_tokens == 5
    assert response.usage.total_tokens == 30  # Auto calculated post-init
    assert response.finish_reason == "stop"
    
    # Metadata should be automatically redacted
    assert "sk-proj" not in str(response.raw_metadata["headers"]["authorization"])
    assert "[REDACTED]" in str(response.raw_metadata["api_key"])
    assert response.raw_metadata["normal_key"] == "value"


def test_error_taxonomy_hierarchy_and_status_codes():
    auth_err = AuthenticationFailure("Invalid API Key provided", provider_id="openai")
    assert isinstance(auth_err, ProviderFailure)
    assert auth_err.status_code == 401
    assert auth_err.retryable is False
    assert auth_err.provider_id == "openai"

    rate_err = RateLimitFailure("Rate limit exceeded 429", provider_id="anthropic")
    assert rate_err.status_code == 429
    assert rate_err.retryable is True

    same_model_err = SameModelEndpointExhausted("All endpoints exhausted for gpt-4o")
    assert isinstance(same_model_err, ProviderFailure)
    assert same_model_err.retryable is False

    # Verify all 15 required exception classes instantiate cleanly
    exceptions = [
        AuthenticationFailure(), PermissionFailure(), RateLimitFailure(),
        QuotaExhaustedFailure(), ModelNotFoundFailure(), InvalidRequestFailure(),
        ContextOverflowFailure(), ContentPolicyFailure(), ProviderUnavailableFailure(),
        NetworkFailure(), TimeoutFailure(), ProtocolMismatchFailure(),
        MalformedResponseFailure(), CancellationFailure(), SameModelEndpointExhausted()
    ]
    assert len(exceptions) == 15


def test_secret_redaction_regex_and_dict():
    raw_str = "Authorization: Bearer sk-1234567890abcdef12345678 and api_key=sk-abcdef1234567890"
    redacted = redact_text(raw_str)
    assert "sk-1234567890abcdef12345678" not in redacted
    assert "[REDACTED]" in redacted

    raw_dict = {
        "user": "admin",
        "api_key": "sk-12345678901234567890",
        "nested": {
            "token": "Bearer nvapi-12345678901234567890"
        }
    }
    sanitized = redact_dict(raw_dict)
    assert sanitized["user"] == "admin"
    assert "sk-" in sanitized["api_key"] and "REDACTED" in sanitized["api_key"]
    assert "nvapi" not in sanitized["nested"]["token"] or "REDACTED" in sanitized["nested"]["token"]


def test_stream_event_ordering():
    events = [
        ProviderStreamEvent(event_type="token", sequence_number=1, delta="Hello"),
        ProviderStreamEvent(event_type="token", sequence_number=2, delta=" World"),
        ProviderStreamEvent(event_type="done", sequence_number=3, finish_reason="stop"),
    ]
    for i, evt in enumerate(events, start=1):
        assert evt.sequence_number == i
    assert events[-1].event_type == "done"
    assert events[-1].finish_reason == "stop"


def test_capability_matching():
    profile = ModelCapabilityProfile(
        model_id="gpt-4o",
        provider_name="openai",
        capabilities=[ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.TOOL_USE],
        context_window=128000
    )
    assert profile.supports_all([ModelCapability.CHAT, ModelCapability.CODING]) is True
    assert profile.supports_all([ModelCapability.CHAT, ModelCapability.VISION]) is False
    assert profile.supports_any([ModelCapability.VISION, ModelCapability.TOOL_USE]) is True


def test_import_boundary_isolation():
    """
    Architecture Acceptance Gate:
    windagent_providers package MUST NOT import SQLAlchemy, FastAPI, Starlette, or apps backend.
    """
    import windagent_providers
    import windagent_providers.base

    provider_modules = [
        mod_name for mod_name in sys.modules
        if mod_name.startswith("windagent_providers")
    ]
    
    prohibited_prefixes = ("sqlalchemy", "fastapi", "starlette", "apps.backend")
    
    for mod_name in provider_modules:
        mod = sys.modules[mod_name]
        if hasattr(mod, "__file__") and mod.__file__:
            for attr_name, attr_val in mod.__dict__.items():
                if hasattr(attr_val, "__module__") and attr_val.__module__:
                    mod_origin = attr_val.__module__
                    for prohibited in prohibited_prefixes:
                        assert not mod_origin.startswith(prohibited), (
                            f"Import boundary violation in {mod_name}: "
                            f"{attr_name} originates from prohibited package '{mod_origin}'"
                        )
