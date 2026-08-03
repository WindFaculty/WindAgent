"""
PromptCompiler (Phase 11) — turns each bound ShotSpecification into a
versioned, sanitized, provider-safe `GenerationRequest` (plan 03 §23-§24).

Pipeline per shot:

    ShotSpecification (+ bindings + continuity ledger)
        -> 12 canonical prompt blocks (plan §24.2)
        -> sanitize (plan §24.4 trust boundary)
        -> CompiledPrompt + prompt_hash
        -> FlowGenerationSpecification (no selector/DOM state)
        -> mode-specific required-input validation (plan §24.3)
        -> GenerationRequest + request_hash (plan §24.5)

FAIL CLOSED: any blocking issue (missing required block, mode missing input,
oversized prompt, forbidden content, unknown field, injection suspect, or a
broken reference binding) raises `ValidationFailureError` — a partial request
set is never published. The compiler is fully deterministic and never calls a
provider.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from windagent_core.domain.video_production.enums import (
    IssueSeverity,
    PromptBlockType,
    PromptCompilerIssueCode,
)
from windagent_core.domain.video_production.generation_job import GenerationRequest
from windagent_core.domain.video_production.ids import (
    CompiledPromptId,
    FlowGenerationSpecificationId,
    GenerationRequestId,
)
from windagent_core.domain.video_production.package import VideoProductionPackage
from windagent_core.domain.video_production.prompt_compiler import (
    CompiledPrompt,
    FlowGenerationSpecification,
    PromptCompilerIssue,
    PromptSecurityFinding,
    compute_prompt_hash,
    compute_request_hash,
)
from windagent_core.domain.video_production.shot_graph import ShotSpecification
from windagent_core.domain.video_production.validation import (
    VideoProductionPackageValidator,
)

from windagent_intelligence.video.continuity.models import ContinuityLedgerReceipt
from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.prompt_compiler.blocks import PromptBlockBuilder
from windagent_intelligence.video.prompt_compiler.modes import (
    MODE_REQUIRED_INPUTS,
    ModeCompiler,
)
from windagent_intelligence.video.prompt_compiler.models import CompiledRequestReceipt
from windagent_intelligence.video.prompt_compiler.security import PromptSanitizer
from windagent_intelligence.video.reference_selector.models import (
    ReferenceBindingPlanReceipt,
)
from windagent_intelligence.video.shot_planner.models import ShotGraphReceipt

COMPILER_VERSION = "1.0.0"

_REQUIRED_BLOCK_NAMES = (
    "PROJECT_STYLE",
    "SHOT_COMPOSITION",
    "ACTION",
    "CAMERA",
    "DURATION",
    "NEGATIVE_CONSTRAINTS",
)

# Sanitizer finding kind -> compiler issue code (plan §24.4).
_FINDING_ISSUE_CODE = {
    "local_path": PromptCompilerIssueCode.FORBIDDEN_CONTENT,
    "secret_marker": PromptCompilerIssueCode.FORBIDDEN_CONTENT,
    "injection_suspect": PromptCompilerIssueCode.INJECTION_SUSPECT,
    "oversized": PromptCompilerIssueCode.PROMPT_OVERSIZED,
}


class PromptCompiler:
    """Deterministic, fail-closed prompt compiler over a bound shot graph."""

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        block_builder: Optional[PromptBlockBuilder] = None,
        sanitizer: Optional[PromptSanitizer] = None,
        mode_compiler: Optional[ModeCompiler] = None,
        compiler_version: str = COMPILER_VERSION,
        allow_overflow: bool = False,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.block_builder = block_builder or PromptBlockBuilder(
            id_factory=self.id_factory,
        )
        self.sanitizer = sanitizer or PromptSanitizer(
            id_factory=self.id_factory,
        )
        self.mode_compiler = mode_compiler or ModeCompiler(
            id_factory=self.id_factory,
        )
        self.compiler_version = compiler_version
        self.prompt_template_version = self.block_builder.template_version
        # `allow_overflow` is a test/verifier escape hatch ONLY; production
        # compilation keeps the length gate ON (blocking, plan §29).
        self.allow_overflow = allow_overflow

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def compile_all(
        self,
        package: VideoProductionPackage,
        graph_receipt: ShotGraphReceipt,
        binding_receipt: ReferenceBindingPlanReceipt,
        *,
        continuity_receipt: Optional[ContinuityLedgerReceipt] = None,
        require_locked: bool = True,
    ) -> CompiledRequestReceipt:
        """Compile one GenerationRequest per shot.

        Raises `ValidationFailureError` on an invalid package, an empty graph,
        a missing plan hash, blocking binding defects, or any blocking compile
        issue (fail closed — no partial request set is ever published).
        """
        package_issues = VideoProductionPackageValidator.validate(package)
        if package_issues:
            raise ValidationFailureError(
                "Cannot compile prompts from an invalid package.",
                details={
                    "issue_count": len(package_issues),
                    "first": [i.code for i in package_issues[:5]],
                },
            )
        graph = graph_receipt.graph
        if not graph.shots:
            raise ValidationFailureError(
                "Prompt compilation requires a shot graph with at least one shot.",
            )
        if require_locked and not graph_receipt.source_plan_hash:
            raise ValidationFailureError(
                "Prompt compilation requires a traceable source plan hash.",
                details={"source_plan_hash": graph_receipt.source_plan_hash},
            )

        blocking_bindings = binding_receipt.blocking_issues
        if blocking_bindings:
            raise ValidationFailureError(
                "Prompt compilation blocked: the reference binding plan has "
                "blocking defects.",
                details={
                    "blocking_issue_count": len(blocking_bindings),
                    "first": [i.code.value for i in blocking_bindings[:5]],
                },
            )

        specs_by_shot = {str(s.shot_id): s for s in graph_receipt.specifications}
        bindings_by_shot: Dict[str, List] = {}
        for binding in binding_receipt.plan.bindings:
            bindings_by_shot.setdefault(str(binding.shot_id), []).append(binding)

        requests: List[GenerationRequest] = []
        specifications: List[FlowGenerationSpecification] = []
        issues: List[PromptCompilerIssue] = []
        findings: List[PromptSecurityFinding] = []

        for shot in sorted(graph.shots, key=lambda s: (str(s.scene_id), s.order)):
            spec = specs_by_shot.get(str(shot.shot_id))
            if spec is None:
                issues.append(
                    self._issue(
                        PromptCompilerIssueCode.MISSING_REQUIRED_BLOCK,
                        f"Shot {shot.shot_id} has no shot specification; cannot compile.",
                        shot_id=shot.shot_id,
                    )
                )
                continue
            shot_bindings = bindings_by_shot.get(str(shot.shot_id), [])
            shot_issues, shot_findings, request, spec_obj = self._compile_shot(
                package=package,
                spec=spec,
                bindings=shot_bindings,
                continuity_receipt=continuity_receipt,
                graph_receipt=graph_receipt,
            )
            issues.extend(shot_issues)
            findings.extend(shot_findings)
            if request is not None and spec_obj is not None:
                requests.append(request)
                specifications.append(spec_obj)

        receipt = CompiledRequestReceipt(
            requests=requests,
            specifications=specifications,
            issues=issues,
            security_findings=findings,
            compiler_version=self.compiler_version,
            prompt_template_version=self.prompt_template_version,
        )

        # FAIL CLOSED: never publish a partial request set.
        blocking = receipt.blocking_issues
        if blocking:
            raise ValidationFailureError(
                "Prompt compilation failed; no GenerationRequest set is published.",
                details={
                    "blocking_issue_count": len(blocking),
                    "first": [i.code.value for i in blocking[:5]],
                },
            )
        return receipt

    # ------------------------------------------------------------------
    # Per-shot compilation
    # ------------------------------------------------------------------
    def _compile_shot(
        self,
        *,
        package: VideoProductionPackage,
        spec: ShotSpecification,
        bindings,
        continuity_receipt: Optional[ContinuityLedgerReceipt],
        graph_receipt: ShotGraphReceipt,
    ):
        shot_id = spec.shot_id
        issues: List[PromptCompilerIssue] = []
        findings: List[PromptSecurityFinding] = []

        # 1. Canonical prompt blocks (plan §24.2).
        blocks = self.block_builder.build_blocks(
            package=package,
            spec=spec,
            bindings=bindings,
            continuity=continuity_receipt,
        )
        # NOTE: required blocks are always emitted (even when content is empty
        # for a fixture without a style bible); the MISSING_REQUIRED_BLOCK
        # check below is a defensive invariant for externally-built specs.
        present_required = {b.block_type for b in blocks if b.required}
        for name in _REQUIRED_BLOCK_NAMES:
            if PromptBlockType(name) not in present_required:
                issues.append(
                    self._issue(
                        PromptCompilerIssueCode.MISSING_REQUIRED_BLOCK,
                        f"Required prompt block {name} is missing for shot {shot_id}.",
                        shot_id=shot_id,
                    )
                )

        # 2. Sanitize each block (plan §24.4 trust boundary).
        sanitized_blocks = []
        for block in blocks:
            result = self.sanitizer.sanitize(
                block.content,
                field=block.block_type.value,
                allow_overflow=self.allow_overflow,
            )
            for kind, finding_id in zip(result.kinds, result.finding_ids):
                findings.append(
                    PromptSecurityFinding(
                        finding_id=finding_id,
                        kind=kind,
                        severity=(
                            IssueSeverity.BLOCKING
                            if kind in result.blocked_kinds
                            else IssueSeverity.WARNING
                        ),
                        message=f"Sanitizer flagged {kind} in "
                        f"{block.block_type.value}.",
                        field=block.block_type.value,
                        redacted=True,
                    )
                )
            for kind in result.blocked_kinds:
                issues.append(
                    self._issue(
                        _FINDING_ISSUE_CODE.get(
                            kind, PromptCompilerIssueCode.FORBIDDEN_CONTENT
                        ),
                        f"Prompt block {block.block_type.value} for shot "
                        f"{shot_id} was blocked by sanitizer rule {kind}.",
                        shot_id=shot_id,
                    )
                )
            sanitized_blocks.append(
                block.model_copy(update={"content": result.text})
            )

        # 3. Assemble CompiledPrompt + prompt_hash.
        text = "\n\n".join(
            f"## {b.block_type.value}\n{b.content}" for b in sanitized_blocks
        )
        prompt_hash = compute_prompt_hash(
            blocks_payload=[b.to_dict() for b in sanitized_blocks],
            template_version=self.prompt_template_version,
        )
        prompt = CompiledPrompt(
            prompt_id=CompiledPromptId(
                self.id_factory.compiled_prompt_id(shot_id)
            ),
            shot_id=shot_id,
            blocks=sanitized_blocks,
            text=text,
            template_version=self.prompt_template_version,
            prompt_hash=prompt_hash,
            total_chars=len(text),
        )

        # 4. Reference hashes from the bound assets.
        reference_hashes = sorted(
            {b.asset_hash for b in bindings if len(b.asset_hash) == 64}
        )
        binding_ids = [str(b.binding_id) for b in bindings]

        # 5. Mode-specific required inputs (plan §24.3).
        mode = spec.generation_mode.preferred_mode
        mode_issues = self.mode_compiler.validate(
            mode=mode,
            shot_id=shot_id,
            bindings=bindings,
            reference_binding_ids=binding_ids,
            first_frame=_has_role(bindings, "FIRST_FRAME"),
            last_frame=_has_role(bindings, "LAST_FRAME"),
            predecessor_clip=_predecessor_clip_available(graph_receipt, shot_id),
            source_clip=_source_clip_available(graph_receipt, shot_id),
            ingredient=_has_role(bindings, "INGREDIENT"),
        )
        issues.extend(mode_issues)

        # 6. Generation parameters + capability constraints.
        parameters = {
            "duration_seconds": spec.duration_seconds,
            "frame_rate": spec.frame_rate,
            "aspect_ratio": spec.aspect_ratio,
            "preferred_mode": mode.value,
            "acceptable_fallback_modes": [
                m.value for m in spec.generation_mode.acceptable_fallback_modes
            ],
            "retry_policy": {
                "max_attempts": spec.retry_policy.max_attempts,
                "retry_boundary": spec.retry_policy.retry_boundary,
            },
        }
        capability_constraints = {
            "required_inputs": MODE_REQUIRED_INPUTS.get(mode, "none"),
        }

        # 7. FlowGenerationSpecification — NO selectors / DOM state.
        spec_obj = FlowGenerationSpecification(
            spec_id=FlowGenerationSpecificationId(
                self.id_factory.flow_spec_id(shot_id)
            ),
            shot_id=shot_id,
            generation_mode=mode,
            prompt=prompt,
            reference_binding_ids=binding_ids,
            reference_hashes=reference_hashes,
            required_inputs=[MODE_REQUIRED_INPUTS.get(mode, "none")],
            parameters=parameters,
            model_capability_constraints=capability_constraints,
        )

        # 8. Deterministic request hash (plan §24.5).
        request_hash = compute_request_hash(
            project_id=package.project_id,
            revision_id=package.revision_id,
            shot_id=shot_id,
            generation_mode=mode,
            compiler_version=self.compiler_version,
            prompt_template_version=self.prompt_template_version,
            prompt_hash=prompt_hash,
            reference_hashes=reference_hashes,
            parameters=parameters,
            model_capability_constraints=capability_constraints,
        )
        request = GenerationRequest(
            request_id=GenerationRequestId(
                self.id_factory.generation_request_id(
                    str(package.project_id),
                    str(package.revision_id),
                    str(shot_id),
                )
            ),
            project_id=package.project_id,
            revision_id=package.revision_id,
            shot_id=shot_id,
            generation_mode=mode,
            provider="",  # chosen at runtime; the Director never calls providers
            prompt_version=self.prompt_template_version,
            prompt_hash=prompt_hash,
            reference_hashes=reference_hashes,
            request_hash=request_hash,
            parameters=parameters,
        )
        return issues, findings, request, spec_obj

    def _issue(
        self,
        code: PromptCompilerIssueCode,
        message: str,
        *,
        shot_id,
    ) -> PromptCompilerIssue:
        seed = f"{code.value}:{shot_id}"
        return PromptCompilerIssue(
            issue_id=self.id_factory.prompt_issue_id(seed),
            code=code,
            severity=IssueSeverity.BLOCKING,
            message=message,
            blocking=True,
            shot_id=shot_id,
            details={},
        )


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------
def _has_role(bindings, role_value: str) -> bool:
    from windagent_core.domain.video_production.enums import ReferenceBindingRole

    target = ReferenceBindingRole(role_value)
    return any(b.role == target for b in bindings)


def _predecessor_clip_available(graph_receipt: ShotGraphReceipt, shot_id) -> bool:
    """True when a blocking edge into the shot requires a clip/frame artifact."""
    for dep in graph_receipt.graph.dependencies:
        if str(dep.to_shot_id) != str(shot_id):
            continue
        if dep.blocking and dep.required_artifact_type.value in (
            "TAIL_FRAME",
            "FULL_CLIP",
            "LAST_FRAME",
        ):
            return True
    return False


def _source_clip_available(graph_receipt: ShotGraphReceipt, shot_id) -> bool:
    """VIDEO_TO_VIDEO transforms a predecessor clip (any incoming clip edge)."""
    for dep in graph_receipt.graph.dependencies:
        if str(dep.to_shot_id) != str(shot_id):
            continue
        if dep.required_artifact_type.value in ("FULL_CLIP", "TAIL_FRAME"):
            return True
    return False


__all__ = ["PromptCompiler", "COMPILER_VERSION"]
