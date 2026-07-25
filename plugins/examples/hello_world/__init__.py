"""
Hello World Plugin Example (Phase 20).
Demonstrates the WindAgent plugin contract with a minimal implementation.
"""

from typing import Any, Dict


class HelloWorldPlugin:
    """A minimal plugin demonstrating the WindAgent extension interface."""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.greeting = self.config.get("greeting", "Hello from WindAgent Plugin!")

    def execute(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Returns a greeting message."""
        name = (params or {}).get("name", "World")
        return {
            "message": f"{self.greeting}, {name}!",
            "plugin": "hello_world",
            "version": "1.0.0",
        }
