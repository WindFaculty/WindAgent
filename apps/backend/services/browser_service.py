"""Browser Service — controls Playwright or falls back to a visual Mock Browser."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List
from uuid import UUID

from PIL import Image, ImageDraw, ImageFont

from schemas.event import EventEnvelope
from services.event_bus import EventBus

log = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class BrowserService:
    """Manages active browser contexts per session. Falls back to Pillow-based mock."""

    def __init__(self, event_bus: EventBus, artifacts_root: Path) -> None:
        self.event_bus = event_bus
        self.artifacts_root = artifacts_root
        self._contexts: Dict[str, Dict[str, Any]] = {}
        self._pw_instance: Optional[Any] = None

    async def start(self) -> None:
        """Initialize the browser service."""
        log.info("BrowserService starting up. Playwright available: %s", PLAYWRIGHT_AVAILABLE)
        if PLAYWRIGHT_AVAILABLE:
            try:
                self._pw_instance = await async_playwright().start()
            except Exception as e:
                log.warning("Failed to start Playwright instance, falling back to mock: %s", e)

    async def close_all(self) -> None:
        """Close all active browser sessions."""
        for session_id in list(self._contexts.keys()):
            try:
                await self.close_browser(session_id)
            except Exception:
                log.exception("Error closing browser for session %s", session_id)
        if self._pw_instance:
            try:
                await self._pw_instance.stop()
            except Exception:
                log.exception("Error stopping Playwright instance")
            self._pw_instance = None

    async def get_or_create_browser(self, session_id: str) -> Dict[str, Any]:
        """Fetch existing browser context or create a new one."""
        if session_id in self._contexts:
            return self._contexts[session_id]

        log.info("Creating new browser session for %s", session_id)
        
        screenshot_dir = self.artifacts_root / "browser" / session_id
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / "current.png"

        context_info: Dict[str, Any] = {
            "session_id": session_id,
            "url": "about:blank",
            "title": "New Tab",
            "loading": False,
            "screenshot_path": str(screenshot_path),
            "controlled_by": "agent",
            "console_logs": [],
            "errors": [],
            "playwright_active": False,
        }

        # Attempt Playwright launch
        if PLAYWRIGHT_AVAILABLE and self._pw_instance:
            try:
                browser = await self._pw_instance.chromium.launch(headless=True)
                pw_context = await browser.new_context(viewport={"width": 1280, "height": 800})
                page = await pw_context.new_page()
                
                context_info.update({
                    "playwright_active": True,
                    "browser": browser,
                    "pw_context": pw_context,
                    "page": page,
                })

                # Register events
                page.on("console", lambda msg: self._handle_console(session_id, msg.text))
                page.on("pageerror", lambda err: self._handle_error(session_id, err.message))
                
                log.info("Successfully launched real Playwright browser for session %s", session_id)
            except Exception as e:
                log.warning("Playwright launch failed for session %s, falling back to mock: %s", session_id, e)

        self._contexts[session_id] = context_info
        
        # Save initial blank screenshot
        await self._update_screenshot(session_id)
        
        # Publish start event
        await self._publish_event(session_id, "browser_session_started", {
            "session_id": session_id,
            "url": context_info["url"],
            "title": context_info["title"],
            "controlled_by": context_info["controlled_by"],
        })
        
        return context_info

    def get_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the serialization-friendly status of a browser session."""
        ctx = self._contexts.get(session_id)
        if not ctx:
            return None
        return {
            "session_id": ctx["session_id"],
            "url": ctx["url"],
            "title": ctx["title"],
            "loading": ctx["loading"],
            "screenshot_path": ctx["screenshot_path"],
            "controlled_by": ctx["controlled_by"],
            "console_logs": ctx["console_logs"][-20:],
            "errors": ctx["errors"][-20:],
        }

    async def navigate(self, session_id: str, url: str) -> Dict[str, Any]:
        """Navigate to a given URL."""
        ctx = await self.get_or_create_browser(session_id)
        ctx["loading"] = True
        ctx["url"] = url
        
        await self._publish_event(session_id, "browser_navigation_started", {
            "session_id": session_id,
            "url": url,
        })

        if ctx["playwright_active"]:
            try:
                page = ctx["page"]
                await page.goto(url, wait_until="load", timeout=30000)
                ctx["url"] = page.url
                ctx["title"] = await page.title() or page.url
            except Exception as e:
                log.exception("Playwright navigation error for %s", url)
                ctx["errors"].append(f"Navigation error: {e}")
                await self._publish_event(session_id, "browser_error", {
                    "session_id": session_id,
                    "message": str(e),
                })
        else:
            # Simulate navigation delay
            await asyncio.sleep(0.5)
            ctx["title"] = f"Mock: {url}"
            # Log some mock console output
            self._handle_console(session_id, f"Mock browser navigated to {url}")

        ctx["loading"] = False
        await self._update_screenshot(session_id)

        state = self.get_state(session_id)
        await self._publish_event(session_id, "browser_navigation_completed", state)
        return state

    async def click(self, session_id: str, selector: Optional[str] = None, x: int = 0, y: int = 0) -> Dict[str, Any]:
        """Click on the page by selector or relative viewport coordinates."""
        ctx = await self.get_or_create_browser(session_id)
        
        await self._publish_event(session_id, "browser_action_started", {
            "session_id": session_id,
            "action": "click",
            "selector": selector,
            "x": x,
            "y": y,
        })

        if ctx["playwright_active"]:
            try:
                page = ctx["page"]
                if selector:
                    await page.click(selector, timeout=5000)
                else:
                    await page.mouse.click(x, y)
                # Wait for potential navigation / DOM update
                await page.wait_for_timeout(1000)
                ctx["url"] = page.url
                ctx["title"] = await page.title() or page.url
            except Exception as e:
                log.exception("Playwright click error")
                ctx["errors"].append(f"Click error: {e}")
        else:
            await asyncio.sleep(0.2)
            self._handle_console(session_id, f"Mock browser clicked coordinates ({x}, {y})")

        await self._update_screenshot(session_id, last_click=(x, y))
        state = self.get_state(session_id)
        await self._publish_event(session_id, "browser_action_completed", {
            **state,
            "last_action": "click",
            "click_x": x,
            "click_y": y,
        })
        return state

    async def type_text(self, session_id: str, text: str, selector: Optional[str] = None) -> Dict[str, Any]:
        """Type text into a selector or focused input."""
        ctx = await self.get_or_create_browser(session_id)

        # Scrub sensitive input logs
        log_text = "[REDACTED]" if "pass" in str(selector).lower() else text
        
        await self._publish_event(session_id, "browser_action_started", {
            "session_id": session_id,
            "action": "type",
            "selector": selector,
            "text": log_text,
        })

        if ctx["playwright_active"]:
            try:
                page = ctx["page"]
                if selector:
                    await page.fill(selector, text, timeout=5000)
                else:
                    await page.keyboard.type(text)
                await page.wait_for_timeout(500)
            except Exception as e:
                log.exception("Playwright type error")
                ctx["errors"].append(f"Type error: {e}")
        else:
            await asyncio.sleep(0.2)
            self._handle_console(session_id, f"Mock browser typed text into {selector or 'active element'}")

        await self._update_screenshot(session_id)
        state = self.get_state(session_id)
        await self._publish_event(session_id, "browser_action_completed", {
            **state,
            "last_action": "type",
        })
        return state

    async def go_back(self, session_id: str) -> Dict[str, Any]:
        """Navigate back in history."""
        ctx = await self.get_or_create_browser(session_id)
        if ctx["playwright_active"]:
            try:
                await ctx["page"].go_back()
                ctx["url"] = ctx["page"].url
                ctx["title"] = await ctx["page"].title()
            except Exception as e:
                log.warning("Go back failed: %s", e)
        else:
            self._handle_console(session_id, "Mock browser go back requested")

        await self._update_screenshot(session_id)
        state = self.get_state(session_id)
        await self._publish_event(session_id, "browser_navigation_completed", state)
        return state

    async def go_forward(self, session_id: str) -> Dict[str, Any]:
        """Navigate forward in history."""
        ctx = await self.get_or_create_browser(session_id)
        if ctx["playwright_active"]:
            try:
                await ctx["page"].go_forward()
                ctx["url"] = ctx["page"].url
                ctx["title"] = await ctx["page"].title()
            except Exception as e:
                log.warning("Go forward failed: %s", e)
        else:
            self._handle_console(session_id, "Mock browser go forward requested")

        await self._update_screenshot(session_id)
        state = self.get_state(session_id)
        await self._publish_event(session_id, "browser_navigation_completed", state)
        return state

    async def reload(self, session_id: str) -> Dict[str, Any]:
        """Reload the page."""
        ctx = await self.get_or_create_browser(session_id)
        if ctx["playwright_active"]:
            try:
                await ctx["page"].reload()
                ctx["url"] = ctx["page"].url
                ctx["title"] = await ctx["page"].title()
            except Exception as e:
                log.warning("Reload failed: %s", e)
        else:
            self._handle_console(session_id, "Mock browser reload requested")

        await self._update_screenshot(session_id)
        state = self.get_state(session_id)
        await self._publish_event(session_id, "browser_navigation_completed", state)
        return state

    async def set_control(self, session_id: str, control: str) -> Dict[str, Any]:
        """Toggle browser ownership (agent vs user)."""
        ctx = await self.get_or_create_browser(session_id)
        ctx["controlled_by"] = control
        
        await self._publish_event(session_id, "browser_screenshot_updated", {
            "session_id": session_id,
            "controlled_by": control,
        })
        return self.get_state(session_id)

    async def close_browser(self, session_id: str) -> None:
        """Close the browser instance for this session."""
        ctx = self._contexts.pop(session_id, None)
        if ctx and ctx["playwright_active"]:
            try:
                await ctx["page"].close()
                await ctx["pw_context"].close()
                await ctx["browser"].close()
                log.info("Closed Playwright browser for session %s", session_id)
            except Exception as e:
                log.warning("Error during Playwright browser close: %s", e)

    # ---------- Private Helpers ----------

    def _handle_console(self, session_id: str, text: str) -> None:
        ctx = self._contexts.get(session_id)
        if ctx:
            ctx["console_logs"].append(text)
            asyncio.create_task(self._publish_event(session_id, "browser_console", {
                "session_id": session_id,
                "message": text,
            }))

    def _handle_error(self, session_id: str, text: str) -> None:
        ctx = self._contexts.get(session_id)
        if ctx:
            ctx["errors"].append(text)
            asyncio.create_task(self._publish_event(session_id, "browser_error", {
                "session_id": session_id,
                "message": text,
            }))

    async def _update_screenshot(self, session_id: str, last_click: Optional[tuple[int, int]] = None) -> None:
        ctx = self._contexts.get(session_id)
        if not ctx:
            return

        path = Path(ctx["screenshot_path"])
        if ctx["playwright_active"]:
            try:
                page = ctx["page"]
                await page.screenshot(path=path)
                
                # If there was a click, overlay a dot to show user where click happened
                if last_click:
                    x, y = last_click
                    try:
                        with Image.open(path) as img:
                            draw = ImageDraw.Draw(img)
                            # Draw a red targeting circle
                            draw.ellipse([x - 6, y - 6, x + 6, y + 6], fill="#ef4444", outline="#ffffff", width=2)
                            img.save(path)
                    except Exception:
                        pass
            except Exception as e:
                log.warning("Failed to take Playwright screenshot: %s", e)
                self._draw_mock_screenshot(path, ctx, last_click)
        else:
            self._draw_mock_screenshot(path, ctx, last_click)

        await self._publish_event(session_id, "browser_screenshot_updated", {
            "session_id": session_id,
            "screenshot_url": f"/api/v1/sessions/{session_id}/browser/screenshot?t={int(datetime.now().timestamp() * 1000)}",
        })

    def _draw_mock_screenshot(self, path: Path, ctx: Dict[str, Any], last_click: Optional[tuple[int, int]] = None) -> None:
        """Draw a visually rich mockup browser preview when running offline / mock mode."""
        # 1280 x 800 viewport
        img = Image.new("RGB", (1280, 800), color="#0f172a") # dark slate theme matching WindAgent
        draw = ImageDraw.Draw(img)

        # Draw Browser top bar / chrome
        draw.rectangle([0, 0, 1280, 80], fill="#1e293b")
        # Draw address bar
        draw.rectangle([120, 25, 1160, 55], fill="#334155", outline="#475569", width=1)
        # Draw address bar URL text
        draw.text((135, 33), ctx["url"], fill="#94a3b8")

        # Draw control buttons (back, forward, refresh placeholders)
        draw.ellipse([20, 30, 44, 54], fill="#475569")
        draw.ellipse([54, 30, 78, 54], fill="#475569")
        draw.ellipse([88, 30, 112, 54], fill="#475569")

        # Draw main page content panel
        draw.rectangle([20, 100, 1260, 780], fill="#1e293b", outline="#334155", width=2)

        # Draw a beautiful mock UI inside the page depending on the URL
        url_lower = ctx["url"].lower()
        if "google.com" in url_lower:
            # Google mock
            draw.text((640, 260), "Google", fill="#ffffff", anchor="mm")
            draw.rectangle([340, 320, 940, 370], fill="#0f172a", outline="#475569", width=1)
            draw.text((640, 345), "Search or type URL...", fill="#64748b", anchor="mm")
            # Buttons
            draw.rectangle([500, 400, 620, 435], fill="#334155", outline="#475569")
            draw.text((560, 417), "Google Search", fill="#e2e8f0", anchor="mm")
            draw.rectangle([660, 400, 780, 435], fill="#334155", outline="#475569")
            draw.text((720, 417), "I'm Feeling Lucky", fill="#e2e8f0", anchor="mm")
        elif "about:blank" in url_lower or not ctx["url"] or ctx["url"] == "about:blank":
            draw.text((640, 400), "New Tab — Enter URL to navigate", fill="#64748b", anchor="mm")
        else:
            # General mockup site layout
            draw.text((60, 130), f"Site: {ctx['title']}", fill="#ffffff")
            draw.text((60, 160), f"Address: {ctx['url']}", fill="#94a3b8")
            
            # Draw mock sections
            draw.rectangle([60, 200, 400, 350], fill="#334155")
            draw.text((230, 275), "Sidebar Menu", fill="#cbd5e1", anchor="mm")
            
            draw.rectangle([430, 200, 1220, 600], fill="#334155")
            draw.text((825, 400), "Main Web Page Layout Content Pane", fill="#cbd5e1", anchor="mm")

            draw.rectangle([430, 620, 1220, 740], fill="#334155")
            draw.text((825, 680), "Console Log Stream (See logs panel)", fill="#94a3b8", anchor="mm")

        # Overlay targeted red click indicator if click coordinate is provided
        if last_click:
            cx, cy = last_click
            # Clamp inside boundaries
            cx = max(10, min(cx, 1270))
            cy = max(10, min(cy, 790))
            draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill="#ef4444", outline="#ffffff", width=2)

        img.save(path)

    async def _publish_event(self, session_id: str, event_name: str, data: Dict[str, Any]) -> None:
        ts = datetime.now(timezone.utc)
        env = EventEnvelope(
            event=event_name,
            timestamp=ts,
            data=data,
        )
        await self.event_bus.publish(session_id, env)
