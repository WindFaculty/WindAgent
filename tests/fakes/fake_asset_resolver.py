"""
Deterministic Fake Asset Resolver & Generator for Stage H testing.

Provides mock implementations for:
- Asset content hash validation
- 3D GLB header inspection
- Preview rendering URL generation
- Background acquisition job execution
- SSRF validation checks
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional, Tuple


class FakeAssetResolver:
    """Deterministic fake for asset resolution and processing."""

    def __init__(self) -> None:
        self.resolved_assets: Dict[str, Dict[str, Any]] = {}
        self.job_history: Dict[str, Dict[str, Any]] = {}

    def resolve_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve simulated asset metadata."""
        if asset_id == "ast_bunny_3d":
            return {
                "asset_id": "ast_bunny_3d",
                "name": "Bunny Character Rig",
                "asset_type": "CHARACTER_MODEL",
                "format": "GLB",
                "content_hash": hashlib.sha256(b"ast_bunny_3d_content").hexdigest(),
                "license_state": "LICENSED",
                "processing_state": "COMPLETED",
                "signed_url": f"https://cdn.windagent.local/signed/ast_bunny_3d.glb?token=mock_valid_token",
                "webgl_renderable": True,
            }
        elif asset_id == "ast_park_bg":
            return {
                "asset_id": "ast_park_bg",
                "name": "Sunlit Park Background",
                "asset_type": "LOCATION_SET",
                "format": "PNG",
                "content_hash": hashlib.sha256(b"ast_park_bg_content").hexdigest(),
                "license_state": "UNKNOWN",
                "processing_state": "COMPLETED",
                "signed_url": f"https://cdn.windagent.local/signed/ast_park_bg.png?token=mock_valid_token",
                "webgl_renderable": False,
            }
        elif asset_id == "ast_missing_ball":
            return {
                "asset_id": "ast_missing_ball",
                "name": "Golden Ball Prop",
                "asset_type": "PROP",
                "format": "GLB",
                "content_hash": hashlib.sha256(b"ast_missing_ball_content").hexdigest(),
                "license_state": "INCOMPATIBLE",
                "processing_state": "FAILED",
                "signed_url": None,
                "webgl_renderable": False,
            }
        return self.resolved_assets.get(asset_id)

    def validate_ssrf_url(self, url: str) -> Tuple[bool, str]:
        """Validate candidate URLs for SSRF safety."""
        forbidden_hosts = ["localhost", "127.0.0.1", "169.254.169.254", "0.0.0.0", "internal.local"]
        for host in forbidden_hosts:
            if host in url.lower():
                return False, f"SSRF Protection: forbidden target host '{host}' in URL."
        if not (url.startswith("http://") or url.startswith("https://")):
            return False, "SSRF Protection: scheme must be http or https."
        return True, "URL validated successfully."

    def execute_job(self, job_id: str, asset_id: str, retry_count: int = 0) -> Dict[str, Any]:
        """Execute a simulated background processing job."""
        asset = self.resolve_asset(asset_id)
        if not asset:
            res = {"job_id": job_id, "status": "TERMINAL_FAILURE", "error": "Asset not found."}
            self.job_history[job_id] = res
            return res

        if asset["license_state"] == "INCOMPATIBLE":
            res = {
                "job_id": job_id,
                "status": "TERMINAL_FAILURE",
                "error": "Asset license verification failed: INCOMPATIBLE.",
            }
        elif asset["license_state"] == "UNKNOWN" and retry_count == 0:
            res = {
                "job_id": job_id,
                "status": "RETRYABLE_FAILURE",
                "error": "Transient storage timeout.",
            }
        else:
            res = {
                "job_id": job_id,
                "status": "COMPLETED",
                "output_hash": asset["content_hash"],
            }
        self.job_history[job_id] = res
        return res
