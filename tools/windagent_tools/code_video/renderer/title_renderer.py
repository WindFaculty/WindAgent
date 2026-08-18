"""
Title Card and Feature Checklist Stage Renderer for Code Video Production.

Renders high-impact Title Cards (S02 Hook), Scope Checklists (S16 Not Yet),
and Outro / Next Video Teaser Cards (S19).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import html
from typing import Any, Dict, List, Optional

from workflows.windagent_workflows.code_video.contracts import Action, ActionType


class ChecklistItemStatus(str, Enum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"
    NEXT_EPISODE = "NEXT_EPISODE"
    DONE = "DONE"


@dataclass(frozen=True)
class ChecklistItem:
    text: str
    status: ChecklistItemStatus
    tag: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "status": self.status.value,
            "tag": self.tag,
        }


@dataclass
class TitleCardState:
    """State for full-screen or overlay title card."""
    title: str = "VIẾT AI AGENT ĐẦU TIÊN BẰNG PYTHON"
    subtitle: str = "Tự xây dựng AI Agent từ con số 0 với Clean Architecture"
    badge: str = "VIDEO 02"
    version_tag: str = "Agentic Studio v0.1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "badge": self.badge,
            "version_tag": self.version_tag,
        }

    def render_html(self) -> str:
        return (
            f'<div class="title-card-container">\n'
            f'  <div class="title-badge-row">\n'
            f'    <span class="badge-pill ep-badge">{html.escape(self.badge)}</span>\n'
            f'    <span class="badge-pill ver-badge">{html.escape(self.version_tag)}</span>\n'
            f'  </div>\n'
            f'  <h1 class="title-card-heading">{html.escape(self.title)}</h1>\n'
            f'  <p class="title-card-subheading">{html.escape(self.subtitle)}</p>\n'
            f'</div>'
        )


@dataclass
class ChecklistState:
    """State for feature scope boundary checklist (S16 Not Yet)."""
    title: str = "PHẠM VI TÍNH NĂNG — VIDEO 02"
    subtitle: str = "Những gì ĐÃ LÀM và những gì CHƯA LÀM trong tập này"
    items: List[ChecklistItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "items": [it.to_dict() for it in self.items],
        }

    def render_html(self) -> str:
        rows_html: List[str] = []
        for it in self.items:
            is_inc = it.status in (ChecklistItemStatus.INCLUDED, ChecklistItemStatus.DONE)
            icon = "✓" if is_inc else "✗"
            cls = "item-included" if is_inc else "item-excluded"
            tag_badge = f'<span class="item-tag">{html.escape(it.tag)}</span>' if it.tag else ""
            rows_html.append(
                f'<li class="checklist-row {cls}">'
                f'<span class="check-icon">{icon}</span>'
                f'<span class="check-text">{html.escape(it.text)}</span>'
                f'{tag_badge}'
                f'</li>'
            )

        return (
            f'<div class="checklist-container">\n'
            f'  <h2 class="checklist-heading">{html.escape(self.title)}</h2>\n'
            f'  <p class="checklist-subheading">{html.escape(self.subtitle)}</p>\n'
            f'  <ul class="checklist-items">\n'
            + "\n".join(rows_html) + "\n"
            f'  </ul>\n</div>'
        )


@dataclass
class OutroCardState:
    """State for Outro and Next Episode teaser (S19)."""
    title: str = "TỔNG KẾT & BƯỚC TIẾP THEO"
    current_milestone: str = "v0.1 Simple Agent Released (git tag video-02)"
    next_episode_title: str = "VIDEO 03: TOOL CALLING & FUNCTION RUNTIME"
    next_episode_topics: List[str] = field(
        default_factory=lambda: [
            "Tool Definition Protocol & Schema",
            "Tool Execution Engine & Error Handling",
            "Multi-Turn Tool Calling Loop",
        ]
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "current_milestone": self.current_milestone,
            "next_episode_title": self.next_episode_title,
            "next_episode_topics": list(self.next_episode_topics),
        }

    def render_html(self) -> str:
        topics_html = "".join(f"<li>{html.escape(t)}</li>" for t in self.next_episode_topics)
        return (
            f'<div class="outro-card-container">\n'
            f'  <h2 class="outro-title">{html.escape(self.title)}</h2>\n'
            f'  <div class="milestone-badge">{html.escape(self.current_milestone)}</div>\n'
            f'  <div class="next-ep-box">\n'
            f'    <span class="next-ep-label">TẬP TIẾP THEO:</span>\n'
            f'    <h3 class="next-ep-title">{html.escape(self.next_episode_title)}</h3>\n'
            f'    <ul class="next-ep-list">{topics_html}</ul>\n'
            f'  </div>\n'
            f'</div>'
        )


class TitleRenderer:
    """Renderer and preset factory for title, checklist, and outro stages."""

    @classmethod
    def build_s02_hook_title(cls) -> TitleCardState:
        return TitleCardState(
            title="VIẾT AI AGENT ĐẦU TIÊN BẰNG PYTHON",
            subtitle="Từ con số 0 đến Simple Agent hoàn chỉnh chạy Offline",
            badge="VIDEO 02",
            version_tag="Agentic Studio v0.1",
        )

    @classmethod
    def build_s16_checklist(cls) -> ChecklistState:
        items = [
            ChecklistItem("Message Contract & Invariant Validation", ChecklistItemStatus.INCLUDED, "v0.1 CORE"),
            ChecklistItem("AgentConfig & System Prompt", ChecklistItemStatus.INCLUDED, "v0.1 CORE"),
            ChecklistItem("LLMClient Protocol Abstraction", ChecklistItemStatus.INCLUDED, "v0.1 CORE"),
            ChecklistItem("Deterministic FakeLLM & Unit Tests", ChecklistItemStatus.INCLUDED, "v0.1 TEST"),
            ChecklistItem("Agent Orchestration Run Method", ChecklistItemStatus.INCLUDED, "v0.1 CORE"),
            ChecklistItem("Tool Calling & Function Calling Runtime", ChecklistItemStatus.EXCLUDED, "VIDEO 03"),
            ChecklistItem("Memory & Context Window Management", ChecklistItemStatus.EXCLUDED, "VIDEO 04+"),
            ChecklistItem("Multi-Agent Collaboration & RAG", ChecklistItemStatus.EXCLUDED, "LATER"),
        ]
        return ChecklistState(
            title="TÍNH NĂNG V0.1 — ĐÃ LÀM VÀ CHƯA LÀM",
            subtitle="Ranh giới kiến trúc rõ ràng: Tập trung vào Core Orchestration",
            items=items,
        )

    @classmethod
    def build_s19_outro_card(cls) -> OutroCardState:
        return OutroCardState()

    def __init__(self) -> None:
        self._title_state = self.build_s02_hook_title()
        self._checklist_state = self.build_s16_checklist()
        self._outro_state = self.build_s19_outro_card()

    @property
    def title_state(self) -> TitleCardState:
        return self._title_state

    @property
    def checklist_state(self) -> ChecklistState:
        return self._checklist_state

    @property
    def outro_state(self) -> OutroCardState:
        return self._outro_state

    def apply_action(self, action: Action) -> None:
        params = action.params
        if action.action_type == ActionType.SHOW_TITLE:
            title = str(params.get("title", self._title_state.title))
            subtitle = str(params.get("subtitle", self._title_state.subtitle))
            badge = str(params.get("badge", self._title_state.badge))
            self._title_state = TitleCardState(title=title, subtitle=subtitle, badge=badge)

        elif action.action_type == ActionType.SHOW_CHECKLIST:
            title = str(params.get("title", self._checklist_state.title))
            self._checklist_state = self.build_s16_checklist()
            self._checklist_state.title = title
