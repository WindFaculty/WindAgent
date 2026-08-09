"""
Stage G — State Recovery Domain & Sanitization Service (UI39).

Defines versioned state recovery snapshots, checksum calculation, validation,
and security sanitization to prevent leaking tokens, credentials, or local paths.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


SCHEMA_VERSION_V1 = "1.0.0"

# Regex patterns for redacting sensitive content
TOKEN_PATTERN = re.compile(r"(Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*)|(sk-[A-Za-z0-9]{16,})|(access_token=[^&]+)")
LOCAL_PATH_PATTERN = re.compile(r"([A-Z]:\\[^:\*\?\"<>\|]+)|(/home/[^\s]+)|(/Users/[^\s]+)")
SIGNED_URL_PATTERN = re.compile(r"https?://[^\s]+(?:\?|&)(?:Signature|X-Amz-Signature|token)=[^&\s]+")


def compute_snapshot_checksum(data_dict: Dict[str, Any]) -> str:
    """Computes a SHA-256 checksum for snapshot data excluding the checksum field itself."""
    canonical_dict = {k: v for k, v in data_dict.items() if k != "checksum"}
    encoded = json.dumps(canonical_dict, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sanitize_recovery_payload(data: Any) -> Any:
    """Recursively redacts tokens, credentials, signed URLs, and absolute local filesystem paths."""
    if isinstance(data, str):
        cleaned = TOKEN_PATTERN.sub("[REDACTED_SECRET]", data)
        cleaned = SIGNED_URL_PATTERN.sub("[REDACTED_SIGNED_URL]", cleaned)
        cleaned = LOCAL_PATH_PATTERN.sub("[REDACTED_LOCAL_PATH]", cleaned)
        return cleaned
    elif isinstance(data, dict):
        sanitized = {}
        for key, val in data.items():
            lower_key = key.lower()
            if any(forbidden in lower_key for forbidden in ["token", "secret", "password", "auth", "credential", "signed_url"]):
                sanitized[key] = "[REDACTED_SECRET]"
            else:
                sanitized[key] = sanitize_recovery_payload(val)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_recovery_payload(item) for item in data]
    return data


class ProductionRecoverySnapshot(BaseModel):
    """Versioned recovery snapshot saved to frontend local storage."""

    schema_version: str = SCHEMA_VERSION_V1
    saved_at: str
    expires_at: Optional[str] = None
    project_id: str
    route: str = "/screenplay"
    revision_id: str
    base_sequence: int = 0
    selected_scene_id: Optional[str] = None
    selected_asset_id: Optional[str] = None
    editor_mode: str = "STRUCTURED"  # "STRUCTURED" | "TEXT" | "HYBRID" | "READ_ONLY"
    draft_kind: str = "SCREENPLAY_DRAFT"  # "SCREENPLAY_DRAFT" | "ASSET_ACQUISITION" | "PROPOSAL_FORM"
    edit_units: Dict[str, Any] = Field(default_factory=dict)
    last_acknowledged_command: Optional[str] = None
    checksum: str = ""

    def validate_checksum(self) -> bool:
        """Returns True if the snapshot checksum matches the computed checksum."""
        expected = compute_snapshot_checksum(self.model_dump())
        return self.checksum == expected

    def sanitize(self) -> ProductionRecoverySnapshot:
        """Returns a copy of the snapshot with sensitive data sanitized."""
        dict_data = self.model_dump()
        sanitized_units = sanitize_recovery_payload(dict_data.get("edit_units", {}))
        dict_data["edit_units"] = sanitized_units
        # Recompute checksum after sanitization
        dict_data["checksum"] = compute_snapshot_checksum(dict_data)
        return ProductionRecoverySnapshot(**dict_data)


def create_recovery_snapshot(
    saved_at: str,
    project_id: str,
    revision_id: str,
    base_sequence: int,
    route: str = "/screenplay",
    selected_scene_id: Optional[str] = None,
    selected_asset_id: Optional[str] = None,
    editor_mode: str = "STRUCTURED",
    draft_kind: str = "SCREENPLAY_DRAFT",
    edit_units: Optional[Dict[str, Any]] = None,
    last_acknowledged_command: Optional[str] = None,
) -> ProductionRecoverySnapshot:
    """Helper factory for building a validated, sanitized recovery snapshot."""
    raw_units = edit_units or {}
    sanitized_units = sanitize_recovery_payload(raw_units)

    snapshot = ProductionRecoverySnapshot(
        schema_version=SCHEMA_VERSION_V1,
        saved_at=saved_at,
        project_id=project_id,
        route=route,
        revision_id=revision_id,
        base_sequence=base_sequence,
        selected_scene_id=selected_scene_id,
        selected_asset_id=selected_asset_id,
        editor_mode=editor_mode,
        draft_kind=draft_kind,
        edit_units=sanitized_units,
        last_acknowledged_command=last_acknowledged_command,
        checksum="",
    )
    snapshot.checksum = compute_snapshot_checksum(snapshot.model_dump())
    return snapshot
