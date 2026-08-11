"""Worker-attested runtime capability provider for the Studio V3 API."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List

from windagent_core.config.certification import certification_mode_enabled
from windagent_core.contracts.studio.capabilities import (
    CapabilityStatus,
    RuntimeCapability,
    RuntimeCapabilityProfile,
    WorkerRuntimeAttestation,
)

if TYPE_CHECKING:
    from windagent_api.composition import ApplicationContainer

logger = logging.getLogger("windagent.api.studio.capability")

_STUDIO_ORCHESTRATION = "studio_orchestration"
_STORY_ENGINE = "story_engine"
_MODEL_ROUTE = "model_route"
_WORKER = "worker"
_DURABLE_DB = "durable_db"
_QUEUE = "queue"
_OUTBOX = "outbox"


@dataclass
class _WorkerEvidence:
    active_count: int = 0
    active_leases: int = 0
    eligible: list[WorkerRuntimeAttestation] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)


class ApiRuntimeCapabilityProvider:
    """Aggregate fresh durable worker attestations without trusting API env as worker truth."""

    def __init__(self, container: "ApplicationContainer") -> None:
        self.container = container

    async def get_capabilities(self) -> RuntimeCapabilityProfile:
        evidence = await self._worker_evidence()
        capabilities: List[RuntimeCapability] = [
            self._durable_db(),
            self._queue(),
            self._outbox(),
            self._worker(evidence),
            self._model_route(evidence),
            self._studio_orchestration(),
            self._story_engine(evidence),
        ]
        return RuntimeCapabilityProfile(
            capabilities=capabilities,
            fail_closed_flags=self._fail_closed_flags(evidence),
            certification_mode=certification_mode_enabled(),
        )

    def _durable_db(self) -> RuntimeCapability:
        db = self.container.db
        if db is None:
            return RuntimeCapability(
                name=_DURABLE_DB,
                status=CapabilityStatus.UNAVAILABLE,
                source="composition.ApplicationContainer.db",
                reason="database manager not composed",
            )
        return RuntimeCapability(
            name=_DURABLE_DB,
            status=CapabilityStatus.AVAILABLE,
            source="composition.ApplicationContainer.db",
            reason="database manager composed; schema applied at bootstrap",
            metadata={"db_url_scheme": str(self.container.db_url).split(":", 1)[0]},
        )

    def _queue(self) -> RuntimeCapability:
        adapter = self.container.task_submission
        if adapter is None:
            return RuntimeCapability(
                name=_QUEUE,
                status=CapabilityStatus.UNAVAILABLE,
                source="composition.ApplicationContainer.task_submission",
                reason="durable queue adapter not composed",
            )
        return RuntimeCapability(
            name=_QUEUE,
            status=CapabilityStatus.AVAILABLE,
            source="composition.ApplicationContainer.task_submission",
            reason="SqlWorkSubmissionAdapter composed",
        )

    def _outbox(self) -> RuntimeCapability:
        if self.container.db is None:
            return RuntimeCapability(
                name=_OUTBOX,
                status=CapabilityStatus.UNAVAILABLE,
                source="storage.unit_of_work.SqlUnitOfWork",
                reason="database not composed; outbox unavailable",
            )
        return RuntimeCapability(
            name=_OUTBOX,
            status=CapabilityStatus.AVAILABLE,
            source="storage.unit_of_work.SqlUnitOfWork",
            reason="outbox submission rides the SQL unit of work",
        )

    async def _worker_evidence(self) -> _WorkerEvidence:
        repository = getattr(self.container, "worker_heartbeat_repo", None)
        evidence = _WorkerEvidence()
        if repository is None:
            evidence.rejected.append({"worker_id": "", "reason": "heartbeat_repository_missing"})
            return evidence
        try:
            workers = await repository.get_active_workers(stale_after_seconds=30)
        except Exception as ex:  # pragma: no cover - defensive probe
            logger.warning("worker capability probe failed: %s", ex)
            evidence.rejected.append(
                {"worker_id": "", "reason": f"heartbeat_probe_{type(ex).__name__}"}
            )
            return evidence

        evidence.active_count = len(workers)
        evidence.active_leases = sum(worker.active_leases for worker in workers)
        api_sha = os.getenv("WINDAGENT_SOURCE_SHA", "").strip()
        expected_model = os.getenv("WINDAGENT_STUDIO_CANONICAL_MODEL", "").strip()
        api_certification = certification_mode_enabled()
        for worker in workers:
            raw = worker.metadata.get("studio_runtime_attestation")
            if not isinstance(raw, dict):
                evidence.rejected.append(
                    {"worker_id": worker.worker_id, "reason": "missing_studio_attestation"}
                )
                continue
            try:
                attestation = WorkerRuntimeAttestation.model_validate(raw)
            except Exception as ex:
                evidence.rejected.append(
                    {
                        "worker_id": worker.worker_id,
                        "reason": f"invalid_studio_attestation_{type(ex).__name__}",
                    }
                )
                continue
            reason = ""
            if attestation.worker_id != worker.worker_id:
                reason = "worker_id_mismatch"
            elif not attestation.is_story_eligible:
                reason = "studio_runtime_ineligible"
            elif api_certification and not attestation.certification_mode:
                reason = "certification_mode_mismatch"
            elif api_certification and (not api_sha or attestation.source_sha != api_sha):
                reason = "source_sha_mismatch"
            elif api_certification and (
                not expected_model or attestation.canonical_model != expected_model
            ):
                reason = "canonical_model_mismatch"
            if reason:
                evidence.rejected.append({"worker_id": worker.worker_id, "reason": reason})
            else:
                evidence.eligible.append(attestation)
        return evidence

    @staticmethod
    def _attestation_summary(attestation: WorkerRuntimeAttestation) -> dict:
        return {
            "worker_id": attestation.worker_id,
            "source_sha": attestation.source_sha,
            "process_version": attestation.process_version,
            "certification_mode": attestation.certification_mode,
            "runtime_adapter": attestation.runtime_adapter,
            "completion_reconciler": attestation.completion_reconciler,
            "completion_recovery": attestation.completion_recovery,
            "handler_count": len(attestation.handler_names),
            "handler_names": attestation.handler_names,
            "handler_digest": attestation.handler_digest,
            "model_port_type": attestation.model_port_type,
            "canonical_model": attestation.canonical_model,
            "provider_route_ready": attestation.provider_route_ready,
            "durable_route_lock": attestation.durable_route_lock,
            "endpoint_binding_identities": attestation.endpoint_binding_identities,
            "fake_runtime": attestation.fake_runtime,
        }

    def _worker(self, evidence: _WorkerEvidence) -> RuntimeCapability:
        metadata = {
            "active_worker_count": evidence.active_count,
            "active_leases": evidence.active_leases,
            "eligible_studio_worker_count": len(evidence.eligible),
            "eligible_studio_workers": [
                self._attestation_summary(attestation) for attestation in evidence.eligible
            ],
            "rejected_workers": evidence.rejected,
            "api_source_sha": os.getenv("WINDAGENT_SOURCE_SHA", "").strip() or None,
        }
        if evidence.active_count:
            return RuntimeCapability(
                name=_WORKER,
                status=CapabilityStatus.AVAILABLE,
                source="storage.worker_heartbeat.studio_runtime_attestation",
                reason=(
                    f"{evidence.active_count} fresh worker(s); "
                    f"{len(evidence.eligible)} eligible Studio worker(s)"
                ),
                metadata=metadata,
            )
        return RuntimeCapability(
            name=_WORKER,
            status=CapabilityStatus.UNAVAILABLE,
            source="storage.worker_heartbeat.studio_runtime_attestation",
            reason="no active worker heartbeat; durable execution is not running",
            metadata=metadata,
        )

    def _model_route(self, evidence: _WorkerEvidence) -> RuntimeCapability:
        if not evidence.eligible:
            return RuntimeCapability(
                name=_MODEL_ROUTE,
                status=CapabilityStatus.UNAVAILABLE,
                source="worker.studio_runtime_attestation",
                reason="no eligible worker attests a real durable provider route",
                metadata={"eligible_studio_worker_count": 0},
            )
        identities = [
            identity
            for attestation in evidence.eligible
            for identity in attestation.endpoint_binding_identities
        ]
        return RuntimeCapability(
            name=_MODEL_ROUTE,
            status=CapabilityStatus.AVAILABLE,
            source="worker.studio_runtime_attestation",
            reason="eligible worker attests a durable route and exact provider binding",
            metadata={
                "canonical_models": sorted(
                    {attestation.canonical_model for attestation in evidence.eligible}
                ),
                "binding_count": len(identities),
                "endpoint_binding_identities": identities,
            },
        )

    def _studio_orchestration(self) -> RuntimeCapability:
        orchestrator = self.container.orchestrator_service
        if orchestrator is None:
            return RuntimeCapability(
                name=_STUDIO_ORCHESTRATION,
                status=CapabilityStatus.UNAVAILABLE,
                source="composition.ApplicationContainer.orchestrator_service",
                reason="orchestrator not composed",
            )
        seam = getattr(orchestrator, "_studio_run_extension", None)
        if seam is not None:
            return RuntimeCapability(
                name=_STUDIO_ORCHESTRATION,
                status=CapabilityStatus.AVAILABLE,
                source="orchestration.orchestrator_service.studio_run_extension",
                reason="Studio run authority seam wired (Plan A A4)",
            )
        return RuntimeCapability(
            name=_STUDIO_ORCHESTRATION,
            status=CapabilityStatus.UNAVAILABLE,
            source="orchestration.orchestrator_service.studio_run_extension",
            reason="Studio run authority seam is not wired; V3 commands fail closed",
        )

    @staticmethod
    def _story_engine(evidence: _WorkerEvidence) -> RuntimeCapability:
        if not evidence.eligible:
            return RuntimeCapability(
                name=_STORY_ENGINE,
                status=CapabilityStatus.UNAVAILABLE,
                source="worker.studio_runtime_attestation",
                reason="no fresh eligible worker attests the complete Story runtime",
                metadata={"rejected_workers": evidence.rejected},
            )
        return RuntimeCapability(
            name=_STORY_ENGINE,
            status=CapabilityStatus.AVAILABLE,
            source="worker.studio_runtime_attestation",
            reason="fresh eligible worker attests the complete Story runtime",
            metadata={
                "worker_ids": [attestation.worker_id for attestation in evidence.eligible],
                "handler_digests": [
                    attestation.handler_digest for attestation in evidence.eligible
                ],
            },
        )

    @staticmethod
    def _fail_closed_flags(evidence: _WorkerEvidence) -> List[str]:
        """Report unsafe certification composition without exposing secrets."""

        if not certification_mode_enabled():
            return []
        flags: List[str] = []
        if os.getenv("WINDAGENT_FAKE_RUNTIME", "").lower() in ("1", "true", "yes"):
            flags.append("fake_runtime_active")
        if os.getenv("WINDAGENT_MODEL_BACKEND", "").lower() in ("mock", "fake", "fixture"):
            flags.append("non_real_model_backend_active")
        if not evidence.eligible:
            flags.append("no_eligible_studio_worker")
        if any(item["reason"] == "source_sha_mismatch" for item in evidence.rejected):
            flags.append("worker_source_sha_mismatch")
        return flags


__all__ = ["ApiRuntimeCapabilityProvider"]
