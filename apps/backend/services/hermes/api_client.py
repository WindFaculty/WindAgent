"""HTTP API client for communicating with the supervised Hermes server."""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, Optional

import httpx

from services.hermes.config import HermesConfig

log = logging.getLogger(__name__)


class HermesApiClient:
    """Async API Client interacting with the Hermes REST endpoints."""

    def __init__(self, config: HermesConfig) -> None:
        self.config = config

    def _get_headers(self) -> Dict[str, str]:
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    async def start_run(
        self,
        *,
        user_message: str,
        session_id: Optional[str] = None,
        instructions: Optional[str] = None,
        model: Optional[str] = None,
        conversation_history: Optional[list[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """POST /v1/runs — Start an agent run and return the run_id."""
        url = f"{self.config.base_url}/v1/runs"
        payload: Dict[str, Any] = {"input": user_message}
        if session_id:
            payload["session_id"] = session_id
        if instructions:
            payload["instructions"] = instructions
        if model:
            payload["model"] = model
        if conversation_history:
            payload["conversation_history"] = conversation_history

        log.info("Starting Hermes run on %s with session_id=%s, model=%s", url, session_id, model)
        async with httpx.AsyncClient(timeout=self.config.request_timeout_s) as client:
            resp = await client.post(url, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    async def get_run(self, run_id: str) -> Dict[str, Any]:
        """GET /v1/runs/{run_id} — Get run status."""
        url = f"{self.config.base_url}/v1/runs/{run_id}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    async def stop_run(self, run_id: str) -> Dict[str, Any]:
        """POST /v1/runs/{run_id}/stop — Force interrupt a run."""
        url = f"{self.config.base_url}/v1/runs/{run_id}/stop"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json={}, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    async def submit_approval(self, run_id: str, choice: str) -> Dict[str, Any]:
        """POST /v1/runs/{run_id}/approval — Respond to a pending approval."""
        url = f"{self.config.base_url}/v1/runs/{run_id}/approval"
        payload = {"choice": choice}
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    async def stream_run_events(self, run_id: str) -> AsyncIterator[Dict[str, Any]]:
        """GET /v1/runs/{run_id}/events — Stream SSE events from Hermes."""
        url = f"{self.config.base_url}/v1/runs/{run_id}/events"
        headers = self._get_headers()
        
        # We need a longer timeout for streaming SSE
        timeout = httpx.Timeout(10.0, read=300.0)
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                
                # Parse Server-Sent Events (SSE) manually.
                # Format:
                #   event: <event_name>\n
                #   data: <json_data>\n\n
                current_event = None
                
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    
                    if line.startswith("event:"):
                        current_event = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        data_str = line[len("data:"):].strip()
                        try:
                            import json
                            data = json.loads(data_str)
                            # Put the event name inside the data dict if not present
                            if current_event and "event" not in data:
                                data["event"] = current_event
                            yield data
                        except Exception:
                            log.exception("Failed to parse event JSON data: %s", data_str)
                        current_event = None

    async def get_health(self) -> Dict[str, Any]:
        """GET /health — Check if Hermes server is up."""
        url = f"{self.config.base_url}/health"
        async with httpx.AsyncClient(timeout=self.config.connect_timeout_s) as client:
            resp = await client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    async def get_detailed_health(self) -> Dict[str, Any]:
        """GET /health/detailed — Get detailed health status from Hermes."""
        url = f"{self.config.base_url}/health/detailed"
        async with httpx.AsyncClient(timeout=self.config.connect_timeout_s) as client:
            resp = await client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    async def get_capabilities(self) -> Dict[str, Any]:
        """GET /v1/capabilities — Get Hermes capabilities."""
        url = f"{self.config.base_url}/v1/capabilities"
        async with httpx.AsyncClient(timeout=self.config.connect_timeout_s) as client:
            resp = await client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    async def get_models(self) -> Dict[str, Any]:
        """GET /v1/models — Get models available in Hermes."""
        url = f"{self.config.base_url}/v1/models"
        async with httpx.AsyncClient(timeout=self.config.connect_timeout_s) as client:
            resp = await client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    async def get_toolsets(self) -> Dict[str, Any]:
        """GET /v1/toolsets — Get tools configured in Hermes."""
        url = f"{self.config.base_url}/v1/toolsets"
        async with httpx.AsyncClient(timeout=self.config.connect_timeout_s) as client:
            resp = await client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    async def get_skills(self) -> Dict[str, Any]:
        """GET /v1/skills — Get skills discovered in Hermes."""
        url = f"{self.config.base_url}/v1/skills"
        async with httpx.AsyncClient(timeout=self.config.connect_timeout_s) as client:
            resp = await client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

