"""Backwards-compatible entrypoint; composition lives in ``bootstrap``.

Run locally with ``uvicorn windagent_api.app:app``; the module-level ``app``
is the default deployment application.
"""

from __future__ import annotations

from .bootstrap import create_app

__all__ = ["create_app", "app"]

app = create_app()
