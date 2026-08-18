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
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from windagent_workflows.code_video.contracts import CodeVideoPlan, Scene


class Video02FrameRenderer:
    """Renders professional 2560x1440 master frames for all 19 scenes of Video 02."""

    # Color Palette (Dark Theme / GitHub Studio)
    BG_COLOR = (13, 17, 23)        # #0d1117
    PANEL_BG = (22, 27, 34)        # #161b22
    BORDER_COLOR = (48, 54, 61)    # #30363d
    ACCENT_BLUE = (88, 166, 255)   # #58a6ff
    SUCCESS_GREEN = (63, 185, 80)  # #3fb950
    ORANGE_ACCENT = (240, 136, 62) # #f0883e
    RED_ACCENT = (248, 81, 73)     # #f85149
    PURPLE_ACCENT = (188, 140, 255)# #bc8cff
    TEXT_PRIMARY = (201, 209, 217) # #c9d1d9
    TEXT_MUTED = (139, 148, 158)   # #8b949e
    TEXT_WHITE = (240, 246, 252)   # #f0f6fc

    def __init__(self, width: int = 2560, height: int = 1440) -> None:
        self.width = width
        self.height = height

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        """Attempt to load system TrueType fonts, fallback to default font."""
        font_candidates = [
            "C:\\Windows\\Fonts\\segoeui.ttf" if not bold else "C:\\Windows\\Fonts\\segoeuib.ttf",
            "C:\\Windows\\Fonts\\arial.ttf" if not bold else "C:\\Windows\\Fonts\\arialbd.ttf",
            "C:\\Windows\\Fonts\\consola.ttf" if not bold else "C:\\Windows\\Fonts\\consolab.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for fpath in font_candidates:
            if os.path.exists(fpath):
                try:
                    return ImageFont.truetype(fpath, size=size)
                except Exception:
                    pass
        return ImageFont.load_default()

    def render_scene_frame(self, scene: Scene, plan: CodeVideoPlan) -> Image.Image:
        """Render a full 2560x1440 master visual frame for a given scene."""
        img = Image.new("RGB", (self.width, self.height), color=self.BG_COLOR)
        draw = ImageDraw.Draw(img)

        # 1. Outer safe area border & Header Bar
        self._draw_header(draw, scene, plan)

        # 2. Main Content based on visual mode & scene ID
        if scene.visual_mode.value == "TITLE_CARD" or scene.scene_id in ("S02", "S18", "S19"):
            self._draw_title_scene(draw, scene)
        elif scene.visual_mode.value == "DIAGRAM" or scene.scene_id in ("S03", "S04", "S11", "S17"):
            self._draw_diagram_scene(draw, scene)
        elif scene.scene_id == "S16":
            self._draw_checklist_scene(draw, scene)
        elif scene.visual_mode.value == "TERMINAL_ONLY" or scene.scene_id in ("S05", "S14"):
            self._draw_terminal_scene(draw, scene)
        else:
            self._draw_code_studio_scene(draw, scene)

        # 3. Footer Bar
        self._draw_footer(draw, scene)

        return img

    def _draw_header(self, draw: ImageDraw.ImageDraw, scene: Scene, plan: CodeVideoPlan) -> None:
        font_title = self._get_font(36, bold=True)
        font_meta = self._get_font(28)

        # Header background
        draw.rectangle([(120, 50), (self.width - 120, 130)], fill=self.PANEL_BG, outline=self.BORDER_COLOR, width=2)

        # Left branding
        draw.text((150, 70), "Agentic Studio v0.1", font=font_title, fill=self.ACCENT_BLUE)
        draw.text((540, 73), "|", font=font_title, fill=self.BORDER_COLOR)
        draw.text((570, 75), f"VIDEO 02 — {scene.title}", font=font_meta, fill=self.TEXT_PRIMARY)

        # Right scene indicator
        start_tc = f"{scene.start_ms // 60000:02d}:{(scene.start_ms % 60000)//1000:02d}"
        end_tc = f"{scene.end_ms // 60000:02d}:{(scene.end_ms % 60000)//1000:02d}"
        timecode_text = f"Scene {scene.scene_id} [{start_tc} – {end_tc}]"
        draw.text((self.width - 500, 75), timecode_text, font=font_meta, fill=self.ORANGE_ACCENT)

    def _draw_footer(self, draw: ImageDraw.ImageDraw, scene: Scene) -> None:
        font_foot = self._get_font(24)
        draw.rectangle([(120, self.height - 110), (self.width - 120, self.height - 50)], fill=self.PANEL_BG, outline=self.BORDER_COLOR, width=2)
        draw.text((150, self.height - 92), "Domain: Clean Architecture • Zero SDK Leaks in Core • Offline Deterministic Replay", font=font_foot, fill=self.TEXT_MUTED)
        draw.text((self.width - 450, self.height - 92), "1440p Master | 30 FPS | Zero Audio", font=font_foot, fill=self.SUCCESS_GREEN)

    def _draw_title_scene(self, draw: ImageDraw.ImageDraw, scene: Scene) -> None:
        font_hero = self._get_font(68, bold=True)
        font_sub = self._get_font(42, bold=True)
        font_body = self._get_font(32)

        # Center Card
        card_box = [(200, 200), (self.width - 200, self.height - 180)]
        draw.rectangle(card_box, fill=self.PANEL_BG, outline=self.BORDER_COLOR, width=4)

        if scene.scene_id == "S02":
            draw.text((300, 320), "VIDEO 02", font=self._get_font(48, bold=True), fill=self.ORANGE_ACCENT)
            draw.text((300, 420), "VIẾT AI AGENT ĐẦU TIÊN BẰNG PYTHON", font=font_hero, fill=self.TEXT_WHITE)
            draw.text((300, 540), "Xây dựng Simple Agent Core từ con số 0 — Không thư viện cồng kềnh", font=font_sub, fill=self.ACCENT_BLUE)
            
            # Key highlights box
            draw.rectangle([(300, 680), (self.width - 300, 1050)], fill=self.BG_COLOR, outline=self.BORDER_COLOR, width=2)
            draw.text((350, 730), "• Tách bạch Clean Architecture: Domain Core vs Infrastructure Provider", font=font_body, fill=self.TEXT_PRIMARY)
            draw.text((350, 810), "• Xây dựng Message Dataclass, AgentConfig, LLMClient Protocol", font=font_body, fill=self.TEXT_PRIMARY)
            draw.text((350, 890), "• Kiểm thử đơn vị Fake LLM hoàn toàn offline (Pytest 2 passed)", font=font_body, fill=self.SUCCESS_GREEN)
            draw.text((350, 970), "• Đóng gói Git Milestone v0.1 — Chuẩn bị nền tảng cho Tool Calling", font=font_body, fill=self.TEXT_PRIMARY)

        elif scene.scene_id == "S18":
            draw.text((300, 320), "GIT RELEASE MILESTONE", font=self._get_font(48, bold=True), fill=self.SUCCESS_GREEN)
            draw.text((300, 420), "Agentic Studio v0.1 — Simple Agent", font=font_hero, fill=self.TEXT_WHITE)
            draw.text((300, 540), "Commit & Release Tags đã được niêm phong trong tutorial repository", font=font_sub, fill=self.ACCENT_BLUE)
            draw.rectangle([(300, 680), (self.width - 300, 1050)], fill=self.BG_COLOR, outline=self.BORDER_COLOR, width=2)
            draw.text((350, 740), "$ git add .", font=self._get_font(36), fill=self.TEXT_MUTED)
            draw.text((350, 810), '$ git commit -m "feat: build simple agent core"', font=self._get_font(36), fill=self.TEXT_WHITE)
            draw.text((350, 880), "$ git tag video-02", font=self._get_font(36), fill=self.ACCENT_BLUE)
            draw.text((350, 950), "$ git tag v0.1", font=self._get_font(36), fill=self.SUCCESS_GREEN)

        elif scene.scene_id == "S19":
            draw.text((300, 320), "NEXT EPISODE TEASER", font=self._get_font(48, bold=True), fill=self.PURPLE_ACCENT)
            draw.text((300, 420), "VIDEO 03 — TOOL CALLING", font=font_hero, fill=self.TEXT_WHITE)
            draw.text((300, 540), "Tool Calling hoạt động bên trong như thế nào?", font=font_sub, fill=self.ACCENT_BLUE)
            draw.rectangle([(300, 680), (self.width - 300, 1050)], fill=self.BG_COLOR, outline=self.BORDER_COLOR, width=2)
            draw.text((350, 750), "Hôm nay (Video 02):  User  ->  Agent  ->  LLM  ->  Answer", font=font_body, fill=self.TEXT_MUTED)
            draw.text((350, 840), "Tập tiếp theo (Video 03): User  ->  Agent  ->  LLM  ->  TOOL EXECUTION  ->  Answer", font=font_body, fill=self.ORANGE_ACCENT)
            draw.text((350, 930), "Nguyên lý cốt lõi: LLM KHÔNG tự chạy code, LLM chỉ phát tín hiệu gọi Tool!", font=font_body, fill=self.SUCCESS_GREEN)

    def _draw_diagram_scene(self, draw: ImageDraw.ImageDraw, scene: Scene) -> None:
        font_title = self._get_font(44, bold=True)
        font_box = self._get_font(34, bold=True)
        font_desc = self._get_font(28)

        card_box = [(200, 180), (self.width - 200, self.height - 160)]
        draw.rectangle(card_box, fill=self.PANEL_BG, outline=self.BORDER_COLOR, width=4)

        if scene.scene_id in ("S01", "S04"):
            draw.text((260, 240), "KIẾN TRÚC SIMPLE AGENT (v0.1)", font=font_title, fill=self.ACCENT_BLUE)
            draw.text((260, 310), "Mô hình luồng dữ liệu 1 vòng đơn giản: User -> Agent -> LLM -> Answer", font=font_desc, fill=self.TEXT_MUTED)

            # Draw diagram boxes
            boxes = [
                (300, 550, 650, 750, "User Prompt\n(Input)", self.BORDER_COLOR, self.TEXT_WHITE),
                (800, 550, 1150, 750, "Agent Core\n(Orchestration)", self.ACCENT_BLUE, self.TEXT_WHITE),
                (1300, 550, 1650, 750, "LLMClient\n(Protocol)", self.ORANGE_ACCENT, self.TEXT_WHITE),
                (1800, 550, 2150, 750, "Final Answer\n(Output)", self.SUCCESS_GREEN, self.TEXT_WHITE),
            ]
            for x1, y1, x2, y2, text, outline_color, fill_color in boxes:
                draw.rectangle([(x1, y1), (x2, y2)], fill=self.BG_COLOR, outline=outline_color, width=4)
                draw.text((x1 + 30, y1 + 50), text, font=font_box, fill=fill_color)

            # Draw connecting arrows
            draw.text((680, 620), "===>", font=font_box, fill=self.ACCENT_BLUE)
            draw.text((1180, 620), "===>", font=font_box, fill=self.ACCENT_BLUE)
            draw.text((1680, 620), "===>", font=font_box, fill=self.ACCENT_BLUE)

            # Note box at bottom
            draw.rectangle([(300, 900), (2150, 1120)], fill=self.BG_COLOR, outline=self.BORDER_COLOR, width=2)
            draw.text((340, 930), "• Domain Layer: Agent gom System Prompt + User Message thành message list.", font=font_desc, fill=self.TEXT_PRIMARY)
            draw.text((340, 990), "• LLMClient: Gửi sang Provider (hoặc Fake offline) và trả về text đơn thuần.", font=font_desc, fill=self.TEXT_PRIMARY)
            draw.text((340, 1050), "• Chưa có Tool Calling, Memory hay Agent Loop phức tạp ở milestone này.", font=font_desc, fill=self.ORANGE_ACCENT)

        elif scene.scene_id == "S11":
            draw.text((260, 240), "IS THIS AN AGENT? — PHÂN TÍCH COGNITIVE LOOP", font=font_title, fill=self.ORANGE_ACCENT)
            draw.text((260, 310), "Chu trình nhận thức chuẩn: Observe -> Decide -> Act -> Observe", font=font_desc, fill=self.TEXT_MUTED)

            # Cognitive Loop Boxes
            cboxes = [
                (350, 480, 750, 680, "1. OBSERVE\n(Nhận câu hỏi)", self.SUCCESS_GREEN),
                (1050, 480, 1450, 680, "2. DECIDE\n(LLM suy luận)", self.SUCCESS_GREEN),
                (1750, 480, 2150, 680, "3. ACT (Chưa có)\n(Gọi Tool / Execute)", self.BORDER_COLOR),
            ]
            for x1, y1, x2, y2, text, col in cboxes:
                draw.rectangle([(x1, y1), (x2, y2)], fill=self.BG_COLOR, outline=col, width=4)
                draw.text((x1 + 30, y1 + 50), text, font=font_box, fill=col if col != self.BORDER_COLOR else self.TEXT_MUTED)

            draw.text((800, 560), "===>", font=font_box, fill=self.ACCENT_BLUE)
            draw.text((1500, 560), "===>", font=font_box, fill=self.BORDER_COLOR)

            draw.rectangle([(350, 800), (2150, 1100)], fill=self.BG_COLOR, outline=self.BORDER_COLOR, width=2)
            draw.text((400, 840), "Đánh giá phạm vi v0.1:", font=self._get_font(32, bold=True), fill=self.TEXT_WHITE)
            draw.text((400, 910), "✓ Có thể coi là Simple Agent / Stateless Agent vì có System Prompt & cấu trúc Agent Core.", font=font_desc, fill=self.SUCCESS_GREEN)
            draw.text((400, 980), "✕ Chưa phải Autonomous Agent hoàn chỉnh vì chưa có vòng lặp phản hồi (Loop) và Tool Calling.", font=font_desc, fill=self.ORANGE_ACCENT)

        elif scene.scene_id == "S17":
            draw.text((260, 240), "CLEAN ARCHITECTURE REVIEW: TÁCH BẠCH DOMAIN & INFRA", font=font_title, fill=self.ACCENT_BLUE)
            draw.text((260, 310), "Quy tắc bất biến: Domain Core KHÔNG phụ thuộc SDK bên ngoài", font=font_desc, fill=self.TEXT_MUTED)

            # Left Box: DOMAIN
            draw.rectangle([(300, 450), (1150, 1080)], fill=self.BG_COLOR, outline=self.ACCENT_BLUE, width=3)
            draw.text((350, 490), "DOMAIN CORE (Pure Python)", font=self._get_font(34, bold=True), fill=self.ACCENT_BLUE)
            draw.text((350, 580), "• Message (frozen dataclass)", font=font_desc, fill=self.TEXT_WHITE)
            draw.text((350, 660), "• AgentConfig (dataclass)", font=font_desc, fill=self.TEXT_WHITE)
            draw.text((350, 740), "• LLMClient (Protocol)", font=font_desc, fill=self.TEXT_WHITE)
            draw.text((350, 820), "• FakeLLMClient (Test mock)", font=font_desc, fill=self.SUCCESS_GREEN)
            draw.text((350, 900), "• Agent (Run loop core)", font=font_desc, fill=self.TEXT_WHITE)
            draw.text((350, 980), "Zero third-party SDK dependencies", font=self._get_font(26, bold=True), fill=self.SUCCESS_GREEN)

            # Right Box: INFRASTRUCTURE
            draw.rectangle([(1300, 450), (2150, 1080)], fill=self.BG_COLOR, outline=self.ORANGE_ACCENT, width=3)
            draw.text((1350, 490), "INFRASTRUCTURE (Adapters)", font=self._get_font(34, bold=True), fill=self.ORANGE_ACCENT)
            draw.text((1350, 580), "• OpenAI / Anthropic / Google SDKs", font=font_desc, fill=self.TEXT_MUTED)
            draw.text((1350, 660), "• HTTP Network Calls & Retries", font=font_desc, fill=self.TEXT_MUTED)
            draw.text((1350, 740), "• API Key & Environment Loading", font=font_desc, fill=self.TEXT_MUTED)
            draw.text((1350, 820), "• Token Quotas & Error Handling", font=font_desc, fill=self.TEXT_MUTED)
            draw.text((1350, 980), "Isolated outside the domain core", font=self._get_font(26, bold=True), fill=self.ORANGE_ACCENT)

    def _draw_checklist_scene(self, draw: ImageDraw.ImageDraw, scene: Scene) -> None:
        font_title = self._get_font(44, bold=True)
        font_item = self._get_font(34)
        font_desc = self._get_font(28)

        card_box = [(200, 180), (self.width - 200, self.height - 160)]
        draw.rectangle(card_box, fill=self.PANEL_BG, outline=self.BORDER_COLOR, width=4)

        draw.text((260, 240), "NOT YET — 7 TÍNH NĂNG CHƯA CÓ TRONG VIDEO 02", font=font_title, fill=self.RED_ACCENT)
        draw.text((260, 310), "Giữ phạm vi bài học tập trung vào cốt lõi, không đưa các tính năng nâng cao vào sớm", font=font_desc, fill=self.TEXT_MUTED)

        checklist = [
            ("Tool Calling (Hàm công cụ ngoại vi)", "Sẽ có ở Video 03"),
            ("Agent Loop (Vòng lặp tự hành)", "Sẽ có ở Video 04"),
            ("Memory (Bộ nhớ ngắn hạn & dài hạn)", "Sẽ có ở Video 05"),
            ("RAG (Truy xuất dữ liệu bên ngoài)", "Sẽ có ở Video 06"),
            ("Planning (Lập kế hoạch đa bước)", "Sẽ có ở Video 07"),
            ("Multi-Agent (Hợp tác đa tác tử)", "Sẽ có ở Video 08"),
            ("Orchestration (Điều phối phức tạp)", "Sẽ có ở Video 09"),
        ]

        y_offset = 420
        for item, note in checklist:
            draw.rectangle([(260, y_offset), (self.width - 260, y_offset + 75)], fill=self.BG_COLOR, outline=self.BORDER_COLOR, width=2)
            draw.text((300, y_offset + 18), "✕", font=self._get_font(36, bold=True), fill=self.RED_ACCENT)
            draw.text((360, y_offset + 20), item, font=font_item, fill=self.TEXT_WHITE)
            draw.text((1600, y_offset + 22), f"[{note}]", font=self._get_font(28), fill=self.TEXT_MUTED)
            y_offset += 95

    def _draw_terminal_scene(self, draw: ImageDraw.ImageDraw, scene: Scene) -> None:
        font_title = self._get_font(38, bold=True)
        font_term = self._get_font(32)

        card_box = [(200, 180), (self.width - 200, self.height - 160)]
        draw.rectangle(card_box, fill=(10, 14, 20), outline=self.BORDER_COLOR, width=4)

        # Terminal top bar
        draw.rectangle([(200, 180), (self.width - 200, 250)], fill=self.PANEL_BG, outline=self.BORDER_COLOR, width=2)
        draw.ellipse([(230, 205), (250, 225)], fill=(248, 81, 73))
        draw.ellipse([(265, 205), (285, 225)], fill=(227, 179, 65))
        draw.ellipse([(300, 205), (320, 225)], fill=(63, 185, 80))
        draw.text((350, 202), "Terminal — PowerShell (agentic-studio)", font=self._get_font(26), fill=self.TEXT_MUTED)

        y = 300
        if scene.scene_id == "S05":
            lines = [
                ("PS D:\\code> mkdir agentic-studio", self.TEXT_WHITE),
                ("PS D:\\code> cd agentic-studio", self.TEXT_WHITE),
                ("PS D:\\code\\agentic-studio> git init", self.TEXT_WHITE),
                ("Initialized empty Git repository in D:/code/agentic-studio/.git/", self.SUCCESS_GREEN),
                ("PS D:\\code\\agentic-studio> code .", self.TEXT_WHITE),
            ]
        elif scene.scene_id == "S14":
            lines = [
                ("PS D:\\code\\agentic-studio> python -m src.agent", self.TEXT_WHITE),
                ("[Agentic Studio v0.1] Khởi tạo Simple Agent thành công.", self.ACCENT_BLUE),
                ("User Prompt: 'Giải thích recursion bằng một ví dụ đơn giản.'", self.ORANGE_ACCENT),
                ("--- Model Response ---", self.TEXT_MUTED),
                ("Đệ quy (Recursion) là kỹ thuật một hàm tự gọi lại chính nó để giải quyết bài toán nhỏ hơn.", self.TEXT_PRIMARY),
                ("Ví dụ kinh điển: Tính giai thừa n! = n * (n-1)!, với điểm dừng là 0! = 1.", self.TEXT_PRIMARY),
                ("----------------------", self.TEXT_MUTED),
                ("[Process exited with status 0]", self.SUCCESS_GREEN),
            ]
        else:
            lines = [
                ("PS D:\\code\\agentic-studio> pytest", self.TEXT_WHITE),
                ("============================= test session starts =============================", self.TEXT_MUTED),
                ("rootdir: D:\\code\\agentic-studio", self.TEXT_MUTED),
                ("collected 2 items", self.TEXT_MUTED),
                ("tests/test_agent.py ..                                                   [100%]", self.SUCCESS_GREEN),
                ("============================== 2 passed in 0.04s ===============================", self.SUCCESS_GREEN),
            ]

        for text, col in lines:
            draw.text((250, y), text, font=font_term, fill=col)
            y += 65

    def _draw_code_studio_scene(self, draw: ImageDraw.ImageDraw, scene: Scene) -> None:
        font_code = self._get_font(28)
        font_hl = self._get_font(32, bold=True)

        # 1. Left Sidebar: File Tree (x: 150 -> 650)
        draw.rectangle([(150, 160), (650, self.height - 140)], fill=self.PANEL_BG, outline=self.BORDER_COLOR, width=2)
        draw.text((180, 190), "EXPLORER: AGENTIC-STUDIO", font=self._get_font(24, bold=True), fill=self.TEXT_MUTED)
        tree_items = [
            ("📁 src", self.ACCENT_BLUE),
            ("    📄 __init__.py", self.TEXT_MUTED),
            ("    📄 agent.py", self.TEXT_WHITE),
            ("📁 tests", self.ACCENT_BLUE),
            ("    📄 test_agent.py", self.TEXT_MUTED),
            ("📄 .env.example", self.ORANGE_ACCENT),
            ("📄 .gitignore", self.TEXT_MUTED),
            ("📄 pyproject.toml", self.TEXT_MUTED),
            ("📄 README.md", self.TEXT_MUTED),
        ]
        y_tree = 250
        for item, col in tree_items:
            draw.text((180, y_tree), item, font=self._get_font(26), fill=col)
            y_tree += 50

        # 2. Center: Code Editor (x: 680 -> self.width - 150)
        draw.rectangle([(680, 160), (self.width - 150, self.height - 140)], fill=(10, 14, 20), outline=self.BORDER_COLOR, width=2)
        draw.rectangle([(680, 160), (self.width - 150, 220)], fill=self.PANEL_BG, outline=self.BORDER_COLOR, width=2)
        draw.text((710, 180), "src/agent.py", font=self._get_font(26, bold=True), fill=self.ACCENT_BLUE)

        # Code snippets based on scene
        code_lines = self._get_scene_code(scene.scene_id)
        y_code = 260
        for idx, (line, is_highlighted) in enumerate(code_lines, 1):
            line_no = f"{idx:2d}  "
            draw.text((710, y_code), line_no, font=font_code, fill=(80, 88, 98))
            draw.text((770, y_code), line, font=font_code, fill=self.SUCCESS_GREEN if is_highlighted else self.TEXT_PRIMARY)
            y_code += 45

    def _get_scene_code(self, scene_id: str) -> List[Tuple[str, bool]]:
        if scene_id == "S06":
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

            print(f"==> Rendering 19 scene frames into {temp_dir}...")
            for idx, scene in enumerate(plan.scenes, 1):
                # 1. Render frame
                frame_img = renderer.render_scene_frame(scene, plan)
                frame_path = temp_dir / f"scene_{idx:02d}_{scene.scene_id}.png"
                frame_img.save(str(frame_path), format="PNG")

                # 2. Render MP4 segment for scene with exact duration
                duration_sec = scene.duration_ms / 1000.0
                seg_path = temp_dir / f"seg_{idx:02d}_{scene.scene_id}.mp4"

                # FFmpeg command for scene clip: exact 30fps, H.264 yuv420p
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
                # Concat file requires forward slashes or escaped backslashes
                escaped_path = str(seg_path).replace("\\", "/")
                concat_lines.append(f"file '{escaped_path}'")

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

            print(f"[SUCCESS] Real Videos synthesized successfully!")
            print(f"Master 1440p:   {master_1440p_path} ({os.path.getsize(master_1440p_path):,} bytes, SHA-256: {master_hash[:16]}...)")
            print(f"Delivery 1080p: {delivery_1080p_path} ({os.path.getsize(delivery_1080p_path):,} bytes, SHA-256: {delivery_hash[:16]}...)")

            return master_1440p_path, delivery_1080p_path, master_hash, delivery_hash

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
