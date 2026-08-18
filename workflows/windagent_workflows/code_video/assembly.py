"""
Code Video Workflow Step: Master Visual Assembly (Phase 10).

Executes the ASSEMBLE_MASTER pipeline step:
- Loads compiled CodeVideoPlan (Phase 4), TakesManifest (Phase 7/9), GraphicsManifest (Phase 8).
- Validates timeline continuity and zero-audio constraints.
- Emits master 1440p and delivery 1080p manifests and representations.
- Emits Voiceover Cue Sheet (cue_sheet.csv) for audio handoff.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from windagent_core.errors.exceptions import ValidationError
from windagent_workflows.code_video.contracts import CodeVideoPlan
from windagent_tools.code_video.capture.receipts import TakeReceipt
from windagent_tools.code_video.media.assembler import (
    CueSheet,
    MasterAssemblyResult,
    TakesManifest,
    TransitionPolicy,
    VideoAssemblyConfig,
    VisualMasterAssembler,
)


class AssembleMasterStepExecutor:
    """
    Step executor for ASSEMBLE_MASTER code video pipeline step.
    """

    def __init__(
        self,
        config: Optional[VideoAssemblyConfig] = None,
        transition_policy: Optional[TransitionPolicy] = None,
    ) -> None:
        self.config = config or VideoAssemblyConfig()
        self.transition_policy = transition_policy or TransitionPolicy()
        self.assembler = VisualMasterAssembler(
            config=self.config,
            transition_policy=self.transition_policy,
        )

    def execute(
        self,
        plan: CodeVideoPlan,
        takes: Sequence[TakeReceipt],
        graphics_manifest: Optional[Dict[str, Any]] = None,
        output_dir: Optional[Path] = None,
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
