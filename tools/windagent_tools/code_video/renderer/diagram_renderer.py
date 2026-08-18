"""
Diagram and Architecture Stage Renderer for Code Video Production (1440p Master).

Generates high-contrast, deterministic SVG visual architecture diagrams
for all canonical video scenes (S01, S03, S04, S08, S10, S11, S12, S17, S19).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import html
import json
from typing import Any, Dict, List, Optional, Tuple

from windagent_workflows.code_video.contracts import Action, ActionType
from windagent_tools.code_video.renderer.theme import CodeVideoVisualTheme


class NodeCategory(str, Enum):
    USER = "user"
    DOMAIN = "domain"
    INFRASTRUCTURE = "infrastructure"
    OUTPUT = "output"
    CONCEPT = "concept"
    DIMMED = "dimmed"


@dataclass(frozen=True)
class DiagramNode:
    id: str
    label: str
    subtext: str = ""
    category: NodeCategory = NodeCategory.DOMAIN
    icon: str = ""
    highlighted: bool = False
    is_dimmed: bool = False
    strike_through: bool = False
    custom_pos: Optional[Tuple[int, int]] = None  # (cx, cy) if explicit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "subtext": self.subtext,
            "category": self.category.value,
            "icon": self.icon,
            "highlighted": self.highlighted,
            "is_dimmed": self.is_dimmed,
            "strike_through": self.strike_through,
            "custom_pos": list(self.custom_pos) if self.custom_pos else None,
        }


@dataclass(frozen=True)
class DiagramEdge:
    source_id: str
    target_id: str
    label: str = ""
    style: str = "solid"  # solid, dashed, animated, dimmed
    strike_through: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "label": self.label,
            "style": self.style,
            "strike_through": self.strike_through,
        }


@dataclass
class DiagramState:
    """State of an architecture or conceptual flow diagram at 2560x1440."""
    diagram_id: str = "DIAG_01_FINAL_ARCH"
    title: str = "Agentic Studio v0.1 Architecture"
    subtitle: str = "User -> Agent -> LLM -> Answer"
    nodes: List[DiagramNode] = field(default_factory=list)
    edges: List[DiagramEdge] = field(default_factory=list)
    highlighted_nodes: List[str] = field(default_factory=list)
    layout_mode: str = "PIPELINE"  # PIPELINE, TWO_TIER, GRID, TODAY_NEXT
    theme: CodeVideoVisualTheme = field(default_factory=CodeVideoVisualTheme)

    def get_source_hash(self) -> str:
        """Computes deterministic SHA-256 hash of semantic diagram contents."""
        data = {
            "diagram_id": self.diagram_id,
            "title": self.title,
            "subtitle": self.subtitle,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "layout_mode": self.layout_mode,
        }
        raw = json.dumps(data, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diagram_id": self.diagram_id,
            "title": self.title,
            "subtitle": self.subtitle,
            "layout_mode": self.layout_mode,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "highlighted_nodes": list(self.highlighted_nodes),
            "source_hash": self.get_source_hash(),
        }

    def render_svg(self, width: int = 2560, height: int = 1440) -> str:
        """Render high-contrast 2560x1440 SVG diagram honoring safe-area insets & typography >= 24px."""
        palette = self.theme.palette
        insets = self.theme.insets
        typo = self.theme.typography

        # Safe area bounds
        left_safe, top_safe, right_safe, bottom_safe = insets.title_safe_box
        safe_w = right_safe - left_safe
        safe_h = bottom_safe - top_safe

        svg_parts: List[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" class="diagram-svg">',
            f'<rect width="100%" height="100%" fill="{palette.canvas_bg}" />',
            # Title & Subtitle inside safe zone
            f'<text x="{width//2}" y="{top_safe + 50}" text-anchor="middle" fill="{palette.primary}" '
            f'font-family="{typo.font_family_sans}" font-size="{typo.hero_title_font_px}" font-weight="800">'
            f'{html.escape(self.title)}</text>',
            f'<text x="{width//2}" y="{top_safe + 110}" text-anchor="middle" fill="{palette.text_muted}" '
            f'font-family="{typo.font_family_sans}" font-size="{typo.table_item_font_px}" font-weight="500">'
            f'{html.escape(self.subtitle)}</text>',
        ]

        node_coords: Dict[str, Tuple[int, int]] = {}
        node_width = 360
        node_height = 180
        y_center = (top_safe + bottom_safe) // 2 + 30

        # Layout computation
        if self.layout_mode == "PIPELINE":
            node_count = max(1, len(self.nodes))
            spacing = safe_w // (node_count + 1)
            for idx, node in enumerate(self.nodes):
                if node.custom_pos:
                    node_coords[node.id] = node.custom_pos
                else:
                    cx = left_safe + spacing * (idx + 1)
                    cy = y_center
                    node_coords[node.id] = (cx, cy)

        elif self.layout_mode == "TWO_TIER":
            domain_nodes = [n for n in self.nodes if n.category != NodeCategory.INFRASTRUCTURE]
            infra_nodes = [n for n in self.nodes if n.category == NodeCategory.INFRASTRUCTURE]

            # Domain row (top)
            d_spacing = safe_w // (max(1, len(domain_nodes)) + 1)
            for idx, node in enumerate(domain_nodes):
                node_coords[node.id] = (left_safe + d_spacing * (idx + 1), y_center - 180)

            # Infra row (bottom)
            i_spacing = safe_w // (max(1, len(infra_nodes)) + 1)
            for idx, node in enumerate(infra_nodes):
                node_coords[node.id] = (left_safe + i_spacing * (idx + 1), y_center + 180)

            # Draw tier separator line
            sep_y = y_center
            svg_parts.append(
                f'<line x1="{left_safe + 60}" y1="{sep_y}" x2="{right_safe - 60}" y2="{sep_y}" '
                f'stroke="{palette.card_border}" stroke-width="2" stroke-dasharray="8,8" />'
            )
            svg_parts.append(
                f'<text x="{left_safe + 80}" y="{sep_y - 15}" fill="{palette.primary}" '
                f'font-family="{typo.font_family_mono}" font-size="{typo.minimum_body_font_px}" font-weight="700">DOMAIN LAYER</text>'
            )
            svg_parts.append(
                f'<text x="{left_safe + 80}" y="{sep_y + 35}" fill="{palette.warning}" '
                f'font-family="{typo.font_family_mono}" font-size="{typo.minimum_body_font_px}" font-weight="700">INFRASTRUCTURE LAYER</text>'
            )

        elif self.layout_mode == "GRID":
            cols = 2
            rows = (len(self.nodes) + cols - 1) // cols
            col_w = safe_w // (cols + 1)
            row_h = (safe_h - 180) // (rows + 1)
            for idx, node in enumerate(self.nodes):
                r = idx // cols
                c = idx % cols
                cx = left_safe + col_w * (c + 1)
                cy = top_safe + 200 + row_h * (r + 1)
                node_coords[node.id] = (cx, cy)

        else:
            node_count = max(1, len(self.nodes))
            spacing = safe_w // (node_count + 1)
            for idx, node in enumerate(self.nodes):
                node_coords[node.id] = (left_safe + spacing * (idx + 1), y_center)

        # Render edges
        for edge in self.edges:
            if edge.source_id in node_coords and edge.target_id in node_coords:
                sx, sy = node_coords[edge.source_id]
                tx, ty = node_coords[edge.target_id]

                # Adjust edge start/end to node boundaries
                if abs(tx - sx) > abs(ty - sy):
                    x1 = sx + (node_width // 2 if tx > sx else -node_width // 2)
                    y1 = sy
                    x2 = tx - (node_width // 2 if tx > sx else -node_width // 2)
                    y2 = ty
                else:
                    x1 = sx
                    y1 = sy + (node_height // 2 if ty > sy else -node_height // 2)
                    x2 = tx
                    y2 = ty - (node_height // 2 if ty > sy else -node_height // 2)

                stroke_color = palette.dimmed_inactive if edge.style == "dimmed" else (
                    palette.primary if edge.style == "animated" else palette.card_border
                )
                stroke_dash = 'stroke-dasharray="8,8"' if edge.style == "dashed" else ""

                svg_parts.append(
                    f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke_color}" '
                    f'stroke-width="4" {stroke_dash} />'
                )
                if edge.label:
                    mid_x = (x1 + x2) // 2
                    mid_y = (y1 + y2) // 2 - 16
                    svg_parts.append(
                        f'<text x="{mid_x}" y="{mid_y}" text-anchor="middle" fill="{palette.text_muted}" '
                        f'font-family="{typo.font_family_sans}" font-size="{typo.minimum_body_font_px}" font-weight="600">{html.escape(edge.label)}</text>'
                    )

        # Render nodes
        for node in self.nodes:
            cx, cy = node_coords[node.id]
            rx = cx - node_width // 2
            ry = cy - node_height // 2

            is_hl = node.highlighted or (node.id in self.highlighted_nodes)
            is_dim = node.is_dimmed or node.category == NodeCategory.DIMMED

            if is_dim:
                border_color = palette.dimmed_inactive
                fill_color = "rgba(22, 27, 34, 0.4)"
                text_color = palette.dimmed_text
                glow = ""
            elif is_hl:
                border_color = palette.card_border_active
                fill_color = palette.card_bg_active
                text_color = palette.text_primary
                glow = 'filter="drop-shadow(0 0 20px rgba(88,166,255,0.6))"'
            else:
                border_color = palette.card_border
                fill_color = palette.card_bg
                text_color = palette.text_secondary
                glow = ""

            cat_colors = {
                NodeCategory.USER: palette.success,
                NodeCategory.DOMAIN: palette.primary,
                NodeCategory.INFRASTRUCTURE: palette.warning,
                NodeCategory.OUTPUT: palette.output,
                NodeCategory.CONCEPT: palette.concept,
                NodeCategory.DIMMED: palette.dimmed_text,
            }
            badge_color = cat_colors.get(node.category, palette.primary)
            if is_dim:
                badge_color = palette.dimmed_text

            svg_parts.append(f'<g class="diagram-node" id="node_{node.id}" {glow}>')
            # Box
            svg_parts.append(
                f'<rect x="{rx}" y="{ry}" width="{node_width}" height="{node_height}" '
                f'rx="16" fill="{fill_color}" stroke="{border_color}" stroke-width="3" />'
            )
            # Category pill
            svg_parts.append(
                f'<rect x="{rx+16}" y="{ry+16}" width="140" height="32" rx="6" fill="{badge_color}22" stroke="{badge_color}44" stroke-width="1" />'
                f'<text x="{rx+86}" y="{ry+38}" text-anchor="middle" fill="{badge_color}" '
                f'font-family="{typo.font_family_mono}" font-size="{typo.badge_font_px}" font-weight="700">{node.category.value.upper()}</text>'
            )
            # Label
            svg_parts.append(
                f'<text x="{cx}" y="{cy+14}" text-anchor="middle" fill="{text_color}" '
                f'font-family="{typo.font_family_sans}" font-size="{typo.table_item_font_px}" font-weight="bold">{html.escape(node.label)}</text>'
            )
            # Subtext
            if node.subtext:
                svg_parts.append(
                    f'<text x="{cx}" y="{cy+52}" text-anchor="middle" fill="{palette.text_muted if not is_dim else palette.dimmed_text}" '
                    f'font-family="{typo.font_family_sans}" font-size="{typo.minimum_body_font_px}">{html.escape(node.subtext)}</text>'
                )
            # Strike-through if missing in v0.1
            if node.strike_through:
                svg_parts.append(
                    f'<line x1="{rx+30}" y1="{cy}" x2="{rx+node_width-30}" y2="{cy}" stroke="{palette.danger}" stroke-width="4" />'
                )
            svg_parts.append('</g>')

        svg_parts.append('</svg>')
        return "\n".join(svg_parts)


class DiagramRenderer:
    """Renderer and builder for all 8 required/optional architecture and flow diagrams."""

    def __init__(self, initial_state: Optional[DiagramState] = None) -> None:
        self._state = initial_state or self.build_diag_01_final_arch()

    @property
    def state(self) -> DiagramState:
        return self._state

    @classmethod
    def build_diag_01_final_arch(cls) -> DiagramState:
        """DIAG_01: Core v0.1 architecture (User -> Agent -> LLM -> Answer)."""
        nodes = [
            DiagramNode("N_USER", "User", "Prompt / Input", NodeCategory.USER),
            DiagramNode("N_AGENT", "Agent", "Orchestrator Core", NodeCategory.DOMAIN, highlighted=True),
            DiagramNode("N_LLM", "LLMClient", "Domain Protocol", NodeCategory.DOMAIN),
            DiagramNode("N_ANSWER", "Answer", "Final String Output", NodeCategory.OUTPUT),
        ]
        edges = [
            DiagramEdge("N_USER", "N_AGENT", "query", style="animated"),
            DiagramEdge("N_AGENT", "N_LLM", "generate"),
            DiagramEdge("N_LLM", "N_ANSWER", "response", style="animated"),
        ]
        return DiagramState(
            diagram_id="DIAG_01_FINAL_ARCH",
            title="Agentic Studio v0.1 Architecture",
            subtitle="User -> Agent -> LLM -> Answer (Zero Tool Calling)",
            nodes=nodes,
            edges=edges,
            layout_mode="PIPELINE",
        )

    @classmethod
    def build_diag_02_component_flow(cls) -> DiagramState:
        """DIAG_02: Component dependency and configuration flow."""
        nodes = [
            DiagramNode("N_CONFIG", "AgentConfig", "name, prompt, model", NodeCategory.DOMAIN),
            DiagramNode("N_AGENT_CORE", "Agent", "run(user_input)", NodeCategory.DOMAIN, highlighted=True),
            DiagramNode("N_LLM_CLIENT", "LLMClient", "generate(messages)", NodeCategory.DOMAIN),
            DiagramNode("N_PROVIDER", "Provider Adapter", "OpenAI / FakeLLM", NodeCategory.INFRASTRUCTURE),
        ]
        edges = [
            DiagramEdge("N_CONFIG", "N_AGENT_CORE", "configures"),
            DiagramEdge("N_AGENT_CORE", "N_LLM_CLIENT", "delegates"),
            DiagramEdge("N_LLM_CLIENT", "N_PROVIDER", "calls"),
        ]
        return DiagramState(
            diagram_id="DIAG_02_COMPONENT_FLOW",
            title="Agentic Studio Component Flow",
            subtitle="AgentConfig -> Agent -> LLMClient -> Provider",
            nodes=nodes,
            edges=edges,
            layout_mode="PIPELINE",
        )

    @classmethod
    def build_diag_03_today_vs_next(cls) -> DiagramState:
        """DIAG_03: TODAY vs NEXT teaser comparison."""
        nodes = [
            DiagramNode("T_TODAY", "TODAY (Video 02)", "User -> Agent -> LLM -> Answer", NodeCategory.DOMAIN, highlighted=True),
            DiagramNode("T_NEXT", "NEXT (Video 03)", "User -> Agent -> LLM -> Tool Execution", NodeCategory.OUTPUT),
        ]
        edges = [
            DiagramEdge("T_TODAY", "T_NEXT", "evolves to", style="animated"),
        ]
        return DiagramState(
            diagram_id="DIAG_03_TODAY_VS_NEXT",
            title="Today (Simple Agent) vs Next (Tool Calling)",
            subtitle="From Static LLM Responses to Dynamic Tool Orchestration",
            nodes=nodes,
            edges=edges,
            layout_mode="PIPELINE",
        )

    @classmethod
    def build_diag_04_llmclient_abstraction(cls) -> DiagramState:
        """DIAG_04: LLMClient Protocol multi-provider decoupling."""
        nodes = [
            DiagramNode("D_AGENT", "Agent Core", "Independent of SDKs", NodeCategory.DOMAIN, highlighted=True),
            DiagramNode("D_CLIENT", "LLMClient Protocol", "generate() Interface", NodeCategory.DOMAIN),
            DiagramNode("I_OPENAI", "OpenAI Provider", "Real API (Preflight)", NodeCategory.INFRASTRUCTURE),
            DiagramNode("I_FAKE", "FakeLLMClient", "Deterministic Offline", NodeCategory.INFRASTRUCTURE),
        ]
        edges = [
            DiagramEdge("D_AGENT", "D_CLIENT", "depends on"),
            DiagramEdge("D_CLIENT", "I_OPENAI", "implements", style="dashed"),
            DiagramEdge("D_CLIENT", "I_FAKE", "implements", style="dashed"),
        ]
        return DiagramState(
            diagram_id="DIAG_04_LLMCLIENT_ABSTRACTION",
            title="LLMClient Protocol Decoupling",
            subtitle="Agent depends only on Protocol — never on concrete SDKs",
            nodes=nodes,
            edges=edges,
            layout_mode="TWO_TIER",
        )

    @classmethod
    def build_diag_05a_cognitive_loop(cls) -> DiagramState:
        """DIAG_05A: Canonical Cognitive Loop (Observe -> Decide -> Act -> Observe)."""
        nodes = [
            DiagramNode("L_OBSERVE", "Observe", "Receive Environment State", NodeCategory.CONCEPT),
            DiagramNode("L_DECIDE", "Decide", "LLM Reasoning / Policy", NodeCategory.DOMAIN, highlighted=True),
            DiagramNode("L_ACT", "Act", "Execute Tool / Action", NodeCategory.CONCEPT),
            DiagramNode("L_FEEDBACK", "Observe Loop", "Evaluate Results", NodeCategory.CONCEPT),
        ]
        edges = [
            DiagramEdge("L_OBSERVE", "L_DECIDE", "perceives"),
            DiagramEdge("L_DECIDE", "L_ACT", "commands"),
            DiagramEdge("L_ACT", "L_FEEDBACK", "yields"),
            DiagramEdge("L_FEEDBACK", "L_OBSERVE", "loops", style="dashed"),
        ]
        return DiagramState(
            diagram_id="DIAG_05A_COGNITIVE_LOOP",
            title="The Canonical Cognitive Loop",
            subtitle="Observe -> Decide -> Act -> Observe (Standard Agent Loop)",
            nodes=nodes,
            edges=edges,
            layout_mode="PIPELINE",
        )

    @classmethod
    def build_diag_05b_missing_capabilities(cls) -> DiagramState:
        """DIAG_05B: Is This An Agent? — Scope Gap & Missing Capabilities."""
        nodes = [
            DiagramNode("G_INPUT", "User Input", "Single Turn Prompt", NodeCategory.USER),
            DiagramNode("G_DECIDE", "LLM Generate", "One-Shot Completion", NodeCategory.DOMAIN, highlighted=True),
            DiagramNode("G_TOOL", "Tool Calling", "NOT in v0.1 (Video 03)", NodeCategory.DIMMED, is_dimmed=True, strike_through=True),
            DiagramNode("G_LOOP", "Multi-Turn Loop", "NOT in v0.1 (Video 03+)", NodeCategory.DIMMED, is_dimmed=True, strike_through=True),
        ]
        edges = [
            DiagramEdge("G_INPUT", "G_DECIDE", "query", style="animated"),
            DiagramEdge("G_DECIDE", "G_TOOL", "cannot call", style="dimmed", strike_through=True),
            DiagramEdge("G_TOOL", "G_LOOP", "cannot loop", style="dimmed", strike_through=True),
        ]
        return DiagramState(
            diagram_id="DIAG_05B_MISSING_CAPABILITIES",
            title="Is This An Agent? — v0.1 Scope Analysis",
            subtitle="v0.1 is a Single-Turn Orchestrator (Tool Calling & Loop are in Video 03)",
            nodes=nodes,
            edges=edges,
            layout_mode="PIPELINE",
        )

    @classmethod
    def build_diag_06_domain_vs_infra(cls) -> DiagramState:
        """DIAG_06: Clean Architecture Domain vs Infrastructure Isolation."""
        nodes = [
            DiagramNode("DM_AGENT", "Agent Core", "src/agent.py (Domain)", NodeCategory.DOMAIN, highlighted=True),
            DiagramNode("DM_MODELS", "Message / Config", "Frozen Dataclasses", NodeCategory.DOMAIN),
            DiagramNode("IF_SDK", "Provider SDK", "openai / anthropic", NodeCategory.INFRASTRUCTURE),
            DiagramNode("IF_ENV", "API Key / Config", ".env / Environment", NodeCategory.INFRASTRUCTURE),
        ]
        edges = [
            DiagramEdge("DM_AGENT", "DM_MODELS", "uses"),
            DiagramEdge("IF_SDK", "DM_AGENT", "cannot leak into", style="dashed", strike_through=True),
            DiagramEdge("IF_ENV", "IF_SDK", "loads"),
        ]
        return DiagramState(
            diagram_id="DIAG_06_DOMAIN_VS_INFRA",
            title="Clean Architecture Isolation",
            subtitle="Domain Core never depends on external SDKs or API Keys",
            nodes=nodes,
            edges=edges,
            layout_mode="TWO_TIER",
        )

    @classmethod
    def build_diag_07_recap(cls) -> DiagramState:
        """DIAG_07: Optional context recap (Prompt -> Chaining -> Agent Architecture)."""
        nodes = [
            DiagramNode("R_PROMPT", "Prompt Engineering", "Static & One-Shot", NodeCategory.CONCEPT),
            DiagramNode("R_CHAIN", "Chaining", "Linear Execution", NodeCategory.CONCEPT),
            DiagramNode("R_AGENT", "Agent Architecture", "Autonomous Decision", NodeCategory.DOMAIN, highlighted=True),
        ]
        edges = [
            DiagramEdge("R_PROMPT", "R_CHAIN", "evolves to"),
            DiagramEdge("R_CHAIN", "R_AGENT", "evolves to"),
        ]
        return DiagramState(
            diagram_id="DIAG_07_RECAP",
            title="Video 01 Recap — Foundations",
            subtitle="From Static Prompts to Autonomous Agent Systems",
            nodes=nodes,
            edges=edges,
            layout_mode="PIPELINE",
        )

    @classmethod
    def build_diag_08_execution_flow(cls) -> DiagramState:
        """DIAG_08: Agent runtime step-by-step execution flow."""
        nodes = [
            DiagramNode("E_PROMPT", '"Hello"', "User Input", NodeCategory.USER),
            DiagramNode("E_RUN", "Agent.run()", "Packets Messages", NodeCategory.DOMAIN, highlighted=True),
            DiagramNode("E_MSGS", "[System, User]", "Immutable Tuple", NodeCategory.DOMAIN),
            DiagramNode("E_GEN", "LLM.generate()", "Call Protocol", NodeCategory.DOMAIN),
            DiagramNode("E_OUT", '"Answer"', "Domain Response", NodeCategory.OUTPUT),
        ]
        edges = [
            DiagramEdge("E_PROMPT", "E_RUN", "input"),
            DiagramEdge("E_RUN", "E_MSGS", "creates"),
            DiagramEdge("E_MSGS", "E_GEN", "passes"),
            DiagramEdge("E_GEN", "E_OUT", "returns", style="animated"),
        ]
        return DiagramState(
            diagram_id="DIAG_08_EXECUTION_FLOW",
            title="Agent.run() Execution Flow",
            subtitle='"Hello" -> Agent.run() -> [system, user] -> LLMClient.generate() -> "Answer"',
            nodes=nodes,
            edges=edges,
            layout_mode="PIPELINE",
        )

    build_s03_recap_diagram = build_diag_07_recap
    build_s04_arch_v01_diagram = build_diag_01_final_arch
    build_s11_concept_diagram = build_diag_05b_missing_capabilities
    build_s17_review_diagram = build_diag_06_domain_vs_infra

    def set_diagram(self, diagram_id: str) -> DiagramState:
        builders = {
            "DIAG_01_FINAL_ARCH": self.build_diag_01_final_arch,
            "S04_ARCH_V0_1": self.build_diag_01_final_arch,
            "DIAG_02_COMPONENT_FLOW": self.build_diag_02_component_flow,
            "DIAG_03_TODAY_VS_NEXT": self.build_diag_03_today_vs_next,
            "DIAG_04_LLMCLIENT_ABSTRACTION": self.build_diag_04_llmclient_abstraction,
            "DIAG_05A_COGNITIVE_LOOP": self.build_diag_05a_cognitive_loop,
            "DIAG_05B_MISSING_CAPABILITIES": self.build_diag_05b_missing_capabilities,
            "S11_IS_THIS_AGENT": self.build_diag_05b_missing_capabilities,
            "DIAG_06_DOMAIN_VS_INFRA": self.build_diag_06_domain_vs_infra,
            "S17_ARCH_REVIEW": self.build_diag_06_domain_vs_infra,
            "DIAG_07_RECAP": self.build_diag_07_recap,
            "S03_RECAP": self.build_diag_07_recap,
            "DIAG_08_EXECUTION_FLOW": self.build_diag_08_execution_flow,
        }
        if diagram_id in builders:
            self._state = builders[diagram_id]()
            if diagram_id in ("S17_ARCH_REVIEW", "S04_ARCH_V0_1", "S03_RECAP", "S11_IS_THIS_AGENT"):
                self._state.diagram_id = diagram_id
        return self._state

    def highlight_node(self, node_id: str) -> DiagramState:
        if node_id not in self._state.highlighted_nodes:
            self._state.highlighted_nodes.append(node_id)
        return self._state

    def clear_highlights(self) -> DiagramState:
        self._state.highlighted_nodes = []
        return self._state

    def apply_action(self, action: Action) -> DiagramState:
        params = action.params
        if action.action_type in (ActionType.SHOW_DIAGRAM, ActionType.SHOW_ARCHITECTURE):
            diag_id = str(params.get("diagram_id", params.get("id", "")))
            if diag_id:
                self.set_diagram(diag_id)
            hl = params.get("highlight")
            if hl:
                self.highlight_node(str(hl))
        elif action.action_type == ActionType.RESET_VIEW:
            self.clear_highlights()
        return self._state
