"""Repository port protocols for WindAgent Core (Phase 3 — Dependency Inversion).

Application-layer packages (orchestration, memory, intelligence, workflows)
depend ONLY on these ports. Concrete SQL implementations live in storage and
are wired by composition roots (apps/*).
"""

from windagent_core.contracts.repositories.lease_repository import (
    LeaseRepositoryPort,
)
from windagent_core.contracts.repositories.runtime_execution_repository import (
    RuntimeExecutionRepositoryPort,
)
from windagent_core.contracts.repositories.cancellation_repository import (
    CancellationRepositoryPort,
)
from windagent_core.contracts.repositories.checkpoint_repository import (
    CheckpointRepositoryPort,
)
from windagent_core.contracts.repositories.event_store import EventStorePort
from windagent_core.contracts.repositories.task_repository import (
    TaskRunRepositoryPort,
)
from windagent_core.contracts.repositories.recovery_leader_repository import (
    RecoveryLeaderLeaseRepositoryPort,
)
from windagent_core.contracts.repositories.unit_of_work import (
    UnitOfWorkPort,
    UnitOfWorkFactory,
    SqlUnitOfWorkPort,
    StudioUnitOfWorkPort,
)
from windagent_core.contracts.repositories.multi_agent_repository import (
    MultiAgentRepositoryPort,
)
from windagent_core.contracts.repositories.memory_repository import (
    MemoryRecordRepositoryPort,
)
from windagent_core.contracts.repositories.routing_repository import (
    RouteLockRepositoryPort,
    RoutingAuditRepositoryPort,
    EndpointBindingRepositoryPort,
    CanonicalModelRepository,
    RouteAttemptRepository,
    RoutingUnitOfWork,
    CanonicalModelRepositoryPort,
    EndpointBindingRepository,
    ProviderRoutingAuditRepository,
    RouteAttemptRepositoryPort,
)
from windagent_core.contracts.repositories.harness_repository import (
    HarnessRepositoryProtocol,
)
from windagent_core.contracts.repositories.experiment_repository import (
    ExperimentRepositoryProtocol,
)
from windagent_core.contracts.repositories.promotion_repository import (
    PromotionRepositoryProtocol,
)
from windagent_core.contracts.repositories.skill_evolution_repository import (
    SkillEvolutionRepositoryProtocol,
)
from windagent_core.contracts.repositories.subagent_evolution_repository import (
    SubagentEvolutionRepositoryProtocol,
)
from windagent_core.contracts.repositories.organizational_learning_repository import (
    OrganizationalLearningRepositoryProtocol,
)

__all__ = [
    "LeaseRepositoryPort",
    "RuntimeExecutionRepositoryPort",
    "CancellationRepositoryPort",
    "CheckpointRepositoryPort",
    "EventStorePort",
    "TaskRunRepositoryPort",
    "RecoveryLeaderLeaseRepositoryPort",
    "UnitOfWorkPort",
    "UnitOfWorkFactory",
    "SqlUnitOfWorkPort",
    "StudioUnitOfWorkPort",
    "MultiAgentRepositoryPort",
    "MemoryRecordRepositoryPort",
    "RouteLockRepositoryPort",
    "RoutingAuditRepositoryPort",
    "EndpointBindingRepositoryPort",
    "CanonicalModelRepository",
    "RouteAttemptRepository",
    "RoutingUnitOfWork",
    "CanonicalModelRepositoryPort",
    "EndpointBindingRepository",
    "RouteLockRepository",
    "ProviderRoutingAuditRepository",
    "RouteAttemptRepositoryPort",
    "HarnessRepositoryProtocol",
    "ExperimentRepositoryProtocol",
    "PromotionRepositoryProtocol",
    "SkillEvolutionRepositoryProtocol",
    "SubagentEvolutionRepositoryProtocol",
    "OrganizationalLearningRepositoryProtocol",
]