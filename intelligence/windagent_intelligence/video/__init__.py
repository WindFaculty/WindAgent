"""
WindAgent Video Pre-production Kernel (Phase 6).

Canonical, provider-neutral reimplementation of the pre-production
capabilities that were characterized in Phase 5
(VP5_VIDEOCLAW_BEHAVIOR_CHARACTERIZED). Nine vertical slices:

1. ideation.brief_expander      — creative brief / idea expansion
2. ideation.outliner            — story outline
3. screenplay.writer            — multi-scene screenplay
4. screenplay.narration         — dialogue and narration
5. entity_extraction.extractor  — character/location/prop extraction
6. style_design.designer        — style bible
7. continuation.service         — plot continuation and revision proposal
8. asset_prompts.builder        — asset prompt specification
9. assembly.assembler           — assemble VideoProductionPackage v1

Design rules (plan 02 §14-18, §16):
- Zero runtime import from third_party/videoclaw/upstream.
- Provider-neutral: every model-backed capability goes through the
  `PreproductionModelPort` protocol; prompts are versioned and hashed
  (`PromptSpec`); model ID / temperature / token limits are config.
- Provider responses are parsed and validated BEFORE entering the domain;
  broken/empty responses raise typed kernel errors (fixes DEF-001, DEF-002,
  DEF-005 from artifacts/video_production/phase_05/defect_inventory.json).
- Identity is bound via stable canonical IDs, never merged on display name
  (fixes DEF-003). Version listing is deterministic (fixes DEF-004).
- Capabilities never write project/session DB, never lock a screenplay,
  never approve assets, and never call video generation.
"""

from windagent_intelligence.video.ports import (
    ModelCompletionRequest,
    ModelCompletionResult,
    PreproductionModelPort,
)
from windagent_intelligence.video.prompts import PromptSpec
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.errors import (
    VideoKernelError,
    ResponseParseError,
    EmptyResponseError,
    MissingModelConfigError,
    ValidationFailureError,
    CancellationError,
)

# Capability services
from windagent_intelligence.video.ideation.brief_expander import CreativeBriefExpander
from windagent_intelligence.video.ideation.outliner import StoryOutliner
from windagent_intelligence.video.screenplay.writer import ScreenplayWriter
from windagent_intelligence.video.screenplay.narration import DialogueNarrator
from windagent_intelligence.video.entity_extraction.extractor import EntityExtractor
from windagent_intelligence.video.style_design.designer import StyleDesigner
from windagent_intelligence.video.continuation.service import ContinuationService
from windagent_intelligence.video.asset_prompts.builder import AssetPromptSpecBuilder
from windagent_intelligence.video.assembly.assembler import (
    PackageAssembler,
    PackageAssemblyReceipt,
)

__all__ = [
    # ports
    "ModelCompletionRequest",
    "ModelCompletionResult",
    "PreproductionModelPort",
    # prompts & ids
    "PromptSpec",
    "StableIdFactory",
    # errors
    "VideoKernelError",
    "ResponseParseError",
    "EmptyResponseError",
    "MissingModelConfigError",
    "ValidationFailureError",
    "CancellationError",
    # capability services
    "CreativeBriefExpander",
    "StoryOutliner",
    "ScreenplayWriter",
    "DialogueNarrator",
    "EntityExtractor",
    "StyleDesigner",
    "ContinuationService",
    "AssetPromptSpecBuilder",
    "PackageAssembler",
    "PackageAssemblyReceipt",
]
