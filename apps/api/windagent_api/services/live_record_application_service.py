"""Live Record application service (live_record.contract/v0.1).

Maps frozen V3 requests onto the ``*RepositoryPort`` protocols from
``windagent_core.contracts.live_record.ports``. The composition root binds a
repo-bundle factory over the async session factory; each service call opens
one session, runs its use case, and commits only on success.

Fail-closed invariants owned here:
- A RecordingTake may only be created for a FROZEN plan; the take stamps the
  plan's canonical ``plan_hash`` at creation.
- Timeline events append to an existing take only.
- Plan lifecycle rules (validate/freeze/staleness) live in the plan aggregate,
  not here — this service orchestrates persistence and error translation.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from windagent_core.contracts.live_record.errors import (
    LiveRecordCapabilityUnavailableError,
    LiveRecordNotFoundError,
    LiveRecordNotFrozenError,
    LiveRecordValidationError,
)
from windagent_core.contracts.live_record.ids import (
    DirectorSessionId,
    LiveExecutionPlanId,
    RecordingTakeId,
)
from windagent_core.domain.live_record.lifecycle import PlanStatusStateMachine
from windagent_core.domain.live_record.plan import (
    ExpectedVisualState,
    LiveExecutionPlan,
    PreparedAction,
    RecordingCue,
    RecordingProfile,
    RecordingScene,
)
from windagent_core.domain.live_record.runtime import (
    DirectorSessionRecord,
    RecordingEventRecord,
    RecordingSegmentRecord,
    RecordingTakeRecord,
)


def _coerce_scene(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate nested value objects eagerly so pydantic errors surface at the
    API boundary with full context."""
    data = dict(payload)
    cues = data.get("cues")
    if cues is not None:
        data["cues"] = [RecordingCue.model_validate(c) for c in cues]
    return data


def _coerce_action(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(payload)
    expected = data.get("expected_after")
    if expected is not None:
        data["expected_after"] = ExpectedVisualState.model_validate(expected)
    return data


class LiveRecordApplicationService:
    """Application boundary for the Episode -> Plan -> Take lineage."""

    def __init__(
        self,
        *,
        session_factory: Any,
        repo_bundle_factory: Callable[[Any], Any],
        credential_resolver: Optional[Callable[[str], Any]] = None,
    ) -> None:
        if session_factory is None:
            raise LiveRecordCapabilityUnavailableError(
                "Live Record session factory is not composed.",
                details={"missing": "session_factory"},
            )
        if repo_bundle_factory is None:
            raise LiveRecordCapabilityUnavailableError(
                "Live Record repositories are not composed.",
                details={"missing": "repo_bundle_factory"},
            )
        self.session_factory = session_factory
        self.repo_bundle_factory = repo_bundle_factory
        # Optional async callable provider_id -> api_key | None. Composed in
        # production (provider management repo + decrypt); tests may omit it.
        self.credential_resolver = credential_resolver

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def parse_id(cls_: type, raw: str, field_name: str):
        try:
            return cls_(raw)
        except Exception as exc:
            raise LiveRecordValidationError(
                f"Invalid {field_name} identifier {raw!r}.",
                details={"field": field_name},
            ) from exc

    async def _transact(self, fn, *, commit: bool):
        """Run ``fn(bundle)`` inside one session; commit only when asked."""
        async with self.session_factory() as session:
            bundle = self.repo_bundle_factory(session)
            result = await fn(bundle)
            if commit:
                await session.commit()
            else:
                await session.rollback()
            return result

    async def _load_plan(self, bundle, plan_id_raw: str) -> LiveExecutionPlan:
        plan = await bundle.plans.get(LiveExecutionPlanId(plan_id_raw))
        if plan is None:
            raise LiveRecordNotFoundError(
                f"Execution plan {plan_id_raw!r} does not exist.",
                details={"plan_id": plan_id_raw},
            )
        return plan

    async def _load_take(self, bundle, take_id_raw: str) -> RecordingTakeRecord:
        take = await bundle.takes.get(RecordingTakeId(take_id_raw))
        if take is None:
            raise LiveRecordNotFoundError(
                f"Recording take {take_id_raw!r} does not exist.",
                details={"take_id": take_id_raw},
            )
        return take

    # -- preparation package (Phase 2) ------------------------------------

    async def prepare_recording_package(
        self,
        *,
        payload: Dict[str, Any],
        idempotency_key: str,
    ) -> Dict[str, Any]:
        """Build a Recording Preparation Package from Episode workspace input.

        Input shape is the same as ``EpisodePreparationInput`` (Section 5):
        high-level scenes with authored actions that the builder freezes into
        exact payload_bundles + artifact:// refs. The resulting plan is
        persisted as DRAFT and may be driven to FROZEN via the normal
        lifecycle endpoints.
        """
        from windagent_core.domain.live_record.preparation import (
            RecordingPreparationBuilder,
        )

        async def op(b):
            # Allocate preparation_revision deterministically per episode.
            episode_id = payload["episode_id"]
            revision = await b.plans.next_preparation_revision(episode_id)
            builder_payload = {**payload, "preparation_revision": revision}
            plan = RecordingPreparationBuilder.build_from_api_payload(builder_payload)
            # Idempotency: retry with same episode+revision lands on same row.
            existing = await b.plans.get(plan.plan_id)
            if existing is not None:
                return existing
            return await b.plans.save(plan)

        return self.plan_view(await self._transact(op, commit=True))

    # -- plans ------------------------------------------------------------

    async def create_plan(
        self,
        *,
        episode_id: str,
        episode_revision_id: str,
        scenes: List[Dict[str, Any]],
        actions: List[Dict[str, Any]],
        recording_profile: Optional[Dict[str, Any]] = None,
        payload_bundles: Optional[Dict[str, str]] = None,
        idempotency_key: str,
    ) -> Dict[str, Any]:

        async def op(b):
            revision = await b.plans.next_preparation_revision(episode_id)
            # Deterministic identity: retrying the same creation command lands
            # on the same plan row instead of duplicating it.
            plan_id = LiveExecutionPlanId(f"plan_{episode_id}_r{revision}")
            existing = await b.plans.get(plan_id)
            if existing is not None:
                return existing
            plan = LiveExecutionPlan.model_validate(
                {
                    "plan_id": plan_id,
                    "episode_id": episode_id,
                    "episode_revision_id": episode_revision_id,
                    "preparation_revision": revision,
                    "recording_profile": RecordingProfile.model_validate(
                        recording_profile or {}
                    ),
                    "scenes": [
                        RecordingScene.model_validate(_coerce_scene(s)) for s in scenes
                    ],
                    "actions": [
                        PreparedAction.model_validate(_coerce_action(a)) for a in actions
                    ],
                    "payload_bundles": payload_bundles or {},
                }
            )
            plan.validate_lineage()
            return await b.plans.save(plan)

        return self.plan_view(await self._transact(op, commit=True))

    async def get_plan(self, plan_id_raw: str) -> Dict[str, Any]:

        async def op(b):
            return await self._load_plan(b, plan_id_raw)

        return self.plan_view(await self._transact(op, commit=False))

    async def list_plans(self, episode_id: str) -> List[Dict[str, Any]]:

        async def op(b):
            return await b.plans.list_by_episode(episode_id)

        return [self.plan_view(p) for p in await self._transact(op, commit=False)]

    async def patch_plan_content(
        self,
        *,
        plan_id_raw: str,
        scenes: Optional[List[Dict[str, Any]]] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
        payload_bundles: Optional[Dict[str, str]] = None,
        source_workspace_hash: Optional[str] = None,
        idempotency_key: str,
    ) -> Dict[str, Any]:

        async def op(b):
            plan = await self._load_plan(b, plan_id_raw)
            updated = plan.edit_content(
                scenes=(
                    [RecordingScene.model_validate(_coerce_scene(s)) for s in scenes]
                    if scenes is not None
                    else None
                ),
                actions=(
                    [PreparedAction.model_validate(_coerce_action(a)) for a in actions]
                    if actions is not None
                    else None
                ),
                payload_bundles=payload_bundles,
                source_workspace_hash=source_workspace_hash,
            )
            return await b.plans.save(updated)

        return self.plan_view(await self._transact(op, commit=True))

    async def transition_plan(
        self,
        *,
        plan_id_raw: str,
        action: str,
        idempotency_key: str,
        current_episode_revision_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply one lifecycle command: ``validate`` | ``freeze`` |
        ``mark-stale`` | ``mark-invalid``; or ``check`` to assert the plan is
        not stale against the episode's current revision without mutating."""

        async def op(b):
            plan = await self._load_plan(b, plan_id_raw)
            if current_episode_revision_id is not None:
                reason = plan.staleness_reason(current_episode_revision_id)
                if reason:
                    raise LiveRecordValidationError(
                        reason,
                        details={"plan_id": plan_id_raw},
                    )
            if action == "check":
                return plan
            operations = {
                "prepare": plan.mark_prepared,
                "validate": plan.mark_validated,
                "freeze": plan.freeze,
                "mark-stale": plan.mark_stale,
                "mark-invalid": plan.mark_invalid,
            }
            if action not in operations:
                raise LiveRecordValidationError(
                    f"Unknown plan lifecycle action '{action}'.",
                    details={"action": action},
                )
            updated = operations[action]()
            return await b.plans.save(updated)

        return self.plan_view(await self._transact(op, commit=(action != "check")))

    # -- takes & timeline ---------------------------------------------------

    async def create_take(
        self, *, plan_id_raw: str, idempotency_key: str
    ) -> Dict[str, Any]:

        async def op(b):
            plan = await self._load_plan(b, plan_id_raw)
            # Fail-closed gate: only FROZEN plans start recording takes.
            plan.assert_usable_for_recording(plan.episode_revision_id)
            seq = len(await b.takes.list_by_plan(str(plan.plan_id))) + 1
            take = RecordingTakeRecord(
                take_id=str(RecordingTakeId(f"take_{plan.episode_id}_{seq}")),
                execution_plan_id=str(plan.plan_id),
                execution_plan_hash=plan.plan_hash,
                episode_id=plan.episode_id,
                session_status="IDLE",
                metadata={"created_via": "api"},
            )
            return await b.takes.save(take)

        return self.take_view(await self._transact(op, commit=True))

    async def list_takes(self, plan_id_raw: str) -> List[Dict[str, Any]]:
        plan_id = self.parse_id(LiveExecutionPlanId, plan_id_raw, "plan_id")

        async def op(b):
            return await b.takes.list_by_plan(str(plan_id))

        return [self.take_view(t) for t in await self._transact(op, commit=False)]

    async def get_take(self, take_id_raw: str) -> Dict[str, Any]:

        async def op(b):
            return await self._load_take(b, take_id_raw)

        return self.take_view(await self._transact(op, commit=False))

    async def append_take_event(
        self, *, take_id_raw: str, payload: Dict[str, Any], idempotency_key: str
    ) -> Dict[str, Any]:

        async def op(b):
            await self._load_take(b, take_id_raw)
            event = RecordingEventRecord.model_validate(
                {**payload, "take_id": take_id_raw}
            )
            return await b.events.append(event)

        return self.event_view(await self._transact(op, commit=True))

    async def list_take_events(self, take_id_raw: str) -> List[Dict[str, Any]]:
        take_id = self.parse_id(RecordingTakeId, take_id_raw, "take_id")

        async def op(b):
            return await b.events.list_by_take(str(take_id))

        return [self.event_view(e) for e in await self._transact(op, commit=False)]

    # -- segments (MKV segment lineage: engine → host → DB) ----------------------

    async def record_take_segment(
        self,
        *,
        take_id_raw: str,
        payload: Dict[str, Any],
        idempotency_key: str = "",
    ) -> Dict[str, Any]:
        """Ingest one finalized MKV segment reported by the desktop host.

        POST /api/v3/live-record/takes/{take_id}/segments

        The sidecar announces every completed ``segment_*.mkv`` via
        ``recorder://segment``; the host relays it here so Take→Segment lineage
        survives in the database (LR_P8). Upsert keyed by ``segment_id`` —
        replays after reconnect are idempotent.
        """

        async def op(b):
            await self._load_take(b, take_id_raw)
            body = {**payload, "take_id": take_id_raw}
            if not body.get("segment_id"):
                index = int(body.get("segment_index", 0))
                body["segment_id"] = f"{take_id_raw}_seg{index:04d}"
            segment = RecordingSegmentRecord.model_validate(body)
            return await b.segments.save(segment)

        record = await self._transact(op, commit=True)
        return self.segment_view(record)

    async def list_take_segments(self, take_id_raw: str) -> List[Dict[str, Any]]:
        take_id = self.parse_id(RecordingTakeId, take_id_raw, "take_id")

        async def op(b):
            return await b.segments.list_by_take(str(take_id))

        return [self.segment_view(s) for s in await self._transact(op, commit=False)]

    @staticmethod
    def segment_view(record: RecordingSegmentRecord) -> Dict[str, Any]:
        return record.model_dump(mode="json")

    # -- director session bootstrap (Phase 5) ------------------------------------

    async def bootstrap_director_session(
        self,
        *,
        episode_id: str,
        execution_plan_id: str,
        current_episode_revision_id: Optional[str] = None,
        idempotency_key: str,
    ) -> Dict[str, Any]:
        """POST /api/v3/live-record/sessions/bootstrap

        Flow (ban_ke_hoach_v1.md Section 10):
            Desktop → WindAgent API
              → Resolve LIVE_DIRECTOR (capability-gated model selection)
              → Google provider credential check
              → live capability check
              → issue ephemeral token (short-lived, one-session, never persisted)
              → Desktop → Google Live API (direct, no proxy)

        Fail-closed guards:
            - plan must be FROZEN (otherwise 409 PLAN_NOT_FROZEN)
            - plan must not be stale (current_episode_revision mismatch → 422 PLAN_STALE)
            - LIVE_DIRECTOR must resolve to a live_api+video_input+tool_use+chat model
            - provider must be configured (otherwise 503 CAPABILITY_UNAVAILABLE)

        Token invariants (enforced here and by provider.live.token_service):
            - not persisted (only sha256 stored server-side if needed)
            - not logged, not returned via GET
            - one-session use
            - constrained to exact model/config + execution_plan_hash
        """

        async def op(b):
            plan = await self._load_plan(b, execution_plan_id)
            # episode_id must match plan ownership
            if plan.episode_id != episode_id:
                raise LiveRecordValidationError(
                    f"Episode mismatch: plan bound to {plan.episode_id!r}, got {episode_id!r}.",
                    details={"episode_id": episode_id, "plan_id": execution_plan_id},
                )
            # Staleness check (Principle A) — optional when caller passes current revision
            check_revision = current_episode_revision_id or plan.episode_revision_id
            reason = plan.staleness_reason(check_revision)
            if reason:
                raise LiveRecordValidationError(
                    reason, details={"plan_id": execution_plan_id}
                )
            # Only FROZEN plans may bootstrap a director session
            plan.assert_usable_for_recording(check_revision)

            # Resolve LIVE_DIRECTOR model via capability matrix
            from windagent_core.contracts.providers.model_capabilities import (
                resolve_live_director_model,
            )
            from windagent_providers.google.live.capability import (
                LIVE_DIRECTOR_DISPLAY_NAME,
            )
            from windagent_providers.google.live.token_service import (
                EphemeralTokenService,
            )

            live_profile = resolve_live_director_model()
            if live_profile is None:
                raise LiveRecordCapabilityUnavailableError(
                    "No LIVE_DIRECTOR-capable model available (live_api+video_input+chat+tool_use).",
                    details={"role": "LIVE_DIRECTOR"},
                )

            # Credential resolution — fail-closed when a resolver is composed:
            # a missing Google credential must never silently downgrade to a
            # locally-minted envelope in production. When no resolver is
            # composed at all (unit tests / hermetic CI), the local envelope
            # fallback keeps the contract verifiable without credentials.
            provider_id = live_profile.provider_name
            model_id = live_profile.model_id

            api_key: Optional[str] = None
            if self.credential_resolver is not None:
                api_key = await self.credential_resolver(provider_id)
                if not api_key:
                    raise LiveRecordCapabilityUnavailableError(
                        f"Provider '{provider_id}' has no configured credential; "
                        "refusing to issue a LIVE_DIRECTOR token (fail-closed).",
                        details={
                            "provider_id": provider_id,
                            "code_hint": "PROVIDER_CREDENTIAL_MISSING",
                            "role": "LIVE_DIRECTOR",
                        },
                    )

            # Mint ephemeral token (30 min TTL) — remote Google auth_tokens
            # when a credential exists, local signed-envelope fallback otherwise.
            session_id = str(DirectorSessionId.generate(prefix="ldir"))
            token_service = EphemeralTokenService(
                provider_id=provider_id, model_id=model_id
            )
            token_mode = "local-fallback"
            if api_key:
                from windagent_providers.google.live.token_service import (
                    EphemeralTokenMintError,
                )
                try:
                    token_obj = await token_service.mint_remote(
                        api_key=api_key,
                        session_id=session_id,
                        execution_plan_hash=plan.plan_hash,
                    )
                    token_mode = "remote"
                except EphemeralTokenMintError as exc:
                    raise LiveRecordCapabilityUnavailableError(
                        "Google auth_tokens rejected the ephemeral token mint "
                        "request; refusing to fall back to a local token.",
                        details={"provider_id": provider_id},
                    ) from exc
            else:
                token_obj = token_service.mint(
                    execution_plan_hash=plan.plan_hash,
                    session_id=session_id,
                )

            # Persist DirectorSessionRecord (token_hash only, never raw token)
            session_record = DirectorSessionRecord(
                session_id=session_id,
                execution_plan_id=str(plan.plan_id),
                execution_plan_hash=plan.plan_hash,
                provider_id=provider_id,
                model_id=model_id,
                connection_state="CONNECTING",
                expires_at=token_obj.expires_at,
                metadata={
                    "token_hash": token_service.token_hash(token_obj.token),
                    "token_mode": token_mode,
                    "episode_id": episode_id,
                    "display_name": LIVE_DIRECTOR_DISPLAY_NAME,
                    "idempotency_key": idempotency_key,
                },
            )
            await b.directors.save(session_record)

            # Ephemeral response — token appears ONLY here, never via GET
            return {
                "session_id": session_id,
                "provider_id": provider_id,
                "model_id": model_id,
                "token": token_obj.token,
                "expires_at": token_obj.expires_at.isoformat(),
                "execution_plan_hash": plan.plan_hash,
                "display_name": LIVE_DIRECTOR_DISPLAY_NAME,
            }

        return await self._transact(op, commit=True)

    async def get_director_session(self, session_id: str) -> Dict[str, Any]:
        """GET director session (never returns raw token)."""

        async def op(b):
            from windagent_core.contracts.live_record.ids import DirectorSessionId as DSId

            record = await b.directors.get(DSId(session_id))
            if record is None:
                raise LiveRecordNotFoundError(
                    f"Director session {session_id!r} does not exist.",
                    details={"session_id": session_id},
                )
            # Project without token — token is one-time use and never persisted
            data = record.model_dump(mode="json")
            data["has_token"] = False
            return data

        return await self._transact(op, commit=False)

    async def refresh_director_token(
        self,
        *,
        session_id_raw: str,
        idempotency_key: str,
    ) -> Dict[str, Any]:
        """POST /api/v3/live-record/sessions/{session_id}/token-refresh

        Section 24/§35 (token refresh): ephemeral tokens have a bounded
        lifetime (~30 min) while takes may run longer. A reconnecting desktop
        re-mints a fresh ephemeral token bound to the SAME session, model and
        frozen plan_hash — the director loop keeps its resumption handle and
        never replays successful actions.

        Fail-closed guards mirror bootstrap: plan must still be FROZEN and not
        stale; a composed credential resolver finding no credential refuses to
        mint. Raw token appears only in this response.
        """

        async def op(b):
            from windagent_core.contracts.live_record.ids import (
                DirectorSessionId as DSId,
            )
            from windagent_providers.google.live.capability import (
                LIVE_DIRECTOR_DISPLAY_NAME,
            )
            from windagent_providers.google.live.token_service import (
                EphemeralTokenMintError,
                EphemeralTokenService,
            )

            record = await b.directors.get(DSId(session_id_raw))
            if record is None:
                raise LiveRecordNotFoundError(
                    f"Director session {session_id_raw!r} does not exist.",
                    details={"session_id": session_id_raw},
                )

            plan = await self._load_plan(b, record.execution_plan_id)
            plan.assert_usable_for_recording(plan.episode_revision_id)

            provider_id = record.provider_id
            model_id = record.model_id

            api_key: Optional[str] = None
            if self.credential_resolver is not None:
                api_key = await self.credential_resolver(provider_id)
                if not api_key:
                    raise LiveRecordCapabilityUnavailableError(
                        f"Provider '{provider_id}' has no configured credential; "
                        "refusing to refresh the LIVE_DIRECTOR token (fail-closed).",
                        details={
                            "provider_id": provider_id,
                            "code_hint": "PROVIDER_CREDENTIAL_MISSING",
                            "role": "LIVE_DIRECTOR",
                        },
                    )

            token_service = EphemeralTokenService(
                provider_id=provider_id, model_id=model_id
            )
            token_mode = "local-fallback"
            if api_key:
                try:
                    token_obj = await token_service.mint_remote(
                        api_key=api_key,
                        session_id=session_id_raw,
                        execution_plan_hash=plan.plan_hash,
                    )
                    token_mode = "remote"
                except EphemeralTokenMintError as exc:
                    raise LiveRecordCapabilityUnavailableError(
                        "Google auth_tokens rejected the ephemeral token refresh "
                        "request; refusing to fall back to a local token.",
                        details={"provider_id": provider_id},
                    ) from exc
            else:
                token_obj = token_service.mint(
                    execution_plan_hash=plan.plan_hash,
                    session_id=session_id_raw,
                )

            metadata = dict(record.metadata or {})
            metadata.update(
                {
                    "token_hash": token_service.token_hash(token_obj.token),
                    "token_mode": token_mode,
                    "idempotency_key": idempotency_key,
                    "refresh_count": int(metadata.get("refresh_count", 0)) + 1,
                }
            )
            updated = record.model_copy(
                update={
                    "expires_at": token_obj.expires_at,
                    "metadata": metadata,
                }
            )
            await b.directors.save(updated)

            return {
                "session_id": session_id_raw,
                "provider_id": provider_id,
                "model_id": model_id,
                "token": token_obj.token,
                "expires_at": token_obj.expires_at.isoformat(),
                "execution_plan_hash": plan.plan_hash,
                "display_name": metadata.get("display_name", LIVE_DIRECTOR_DISPLAY_NAME),
                "refreshed": True,
            }

        return await self._transact(op, commit=True)

    # -- privacy scan (Section 23/33 preflight guard) ----------------------------

    #: Providers whose configured credentials are exact-match scanned against
    #: plan content. Resolution failures are swallowed — a provider that is not
    #: configured simply contributes nothing to scan.
    PRIVACY_SCAN_PROVIDER_IDS = ("google", "openai", "anthropic")

    async def scan_plan_privacy(
        self,
        *,
        plan_id_raw: str,
    ) -> Dict[str, Any]:
        """POST /api/v3/live-record/plans/{plan_id}/privacy-scan

        Section 23 preflight invariant: "Privacy scan đạt: không secret trong
        vùng quay". The API host cannot see the screen, so it proves the part
        it owns — no configured provider credential and no credential-shaped
        string may appear anywhere in the frozen preparation content that will
        be typed, spoken or shown during the take.
        """

        from windagent_core.domain.live_record.privacy_scan import (
            scan_live_record_plan,
        )

        extra_values: List[str] = []
        if self.credential_resolver is not None:
            for provider_id in self.PRIVACY_SCAN_PROVIDER_IDS:
                try:
                    value = await self.credential_resolver(provider_id)
                except Exception:  # noqa: BLE001 — unconfigured provider is fine here
                    continue
                if isinstance(value, str) and value.strip():
                    extra_values.append(value)

        async def op(b):
            return await self._load_plan(b, plan_id_raw)

        plan = await self._transact(op, commit=False)
        report = scan_live_record_plan(
            payload_bundles=plan.payload_bundles,
            scenes=plan.scenes,
            actions=plan.actions,
            extra_secret_values=extra_values,
        )
        result = report.to_dict()
        result["plan_id"] = str(plan.plan_id)
        result["plan_status"] = plan.status.value
        return result

    # -- prepared action dispatch (Phase 3/7 — constrained executor) -------------

    async def prepare_action_dispatch(
        self, *, plan_id_raw: str, action_id_raw: str
    ) -> Dict[str, Any]:
        """Resolve one prepared action into a desktop dispatch ticket.

        POST /api/v3/live-record/live-record/plans/{plan_id}/actions/{action_id}/prepare

        Fail-closed guards:
            - plan must be FROZEN (Principle A);
            - action_id must exist in the frozen plan (ACTION_NOT_IN_PLAN);
            - CODE_PLAYBACK payload must resolve from the plan's own bundle
              store — the ticket carries the operator's prepared content to the
              operator's desktop, never model-generated text.
        """

        async def op(b):
            plan = await self._load_plan(b, plan_id_raw)
            if not PlanStatusStateMachine.is_frozen(plan.status):
                raise LiveRecordNotFrozenError(
                    f"ACTION_DISPATCH_NOT_FROZEN: plan status={plan.status.value}.",
                    details={"plan_id": plan_id_raw, "status": plan.status.value},
                )
            action = next(
                (a for a in plan.actions if a.action_id == action_id_raw), None
            )
            if action is None:
                raise LiveRecordNotFoundError(
                    f"ACTION_NOT_IN_PLAN: action '{action_id_raw}' is not part of "
                    f"plan '{plan_id_raw}'.",
                    details={"plan_id": plan_id_raw, "action_id": action_id_raw},
                )
            payload_text = plan.payload_bundles.get(action.action_id)
            if action.type == "CODE_PLAYBACK" and payload_text is None:
                raise LiveRecordValidationError(
                    f"PAYLOAD_BUNDLE_MISSING: no prepared payload bundle for "
                    f"action '{action.action_id}'.",
                    details={"action_id": action.action_id},
                )
            return {
                "plan_id": str(plan.plan_id),
                "plan_hash": plan.plan_hash,
                "action": action.model_dump(mode="json"),
                "payload_text": payload_text,
                "expected_after": (
                    action.expected_after.model_dump(mode="json")
                    if action.expected_after is not None
                    else None
                ),
            }

        return await self._transact(op, commit=False)

    async def record_action_result(
        self,
        *,
        plan_id_raw: str,
        take_id_raw: str,
        action_id_raw: str,
        status: str,
        execution_id: str,
        idempotency_key: str,
        t: float,
        detail: str = "",
        before_hash_observed: Optional[str] = None,
        after_hash_observed: Optional[str] = None,
        observed: Optional[Dict[str, Any]] = None,
        scene_id: Optional[str] = None,
        cue_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify a desktop-executed action and append its timeline event.

        POST /api/v3/live-record/plans/{plan_id}/actions/result

        CODE_PLAYBACK results are hash-verified against the frozen plan's
        before_hash/after_hash (tool_contract.md invariant 4); a mismatch is a
        tamper event — the timeline records ACTION_TAMPERED and the result is
        reported as FAILURE regardless of what the desktop claimed.
        """

        async def op(b):
            plan = await self._load_plan(b, plan_id_raw)
            if not PlanStatusStateMachine.is_frozen(plan.status):
                raise LiveRecordNotFrozenError(
                    f"ACTION_RESULT_NOT_FROZEN: plan status={plan.status.value}.",
                    details={"plan_id": plan_id_raw},
                )
            action = next(
                (a for a in plan.actions if a.action_id == action_id_raw), None
            )
            if action is None:
                raise LiveRecordNotFoundError(
                    f"ACTION_NOT_IN_PLAN: action '{action_id_raw}' is not part of "
                    f"plan '{plan_id_raw}'.",
                    details={"plan_id": plan_id_raw, "action_id": action_id_raw},
                )
            take = await self._load_take(b, take_id_raw)
            if take.execution_plan_id != str(plan.plan_id):
                raise LiveRecordValidationError(
                    "TAKE_PLAN_MISMATCH: take does not belong to this plan.",
                    details={"take_id": take_id_raw, "plan_id": plan_id_raw},
                )

            verification: Dict[str, Any] = {"verified": True, "checks": []}
            event_type = "ACTION_SUCCESS" if status == "SUCCESS" else "ACTION_FAILURE"
            if action.type == "CODE_PLAYBACK":
                checks = verification["checks"]
                if action.before_hash is not None:
                    ok = before_hash_observed == action.before_hash
                    checks.append({"check": "before_hash", "ok": ok})
                    if not ok:
                        verification["verified"] = False
                if action.after_hash is not None:
                    ok = after_hash_observed == action.after_hash
                    checks.append({"check": "after_hash", "ok": ok})
                    if not ok:
                        verification["verified"] = False
                if not verification["verified"]:
                    event_type = "ACTION_TAMPERED"

            event = RecordingEventRecord(
                take_id=take_id_raw,
                event_type=event_type,
                t=t,
                scene_id=scene_id or action.scene_id,
                cue_id=cue_id or action.cue_id,
                action_id=action.action_id,
                execution_id=execution_id,
                detail=detail,
                payload={
                    "status": status,
                    "verification": verification,
                    "idempotency_key": idempotency_key,
                    **(observed or {}),
                },
            )
            saved = await b.events.append(event)
            return {"event": self.event_view(saved), "verification": verification}

        return await self._transact(op, commit=True)

    # -- views ---------------------------------------------------------------

    @staticmethod
    def plan_view(plan: LiveExecutionPlan) -> Dict[str, Any]:
        data = plan.model_dump(mode="json")
        data["status"] = plan.status.value
        data["recordable"] = PlanStatusStateMachine.is_recordable(plan.status)
        return data

    @staticmethod
    def take_view(record: RecordingTakeRecord) -> Dict[str, Any]:
        return record.model_dump(mode="json")

    @staticmethod
    def event_view(record: RecordingEventRecord) -> Dict[str, Any]:
        return record.model_dump(mode="json")


__all__ = ["LiveRecordApplicationService"]
