"""Hermes integration configurations parsed from the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class HermesConfig:
    enabled: bool = False
    base_url: str = "http://127.0.0.1:8642"
    api_key: Optional[str] = None
    request_timeout_s: float = 30.0
    connect_timeout_s: float = 5.0
    auto_start: bool = True
    executable: str = "hermes"
    profile: Optional[str] = "default"
    max_concurrent_runs: int = 5

    def __repr__(self) -> str:
        key_repr = "None" if self.api_key is None else "[REDACTED]"
        return (
            f"HermesConfig(enabled={self.enabled}, base_url={self.base_url!r}, "
            f"api_key={key_repr}, request_timeout_s={self.request_timeout_s}, "
            f"connect_timeout_s={self.connect_timeout_s}, auto_start={self.auto_start}, "
            f"executable={self.executable!r}, profile={self.profile!r}, "
            f"max_concurrent_runs={self.max_concurrent_runs})"
        )

    def get_scrubbed_dict(self) -> dict:
        """Return a dictionary representation of the config with secrets masked."""
        import dataclasses
        d = dataclasses.asdict(self)
        if d.get("api_key") is not None:
            d["api_key"] = "[REDACTED]"
        return d


def load_hermes_config() -> HermesConfig:
    """Load configuration from environment variables."""
    import logging
    logger = logging.getLogger(__name__)

    enabled = os.environ.get("WINDAGENT_HERMES_ENABLED", "true").lower() in ("1", "true", "yes")
    base_url = os.environ.get("WINDAGENT_HERMES_BASE_URL", "http://127.0.0.1:8642").rstrip("/")
    api_key = os.environ.get("WINDAGENT_HERMES_API_KEY")
    auto_start = os.environ.get("WINDAGENT_HERMES_AUTO_START", "true").lower() in ("1", "true", "yes")
    executable = os.environ.get("WINDAGENT_HERMES_EXECUTABLE", "hermes")
    profile = os.environ.get("WINDAGENT_HERMES_PROFILE", "default")

    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        logger.warning("WINDAGENT_HERMES_BASE_URL is not a valid HTTP/HTTPS URL: %s", base_url)
    
    try:
        timeout = float(os.environ.get("WINDAGENT_HERMES_TIMEOUT_S", "30.0"))
    except ValueError:
        timeout = 30.0

    try:
        max_runs = int(os.environ.get("WINDAGENT_HERMES_MAX_CONCURRENT_RUNS", "5"))
    except ValueError:
        max_runs = 5

    return HermesConfig(
        enabled=enabled,
        base_url=base_url,
        api_key=api_key,
        request_timeout_s=timeout,
        auto_start=auto_start,
        executable=executable,
        profile=profile,
        max_concurrent_runs=max_runs,
    )
