"""
B-Roll and Visual Overlay Callout Renderer for Code Video Production (1440p Master).

Renders floating code highlights, security warning banners, formula callouts,
and concept callout overlays for scenes S06, S07, S08, S09, S10, S13, and S19.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import html
import json
from typing import Any, Dict, List, Optional

from windagent_tools.code_video.renderer.theme import CodeVideoVisualTheme


class OverlayPosition(str, Enum):
    TOP_RIGHT = "TOP_RIGHT"
    BOTTOM_RIGHT = "BOTTOM_RIGHT"
    BOTTOM_CENTER = "BOTTOM_CENTER"
    CENTER = "CENTER"
    FULL_SPLIT = "FULL_SPLIT"


@dataclass
class OverlayCardState:
    """State for a visual callout/overlay banner."""
    overlay_id: str
    title: str
    body_text: str = ""
    badge: str = ""
    highlight_code: str = ""
    position: OverlayPosition = OverlayPosition.BOTTOM_RIGHT
    is_warning: bool = False
    is_security: bool = False
    theme: CodeVideoVisualTheme = field(default_factory=CodeVideoVisualTheme)

    def get_source_hash(self) -> str:
        data = {
            "overlay_id": self.overlay_id,
            "title": self.title,
            "body_text": self.body_text,
            "badge": self.badge,
            "highlight_code": self.highlight_code,
            "position": self.position.value,
            "is_warning": self.is_warning,
            "is_security": self.is_security,
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overlay_id": self.overlay_id,
            "title": self.title,
            "body_text": self.body_text,
            "badge": self.badge,
            "highlight_code": self.highlight_code,
            "position": self.position.value,
            "is_warning": self.is_warning,
            "is_security": self.is_security,
            "source_hash": self.get_source_hash(),
        }

    def render_html(self) -> str:
        palette = self.theme.palette
        insets = self.theme.insets
        typo = self.theme.typography

        # Determine accent color and border
        if self.is_security:
            accent_color = palette.danger
            card_border = palette.danger
            bg_tint = "rgba(248, 81, 73, 0.15)"
        elif self.is_warning:
            accent_color = palette.warning
            card_border = palette.warning
            bg_tint = "rgba(210, 153, 34, 0.15)"
        else:
            accent_color = palette.primary
            card_border = palette.card_border_active
            bg_tint = "rgba(88, 166, 255, 0.1)"

        badge_html = (
            f'<span style="background: {bg_tint}; color: {accent_color}; border: 1px solid {accent_color}; '
            f'padding: 4px 16px; border-radius: 6px; font-size: {typo.badge_font_px}px; font-family: {typo.font_family_mono}; '
            f'font-weight: 700; margin-bottom: 12px; display: inline-block;">{html.escape(self.badge)}</span>'
        ) if self.badge else ""

        code_html = (
            f'<div style="background: #040d21; border: 1px solid {palette.card_border}; border-radius: 8px; '
            f'padding: 16px 20px; margin-top: 14px; font-family: {typo.font_family_mono}; font-size: {typo.body_font_px}px; '
            f'color: {palette.success}; white-space: pre;">{html.escape(self.highlight_code)}</div>'
        ) if self.highlight_code else ""

        body_html = (
            f'<p style="color: {palette.text_secondary}; font-size: {typo.body_font_px}px; margin: 8px 0 0 0; '
            f'line-height: 1.4;">{html.escape(self.body_text)}</p>'
        ) if self.body_text else ""

        # Positioning styles
        pos_style = "position: absolute; "
        if self.position == OverlayPosition.BOTTOM_RIGHT:
            pos_style += f"right: {insets.action_safe_dx}px; bottom: {insets.action_safe_dy}px; max-width: 900px;"
        elif self.position == OverlayPosition.TOP_RIGHT:
            pos_style += f"right: {insets.action_safe_dx}px; top: {insets.action_safe_dy}px; max-width: 900px;"
        elif self.position == OverlayPosition.BOTTOM_CENTER:
            pos_style += f"left: 50%; transform: translateX(-50%); bottom: {insets.action_safe_dy}px; max-width: 1200px; width: 90%;"
        elif self.position == OverlayPosition.CENTER:
            pos_style += f"left: 50%; top: 50%; transform: translate(-50%, -50%); max-width: 1200px; width: 90%;"
        else:
            pos_style += f"left: {insets.action_safe_dx}px; top: {insets.action_safe_dy}px; right: {insets.action_safe_dx}px; bottom: {insets.action_safe_dy}px;"

        return (
            f'<div class="overlay-stage" style="width: 2560px; height: 1440px; position: relative; pointer-events: none; overflow: hidden;">\n'
            f'  <div class="overlay-card" id="{self.overlay_id}" style="'
            f'{pos_style} background: {palette.card_bg}; border: 2px solid {card_border}; '
            f'border-radius: 16px; padding: 28px 36px; box-shadow: 0 0 24px rgba(0,0,0,0.6); '
            f'box-sizing: border-box; font-family: {typo.font_family_sans}; z-index: 1000; pointer-events: auto;">\n'
            f'    {badge_html}\n'
            f'    <h3 style="color: {palette.text_primary}; font-size: {typo.card_title_font_px}px; font-weight: 800; margin: 0;">'
            f'{html.escape(self.title)}</h3>\n'
            f'    {body_html}\n'
            f'    {code_html}\n'
            f'  </div>\n'
            f'</div>'
        )


class OverlayRenderer:
    """Catalog of canonical B-roll overlays and banners for Video 02."""

    @classmethod
    def build_ovr_s06_message(cls) -> OverlayCardState:
        return OverlayCardState(
            overlay_id="OVR_S06_MESSAGE_DATACLASS",
            badge="CONTRACT IMMUTABILITY",
            title="Message: Frozen Dataclass",
            body_text="role ('system' | 'user' | 'assistant') + content (str). Bất biến & Thread-safe.",
            highlight_code="@dataclass(frozen=True)\nclass Message:\n    role: str\n    content: str",
            position=OverlayPosition.BOTTOM_RIGHT,
        )

    @classmethod
    def build_ovr_s07_config(cls) -> OverlayCardState:
        return OverlayCardState(
            overlay_id="OVR_S07_CONFIG_FIELDS",
            badge="AGENT CONFIGURATION",
            title="AgentConfig: Domain Parameters",
            body_text="Định nghĩa danh tính agent, prompt hệ thống, model ID và temperature.",
            highlight_code="name: str = 'SimpleAgent'\nsystem_prompt: str = '...'\nmodel: str = '...'\ntemperature: float = 0.7",
            position=OverlayPosition.BOTTOM_RIGHT,
        )

    @classmethod
    def build_ovr_s08_protocol(cls) -> OverlayCardState:
        return OverlayCardState(
            overlay_id="OVR_S08_LLMCLIENT_PROTOCOL",
            badge="CLEAN ARCHITECTURE",
            title="LLMClient Protocol",
            body_text="Agent Core phụ thuộc vào Protocol trừu tượng, không phụ thuộc OpenAI / Anthropic SDK.",
            highlight_code="class LLMClient(Protocol):\n    def generate(self, messages: Tuple[Message, ...]) -> str:\n        ...",
            position=OverlayPosition.BOTTOM_RIGHT,
        )

    @classmethod
    def build_ovr_s09_unit_test_vs_api(cls) -> OverlayCardState:
        return OverlayCardState(
            overlay_id="OVR_S09_UNIT_TEST_VS_API",
            badge="TESTING POLICY",
            title="Unit Test ≠ Real API",
            body_text="Unit tests dùng FakeLLMClient chạy 100% offline, 0ms network latency, deterministic.",
            highlight_code="FakeLLMClient(responses={'Hello': 'Hi!'})\n# Passes in 0.01s without API Key",
            position=OverlayPosition.BOTTOM_RIGHT,
            is_warning=True,
        )

    @classmethod
    def build_ovr_s10_execution_flow(cls) -> OverlayCardState:
        return OverlayCardState(
            overlay_id="OVR_S10_EXECUTION_FLOW",
            badge="PIPELINE OVERLAY",
            title="Agent.run() Execution Flow",
            body_text='"Hello" → Agent.run() → [System, User Messages] → LLMClient.generate() → "Answer"',
            highlight_code="system_msg = Message(role='system', content=self.config.system_prompt)\nuser_msg = Message(role='user', content=user_input)\nreturn self.llm_client.generate((system_msg, user_msg))",
            position=OverlayPosition.BOTTOM_RIGHT,
        )

    @classmethod
    def build_ovr_s13_api_key_security(cls) -> OverlayCardState:
        return OverlayCardState(
            overlay_id="OVR_S13_API_KEY_SECURITY",
            badge="SECURITY GATE",
            title="API Key Configuration & Redaction",
            body_text="api_key = 'sk-...' ✕ (Placeholder Only). Tuyệt đối không commit raw secret vào repository!",
            highlight_code=".gitignore: add .env\n.env.example: PROVIDER_API_KEY=your_api_key_here",
            position=OverlayPosition.BOTTOM_RIGHT,
            is_security=True,
        )

    @classmethod
    def build_ovr_s19_llm_not_executor(cls) -> OverlayCardState:
        return OverlayCardState(
            overlay_id="OVR_S19_LLM_NOT_EXECUTOR",
            badge="CONCEPT SUMMARY",
            title="LLM ≠ Function Executor",
            body_text="LLM chỉ sinh văn bản. Để chạy code hoặc gọi API, Agent cần Tool Calling runtime (Video 03).",
            highlight_code="Today: LLM generates text\nNext:  LLM emits ToolCall -> Runtime executes",
            position=OverlayPosition.BOTTOM_RIGHT,
            is_warning=True,
        )
