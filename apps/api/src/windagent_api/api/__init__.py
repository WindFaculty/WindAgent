"""Canonical versioned API surface (``/api/v4``)."""

from .router import API_PREFIX, API_VERSION, build_api_router

__all__ = ["API_PREFIX", "API_VERSION", "build_api_router"]
