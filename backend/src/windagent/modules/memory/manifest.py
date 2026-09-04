"""Module manifest for the Memory bounded context (Phase 14).

Discovered automatically by ``PackageModuleDiscovery`` — no bootstrap file
needs to import this module by name except for testing.
"""

from __future__ import annotations

from windagent.platform.modules import (
    CommandRegistration,
    JobRegistration,
    ModuleManifest,
    QueryRegistration,
)

from .api.routes import MODULE_ID, MODULE_VERSION, create_memory_router
from .application.commands import (
    DeleteMemory,
    EvictExpiredMemories,
    ForgetMemory,
    ForgetMemoryByPattern,
    SaveManyMemories,
    SaveMemory,
    SetMemoryTtl,
)
from .application.handlers import (
    DeleteMemoryHandler,
    EvictExpiredMemoriesHandler,
    ForgetMemoryByPatternHandler,
    ForgetMemoryHandler,
    GetMemoryByIdHandler,
    GetMemoryHandler,
    GetMemoryStatsHandler,
    ListEpisodicMemoriesHandler,
    ListMemoriesByProjectHandler,
    ListMemoriesByScopeHandler,
    ListMemoriesBySessionHandler,
    ListMemoriesByStatusHandler,
    ListMemoriesHandler,
    ListPoliciesHandler,
    ListProceduralMemoriesHandler,
    ListValidatedKnowledgeHandler,
    MemoryEvictExpiredJobHandler,
    SaveManyMemoriesHandler,
    SaveMemoryHandler,
    SearchMemoriesByTagHandler,
    SetMemoryTtlHandler,
)
from .application.queries import (
    GetMemory,
    GetMemoryById,
    GetMemoryStats,
    ListEpisodicMemories,
    ListMemories,
    ListMemoriesByProject,
    ListMemoriesByScope,
    ListMemoriesBySession,
    ListMemoriesByStatus,
    ListPolicies,
    ListProceduralMemories,
    ListValidatedKnowledge,
    SearchMemoriesByTag,
)
from .application.runtime import MemoryServices

MEMORY_JOB_TYPES = ("memory.evict_expired",)


def build_memory_manifest(services: MemoryServices | None = None) -> ModuleManifest:
    return ModuleManifest(
        id=MODULE_ID,
        version=MODULE_VERSION,
        commands=(
            CommandRegistration(SaveMemory, SaveMemoryHandler(services)),
            CommandRegistration(SaveManyMemories, SaveManyMemoriesHandler(services)),
            CommandRegistration(DeleteMemory, DeleteMemoryHandler(services)),
            CommandRegistration(ForgetMemory, ForgetMemoryHandler(services)),
            CommandRegistration(ForgetMemoryByPattern, ForgetMemoryByPatternHandler(services)),
            CommandRegistration(SetMemoryTtl, SetMemoryTtlHandler(services)),
            CommandRegistration(EvictExpiredMemories, EvictExpiredMemoriesHandler(services)),
        ),
        queries=(
            QueryRegistration(GetMemory, GetMemoryHandler(services)),
            QueryRegistration(GetMemoryById, GetMemoryByIdHandler(services)),
            QueryRegistration(ListMemories, ListMemoriesHandler(services)),
            QueryRegistration(ListMemoriesByScope, ListMemoriesByScopeHandler(services)),
            QueryRegistration(ListMemoriesByProject, ListMemoriesByProjectHandler(services)),
            QueryRegistration(ListMemoriesBySession, ListMemoriesBySessionHandler(services)),
            QueryRegistration(SearchMemoriesByTag, SearchMemoriesByTagHandler(services)),
            QueryRegistration(ListMemoriesByStatus, ListMemoriesByStatusHandler(services)),
            QueryRegistration(ListValidatedKnowledge, ListValidatedKnowledgeHandler(services)),
            QueryRegistration(ListPolicies, ListPoliciesHandler(services)),
            QueryRegistration(ListProceduralMemories, ListProceduralMemoriesHandler(services)),
            QueryRegistration(ListEpisodicMemories, ListEpisodicMemoriesHandler(services)),
            QueryRegistration(GetMemoryStats, GetMemoryStatsHandler(services)),
        ),
        jobs=(
            JobRegistration("memory.evict_expired", MemoryEvictExpiredJobHandler(services)),
        ),
        routers=(create_memory_router(),),
        capabilities=(
            "memory",
            "working_memory",
            "session_memory",
            "project_memory",
            "user_memory",
            "episodic_memory",
            "semantic_memory",
            "procedural_memory",
            "policy_memory",
            "retention",
            "learning_admission",
        ),
    )


manifest = build_memory_manifest()
