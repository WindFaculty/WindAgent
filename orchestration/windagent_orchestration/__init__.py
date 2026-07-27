"""
Task manager, workflow engine, state machine, scheduler, dispatcher, retry, recovery
"""

from windagent_core.version import PRODUCT_VERSION

__version__ = PRODUCT_VERSION
from windagent_orchestration.composition import OrchestrationV2Container

__all__ = ["OrchestrationV2Container"]