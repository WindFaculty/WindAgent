"""
Canonical Bootstrap Package for WindAgent V2 API (Phase 16).
Initializes environment settings, logging, and feature flags.
"""

from __future__ import annotations
import logging
import os
from typing import Dict, Any

from windagent_api.bootstrap.feature_flags import FeatureFlagsManager

logger = logging.getLogger("windagent.api.bootstrap")


class BootstrapConfig:
    def __init__(self):
        self.env = os.getenv("WINDAGENT_ENV", "development")
        self.db_url = os.getenv("WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///windagent.db")
        self.host = os.getenv("WINDAGENT_HOST", "0.0.0.0")
        self.port = int(os.getenv("WINDAGENT_PORT", "8000"))
        self.feature_flags = FeatureFlagsManager()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "env": self.env,
            "db_url": self.db_url,
            "host": self.host,
            "port": self.port,
            "v2_enabled": self.feature_flags.is_v2_enabled(),
        }


def initialize_bootstrap() -> BootstrapConfig:
    config = BootstrapConfig()
    logging.basicConfig(
        level=logging.INFO if config.env == "production" else logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # Mute noisy third-party loggers in development
    for noisy_logger in ("aiosqlite", "sqlalchemy.engine", "asyncio", "httpx", "httpcore"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    logger.info(f"Bootstrap initialized in '{config.env}' mode.")
    return config
