"""Phase 8A Worker composition package.

The monolithic ``composition.py`` module was split into a typed settings module
(``settings.py``) and the container implementation (``container.py``).  This
package keeps the compatibility exports so existing imports
``from windagent_worker.composition import WorkerContainer`` continue to work
unchanged.
"""

from windagent_worker.composition.container import (
    CertificationPreflightError,
    WorkerContainer,
)
from windagent_worker.composition.settings import (
    WorkerRuntimeSettings,
    WorkerSettingsError,
)

__all__ = [
    "CertificationPreflightError",
    "WorkerContainer",
    "WorkerRuntimeSettings",
    "WorkerSettingsError",
]