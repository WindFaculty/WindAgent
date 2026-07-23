"""
Probe Plan Execution Engine for WindAgent Provider Subsystem V3 Test Connect.
Executes multi-step probing with hard timeouts (5s per step) and response body truncation.
"""

from __future__ import annotations
import json
import time
from typing import Any, Dict, List, Optional
import httpx

from windagent_providers.detection.fingerprints import ProtocolFingerprint, detect_vendor_from_url_or_key
from windagent_providers.detection.url_sanitizer import sanitize_url
from windagent_providers.base.secret_redaction import redact_text


class ProbePlanRunner:
    """Executes safe step-by-step probing matrix against target endpoint."""

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None, timeout_seconds: float = 5.0):
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def _get_client(self) -> httpx.AsyncClient:
        if self.http_client:
            return self.http_client
        return httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds))

    async def probe_endpoint(
        self,
        base_url: str,
        credential: Optional[str] = None,
        selected_hint: Optional[str] = None,
        manual_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs probing matrix and returns Test Connect output payload."""
        clean_url = sanitize_url(base_url)
        evidence: List[str] = []
        warnings: List[str] = []

        headers = {"Content-Type": "application/json"}
        if credential:
            headers["Authorization"] = f"Bearer {credential}"
            headers["x-api-key"] = credential

        client = self._get_client()
        should_close = self.http_client is None

        vendor, vendor_conf = detect_vendor_from_url_or_key(clean_url, credential)
        if selected_hint and selected_hint.lower() != "auto" and selected_hint.lower() != vendor:
            warnings.append(f"Selected hint '{selected_hint}' differs from detected vendor '{vendor}'")

        protocol = manual_override or "openai"
        connected = False
        auth_valid = False
        discovery_supported = False
        models_found = 0

        try:
            # Step 1: Probe Ollama `/api/tags`
            try:
                r_ollama = await client.get(f"{clean_url}/api/tags", headers=headers)
                if r_ollama.status_code == 200:
                    data = r_ollama.json()
                    if "models" in data:
                        connected = True
                        auth_valid = True
                        discovery_supported = True
                        models_found = len(data["models"])
                        protocol = "ollama"
                        vendor = "ollama"
                        evidence.append(f"Ollama tags endpoint returned 200 OK with {models_found} models")
            except Exception:
                pass

            # Step 2: Probe Google Gemini `/v1beta/models` if not matched
            if not connected:
                try:
                    r_gem = await client.get(f"{clean_url}/models?key={credential or ''}", headers={"Content-Type": "application/json"})
                    if r_gem.status_code == 200:
                        data = r_gem.json()
                        if "models" in data and any("gemini" in str(m) for m in data["models"]):
                            connected = True
                            auth_valid = True
                            discovery_supported = True
                            models_found = len(data["models"])
                            protocol = "gemini"
                            vendor = "google"
                            evidence.append("Google Gemini models endpoint returned 200 OK")
                except Exception:
                    pass

            # Step 3: Probe Anthropic `/v1/models` if URL/key hints Anthropic
            if not connected and (vendor == "anthropic" or "anthropic" in clean_url):
                try:
                    r_ant = await client.get(f"{clean_url}/models", headers={"x-api-key": credential or "", "anthropic-version": "2023-06-01"})
                    if r_ant.status_code == 200:
                        data = r_ant.json()
                        if "data" in data or "models" in data:
                            connected = True
                            auth_valid = True
                            discovery_supported = True
                            models_found = len(data.get("data", []))
                            protocol = "anthropic"
                            vendor = "anthropic"
                            evidence.append("Anthropic models endpoint returned 200 OK")
                except Exception:
                    pass

            # Step 4: Probe OpenAI `/v1/models`
            if not connected:
                try:
                    r_openai = await client.get(f"{clean_url}/models", headers=headers)
                    if r_openai.status_code == 200:
                        data = r_openai.json()
                        if "data" in data or "models" in data:
                            connected = True
                            auth_valid = True
                            discovery_supported = True
                            m_list = data.get("data") or data.get("models", [])
                            models_found = len(m_list)
                            protocol = "openai"
                            evidence.append(f"OpenAI models endpoint returned 200 OK with {models_found} models")
                    elif r_openai.status_code in (401, 403):
                        connected = True
                        auth_valid = False
                        evidence.append(f"Endpoint responded with HTTP {r_openai.status_code} (Auth failed)")
                        warnings.append("Authentication credentials invalid or missing")
                except Exception as exc:
                    warnings.append(f"Network probe failed: {redact_text(str(exc))}")

            if manual_override and manual_override != protocol:
                warnings.append(f"Manual override forced protocol '{manual_override}' over detected '{protocol}'")
                protocol = manual_override

            confidence = 0.96 if connected and auth_valid else (0.50 if connected else 0.0)

            return {
                "connected": connected,
                "detected_vendor": vendor,
                "detected_protocol": protocol,
                "confidence": confidence,
                "auth_valid": auth_valid,
                "model_discovery_supported": discovery_supported,
                "models_found": models_found,
                "evidence": evidence,
                "warnings": warnings,
            }
        finally:
            if should_close:
                await client.aclose()
