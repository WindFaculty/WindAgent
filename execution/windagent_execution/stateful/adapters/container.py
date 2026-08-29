
from ..runtime import InMemoryStatefulRuntimeBase
from ..types import StatefulExecuteResult
class ContainerRuntime(InMemoryStatefulRuntimeBase):
    def __init__(self, *, backing_store=None, sandbox=None, stream_manager=None, worktree_manager=None, image="python:3.11-slim"):
        super().__init__(runtime_kind="container", backing_store=backing_store, sandbox=sandbox, stream_manager=stream_manager, worktree_manager=worktree_manager)
        self.image=image
    async def _do_execute(self, session_id, request, started):
        try:
            import docker  # noqa: F401
        except ImportError:
            base=await super()._do_execute(session_id, request, started)
            out=dict(base.output or {})
            out["_container_fallback"]=True
            out["_container_image"]=self.image
            return StatefulExecuteResult(session_id=base.session_id, execution_id=base.execution_id, status=base.status, output=out, error=base.error, started_at=base.started_at, finished_at=base.finished_at)
        return await super()._do_execute(session_id, request, started)
