"""Plan A A5 — Studio worker runtime adapter + completion recovery.

The independent worker executes frozen Story task types through this adapter:

- ``StudioRuntimeAdapter`` decodes/validates the durable ``StudioTaskEnvelope``
  BEFORE any side effect, resolves the Plan B handler for the frozen task
  type, loads input artifacts, runs the handler, persists output artifacts
  (content-addressed, idempotent by hash, fenced by task/fencing token), and
  returns an ``ExecutionResult`` whose ``result_data`` IS the serialized
  ``StudioTaskResult`` — the generic worker finalizer then commits task
  state + result + terminal event + outbox + lease release atomically.
- Failures never raise out of ``dispatch``: they become a FAILED/CANCELLED
  ``StudioTaskResult`` so the durable retry path (orchestrator-side) owns the
  decision. Envelope/registry/certification violations fail closed the same
  way (no handler call, no artifacts).
- ``StudioCompletionRecovery`` re-drives the reconciler for terminal Studio
  tasks whose completion was committed but never reconciled (crash window
  after finalizer commit, before reconciliation) — idempotent by design
  (reconciler answers ``duplicate=True`` for already-advanced nodes).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from windagent_core.config.certification import certification_mode_enabled
from windagent_core.contracts.execution import (
    ExecutionHandle,
    ExecutionRequest,
    ExecutionResult,
    ExecutionRuntimePort,
    RuntimeStatus,
    RuntimeStatusEnum,
)
from windagent_core.contracts.studio.models import (
    CONTRACT_VERSION,
    TASK_ENVELOPE_SCHEMA_VERSION,
    StudioArtifactRef,
    StudioRouteProvenance,
    StudioTaskEnvelope,
    StudioTaskResult,
    StudioTaskStatus,
)
from windagent_core.domain.story.bibles.models import CharacterCanon, StoryBible, WorldBible
from windagent_core.domain.story.ideation.models import (
    CreativeBrief,
    IdeaCandidateSet,
    SelectedIdea,
)
from windagent_core.domain.story.outline.models import BeatSheet, EpisodeOutline
from windagent_core.domain.story.review import (
    LockedScreenplayReceipt,
    PackageArtifactRef,
    ReviewReport,
)
from windagent_core.domain.story.screenplay import ScreenplayDraft
from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

logger = logging.getLogger("windagent.worker.studio")

STUDIO_TASK_PREFIX = "studio."

#: Redaction-safe error codes for worker-side failures (additive, A-owned).
ENVELOPE_INVALID = "STUDIO_ENVELOPE_INVALID"
UNREGISTERED_TASK_TYPE = "STUDIO_UNREGISTERED_TASK_TYPE"
CERTIFICATION_VIOLATION = "STUDIO_CERTIFICATION_VIOLATION"
MODEL_PORT_UNAVAILABLE = "STUDIO_MODEL_PORT_UNAVAILABLE"
#: Envelope deadline reached while the task was still executing (or about to).
#: The run deadline is authoritative: no provider call may leave a Studio run
#: in RUNNING past it (C7 attempt-8 forensic finding).
STUDIO_RUN_DEADLINE_EXCEEDED = "STUDIO_RUN_DEADLINE_EXCEEDED"

#: Envelope fields that are fine in worker metrics/events (ids + status only).
_METRIC_SAFE_FIELDS = ("task_id", "task_type", "attempt", "status", "dag_node_id", "studio_run_id")


def certification_enabled() -> bool:
    """Certification mode rejects fake runtimes and fixture providers."""
    return certification_mode_enabled(os.environ)


def is_studio_task(tool_name: str) -> bool:
    return tool_name.startswith(STUDIO_TASK_PREFIX)


def redact(value: Any) -> Any:
    """Strip anything that is not an id/status/duration (never content)."""
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if k in _METRIC_SAFE_FIELDS}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def _safe_failure_detail(exc: BaseException) -> str:
    """Expose only typed validation issue codes, never model or prompt content."""
    issue_codes: List[str] = []
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        issues = details.get("issues")
        if isinstance(issues, list):
            for issue in issues:
                if not isinstance(issue, dict):
                    continue
                code = str(issue.get("code", ""))
                if code and code.isascii() and code.replace("_", "").isalnum():
                    issue_codes.append(code[:64])
    unique_codes = sorted(set(issue_codes))[:8]
    suffix = f"[{','.join(unique_codes)}]" if unique_codes else ""
    return f"{type(exc).__name__}{suffix}"


# ---------------------------------------------------------------------------
# Task-type contract tables (frozen against story_task_io.json + B handlers)
# ---------------------------------------------------------------------------

#: artifact_type -> StoryContent model class used to decode envelope inputs.
INPUT_MODEL_BY_TYPE: Dict[str, Any] = {
    "CreativeBrief": CreativeBrief,
    "IdeaCandidateSet": IdeaCandidateSet,
    "SelectedIdea": SelectedIdea,
    "StoryBible": StoryBible,
    "WorldBible": WorldBible,
    "CharacterCanon": CharacterCanon,
    "BeatSheet": BeatSheet,
    "EpisodeOutline": EpisodeOutline,
    "ScreenplayDraft": ScreenplayDraft,
    "ReviewReport": ReviewReport,
}

#: frozen task type -> ordered input artifact types (story_task_io.json).
INPUT_TYPES_BY_TASK: Dict[str, List[str]] = {
    "studio.story.idea.generate": [],
    "studio.story.idea.evaluate": ["IdeaCandidateSet"],
    "studio.story.bible.generate": ["SelectedIdea"],
    "studio.story.beats.generate": ["StoryBible", "WorldBible", "CharacterCanon"],
    "studio.story.outline.generate": ["BeatSheet"],
    "studio.story.screenplay.generate": ["EpisodeOutline"],
    "studio.story.review": ["ScreenplayDraft"],
    "studio.story.revise": ["ScreenplayDraft", "ReviewReport"],
    "studio.story.lock": ["ScreenplayDraft", "ReviewReport"],
}

#: frozen task type -> output model extractor from the handler result.
def _outputs_from(result: Any, names: List[str]) -> List[Any]:
    return [getattr(result, name) for name in names]


OUTPUT_NAMES_BY_TASK: Dict[str, List[str]] = {
    "studio.story.idea.generate": ["candidate_set"],
    "studio.story.idea.evaluate": ["candidate_set"],
    "studio.story.bible.generate": ["story_bible", "world_bible", "character_canon"],
    "studio.story.beats.generate": ["beat_sheet"],
    "studio.story.outline.generate": ["episode_outline"],
    "studio.story.screenplay.generate": ["draft"],
    "studio.story.review": ["report"],
    "studio.story.revise": ["proposal", "new_draft"],
    "studio.story.lock": ["receipt", "package"],
}

#: task types whose handler needs a provider-neutral model port.
MODEL_PORT_TASK_TYPES = frozenset(
    {
        "studio.story.idea.generate",
        "studio.story.bible.generate",
        "studio.story.beats.generate",
        "studio.story.outline.generate",
        "studio.story.screenplay.generate",
        "studio.story.review",
        "studio.story.revise",
    }
)


def _brief_from(episode: Any, envelope: StudioTaskEnvelope) -> Optional[CreativeBrief]:
    """Creative brief: envelope payload wins, episode metadata is the fallback."""
    raw = envelope.payload.get("brief") if envelope.payload else None
    if raw is None and episode is not None:
        raw = (episode.metadata or {}).get("creative_brief")
    if not raw:
        return None
    return CreativeBrief.model_validate(raw)


# ---------------------------------------------------------------------------
# Studio worker runtime adapter
# ---------------------------------------------------------------------------


class StudioRuntimeAdapter(ExecutionRuntimePort):
    """Executes frozen Story task envelopes against Plan B handlers."""

    def __init__(
        self,
        handler_registry: Dict[str, Any],
        session_factory: Any,
        *,
        model_port: Any = None,
        certification: Optional[bool] = None,
        fake_runtime_active: bool = False,
        cancel_check: Optional[Callable[[], bool]] = None,
        worker_id: str = "studio-worker",
        studio_uow_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._handler_registry = handler_registry
        self._session_factory = session_factory
        if studio_uow_factory is None:
            raise RuntimeError(
                "StudioRuntimeAdapter requires studio_uow_factory (wired by composition root)."
            )
        self._studio_uow_factory: Callable[[], Any] = studio_uow_factory
        self._model_port = model_port
        self._certification = certification_enabled() if certification is None else certification
        self._fake_runtime_active = fake_runtime_active
        self._cancel_check = cancel_check or (lambda: False)
        self._worker_id = worker_id
        self._results: Dict[str, ExecutionResult] = {}

    # -- ExecutionRuntimePort -------------------------------------------------

    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        handle = ExecutionHandle(
            handle_id=f"studio_{request.step_run_id}_{request.fencing_token[:8]}",
            runtime_run_id=f"studio_run_{request.step_run_id}",
            step_run_id=request.step_run_id,
            attempt_id=request.attempt_id,
            fencing_token=request.fencing_token,
        )
        result = await self._execute(request, handle)
        self._results[handle.handle_id] = result
        return handle

    async def get_status(self, handle: ExecutionHandle) -> RuntimeStatus:
        result = self._results.get(handle.handle_id)
        return RuntimeStatus(
            handle_id=handle.handle_id,
            status=result.status if result else RuntimeStatusEnum.UNKNOWN,
        )

    async def cancel(self, handle: ExecutionHandle) -> None:
        # Cancellation is cooperative: the cancel_check callback aborts between
        # phases; there is no provider process to kill in the A5 seam.
        return None

    async def get_result(self, handle: ExecutionHandle) -> ExecutionResult:
        return self._results.get(handle.handle_id) or ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=RuntimeStatusEnum.LOST,
        )

    async def reattach(self, runtime_run_id: str) -> Optional[ExecutionHandle]:
        return None

    # -- internals ------------------------------------------------------------

    async def _execute(self, request: ExecutionRequest, handle: ExecutionHandle) -> ExecutionResult:
        # The durable task identity is the claimed queue row (step_run_id);
        # envelope.task_id is orchestrator-side metadata and must never leak
        # into finalization/reconciliation identity.
        durable_task_id = request.step_run_id
        raw_envelope = (request.parameters or {}).get("studio_envelope")
        if not isinstance(raw_envelope, dict):
            return self._fail(
                handle,
                ENVELOPE_INVALID,
                "studio_envelope missing from execution parameters",
                task_id=durable_task_id,
            )

        try:
            envelope = StudioTaskEnvelope.model_validate(raw_envelope)
        except Exception as exc:  # noqa: BLE001 — envelope rejection is fail-closed
            return self._fail(
                handle,
                ENVELOPE_INVALID,
                f"envelope rejected: {type(exc).__name__}",
                task_id=durable_task_id,
            )

        if envelope.schema_version != TASK_ENVELOPE_SCHEMA_VERSION:
            return self._fail(
                handle,
                ENVELOPE_INVALID,
                f"unsupported envelope schema {envelope.schema_version!r}",
                envelope=envelope,
                task_id=durable_task_id,
            )
        if envelope.contract_version != CONTRACT_VERSION:
            return self._fail(
                handle,
                ENVELOPE_INVALID,
                f"unsupported contract {envelope.contract_version!r}",
                envelope=envelope,
                task_id=durable_task_id,
            )

        task_type = envelope.task_type.value
        handler_cls = self._handler_registry.get(envelope.task_type)
        if handler_cls is None:
            return self._fail(
                handle,
                UNREGISTERED_TASK_TYPE,
                f"no handler registered for {task_type}",
                envelope=envelope,
                task_id=durable_task_id,
            )

        # Certification profile: fake runtime / fixture providers fail closed.
        if self._certification:
            if self._fake_runtime_active:
                return self._fail(
                    handle,
                    CERTIFICATION_VIOLATION,
                    "fake runtime active in certification mode",
                    envelope=envelope,
                    task_id=durable_task_id,
                )
            if self._is_fixture_model_port():
                return self._fail(
                    handle,
                    CERTIFICATION_VIOLATION,
                    "fixture model port active in certification mode",
                    envelope=envelope,
                    task_id=durable_task_id,
                )

        if self._cancel_check():
            return self._cancel(handle, envelope, task_id=durable_task_id)

        try:
            handler = self._instantiate(handler_cls, task_type)
        except StudioModelPortUnavailable as exc:
            return self._fail(
                handle, MODEL_PORT_UNAVAILABLE, str(exc), envelope=envelope, task_id=durable_task_id
            )
        except Exception as exc:  # noqa: BLE001 — construction failure is fail-closed
            return self._fail(
                handle,
                "STUDIO_HANDLER_CONSTRUCTION_FAILURE",
                type(exc).__name__,
                envelope=envelope,
                task_id=durable_task_id,
            )

        async with self._studio_uow_factory() as uow:
            episode = await uow.episodes.get(envelope.episode_id)
            try:
                inputs = await self._load_inputs(uow, envelope, episode)
            except StudioInputArtifactMissing as exc:
                return self._fail(
                    handle,
                    "STUDIO_INPUT_ARTIFACT_MISSING",
                    str(exc),
                    envelope=envelope,
                    task_id=durable_task_id,
                )

            if self._cancel_check():
                return self._cancel(handle, envelope, task_id=durable_task_id)

            try:
                deadline = envelope.deadline
                remaining = (
                    (deadline - datetime.now(timezone.utc)).total_seconds()
                    if deadline is not None
                    else None
                )
                if remaining is not None and remaining <= 0:
                    # Deadline already gone (e.g. retry dispatched after the
                    # run budget): fail fast, never start a doomed provider call.
                    return self._fail(
                        handle,
                        STUDIO_RUN_DEADLINE_EXCEEDED,
                        f"run deadline already passed (remaining {remaining:.1f}s)",
                        envelope=envelope,
                        task_id=durable_task_id,
                    )
                if remaining is not None:
                    # Hard cap on provider generation: wait_for cancels the
                    # handler on expiry, which abandons the in-flight provider
                    # request (httpx client closes in the adapter finally).
                    outputs, provenance = await asyncio.wait_for(
                        self._run_handler(handler, task_type, envelope, inputs),
                        timeout=remaining,
                    )
                else:
                    outputs, provenance = await self._run_handler(
                        handler, task_type, envelope, inputs
                    )
            except asyncio.TimeoutError:
                return self._fail(
                    handle,
                    STUDIO_RUN_DEADLINE_EXCEEDED,
                    f"run deadline exceeded during provider generation (budget {remaining:.0f}s); request abandoned",
                    envelope=envelope,
                    task_id=durable_task_id,
                )
            except Exception as exc:  # noqa: BLE001 — mapped through the B taxonomy
                from windagent_intelligence.story.prompts.structured import story_error_code

                code = story_error_code(exc)
                return self._fail(
                    handle,
                    code,
                    _safe_failure_detail(exc),
                    envelope=envelope,
                    task_id=durable_task_id,
                )

            if self._cancel_check():
                return self._cancel(handle, envelope, task_id=durable_task_id)

            refs = await self._persist_outputs(
                uow, envelope, handle, inputs, outputs, provenance
            )
            await uow.commit()

        result = StudioTaskResult(
            task_id=durable_task_id,
            studio_run_id=envelope.studio_run_id,
            dag_node_id=envelope.dag_node_id,
            status=StudioTaskStatus.SUCCEEDED,
            output_artifact_refs=refs,
            output_hashes=[r.content_hash for r in refs],
            route_provenance=provenance,
            usage=provenance.usage if provenance else {},
        )
        return ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=RuntimeStatusEnum.COMPLETED,
            result_data=result.to_dict(),
        )

    def _instantiate(self, handler_cls: Any, task_type: str) -> Any:
        params = inspect.signature(handler_cls.__init__).parameters
        if "model_port" in params:
            if self._model_port is None:
                raise StudioModelPortUnavailable(
                    f"{task_type} requires a model port; none configured in worker"
                )
            return handler_cls(model_port=self._model_port)
        return handler_cls()

    async def _load_inputs(
        self, uow: StudioUnitOfWork, envelope: StudioTaskEnvelope, episode: Any
    ) -> Dict[str, Any]:
        inputs: Dict[str, Any] = {}
        wanted = INPUT_TYPES_BY_TASK.get(envelope.task_type.value, [])
        for ref in envelope.input_artifact_refs:
            artifact = await uow.artifacts.get(ref.artifact_id)
            if artifact is None:
                raise StudioInputArtifactMissing(f"input artifact {ref.artifact_id!s} not found")
            model_cls = INPUT_MODEL_BY_TYPE.get(artifact.artifact_type)
            if model_cls is not None:
                inputs[artifact.artifact_type] = model_cls.model_validate(artifact.content)
        missing = [t for t in wanted if t not in inputs]
        if missing:
            raise StudioInputArtifactMissing(
                f"{envelope.task_type.value} missing input artifacts: {', '.join(missing)}"
            )
        brief = _brief_from(episode, envelope)
        if brief is not None:
            inputs["CreativeBrief"] = brief
        return inputs

    def _lock_receipt_from(self, envelope: StudioTaskEnvelope) -> LockedScreenplayReceipt:
        """A-issued receipt travels in the envelope payload (A authority)."""
        payload = envelope.payload or {}
        raw = payload.get("receipt")
        if not isinstance(raw, dict):
            raise StudioInputArtifactMissing("studio.story.lock requires an A-issued receipt in payload")
        return LockedScreenplayReceipt.model_validate(raw)

    def _lock_lineage_from(self, envelope: StudioTaskEnvelope) -> List[PackageArtifactRef]:
        """Lineage = payload refs (upstream artifacts) + envelope input refs
        (draft/report, hash-bound by A) + the issued receipt ref. Never
        copies mutable state; the lock handler re-verifies every hash."""
        payload = envelope.payload or {}
        by_type: Dict[str, PackageArtifactRef] = {}
        for raw in payload.get("lineage_refs", []):
            ref = PackageArtifactRef.model_validate(raw)
            by_type[ref.artifact_type] = ref
        for ref in envelope.input_artifact_refs:
            by_type[ref.artifact_type] = PackageArtifactRef(
                artifact_type=ref.artifact_type,
                artifact_id=ref.artifact_id.value,
                content_hash=ref.content_hash,
                revision_id=envelope.revision_id.value if envelope.revision_id else None,
            )
        receipt = self._lock_receipt_from(envelope)
        receipt_id = (payload.get("receipt_artifact_id") or f"art_{receipt.receipt_id.value}")
        by_type["LockedScreenplayReceipt"] = PackageArtifactRef(
            artifact_type="LockedScreenplayReceipt",
            artifact_id=receipt_id,
            content_hash=receipt.content_hash(),
        )
        return list(by_type.values())

    async def _run_handler(
        self,
        handler: Any,
        task_type: str,
        envelope: StudioTaskEnvelope,
        inputs: Dict[str, Any],
    ) -> tuple[List[Any], Optional[StudioRouteProvenance]]:
        brief = inputs.get("CreativeBrief")
        if task_type == "studio.story.idea.generate":
            result = await handler.handle(brief)
        elif task_type == "studio.story.idea.evaluate":
            result = handler.handle(brief, inputs["IdeaCandidateSet"])
        elif task_type == "studio.story.bible.generate":
            result = await handler.handle(
                inputs["SelectedIdea"],
                brief=brief,
                language=brief.language if brief else None,
                audience_min_age=brief.audience_min_age if brief else None,
                audience_max_age=brief.audience_max_age if brief else None,
            )
        elif task_type == "studio.story.beats.generate":
            result = await handler.handle(
                inputs["StoryBible"],
                inputs["WorldBible"],
                inputs["CharacterCanon"],
                target_duration_seconds=brief.target_duration_seconds if brief else 240,
                language=brief.language if brief else "vi",
            )
        elif task_type == "studio.story.outline.generate":
            result = await handler.handle(
                inputs["BeatSheet"],
                canon=inputs.get("CharacterCanon"),
                world=inputs.get("WorldBible"),
                target_duration_seconds=brief.target_duration_seconds if brief else None,
                language=brief.language if brief else "vi",
                audience_band=(
                    f"{brief.audience_min_age}-{brief.audience_max_age}" if brief else "5-8"
                ),
            )
        elif task_type == "studio.story.screenplay.generate":
            result = await handler.handle(
                inputs["EpisodeOutline"],
                beat_sheet=inputs.get("BeatSheet"),
                canon=inputs.get("CharacterCanon"),
                world=inputs.get("WorldBible"),
                target_duration_seconds=brief.target_duration_seconds if brief else None,
                language=brief.language if brief else "vi",
                audience_band=(
                    f"{brief.audience_min_age}-{brief.audience_max_age}" if brief else "5-8"
                ),
            )
        elif task_type == "studio.story.review":
            result = await handler.handle(
                inputs["ScreenplayDraft"],
                review_iteration=int((envelope.payload or {}).get("review_iteration", 1)),
                maximum_iterations=int((envelope.payload or {}).get("maximum_iterations", 3)),
                quality_threshold=(envelope.payload or {}).get("quality_threshold"),
            )
        elif task_type == "studio.story.revise":
            result = await handler.handle(
                inputs["ScreenplayDraft"],
                inputs["ReviewReport"],
                language=brief.language if brief else "vi",
                audience_band=(
                    f"{brief.audience_min_age}-{brief.audience_max_age}" if brief else "5-8"
                ),
            )
        elif task_type == "studio.story.lock":
            result = await handler.handle(
                inputs["ScreenplayDraft"],
                inputs["ReviewReport"],
                self._lock_receipt_from(envelope),
                lineage_refs=self._lock_lineage_from(envelope),
                title=(envelope.payload or {}).get("title"),
            )
        else:
            raise StudioUnsupportedTaskType(f"no execution mapping for {task_type}")

        provenance = getattr(result, "provenance", None)
        route = None
        if provenance is not None and getattr(provenance, "prompt_id", None):
            usage = dict(getattr(provenance, "usage", {}) or {})
            route = StudioRouteProvenance(
                prompt_id=provenance.prompt_id,
                prompt_version=getattr(provenance, "prompt_version", None),
                prompt_hash=getattr(provenance, "prompt_hash", None),
                provider_id=getattr(provenance, "provider", None),
                model_id=getattr(provenance, "provider_model_id", None),
                canonical_model_id=getattr(provenance, "canonical_model_id", None),
                provider_model_id=getattr(provenance, "provider_model_id", None),
                endpoint_id=getattr(provenance, "endpoint_id", None),
                provider_binding_id=getattr(
                    provenance, "provider_binding_id", None
                ),
                provider_attempt_id=getattr(
                    provenance, "provider_attempt_id", None
                ),
                provider_request_id=getattr(
                    provenance, "provider_request_id", None
                ),
                output_schema_contract=getattr(
                    provenance, "output_schema_contract", None
                ),
                model_route_id=(
                    getattr(provenance, "route_lock_id", None) or usage.get("route_lock_id")
                ),
                usage=usage,
            )
        outputs = _outputs_from(result, OUTPUT_NAMES_BY_TASK[task_type])
        return outputs, route

    async def _persist_outputs(
        self,
        uow: StudioUnitOfWork,
        envelope: StudioTaskEnvelope,
        handle: ExecutionHandle,
        inputs: Dict[str, Any],
        outputs: List[Any],
        provenance: Optional[StudioRouteProvenance],
    ) -> List[StudioArtifactRef]:
        refs: List[StudioArtifactRef] = []
        input_ids = [a.artifact_id for a in envelope.input_artifact_refs]
        for model in outputs:
            content = model.to_canonical_dict()
            content_hash = model.content_hash()
            existing = await uow.artifacts.find_by_hash(content_hash)
            if existing is not None:
                refs.append(
                    StudioArtifactRef(
                        artifact_id=existing.artifact_id,
                        artifact_type=model.artifact_type,
                        content_hash=existing.content_hash,
                    )
                )
                continue
            from windagent_core.contracts.studio.ids import ArtifactId

            from windagent_core.domain.studio.artifact import StoryArtifactEnvelope

            artifact = StoryArtifactEnvelope(
                artifact_id=ArtifactId(f"art_{content_hash[:16]}"),
                artifact_type=model.artifact_type,
                series_id=envelope.series_id,
                episode_id=envelope.episode_id,
                revision_id=envelope.revision_id,
                content_hash=content_hash,
                input_artifact_refs=[ArtifactId(str(i)) for i in input_ids],
                prompt_id=provenance.prompt_id if provenance else None,
                prompt_version=provenance.prompt_version if provenance else None,
                prompt_hash=provenance.prompt_hash if provenance else None,
                model_route_id=getattr(provenance, "model_route_id", None),
                provider_id=provenance.provider_id if provenance else None,
                model_id=provenance.model_id if provenance else None,
                canonical_model_id=(
                    provenance.canonical_model_id if provenance else None
                ),
                provider_model_id=(
                    provenance.provider_model_id if provenance else None
                ),
                endpoint_id=provenance.endpoint_id if provenance else None,
                provider_binding_id=(
                    provenance.provider_binding_id if provenance else None
                ),
                provider_attempt_id=(
                    provenance.provider_attempt_id if provenance else None
                ),
                provider_request_id=(
                    provenance.provider_request_id if provenance else None
                ),
                output_schema_contract=(
                    provenance.output_schema_contract if provenance else None
                ),
                created_by=f"worker:{self._worker_id}:task:{handle.step_run_id}:fence:{handle.fencing_token[:8]}",
                content=content,
            )
            await uow.artifacts.save(artifact)
            refs.append(
                StudioArtifactRef(
                    artifact_id=artifact.artifact_id,
                    artifact_type=model.artifact_type,
                    content_hash=content_hash,
                )
            )
        return refs

    def _fail(
        self,
        handle: ExecutionHandle,
        code: str,
        detail: str,
        *,
        envelope: Optional[StudioTaskEnvelope] = None,
        task_id: Optional[str] = None,
    ) -> ExecutionResult:
        error = f"{code}: {detail}"
        result: Optional[StudioTaskResult] = None
        if envelope is not None:
            result = StudioTaskResult(
                task_id=task_id or envelope.task_id,
                studio_run_id=envelope.studio_run_id,
                dag_node_id=envelope.dag_node_id,
                status=StudioTaskStatus.FAILED,
                error=error,
            )
        return ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=RuntimeStatusEnum.FAILED,
            result_data=result.to_dict() if result is not None else None,
            error=error,
        )

    def _cancel(
        self,
        handle: ExecutionHandle,
        envelope: StudioTaskEnvelope,
        *,
        task_id: Optional[str] = None,
    ) -> ExecutionResult:
        result = StudioTaskResult(
            task_id=task_id or envelope.task_id,
            studio_run_id=envelope.studio_run_id,
            dag_node_id=envelope.dag_node_id,
            status=StudioTaskStatus.CANCELLED,
            error="STUDIO_TASK_CANCELLED: cooperative cancellation before side effects",
        )
        return ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=RuntimeStatusEnum.CANCELLED,
            result_data=result.to_dict(),
            error=result.error,
        )

    def _is_fixture_model_port(self) -> bool:
        if self._model_port is None:
            return False
        try:
            from windagent_intelligence.story.prompts.fixture import is_fixture_provider

            return bool(is_fixture_provider(self._model_port))
        except Exception:  # noqa: BLE001 — absence of the check fails open is NOT ok
            return True


class StudioModelPortUnavailable(Exception):
    """Handler requires a model port that the worker does not compose."""


class StudioInputArtifactMissing(Exception):
    """Envelope references an input artifact that is absent or of the wrong type."""


class StudioUnsupportedTaskType(Exception):
    """Frozen task type has no execution mapping in this runtime version."""


# ---------------------------------------------------------------------------
# Completion recovery (crash window: after finalizer commit, before reconcile)
# ---------------------------------------------------------------------------


class StudioCompletionRecovery:
    """Re-drives the reconciler for terminal Studio tasks never reconciled.

    Idempotent: the reconciler answers ``duplicate=True`` for nodes already
    advanced, and raises ``StudioNotFoundError`` for runs that no longer
    exist (skipped + logged).
    """

    def __init__(
        self,
        session_factory: Any,
        reconciler: Any,
    ) -> None:
        self._session_factory = session_factory
        self._reconciler = reconciler

    async def recover_pending_completions(self) -> int:
        from windagent_core.contracts.studio.errors import StudioNotFoundError
        from windagent_storage.studio.completions import list_terminal_studio_completions

        recovered = 0
        for row in await list_terminal_studio_completions(self._session_factory):
            try:
                raw_result = row["facts"].get("result")
                if not isinstance(raw_result, dict):
                    continue
                result = StudioTaskResult.model_validate(raw_result)
                outcome = await self._reconciler.reconcile(result)
                if isinstance(outcome, dict) and outcome.get("duplicate"):
                    continue  # already advanced; sweep must stay idempotent
                recovered += 1
            except StudioNotFoundError as exc:
                logger.info(f"Recovery skipped unknown run completion: {exc}")
            except Exception as exc:  # noqa: BLE001 — one bad row never blocks the sweep
                logger.warning(f"Recovery failed for task [{row['task_id']}]: {exc}")
        if recovered:
            logger.info(f"Studio completion recovery reconciled {recovered} pending completion(s).")
        return recovered


__all__ = [
    "StudioRuntimeAdapter",
    "StudioCompletionRecovery",
    "StudioModelPortUnavailable",
    "StudioInputArtifactMissing",
    "StudioUnsupportedTaskType",
    "certification_enabled",
    "is_studio_task",
    "redact",
    "ENVELOPE_INVALID",
    "UNREGISTERED_TASK_TYPE",
    "CERTIFICATION_VIOLATION",
    "MODEL_PORT_UNAVAILABLE",
]
