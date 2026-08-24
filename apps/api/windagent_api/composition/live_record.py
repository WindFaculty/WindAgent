"""Live Record composer for the API composition root.

Binds the SQL repository bundle factory (``windagent_storage.live_record``)
onto the ``LiveRecordApplicationService`` over the shared async session
factory. The API service itself only sees ports.

The optional credential resolver decrypts the configured provider credential
(AES-GCM ``secret_ciphertext`` via the provider-management repository) so the
director-session bootstrap can mint a REAL Google ephemeral token. Without it
the service falls back to the local signed envelope (hermetic CI only).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Callable, Optional

from windagent_api.services.live_record_application_service import (
    LiveRecordApplicationService,
)

logger = logging.getLogger(__name__)

CredentialResolver = Callable[[str], Any]


def make_provider_credential_resolver(
    provider_management_repo: Any,
    decrypt_fn: Optional[Callable[[str], str]] = None,
) -> CredentialResolver:
    """Build an async resolver provider_id → api_key | None.

    Uses the same probe-material path as ProviderProbeService: the first
    enabled endpoint of the vendor carries the credential ciphertext. Any
    failure resolves to ``None`` — the caller (bootstrap) fails closed.
    """

    async def resolve(provider_name: str) -> Optional[str]:
        if decrypt_fn is None:
            from windagent_storage.security.encryption import decrypt as decrypt_fn_local
            decrypt = decrypt_fn_local
        else:
            decrypt = decrypt_fn
        try:
            endpoints = provider_management_repo.list_endpoints(provider_name)
        except Exception:  # noqa: BLE001 — resolver must never break bootstrap paths
            logger.warning("credential resolver: no endpoints for %s", provider_name)
            return None
        for endpoint in endpoints or []:
            if not getattr(endpoint, "enabled", True):
                continue
            material = provider_management_repo.get_probe_material(endpoint.id)
            ciphertext = getattr(material, "credential_ciphertext", None)
            if not ciphertext:
                continue
            try:
                secret = decrypt(ciphertext)
            except Exception:  # noqa: BLE001 — undecryptable ⇒ treat as absent
                logger.warning(
                    "credential resolver: undecryptable credential for endpoint %s",
                    endpoint.id,
                )
                continue
            if secret:
                return secret
        return None

    return resolve


class LiveRecordComposer:
    @staticmethod
    def compose(
        db,
        credential_resolver: Optional[CredentialResolver] = None,
    ) -> LiveRecordApplicationService:
        from windagent_storage.live_record.repositories import (
            create_sql_director_session_repository,
            create_sql_live_execution_plan_repository,
            create_sql_recording_event_repository,
            create_sql_recording_segment_repository,
            create_sql_recording_take_repository,
        )

        def repo_bundle_factory(session) -> SimpleNamespace:
            return SimpleNamespace(
                plans=create_sql_live_execution_plan_repository(session),
                takes=create_sql_recording_take_repository(session),
                segments=create_sql_recording_segment_repository(session),
                events=create_sql_recording_event_repository(session),
                directors=create_sql_director_session_repository(session),
            )

        return LiveRecordApplicationService(
            session_factory=db.session_factory,
            repo_bundle_factory=repo_bundle_factory,
            credential_resolver=credential_resolver,
        )


__all__ = ["LiveRecordComposer", "make_provider_credential_resolver"]
