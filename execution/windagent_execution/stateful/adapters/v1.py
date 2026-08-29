from __future__ import annotations
from typing import Any, Dict, Optional
from ..runtime import InMemoryStatefulRuntimeBase
class StatefulV1Adapter(InMemoryStatefulRuntimeBase):
    def __init__(self, *, backing_store: Optional[Dict[str, Any]] = None, sandbox=None, stream_manager=None, worktree_manager=None) -> None:
        super().__init__(runtime_kind="v1", backing_store=backing_store, sandbox=sandbox, stream_manager=stream_manager, worktree_manager=worktree_manager)
