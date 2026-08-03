"""Credential public serialization (Phase 1 — G2.3).

Guarantees the API surface only ever returns credential **metadata** — never
``secret_ciphertext`` and never the plaintext secret. Any caller that needs to
decrypt must do so inside the trusted storage/providers boundary and must not
round-trip the value through an API response.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def public_credential_dict(
    *,
    credential_id: str,
    label: str,
    is_env_ref: bool,
    env_var_name: Optional[str],
    secret_version: int,
    enabled: bool,
    created_at: Any = None,
    updated_at: Any = None,
) -> Dict[str, Any]:
    """Build the metadata-only DTO for a provider credential.

    Deliberately has no ``secret`` / ``api_key`` / ``secret_ciphertext`` field —
    the exit gate "API GET không lộ key" is enforced structurally here: there is
    no way to include the secret value in this dict.
    """
    return {
        "credential_id": credential_id,
        "label": label,
        "is_env_ref": is_env_ref,
        "env_var_name": env_var_name,
        "secret_version": secret_version,
        "enabled": enabled,
        "has_secret": True,  # metadata only: a secret exists, but its value is never exposed
        "created_at": created_at,
        "updated_at": updated_at,
    }


def public_credential_from_orm(orm: Any) -> Dict[str, Any]:
    """Map a ``ProviderCredentialORM`` row to its metadata-only public dict."""
    return public_credential_dict(
        credential_id=orm.id,
        label=orm.label,
        is_env_ref=orm.is_env_ref,
        env_var_name=orm.env_var_name,
        secret_version=orm.secret_version,
        enabled=orm.enabled,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )
