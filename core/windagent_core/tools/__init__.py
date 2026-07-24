"""
WindAgent Core Tools Package.
Re-exports canonical ToolInvocation and ToolResult models.
"""

from windagent_core.tools.models import ToolInvocation, ToolResult

__all__ = [
    "ToolInvocation",
    "ToolResult",
]
