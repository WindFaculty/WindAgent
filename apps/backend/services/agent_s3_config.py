"""Agent-S3 configuration loader.

Single source of truth for every ``WINDAGENT_AGENT_S3_*`` env var.

Design rules (from `docs/agent_s3_integration.md`):

  - Agent-S3 is **optional**. The backend starts fine without it.
  - All env reads happen here -- callers (``agent_s3_adapter``,
    ``agent_s3_health``, ``main.py``) consume the dataclass below.
  - We never raise on missing config; we surface a status object that
    ``/health`` and ``/agent-s3/health`` return. The only exception is
    ``validate_or_raise()``, used by tests + the setup script.

Env vars recognised (with safe defaults):

  WINDAGENT_AGENT_S3_ENABLED         0|1            default 0
  WINDAGENT_AGENT_S3_SOURCE          package|external  default package
  WINDAGENT_AGENT_S3_EXTERNAL_PATH   <path>          default external/Agent-S
  WINDAGENT_AGENT_S3_PROVIDER        <str>           default "openai"
  WINDAGENT_AGENT_S3_MODEL           <str>           default "gpt-5-2025-08-07"
  WINDAGENT_AGENT_S3_MODEL_URL       <url>           default ""
  WINDAGENT_AGENT_S3_MODEL_API_KEY   <str>           default ""
  WINDAGENT_AGENT_S3_GROUND_PROVIDER <str>           default ""
  WINDAGENT_AGENT_S3_GROUND_MODEL    <str>           default ""
  WINDAGENT_AGENT_S3_GROUND_URL      <url>           default ""
  WINDAGENT_AGENT_S3_GROUND_API_KEY  <str>           default ""
  WINDAGENT_AGENT_S3_ENABLE_LOCAL_ENV 0|1            default 0  (NEVER 1 in WindAgent)

The ``ENABLE_LOCAL_ENV`` flag corresponds to Agent-S3's local-coding
sandbox which executes arbitrary Python + bash. WindAgent always
overrides it to ``0`` regardless of env to keep the safety guarantee
that no raw action code is ever exec'd by the adapter. See
``agent_s3_action_translator.py`` for the enforcement path.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


# ---------- Types ----------

AgentS3Source = Literal["package", "external"]
AgentS3Mode = Literal["disabled", "package", "external", "misconfigured"]


# ---------- Config dataclass ----------

@dataclass(frozen=True)
class AgentS3Config:
    """Resolved configuration for the Agent-S3 integration.

    Immutable so it can be safely passed across threads / tasks.
    Use ``replace`` (dataclasses.replace) to derive a new value.
    """

    enabled: bool
    source: AgentS3Source
    external_path: Path

    # Worker LLM (the planner that decides the next action).
    provider: str
    model: str
    model_url: str
    model_api_key: str

    # Grounding LLM (the model that finds screen coordinates).
    ground_provider: str
    ground_model: str
    ground_url: str
    ground_api_key: str

    # Safety: WindAgent always forces this to False. Exposed so the
    # adapter can sanity-check its own state.
    enable_local_env: bool

    # Resolved external checkout path (only set when source=="external"
    # AND the directory contains ``gui_agents/``). ``None`` means the
    # checkout is missing.
    external_checkout_root: Optional[Path] = None

    # Free-form notes -- surfaced in /health for debug.
    notes: List[str] = field(default_factory=list)


# ---------- Status dataclass (for /health) ----------

@dataclass(frozen=True)
class AgentS3ConfigStatus:
    """Status snapshot returned by ``agent_s3_health.status()`` and
    the ``GET /agent-s3/health`` endpoint."""

    mode: AgentS3Mode
    enabled: bool
    source: str
    package_available: bool
    external_repo_available: bool
    config_missing: List[str]
    last_error: Optional[str]
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------- Helpers ----------

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_str(name: str, default: str = "") -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip()


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


# ---------- Detection ----------

def package_available() -> bool:
    """True iff the ``gui_agents`` package is importable.

    Imports are kept inside the function so the import error stays
    isolated and never breaks the rest of the backend.
    """
    try:
        import gui_agents  # noqa: F401
        return True
    except Exception:
        return False


def external_repo_available(path) -> bool:
    """True iff ``path`` contains the Agent-S Python package directory.

    Accepts both ``str`` and ``pathlib.Path`` so callers don't have to
    coerce. Looks for either ``gui_agents/`` (post-v0.2 layout) or the
    older ``agent_s/`` directory; either is sufficient because
    Agent-S has shipped both layouts across versions.
    """
    if path is None:
        return False
    p = path if isinstance(path, Path) else Path(path)
    if not p.exists() or not p.is_dir():
        return False
    return (p / "gui_agents").is_dir() or (p / "agent_s").is_dir()


def resolve_external_path(raw: str) -> Path:
    """Resolve ``WINDAGENT_AGENT_S3_EXTERNAL_PATH`` to an absolute Path.

    Accepts both repo-relative (``external/Agent-S``) and absolute
    paths. Repo-relative paths are anchored on the WindAgent repo
    root (the directory that contains both ``apps/backend/`` and
    ``external/``) -- we walk up from ``__file__`` until we find a
    directory containing ``apps/backend``, so this works regardless
    of the process cwd. Never raises.
    """
    if not raw:
        return _default_external_path()
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p

    # Anchor on the repo root, not cwd. The backend is launched with
    # cwd=apps/backend (see scripts/dev_backend.ps1) so cwd-relative
    # resolution would point at the wrong place.
    repo_root = _find_repo_root()
    return (repo_root / p).resolve()


def _default_external_path() -> Path:
    """Return ``<repo_root>/external/Agent-S`` (always absolute)."""
    return _find_repo_root() / "external" / "Agent-S"


def _find_repo_root() -> Path:
    """Walk up from ``apps/backend/services`` until we find the repo
    root -- identified by the presence of ``apps/backend/`` (which
    contains pyproject.toml).

    Falls back to ``Path.cwd()`` if the marker can't be found; that
    keeps the function total even when the package is vendored into
    a non-standard layout.
    """
    here = Path(__file__).resolve()
    for ancestor in (here, *here.parents):
        if (ancestor / "apps" / "backend" / "pyproject.toml").is_file():
            return ancestor
    return Path.cwd()


# ---------- Loader ----------

def load_agent_s3_config() -> AgentS3Config:
    """Read every ``WINDAGENT_AGENT_S3_*`` env var into an immutable config.

    Never raises. Callers that need a hard error should use
    ``validate_or_raise()`` after loading.

    The ``external_checkout_root`` field is only populated when the
    user requested the ``external`` source AND the directory contains
    the Agent-S Python package -- so callers can use ``is None`` as a
    proxy for "external repo not actually usable".
    """
    enabled = _env_bool("WINDAGENT_AGENT_S3_ENABLED", False)
    source_raw = _env_str("WINDAGENT_AGENT_S3_SOURCE", "package").lower()
    source: AgentS3Source = "external" if source_raw == "external" else "package"
    external_path = resolve_external_path(
        _env_str("WINDAGENT_AGENT_S3_EXTERNAL_PATH", "external/Agent-S")
    )

    provider = _env_str("WINDAGENT_AGENT_S3_PROVIDER", "openai")
    model = _env_str(
        "WINDAGENT_AGENT_S3_MODEL", "gpt-5-2025-08-07"
    )
    model_url = _env_str("WINDAGENT_AGENT_S3_MODEL_URL", "")
    model_api_key = _env_str("WINDAGENT_AGENT_S3_MODEL_API_KEY", "")

    ground_provider = _env_str("WINDAGENT_AGENT_S3_GROUND_PROVIDER", "")
    ground_model = _env_str("WINDAGENT_AGENT_S3_GROUND_MODEL", "")
    ground_url = _env_str("WINDAGENT_AGENT_S3_GROUND_URL", "")
    ground_api_key = _env_str("WINDAGENT_AGENT_S3_GROUND_API_KEY", "")

    # Hard safety override: WindAgent never lets Agent-S3 run its local
    # coding sandbox. If the user sets ENABLE_LOCAL_ENV=1 we still pass
    # False downstream and record a note so debug is easy.
    notes: List[str] = []
    enable_local_env = False
    if _truthy(_env_str("WINDAGENT_AGENT_S3_ENABLE_LOCAL_ENV", "0")):
        notes.append(
            "WINDAGENT_AGENT_S3_ENABLE_LOCAL_ENV=1 was forced to False "
            "by WindAgent safety policy."
        )

    external_checkout_root: Optional[Path] = None
    if source == "external" and external_repo_available(external_path):
        external_checkout_root = external_path

    return AgentS3Config(
        enabled=enabled,
        source=source,
        external_path=external_path,
        provider=provider,
        model=model,
        model_url=model_url,
        model_api_key=model_api_key,
        ground_provider=ground_provider,
        ground_model=ground_model,
        ground_url=ground_url,
        ground_api_key=ground_api_key,
        enable_local_env=enable_local_env,
        external_checkout_root=external_checkout_root,
        notes=tuple(notes),
    )


# ---------- Validation ----------

def config_missing_fields(cfg: AgentS3Config) -> List[str]:
    """Return the names of required env vars that are empty.

    "Required" here means: needed at adapter-construction time. Model
    URL / API key are only required when the provider isn't already
    configured through another mechanism, but for portability we
    require them all when the integration is enabled.
    """
    missing: List[str] = []
    if not cfg.enabled:
        return missing
    if not cfg.provider:
        missing.append("WINDAGENT_AGENT_S3_PROVIDER")
    if not cfg.model:
        missing.append("WINDAGENT_AGENT_S3_MODEL")
    if not cfg.ground_provider:
        missing.append("WINDAGENT_AGENT_S3_GROUND_PROVIDER")
    if not cfg.ground_model:
        missing.append("WINDAGENT_AGENT_S3_GROUND_MODEL")
    if cfg.source == "external" and cfg.external_checkout_root is None:
        missing.append(
            "WINDAGENT_AGENT_S3_EXTERNAL_PATH "
            f"(no Agent-S checkout at {cfg.external_path})"
        )
    return missing


def validate_or_raise(cfg: AgentS3Config) -> None:
    """Raise ``ValueError`` if the config is unusable.

    Used by the setup script + tests to fail fast. Production code
    should consult ``config_missing_fields`` instead and surface the
    result through ``/agent-s3/health``.
    """
    if not cfg.enabled:
        return
    missing = config_missing_fields(cfg)
    if missing:
        raise ValueError(
            "Agent-S3 enabled but config is incomplete: " + ", ".join(missing)
        )
    if cfg.source == "package" and not package_available():
        raise ValueError(
            "WINDAGENT_AGENT_S3_SOURCE=package but the `gui_agents` "
            "package is not importable. Install it with:\n"
            "    uv pip install \"gui-agents==0.3.2\"\n"
            "or run scripts/setup_agent_s3.ps1."
        )
    if cfg.source == "external" and cfg.external_checkout_root is None:
        raise ValueError(
            f"WINDAGENT_AGENT_S3_SOURCE=external but no Agent-S checkout "
            f"found at {cfg.external_path}. Clone with:\n"
            f"    git clone https://github.com/simular-ai/Agent-S "
            f"{cfg.external_path}"
        )


# ---------- Status snapshot ----------

def status_from_config(cfg: AgentS3Config, last_error: Optional[str] = None) -> AgentS3ConfigStatus:
    """Build the snapshot the health endpoint returns."""
    if not cfg.enabled:
        mode: AgentS3Mode = "disabled"
    elif config_missing_fields(cfg):
        mode = "misconfigured"
    elif cfg.source == "package":
        mode = "package" if package_available() else "misconfigured"
    else:  # external
        mode = "external" if cfg.external_checkout_root is not None else "misconfigured"

    return AgentS3ConfigStatus(
        mode=mode,
        enabled=cfg.enabled,
        source=cfg.source,
        package_available=package_available(),
        external_repo_available=(
            cfg.external_checkout_root is not None
            if cfg.source == "external"
            else external_repo_available(cfg.external_path)
        ),
        config_missing=config_missing_fields(cfg),
        last_error=last_error,
        extra={
            "external_path": str(cfg.external_path),
            "provider": cfg.provider,
            "model": cfg.model,
            "ground_provider": cfg.ground_provider,
            "ground_model": cfg.ground_model,
            "enable_local_env": cfg.enable_local_env,
            "notes": list(cfg.notes),
        },
    )


__all__ = [
    "AgentS3Config",
    "AgentS3ConfigStatus",
    "AgentS3Source",
    "AgentS3Mode",
    "config_missing_fields",
    "external_repo_available",
    "load_agent_s3_config",
    "package_available",
    "resolve_external_path",
    "status_from_config",
    "validate_or_raise",
]