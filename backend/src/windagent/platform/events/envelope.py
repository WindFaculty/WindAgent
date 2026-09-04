"""The canonical event envelope (re-exported from the kernel).

The kernel owns the transport-neutral envelope definition (plan section 10);
platform events add persistence, dispatch and delivery around it.
"""

from windagent.kernel.events import EventEnvelope

__all__ = ["EventEnvelope"]
