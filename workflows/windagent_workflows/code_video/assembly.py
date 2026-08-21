"""
Code Video Workflow Step: Master Visual Assembly (Phase 10).

Executes the ASSEMBLE_MASTER pipeline step:
- Loads compiled CodeVideoPlan (Phase 4), TakesManifest (Phase 7/9), GraphicsManifest (Phase 8).
- Validates timeline continuity and zero-audio constraints.
- Emits master 1440p and delivery 1080p manifests and representations.
- Emits Voiceover Cue Sheet (cue_sheet.csv) for audio handoff.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from windagent_core.errors.exceptions import ValidationError
from windagent_core.contracts.code_video import CodeVideoPlan
from windagent_core.contracts.code_video.capture import TakeReceipt
from windagent_core.contracts.code_video.assembly import (
    MasterAssemblyResult,
    TransitionPolicy,
    VideoAssemblyConfig,
)
from windagent_core.contracts.code_video.tools import AssemblerPort


class AssembleMasterStepExecutor:
    """
    Step executor for ASSEMBLE_MASTER code video pipeline step.
    """

    def __init__(
        self,
        assembler: AssemblerPort,
        config: Optional[VideoAssemblyConfig] = None,
        transition_policy: Optional[TransitionPolicy] = None,
    ) -> None:
        self.assembler = assembler
        self.config = config or VideoAssemblyConfig()
        self.transition_policy = transition_policy or TransitionPolicy()

    def execute(
        self,
        plan: CodeVideoPlan,
        takes: Sequence[TakeReceipt],
        graphics_manifest: Optional[Dict[str, Any]] = None,
        output_dir: Optional[Any] = None,
    ) -> MasterAssemblyResult:
        """Execute assembly step and return certified MasterAssemblyResult."""
        if not plan or not plan.scenes:
            raise ValidationError("Cannot assemble master without a valid CodeVideoPlan.")
        if not takes:
            raise ValidationError("Cannot assemble master without take receipts.")

        return self.assembler.assemble_master(
            plan=plan,
            takes=takes,
            graphics_manifest=graphics_manifest,
            output_dir=output_dir,
        )


__all__ = [
    "AssembleMasterStepExecutor",
]
