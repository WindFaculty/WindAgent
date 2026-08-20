"""Phase 7 API composition package.

The monolithic ``composition.py`` module was split into focused composer
modules.  This package keeps the compatibility export so existing imports
``from windagent_api.composition import ApplicationContainer`` continue to work.
"""

from windagent_api.composition.container import ApplicationContainer

__all__ = ["ApplicationContainer"]