"""
EndpointDetector entry point for WindAgent Provider Subsystem V3.
Safely detects provider endpoints, protocols, vendors, and auth status for Test Connect workflows.
"""

from __future__ import annotations
from typing import Any, Dict, Optional
import httpx

from windagent_providers.detection.probe_plan import ProbePlanRunner


class EndpointDetector:
    """High-level detector interface for Test Connect workflows."""

    def __init__(
        self,
        http_client: Optional[httpx.AsyncClient] = None,
        timeout_seconds: float = 5.0,
    ):
        self.runner = ProbePlanRunner(
            http_client=http_client, timeout_seconds=timeout_seconds
        )

    async def test_connection(
        self,
        base_url: str,
        credential: Optional[str] = None,
        selected_provider_hint: Optional[str] = None,
        manual_protocol_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes safe Test Connect detection.
        Credentials exist ONLY in volatile memory and are NEVER saved or echoed.
        """
        return await self.runner.probe_endpoint(
            base_url=base_url,
            credential=credential,
            selected_hint=selected_provider_hint,
            manual_override=manual_protocol_override,
        )
