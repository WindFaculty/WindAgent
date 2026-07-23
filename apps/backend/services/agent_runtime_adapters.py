"""Phase 2 — Agent runtime adapters routing requests through the central router service."""
from __future__ import annotations

from typing import Optional
from services.router_execution_service import RouterExecutionService

class CodingAgent:
    """Agent runtime adapter for Coding tasks routing via 'Coder' role."""

    def __init__(self, router_service: RouterExecutionService) -> None:
        self.router_service = router_service

    async def execute_task(self, prompt: str, context: Optional[str] = None) -> str:
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})
        return await self.router_service.execute_chat("Coder", messages)


class GUIAgent:
    """Agent runtime adapter for GUI layout tasks routing via 'GUI Agent' role."""

    def __init__(self, router_service: RouterExecutionService) -> None:
        self.router_service = router_service

    async def run_step(self, instruction: str, screenshot_base64: Optional[str] = None) -> str:
        system = "You are a GUI action coordinator. Propose pyautogui coordinates."
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Instruction: {instruction}. Observation: {screenshot_base64 or 'None'}"}
        ]
        return await self.router_service.execute_chat("GUI Agent", messages)


class WorkflowAgent:
    """Agent runtime adapter for Workflow tasks routing via 'Memory Agent' or 'Fallback' role."""

    def __init__(self, router_service: RouterExecutionService) -> None:
        self.router_service = router_service

    async def lookup_memory(self, query: str) -> str:
        messages = [
            {"role": "system", "content": "You are a context lookup memory retriever."},
            {"role": "user", "content": query}
        ]
        return await self.router_service.execute_chat("Memory Agent", messages)


class ResearchAgent:
    """Agent runtime adapter for Research tasks routing via 'Researcher' role."""

    def __init__(self, router_service: RouterExecutionService) -> None:
        self.router_service = router_service

    async def scrape_and_parse(self, url: str) -> str:
        messages = [
            {"role": "system", "content": "Parse HTML structure and extract facts."},
            {"role": "user", "content": f"Target: {url}"}
        ]
        return await self.router_service.execute_chat("Researcher", messages)
