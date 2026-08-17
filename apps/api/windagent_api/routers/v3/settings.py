"""
V3 Settings Router — Canonical Settings Authority (Phase 13E).

Backend owns the entire settings schema: frontend renders from GET /settings/schema
and never hardcodes setting semantics. Values persist in a JSON store on the
server; secrets (API keys, tokens, credentials) are stored server-side in a
secret store and the frontend only ever receives {"configured": true/false} —
raw secrets never cross back to the browser.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from windagent_api.routers.v3.logs import emit_log

router = APIRouter(prefix="/api/v3/settings", tags=["Settings V3"])

SETTING_TYPES = {"string", "number", "boolean", "enum", "secret"}


class SettingSchemaItem(BaseModel):
    key: str
    type: str
    default: Any
    value: Any = None
    requires_restart: bool = False
    secret: bool = False
    read_only: bool = False
    min: Optional[float] = None
    max: Optional[float] = None
    enum: Optional[List[str]] = None
    description: str = ""
    group: str = "general"


class SettingsResponse(BaseModel):
    settings: List[SettingSchemaItem]
    schema_version: int = 1


class PatchSettingsRequest(BaseModel):
    values: Dict[str, Any]


class SecretConfiguredStatus(BaseModel):
    configured: bool


# ─── Canonical Settings Schema (server-owned semantics) ─────────────────────

_SETTINGS_SCHEMA: List[SettingSchemaItem] = [
    SettingSchemaItem(
        key="appearance.theme",
        type="enum",
        default="dark",
        enum=["dark", "light", "system"],
        description="UI theme mode",
        group="appearance",
    ),
    SettingSchemaItem(
        key="appearance.language",
        type="enum",
        default="vi",
        enum=["vi", "en"],
        description="Interface language",
        group="appearance",
    ),
    SettingSchemaItem(
        key="general.workspace_root",
        type="string",
        default=os.getenv("WINDAGENT_WORKSPACE_ROOT", ""),
        read_only=True,
        description="Server workspace root (read-only)",
        group="general",
    ),
    SettingSchemaItem(
        key="general.log_level",
        type="enum",
        default="INFO",
        enum=["DEBUG", "INFO", "WARNING", "ERROR"],
        description="Runtime log level",
        group="general",
    ),
    SettingSchemaItem(
        key="agent.max_concurrent_instances",
        type="number",
        default=4,
        min=1,
        max=64,
        description="Maximum concurrent agent instances",
        group="agent",
    ),
    SettingSchemaItem(
        key="agent.default_timeout_seconds",
        type="number",
        default=600,
        min=30,
        max=86_400,
        description="Default agent task timeout",
        group="agent",
    ),
    SettingSchemaItem(
        key="model.default_provider",
        type="string",
        default="auto",
        description="Default provider binding for new agents",
        group="model",
    ),
    SettingSchemaItem(
        key="routing.failover_enabled",
        type="boolean",
        default=True,
        description="Enable automatic provider failover",
        group="routing",
    ),
    SettingSchemaItem(
        key="routing.quota_window_minutes",
        type="number",
        default=60,
        min=1,
        max=1440,
        description="Quota tracking window",
        group="routing",
    ),
    SettingSchemaItem(
        key="browser.screenshot_enabled",
        type="boolean",
        default=True,
        description="Capture screenshots for browser sessions",
        group="browser",
    ),
    SettingSchemaItem(
        key="browser.max_sessions",
        type="number",
        default=5,
        min=1,
        max=20,
        description="Maximum concurrent browser sessions",
        group="browser",
    ),
    SettingSchemaItem(
        key="security.require_confirmation_destructive",
        type="boolean",
        default=True,
        description="Require confirmation for destructive actions",
        group="security",
    ),
    SettingSchemaItem(
        key="security.secret_rotation_days",
        type="number",
        default=90,
        min=1,
        max=365,
        description="Secret rotation period in days",
        group="security",
    ),
    SettingSchemaItem(
        key="integration.google_api_key",
        type="secret",
        default=None,
        secret=True,
        description="Google API key (never returned to the client)",
        group="integrations",
    ),
    SettingSchemaItem(
        key="integration.openai_api_key",
        type="secret",
        default=None,
        secret=True,
        description="OpenAI API key (never returned to the client)",
        group="integrations",
    ),
    SettingSchemaItem(
        key="integration.anthropic_api_key",
        type="secret",
        default=None,
        secret=True,
        description="Anthropic API key (never returned to the client)",
        group="integrations",
    ),
    SettingSchemaItem(
        key="integration.telegram_bot_token",
        type="secret",
        default=None,
        secret=True,
        description="Telegram bot token (never returned to the client)",
        group="integrations",
    ),
]

_DEFAULTS: Dict[str, Any] = {item.key: item.default for item in _SETTINGS_SCHEMA}
_SECRET_KEYS: List[str] = [item.key for item in _SETTINGS_SCHEMA if item.secret]


def _settings_dir() -> Path:
    root = Path(os.getenv("WINDAGENT_CONFIG_DIR", str(Path.home() / ".windagent")))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _values_path() -> Path:
    return _settings_dir() / "settings.json"


def _secrets_path() -> Path:
    return _settings_dir() / "secrets.json"


def _load_values() -> Dict[str, Any]:
    values = dict(_DEFAULTS)
    try:
        if _values_path().exists():
            stored = json.loads(_values_path().read_text(encoding="utf-8"))
            values.update({k: v for k, v in stored.items() if k in _DEFAULTS and k not in _SECRET_KEYS})
    except (ValueError, OSError):
        pass
    return values


def _load_secret_status() -> Dict[str, bool]:
    configured: Dict[str, bool] = {}
    try:
        if _secrets_path().exists():
            secrets = json.loads(_secrets_path().read_text(encoding="utf-8"))
            configured = {k: bool(v) for k, v in secrets.items() if k in _SECRET_KEYS}
    except (ValueError, OSError):
        pass
    return configured


def _save_secret(key: str, value: Optional[str]) -> None:
    secrets: Dict[str, Any] = {}
    try:
        if _secrets_path().exists():
            secrets = json.loads(_secrets_path().read_text(encoding="utf-8"))
    except (ValueError, OSError):
        pass
    if value is None or value == "":
        secrets.pop(key, None)
    else:
        secrets[key] = value  # stored server-side only; never returned
    _secrets_path().write_text(json.dumps(secrets, indent=2), encoding="utf-8")


def _persist_values(values: Dict[str, Any]) -> None:
    _values_path().write_text(json.dumps(values, indent=2), encoding="utf-8")


@router.get("/schema", response_model=SettingsResponse, operation_id="settings.getSchema")
async def get_settings_schema(request: Request) -> SettingsResponse:
    """Full settings schema with current values. Secrets render as configured-status only."""
    values = _load_values()
    secret_status = _load_secret_status()
    items: List[SettingSchemaItem] = []
    for item in _SETTINGS_SCHEMA:
        copy = item.model_copy(deep=True)
        if copy.secret:
            copy.value = {"configured": bool(secret_status.get(copy.key))}
        else:
            copy.value = values.get(copy.key, copy.default)
        items.append(copy)
    return SettingsResponse(settings=items)


@router.get("", response_model=SettingsResponse, operation_id="settings.get")
async def get_settings(request: Request) -> SettingsResponse:
    """Current settings with schema metadata."""
    return await get_settings_schema(request)


@router.patch("", response_model=SettingsResponse, operation_id="settings.patch")
async def patch_settings(body: PatchSettingsRequest, request: Request) -> SettingsResponse:
    """Apply setting updates. Secret values are stored server-side and echoed
    back only as configured-status; non-secret values persist to the settings store."""
    values = _load_values()
    for key, value in body.values.items():
        if key not in _DEFAULTS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown setting key: {key}")
        if key in _SECRET_KEYS:
            _save_secret(key, str(value) if value not in (None, "") else None)
        else:
            schema_item = next((s for s in _SETTINGS_SCHEMA if s.key == key), None)
            if schema_item:
                if schema_item.type == "boolean" and not isinstance(value, bool):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} must be boolean")
                if schema_item.type == "number":
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} must be numeric")
                    if schema_item.min is not None and value < schema_item.min:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} below minimum")
                    if schema_item.max is not None and value > schema_item.max:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} above maximum")
                if schema_item.enum and value not in schema_item.enum:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} must be one of {schema_item.enum}")
            values[key] = value
    _persist_values(values)
    emit_log(
        "INFO",
        "settings",
        "Settings updated",
        correlation_id=f"set-{len(values)}",
        metadata={"keys": list(body.values.keys())},
    )
    return await get_settings_schema(request)