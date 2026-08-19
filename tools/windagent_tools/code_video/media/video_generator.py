"""
Real Video Synthesizer & FFmpeg Master Video Generator for Video 02.

Renders high-definition visual frames (2560x1440) for all 19 scenes of Video 02:
- Code Studio layouts (file tree, syntax-highlighted editor, terminal)
- Clean architecture diagrams
- Hero title cards & checklist overlays
- Accurate timecodes, status badges, and safe-area insets (WCAG AA compliant)

Encodes and concatenates real binary MP4 video bitstreams using FFmpeg:
- Master: 2560x1440 @ 30fps (H.264 / yuv420p, zero audio streams)
- Delivery: 1920x1080 @ 30fps (Lanczos downscaled)
- Exact duration: 16:15.000 (975.000 seconds = 29,250 frames)
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from windagent_workflows.code_video.contracts import CodeVideoPlan, Scene


class Video02FrameRenderer:
    """Renders pixel-perfect 2560x1440 master frames with Visual Studio Code / Antigravity IDE aesthetics."""

    # VS Code / Antigravity Dark Theme Palette
    IDE_TITLEBAR_BG = (30, 30, 30)         # #1e1e1e (Window title bar)
    IDE_ACTIVITY_BG = (24, 24, 24)         # #181818 (Left activity bar)
    IDE_SIDEBAR_BG = (37, 37, 38)          # #252526 (Explorer sidebar)
    IDE_EDITOR_BG = (30, 30, 30)           # #1e1e1e (Editor background)
    IDE_TABBAR_BG = (24, 24, 24)           # #181818 (Tabs background)
    IDE_ACTIVE_TAB_BG = (30, 30, 30)       # #1e1e1e (Active tab)
    IDE_INACTIVE_TAB_BG = (45, 45, 45)     # #2d2d2d (Inactive tab)
    IDE_BORDER = (50, 50, 50)              # #323232 (Subtle dividers)
    IDE_STATUSBAR_BG = (0, 122, 204)       # #007acc (VS Code status bar blue)
    IDE_TERMINAL_BG = (24, 24, 24)         # #181818 (Terminal background)

    # Syntax Highlighting Colors (VS Code Dark+ & Antigravity)
    SYN_KEYWORD = (197, 134, 192)          # #c586c0 (def, class, return, from, import, if, raise)
    SYN_TYPE = (78, 201, 176)              # #4ec9b0 (str, float, int, Protocol, Sequence, Message)
    SYN_FUNCTION = (220, 220, 170)         # #dcdcaa (run, generate, validate, post_init)
    SYN_DECORATOR = (220, 220, 170)        # #dcdcaa (@dataclass)
    SYN_STRING = (206, 145, 120)           # #ce9178 ('system', 'user', "Hello")
    SYN_NUMBER = (181, 206, 168)           # #b5cea8 (0.7, 2.0, 1)
    SYN_COMMENT = (106, 153, 85)           # #6a9955 (# comment)
    SYN_VARIABLE = (156, 220, 254)         # #9cdcfe (self, config, messages, user_input)
    SYN_PUNCTUATION = (212, 212, 212)      # #d4d4d4 (=, :, ->, (, ), [, ])
    SYN_WHITE = (240, 240, 240)
    SYN_HIGHLIGHT_BG = (45, 51, 59)        # Active line / teaching highlight
    SYN_ACCENT_BLUE = (0, 122, 204)        # Highlight left border & active tab indicator

    # Accent Colors for Diagrams & UI
    ACCENT_BLUE = (88, 166, 255)
    SUCCESS_GREEN = (63, 185, 80)
    ORANGE_ACCENT = (240, 136, 62)
    RED_ACCENT = (248, 81, 73)
    PURPLE_ACCENT = (188, 140, 255)
    TEXT_PRIMARY = (201, 209, 217)
    TEXT_MUTED = (139, 148, 158)
    TEXT_WHITE = (240, 246, 252)

    def __init__(self, width: int = 2560, height: int = 1440) -> None:
        self.width = width
        self.height = height

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        """Attempt to load system TrueType fonts, fallback to default font."""
        font_candidates = [
            "C:\\Windows\\Fonts\\segoeui.ttf" if not bold else "C:\\Windows\\Fonts\\segoeuib.ttf",
            "C:\\Windows\\Fonts\\consola.ttf" if not bold else "C:\\Windows\\Fonts\\consolab.ttf",
            "C:\\Windows\\Fonts\\arial.ttf" if not bold else "C:\\Windows\\Fonts\\arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for fpath in font_candidates:
            if os.path.exists(fpath):
                try:
                    return ImageFont.truetype(fpath, size=size)
                except Exception:
                    pass
        return ImageFont.load_default()

    def _get_mono_font(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        """Attempt to load monospace font for code & terminal."""
        font_candidates = [
            "C:\\Windows\\Fonts\\consola.ttf" if not bold else "C:\\Windows\\Fonts\\consolab.ttf",
            "C:\\Windows\\Fonts\\cour.ttf" if not bold else "C:\\Windows\\Fonts\\courbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        ]
        for fpath in font_candidates:
            if os.path.exists(fpath):
                try:
                    return ImageFont.truetype(fpath, size=size)
                except Exception:
                    pass
        return self._get_font(size, bold)

    def render_scene_frame(
        self,
        scene: Scene,
        plan: CodeVideoPlan,
        typing_progress: Optional[float] = None,
        frame_idx: int = 0,
    ) -> Image.Image:
        """Render a full 2560x1440 master visual frame for a given scene with optional typing progress."""
        img = Image.new("RGB", (self.width, self.height), color=self.IDE_EDITOR_BG)
        draw = ImageDraw.Draw(img)

        # 1. Window Title Bar (Top 50px)
        self._draw_window_titlebar(draw, scene, plan)

        # 2. Activity Bar (Left 70px, y: 50 -> 1395)
        self._draw_activity_bar(draw)

        # 3. Main Content based on visual mode & scene ID
        if scene.visual_mode.value == "TITLE_CARD" or scene.scene_id in ("S02", "S18", "S19"):
            self._draw_title_scene(draw, scene)
        elif scene.visual_mode.value == "DIAGRAM" or scene.scene_id in ("S03", "S04", "S11", "S17"):
            self._draw_diagram_scene(draw, scene)
        elif scene.scene_id == "S16":
            self._draw_checklist_scene(draw, scene)
        elif scene.visual_mode.value == "TERMINAL_ONLY" or scene.scene_id in ("S05", "S14"):
            self._draw_terminal_only_scene(draw, scene, typing_progress, frame_idx)
        else:
            self._draw_code_studio_scene(draw, scene, typing_progress, frame_idx)

        # 4. Status Bar (Bottom 45px, y: 1395 -> 1440)
        self._draw_status_bar(draw, scene)

        return img

    def _draw_window_titlebar(self, draw: ImageDraw.ImageDraw, scene: Scene, plan: CodeVideoPlan) -> None:
        """Draw authentic VS Code / Antigravity title bar."""
        draw.rectangle([(0, 0), (self.width, 50)], fill=self.IDE_TITLEBAR_BG)
        draw.line([(0, 50), (self.width, 50)], fill=self.IDE_BORDER, width=1)

        font_menu = self._get_font(20)
        font_search = self._get_font(20)
        font_bold = self._get_font(20, bold=True)

        # App branding
        draw.text((20, 14), "WindAgent IDE", font=font_bold, fill=self.ACCENT_BLUE)

        # Dynamic Menu Bar
        menus = ["File", "Edit", "Selection", "View", "Go", "Run", "Terminal", "Help"]
        x_menu = 195
        for m in menus:
            draw.text((x_menu, 14), m, font=font_menu, fill=(190, 190, 190))
            try:
                mw = font_menu.getlength(m)
            except Exception:
                mw = len(m) * 12
            x_menu += int(mw) + 22

        # Center Search / Command Palette Box
        search_box = [(850, 8), (1710, 42)]
        draw.rectangle(search_box, fill=(45, 45, 45), outline=(65, 65, 65), width=1)
        # Draw search magnifying glass vector
        draw.ellipse([(870, 18), (882, 30)], outline=(170, 170, 170), width=2)
        draw.line([(880, 28), (887, 35)], fill=(170, 170, 170), width=2)
        draw.text((900, 14), "agentic-studio — src/agent.py  (Ctrl + P)", font=font_search, fill=(170, 170, 170))

        # Right scene indicator & window buttons
        start_tc = f"{scene.start_ms // 60000:02d}:{(scene.start_ms % 60000)//1000:02d}"
        end_tc = f"{scene.end_ms // 60000:02d}:{(scene.end_ms % 60000)//1000:02d}"
        badge_text = f"SCENE {scene.scene_id} [{start_tc} – {end_tc}]"

        draw.rectangle([(1780, 10), (2080, 40)], fill=(40, 44, 52), outline=self.IDE_BORDER, width=1)
        draw.text((1800, 14), badge_text, font=font_bold, fill=self.ORANGE_ACCENT)

        draw.rectangle([(2100, 10), (2230, 40)], fill=(180, 40, 40), outline=(220, 50, 50), width=1)
        draw.text((2115, 14), "● REC SAFE", font=font_bold, fill=(255, 255, 255))

        # Window Controls: Minimize, Maximize, Close
        draw.line([(2405, 25), (2425, 25)], fill=(180, 180, 180), width=2)
        draw.rectangle([(2460, 16), (2478, 34)], outline=(180, 180, 180), width=2)
        draw.line([(2520, 16), (2536, 32)], fill=(180, 180, 180), width=2)
        draw.line([(2536, 16), (2520, 32)], fill=(180, 180, 180), width=2)

    def _draw_activity_bar(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw authentic left vertical Activity Bar matching Antigravity IDE."""
        draw.rectangle([(0, 50), (70, 1395)], fill=self.IDE_ACTIVITY_BG)
        draw.line([(70, 50), (70, 1395)], fill=self.IDE_BORDER, width=1)

        # 1. Explorer (Active - with blue indicator on left)
        draw.rectangle([(0, 60), (4, 110)], fill=self.IDE_STATUSBAR_BG)
        draw.rectangle([(23, 72), (39, 92)], outline=(255, 255, 255), width=2)
        draw.rectangle([(27, 76), (43, 96)], outline=(255, 255, 255), width=2)

        # 2. Search icon
        draw.ellipse([(25, 136), (41, 152)], outline=(140, 140, 140), width=2)
        draw.line([(37, 148), (46, 157)], fill=(140, 140, 140), width=2)

        # 3. Source Control with badge '24'
        draw.ellipse([(28, 198), (36, 206)], outline=(140, 140, 140), width=2)
        draw.ellipse([(28, 216), (36, 224)], outline=(140, 140, 140), width=2)
        draw.ellipse([(42, 206), (50, 214)], outline=(140, 140, 140), width=2)
        draw.line([(32, 206), (32, 216)], fill=(140, 140, 140), width=2)
        draw.line([(32, 211), (42, 211)], fill=(140, 140, 140), width=2)
        # Blue notification badge '24'
        draw.rectangle([(38, 192), (60, 208)], fill=self.IDE_STATUSBAR_BG)
        draw.text((41, 193), "24", font=self._get_font(12, bold=True), fill=(255, 255, 255))

        # 4. Run & Debug (Play triangle + bug)
        draw.polygon([(26, 260), (26, 280), (44, 270)], fill=(140, 140, 140))
        draw.ellipse([(38, 274), (48, 284)], outline=(140, 140, 140), width=2)

        # 5. Remote / Dev Containers [><]
        draw.rectangle([(23, 324), (47, 344)], outline=(140, 140, 140), width=2)
        draw.line([(28, 330), (32, 334)], fill=(140, 140, 140), width=2)
        draw.line([(32, 334), (28, 338)], fill=(140, 140, 140), width=2)
        draw.line([(42, 330), (38, 334)], fill=(140, 140, 140), width=2)
        draw.line([(38, 334), (42, 338)], fill=(140, 140, 140), width=2)

        # 6. Extensions (4 squares grid)
        draw.rectangle([(24, 388), (33, 397)], fill=(140, 140, 140))
        draw.rectangle([(37, 388), (46, 397)], fill=(140, 140, 140))
        draw.rectangle([(24, 401), (33, 410)], fill=(140, 140, 140))
        draw.rectangle([(37, 401), (46, 410)], outline=(140, 140, 140), width=2)

        # 7. Testing Beaker (Flask icon)
        draw.line([(33, 452), (37, 452)], fill=(140, 140, 140), width=2)
        draw.line([(33, 452), (33, 460)], fill=(140, 140, 140), width=2)
        draw.line([(37, 452), (37, 460)], fill=(140, 140, 140), width=2)
        draw.line([(33, 460), (24, 474)], fill=(140, 140, 140), width=2)
        draw.line([(37, 460), (46, 474)], fill=(140, 140, 140), width=2)
        draw.line([(24, 474), (46, 474)], fill=(140, 140, 140), width=2)

        # Bottom icons: Accounts & Settings
        # Profile
        draw.ellipse([(28, 1262), (42, 1276)], outline=(140, 140, 140), width=2)
        draw.arc([(22, 1276), (48, 1296)], 180, 360, fill=(140, 140, 140), width=2)
        # Settings Gear
        draw.ellipse([(28, 1332), (42, 1346)], outline=(140, 140, 140), width=3)
        draw.line([(35, 1327), (35, 1351)], fill=(140, 140, 140), width=2)
        draw.line([(23, 1339), (47, 1339)], fill=(140, 140, 140), width=2)

    def _draw_status_bar(self, draw: ImageDraw.ImageDraw, scene: Scene) -> None:
        """Draw authentic bottom Status Bar."""
        draw.rectangle([(0, 1395), (self.width, 1440)], fill=self.IDE_STATUSBAR_BG)

        font_stat = self._get_font(20)
        font_stat_b = self._get_font(20, bold=True)

        # Left items
        draw.rectangle([(0, 1395), (60, 1440)], fill=(0, 100, 180))
        draw.text((16, 1406), "><", font=font_stat_b, fill=(255, 255, 255))

        draw.text((80, 1406), "[git] main*", font=font_stat, fill=(255, 255, 255))
        draw.text((210, 1406), "0 v 1 ^", font=font_stat, fill=(255, 255, 255))
        draw.text((310, 1406), "0 Errors  0 Warnings", font=font_stat, fill=(255, 255, 255))
        draw.text((540, 1406), "• Domain: Clean Architecture (Zero SDK leaks)", font=font_stat, fill=(230, 240, 255))

        # Right items
        draw.text((1520, 1406), "Ln 14, Col 21", font=font_stat, fill=(255, 255, 255))
        draw.text((1690, 1406), "Spaces: 4", font=font_stat, fill=(255, 255, 255))
        draw.text((1820, 1406), "UTF-8", font=font_stat, fill=(255, 255, 255))
        draw.text((1920, 1406), "LF", font=font_stat, fill=(255, 255, 255))
        draw.text((1990, 1406), "{ } Python 3.11.8 ('agentic-studio')", font=font_stat, fill=(255, 255, 255))
        draw.text((2360, 1406), "* Antigravity: Ready", font=font_stat_b, fill=(255, 255, 200))
        draw.rectangle([(2520, 1408), (2536, 1424)], outline=(255, 255, 255), width=2)

    def _draw_code_studio_scene(
        self,
        draw: ImageDraw.ImageDraw,
        scene: Scene,
        typing_progress: Optional[float] = None,
        frame_idx: int = 0,
    ) -> None:
        """Render complete Code Studio with Antigravity Explorer tree matching user screenshot and real-time typing."""
        font_code = self._get_mono_font(28)
        font_sm = self._get_font(20)
        font_bold = self._get_font(22, bold=True)

        # -------------------------------------------------------------
        # 1. Primary Sidebar: Explorer (x: 70 -> 520, y: 50 -> 1395)
        # -------------------------------------------------------------
        sidebar_x1, sidebar_x2 = 70, 520
        draw.rectangle([(sidebar_x1, 50), (sidebar_x2, 1395)], fill=(20, 20, 20))
        draw.line([(sidebar_x2, 50), (sidebar_x2, 1395)], fill=self.IDE_BORDER, width=1)

        # Sidebar Header: Explorer with ...
        draw.text((sidebar_x1 + 20, 68), "Explorer", font=self._get_font(20, bold=False), fill=(200, 200, 200))
        draw.text((sidebar_x2 - 40, 64), "...", font=self._get_font(22, bold=True), fill=(140, 140, 140))

        # Root Section Accordion: agentic-studio (matching user screenshot)
        y_root = 106
        # Downward chevron vector for root
        draw.line([(sidebar_x1 + 16, y_root + 7), (sidebar_x1 + 21, y_root + 12)], fill=(180, 180, 180), width=2)
        draw.line([(sidebar_x1 + 21, y_root + 12), (sidebar_x1 + 26, y_root + 7)], fill=(180, 180, 180), width=2)
        # Folder icon for root
        draw.polygon([(sidebar_x1 + 34, y_root+3), (sidebar_x1 + 41, y_root+3), (sidebar_x1 + 44, y_root+6), (sidebar_x1 + 55, y_root+6), (sidebar_x1 + 55, y_root+18), (sidebar_x1 + 34, y_root+18)], fill=(220, 180, 100))
        draw.text((sidebar_x1 + 62, y_root - 1), "agentic-studio", font=self._get_font(21, bold=False), fill=(217, 125, 100))
        # Root modified dot on far right
        draw.ellipse([(sidebar_x2 - 35, y_root + 5), (sidebar_x2 - 25, y_root + 15)], fill=(150, 96, 80))

        # Guide lines
        guide_x1 = sidebar_x1 + 22
        guide_x2 = sidebar_x1 + 40
        draw.line([(guide_x1, y_root + 28), (guide_x1, y_root + 550)], fill=(45, 45, 45), width=1)

        # Children entries matching the user screenshot exactly:
        tree_entries = [
            (">", "folder", ".pytest_cache", (140, 140, 140), 1, False, None),
            ("v", "code_folder", "src", (126, 199, 148), 1, False, ("dot", (78, 142, 88))),
            (">", "folder", "__pycache__", (140, 140, 140), 2, False, None),
            (" ", "py_snake", "__init__.py", (137, 209, 133), 2, False, ("U", (115, 201, 145))),
            (" ", "py_snake", "agent.py", (137, 209, 133), 2, True, ("U", (115, 201, 145))),  # Active
            ("v", "code_folder", "tests", (217, 125, 100), 1, False, ("dot", (150, 96, 80))),
            (">", "folder", "__pycache__", (140, 140, 140), 2, False, None),
            (" ", "py_snake", "__init__.py", (137, 209, 133), 2, False, ("U", (115, 201, 145))),
            (" ", "py_snake", "test_agent.py", (229, 124, 101), 2, False, ("1, U", (229, 124, 101))),
            (" ", "doc", ".env.example", (137, 209, 133), 1, False, ("U", (115, 201, 145))),
            (" ", "git_diamond", ".gitignore", (137, 209, 133), 1, False, ("U", (115, 201, 145))),
            (" ", "py_snake", "pyproject.toml", (137, 209, 133), 1, False, ("U", (115, 201, 145))),
            (" ", "md_badge", "README.md", (220, 220, 170), 1, False, ("M", (229, 192, 123))),
        ]

        y_tree = 145
        for chevron, btype, name, col, indent, is_active, badge_info in tree_entries:
            if is_active:
                draw.rectangle([(sidebar_x1, y_tree - 4), (sidebar_x2, y_tree + 32)], fill=(42, 45, 46))
                draw.rectangle([(sidebar_x1, y_tree - 4), (sidebar_x1 + 3, y_tree + 32)], fill=self.IDE_STATUSBAR_BG)

            x_pos = sidebar_x1 + 10 + indent * 18

            # Sub-guide line for level 2
            if indent == 2:
                draw.line([(guide_x2, y_tree - 4), (guide_x2, y_tree + 32)], fill=(45, 45, 45), width=1)

            # Draw vector chevron
            if chevron == ">":
                draw.line([(x_pos + 4, y_tree + 7), (x_pos + 9, y_tree + 12)], fill=(160, 160, 160), width=2)
                draw.line([(x_pos + 9, y_tree + 12), (x_pos + 4, y_tree + 17)], fill=(160, 160, 160), width=2)
            elif chevron == "v":
                draw.line([(x_pos + 2, y_tree + 9), (x_pos + 7, y_tree + 14)], fill=(160, 160, 160), width=2)
                draw.line([(x_pos + 7, y_tree + 14), (x_pos + 12, y_tree + 9)], fill=(160, 160, 160), width=2)
            x_pos += 18

            # Draw icons
            if btype == "folder":
                draw.polygon([(x_pos+1, y_tree+4), (x_pos+7, y_tree+4), (x_pos+10, y_tree+7), (x_pos+20, y_tree+7), (x_pos+20, y_tree+19), (x_pos+1, y_tree+19)], fill=(220, 180, 100))
                x_pos += 26
            elif btype == "code_folder":
                draw.polygon([(x_pos+1, y_tree+4), (x_pos+7, y_tree+4), (x_pos+10, y_tree+7), (x_pos+20, y_tree+7), (x_pos+20, y_tree+19), (x_pos+1, y_tree+19)], fill=(220, 180, 100))
                draw.text((x_pos+4, y_tree+3), "</>", font=self._get_font(9, bold=True), fill=(40, 40, 40))
                x_pos += 26
            elif btype == "py_snake":
                # Python snake logo (cyan & yellow)
                draw.rectangle([(x_pos+1, y_tree+4), (x_pos+13, y_tree+12)], fill=(75, 139, 190))
                draw.ellipse([(x_pos+9, y_tree+6), (x_pos+11, y_tree+8)], fill=(255, 255, 255))
                draw.rectangle([(x_pos+7, y_tree+10), (x_pos+19, y_tree+18)], fill=(255, 212, 59))
                draw.ellipse([(x_pos+9, y_tree+13), (x_pos+11, y_tree+15)], fill=(255, 255, 255))
                x_pos += 26
            elif btype == "doc":
                draw.rectangle([(x_pos+2, y_tree+3), (x_pos+18, y_tree+19)], outline=(107, 139, 164), width=2)
                draw.line([(x_pos+11, y_tree+3), (x_pos+18, y_tree+10)], fill=(107, 139, 164), width=2)
                x_pos += 26
            elif btype == "git_diamond":
                draw.polygon([(x_pos+10, y_tree+2), (x_pos+19, y_tree+11), (x_pos+10, y_tree+20), (x_pos+1, y_tree+11)], fill=(240, 80, 50))
                draw.ellipse([(x_pos+8, y_tree+9), (x_pos+12, y_tree+13)], fill=(255, 255, 255))
                x_pos += 26
            elif btype == "md_badge":
                draw.rectangle([(x_pos+1, y_tree+4), (x_pos+22, y_tree+19)], fill=(81, 154, 186))
                draw.text((x_pos+2, y_tree+2), "M↓", font=self._get_font(12, bold=True), fill=(255, 255, 255))
                x_pos += 28

            draw.text((x_pos, y_tree), name, font=self._get_font(19, bold=is_active), fill=col)

            # Draw right-side Git badges
            if badge_info:
                b_type, b_col = badge_info
                if b_type == "dot":
                    draw.ellipse([(sidebar_x2 - 35, y_tree + 6), (sidebar_x2 - 25, y_tree + 16)], fill=b_col)
                elif b_type == "1, U":
                    draw.text((sidebar_x2 - 50, y_tree), "1, U", font=self._get_font(16, bold=True), fill=b_col)
                else:
                    draw.text((sidebar_x2 - 32, y_tree), b_type, font=self._get_font(16, bold=True), fill=b_col)

            y_tree += 36

        # -------------------------------------------------------------
        # 2. Editor Tabs Bar (x: 520 -> 2560, y: 50 -> 95)
        # -------------------------------------------------------------
        editor_x1 = sidebar_x2
        draw.rectangle([(editor_x1, 50), (self.width, 95)], fill=self.IDE_TABBAR_BG)
        draw.line([(editor_x1, 95), (self.width, 95)], fill=self.IDE_BORDER, width=1)

        # Active Tab: src/agent.py
        tab_w = 260
        draw.rectangle([(editor_x1, 50), (editor_x1 + tab_w, 95)], fill=self.IDE_EDITOR_BG)
        draw.rectangle([(editor_x1, 50), (editor_x1 + tab_w, 53)], fill=self.IDE_STATUSBAR_BG)  # Top blue indicator
        # Tab py badge
        draw.rectangle([(editor_x1 + 18, 62), (editor_x1 + 40, 78)], fill=(45, 95, 145))
        draw.text((editor_x1 + 21, 61), "py", font=self._get_font(13, bold=True), fill=(255, 212, 59))
        draw.text((editor_x1 + 48, 59), "agent.py", font=font_bold, fill=(255, 255, 255))
        draw.text((editor_x1 + tab_w - 30, 60), "x", font=font_sm, fill=(160, 160, 160))

        # Inactive Tab: test_agent.py
        draw.rectangle([(editor_x1 + tab_w, 50), (editor_x1 + tab_w * 2, 95)], fill=self.IDE_TABBAR_BG)
        draw.rectangle([(editor_x1 + tab_w + 18, 62), (editor_x1 + tab_w + 40, 78)], fill=(45, 95, 145))
        draw.text((editor_x1 + tab_w + 21, 61), "py", font=self._get_font(13, bold=True), fill=(255, 212, 59))
        draw.text((editor_x1 + tab_w + 48, 59), "test_agent.py", font=font_sm, fill=(150, 150, 150))
        draw.text((editor_x1 + tab_w * 2 - 30, 60), "x", font=font_sm, fill=(120, 120, 120))

        # Right tab controls
        draw.text((self.width - 120, 62), "[|]  ...", font=self._get_font(20), fill=(160, 160, 160))

        # -------------------------------------------------------------
        # 3. Breadcrumbs Bar (x: 520 -> 2560, y: 95 -> 135)
        # -------------------------------------------------------------
        draw.rectangle([(editor_x1, 95), (self.width, 135)], fill=self.IDE_EDITOR_BG)
        draw.line([(editor_x1, 135), (self.width, 135)], fill=self.IDE_BORDER, width=1)
        draw.text((editor_x1 + 25, 102), "agentic-studio  >  src  >  agent.py  >  class Agent  >  def run", font=self._get_font(20), fill=(160, 160, 160))

        # -------------------------------------------------------------
        # 4. Code Editor Canvas & Line Gutter (y: 135 -> 950)
        # -------------------------------------------------------------
        gutter_w = 90
        code_start_x = editor_x1 + gutter_w + 25
        minimap_x1 = self.width - 160

        draw.rectangle([(editor_x1, 135), (self.width, 950)], fill=self.IDE_EDITOR_BG)
        draw.rectangle([(editor_x1, 135), (editor_x1 + gutter_w, 950)], fill=(33, 33, 33))
        draw.line([(editor_x1 + gutter_w, 135), (editor_x1 + gutter_w, 950)], fill=self.IDE_BORDER, width=1)

        # Code lines tokenization & progressive human typing
        code_lines = self._get_scene_code(scene.scene_id)
        y_code = 160
        line_h = 48

        # Pure top-to-bottom character-by-character human typing simulation
        if typing_progress is not None and typing_progress < 1.0:
            total_chars = sum(len(line_text) + 1 for line_text, _ in code_lines)
            chars_to_show = int(round(total_chars * max(0.0, min(1.0, typing_progress))))
            curr_budget = chars_to_show
        else:
            curr_budget = None

        for idx, (line_text, is_highlighted) in enumerate(code_lines, start=1):
            if curr_budget is not None:
                line_len = len(line_text)
                if curr_budget > line_len:
                    # Line is fully typed, consume characters + Enter newline
                    rendered_text = line_text
                    is_current_typing = False
                    curr_budget -= (line_len + 1)
                elif curr_budget >= 0:
                    # Currently typing this line letter by letter
                    rendered_text = line_text[:curr_budget]
                    is_current_typing = True
                    curr_budget = -1  # Exceeded budget, subsequent lines not yet typed
                else:
                    # Not yet reached in typing progression
                    rendered_text = None
                    is_current_typing = False
            else:
                # Fully rendered static frame
                rendered_text = line_text
                is_current_typing = False

            if rendered_text is None:
                # Line has not been typed yet: show blank line in editor
                y_code += line_h
                continue

            # Row highlight:
            # When typing: highlight the currently active typing row
            # When finished (teaching mode): highlight key conceptual lines
            show_row_hl = is_current_typing if (curr_budget is not None) else is_highlighted
            if show_row_hl:
                draw.rectangle([(editor_x1, y_code - 6), (minimap_x1 - 10, y_code + line_h - 6)], fill=self.SYN_HIGHLIGHT_BG)
                draw.rectangle([(editor_x1, y_code - 6), (editor_x1 + 4, y_code + line_h - 6)], fill=self.SYN_ACCENT_BLUE)
                draw.rectangle([(editor_x1 + gutter_w - 4, y_code - 6), (editor_x1 + gutter_w, y_code + line_h - 6)], fill=self.SUCCESS_GREEN)

            # Gutter Line Number
            num_str = f"{idx:3d}"
            draw.text((editor_x1 + 20, y_code), num_str, font=font_code, fill=(220, 220, 220) if show_row_hl else (100, 100, 100))

            # Render syntax tokens
            self._render_syntax_tokens(draw, rendered_text, code_start_x, y_code, font_code)

            # Blinking cursor: follow the typing head exactly
            if is_current_typing or (curr_budget is None and idx == len(code_lines)):
                try:
                    cw = font_code.getlength(rendered_text)
                except Exception:
                    cw = len(rendered_text) * 16.8
                cur_x = code_start_x + int(cw)
                if (frame_idx // 15) % 2 == 0 or is_current_typing:
                    draw.rectangle([(cur_x + 1, y_code + 2), (cur_x + 3, y_code + 36)], fill=(255, 255, 255))

            y_code += line_h

        # Minimap (Right side)
        draw.rectangle([(minimap_x1, 135), (self.width, 950)], fill=(28, 28, 28))
        draw.line([(minimap_x1, 135), (minimap_x1, 950)], fill=self.IDE_BORDER, width=1)
        # Draw mini lines in minimap
        y_mini = 150
        for ltext, hl in code_lines:
            mini_w = min(120, max(20, len(ltext) * 3))
            draw.rectangle([(minimap_x1 + 15, y_mini), (minimap_x1 + 15 + mini_w, y_mini + 4)], fill=(120, 160, 220) if hl else (70, 70, 70))
            y_mini += 8
        # Minimap slider view box
        draw.rectangle([(minimap_x1 + 5, 145), (self.width - 5, y_mini + 20)], outline=(100, 100, 100), width=1)

        # -------------------------------------------------------------
        # 5. Integrated Terminal Panel (y: 950 -> 1395)
        # -------------------------------------------------------------
        draw.rectangle([(editor_x1, 950), (self.width, 1395)], fill=self.IDE_TERMINAL_BG)
        draw.line([(editor_x1, 950), (self.width, 950)], fill=self.IDE_BORDER, width=2)

        # Terminal Tabs Header
        term_tabs_y = 960
        draw.text((editor_x1 + 30, term_tabs_y), "PROBLEMS  0", font=self._get_font(20), fill=(140, 140, 140))
        draw.text((editor_x1 + 200, term_tabs_y), "OUTPUT", font=self._get_font(20), fill=(140, 140, 140))
        draw.text((editor_x1 + 320, term_tabs_y), "DEBUG CONSOLE", font=self._get_font(20), fill=(140, 140, 140))

        # ACTIVE: TERMINAL Tab
        draw.text((editor_x1 + 520, term_tabs_y), "TERMINAL", font=self._get_font(20, bold=True), fill=(255, 255, 255))
        draw.rectangle([(editor_x1 + 520, term_tabs_y + 26), (editor_x1 + 625, term_tabs_y + 29)], fill=self.IDE_STATUSBAR_BG)

        draw.text((editor_x1 + 670, term_tabs_y), "PORTS", font=self._get_font(20), fill=(140, 140, 140))

        # Terminal action icons on right
        draw.rectangle([(self.width - 480, term_tabs_y - 2), (self.width - 280, term_tabs_y + 26)], fill=(40, 40, 40), outline=self.IDE_BORDER, width=1)
        draw.text((self.width - 465, term_tabs_y), "1: powershell ⌵", font=self._get_font(18), fill=(200, 200, 200))
        draw.text((self.width - 240, term_tabs_y), "+   ◫   🗑   ✕", font=self._get_font(20), fill=(160, 160, 160))

        draw.line([(editor_x1, term_tabs_y + 35), (self.width, term_tabs_y + 35)], fill=self.IDE_BORDER, width=1)

        # Terminal Content
        font_term = self._get_mono_font(24)
        term_lines = [
            ("PS D:\\code\\agentic-studio> pytest", (255, 255, 255)),
            ("============================= test session starts =============================", (130, 130, 130)),
            ("rootdir: D:\\code\\agentic-studio", (130, 130, 130)),
            ("collected 2 items", (130, 130, 130)),
            ("tests/test_agent.py ..                                                   [100%]", self.SUCCESS_GREEN),
            ("============================== 2 passed in 0.04s ===============================", self.SUCCESS_GREEN),
            ("PS D:\\code\\agentic-studio> python -m src.agent", (255, 255, 255)),
            ("[Agentic Studio v0.1] Simple Agent response: 'Clean architecture initialized.'", self.ACCENT_BLUE),
        ]
        y_tline = 1015
        for tline, tcol in term_lines:
            draw.text((editor_x1 + 35, y_tline), tline, font=font_term, fill=tcol)
            y_tline += 38

    def _render_syntax_tokens(self, draw: ImageDraw.ImageDraw, line: str, x: int, y: int, font: ImageFont.ImageFont) -> None:
        """Tokenize a Python line and render with authentic VS Code Dark+ syntax colors."""
        if not line:
            return

        # Comment line
        if line.strip().startswith("#"):
            draw.text((x, y), line, font=font, fill=self.SYN_COMMENT)
            return

        # Tokenize by regex preserving spaces and words
        import re
        tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*|\'[^\']*\'|"[^"]*"|@[a-zA-Z0-9_()=,\'"]+|[0-9.]+|->|==|!=|<=|>=|[=+\-*/%&|^~:,()\[\]{}]|\s+|.', line)

        KEYWORDS = {
            "def", "class", "return", "from", "import", "if", "else", "elif",
            "raise", "try", "except", "finally", "while", "for", "in", "is",
            "and", "or", "not", "with", "as", "pass", "break", "continue",
            "None", "True", "False", "async", "await", "yield"
        }
        TYPES = {
            "str", "int", "float", "bool", "list", "dict", "set", "tuple", "bytes",
            "Sequence", "Protocol", "Literal", "Optional", "List", "Dict", "Set",
            "Tuple", "Any", "Message", "AgentConfig", "LLMClient", "FakeLLMClient",
            "Agent", "ValueError", "Exception"
        }
        FUNCTIONS = {
            "run", "generate", "validate", "__post_init__", "__init__", "append",
            "pop", "strip", "len", "print", "range", "enumerate", "isinstance",
            "test_agent_run_with_fake_llm"
        }

        curr_x = x
        for tok in tokens:
            color = self.SYN_WHITE
            if tok in KEYWORDS:
                color = self.SYN_KEYWORD
            elif tok in TYPES:
                color = self.SYN_TYPE
            elif tok in FUNCTIONS:
                color = self.SYN_FUNCTION
            elif tok.startswith("@"):
                color = self.SYN_DECORATOR
            elif (tok.startswith("'") and tok.endswith("'")) or (tok.startswith('"') and tok.endswith('"')):
                color = self.SYN_STRING
            elif tok.replace(".", "", 1).isdigit():
                color = self.SYN_NUMBER
            elif tok.startswith("#"):
                color = self.SYN_COMMENT
            elif tok in ("self", "config", "client", "messages", "user_input", "prompt", "responses", "calls", "name", "system_prompt", "model", "temperature", "role", "content"):
                color = self.SYN_VARIABLE
            elif tok in ("=", "->", ":", "(", ")", "[", "]", "{", "}", ",", "."):
                color = self.SYN_PUNCTUATION

            draw.text((curr_x, y), tok, font=font, fill=color)
            # Advance x position based on token text length
            # Monospace character width estimation or font.getlength
            try:
                tw = font.getlength(tok)
            except Exception:
                tw = len(tok) * 16
            curr_x += int(tw)

    def _draw_terminal_only_scene(
        self,
        draw: ImageDraw.ImageDraw,
        scene: Scene,
        typing_progress: Optional[float] = None,
        frame_idx: int = 0,
    ) -> None:
        """Render full-view terminal IDE layout for scenes S05 & S14 with progressive typing."""
        # Draw base IDE frames
        self._draw_activity_bar(draw)

        # Full Terminal Container (x: 70 -> 2560, y: 50 -> 1395)
        draw.rectangle([(70, 50), (self.width, 1395)], fill=self.IDE_TERMINAL_BG)

        # Terminal Tab Bar
        draw.rectangle([(70, 50), (self.width, 100)], fill=self.IDE_TABBAR_BG)
        draw.line([(70, 100), (self.width, 100)], fill=self.IDE_BORDER, width=1)

        draw.text((100, 68), "PROBLEMS  0", font=self._get_font(20), fill=(140, 140, 140))
        draw.text((270, 68), "OUTPUT", font=self._get_font(20), fill=(140, 140, 140))
        draw.text((390, 68), "DEBUG CONSOLE", font=self._get_font(20), fill=(140, 140, 140))

        # ACTIVE: TERMINAL
        draw.text((590, 68), "TERMINAL", font=self._get_font(20, bold=True), fill=(255, 255, 255))
        draw.rectangle([(590, 96), (695, 99)], fill=self.IDE_STATUSBAR_BG)

        draw.text((740, 68), "PORTS", font=self._get_font(20), fill=(140, 140, 140))
        draw.text((self.width - 250, 68), "1: powershell ⌵   +   🗑", font=self._get_font(20), fill=(200, 200, 200))

        font_term = self._get_mono_font(32)
        y = 150
        if scene.scene_id == "S05":
            lines = [
                ("PS D:\\code> mkdir agentic-studio", (255, 255, 255)),
                ("PS D:\\code> cd agentic-studio", (255, 255, 255)),
                ("PS D:\\code\\agentic-studio> git init", (255, 255, 255)),
                ("Initialized empty Git repository in D:/code/agentic-studio/.git/", self.SUCCESS_GREEN),
                ("PS D:\\code\\agentic-studio> code .", (255, 255, 255)),
                ("Launching Visual Studio Code in workspace D:\\code\\agentic-studio...", self.ACCENT_BLUE),
            ]
        elif scene.scene_id == "S14":
            lines = [
                ("PS D:\\code\\agentic-studio> python -m src.agent", (255, 255, 255)),
                ("[Agentic Studio v0.1] Khởi tạo Simple Agent thành công.", self.ACCENT_BLUE),
                ("User Prompt: 'Giải thích recursion bằng một ví dụ đơn giản.'", self.ORANGE_ACCENT),
                ("--- Model Response ---", (160, 160, 160)),
                ("Đệ quy (Recursion) là kỹ thuật một hàm tự gọi lại chính nó để giải quyết bài toán nhỏ hơn.", self.TEXT_WHITE),
                ("Ví dụ kinh điển: Tính giai thừa n! = n * (n-1)!, với điểm dừng là 0! = 1.", self.TEXT_WHITE),
                ("----------------------", (160, 160, 160)),
                ("[Process exited with status 0]", self.SUCCESS_GREEN),
            ]
        else:
            lines = [
                ("PS D:\\code\\agentic-studio> pytest", (255, 255, 255)),
                ("============================= test session starts =============================", (130, 130, 130)),
                ("rootdir: D:\\code\\agentic-studio", (130, 130, 130)),
                ("collected 2 items", (130, 130, 130)),
                ("tests/test_agent.py ..                                                   [100%]", self.SUCCESS_GREEN),
                ("============================== 2 passed in 0.04s ===============================", self.SUCCESS_GREEN),
            ]

        if typing_progress is not None and typing_progress < 1.0:
            total_chars = sum(len(txt) + 1 for txt, _ in lines)
            curr_budget = int(round(total_chars * max(0.0, min(1.0, typing_progress))))
            for text, col in lines:
                line_len = len(text)
                if curr_budget > line_len:
                    draw.text((120, y), text, font=font_term, fill=col)
                    curr_budget -= (line_len + 1)
                elif curr_budget >= 0:
                    partial = text[:curr_budget]
                    draw.text((120, y), partial, font=font_term, fill=col)
                    # Blinking block cursor
                    try:
                        pw = font_term.getlength(partial)
                    except Exception:
                        pw = len(partial) * 19.2
                    if (frame_idx // 15) % 2 == 0 or True:
                        draw.rectangle([(120 + int(pw) + 2, y + 4), (120 + int(pw) + 18, y + 36)], fill=(255, 255, 255))
                    curr_budget = -1
                else:
                    break
                y += 65
        else:
            for text, col in lines:
                draw.text((120, y), text, font=font_term, fill=col)
                y += 65

    def _draw_title_scene(self, draw: ImageDraw.ImageDraw, scene: Scene) -> None:
        """Render Title Card with VS Code Dark+ Studio aesthetic."""
        self._draw_activity_bar(draw)

        font_hero = self._get_font(68, bold=True)
        font_sub = self._get_font(40, bold=True)
        font_body = self._get_font(32)

        # Center Card inside IDE canvas
        card_box = [(150, 100), (self.width - 80, 1350)]
        draw.rectangle(card_box, fill=self.IDE_SIDEBAR_BG, outline=self.IDE_BORDER, width=2)

        if scene.scene_id == "S02":
            draw.text((250, 180), "WINDAGENT TUTORIAL SERIES", font=self._get_font(36, bold=True), fill=self.ORANGE_ACCENT)
            draw.text((250, 260), "VIẾT AI AGENT ĐẦU TIÊN BẰNG PYTHON", font=font_hero, fill=self.TEXT_WHITE)
            draw.text((250, 370), "Xây dựng Simple Agent Core từ con số 0 — Không thư viện cồng kềnh", font=font_sub, fill=self.ACCENT_BLUE)

            # Highlights box
            draw.rectangle([(250, 480), (self.width - 160, 1250)], fill=self.IDE_EDITOR_BG, outline=self.IDE_BORDER, width=2)
            draw.text((300, 540), "• Tách bạch Clean Architecture: Domain Core vs Infrastructure Provider", font=font_body, fill=self.TEXT_WHITE)
            draw.text((300, 640), "• Xây dựng Message Dataclass, AgentConfig, LLMClient Protocol", font=font_body, fill=self.TEXT_WHITE)
            draw.text((300, 740), "• Kiểm thử đơn vị Fake LLM hoàn toàn offline (Pytest 2 passed)", font=font_body, fill=self.SUCCESS_GREEN)
            draw.text((300, 840), "• Đóng gói Git Milestone v0.1 — Chuẩn bị nền tảng cho Tool Calling", font=font_body, fill=self.TEXT_WHITE)
            draw.text((300, 960), "Môi trường: Visual Studio Code / Antigravity IDE • Python 3.11+", font=self._get_font(28), fill=self.TEXT_MUTED)

        elif scene.scene_id == "S18":
            draw.text((250, 180), "GIT RELEASE MILESTONE", font=self._get_font(36, bold=True), fill=self.SUCCESS_GREEN)
            draw.text((250, 260), "Agentic Studio v0.1 — Simple Agent", font=font_hero, fill=self.TEXT_WHITE)
            draw.text((250, 370), "Commit & Release Tags đã được niêm phong trong tutorial repository", font=font_sub, fill=self.ACCENT_BLUE)
            draw.rectangle([(250, 480), (self.width - 160, 1250)], fill=self.IDE_EDITOR_BG, outline=self.IDE_BORDER, width=2)
            draw.text((300, 560), "$ git add .", font=self._get_mono_font(36), fill=self.TEXT_MUTED)
            draw.text((300, 660), '$ git commit -m "feat: build simple agent core"', font=self._get_mono_font(36), fill=self.TEXT_WHITE)
            draw.text((300, 760), "$ git tag video-02", font=self._get_mono_font(36), fill=self.ACCENT_BLUE)
            draw.text((300, 860), "$ git tag v0.1", font=self._get_mono_font(36), fill=self.SUCCESS_GREEN)

        elif scene.scene_id == "S19":
            draw.text((250, 180), "NEXT EPISODE TEASER", font=self._get_font(36, bold=True), fill=self.PURPLE_ACCENT)
            draw.text((250, 260), "VIDEO 03 — TOOL CALLING", font=font_hero, fill=self.TEXT_WHITE)
            draw.text((250, 370), "Tool Calling hoạt động bên trong như thế nào?", font=font_sub, fill=self.ACCENT_BLUE)
            draw.rectangle([(250, 480), (self.width - 160, 1250)], fill=self.IDE_EDITOR_BG, outline=self.IDE_BORDER, width=2)
            draw.text((300, 560), "Hôm nay (Video 02):  User  ->  Agent  ->  LLM  ->  Answer", font=font_body, fill=self.TEXT_MUTED)
            draw.text((300, 680), "Tập tiếp theo (Video 03): User  ->  Agent  ->  LLM  ->  TOOL EXECUTION  ->  Answer", font=font_body, fill=self.ORANGE_ACCENT)
            draw.text((300, 800), "Nguyên lý cốt lõi: LLM KHÔNG tự chạy code, LLM chỉ phát tín hiệu gọi Tool!", font=font_body, fill=self.SUCCESS_GREEN)

    def _draw_diagram_scene(self, draw: ImageDraw.ImageDraw, scene: Scene) -> None:
        """Render architecture diagram scene in IDE dark theme style."""
        self._draw_activity_bar(draw)

        font_title = self._get_font(42, bold=True)
        font_box = self._get_font(32, bold=True)
        font_desc = self._get_font(28)

        card_box = [(140, 90), (self.width - 60, 1360)]
        draw.rectangle(card_box, fill=self.IDE_SIDEBAR_BG, outline=self.IDE_BORDER, width=2)

        if scene.scene_id in ("S01", "S04"):
            draw.text((200, 140), "KIẾN TRÚC SIMPLE AGENT (v0.1)", font=font_title, fill=self.ACCENT_BLUE)
            draw.text((200, 205), "Mô hình luồng dữ liệu 1 vòng đơn giản: User -> Agent -> LLM -> Answer", font=font_desc, fill=self.TEXT_MUTED)

            # Diagram boxes
            boxes = [
                (240, 420, 590, 620, "User Prompt\n(Input)", self.IDE_BORDER, self.TEXT_WHITE),
                (740, 420, 1140, 620, "Agent Core\n(Orchestration)", self.ACCENT_BLUE, self.TEXT_WHITE),
                (1290, 420, 1690, 620, "LLMClient\n(Protocol)", self.ORANGE_ACCENT, self.TEXT_WHITE),
                (1840, 420, 2290, 620, "Final Answer\n(Output)", self.SUCCESS_GREEN, self.TEXT_WHITE),
            ]
            for x1, y1, x2, y2, text, outline_color, fill_color in boxes:
                draw.rectangle([(x1, y1), (x2, y2)], fill=self.IDE_EDITOR_BG, outline=outline_color, width=3)
                draw.text((x1 + 30, y1 + 50), text, font=font_box, fill=fill_color)

            # Connecting arrows
            draw.text((630, 490), "===>", font=font_box, fill=self.ACCENT_BLUE)
            draw.text((1180, 490), "===>", font=font_box, fill=self.ACCENT_BLUE)
            draw.text((1730, 490), "===>", font=font_box, fill=self.ACCENT_BLUE)

            # Note box at bottom
            draw.rectangle([(240, 780), (2290, 1180)], fill=self.IDE_EDITOR_BG, outline=self.IDE_BORDER, width=2)
            draw.text((280, 830), "• Domain Layer: Agent gom System Prompt + User Message thành message list.", font=font_desc, fill=self.TEXT_PRIMARY)
            draw.text((280, 920), "• LLMClient: Gửi sang Provider (hoặc Fake offline) và trả về text đơn thuần.", font=font_desc, fill=self.TEXT_PRIMARY)
            draw.text((280, 1010), "• Chưa có Tool Calling, Memory hay Agent Loop phức tạp ở milestone này.", font=font_desc, fill=self.ORANGE_ACCENT)

        elif scene.scene_id == "S11":
            draw.text((200, 140), "IS THIS AN AGENT? — PHÂN TÍCH COGNITIVE LOOP", font=font_title, fill=self.ORANGE_ACCENT)
            draw.text((200, 205), "Chu trình nhận thức chuẩn: Observe -> Decide -> Act -> Observe", font=font_desc, fill=self.TEXT_MUTED)

            cboxes = [
                (280, 380, 720, 580, "1. OBSERVE\n(Nhận câu hỏi)", self.SUCCESS_GREEN),
                (1020, 380, 1460, 580, "2. DECIDE\n(LLM suy luận)", self.SUCCESS_GREEN),
                (1760, 380, 2200, 580, "3. ACT (Chưa có)\n(Gọi Tool / Execute)", self.IDE_BORDER),
            ]
            for x1, y1, x2, y2, text, col in cboxes:
                draw.rectangle([(x1, y1), (x2, y2)], fill=self.IDE_EDITOR_BG, outline=col, width=3)
                draw.text((x1 + 30, y1 + 50), text, font=font_box, fill=col if col != self.IDE_BORDER else self.TEXT_MUTED)

            draw.text((780, 460), "===>", font=font_box, fill=self.ACCENT_BLUE)
            draw.text((1520, 460), "===>", font=font_box, fill=self.IDE_BORDER)

            draw.rectangle([(280, 720), (2200, 1200)], fill=self.IDE_EDITOR_BG, outline=self.IDE_BORDER, width=2)
            draw.text((330, 770), "Đánh giá phạm vi v0.1:", font=self._get_font(32, bold=True), fill=self.TEXT_WHITE)
            draw.text((330, 860), "[PASS] Có thể coi là Simple Agent / Stateless Agent vì có System Prompt & cấu trúc Agent Core.", font=font_desc, fill=self.SUCCESS_GREEN)
            draw.text((330, 950), "[NOT YET] Chưa phải Autonomous Agent hoàn chỉnh vì chưa có vòng lặp phản hồi (Loop) và Tool Calling.", font=font_desc, fill=self.ORANGE_ACCENT)

        elif scene.scene_id == "S17":
            draw.text((200, 140), "CLEAN ARCHITECTURE REVIEW: TÁCH BẠCH DOMAIN & INFRA", font=font_title, fill=self.ACCENT_BLUE)
            draw.text((200, 205), "Quy tắc bất biến: Domain Core KHÔNG phụ thuộc SDK bên ngoài", font=font_desc, fill=self.TEXT_MUTED)

            # Left Box: DOMAIN
            draw.rectangle([(240, 340), (1180, 1220)], fill=self.IDE_EDITOR_BG, outline=self.ACCENT_BLUE, width=3)
            draw.text((290, 380), "DOMAIN CORE (Pure Python)", font=self._get_font(34, bold=True), fill=self.ACCENT_BLUE)
            draw.text((290, 480), "• Message (frozen dataclass)", font=font_desc, fill=self.TEXT_WHITE)
            draw.text((290, 580), "• AgentConfig (dataclass)", font=font_desc, fill=self.TEXT_WHITE)
            draw.text((290, 680), "• LLMClient (Protocol)", font=font_desc, fill=self.TEXT_WHITE)
            draw.text((290, 780), "• FakeLLMClient (Test mock)", font=font_desc, fill=self.SUCCESS_GREEN)
            draw.text((290, 880), "• Agent (Run loop core)", font=font_desc, fill=self.TEXT_WHITE)
            draw.text((290, 1040), "Zero third-party SDK dependencies", font=self._get_font(26, bold=True), fill=self.SUCCESS_GREEN)

            # Right Box: INFRASTRUCTURE
            draw.rectangle([(1320, 340), (2260, 1220)], fill=self.IDE_EDITOR_BG, outline=self.ORANGE_ACCENT, width=3)
            draw.text((1370, 380), "INFRASTRUCTURE (Adapters)", font=self._get_font(34, bold=True), fill=self.ORANGE_ACCENT)
            draw.text((1370, 480), "• OpenAI / Anthropic / Google SDKs", font=font_desc, fill=self.TEXT_MUTED)
            draw.text((1370, 580), "• HTTP Network Calls & Retries", font=font_desc, fill=self.TEXT_MUTED)
            draw.text((1370, 680), "• API Key & Environment Loading", font=font_desc, fill=self.TEXT_MUTED)
            draw.text((1370, 780), "• Token Quotas & Error Handling", font=font_desc, fill=self.TEXT_MUTED)
            draw.text((1370, 1040), "Isolated outside the domain core", font=self._get_font(26, bold=True), fill=self.ORANGE_ACCENT)

    def _draw_checklist_scene(self, draw: ImageDraw.ImageDraw, scene: Scene) -> None:
        """Render Checklist Scene with VS Code Dark+ styling."""
        self._draw_activity_bar(draw)

        font_title = self._get_font(42, bold=True)
        font_item = self._get_font(32)
        font_desc = self._get_font(26)

        card_box = [(140, 90), (self.width - 60, 1360)]
        draw.rectangle(card_box, fill=self.IDE_SIDEBAR_BG, outline=self.IDE_BORDER, width=2)

        draw.text((200, 140), "NOT YET — 7 TÍNH NĂNG CHƯA CÓ TRONG VIDEO 02", font=font_title, fill=self.RED_ACCENT)
        draw.text((200, 205), "Giữ phạm vi bài học tập trung vào cốt lõi, không đưa các tính năng nâng cao vào sớm", font=font_desc, fill=self.TEXT_MUTED)

        checklist = [
            ("Tool Calling (Hàm công cụ ngoại vi)", "Sẽ có ở Video 03"),
            ("Agent Loop (Vòng lặp tự hành)", "Sẽ có ở Video 04"),
            ("Memory (Bộ nhớ ngắn hạn & dài hạn)", "Sẽ có ở Video 05"),
            ("RAG (Truy xuất dữ liệu bên ngoài)", "Sẽ có ở Video 06"),
            ("Planning (Lập kế hoạch đa bước)", "Sẽ có ở Video 07"),
            ("Multi-Agent (Hợp tác đa tác tử)", "Sẽ có ở Video 08"),
            ("Orchestration (Điều phối phức tạp)", "Sẽ có ở Video 09"),
        ]

        y_offset = 320
        for item, note in checklist:
            draw.rectangle([(200, y_offset), (self.width - 120, y_offset + 95)], fill=self.IDE_EDITOR_BG, outline=self.IDE_BORDER, width=2)
            # Vector Red Cross
            draw.line([(240, y_offset + 32), (258, y_offset + 50)], fill=self.RED_ACCENT, width=4)
            draw.line([(258, y_offset + 32), (240, y_offset + 50)], fill=self.RED_ACCENT, width=4)
            draw.text((290, y_offset + 28), item, font=font_item, fill=self.TEXT_WHITE)
            draw.text((1700, y_offset + 30), f"[{note}]", font=self._get_font(26), fill=self.TEXT_MUTED)
            y_offset += 120

    def _get_scene_code(self, scene_id: str) -> List[Tuple[str, bool]]:
        """Return code lines and active highlight flags for each scene."""
        if scene_id == "S01":
            return [
                ("# Agentic Studio v0.1 — Live Execution Demo", False),
                ("from src.agent import Agent, AgentConfig, FakeLLMClient", False),
                ("", False),
                ("config = AgentConfig(name='SimpleAgent')", True),
                ("client = FakeLLMClient(['Clean architecture initialized.'])", True),
                ("agent = Agent(config=config, client=client)", True),
                ("response = agent.run('Hello, what can you do?')", True),
                ("print(f'[Agentic Studio v0.1] Simple Agent response: {response}')", True),
            ]
        elif scene_id == "S06":
            return [
                ("from dataclasses import dataclass", False),
                ("from typing import Literal, Protocol, Sequence", False),
                ("", False),
                ("@dataclass(frozen=True)", True),
                ("class Message:", True),
                ("    role: Literal['system', 'user', 'assistant']", True),
                ("    content: str", True),
                ("", False),
                ("    def __post_init__(self) -> None:", False),
                ("        if not self.content.strip():", False),
                ("            raise ValueError('Message content cannot be empty')", False),
            ]
        elif scene_id == "S07":
            return [
                ("@dataclass", False),
                ("class AgentConfig:", True),
                ("    name: str = 'SimpleAgent'", True),
                ("    system_prompt: str = 'You are a helpful AI assistant.'", True),
                ("    model: str = 'gemini-3.7-flash'", True),
                ("    temperature: float = 0.7", True),
                ("", False),
                ("    def validate(self) -> None:", False),
                ("        if not (0.0 <= self.temperature <= 2.0):", False),
                ("            raise ValueError('Temperature must be between 0.0 and 2.0')", False),
            ]
        elif scene_id == "S08":
            return [
                ("class LLMClient(Protocol):", True),
                ("    \"\"\"Domain protocol for LLM providers. Clean Architecture boundary.\"\"\"", False),
                ("", False),
                ("    def generate(self, messages: Sequence[Message], config: AgentConfig) -> str:", True),
                ("        ...", True),
                ("", False),
                ("# Domain core does not import OpenAI, Anthropic, or Google SDKs!", False),
                ("# Any provider can be plugged in by implementing this single method.", False),
            ]
        elif scene_id == "S09":
            return [
                ("class FakeLLMClient(LLMClient):", True),
                ("    \"\"\"Deterministic offline mock for lightning-fast unit tests.\"\"\"", False),
                ("", False),
                ("    def __init__(self, responses: Optional[Sequence[str]] = None) -> None:", False),
                ("        self._responses = list(responses or ['Fake deterministic answer'])", False),
                ("        self.calls: list[Sequence[Message]] = []", False),
                ("", False),
                ("    def generate(self, messages: Sequence[Message], config: AgentConfig) -> str:", True),
                ("        self.calls.append(messages)", False),
                ("        return self._responses.pop(0) if self._responses else 'OK'", True),
            ]
        elif scene_id == "S10":
            return [
                ("class Agent:", True),
                ("    def __init__(self, config: AgentConfig, client: LLMClient) -> None:", True),
                ("        self.config = config", False),
                ("        self.client = client", False),
                ("", False),
                ("    def run(self, user_input: str) -> str:", True),
                ("        messages = [", True),
                ("            Message(role='system', content=self.config.system_prompt),", True),
                ("            Message(role='user', content=user_input),", True),
                ("        ]", True),
                ("        return self.client.generate(messages, self.config)", True),
            ]
        elif scene_id == "S12":
            return [
                ("# Infrastructure Layer (Separate module outside Domain Core)", False),
                ("class GeminiProviderAdapter(LLMClient):", True),
                ("    def __init__(self, api_key: str) -> None:", False),
                ("        self.api_key = api_key", False),
                ("", False),
                ("    def generate(self, messages: Sequence[Message], config: AgentConfig) -> str:", True),
                ("        # SDK import is strictly isolated to this adapter file", False),
                ("        from google import genai", False),
                ("        client = genai.Client(api_key=self.api_key)", False),
                ("        response = client.models.generate_content(model=config.model, ...)", False),
                ("        return response.text", False),
            ]
        elif scene_id == "S13":
            return [
                ("# .env.example (Safe to commit to Git)", False),
                ("GEMINI_API_KEY=your_api_key_here", True),
                ("OPENAI_API_KEY=your_api_key_here", True),
                ("", False),
                ("# .gitignore", False),
                (".env", True),
                (".env.local", True),
                ("__pycache__/", False),
                ("", False),
                ("# SECURITY RULE: NEVER HARDCODE API KEYS IN SOURCE CODE!", True),
            ]
        else:
            return [
                ("def test_agent_run_with_fake_llm():", True),
                ("    config = AgentConfig(name='TestAgent')", False),
                ("    fake_client = FakeLLMClient(['Recursion explanation answer'])", False),
                ("    agent = Agent(config=config, client=fake_client)", False),
                ("    answer = agent.run('Explain recursion')", True),
                ("    assert answer == 'Recursion explanation answer'", True),
                ("    assert len(fake_client.calls) == 1", True),
            ]


class RealMasterVideoSynthesizer:
    """Synthesizes genuine playable MP4 videos for Video 02 using FFmpeg."""

    @classmethod
    def synthesize_video(
        cls,
        plan: CodeVideoPlan,
        output_dir: Path,
        fast_mode: bool = False,
    ) -> Tuple[Path, Path, str, str]:
        """
        Render all 19 scenes to frames and compile 1440p master and 1080p delivery MP4 files.
        Returns: (master_1440p_path, delivery_1080p_path, master_hash, delivery_hash)
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        renderer = Video02FrameRenderer()

        temp_dir = Path(tempfile.mkdtemp(prefix="windagent_video02_"))
        try:
            segment_paths: List[Path] = []
            concat_list_path = temp_dir / "concat_list.txt"
            concat_lines: List[str] = []

            print(f"==> Rendering 19 scene master videos with human typing simulation into {temp_dir}...")
            typing_scene_ids = {"S01", "S05", "S06", "S07", "S08", "S09", "S10", "S12", "S13", "S14", "S15"}

            for idx, scene in enumerate(plan.scenes, 1):
                duration_sec = scene.duration_ms / 1000.0
                seg_path = temp_dir / f"seg_{idx:02d}_{scene.scene_id}.mp4"

                if scene.scene_id in typing_scene_ids:
                    # Natural human typing speed simulation (~15-18 chars/sec):
                    if scene.visual_mode.value == "TERMINAL_ONLY" or scene.scene_id in ("S05", "S14"):
                        if scene.scene_id == "S05":
                            num_chars = 240
                        elif scene.scene_id == "S14":
                            num_chars = 380
                        else:
                            num_chars = 200
                    else:
                        code_lines = renderer._get_scene_code(scene.scene_id)
                        num_chars = sum(len(txt) + 1 for txt, _ in code_lines)

                    typing_sec = min(duration_sec * 0.65, max(8.0, num_chars / 16.0))
                    steady_sec = max(0.0, duration_sec - typing_sec)
                    typing_frames = int(round(typing_sec * 30))

                    # 1. Render typing sub-segment
                    sub_type_path = temp_dir / f"sub_type_{idx:02d}.mp4"
                    cmd_type = [
                        "ffmpeg", "-y",
                        "-f", "rawvideo",
                        "-pix_fmt", "rgb24",
                        "-s", "2560x1440",
                        "-r", "30",
                        "-i", "-",
                        "-c:v", "libx264",
                        "-t", f"{typing_sec:.3f}",
                        "-pix_fmt", "yuv420p",
                        "-preset", "ultrafast",
                        str(sub_type_path),
                    ]
                    proc = subprocess.Popen(
                        cmd_type,
                        stdin=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                    )
                    for f in range(typing_frames):
                        progress = f / float(max(1, typing_frames))
                        frame_img = renderer.render_scene_frame(
                            scene, plan, typing_progress=progress, frame_idx=f
                        )
                        proc.stdin.write(frame_img.tobytes())
                    proc.stdin.close()
                    proc.wait()

                    # 2. Render steady sub-segment with looping
                    if steady_sec > 0.05:
                        steady_frame = renderer.render_scene_frame(
                            scene, plan, typing_progress=1.0, frame_idx=0
                        )
                        steady_frame_path = temp_dir / f"steady_frame_{idx:02d}.png"
                        steady_frame.save(str(steady_frame_path), format="PNG")
                        sub_steady_path = temp_dir / f"sub_steady_{idx:02d}.mp4"

                        cmd_steady = [
                            "ffmpeg", "-y",
                            "-loop", "1",
                            "-i", str(steady_frame_path),
                            "-c:v", "libx264",
                            "-t", f"{steady_sec:.3f}",
                            "-pix_fmt", "yuv420p",
                            "-r", "30",
                            "-preset", "ultrafast",
                            str(sub_steady_path),
                        ]
                        subprocess.run(cmd_steady, capture_output=True, text=True, check=True)

                        # Concat sub_type and sub_steady
                        sub_concat_list = temp_dir / f"sub_concat_{idx:02d}.txt"
                        p1 = str(sub_type_path).replace("\\", "/")
                        p2 = str(sub_steady_path).replace("\\", "/")
                        sub_concat_list.write_text(f"file '{p1}'\nfile '{p2}'\n", encoding="utf-8")

                        cmd_join = [
                            "ffmpeg", "-y",
                            "-f", "concat",
                            "-safe", "0",
                            "-i", str(sub_concat_list),
                            "-c", "copy",
                            str(seg_path),
                        ]
                        subprocess.run(cmd_join, capture_output=True, text=True, check=True)
                    else:
                        shutil.copyfile(sub_type_path, seg_path)

                else:
                    # Static Diagram, Title Card, Outro, Checklist
                    frame_img = renderer.render_scene_frame(scene, plan, typing_progress=1.0, frame_idx=0)
                    frame_path = temp_dir / f"scene_{idx:02d}_{scene.scene_id}.png"
                    frame_img.save(str(frame_path), format="PNG")

                    cmd_seg = [
                        "ffmpeg", "-y",
                        "-loop", "1",
                        "-i", str(frame_path),
                        "-c:v", "libx264",
                        "-t", f"{duration_sec:.3f}",
                        "-pix_fmt", "yuv420p",
                        "-r", "30",
                        "-preset", "ultrafast",
                        str(seg_path),
                    ]
                    res = subprocess.run(cmd_seg, capture_output=True, text=True)
                    if res.returncode != 0:
                        raise RuntimeError(f"FFmpeg failed rendering scene {scene.scene_id}: {res.stderr}")

                segment_paths.append(seg_path)
                escaped_path = str(seg_path).replace("\\", "/")
                concat_lines.append(f"file '{escaped_path}'")
                print(f"  [+] Scene {idx:02d}/{len(plan.scenes):02d} ({scene.scene_id}): {duration_sec:.1f}s segment rendered.", flush=True)

            concat_list_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

            # 3. Concatenate all segments into Master 1440p MP4
            master_1440p_path = output_dir / "video_02_visual_master_1440p.mp4"
            print("==> Concatenating scenes into Master 1440p MP4...")
            cmd_concat = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list_path),
                "-c", "copy",
                "-an",
                str(master_1440p_path),
            ]
            res_concat = subprocess.run(cmd_concat, capture_output=True, text=True)
            if res_concat.returncode != 0:
                raise RuntimeError(f"FFmpeg concat failed: {res_concat.stderr}")

            # 4. Create Delivery 1080p MP4 by downscaling
            delivery_1080p_path = output_dir / "video_02_visual_master_1080p.mp4"
            print("==> Transcoding Delivery 1080p MP4...")
            cmd_downscale = [
                "ffmpeg", "-y",
                "-i", str(master_1440p_path),
                "-vf", "scale=1920:1080:flags=lanczos",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "ultrafast",
                "-an",
                str(delivery_1080p_path),
            ]
            res_down = subprocess.run(cmd_downscale, capture_output=True, text=True)
            if res_down.returncode != 0:
                raise RuntimeError(f"FFmpeg downscale failed: {res_down.stderr}")

            master_hash = hashlib.sha256(master_1440p_path.read_bytes()).hexdigest()
            delivery_hash = hashlib.sha256(delivery_1080p_path.read_bytes()).hexdigest()

            print("[SUCCESS] Real Videos synthesized successfully!")
            print(f"Master 1440p:   {master_1440p_path} ({os.path.getsize(master_1440p_path):,} bytes, SHA-256: {master_hash[:16]}...)")
            print(f"Delivery 1080p: {delivery_1080p_path} ({os.path.getsize(delivery_1080p_path):,} bytes, SHA-256: {delivery_hash[:16]}...)")

            return master_1440p_path, delivery_1080p_path, master_hash, delivery_hash

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
