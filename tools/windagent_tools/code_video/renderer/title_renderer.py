"""
Title Card and Feature Checklist Stage Renderer for Code Video Production (1440p Master).

Renders high-impact Title Cards (S02 Hook, S18 Milestone), Scope Checklists (S16 Not Yet),
and Outro / Next Video Teaser Cards (S19).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import html
import json
from typing import Any, Dict, List

from windagent_core.contracts.code_video import Action, ActionType
from windagent_tools.code_video.renderer.theme import CodeVideoVisualTheme


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
    """State for full-screen title card at 2560x1440."""
    card_id: str = "CARD_S02_HOOK"
    title: str = "VIẾT AI AGENT ĐẦU TIÊN BẰNG PYTHON"
    subtitle: str = "Tự xây dựng AI Agent từ con số 0 với Clean Architecture"
    badge: str = "VIDEO 02"
    version_tag: str = "Agentic Studio v0.1"
    theme: CodeVideoVisualTheme = field(default_factory=CodeVideoVisualTheme)

    def get_source_hash(self) -> str:
        data = {
            "card_id": self.card_id,
            "title": self.title,
            "subtitle": self.subtitle,
            "badge": self.badge,
            "version_tag": self.version_tag,
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "card_id": self.card_id,
            "title": self.title,
            "subtitle": self.subtitle,
            "badge": self.badge,
            "version_tag": self.version_tag,
            "source_hash": self.get_source_hash(),
        }

    def render_html(self) -> str:
        palette = self.theme.palette
        insets = self.theme.insets
        typo = self.theme.typography

        return (
            f'<div class="title-card-container" style="'
            f'width: 2560px; height: 1440px; background: {palette.canvas_bg}; '
            f'display: flex; flex-direction: column; align-items: center; justify-content: center; '
            f'padding: {insets.title_safe_dy}px {insets.title_safe_dx}px; box-sizing: border-box; '
            f'font-family: {typo.font_family_sans}; text-align: center;">\n'
            f'  <div class="title-badge-row" style="display: flex; gap: 16px; margin-bottom: 32px;">\n'
            f'    <span class="badge-pill ep-badge" style="background: rgba(88,166,255,0.15); color: {palette.primary}; '
            f'      border: 1px solid {palette.primary}; padding: 8px 24px; border-radius: 8px; font-size: {typo.badge_font_px}px; '
            f'      font-weight: 700; font-family: {typo.font_family_mono};">{html.escape(self.badge)}</span>\n'
            f'    <span class="badge-pill ver-badge" style="background: rgba(126,231,135,0.15); color: {palette.success}; '
            f'      border: 1px solid {palette.success}; padding: 8px 24px; border-radius: 8px; font-size: {typo.badge_font_px}px; '
            f'      font-weight: 700; font-family: {typo.font_family_mono};">{html.escape(self.version_tag)}</span>\n'
            f'  </div>\n'
            f'  <h1 class="title-card-heading" style="color: {palette.text_primary}; font-size: {typo.hero_title_font_px}px; '
            f'    font-weight: 800; line-height: 1.2; margin: 0 0 24px 0; max-width: 1800px;">{html.escape(self.title)}</h1>\n'
            f'  <p class="title-card-subheading" style="color: {palette.text_muted}; font-size: {typo.card_title_font_px}px; '
            f'    font-weight: 500; margin: 0; max-width: 1600px;">{html.escape(self.subtitle)}</p>\n'
            f'</div>'
        )


@dataclass
class ChecklistState:
    """State for feature scope boundary checklist (S16 Not Yet). Strictly 7 excluded items."""
    checklist_id: str = "CHECKLIST_S16_NOT_YET"
    title: str = "PHẠM VI TÍNH NĂNG — CHƯA CÓ TRONG TẬP NÀY (NOT YET)"
    subtitle: str = "Ranh giới kiến trúc rõ ràng: Tập trung vào Simple Agent Core"
    items: List[ChecklistItem] = field(default_factory=list)
    theme: CodeVideoVisualTheme = field(default_factory=CodeVideoVisualTheme)

    def get_source_hash(self) -> str:
        data = {
            "checklist_id": self.checklist_id,
            "title": self.title,
            "subtitle": self.subtitle,
            "items": [it.to_dict() for it in self.items],
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checklist_id": self.checklist_id,
            "title": self.title,
            "subtitle": self.subtitle,
            "items": [it.to_dict() for it in self.items],
            "source_hash": self.get_source_hash(),
        }

    def render_html(self) -> str:
        palette = self.theme.palette
        insets = self.theme.insets
        typo = self.theme.typography

        rows_html: List[str] = []
        for it in self.items:
            is_inc = it.status in (ChecklistItemStatus.INCLUDED, ChecklistItemStatus.DONE)
            icon = "✓" if is_inc else "✕"
            icon_color = palette.success if is_inc else palette.danger
            row_bg = "rgba(22, 27, 34, 0.8)"
            tag_badge = (
                f'<span class="item-tag" style="background: rgba(248,81,73,0.15); color: {palette.danger}; '
                f'border: 1px solid {palette.danger}44; padding: 4px 16px; border-radius: 6px; '
                f'font-size: {typo.badge_font_px}px; font-family: {typo.font_family_mono}; font-weight: 700;">{html.escape(it.tag)}</span>'
            ) if it.tag else ""

            rows_html.append(
                f'<li class="checklist-row" style="background: {row_bg}; border: 1px solid {palette.card_border}; '
                f'  border-radius: 12px; padding: 16px 28px; display: flex; align-items: center; justify-content: space-between; '
                f'  margin-bottom: 12px; list-style: none;">\n'
                f'  <div style="display: flex; align-items: center; gap: 20px;">\n'
                f'    <span class="check-icon" style="color: {icon_color}; font-size: {typo.table_item_font_px}px; font-weight: 900; width: 36px;">{icon}</span>\n'
                f'    <span class="check-text" style="color: {palette.text_primary}; font-size: {typo.table_item_font_px}px; font-weight: 600;">{html.escape(it.text)}</span>\n'
                f'  </div>\n'
                f'  {tag_badge}\n'
                f'</li>'
            )

        return (
            f'<div class="checklist-container" style="'
            f'width: 2560px; height: 1440px; background: {palette.canvas_bg}; '
            f'display: flex; flex-direction: column; justify-content: center; align-items: center; '
            f'padding: {insets.title_safe_dy}px {insets.title_safe_dx}px; box-sizing: border-box; '
            f'font-family: {typo.font_family_sans};">\n'
            f'  <h2 class="checklist-heading" style="color: {palette.danger}; font-size: {typo.section_heading_font_px}px; '
            f'    font-weight: 800; margin: 0 0 12px 0; text-align: center;">{html.escape(self.title)}</h2>\n'
            f'  <p class="checklist-subheading" style="color: {palette.text_muted}; font-size: {typo.body_font_px}px; '
            f'    font-weight: 500; margin: 0 0 36px 0; text-align: center;">{html.escape(self.subtitle)}</p>\n'
            f'  <ul class="checklist-items" style="width: 1400px; padding: 0; margin: 0;">\n'
            + "\n".join(rows_html) + "\n"
            '  </ul>\n</div>'
        )


@dataclass
class OutroCardState:
    """State for Outro and Next Episode teaser (S19)."""
    card_id: str = "CARD_S19_TEASER"
    title: str = "TỔNG KẾT & TẬP TIẾP THEO"
    current_milestone: str = "v0.1 Simple Agent Released (git tag video-02 / v0.1)"
    next_episode_title: str = "VIDEO 03: TOOL CALLING"
    next_episode_subtitle: str = "TOOL CALLING HOẠT ĐỘNG BÊN TRONG NHƯ THẾ NÀO?"
    next_episode_topics: List[str] = field(
        default_factory=lambda: [
            "Tool Definition Protocol & Schema Validation",
            "Tool Execution Engine & Error Handling",
            "Multi-Turn Tool Calling Orchestration Loop",
        ]
    )
    theme: CodeVideoVisualTheme = field(default_factory=CodeVideoVisualTheme)

    def get_source_hash(self) -> str:
        data = {
            "card_id": self.card_id,
            "title": self.title,
            "current_milestone": self.current_milestone,
            "next_episode_title": self.next_episode_title,
            "next_episode_subtitle": self.next_episode_subtitle,
            "next_episode_topics": list(self.next_episode_topics),
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "card_id": self.card_id,
            "title": self.title,
            "current_milestone": self.current_milestone,
            "next_episode_title": self.next_episode_title,
            "next_episode_subtitle": self.next_episode_subtitle,
            "next_episode_topics": list(self.next_episode_topics),
            "source_hash": self.get_source_hash(),
        }

    def render_html(self) -> str:
        palette = self.theme.palette
        insets = self.theme.insets
        typo = self.theme.typography

        topics_html = "".join(
            f'<li style="color: {palette.text_secondary}; font-size: {typo.body_font_px}px; font-weight: 500; margin-bottom: 12px;">{html.escape(t)}</li>'
            for t in self.next_episode_topics
        )

        return (
            f'<div class="outro-card-container" style="'
            f'width: 2560px; height: 1440px; background: {palette.canvas_bg}; '
            f'display: flex; flex-direction: column; align-items: center; justify-content: center; '
            f'padding: {insets.title_safe_dy}px {insets.title_safe_dx}px; box-sizing: border-box; '
            f'font-family: {typo.font_family_sans}; text-align: center;">\n'
            f'  <div class="milestone-badge" style="background: rgba(126,231,135,0.15); color: {palette.success}; '
            f'    border: 1px solid {palette.success}; padding: 10px 32px; border-radius: 8px; '
            f'    font-size: {typo.badge_font_px}px; font-weight: 700; font-family: {typo.font_family_mono}; margin-bottom: 24px;">'
            f'{html.escape(self.current_milestone)}</div>\n'
            f'  <h2 class="outro-title" style="color: {palette.primary}; font-size: {typo.hero_title_font_px}px; '
            f'    font-weight: 800; margin: 0 0 32px 0;">{html.escape(self.title)}</h2>\n'
            f'  <div class="next-ep-box" style="background: {palette.card_bg}; border: 2px solid {palette.card_border_active}; '
            f'    border-radius: 16px; padding: 36px 48px; max-width: 1400px; width: 100%; box-shadow: 0 0 32px rgba(88,166,255,0.15); '
            f'    box-sizing: border-box; text-align: left;">\n'
            f'    <span class="next-ep-label" style="background: rgba(88,166,255,0.2); color: {palette.primary}; '
            f'      padding: 6px 16px; border-radius: 6px; font-size: {typo.badge_font_px}px; font-weight: 700; font-family: {typo.font_family_mono};">TẬP TIẾP THEO:</span>\n'
            f'    <h3 class="next-ep-title" style="color: {palette.text_primary}; font-size: {typo.section_heading_font_px}px; '
            f'      font-weight: 800; margin: 16px 0 8px 0;">{html.escape(self.next_episode_title)}</h3>\n'
            f'    <p style="color: {palette.text_muted}; font-size: {typo.body_font_px}px; margin: 0 0 20px 0;">{html.escape(self.next_episode_subtitle)}</p>\n'
            f'    <ul class="next-ep-list" style="padding-left: 28px; margin: 0;">{topics_html}</ul>\n'
            f'  </div>\n'
            f'</div>'
        )


class TitleRenderer:
    """Renderer and preset factory for title, checklist, and outro stages."""

    @classmethod
    def build_s02_hook_title(cls) -> TitleCardState:
        return TitleCardState(
            card_id="CARD_S02_HOOK",
            title="VIẾT AI AGENT ĐẦU TIÊN BẰNG PYTHON",
            subtitle="Từ con số 0 đến Simple Agent hoàn chỉnh chạy Offline",
            badge="VIDEO 02",
            version_tag="Agentic Studio v0.1",
        )

    @classmethod
    def build_s18_git_milestone(cls) -> TitleCardState:
        return TitleCardState(
            card_id="CARD_S18_MILESTONE",
            title="Agentic Studio v0.1",
            subtitle="Simple Agent Core Released — git tag video-02 & v0.1",
            badge="GIT MILESTONE",
            version_tag="v0.1 RELEASED",
        )

    @classmethod
    def build_s16_checklist(cls) -> ChecklistState:
        """Strictly the 7 excluded items from the script authority."""
        items = [
            ChecklistItem("Tool Calling", ChecklistItemStatus.EXCLUDED, "VIDEO 03"),
            ChecklistItem("Agent Loop", ChecklistItemStatus.EXCLUDED, "VIDEO 03"),
            ChecklistItem("Memory", ChecklistItemStatus.EXCLUDED, "VIDEO 04+"),
            ChecklistItem("RAG", ChecklistItemStatus.EXCLUDED, "LATER"),
            ChecklistItem("Planning", ChecklistItemStatus.EXCLUDED, "LATER"),
            ChecklistItem("Multi-Agent", ChecklistItemStatus.EXCLUDED, "LATER"),
            ChecklistItem("Orchestration", ChecklistItemStatus.EXCLUDED, "LATER"),
        ]
        return ChecklistState(
            checklist_id="CHECKLIST_S16_NOT_YET",
            title="PHẠM VI TÍNH NĂNG — CHƯA CÓ TRONG TẬP NÀY (NOT YET)",
            subtitle="Ranh giới kiến trúc rõ ràng: Tập trung vào Simple Agent Core",
            items=items,
        )

    @classmethod
    def build_s19_outro_card(cls) -> OutroCardState:
        return OutroCardState()

    def __init__(self) -> None:
        self._hook_title = self.build_s02_hook_title()
        self._milestone_title = self.build_s18_git_milestone()
        self._checklist_state = self.build_s16_checklist()
        self._outro_state = self.build_s19_outro_card()
        self._active_card: TitleCardState = self._hook_title

    @property
    def title_state(self) -> TitleCardState:
        return self._active_card

    @property
    def checklist_state(self) -> ChecklistState:
        return self._checklist_state

    @property
    def outro_state(self) -> OutroCardState:
        return self._outro_state

    def set_card(self, card_id: str) -> None:
        if card_id in ("CARD_S02_HOOK", "S02_HOOK"):
            self._active_card = self._hook_title
        elif card_id in ("CARD_S18_MILESTONE", "S18_MILESTONE"):
            self._active_card = self._milestone_title

    def apply_action(self, action: Action) -> None:
        params = action.params
        if action.action_type == ActionType.SHOW_TITLE:
            card_id = params.get("card_id", params.get("id"))
            if card_id:
                self.set_card(str(card_id))
            else:
                title = str(params.get("title", self._active_card.title))
                subtitle = str(params.get("subtitle", self._active_card.subtitle))
                badge = str(params.get("badge", self._active_card.badge))
                ver = str(params.get("version_tag", self._active_card.version_tag))
                self._active_card = TitleCardState(
                    card_id="CUSTOM_CARD",
                    title=title,
                    subtitle=subtitle,
                    badge=badge,
                    version_tag=ver,
                )
        elif action.action_type == ActionType.SHOW_CHECKLIST:
            pass  # Checklist state is rendered via checklist_state
