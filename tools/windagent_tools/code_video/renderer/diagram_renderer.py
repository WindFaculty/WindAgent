"""
Diagram and Architecture Stage Renderer for Code Video Production.

Generates high-contrast, deterministic SVG and HTML visual architecture diagrams
for scenes S03 (Recap), S04 (v0.1 Arch), S11 (Concept Deep Dive), and S17 (Arch Review).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import html
from typing import Any, Dict, List, Optional

from windagent_workflows.code_video.contracts import Action, ActionType


class NodeCategory(str, Enum):
    USER = "user"
    DOMAIN = "domain"
    INFRASTRUCTURE = "infrastructure"
    OUTPUT = "output"
    CONCEPT = "concept"


@dataclass(frozen=True)
class DiagramNode:
    id: str
    label: str
    subtext: str = ""
    category: NodeCategory = NodeCategory.DOMAIN
    icon: str = ""
    highlighted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "subtext": self.subtext,
            "category": self.category.value,
            "icon": self.icon,
            "highlighted": self.highlighted,
        }


@dataclass(frozen=True)
class DiagramEdge:
    source_id: str
    target_id: str
    label: str = ""
    style: str = "solid"  # solid, dashed, animated

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "label": self.label,
            "style": self.style,
        }


@dataclass
class DiagramState:
    """State of an architecture or conceptual flow diagram."""
    diagram_id: str = "S04_ARCH_V0_1"
    title: str = "Agentic Studio v0.1 Architecture"
    subtitle: str = "User -> Agent -> LLM -> Answer"
    nodes: List[DiagramNode] = field(default_factory=list)
    edges: List[DiagramEdge] = field(default_factory=list)
    highlighted_nodes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diagram_id": self.diagram_id,
            "title": self.title,
            "subtitle": self.subtitle,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "highlighted_nodes": list(self.highlighted_nodes),
        }

    def render_svg(self, width: int = 1600, height: int = 900) -> str:
        """Render high-contrast SVG diagram."""
        node_count = max(1, len(self.nodes))
        spacing = width // (node_count + 1)
        node_width = 240
        node_height = 120
        y_center = height // 2

        node_coords: Dict[str, Tuple[int, int]] = {}
        svg_parts: List[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" class="diagram-svg">',
            f'<rect width="100%" height="100%" fill="#0d1117" />',
            f'<text x="{width//2}" y="80" text-anchor="middle" fill="#58a6ff" '
            f'font-family="system-ui, sans-serif" font-size="32" font-weight="bold">{html.escape(self.title)}</text>',
            f'<text x="{width//2}" y="120" text-anchor="middle" fill="#8b949e" '
            f'font-family="system-ui, sans-serif" font-size="20">{html.escape(self.subtitle)}</text>',
        ]

        # Calculate node positions (horizontal pipeline layout)
        for idx, node in enumerate(self.nodes):
            cx = spacing * (idx + 1)
            cy = y_center
            node_coords[node.id] = (cx, cy)

        # Render edges
        for edge in self.edges:
            if edge.source_id in node_coords and edge.target_id in node_coords:
                sx, sy = node_coords[edge.source_id]
                tx, ty = node_coords[edge.target_id]
                x1 = sx + node_width // 2
                x2 = tx - node_width // 2

                stroke_color = "#58a6ff" if edge.style == "animated" else "#30363d"
                stroke_dash = 'stroke-dasharray="6,6"' if edge.style == "dashed" else ""

                svg_parts.append(
                    f'<line x1="{x1}" y1="{sy}" x2="{x2}" y2="{ty}" stroke="{stroke_color}" '
                    f'stroke-width="3" {stroke_dash} />'
                )
                if edge.label:
                    mid_x = (x1 + x2) // 2
                    svg_parts.append(
                        f'<text x="{mid_x}" y="{sy - 15}" text-anchor="middle" fill="#8b949e" '
                        f'font-family="system-ui, sans-serif" font-size="14">{html.escape(edge.label)}</text>'
                    )

        # Render nodes
        for node in self.nodes:
            cx, cy = node_coords[node.id]
            rx = cx - node_width // 2
            ry = cy - node_height // 2

            is_hl = node.highlighted or (node.id in self.highlighted_nodes)
            border_color = "#388bfd" if is_hl else "#30363d"
            fill_color = "#161b22" if not is_hl else "#1f242c"
            glow = 'filter="drop-shadow(0 0 12px rgba(56,139,253,0.5))"' if is_hl else ""

            cat_colors = {
                NodeCategory.USER: "#7ee787",
                NodeCategory.DOMAIN: "#58a6ff",
                NodeCategory.INFRASTRUCTURE: "#d29922",
                NodeCategory.OUTPUT: "#a371f7",
                NodeCategory.CONCEPT: "#f0883e",
            }
            badge_color = cat_colors.get(node.category, "#58a6ff")

            svg_parts.append(f'<g class="diagram-node" {glow}>')
            svg_parts.append(
                f'<rect x="{rx}" y="{ry}" width="{node_width}" height="{node_height}" '
                f'rx="12" fill="{fill_color}" stroke="{border_color}" stroke-width="2" />'
            )
            # Category pill
            svg_parts.append(
                f'<rect x="{rx+12}" y="{ry+12}" width="80" height="20" rx="4" fill="{badge_color}22" />'
                f'<text x="{rx+52}" y="{ry+26}" text-anchor="middle" fill="{badge_color}" '
                f'font-family="system-ui, sans-serif" font-size="11" font-weight="600">{node.category.value.upper()}</text>'
            )
            # Node label
            svg_parts.append(
                f'<text x="{cx}" y="{cy+10}" text-anchor="middle" fill="#c9d1d9" '
                f'font-family="system-ui, sans-serif" font-size="20" font-weight="bold">{html.escape(node.label)}</text>'
            )
            # Node subtext
            if node.subtext:
                svg_parts.append(
                    f'<text x="{cx}" y="{cy+34}" text-anchor="middle" fill="#8b949e" '
                    f'font-family="system-ui, sans-serif" font-size="13">{html.escape(node.subtext)}</text>'
                )
            svg_parts.append('</g>')

        svg_parts.append('</svg>')
        return "\n".join(svg_parts)


class DiagramRenderer:
    """Renderer and builder for architecture and flow diagrams."""

    def __init__(self, initial_state: Optional[DiagramState] = None) -> None:
        self._state = initial_state or self.build_s04_arch_v01_diagram()

    @property
    def state(self) -> DiagramState:
        return self._state

    @classmethod
    def build_s03_recap_diagram(cls) -> DiagramState:
        """S03: Recap of Video 01 agent foundational concepts."""
        nodes = [
            DiagramNode("V01_PROMPT", "Prompt Engineering", "Static & One-Shot", NodeCategory.CONCEPT),
            DiagramNode("V01_CHAIN", "Chaining", "Linear Execution", NodeCategory.CONCEPT),
            DiagramNode("V01_AGENT", "Agent Architecture", "Autonomous Decision", NodeCategory.DOMAIN, highlighted=True),
        ]
        edges = [
            DiagramEdge("V01_PROMPT", "V01_CHAIN", "evolves to"),
            DiagramEdge("V01_CHAIN", "V01_AGENT", "evolves to"),
        ]
        return DiagramState(
            diagram_id="S03_RECAP",
            title="Video 01 Recap — Agent Architecture Foundations",
            subtitle="From Static Prompts to Autonomous Agent Systems",
            nodes=nodes,
            edges=edges,
        )

    @classmethod
    def build_s04_arch_v01_diagram(cls) -> DiagramState:
        """S04: Core v0.1 architecture (User -> Agent -> LLM -> Answer)."""
        nodes = [
            DiagramNode("N_USER", "User", "Prompt / Input", NodeCategory.USER),
            DiagramNode("N_AGENT", "Agent", "Orchestrator Core", NodeCategory.DOMAIN, highlighted=True),
            DiagramNode("N_LLM", "LLM Protocol", "Domain Client", NodeCategory.DOMAIN),
            DiagramNode("N_ANSWER", "Answer", "Structured Output", NodeCategory.OUTPUT),
        ]
        edges = [
            DiagramEdge("N_USER", "N_AGENT", "query", style="animated"),
            DiagramEdge("N_AGENT", "N_LLM", "generate"),
            DiagramEdge("N_LLM", "N_ANSWER", "response", style="animated"),
        ]
        return DiagramState(
            diagram_id="S04_ARCH_V0_1",
            title="Agentic Studio v0.1 Architecture",
            subtitle="User -> Agent -> LLM -> Answer (Zero Tool Calling)",
            nodes=nodes,
            edges=edges,
        )

    @classmethod
    def build_s11_concept_diagram(cls) -> DiagramState:
        """S11: Concept Deep Dive — Is This An Agent?"""
        nodes = [
            DiagramNode("C_CALL", "Simple LLM Call", "Stateless / Single Turn", NodeCategory.CONCEPT),
            DiagramNode("C_CONTRACT", "Domain Protocol", "Decoupled LLMClient", NodeCategory.DOMAIN, highlighted=True),
            DiagramNode("C_LOOP", "Agent Loop", "State + Orchestration", NodeCategory.DOMAIN),
        ]
        edges = [
            DiagramEdge("C_CALL", "C_CONTRACT", "abstracted by"),
            DiagramEdge("C_CONTRACT", "C_LOOP", "powers"),
        ]
        return DiagramState(
            diagram_id="S11_IS_THIS_AGENT",
            title="Is This An Agent?",
            subtitle="Domain Contracts & Orchestration vs Direct API Invocation",
            nodes=nodes,
            edges=edges,
        )

    @classmethod
    def build_s17_review_diagram(cls) -> DiagramState:
        """S17: Architecture Review — Domain vs Infrastructure Layer Isolation."""
        nodes = [
            DiagramNode("D_MODELS", "Domain Core", "Message, AgentConfig, Agent", NodeCategory.DOMAIN, highlighted=True),
            DiagramNode("D_PORT", "LLMClient Protocol", "Abstract Interface", NodeCategory.DOMAIN),
            DiagramNode("I_ADAPTER", "Infrastructure Adapters", "OpenAI / FakeLLM", NodeCategory.INFRASTRUCTURE),
        ]
        edges = [
            DiagramEdge("D_MODELS", "D_PORT", "depends on"),
            DiagramEdge("I_ADAPTER", "D_PORT", "implements", style="dashed"),
        ]
        return DiagramState(
            diagram_id="S17_ARCH_REVIEW",
            title="Architecture Review — Clean Architecture Isolation",
            subtitle="Domain Core never depends on external SDKs or Providers",
            nodes=nodes,
            edges=edges,
        )

    def set_diagram(self, diagram_id: str) -> DiagramState:
        if diagram_id == "S03_RECAP":
            self._state = self.build_s03_recap_diagram()
        elif diagram_id in ("S04_ARCH_V0_1", "ARCHITECTURE_V0_1"):
            self._state = self.build_s04_arch_v01_diagram()
        elif diagram_id in ("S11_IS_THIS_AGENT", "IS_THIS_AN_AGENT"):
            self._state = self.build_s11_concept_diagram()
        elif diagram_id in ("S17_ARCH_REVIEW", "ARCHITECTURE_REVIEW"):
            self._state = self.build_s17_review_diagram()
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
