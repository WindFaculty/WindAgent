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
