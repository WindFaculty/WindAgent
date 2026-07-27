"""
FastAPI REST & WebSocket entrypoint for Architecture V2
"""

from windagent_core.version import PRODUCT_VERSION

from windagent_api.main import app

__version__ = PRODUCT_VERSION
__all__ = ["app"]
