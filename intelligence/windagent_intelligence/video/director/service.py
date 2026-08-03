"""
VideoDirectorService (Phase 8) — turns a VideoProductionPackage into a
provider-agnostic, validated CinematicPlan.

Responsibilities (plan 03 §7-§10):
- build a structured planning prompt from the package and call the
  `PreproductionModelPort` (LLM PROPOSES the plan);
- parse the structured `PlannerOutput` (never free-text);
- deterministically validate with `DirectorPlanValidator` (unknown references
  / missing coverage FAIL CLOSED — no partial plan ever);
- enforce the duration budget (overflow → issue; dialogue never silently cut);
- NEVER mutate the locked screenplay — blocking issues become
  `ScriptRevisionProposal`s (plan §9.3);
- every output plan is versioned and hashed (planner/prompt/duration policy
  versions + source package hash) so the same input yields the same hash.

The Director never calls a media-generation provider and never submits Flow.
"""

from __future__ import annotations

import json
from typing import Optional

from windagent_core.domain.video_production.director import compute_plan_hash
from windagent_core.domain.video_production.enums import ScreenplayStatus
from windagent_core.domain.video_production.package import VideoProductionPackage
from windagent_core.domain.video_production.shot import CinematicPlan
from windagent_core.domain.video_production.validation import (
    VideoProductionPackageValidator,
)

from windagent_intelligence.video.director.duration import DurationBudgetPolicy
from windagent_intelligence.video.director.models import (
    DirectorPlanReceipt,
    PlannerOutput,
)
from windagent_intelligence.video.director.prompts import (
    DIRECTOR_PLANNING_PROMPT_V1,
    _DIRECTOR_SCHEMA_HINT,
)
from windagent_intelligence.video.director.revision import (
    ScriptRevisionProposalFactory,
)
from windagent_intelligence.video.director.validator import DirectorPlanValidator
from windagent_intelligence.video.errors import (
    EmptyResponseError,
    ResponseParseError,
    ValidationFailureError,
)
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.ports import (
    ModelCompletionRequest,
    PreproductionModelPort,
)
from windagent_intelligence.video.prompts import PromptSpec


class VideoDirectorService:
    """Provider-agnostic director: package -> validated CinematicPlan."""

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        id_factory: Optional[StableIdFactory] = None,
        canonical_model: str = "canonical-default",
        prompt_spec: PromptSpec = DIRECTOR_PLANNING_PROMPT_V1,
        duration_policy: Optional[DurationBudgetPolicy] = None,
    ) -> None:
        self.model_port = model_port
        self.id_factory = id_factory or StableIdFactory()
        self.canonical_model = canonical_model
        self.prompt_spec = prompt_spec
        self.duration_policy = duration_policy or DurationBudgetPolicy()
        self.validator = DirectorPlanValidator(
            id_factory=self.id_factory,
            duration_policy=self.duration_policy,
        )
        self.revision_factory = ScriptRevisionProposalFactory(
            id_factory=self.id_factory,
        )

    # ------------------------------------------------------------------
    # Port contract (VideoDirectionPort)
    # ------------------------------------------------------------------
    async def create_cinematic_plan(
        self,
        package: VideoProductionPackage,
    ) -> CinematicPlan:
        """Create the provider-neutral cinematic plan required by the port.

        The public port deliberately returns only the immutable domain plan.
        Call :meth:`create_cinematic_plan_receipt` when a workflow also needs
        planning issues, revision proposals, and deterministic evidence.
        """
        return (await self.create_cinematic_plan_receipt(package)).plan

    async def create_cinematic_plan_receipt(
        self,
        package: VideoProductionPackage,
        *,
        require_locked: bool = True,
    ) -> DirectorPlanReceipt:
        """Create a validated cinematic-plan receipt from an immutable package.

        `require_locked=True` (default) rejects a package whose screenplay is
        not locked — planning must start from a frozen screenplay.
        """
        # 1. Package must itself be canonically valid.
        package_issues = VideoProductionPackageValidator.validate(package)
        if package_issues:
            raise ValidationFailureError(
                "Cannot plan from an invalid package.",
                details={
                    "issue_count": len(package_issues),
                    "first": [i.code for i in package_issues[:5]],
                },
            )
        if package.screenplay is None:
            raise ValidationFailureError(
                "Package has no screenplay; planning requires a screenplay.",
            )

        screenplay_locked = package.screenplay.status == ScreenplayStatus.LOCKED
        if require_locked and not screenplay_locked:
            raise ValidationFailureError(
                "Planning requires a LOCKED screenplay "
                f"(status={package.screenplay.status.value}).",
                details={"status": package.screenplay.status.value},
            )

        # 2. Ask the LLM to PROPOSE a structured plan (no free text).
        package_json = json.dumps(
            package.to_content_dict(), sort_keys=True, ensure_ascii=False
        )
        rendered = self.prompt_spec.render(
            package_json=package_json, schema_hint=_DIRECTOR_SCHEMA_HINT
        )
        result = await self.model_port.complete(
            ModelCompletionRequest(
                capability="cinematic_planning",
                system="You are the WindAgent director. Propose a structured plan only.",
                user=rendered,
                canonical_model=self.canonical_model,
                temperature=0.2,
                max_tokens=4000,
                prompt_spec=self.prompt_spec,
            )
        )
        if not result.content or not result.content.strip():
            raise EmptyResponseError("Director received an empty planner response.")

        # 3. Parse structured output; invalid output → typed failure.
        try:
            output = PlannerOutput.model_validate_json(result.content)
        except Exception as exc:
            raise ResponseParseError(
                "Director planner returned invalid structured output.",
                details={"error": str(exc)[:300]},
            ) from exc

        # 4. Deterministic validation + canonical plan (fail closed).
        validated = self.validator.validate(package, output)

        # 5. Deterministic plan hash (plan §24.5 semantics at plan level).
        plan_payload = json.loads(validated.plan.model_dump_json())
        source_package_hash = package.content_hash()
        plan_hash = compute_plan_hash(
            project_id=package.project_id,
            revision_id=package.revision_id,
            plan_payload=plan_payload,
            planner_version=output.planner_version,
            prompt_version=self.prompt_spec.version,
            prompt_hash=self.prompt_spec.content_hash,
            source_package_hash=source_package_hash,
            duration_policy_version=self.duration_policy.version,
        )

        # 6. Blocking issues → proposals (never mutate the screenplay).
        proposals = self.revision_factory.build(
            package,
            validated.issues,
            source_plan_hash=plan_hash,
        )

        # 7. Record versions/hash on the plan (traceable to source revision).
        plan = validated.plan.model_copy(
            update={
                "metadata": {
                    **validated.plan.metadata,
                    "planner_version": output.planner_version,
                    "prompt_version": self.prompt_spec.version,
                    "prompt_hash": self.prompt_spec.content_hash,
                    "duration_policy_version": self.duration_policy.version,
                    "source_package_hash": source_package_hash,
                    "plan_hash": plan_hash,
                    "screenplay_locked": screenplay_locked,
                    "scene_objectives": [
                        o.model_dump(mode="json") for o in validated.scene_objectives
                    ],
                }
            }
        )

        return DirectorPlanReceipt(
            plan=plan,
            plan_hash=plan_hash,
            source_package_hash=source_package_hash,
            scene_objectives=validated.scene_objectives,
            issues=validated.issues,
            proposals=proposals,
            planner_version=output.planner_version,
            prompt_version=self.prompt_spec.version,
            prompt_hash=self.prompt_spec.content_hash,
            duration_policy_version=self.duration_policy.version,
            screenplay_locked=screenplay_locked,
        )

    async def lock_shot_plan(self, plan: CinematicPlan) -> CinematicPlan:
        """Return a LOCKED copy of a shot plan (never mutates the input)."""
        return plan.model_copy(
            update={"locked": True, "metadata": {**plan.metadata, "locked": True}}
        )


__all__ = ["VideoDirectorService"]
