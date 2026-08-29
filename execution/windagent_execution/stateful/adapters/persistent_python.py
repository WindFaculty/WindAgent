
from ..runtime import InMemoryStatefulRuntimeBase
class PersistentPythonRuntime(InMemoryStatefulRuntimeBase):
    def __init__(self, *, backing_store=None, sandbox=None, stream_manager=None, worktree_manager=None, use_ipython: bool=False):
        super().__init__(runtime_kind="persistent_python", backing_store=backing_store, sandbox=sandbox, stream_manager=stream_manager, worktree_manager=worktree_manager)
        self.use_ipython=use_ipython
        if use_ipython:
            try:
                import IPython  # noqa: F401
            except ImportError as ex:
                raise ImportError("PersistentPythonRuntime with use_ipython=True requires ipython") from ex
