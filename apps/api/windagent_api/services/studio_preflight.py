"""Story Start preflight — server-authoritative START_BLOCKED gate (P0.4.1).

Before a Story run is started the server verifies:

    episode exists → creative brief valid → provider configured →
    required routing rules resolve → worker capability available →
    persistence available

Every failed check becomes an explicit reason; when any check fails the start
endpoint answers ``START_BLOCKED`` with those reasons instead of enqueueing a
doomed DAG. The report itself is always truthful data (PASS/FAIL per check),
never a fabricated green light.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_core.contracts.studio.story_roles import expand_role_labels
from windagent_core.domain.story.ideation import CreativeBrief
from windagent_providers.routing.rule_matcher import RuleMatchContext, RuleMatcher

#: Capabilities that MUST resolve through routing for a story run to proceed.
REQUIRED_STORY_CAPABILITIES = (
    "ideation",
    "bibles",
    "beats",
    "outline",
    "screenplay",
    "review",
    "revise",
)

CHECK_NAMES = (
    "episode_exists",
    "creative_brief_valid",
    "provider_configured",
    "routing_rules_resolve",
    "worker_capability_available",
    "persistence_available",
)


class StoryStartPreflight:
    """Compose the six P0.4.1 checks from real runtime authorities."""

    def __init__(
        self,
        *,
        episodes_repo: Any,
        series_repo: Any,
        provider_management_service: Any,
        route_lock_service: Any,
        capability_provider: Optional[Any] = None,
        matcher: Optional[RuleMatcher] = None,
    ) -> None:
        self._episodes_repo = episodes_repo
        self._series_repo = series_repo
        self._providers = provider_management_service
        self._route_locks = route_lock_service
        self._capability = capability_provider
        self._matcher = matcher or RuleMatcher()

    async def run(self, episode_id: Any) -> Dict[str, Any]:
        checks: List[Dict[str, str]] = []
        episode = None
        try:
            episode = await self._episodes_repo.get(episode_id)
        except Exception as exc:  # noqa: BLE001 — persistence failure is a finding
            checks.append(
                {"name": "episode_exists", "status": "FAIL", "detail": f"episode query failed: {type(exc).__name__}"}
            )
        if episode is not None:
            checks.append({"name": "episode_exists", "status": "PASS", "detail": ""})
        elif not any(c["name"] == "episode_exists" for c in checks):
            checks.append(
                {"name": "episode_exists", "status": "FAIL", "detail": "episode not found"}
            )

        # 2. Creative brief parses against the frozen CreativeBrief contract.
        brief_raw = (getattr(episode, "metadata", None) or {}).get("creative_brief")
        if brief_raw is None:
            checks.append(
                {"name": "creative_brief_valid", "status": "FAIL", "detail": "metadata.creative_brief missing"}
            )
        else:
            try:
                CreativeBrief.model_validate(brief_raw)
                checks.append({"name": "creative_brief_valid", "status": "PASS", "detail": ""})
            except Exception as exc:  # noqa: BLE001 — invalid brief is a finding
                checks.append(
                    {
                        "name": "creative_brief_valid",
                        "status": "FAIL",
                        "detail": f"invalid creative brief: {type(exc).__name__}",
                    }
                )

        # 3. At least one enabled provider with a configured endpoint.
        try:
            providers = self._providers.list_providers()
            usable = [
                p
                for p in providers or []
                if p.get("enabled", True)
                and any(
                    ep.get("is_configured") or ep.get("credential_configured")
                    for ep in (p.get("endpoints") or [])
                )
            ]
            if usable:
                checks.append(
                    {"name": "provider_configured", "status": "PASS", "detail": f"{len(usable)} usable provider(s)"}
                )
            else:
                checks.append(
                    {"name": "provider_configured", "status": "FAIL", "detail": "no enabled provider with a configured credential"}
                )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                {"name": "provider_configured", "status": "FAIL", "detail": f"provider query failed: {type(exc).__name__}"}
            )

        # 4. Every required story capability resolves in the current ruleset.
        missing: List[str] = []
        ruleset = self._route_locks.current_ruleset
        for capability in REQUIRED_STORY_CAPABILITIES:
            context = RuleMatchContext(
                scope_type="preflight",
                scope_id=f"preflight:{capability}",
                task_labels=expand_role_labels(capability),
                available_capabilities=expand_role_labels(capability),
            )
            if self._matcher.find_first_match(ruleset, context) is None:
                missing.append(capability)
        if missing:
            checks.append(
                {
                    "name": "routing_rules_resolve",
                    "status": "FAIL",
                    "detail": "no rule resolves: " + ", ".join(missing),
                }
            )
        else:
            checks.append(
                {"name": "routing_rules_resolve", "status": "PASS", "detail": f"{len(REQUIRED_STORY_CAPABILITIES)} roles resolve"}
            )

        # 5. Worker/story capability honestly reported by the probe.
        #    P0.4.1 (ban_ke_hoach_v1 §P0.4.1): "Worker capability available"
        #    is a REQUIRED pre-start check — a missing/unavailable worker
        #    blocks the start (START_BLOCKED) instead of warning. The durable
        #    queue still accepts submit-before-worker for RESUME of an existing
        #    run (the start endpoint only enforces FAIL on new runs).
        if self._capability is None:
            checks.append(
                {"name": "worker_capability_available", "status": "FAIL", "detail": "capability provider not composed"}
            )
        else:
            try:
                profile = await self._capability.get_capabilities()
                model_route = profile.by_name("model_route")
                story_engine = profile.by_name("story_engine")
                worker = profile.by_name("worker")
                problems: List[str] = []
                # P0.4.1 fail-closed: a missing capability is NOT available —
                # it blocks the start exactly like an unavailable one.
                if worker is None:
                    problems.append("worker=MISSING (capability absent from profile)")
                elif worker.status.value != "AVAILABLE":
                    problems.append(f"worker={worker.status.value} ({(worker.reason or '')[:80]})")
                if model_route is None:
                    problems.append("model_route=MISSING (capability absent from profile)")
                elif model_route.status.value != "AVAILABLE":
                    problems.append(
                        f"model_route={model_route.status.value} ({(model_route.reason or '')[:80]})"
                    )
                if story_engine is None:
                    problems.append("story_engine=MISSING (capability absent from profile)")
                elif story_engine.status.value != "AVAILABLE":
                    problems.append(
                        f"story_engine={story_engine.status.value} ({(story_engine.reason or '')[:80]})"
                    )
                if problems:
                    checks.append(
                        {"name": "worker_capability_available", "status": "FAIL", "detail": "; ".join(problems)}
                    )
                else:
                    checks.append({"name": "worker_capability_available", "status": "PASS", "detail": ""})
            except Exception as exc:  # noqa: BLE001
                checks.append(
                    {"name": "worker_capability_available", "status": "FAIL", "detail": f"probe failed: {type(exc).__name__}"}
                )

        # 6. Persistence: the episode's series must be readable.
        series_id = getattr(episode, "series_id", None) if episode is not None else None
        if series_id is None:
            checks.append(
                {"name": "persistence_available", "status": "FAIL", "detail": "episode unreadable"}
            )
        else:
            try:
                series = await self._series_repo.get(series_id)
                if series is None:
                    checks.append(
                        {"name": "persistence_available", "status": "FAIL", "detail": f"series {series_id} missing"}
                    )
                else:
                    checks.append({"name": "persistence_available", "status": "PASS", "detail": ""})
            except Exception as exc:  # noqa: BLE001
                checks.append(
                    {"name": "persistence_available", "status": "FAIL", "detail": f"series query failed: {type(exc).__name__}"}
                )

        ordered = [next(c for c in checks if c["name"] == name) for name in CHECK_NAMES]
        return {
            "episode_id": str(episode_id),
            "ready": all(c["status"] != "FAIL" for c in ordered),
            "checks": ordered,
        }


__all__ = ["StoryStartPreflight", "REQUIRED_STORY_CAPABILITIES", "CHECK_NAMES"]
