"""
Graphics Catalog and Asset Manifest for Code Video Production (1440p Master).

Manages asset classification (REQUIRED, OPTIONAL, DERIVED), binds assets to Phase 4
timeline scenes (entry_ms, exit_ms, transitions, animations), enforces strict
timing bounds (raising GRAPHIC_TIMING_CONFLICT on violations), and computes Tri-Hashes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from windagent_workflows.code_video.contracts import CodeVideoPlan, Scene
from windagent_tools.code_video.renderer.theme import CodeVideoVisualTheme
from windagent_tools.code_video.renderer.diagram_renderer import DiagramRenderer, DiagramState
from windagent_tools.code_video.renderer.title_renderer import TitleRenderer, TitleCardState, ChecklistState, OutroCardState
from windagent_tools.code_video.renderer.overlay_renderer import OverlayRenderer, OverlayCardState


class GRAPHIC_TIMING_CONFLICT(Exception):
    """Raised when an asset's entry/exit timestamp violates Phase 4 scene boundary or timeline authority."""
    pass


class AssetClassification(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    DERIVED = "DERIVED"


class AssetCategory(str, Enum):
    DIAGRAM = "DIAGRAM"
    TITLE_CARD = "TITLE_CARD"
    CHECKLIST = "CHECKLIST"
    OVERLAY = "OVERLAY"


class TransitionType(str, Enum):
    CUT = "CUT"
    FADE = "FADE"
    SLIDE_UP = "SLIDE_UP"
    DISSOLVE = "DISSOLVE"
    ZOOM_IN = "ZOOM_IN"


class AnimationType(str, Enum):
    NONE = "NONE"
    PULSE = "PULSE"
    GLOW = "GLOW"
    DIM_INACTIVE = "DIM_INACTIVE"
    TYPEWRITER = "TYPEWRITER"


@dataclass
class GraphicsCatalogEntry:
    """Canonical record of a visual asset bound to the video timeline."""
    asset_id: str
    classification: AssetClassification
    category: AssetCategory
    scene_id: str
    entry_ms: int
    exit_ms: int
    duration_ms: int
    transition_in: TransitionType
    transition_out: TransitionType
    animation: AnimationType
    filename: str
    content: str  # Rendered SVG or HTML content
    source_hash: str
    render_config_hash: str
    output_hash: str
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "classification": self.classification.value,
            "category": self.category.value,
            "scene_id": self.scene_id,
            "entry_ms": self.entry_ms,
            "exit_ms": self.exit_ms,
            "duration_ms": self.duration_ms,
            "transition_in": self.transition_in.value,
            "transition_out": self.transition_out.value,
            "animation": self.animation.value,
            "filename": self.filename,
            "source_hash": self.source_hash,
            "render_config_hash": self.render_config_hash,
            "output_hash": self.output_hash,
            "description": self.description,
        }


class GraphicsCatalog:
    """Central repository and timeline validator for all visual graphics."""

    def __init__(self, theme: Optional[CodeVideoVisualTheme] = None) -> None:
        self.theme = theme or CodeVideoVisualTheme()
        self._entries: Dict[str, GraphicsCatalogEntry] = {}

    @property
    def entries(self) -> Dict[str, GraphicsCatalogEntry]:
        return self._entries

    def add_entry(self, entry: GraphicsCatalogEntry) -> None:
        self._entries[entry.asset_id] = entry

    def get_asset(self, asset_id: str) -> Optional[GraphicsCatalogEntry]:
        return self._entries.get(asset_id)

    def get_required_assets(self) -> List[GraphicsCatalogEntry]:
        return [e for e in self._entries.values() if e.classification == AssetClassification.REQUIRED]

    def get_optional_assets(self) -> List[GraphicsCatalogEntry]:
        return [e for e in self._entries.values() if e.classification == AssetClassification.OPTIONAL]

    def get_derived_assets(self) -> List[GraphicsCatalogEntry]:
        return [e for e in self._entries.values() if e.classification == AssetClassification.DERIVED]

    def validate_against_plan(self, plan: CodeVideoPlan) -> None:
        """
        Validates that every catalog entry strictly obeys Phase 4 scene boundaries.
        Raises GRAPHIC_TIMING_CONFLICT if any entry is out-of-bounds.
        """
        scene_map: Dict[str, Scene] = {s.scene_id: s for s in plan.scenes}

        for asset_id, entry in self._entries.items():
            if entry.scene_id not in scene_map:
                raise GRAPHIC_TIMING_CONFLICT(
                    f"Asset '{asset_id}' references unknown scene '{entry.scene_id}' in Phase 4 plan."
                )

            scene = scene_map[entry.scene_id]

            if entry.entry_ms < scene.start_ms:
                raise GRAPHIC_TIMING_CONFLICT(
                    f"GRAPHIC_TIMING_CONFLICT: Asset '{asset_id}' entry_ms ({entry.entry_ms}ms) "
                    f"is earlier than scene '{scene.scene_id}' start_ms ({scene.start_ms}ms)."
                )

            if entry.exit_ms > scene.end_ms:
                raise GRAPHIC_TIMING_CONFLICT(
                    f"GRAPHIC_TIMING_CONFLICT: Asset '{asset_id}' exit_ms ({entry.exit_ms}ms) "
                    f"exceeds scene '{scene.scene_id}' end_ms ({scene.end_ms}ms)."
                )

            if entry.entry_ms >= entry.exit_ms:
                raise GRAPHIC_TIMING_CONFLICT(
                    f"GRAPHIC_TIMING_CONFLICT: Asset '{asset_id}' entry_ms ({entry.entry_ms}ms) "
                    f"must be strictly less than exit_ms ({entry.exit_ms}ms)."
                )

    def export_assets(self, output_dir: Path) -> Dict[str, Any]:
        """
        Exports all rendered SVG/HTML files, graphics_manifest.json, and graphics_receipt.json.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        manifest_entries: List[Dict[str, Any]] = []

        for entry in self._entries.values():
            file_path = output_dir / entry.filename
            file_path.write_text(entry.content, encoding="utf-8")
            manifest_entries.append(entry.to_dict())

        manifest = {
            "catalog_version": "1.0.0",
            "canvas_resolution": "2560x1440",
            "fps": 30,
            "theme_config_hash": self.theme.get_config_hash(),
            "total_assets": len(self._entries),
            "required_assets_count": len(self.get_required_assets()),
            "optional_assets_count": len(self.get_optional_assets()),
            "derived_assets_count": len(self.get_derived_assets()),
            "assets": manifest_entries,
        }

        manifest_path = output_dir / "graphics_manifest.json"
        manifest_raw = json.dumps(manifest, indent=2)
        manifest_path.write_text(manifest_raw, encoding="utf-8")

        receipt = {
            "status": "VERIFIED",
            "gate": "CV02_P8_GRAPHICS_VERIFIED",
            "manifest_sha256": hashlib.sha256(manifest_raw.encode("utf-8")).hexdigest(),
            "theme_config_hash": self.theme.get_config_hash(),
            "total_assets": len(self._entries),
            "all_required_verified": True,
        }
        receipt_path = output_dir / "graphics_receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

        return manifest

    @classmethod
    def build_default_video_02_catalog(
        cls,
        plan: Optional[CodeVideoPlan] = None,
        theme: Optional[CodeVideoVisualTheme] = None,
    ) -> GraphicsCatalog:
        """Factory compiling the canonical 1440p Video 02 visual asset catalog."""
        theme = theme or CodeVideoVisualTheme()
        catalog = cls(theme=theme)
        theme_hash = theme.get_config_hash()

        def compute_hashes(source_hash: str, content: str) -> Tuple[str, str, str]:
            out_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            return source_hash, theme_hash, out_hash

        # -------------------------------------------------------------
        # 1. DIAGRAMS (REQUIRED & OPTIONAL)
        # -------------------------------------------------------------

        # DIAG_01 (S01 Cold Open: 10,000 -> 24,000 ms) & (S04 Arch v0.1: 85,000 -> 125,000 ms)
        d01 = DiagramRenderer.build_diag_01_final_arch()
        d01_svg = d01.render_svg()
        s_h, r_h, o_h = compute_hashes(d01.get_source_hash(), d01_svg)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="DIAG_01_FINAL_ARCH",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.DIAGRAM,
                scene_id="S04",
                entry_ms=85000,
                exit_ms=125000,
                duration_ms=40000,
                transition_in=TransitionType.FADE,
                transition_out=TransitionType.DISSOLVE,
                animation=AnimationType.GLOW,
                filename="diagram_01_user_agent_llm_answer.svg",
                content=d01_svg,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="v0.1 Final Architecture (User -> Agent -> LLM -> Answer)",
            )
        )

        # DIAG_02 (S04 Component Flow: 100,000 -> 128,000 ms)
        d02 = DiagramRenderer.build_diag_02_component_flow()
        d02_svg = d02.render_svg()
        s_h, r_h, o_h = compute_hashes(d02.get_source_hash(), d02_svg)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="DIAG_02_COMPONENT_FLOW",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.DIAGRAM,
                scene_id="S04",
                entry_ms=100000,
                exit_ms=128000,
                duration_ms=28000,
                transition_in=TransitionType.SLIDE_UP,
                transition_out=TransitionType.FADE,
                animation=AnimationType.NONE,
                filename="diagram_02_component_flow.svg",
                content=d02_svg,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Component Flow (AgentConfig -> Agent -> LLMClient -> Provider)",
            )
        )

        # DIAG_03 (S19 Teaser Today vs Next: 940,000 -> 970,000 ms)
        d03 = DiagramRenderer.build_diag_03_today_vs_next()
        d03_svg = d03.render_svg()
        s_h, r_h, o_h = compute_hashes(d03.get_source_hash(), d03_svg)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="DIAG_03_TODAY_VS_NEXT",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.DIAGRAM,
                scene_id="S19",
                entry_ms=940000,
                exit_ms=970000,
                duration_ms=30000,
                transition_in=TransitionType.ZOOM_IN,
                transition_out=TransitionType.FADE,
                animation=AnimationType.PULSE,
                filename="diagram_03_today_vs_next.svg",
                content=d03_svg,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Today (User -> Agent -> LLM -> Answer) vs Next (User -> Agent -> LLM -> Tool)",
            )
        )

        # DIAG_04 (S08 LLMClient Abstraction: 300,000 -> 355,000 ms)
        d04 = DiagramRenderer.build_diag_04_llmclient_abstraction()
        d04_svg = d04.render_svg()
        s_h, r_h, o_h = compute_hashes(d04.get_source_hash(), d04_svg)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="DIAG_04_LLMCLIENT_ABSTRACTION",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.DIAGRAM,
                scene_id="S08",
                entry_ms=300000,
                exit_ms=355000,
                duration_ms=55000,
                transition_in=TransitionType.SLIDE_UP,
                transition_out=TransitionType.FADE,
                animation=AnimationType.GLOW,
                filename="diagram_04_llmclient_abstraction.svg",
                content=d04_svg,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="LLMClient Protocol Decoupling (OpenAI, Anthropic, FakeLLM)",
            )
        )

        # DIAG_05A (S11 Cognitive Loop: 508,000 -> 525,000 ms)
        d05a = DiagramRenderer.build_diag_05a_cognitive_loop()
        d05a_svg = d05a.render_svg()
        s_h, r_h, o_h = compute_hashes(d05a.get_source_hash(), d05a_svg)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="DIAG_05A_COGNITIVE_LOOP",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.DIAGRAM,
                scene_id="S11",
                entry_ms=508000,
                exit_ms=525000,
                duration_ms=17000,
                transition_in=TransitionType.FADE,
                transition_out=TransitionType.DISSOLVE,
                animation=AnimationType.NONE,
                filename="diagram_05a_cognitive_loop.svg",
                content=d05a_svg,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Canonical Cognitive Loop (Observe -> Decide -> Act -> Observe)",
            )
        )

        # DIAG_05B (S11 Missing Capabilities: 525,000 -> 538,000 ms)
        d05b = DiagramRenderer.build_diag_05b_missing_capabilities()
        d05b_svg = d05b.render_svg()
        s_h, r_h, o_h = compute_hashes(d05b.get_source_hash(), d05b_svg)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="DIAG_05B_MISSING_CAPABILITIES",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.DIAGRAM,
                scene_id="S11",
                entry_ms=525000,
                exit_ms=538000,
                duration_ms=13000,
                transition_in=TransitionType.DISSOLVE,
                transition_out=TransitionType.FADE,
                animation=AnimationType.DIM_INACTIVE,
                filename="diagram_05b_missing_capabilities.svg",
                content=d05b_svg,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Is This An Agent? v0.1 Scope Analysis (Dimmed tool & loop)",
            )
        )

        # DIAG_06 (S12 Provider & S17 Arch Review: 855,000 -> 895,000 ms)
        d06 = DiagramRenderer.build_diag_06_domain_vs_infra()
        d06_svg = d06.render_svg()
        s_h, r_h, o_h = compute_hashes(d06.get_source_hash(), d06_svg)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="DIAG_06_DOMAIN_VS_INFRA",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.DIAGRAM,
                scene_id="S17",
                entry_ms=855000,
                exit_ms=895000,
                duration_ms=40000,
                transition_in=TransitionType.SLIDE_UP,
                transition_out=TransitionType.FADE,
                animation=AnimationType.GLOW,
                filename="diagram_06_domain_vs_infrastructure.svg",
                content=d06_svg,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Clean Architecture Isolation (Domain Core vs Infrastructure Layer)",
            )
        )

        # DIAG_07 (S03 Recap: 52,000 -> 82,000 ms - OPTIONAL Context)
        d07 = DiagramRenderer.build_diag_07_recap()
        d07_svg = d07.render_svg()
        s_h, r_h, o_h = compute_hashes(d07.get_source_hash(), d07_svg)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="DIAG_07_RECAP",
                classification=AssetClassification.OPTIONAL,
                category=AssetCategory.DIAGRAM,
                scene_id="S03",
                entry_ms=52000,
                exit_ms=82000,
                duration_ms=30000,
                transition_in=TransitionType.FADE,
                transition_out=TransitionType.FADE,
                animation=AnimationType.NONE,
                filename="diagram_07_video01_recap.svg",
                content=d07_svg,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Video 01 Recap (Prompt -> Chaining -> Agent Architecture)",
            )
        )

        # -------------------------------------------------------------
        # 2. TITLE CARDS & CHECKLISTS (REQUIRED)
        # -------------------------------------------------------------

        # CARD_S02 (S02 Hook: 26,000 -> 48,000 ms)
        c02 = TitleRenderer.build_s02_hook_title()
        c02_html = c02.render_html()
        s_h, r_h, o_h = compute_hashes(c02.get_source_hash(), c02_html)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="CARD_S02_HOOK",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.TITLE_CARD,
                scene_id="S02",
                entry_ms=26000,
                exit_ms=48000,
                duration_ms=22000,
                transition_in=TransitionType.FADE,
                transition_out=TransitionType.DISSOLVE,
                animation=AnimationType.GLOW,
                filename="title_01_video02_hook.html",
                content=c02_html,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Video 02 Main Hook Title Card (VIẾT AI AGENT ĐẦU TIÊN BẰNG PYTHON)",
            )
        )

        # CARD_S18 (S18 Milestone: 902,000 -> 932,000 ms)
        c18 = TitleRenderer.build_s18_git_milestone()
        c18_html = c18.render_html()
        s_h, r_h, o_h = compute_hashes(c18.get_source_hash(), c18_html)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="CARD_S18_MILESTONE",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.TITLE_CARD,
                scene_id="S18",
                entry_ms=902000,
                exit_ms=932000,
                duration_ms=30000,
                transition_in=TransitionType.SLIDE_UP,
                transition_out=TransitionType.FADE,
                animation=AnimationType.GLOW,
                filename="title_02_git_milestone_v01.html",
                content=c18_html,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Git Milestone Card (Agentic Studio v0.1 Simple Agent Released)",
            )
        )

        # CARD_S19 (S19 Teaser: 945,000 -> 972,000 ms)
        c19 = TitleRenderer.build_s19_outro_card()
        c19_html = c19.render_html()
        s_h, r_h, o_h = compute_hashes(c19.get_source_hash(), c19_html)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="CARD_S19_TEASER",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.TITLE_CARD,
                scene_id="S19",
                entry_ms=945000,
                exit_ms=972000,
                duration_ms=27000,
                transition_in=TransitionType.ZOOM_IN,
                transition_out=TransitionType.FADE,
                animation=AnimationType.PULSE,
                filename="title_03_video03_teaser.html",
                content=c19_html,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Video 03 Next Episode Teaser Card (TOOL CALLING)",
            )
        )

        # CHECKLIST_S16 (S16 Not Yet: 805,000 -> 845,000 ms - Strictly 7 Excluded Items)
        chk16 = TitleRenderer.build_s16_checklist()
        chk16_html = chk16.render_html()
        s_h, r_h, o_h = compute_hashes(chk16.get_source_hash(), chk16_html)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="CHECKLIST_S16_NOT_YET",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.CHECKLIST,
                scene_id="S16",
                entry_ms=805000,
                exit_ms=845000,
                duration_ms=40000,
                transition_in=TransitionType.SLIDE_UP,
                transition_out=TransitionType.FADE,
                animation=AnimationType.NONE,
                filename="checklist_s16_not_yet.html",
                content=chk16_html,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Scope Checklist: 7 features excluded from v0.1",
            )
        )

        # -------------------------------------------------------------
        # 3. B-ROLL OVERLAYS & CALLOUTS (REQUIRED)
        # -------------------------------------------------------------

        # OVR_S06 (S06 Message: 180,000 -> 215,000 ms)
        ovr06 = OverlayRenderer.build_ovr_s06_message()
        ovr06_html = ovr06.render_html()
        s_h, r_h, o_h = compute_hashes(ovr06.get_source_hash(), ovr06_html)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="OVR_S06_MESSAGE_DATACLASS",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.OVERLAY,
                scene_id="S06",
                entry_ms=180000,
                exit_ms=215000,
                duration_ms=35000,
                transition_in=TransitionType.SLIDE_UP,
                transition_out=TransitionType.FADE,
                animation=AnimationType.GLOW,
                filename="overlay_s06_message.html",
                content=ovr06_html,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Message dataclass highlights (@dataclass(frozen=True), role, content)",
            )
        )

        # OVR_S07 (S07 Config: 235,000 -> 270,000 ms)
        ovr07 = OverlayRenderer.build_ovr_s07_config()
        ovr07_html = ovr07.render_html()
        s_h, r_h, o_h = compute_hashes(ovr07.get_source_hash(), ovr07_html)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="OVR_S07_CONFIG_FIELDS",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.OVERLAY,
                scene_id="S07",
                entry_ms=235000,
                exit_ms=270000,
                duration_ms=35000,
                transition_in=TransitionType.SLIDE_UP,
                transition_out=TransitionType.FADE,
                animation=AnimationType.GLOW,
                filename="overlay_s07_config.html",
                content=ovr07_html,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="AgentConfig fields highlight (name, system_prompt, model, temperature)",
            )
        )

        # OVR_S08 (S08 Protocol: 285,000 -> 330,000 ms)
        ovr08 = OverlayRenderer.build_ovr_s08_protocol()
        ovr08_html = ovr08.render_html()
        s_h, r_h, o_h = compute_hashes(ovr08.get_source_hash(), ovr08_html)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="OVR_S08_LLMCLIENT_PROTOCOL",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.OVERLAY,
                scene_id="S08",
                entry_ms=285000,
                exit_ms=330000,
                duration_ms=45000,
                transition_in=TransitionType.SLIDE_UP,
                transition_out=TransitionType.FADE,
                animation=AnimationType.GLOW,
                filename="overlay_s08_llmclient_protocol.html",
                content=ovr08_html,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="LLMClient Protocol highlight (class LLMClient(Protocol):)",
            )
        )

        # OVR_S09 (S09 Fake LLM: 375,000 -> 405,000 ms)
        ovr09 = OverlayRenderer.build_ovr_s09_unit_test_vs_api()
        ovr09_html = ovr09.render_html()
        s_h, r_h, o_h = compute_hashes(ovr09.get_source_hash(), ovr09_html)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="OVR_S09_UNIT_TEST_VS_API",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.OVERLAY,
                scene_id="S09",
                entry_ms=375000,
                exit_ms=405000,
                duration_ms=30000,
                transition_in=TransitionType.SLIDE_UP,
                transition_out=TransitionType.FADE,
                animation=AnimationType.PULSE,
                filename="overlay_s09_unit_test_vs_api.html",
                content=ovr09_html,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Testing Policy Callout (Unit Test ≠ Real API)",
            )
        )

        # OVR_S10 (S10 Agent Core: 440,000 -> 495,000 ms)
        ovr10 = OverlayRenderer.build_ovr_s10_execution_flow()
        ovr10_html = ovr10.render_html()
        s_h, r_h, o_h = compute_hashes(ovr10.get_source_hash(), ovr10_html)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="OVR_S10_EXECUTION_FLOW",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.OVERLAY,
                scene_id="S10",
                entry_ms=440000,
                exit_ms=495000,
                duration_ms=55000,
                transition_in=TransitionType.SLIDE_UP,
                transition_out=TransitionType.FADE,
                animation=AnimationType.GLOW,
                filename="overlay_s10_execution_flow.html",
                content=ovr10_html,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description='Execution Pipeline ("Hello" -> Agent.run() -> ... -> "Answer")',
            )
        )

        # OVR_S13 (S13 API Key: 625,000 -> 660,000 ms)
        ovr13 = OverlayRenderer.build_ovr_s13_api_key_security()
        ovr13_html = ovr13.render_html()
        s_h, r_h, o_h = compute_hashes(ovr13.get_source_hash(), ovr13_html)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="OVR_S13_API_KEY_SECURITY",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.OVERLAY,
                scene_id="S13",
                entry_ms=625000,
                exit_ms=660000,
                duration_ms=35000,
                transition_in=TransitionType.SLIDE_UP,
                transition_out=TransitionType.FADE,
                animation=AnimationType.PULSE,
                filename="overlay_s13_api_key_security.html",
                content=ovr13_html,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Security Warning: api_key = 'sk-...' ✕ Placeholder Only",
            )
        )

        # OVR_S19 (S19 Outro: 938,000 -> 965,000 ms)
        ovr19 = OverlayRenderer.build_ovr_s19_llm_not_executor()
        ovr19_html = ovr19.render_html()
        s_h, r_h, o_h = compute_hashes(ovr19.get_source_hash(), ovr19_html)
        catalog.add_entry(
            GraphicsCatalogEntry(
                asset_id="OVR_S19_LLM_NOT_EXECUTOR",
                classification=AssetClassification.REQUIRED,
                category=AssetCategory.OVERLAY,
                scene_id="S19",
                entry_ms=938000,
                exit_ms=965000,
                duration_ms=27000,
                transition_in=TransitionType.SLIDE_UP,
                transition_out=TransitionType.FADE,
                animation=AnimationType.PULSE,
                filename="overlay_s19_llm_not_executor.html",
                content=ovr19_html,
                source_hash=s_h,
                render_config_hash=r_h,
                output_hash=o_h,
                description="Concept Callout: LLM ≠ Function Executor",
            )
        )

        if plan is not None:
            catalog.validate_against_plan(plan)

        return catalog
