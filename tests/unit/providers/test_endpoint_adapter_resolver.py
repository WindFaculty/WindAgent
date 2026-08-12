from types import SimpleNamespace

import pytest

from windagent_providers.base.errors import ProviderUnavailableFailure
from windagent_providers.routing.endpoint_adapter_resolver import EndpointAdapterResolver


def test_resolver_receives_credential_decryption_from_its_composition_root() -> None:
    ciphertexts: list[str] = []
    resolver = EndpointAdapterResolver(
        lambda ciphertext: ciphertexts.append(ciphertext) or "decrypted-token"
    )

    transport = resolver(
        SimpleNamespace(
            protocol_mode="openai_compatible",
            credential_ciphertext="encrypted-token",
            provider_name="example-provider",
            base_url="https://example.test/v1/",
        )
    )

    assert ciphertexts == ["encrypted-token"]
    assert transport.provider_name == "example-provider"
    assert transport.base_url == "https://example.test/v1"
    assert transport.api_key == "decrypted-token"


def test_resolver_rejects_protocols_without_a_supported_transport() -> None:
    resolver = EndpointAdapterResolver(lambda _: "unused")

    with pytest.raises(ProviderUnavailableFailure, match="Unsupported conversation endpoint protocol"):
        resolver(
            SimpleNamespace(
                protocol_mode="anthropic",
                credential_ciphertext="encrypted-token",
                provider_name="example-provider",
                base_url="https://example.test/v1",
            )
        )


def test_resolver_does_not_decrypt_missing_ollama_credential() -> None:
    ciphertexts: list[str] = []
    resolver = EndpointAdapterResolver(
        lambda ciphertext: ciphertexts.append(ciphertext) or "unexpected"
    )

    transport = resolver(
        SimpleNamespace(
            protocol_mode="ollama",
            credential_ciphertext=None,
            provider_name="ollama-local",
            base_url="http://127.0.0.1:11434/v1",
        )
    )

    assert ciphertexts == []
    assert transport.api_key == ""
    assert transport.stream_generate is True
    assert transport.default_payload == {"think": False, "num_ctx": 16384}


def test_resolver_builds_native_google_adapter() -> None:
    resolver = EndpointAdapterResolver(lambda ciphertext: f"dec-{ciphertext}")

    adapter = resolver(
        SimpleNamespace(
            protocol_mode="google",
            credential_ciphertext="enc-google",
            provider_name="google",
            base_url="https://generativelanguage.googleapis.com/v1beta",
        )
    )

    assert type(adapter).__name__ == "GoogleGeminiProviderAdapter"
    assert adapter.api_key == "dec-enc-google"
    assert adapter.base_url == "https://generativelanguage.googleapis.com/v1beta"
    assert adapter.timeout_seconds == 300.0
