"""
Local & LAN Ollama Server Endpoint Manager for WindAgent Provider Subsystem V3.
Manages reachability probing and endpoint discovery for localhost and LAN Ollama servers.
Strictly adheres to ADR-05 (No in-process transformers or llama.cpp execution).
"""

from __future__ import annotations
from typing import Dict, List, Optional
import httpx

from windagent_providers.base.contracts import ProviderHealth
from windagent_providers.factory import create_ollama_provider_adapter


class LocalOllamaManager:
    """Manager and Probe Controller for Localhost and LAN Ollama Endpoints."""

    def __init__(
        self,
        endpoints: Optional[List[str]] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.endpoints = endpoints or ["http://localhost:11434"]
        self._http_client = http_client

    async def probe_endpoint(self, base_url: str) -> ProviderHealth:
        """Probes a specific local or LAN Ollama endpoint for reachability and model tags."""
        adapter = create_ollama_provider_adapter(
            base_url=base_url, http_client=self._http_client
        )
        return await adapter.health()

    async def probe_all(self) -> Dict[str, ProviderHealth]:
        """Probes all configured local/LAN endpoints and returns health map."""
        results: Dict[str, ProviderHealth] = {}
        for ep in self.endpoints:
            results[ep] = await self.probe_endpoint(ep)
        return results

    async def get_healthy_endpoint(self) -> Optional[str]:
        """Returns the first available healthy local/LAN endpoint URL."""
        health_map = await self.probe_all()
        for ep, health in health_map.items():
            if health.healthy:
                return ep
        return None
