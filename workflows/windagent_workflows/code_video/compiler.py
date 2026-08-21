"""Code Video Compiler compatibility shim.

Concrete implementation is available via __getattr__ in the package __init__.
This module is kept for backward compatibility of direct imports.
"""
from windagent_core.contracts.code_video.tools import CompilerPort

__all__ = ["CompilerPort"]
