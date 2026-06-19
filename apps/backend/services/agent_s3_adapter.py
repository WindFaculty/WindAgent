"""Agent-S3 adapter -- thin wrapper around Simular AI's `gui-agents` SDK.

Design rules (see docs/agent_s3_integration.md):

  - We **only import** the official SDK. We do NOT reimplement the
    planner, the memory engine, the grounding engine, or the agent
    loop. If the upstream package is missing, the adapter reports
    ``status="unavailable"`` and never raises.
  - The adapter exposes a tiny surface -- ``propose()`` -- that
    returns the upstream Agent-S3 ``predict()`` result verbatim
    (info dict + list of raw action strings). The translator in
    ``agent_s3_action_translator.py`` is responsible for parsing the
    raw strings into WindAgent tool calls.
  - **We never call ``exec()`` on the action strings.** The
    translator maps each recognised pattern (``pyautogui.click``,
    ``pyautogui.typewrite``, ``pyautogui.hotkey``, ``pyautogui.press``,
    ``pyautogui.scroll``, ``time.sleep``) into one of the existing
    WindAgent tools. Anything else is rejected. This preserves the
    safety guarantee that the WindAgent planner keeps: every GUI
    action still goes through ``GuiAdapter`` + permission gate.
  - The upstream ``enable_local_env`` flag is forced to ``False``
    even if the user enabled it in env -- this is enforced here AND
    in ``agent_s3_config.py``.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.agent_s3_config import (
    AgentS3Config,
    package_available,
)


log = logging.getLogger(__name__)


# ---------- Data ----------

@dataclass(frozen=True)
class AgentS3Proposal:
    """Result of a single ``propose()`` call.

    Attributes mirror the upstream ``AgentS3.predict(instruction, obs)``
    return value: ``(info_dict, actions_list)``.

    ``raw_actions`` is the verbatim list of action code strings the
    upstream model emitted. The translator turns them into tool calls;
    callers MUST NOT exec these strings.
    """

    info: Dict[str, Any]
    raw_actions: List[str]
    instruction: str
    backend: str  # "package" | "external" | "mock"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "info": self.info,
            "raw_actions": list(self.raw_actions),
            "instruction": self.instruction,
            "backend": self.backend,
        }


@dataclass
class _AdapterState:
    """Mutable runtime state -- last error etc. -- kept off the
    frozen config so the adapter can record failures without losing
    the original config snapshot."""
    last_error: Optional[str] = None
    last_actions: List[str] = field(default_factory=list)


# ---------- Base adapter ----------

class AgentS3Adapter:
    """Thin wrapper around ``gui_agents.s3.agents.agent_s.AgentS3``.

    Construction is lazy: the upstream module is only imported on the
    first ``propose()`` call. If the import fails (package missing,
    external repo missing) the adapter stays usable -- ``propose()``
    returns ``None`` and ``last_error`` is set.

    Subclasses for tests can override ``_build_agent()`` and
    ``_call_agent()``.
    """

    name = "agent_s3"

    def __init__(self, config: AgentS3Config) -> None:
        self._cfg = config
        self._state = _AdapterState()
        # ``_agent`` is created on first propose(); None means "not
        # yet built".
        self._agent: Any = None

    # ---- Public API ----

    @property
    def last_error(self) -> Optional[str]:
        return self._state.last_error

    @property
    def last_actions(self) -> List[str]:
        return list(self._state.last_actions)

    @property
    def config(self) -> AgentS3Config:
        return self._cfg

    def is_available(self) -> bool:
        """True iff this adapter can serve ``propose()`` calls.

        Returns False when:
          - the integration is disabled, OR
          - the package is not installed (package mode), OR
          - the external checkout is missing (external mode), OR
          - required env vars are empty (see agent_s3_config).
        """
        if not self._cfg.enabled:
            return False
        if self._cfg.source == "package" and not package_available():
            return False
        if self._cfg.source == "external" and self._cfg.external_checkout_root is None:
            return False
        # If we're missing required provider / model fields, still
        # report as not-available; the health endpoint will explain
        # which fields are missing.
        from services.agent_s3_config import config_missing_fields
        if config_missing_fields(self._cfg):
            return False
        return True

    async def propose(
        self,
        instruction: str,
        observation: Dict[str, Any],
    ) -> Optional[AgentS3Proposal]:
        """Ask Agent-S3 for the next action.

        ``observation`` follows Agent-S3's schema -- usually at minimum
        ``{"screenshot": "<png path or base64>"}``. We pass it through
        verbatim.

        Returns ``None`` when the adapter is unavailable or the call
        raises; ``last_error`` is set in both cases so the caller can
        surface it.
        """
        if not self.is_available():
            self._state.last_error = (
                "agent-s3 adapter is not available; "
                "see /agent-s3/health for the reason."
            )
            return None

        try:
            agent = self._ensure_agent()
        except Exception as exc:  # noqa: BLE001
            self._state.last_error = f"build agent failed: {exc}"
            log.warning("agent_s3: build failed: %s", exc)
            return None

        try:
            info, actions = self._call_agent(agent, instruction, observation)
        except Exception as exc:  # noqa: BLE001
            self._state.last_error = f"predict failed: {exc}"
            log.warning("agent_s3: predict failed: %s", exc)
            return None

        # Normalise the result -- guard against the upstream changing shape.
        info_dict: Dict[str, Any] = info if isinstance(info, dict) else {"info": str(info)}
        actions_list: List[str] = list(actions) if actions else []

        self._state.last_actions = actions_list
        self._state.last_error = None

        return AgentS3Proposal(
            info=info_dict,
            raw_actions=actions_list,
            instruction=instruction,
            backend=self._cfg.source,
        )

    # ---- Internal: agent construction ----

    def _ensure_agent(self) -> Any:
        """Build the underlying AgentS3 instance once and cache it."""
        if self._agent is not None:
            return self._agent
        self._agent = self._build_agent()
        return self._agent

    def _build_agent(self) -> Any:
        """Import + construct the upstream AgentS3.

        Subclasses (e.g. ``MockAgentS3Adapter``) override this.
        """
        engine_params = {
            "engine_type": self._cfg.provider,
            "model": self._cfg.model,
            "base_url": self._cfg.model_url or None,
            "api_key": self._cfg.model_api_key or None,
        }
        # Ground model is mandatory in Agent-S3.
        engine_params_for_grounding = {
            "engine_type": self._cfg.ground_provider,
            "model": self._cfg.ground_model,
            "base_url": self._cfg.ground_url or None,
            "api_key": self._cfg.ground_api_key or None,
        }

        if self._cfg.source == "external":
            self._inject_external_path(self._cfg.external_checkout_root)

        AgentS3Cls, OSWorldACICls = _import_agent_s3_classes()
        # The ACI requires an `env` (the LiveComputer / LocalEnv) --
        # we pass None and rely on Agent-S3 to fall back to its
        # built-in default. (WindAgent never calls ``predict()`` in
        # production with a real env bound to the screen; that's a
        # follow-up phase.)
        grounding_agent = OSWorldACICls(
            env=None,
            platform=_detect_platform(),
            engine_params_for_generation=engine_params_for_grounding,
            engine_params_for_grounding=engine_params_for_grounding,
        )
        return AgentS3Cls(
            worker_engine_params=engine_params,
            grounding_agent=grounding_agent,
            platform=_detect_platform(),
        )

    def _call_agent(
        self,
        agent: Any,
        instruction: str,
        observation: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Call ``predict`` on the underlying agent.

        Wrapped in a helper so the mock adapter can short-circuit.
        """
        # ``predict`` is sync in the upstream SDK; we run it inline
        # because the adapter is already off the asyncio thread (it's
        # called from the WorkflowRunner via ``asyncio.to_thread``).
        return agent.predict(instruction=instruction, observation=observation)

    # ---- Internal: external source path ----

    @staticmethod
    def _inject_external_path(path: Optional[Path]) -> None:
        """Prepend the external Agent-S checkout to ``sys.path``.

        Idempotent -- if the path is already present, no-op.
        """
        if path is None:
            return
        p_str = str(path)
        if p_str in sys.path:
            return
        sys.path.insert(0, p_str)


# ---------- Mock adapter (tests) ----------

class MockAgentS3Adapter(AgentS3Adapter):
    """In-memory adapter. Never imports ``gui_agents``.

    Used by the test suite so we can assert on the translator / health
    behaviour without installing the upstream package.
    """

    def __init__(
        self,
        config: AgentS3Config,
        *,
        actions: Optional[List[str]] = None,
        info: Optional[Dict[str, Any]] = None,
        raise_on_call: Optional[Exception] = None,
        available: bool = True,
    ) -> None:
        super().__init__(config)
        # ``actions is None`` -> use a sensible default so tests that
        # only care about the propose() plumbing don't have to spell
        # out an action list. Tests that pass an explicit list (even
        # an empty one) get exactly what they asked for.
        if actions is None:
            self._mock_actions: List[str] = ["pyautogui.click(500, 300)"]
        else:
            self._mock_actions = list(actions)
        self._mock_info = info if info is not None else {"thought": "mock proposal"}
        self._raise = raise_on_call
        self._mock_available = available

    def is_available(self) -> bool:  # type: ignore[override]
        return self._mock_available and self._cfg.enabled

    def _build_agent(self) -> Any:  # type: ignore[override]
        return object()  # placeholder; never used directly

    def _call_agent(  # type: ignore[override]
        self,
        agent: Any,
        instruction: str,
        observation: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        if self._raise is not None:
            raise self._raise
        return self._mock_info, list(self._mock_actions)


# ---------- Helpers (module-level, no state) ----------

def _import_agent_s3_classes() -> Tuple[Any, Any]:
    """Lazy import of ``AgentS3`` + ``OSWorldACI``.

    Two layouts are supported:

      1. The PyPI package ``gui-agents``: ``gui_agents.s3.agents.agent_s``
         + ``gui_agents.s3.agents.grounding``.
      2. An external checkout (source == "external") where the
         upstream module path may be older / ``agent_s.s3.agents.*``.

    Returns (AgentS3, OSWorldACI). Raises ``ImportError`` with a
    message that tells the user how to fix the install.
    """
    last_err: Optional[Exception] = None
    for module_path, cls_names in _IMPORT_CANDIDATES:
        try:
            mod = importlib.import_module(module_path)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
        try:
            agent_cls = getattr(mod, cls_names[0])
            aci_cls = getattr(mod, cls_names[1])
        except AttributeError as exc:
            last_err = exc
            continue
        return agent_cls, aci_cls

    raise ImportError(
        "Could not import Agent-S3 from `gui_agents` or `agent_s`. "
        "Install with `uv pip install \"gui-agents==0.3.2\"` or clone "
        "Agent-S into external/Agent-S. Last error: "
        f"{last_err!r}"
    )


# Module-paths and class names to try, in order. Adding to this list is
# how we adapt to upstream renames without touching call sites.
_IMPORT_CANDIDATES: List[Tuple[str, Tuple[str, str]]] = [
    ("gui_agents.s3.agents.agent_s", ("AgentS3", "OSWorldACI")),
    ("agent_s.s3.agents.agent_s", ("AgentS3", "OSWorldACI")),
]


def _detect_platform() -> str:
    """Return the string Agent-S3 expects for the current platform."""
    import platform as _plat
    sysname = _plat.system().lower()
    if sysname.startswith("win"):
        return "windows"
    if sysname == "darwin":
        return "darwin"
    return "linux"


def has_gui_agents_package() -> bool:
    """Cheap check used by health + setup script."""
    return importlib.util.find_spec("gui_agents") is not None


__all__ = [
    "AgentS3Adapter",
    "AgentS3Proposal",
    "MockAgentS3Adapter",
    "has_gui_agents_package",
]