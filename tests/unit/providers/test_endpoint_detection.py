"""
Unit tests for Provider Routing V3 Test Connect and Protocol Detection Engine.
Adheres strictly to ban_ke_hoach.md §PHASE 5 requirements using httpx.MockTransport.
"""

import pytest
import httpx

from windagent_providers.detection.url_sanitizer import sanitize_url
from windagent_providers.detection.fingerprints import detect_vendor_from_url_or_key
from windagent_providers.detection.detector import EndpointDetector


def test_ssrf_protection_blocks_metadata_ips():
    # Blocks cloud metadata IP
    with pytest.raises(ValueError) as exc1:
        sanitize_url("http://169.254.169.254/latest/meta-data")
    assert "SSRF Security Block" in str(exc1.value)

    # Blocks Google metadata domain
    with pytest.raises(ValueError) as exc2:
        sanitize_url("http://metadata.google.internal/computeMetadata/v1")
    assert "SSRF Security Block" in str(exc2.value)

    # Blocks prohibited scheme
    with pytest.raises(ValueError) as exc3:
        sanitize_url("file:///etc/passwd")
    assert "Prohibited URL scheme" in str(exc3.value)

    # Allows valid HTTP URL
    clean = sanitize_url("http://localhost:11434")
    assert clean == "http://localhost:11434"


def test_vendor_fingerprint_matching():
    v1, _ = detect_vendor_from_url_or_key("https://openrouter.ai/api/v1")
    assert v1 == "openrouter"

    v2, _ = detect_vendor_from_url_or_key("https://integrate.api.nvidia.com/v1", "nvapi-12345")
    assert v2 == "nvidia"

    v3, _ = detect_vendor_from_url_or_key("https://api.mistral.ai/v1")
    assert v3 == "mistral"


@pytest.mark.asyncio
async def test_detect_ollama_protocol():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in ("/api/tags", "/v1/api/tags"):
            return httpx.Response(200, json={"models": [{"name": "llama3.1:latest"}]})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    detector = EndpointDetector(http_client=client)

    result = await detector.test_connection(base_url="http://localhost:11434")
    assert result["connected"] is True
    assert result["detected_protocol"] == "ollama"
    assert result["detected_vendor"] == "ollama"
    assert result["auth_valid"] is True
    assert result["models_found"] == 1


@pytest.mark.asyncio
async def test_detect_openai_compatible_protocol():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in ("/models", "/v1/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-4o"}]})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    detector = EndpointDetector(http_client=client)

    result = await detector.test_connection(base_url="https://api.openai.com/v1", credential="sk-test")
    assert result["connected"] is True
    assert result["detected_protocol"] == "openai"
    assert result["auth_valid"] is True
    assert result["models_found"] == 1


@pytest.mark.asyncio
async def test_manual_protocol_override_and_mismatch_warning():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "gpt-4o"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    detector = EndpointDetector(http_client=client)

    result = await detector.test_connection(
        base_url="https://api.openai.com/v1",
        credential="sk-test",
        selected_provider_hint="anthropic",
        manual_protocol_override="custom_openai"
    )
    assert result["connected"] is True
    assert result["detected_protocol"] == "custom_openai"
    assert len(result["warnings"]) > 0
    assert "Selected hint 'anthropic' differs" in result["warnings"][0]


@pytest.mark.asyncio
async def test_zero_credential_persistence_on_test_connect():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    detector = EndpointDetector(http_client=client)

    raw_secret = "sk-super-secret-key-99999"
    result = await detector.test_connection(base_url="https://api.openai.com/v1", credential=raw_secret)

    result_str = str(result)
    assert raw_secret not in result_str
