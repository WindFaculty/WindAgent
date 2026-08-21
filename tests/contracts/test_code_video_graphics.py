"""
Contract and Unit Test Suite for Code Video Graphics, Diagrams, Title Cards & B-Roll (Phase 8).

Verifies:
- Visual Theme single source of truth, safe-area insets (pixel/percentage), typography (font >= 24px), contrast
- All 8 diagrams (including separated Cognitive Loop 05A & Missing Capabilities 05B) and SVG generation
- Title cards (S02 Hook, S18 Milestone, S19 Teaser) and strict S16 Checklist (7 excluded items)
- B-roll overlays and security callout banners
- GraphicsCatalog dynamic asset classification (REQUIRED, OPTIONAL, DERIVED) and timeline binding
- Phase 4 timeline consumer authority and GRAPHIC_TIMING_CONFLICT assertion
- Tri-hash determinism (source_hash, render_config_hash, output_hash)
- Full export and verification to artifacts/code_video/video_02/graphics/
"""

import html
import json
from pathlib import Path
import pytest

from windagent_workflows.code_video.contracts import CodeVideoPlan
from windagent_tools.code_video.renderer import (
    AnimationType,
    AssetCategory,
    AssetClassification,
    ChecklistItemStatus,
    CodeVideoVisualTheme,
    DiagramRenderer,
    GRAPHIC_TIMING_CONFLICT,
    GraphicsCatalog,
    GraphicsCatalogEntry,
    GraphicsVerifier,
    OverlayRenderer,
    SafeInsets,
    TitleRenderer,
    TransitionType,
)


class TestCodeVideoVisualTheme:
    """Test suite for CodeVideoVisualTheme, safe insets, and typography scales."""

    def test_theme_safe_insets_calculation(self) -> None:
        insets = SafeInsets(canvas_width=2560, canvas_height=1440, action_safe_pct=0.05, title_safe_pct=0.10)
        assert insets.action_safe_dx == 128
        assert insets.action_safe_dy == 72
        assert insets.title_safe_dx == 256
        assert insets.title_safe_dy == 144

        assert insets.action_safe_box == (128, 72, 2432, 1368)
        assert insets.title_safe_box == (256, 144, 2304, 1296)

    def test_theme_typography_minimums(self) -> None:
        theme = CodeVideoVisualTheme()
        assert theme.typography.minimum_body_font_px == 24
        assert theme.typography.body_font_px >= 24
        assert theme.typography.table_item_font_px >= 32
        assert theme.typography.section_heading_font_px >= 40
        assert theme.typography.hero_title_font_px >= 56

    def test_theme_contrast_calculation(self) -> None:
        theme = CodeVideoVisualTheme()
        # White on dark canvas
        ratio_light = theme.calculate_contrast_ratio("#f0f6fc", "#0d1117")
        assert ratio_light >= 10.0

        # Primary blue on dark canvas
        ratio_blue = theme.calculate_contrast_ratio("#58a6ff", "#0d1117")
        assert ratio_blue >= 4.5

        # Validation helper
        issues = theme.validate_text_element(font_size_px=28, fg_color="#f0f6fc", bg_color="#0d1117")
        assert len(issues) == 0

        # Sub-minimum font size triggers validation issue
        issues_small = theme.validate_text_element(font_size_px=18, fg_color="#f0f6fc", bg_color="#0d1117")
        assert len(issues_small) == 1
        assert "below minimum required 24px" in issues_small[0]

    def test_theme_config_hash_determinism(self) -> None:
        theme1 = CodeVideoVisualTheme()
        theme2 = CodeVideoVisualTheme()
        assert theme1.get_config_hash() == theme2.get_config_hash()
        assert len(theme1.get_config_hash()) == 64


class TestDiagramRendererSuite:
    """Test suite for all 8 architecture & concept diagrams."""

    def test_diag_01_final_arch(self) -> None:
        diag = DiagramRenderer.build_diag_01_final_arch()
        assert diag.diagram_id == "DIAG_01_FINAL_ARCH"
        assert len(diag.nodes) == 4
        node_ids = [n.id for n in diag.nodes]
        assert node_ids == ["N_USER", "N_AGENT", "N_LLM", "N_ANSWER"]

        svg = diag.render_svg()
        assert 'viewBox="0 0 2560 1440"' in svg
        assert "Agentic Studio v0.1 Architecture" in svg
        assert "font-size=" in svg
        assert diag.get_source_hash() is not None

    def test_diag_02_component_flow(self) -> None:
        diag = DiagramRenderer.build_diag_02_component_flow()
        assert diag.diagram_id == "DIAG_02_COMPONENT_FLOW"
        assert len(diag.nodes) == 4
        node_ids = {n.id for n in diag.nodes}
        assert {"N_CONFIG", "N_AGENT_CORE", "N_LLM_CLIENT", "N_PROVIDER"}.issubset(node_ids)
        svg = diag.render_svg()
        assert "AgentConfig" in svg
        assert "Provider" in svg

    def test_diag_03_today_vs_next(self) -> None:
        diag = DiagramRenderer.build_diag_03_today_vs_next()
        assert diag.diagram_id == "DIAG_03_TODAY_VS_NEXT"
        assert len(diag.nodes) == 2
        svg = diag.render_svg()
        assert "TODAY" in svg
        assert "NEXT" in svg

    def test_diag_04_llmclient_abstraction(self) -> None:
        diag = DiagramRenderer.build_diag_04_llmclient_abstraction()
        assert diag.diagram_id == "DIAG_04_LLMCLIENT_ABSTRACTION"
        assert len(diag.nodes) == 4
        assert diag.layout_mode == "TWO_TIER"
        svg = diag.render_svg()
        assert "DOMAIN LAYER" in svg
        assert "INFRASTRUCTURE LAYER" in svg

    def test_diag_05a_cognitive_loop(self) -> None:
        diag = DiagramRenderer.build_diag_05a_cognitive_loop()
        assert diag.diagram_id == "DIAG_05A_COGNITIVE_LOOP"
        assert len(diag.nodes) == 4
        node_ids = [n.id for n in diag.nodes]
        assert node_ids == ["L_OBSERVE", "L_DECIDE", "L_ACT", "L_FEEDBACK"]
        svg = diag.render_svg()
        assert "Canonical Cognitive Loop" in svg

    def test_diag_05b_missing_capabilities(self) -> None:
        diag = DiagramRenderer.build_diag_05b_missing_capabilities()
        assert diag.diagram_id == "DIAG_05B_MISSING_CAPABILITIES"
        assert len(diag.nodes) == 4
        # Check tool and loop are dimmed and struck through
        dimmed = [n for n in diag.nodes if n.is_dimmed]
        assert len(dimmed) == 2
        svg = diag.render_svg()
        assert "v0.1 Scope Analysis" in svg
        assert "Tool Calling" in svg

    def test_diag_06_domain_vs_infra(self) -> None:
        diag = DiagramRenderer.build_diag_06_domain_vs_infra()
        assert diag.diagram_id == "DIAG_06_DOMAIN_VS_INFRA"
        assert len(diag.nodes) == 4
        svg = diag.render_svg()
        assert "Clean Architecture Isolation" in svg

    def test_diag_07_recap(self) -> None:
        diag = DiagramRenderer.build_diag_07_recap()
        assert diag.diagram_id == "DIAG_07_RECAP"
        assert len(diag.nodes) == 3
        svg = diag.render_svg()
        assert "Video 01 Recap" in svg

    def test_diag_08_execution_flow(self) -> None:
        diag = DiagramRenderer.build_diag_08_execution_flow()
        assert diag.diagram_id == "DIAG_08_EXECUTION_FLOW"
        assert len(diag.nodes) == 5
        svg = diag.render_svg()
        assert "Execution Flow" in svg


class TestTitleAndChecklistSuite:
    """Test suite for Title cards and strict S16 Checklist."""

    def test_s02_hook_title_card(self) -> None:
        card = TitleRenderer.build_s02_hook_title()
        assert card.badge == "VIDEO 02"
        assert "VIẾT AI AGENT" in card.title
        html_out = card.render_html()
        assert "2560px" in html_out
        assert "1440px" in html_out
        assert len(card.get_source_hash()) == 64

    def test_s18_git_milestone_card(self) -> None:
        card = TitleRenderer.build_s18_git_milestone()
        assert card.card_id == "CARD_S18_MILESTONE"
        assert "Agentic Studio v0.1" in card.title
        html_out = card.render_html()
        assert "GIT MILESTONE" in html_out

    def test_s19_outro_card(self) -> None:
        card = TitleRenderer.build_s19_outro_card()
        assert "VIDEO 03: TOOL CALLING" in card.next_episode_title
        html_out = card.render_html()
        assert "TẬP TIẾP THEO" in html_out

    def test_s16_strict_excluded_checklist(self) -> None:
        checklist = TitleRenderer.build_s16_checklist()
        assert checklist.checklist_id == "CHECKLIST_S16_NOT_YET"
        # Must strictly have 7 items from script
        assert len(checklist.items) == 7
        for it in checklist.items:
            assert it.status == ChecklistItemStatus.EXCLUDED

        item_texts = [it.text for it in checklist.items]
        expected_items = [
            "Tool Calling",
            "Agent Loop",
            "Memory",
            "RAG",
            "Planning",
            "Multi-Agent",
            "Orchestration",
        ]
        assert item_texts == expected_items

        html_out = checklist.render_html()
        assert "2560px" in html_out
        assert "NOT YET" in html_out


class TestOverlayRendererSuite:
    """Test suite for B-roll overlays & security callouts."""

    def test_all_canonical_overlays(self) -> None:
        ovrs = [
            OverlayRenderer.build_ovr_s06_message(),
            OverlayRenderer.build_ovr_s07_config(),
            OverlayRenderer.build_ovr_s08_protocol(),
            OverlayRenderer.build_ovr_s09_unit_test_vs_api(),
            OverlayRenderer.build_ovr_s10_execution_flow(),
            OverlayRenderer.build_ovr_s13_api_key_security(),
            OverlayRenderer.build_ovr_s19_llm_not_executor(),
        ]
        assert len(ovrs) == 7
        for ovr in ovrs:
            assert len(ovr.overlay_id) > 0
            assert len(ovr.get_source_hash()) == 64
            html_out = ovr.render_html()
            assert "overlay-card" in html_out
            assert html.escape(ovr.title) in html_out


class TestGraphicsCatalogSuite:
    """Test suite for GraphicsCatalog, timeline bindings, and conflict policies."""

    def test_catalog_construction_and_classification(self) -> None:
        catalog = GraphicsCatalog.build_default_video_02_catalog()
        assert len(catalog.entries) >= 16

        required = catalog.get_required_assets()
        optional = catalog.get_optional_assets()
        assert len(required) >= 15
        assert len(optional) >= 1

        # Check DIAG_07_RECAP is classified as OPTIONAL
        recap_entry = catalog.entries.get("DIAG_07_RECAP")
        assert recap_entry is not None
        assert recap_entry.classification == AssetClassification.OPTIONAL

        # Check Tri-Hashes exist for all entries
        for entry in catalog.entries.values():
            assert len(entry.source_hash) == 64
            assert len(entry.render_config_hash) == 64
            assert len(entry.output_hash) == 64
            assert entry.duration_ms == entry.exit_ms - entry.entry_ms

    def test_catalog_timeline_validation_against_plan(self) -> None:
        plan_path = Path("artifacts/code_video/video_02/plans/video_02_plan.json")
        assert plan_path.exists(), "Phase 4 plan must exist"

        with open(plan_path, "r", encoding="utf-8") as f:
            plan = CodeVideoPlan.from_dict(json.load(f))

        catalog = GraphicsCatalog.build_default_video_02_catalog(plan=plan)
        # Should pass without throwing GRAPHIC_TIMING_CONFLICT
        catalog.validate_against_plan(plan)

    def test_graphic_timing_conflict_assertion(self) -> None:
        plan_path = Path("artifacts/code_video/video_02/plans/video_02_plan.json")
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = CodeVideoPlan.from_dict(json.load(f))

        catalog = GraphicsCatalog()
        # Add invalid entry exceeding S01 end bounds (S01 is 0 - 25,000 ms)
        invalid_entry = GraphicsCatalogEntry(
            asset_id="INVALID_ASSET",
            classification=AssetClassification.REQUIRED,
            category=AssetCategory.DIAGRAM,
            scene_id="S01",
            entry_ms=10000,
            exit_ms=30000,  # Exceeds S01 25,000ms!
            duration_ms=20000,
            transition_in=TransitionType.FADE,
            transition_out=TransitionType.FADE,
            animation=AnimationType.NONE,
            filename="invalid.svg",
            content="<svg></svg>",
            source_hash="a" * 64,
            render_config_hash="b" * 64,
            output_hash="c" * 64,
        )
        catalog.add_entry(invalid_entry)

        with pytest.raises(GRAPHIC_TIMING_CONFLICT) as excinfo:
            catalog.validate_against_plan(plan)
        assert "GRAPHIC_TIMING_CONFLICT" in str(excinfo.value)


class TestGraphicsVerifierAndExport:
    """Test suite for automated verification and gate certification."""

    def test_verifier_inspects_all_catalog_assets(self) -> None:
        plan_path = Path("artifacts/code_video/video_02/plans/video_02_plan.json")
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = CodeVideoPlan.from_dict(json.load(f))

        catalog = GraphicsCatalog.build_default_video_02_catalog(plan=plan)
        verifier = GraphicsVerifier(theme=catalog.theme)

        report = verifier.verify_catalog(catalog=catalog, plan=plan)
        assert report.gate == "CV02_P8_GRAPHICS_VERIFIED"
        assert report.status == "PASS"
        assert report.all_required_passed is True
        assert report.required_passed_count == report.required_assets_count
        assert report.required_assets_count >= 15

    def test_export_assets_to_disk_and_verify_manifest(self, tmp_path: Path) -> None:
        catalog = GraphicsCatalog.build_default_video_02_catalog()
        manifest = catalog.export_assets(output_dir=tmp_path)

        assert manifest["total_assets"] >= 16
        assert (tmp_path / "graphics_manifest.json").exists()
        assert (tmp_path / "graphics_receipt.json").exists()
        assert (tmp_path / "diagram_01_user_agent_llm_answer.svg").exists()
        assert (tmp_path / "title_01_video02_hook.html").exists()
        assert (tmp_path / "checklist_s16_not_yet.html").exists()
        assert (tmp_path / "overlay_s06_message.html").exists()
