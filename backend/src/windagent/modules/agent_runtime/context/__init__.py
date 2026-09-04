"""Context assembly subpackage for Agent Runtime."""

from .budget import (
    TASK_TYPE_BUDGET_PROFILES,
    TokenBudgetManager,
    estimate_tokens,
)
from .builder import ContextBuilder
from .compaction import (
    PRESERVE_KEYWORDS,
    ContextCompactor,
)
from .pipeline import (
    STAGE_COMPACTION,
    STAGE_DEDUPLICATION,
    STAGE_FILE_RETRIEVAL,
    STAGE_MANIFEST,
    STAGE_PROJECT_MEMORY,
    STAGE_REPO_DISCOVERY,
    STAGE_SESSION_CONTEXT,
    STAGE_TOKEN_ALLOCATION,
    STAGE_TOOL_OUTPUTS,
    ContextPipeline,
    ContextPipelineConfig,
)
from .provenance import (
    ContextItem,
    ContextItemProvenance,
    ProvenanceManifest,
    ProvenanceManifestEntry,
    SensitivityLevel,
    SourceType,
)

__all__ = [
    "PRESERVE_KEYWORDS",
    "STAGE_COMPACTION",
    "STAGE_DEDUPLICATION",
    "STAGE_FILE_RETRIEVAL",
    "STAGE_MANIFEST",
    "STAGE_PROJECT_MEMORY",
    "STAGE_REPO_DISCOVERY",
    "STAGE_SESSION_CONTEXT",
    "STAGE_TOKEN_ALLOCATION",
    "STAGE_TOOL_OUTPUTS",
    "TASK_TYPE_BUDGET_PROFILES",
    "ContextBuilder",
    "ContextCompactor",
    "ContextItem",
    "ContextItemProvenance",
    "ContextPipeline",
    "ContextPipelineConfig",
    "ProvenanceManifest",
    "ProvenanceManifestEntry",
    "SensitivityLevel",
    "SourceType",
    "TokenBudgetManager",
    "estimate_tokens",
]
