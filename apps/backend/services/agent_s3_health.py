"""Agent-S3 health snapshot.

Tiny module that turns the runtime state (config + adapter last_error
+ import availability) into a single status dict the health endpoint
returns. Kept separate from ``agent_s3_config`` and ``agent_s3_adapter``
so the import graph stays shallow and the tests can poke at the three
modules independently.

Endpoints that consume this:

  - ``GET /health``                (basic summary)
  - ``GET /agent-s3/health``       (full snapshot -- new in this phase)

SECURITY (Phase 11 — SEC-002 closeout):

  The status payload is exposed over HTTP and is typically scraped by
  ops dashboards / mirrored into logs. Any field that resembles a
  secret MUST be scrubbed before the dict leaves this module.

  The scrub layer is intentionally **defence-in-depth** -- even though
  ``status_from_config()`` already excludes ``model_api_key`` /
  ``ground_api_key`` from the ``extra`` dict, any future change (e.g.
  someone calling ``extra.update(asdict(cfg))``) could reintroduce a
  leak. The ``scrub_secrets()`` helper guarantees that nothing matching
  a secret-shaped key name ever reaches the JSON response.
"""
from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any, Dict, Optional

from services.agent_s3_adapter import AgentS3Adapter
from services.agent_s3_config import (
    AgentS3Config,
    AgentS3ConfigStatus,
    external_repo_available,
    package_available,
    status_from_config,
)


# ---------- Secret scrub (SEC-002) ----------

# Lowercase substrings that indicate a secret-shaped key. Any dict key
# containing one of these substrings is replaced with a non-sensitive
# boolean placeholder before the response is serialised.
#
# Matched substrings (case-insensitive):
#   api_key / apikey
#   secret
#   token
#   password / passwd
#   bearer
#   authorization / auth_header
_SECRET_KEY_PATTERNS = (
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"\btoken\b", re.IGNORECASE),
    re.compile(r"passw(or)?d", re.IGNORECASE),
    re.compile(r"bearer", re.IGNORECASE),
    re.compile(r"auth(orization|_header)", re.IGNORECASE),
)

# Replacement placeholder key suffix. Original name "model_api_key" →
# "model_api_key_configured" (bool).
_CONFIGURED_SUFFIX = "_configured"


def _is_secret_key(name: str) -> bool:
    return any(p.search(name) for p in _SECRET_KEY_PATTERNS)


def _placeholder_key(name: str) -> str:
    """``model_api_key`` → ``model_api_key_configured``."""
    return f"{name}{_CONFIGURED_SUFFIX}"


def scrub_secrets(obj: Any) -> Any:
    """Recursively replace secret-shaped values with a boolean placeholder.

    Rules:
      - If ``obj`` is a dict, every key whose name matches a secret
        pattern is replaced. The new value is a boolean indicating
        whether the original was non-empty (configured).
      - All other keys are passed through unchanged. Nested dicts and
        lists are scrubbed recursively.
      - Anything that isn't a dict/list is returned as-is.

    This function never raises and never logs the original value.
    """
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for key, value in obj.items():
            if _is_secret_key(key):
                # Convert empty / None / 0-length strings to False; any
                # non-empty value to True. Never echo the value back.
                configured = bool(value) and value != ""
                out[_placeholder_key(key)] = configured
            else:
                out[key] = scrub_secrets(value)
        return out
    if isinstance(obj, list):
        return [scrub_secrets(item) for item in obj]
    return obj


# ---------- Builders ----------

def build_status(
    cfg: AgentS3Config,
    adapter: Optional[AgentS3Adapter],
) -> AgentS3ConfigStatus:
    """Snapshot of every healthcheck field.

    The adapter is consulted for its ``last_error`` so the endpoint
    surfaces real runtime errors, not just config-level issues.
    """
    last_error: Optional[str] = None
    if adapter is not None and adapter.last_error:
        last_error = adapter.last_error

    status = status_from_config(cfg, last_error=last_error)

    # Augment with a couple of adapter-runtime fields so debug is
    # one-stop in /agent-s3/health.
    extra = dict(status.extra)
    if adapter is not None:
        extra["adapter_initialised"] = adapter.is_available()
        extra["last_actions"] = adapter.last_actions
    else:
        extra["adapter_initialised"] = False
        extra["last_actions"] = []
    status = AgentS3ConfigStatus(
        mode=status.mode,
        enabled=status.enabled,
        source=status.source,
        package_available=status.package_available,
        external_repo_available=status.external_repo_available,
        config_missing=status.config_missing,
        last_error=status.last_error,
        extra=extra,
    )
    return status


def status_to_dict(status: AgentS3ConfigStatus) -> Dict[str, Any]:
    """Serialise the status dataclass for the JSON response.

    Defence-in-depth: every value that goes through this function is
    passed to ``scrub_secrets()`` before being returned. Even if a
    future code path accidentally adds ``model_api_key`` /
    ``ground_api_key`` / ``bearer_token`` / etc. to the response, the
    scrub layer will replace it with a boolean ``*_configured`` field.
    """
    d = asdict(status)
    # Make the shape predictable: top-level keys + nested "config".
    raw = {
        "mode": d["mode"],
        "enabled": d["enabled"],
        "source": d["source"],
        "package_available": d["package_available"],
        "external_repo_available": d["external_repo_available"],
        "config_missing": list(d["config_missing"]),
        "last_error": d["last_error"],
        "config": dict(d["extra"]),
    }
    return scrub_secrets(raw)


def health_summary(status: AgentS3ConfigStatus) -> Dict[str, Any]:
    """Cheap one-line summary used by ``GET /health``.

    Only the fields the desktop app cares about for its status pill.
    Defence-in-depth: scrub_secrets() applied even though this view
    only contains booleans + enums (no secrets are expected here).
    """
    return scrub_secrets({
        "agent_s3": {
            "mode": status.mode,
            "enabled": status.enabled,
            "package_available": status.package_available,
            "external_repo_available": status.external_repo_available,
            "config_missing_count": len(status.config_missing),
        }
    })


# ---------- Imports kept lazy so this module is cheap to import
#            when Agent-S3 is disabled. ----------

__all__ = [
    "build_status",
    "health_summary",
    "scrub_secrets",
    "status_to_dict",
]