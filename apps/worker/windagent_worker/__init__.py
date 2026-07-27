"""
Background Worker for WindAgent (Phase 18 Durable Worker).
"""

from windagent_core.version import PRODUCT_VERSION

from windagent_worker.lease import TaskLeaseManager, DurableTaskLeaseManager, TaskLease
from windagent_worker.runner import ProductionWorker, WorkerRunner

__all__ = ["TaskLeaseManager", "DurableTaskLeaseManager", "TaskLease", "ProductionWorker", "WorkerRunner"]
__version__ = PRODUCT_VERSION