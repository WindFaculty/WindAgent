"""
WindAgent Production Engines (VP3D Stage B).

Engine adapters that compile the engine-neutral Production IR onto a concrete
3D engine (Blender first). Core/domain NEVER imports this package; only the
composition root wires concrete engines.
"""

from windagent_tools.production_engines.blender import (
    BlenderEngineAdapter,
    BlenderExecutionReceipt,
    BlenderInstallationCandidate,
    BlenderInstallationDetector,
    BlenderVersionValidationResult,
    BlenderVersionValidator,
    create_blender_engine_adapter,
)

__all__ = [
    "BlenderEngineAdapter",
    "BlenderExecutionReceipt",
    "BlenderInstallationCandidate",
    "BlenderInstallationDetector",
    "BlenderVersionValidationResult",
    "BlenderVersionValidator",
    "create_blender_engine_adapter",
]
