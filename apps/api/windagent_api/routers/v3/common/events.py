"""
Canonical EventEnvelope Schema for Realtime & SSE Event Streaming in V3.
Re-exports the core EventEnvelope implementation to maintain strict single authority.
"""

from windagent_core.events.envelope import EventEnvelope

__all__ = ["EventEnvelope"]
