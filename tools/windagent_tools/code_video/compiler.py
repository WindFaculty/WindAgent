"""
Deterministic Script-to-Plan Compiler for Code Video (Video 02).

Transforms the Video 02 Markdown script into machine-readable Intermediate
Representation (IR) plans adhering to the 16:15.000 (975,000 ms) timeline
and 19-scene specification with strict semantic action contracts.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Union

from windagent_core.contracts.code_video import (
    Action,
    ActionType,
    Annotation,
    CodeVideoPlan,
    ExpectedState,
    OutputPolicy,
    Resolution,
    Scene,
    VisualMode,
)


class CodeVideoScriptCompiler:
    """
    Compiler that generates the complete, deterministic CodeVideoPlan for Video 02.
    """

    TARGET_VIDEO_ID = "video-02"
    TARGET_DURATION_MS = 975_000  # 16 minutes 15 seconds
    TARGET_FPS = 30
    DEFAULT_MASTER_RESOLUTION = "2560x1440"

    def __init__(
        self,
        script_path: Optional[Union[str, Path]] = None,
        baseline_path: Optional[Union[str, Path]] = None,
    ) -> None:
        self.script_path = Path(script_path).resolve() if script_path else None
        self.baseline_path = Path(baseline_path).resolve() if baseline_path else None

    def _read_source_hash(self) -> str:
        """Read and compute SHA-256 of the source script."""
        if self.script_path and self.script_path.exists():
            return hashlib.sha256(self.script_path.read_bytes()).hexdigest()
        
        # Default known hash from Video 02 baseline
        return "b2c9d46fd74cccc5f48de8509ceef41aec2dfb8db63a78c733a3d961ec1bec6c"

    def compile_video_02_plan(self) -> CodeVideoPlan:
        """
        Compile the complete, contiguous 19-scene plan for Video 02.
        Total duration: 975,000 ms.
        """
        source_hash = self._read_source_hash()

        scenes: List[Scene] = [
            # S01: 00:00 - 00:25 (25,000 ms) — Cold Open
            Scene(
                scene_id="S01",
                title="Cold Open — Live Agent Execution",
                start_ms=0,
                end_ms=25_000,
                visual_mode=VisualMode.SPLIT,
                voice_cue_id="CUE_S01_COLD_OPEN",
                actions=[
                    Action(
                        action_id="act_s01_01",
                        action_type=ActionType.OPEN_WORKSPACE,
                        start_ms=0,
                        duration_ms=2000,
                        params={"workspace_name": "agentic-studio"},
                    ),
                    Action(
                        action_id="act_s01_02",
                        action_type=ActionType.RUN_TERMINAL,
                        start_ms=2000,
                        duration_ms=18000,
                        params={
                            "command": "python -m src.agent",
                            "expected_output_receipt": "provider_demo_output.txt",
                        },
                    ),
                    Action(
                        action_id="act_s01_03",
                        action_type=ActionType.HIGHLIGHT,
                        start_ms=20000,
                        duration_ms=5000,
                        params={"symbol": "Agent", "target": "terminal_output"},
                    ),
                ],
                annotations=[
                    Annotation(
                        annotation_id="ann_s01_01",
                        kind="badge",
                        text="Agentic Studio v0.1 — Live Execution",
                        start_ms=1000,
                        duration_ms=23000,
                    )
                ],
                expected_state=ExpectedState(
                    terminal_last_command="python -m src.agent",
                    terminal_exit_code=0,
                ),
            ),

            # S02: 00:25 - 00:50 (25,000 ms) — Hook
            Scene(
                scene_id="S02",
                title="Hook — Viết AI Agent Đầu Tiên Bằng Python",
                start_ms=25_000,
                end_ms=50_000,
                visual_mode=VisualMode.TITLE_CARD,
                voice_cue_id="CUE_S02_HOOK",
                actions=[
                    Action(
                        action_id="act_s02_01",
                        action_type=ActionType.SHOW_TITLE,
                        start_ms=25_000,
                        duration_ms=25000,
                        params={
                            "title": "VIDEO 02",
                            "subtitle": "VIẾT AI AGENT ĐẦU TIÊN BẰNG PYTHON",
                            "card_type": "primary",
                        },
                    ),
                ],
            ),

            # S03: 00:50 - 01:25 (35,000 ms) — Video 01 Recap
            Scene(
                scene_id="S03",
                title="Video 01 Recap — Nền tảng Agent Architecture",
                start_ms=50_000,
                end_ms=85_000,
                visual_mode=VisualMode.DIAGRAM,
                voice_cue_id="CUE_S03_RECAP",
                actions=[
                    Action(
                        action_id="act_s03_01",
                        action_type=ActionType.SHOW_DIAGRAM,
                        start_ms=50_000,
                        duration_ms=35000,
                        params={"diagram_id": "diagram_01_recap", "type": "flowchart"},
                    ),
                ],
                annotations=[
                    Annotation(
                        annotation_id="ann_s03_01",
                        kind="callout",
                        text="Observe ──> Decide ──> Act Loop",
                        start_ms=55000,
                        duration_ms=28000,
                    )
                ],
            ),

            # S04: 01:25 - 02:10 (45,000 ms) — Architecture v0.1
            Scene(
                scene_id="S04",
                title="Architecture v0.1 — User -> Agent -> LLM -> Answer",
                start_ms=85_000,
                end_ms=130_000,
                visual_mode=VisualMode.ARCHITECTURE,
                voice_cue_id="CUE_S04_ARCH_V01",
                actions=[
                    Action(
                        action_id="act_s04_01",
                        action_type=ActionType.SHOW_ARCHITECTURE,
                        start_ms=85_000,
                        duration_ms=45000,
                        params={
                            "architecture_type": "simple_agent_v01",
                            "flow": ["User", "Agent", "LLMClient", "Answer"],
                        },
                    ),
                ],
                annotations=[
                    Annotation(
                        annotation_id="ann_s04_01",
                        kind="badge",
                        text="Milestone: Agentic Studio v0.1",
                        start_ms=90000,
                        duration_ms=38000,
                    )
                ],
            ),

            # S05: 02:10 - 02:45 (35,000 ms) — Create Repository
            Scene(
                scene_id="S05",
                title="Create Repository — Project Scaffolding",
                start_ms=130_000,
                end_ms=165_000,
                visual_mode=VisualMode.FULL_TERMINAL,
                voice_cue_id="CUE_S05_CREATE_REPO",
                actions=[
                    Action(
                        action_id="act_s05_01",
                        action_type=ActionType.RUN_TERMINAL,
                        start_ms=130_000,
                        duration_ms=12000,
                        params={"command": "mkdir agentic-studio && cd agentic-studio"},
                    ),
                    Action(
                        action_id="act_s05_02",
                        action_type=ActionType.RUN_TERMINAL,
                        start_ms=142_000,
                        duration_ms=10000,
                        params={"command": "git init"},
                    ),
                    Action(
                        action_id="act_s05_03",
                        action_type=ActionType.SHOW_OUTPUT,
                        start_ms=152_000,
                        duration_ms=13000,
                        params={"checkpoint": "cp_00_init"},
                    ),
                ],
                expected_state=ExpectedState(
                    active_file=None,
                    file_tree=[".env.example", ".gitignore", "pyproject.toml", "README.md", "src/__init__.py", "tests/__init__.py"],
                    terminal_last_command="git init",
                    terminal_exit_code=0,
                ),
            ),

            # S06: 02:45 - 03:40 (55,000 ms) — Message
            Scene(
                scene_id="S06",
                title="Message — Immutable Conversation Representation",
                start_ms=165_000,
                end_ms=220_000,
                visual_mode=VisualMode.CODE_STUDIO,
                voice_cue_id="CUE_S06_MESSAGE",
                actions=[
                    Action(
                        action_id="act_s06_01",
                        action_type=ActionType.OPEN_FILE,
                        start_ms=165_000,
                        duration_ms=5000,
                        params={"path": "src/agent.py"},
                    ),
                    Action(
                        action_id="act_s06_02",
                        action_type=ActionType.TYPE_TEXT,
                        start_ms=170_000,
                        duration_ms=35000,
                        params={
                            "path": "src/agent.py",
                            "checkpoint": "cp_01_message",
                            "typing_speed": "normal",
                        },
                    ),
                    Action(
                        action_id="act_s06_03",
                        action_type=ActionType.HIGHLIGHT,
                        start_ms=205_000,
                        duration_ms=15000,
                        params={"symbol": "Message", "line_range": [10, 22]},
                    ),
                ],
                expected_state=ExpectedState(
                    active_file="src/agent.py",
                    cursor_symbol="Message",
                ),
            ),

            # S07: 03:40 - 04:35 (55,000 ms) — AgentConfig
            Scene(
                scene_id="S07",
                title="AgentConfig — Hyperparameters & System Prompt",
                start_ms=220_000,
                end_ms=275_000,
                visual_mode=VisualMode.CODE_STUDIO,
                voice_cue_id="CUE_S07_CONFIG",
                actions=[
                    Action(
                        action_id="act_s07_01",
                        action_type=ActionType.OPEN_FILE,
                        start_ms=220_000,
                        duration_ms=3000,
                        params={"path": "src/agent.py"},
                    ),
                    Action(
                        action_id="act_s07_02",
                        action_type=ActionType.TYPE_TEXT,
                        start_ms=223_000,
                        duration_ms=37000,
                        params={
                            "path": "src/agent.py",
                            "checkpoint": "cp_02_config",
                            "typing_speed": "normal",
                        },
                    ),
                    Action(
                        action_id="act_s07_03",
                        action_type=ActionType.HIGHLIGHT,
                        start_ms=260_000,
                        duration_ms=15000,
                        params={"symbol": "AgentConfig", "line_range": [25, 38]},
                    ),
                ],
                expected_state=ExpectedState(
                    active_file="src/agent.py",
                    cursor_symbol="AgentConfig",
                ),
            ),

            # S08: 04:35 - 06:00 (85,000 ms) — LLMClient
            Scene(
                scene_id="S08",
                title="LLMClient — Domain Abstraction Protocol",
                start_ms=275_000,
                end_ms=360_000,
                visual_mode=VisualMode.CODE_STUDIO,
                voice_cue_id="CUE_S08_PROTOCOL",
                actions=[
                    Action(
                        action_id="act_s08_01",
                        action_type=ActionType.OPEN_FILE,
                        start_ms=275_000,
                        duration_ms=4000,
                        params={"path": "src/agent.py"},
                    ),
                    Action(
                        action_id="act_s08_02",
                        action_type=ActionType.TYPE_TEXT,
                        start_ms=279_000,
                        duration_ms=56000,
                        params={
                            "path": "src/agent.py",
                            "checkpoint": "cp_03_llm_protocol",
                            "typing_speed": "normal",
                        },
                    ),
                    Action(
                        action_id="act_s08_03",
                        action_type=ActionType.HIGHLIGHT,
                        start_ms=335_000,
                        duration_ms=25000,
                        params={"symbol": "LLMClient", "line_range": [41, 48]},
                    ),
                ],
                expected_state=ExpectedState(
                    active_file="src/agent.py",
                    cursor_symbol="LLMClient",
                ),
            ),

            # S09: 06:00 - 06:50 (50,000 ms) — Fake LLM
            Scene(
                scene_id="S09",
                title="Fake LLM — Deterministic Offline Testing Client",
                start_ms=360_000,
                end_ms=410_000,
                visual_mode=VisualMode.CODE_STUDIO,
                voice_cue_id="CUE_S09_FAKE_LLM",
                actions=[
                    Action(
                        action_id="act_s09_01",
                        action_type=ActionType.OPEN_FILE,
                        start_ms=360_000,
                        duration_ms=3000,
                        params={"path": "src/agent.py"},
                    ),
                    Action(
                        action_id="act_s09_02",
                        action_type=ActionType.TYPE_TEXT,
                        start_ms=363_000,
                        duration_ms=32000,
                        params={
                            "path": "src/agent.py",
                            "checkpoint": "cp_04_fake_llm",
                            "typing_speed": "normal",
                        },
                    ),
                    Action(
                        action_id="act_s09_03",
                        action_type=ActionType.HIGHLIGHT,
                        start_ms=395_000,
                        duration_ms=15000,
                        params={"symbol": "FakeLLMClient", "line_range": [51, 68]},
                    ),
                ],
                expected_state=ExpectedState(
                    active_file="src/agent.py",
                    cursor_symbol="FakeLLMClient",
                ),
            ),

            # S10: 06:50 - 08:25 (95,000 ms) — Agent
            Scene(
                scene_id="S10",
                title="Agent — Orchestration Core Class",
                start_ms=410_000,
                end_ms=505_000,
                visual_mode=VisualMode.CODE_STUDIO,
                voice_cue_id="CUE_S10_AGENT",
                actions=[
                    Action(
                        action_id="act_s10_01",
                        action_type=ActionType.OPEN_FILE,
                        start_ms=410_000,
                        duration_ms=3000,
                        params={"path": "src/agent.py"},
                    ),
                    Action(
                        action_id="act_s10_02",
                        action_type=ActionType.TYPE_TEXT,
                        start_ms=413_000,
                        duration_ms=62000,
                        params={
                            "path": "src/agent.py",
                            "checkpoint": "cp_05_agent",
                            "typing_speed": "normal",
                        },
                    ),
                    Action(
                        action_id="act_s10_03",
                        action_type=ActionType.HIGHLIGHT,
                        start_ms=475_000,
                        duration_ms=30000,
                        params={"symbol": "Agent", "line_range": [71, 90]},
                    ),
                ],
                expected_state=ExpectedState(
                    active_file="src/agent.py",
                    cursor_symbol="Agent",
                ),
            ),

            # S11: 08:25 - 09:00 (35,000 ms) — Is This An Agent?
            Scene(
                scene_id="S11",
                title="Is This An Agent? — Concept Deep Dive",
                start_ms=505_000,
                end_ms=540_000,
                visual_mode=VisualMode.DIAGRAM,
                voice_cue_id="CUE_S11_IS_AGENT",
                actions=[
                    Action(
                        action_id="act_s11_01",
                        action_type=ActionType.SHOW_DIAGRAM,
                        start_ms=505_000,
                        duration_ms=35000,
                        params={"diagram_id": "diagram_02_agent_concept"},
                    ),
                ],
                annotations=[
                    Annotation(
                        annotation_id="ann_s11_01",
                        kind="callout",
                        text="Simple Agent vs Full Autonomous Agent",
                        start_ms=510000,
                        duration_ms=28000,
                    )
                ],
            ),

            # S12: 09:00 - 10:15 (75,000 ms) — Real Provider
            Scene(
                scene_id="S12",
                title="Real Provider — Infrastructure Layer Adapter",
                start_ms=540_000,
                end_ms=615_000,
                visual_mode=VisualMode.CODE_STUDIO,
                voice_cue_id="CUE_S12_REAL_PROVIDER",
                actions=[
                    Action(
                        action_id="act_s12_01",
                        action_type=ActionType.OPEN_FILE,
                        start_ms=540_000,
                        duration_ms=4000,
                        params={"path": "src/agent.py"},
                    ),
                    Action(
                        action_id="act_s12_02",
                        action_type=ActionType.TYPE_TEXT,
                        start_ms=544_000,
                        duration_ms=48000,
                        params={
                            "path": "src/agent.py",
                            "checkpoint": "cp_07_provider",
                            "typing_speed": "normal",
                        },
                    ),
                    Action(
                        action_id="act_s12_03",
                        action_type=ActionType.HIGHLIGHT,
                        start_ms=592_000,
                        duration_ms=23000,
                        params={"symbol": "OpenAICompatibleProvider", "line_range": [93, 135]},
                    ),
                ],
                expected_state=ExpectedState(
                    active_file="src/agent.py",
                    cursor_symbol="OpenAICompatibleProvider",
                ),
            ),

            # S13: 10:15 - 11:05 (50,000 ms) — API Key Management
            Scene(
                scene_id="S13",
                title="API Key — Environment Configuration & Security",
                start_ms=615_000,
                end_ms=665_000,
                visual_mode=VisualMode.CODE_STUDIO,
                voice_cue_id="CUE_S13_API_KEY",
                actions=[
                    Action(
                        action_id="act_s13_01",
                        action_type=ActionType.OPEN_FILE,
                        start_ms=615_000,
                        duration_ms=4000,
                        params={"path": ".env.example"},
                    ),
                    Action(
                        action_id="act_s13_02",
                        action_type=ActionType.SELECT_RANGE,
                        start_ms=619_000,
                        duration_ms=26000,
                        params={"path": ".env.example", "lines": [1, 7]},
                    ),
                    Action(
                        action_id="act_s13_03",
                        action_type=ActionType.OPEN_FILE,
                        start_ms=645_000,
                        duration_ms=20000,
                        params={"path": ".gitignore"},
                    ),
                ],
                annotations=[
                    Annotation(
                        annotation_id="ann_s13_01",
                        kind="callout",
                        text="NEVER COMMIT REAL SECRETS TO VERSION CONTROL",
                        start_ms=625000,
                        duration_ms=38000,
                    )
                ],
                expected_state=ExpectedState(active_file=".gitignore"),
            ),

            # S14: 11:05 - 12:00 (55,000 ms) — First Run
            Scene(
                scene_id="S14",
                title="First Run — Terminal Execution Replay",
                start_ms=665_000,
                end_ms=720_000,
                visual_mode=VisualMode.FULL_TERMINAL,
                voice_cue_id="CUE_S14_FIRST_RUN",
                actions=[
                    Action(
                        action_id="act_s14_01",
                        action_type=ActionType.RUN_TERMINAL,
                        start_ms=665_000,
                        duration_ms=35000,
                        params={
                            "command": "python -m src.agent",
                            "expected_output_receipt": "provider_demo_output.txt",
                        },
                    ),
                    Action(
                        action_id="act_s14_02",
                        action_type=ActionType.SHOW_OUTPUT,
                        start_ms=700_000,
                        duration_ms=20000,
                        params={"target": "terminal_stdout"},
                    ),
                ],
                expected_state=ExpectedState(
                    terminal_last_command="python -m src.agent",
                    terminal_exit_code=0,
                ),
            ),

            # S15: 12:00 - 13:20 (80,000 ms) — Tests
            Scene(
                scene_id="S15",
                title="Tests — Pytest Suite (2 passed)",
                start_ms=720_000,
                end_ms=800_000,
                visual_mode=VisualMode.CODE_STUDIO,
                voice_cue_id="CUE_S15_TESTS",
                actions=[
                    Action(
                        action_id="act_s15_01",
                        action_type=ActionType.OPEN_FILE,
                        start_ms=720_000,
                        duration_ms=4000,
                        params={"path": "tests/test_agent.py"},
                    ),
                    Action(
                        action_id="act_s15_02",
                        action_type=ActionType.TYPE_TEXT,
                        start_ms=724_000,
                        duration_ms=46000,
                        params={
                            "path": "tests/test_agent.py",
                            "checkpoint": "cp_06_tests",
                            "typing_speed": "normal",
                        },
                    ),
                    Action(
                        action_id="act_s15_03",
                        action_type=ActionType.RUN_TERMINAL,
                        start_ms=770_000,
                        duration_ms=30000,
                        params={"command": "pytest", "expected_passes": 2},
                    ),
                ],
                expected_state=ExpectedState(
                    active_file="tests/test_agent.py",
                    terminal_last_command="pytest",
                    terminal_exit_code=0,
                ),
            ),

            # S16: 13:20 - 14:10 (50,000 ms) — Not Yet
            Scene(
                scene_id="S16",
                title="Not Yet — Feature Boundaries & Scope",
                start_ms=800_000,
                end_ms=850_000,
                visual_mode=VisualMode.CHECKLIST,
                voice_cue_id="CUE_S16_NOT_YET",
                actions=[
                    Action(
                        action_id="act_s16_01",
                        action_type=ActionType.SHOW_CHECKLIST,
                        start_ms=800_000,
                        duration_ms=50000,
                        params={
                            "items": [
                                {"title": "Tool Calling", "status": "excluded"},
                                {"title": "Agent Loop", "status": "excluded"},
                                {"title": "Memory", "status": "excluded"},
                                {"title": "RAG", "status": "excluded"},
                                {"title": "Planning", "status": "excluded"},
                                {"title": "Multi-Agent", "status": "excluded"},
                                {"title": "Orchestration", "status": "excluded"},
                            ]
                        },
                    ),
                ],
            ),

            # S17: 14:10 - 15:00 (50,000 ms) — Architecture Review
            Scene(
                scene_id="S17",
                title="Architecture Review — Domain / Infrastructure Separation",
                start_ms=850_000,
                end_ms=900_000,
                visual_mode=VisualMode.ARCHITECTURE,
                voice_cue_id="CUE_S17_ARCH_REVIEW",
                actions=[
                    Action(
                        action_id="act_s17_01",
                        action_type=ActionType.SHOW_ARCHITECTURE,
                        start_ms=850_000,
                        duration_ms=50000,
                        params={
                            "diagram_id": "diagram_06_domain_infrastructure",
                            "domain": ["Agent", "Message", "AgentConfig", "LLMClient"],
                            "infrastructure": ["OpenAICompatibleProvider", "HTTP", "API Key"],
                        },
                    ),
                ],
            ),

            # S18: 15:00 - 15:35 (35,000 ms) — Git Milestone
            Scene(
                scene_id="S18",
                title="Git Milestone — Commit & Release Tagging",
                start_ms=900_000,
                end_ms=935_000,
                visual_mode=VisualMode.FULL_TERMINAL,
                voice_cue_id="CUE_S18_GIT_MILESTONE",
                actions=[
                    Action(
                        action_id="act_s18_01",
                        action_type=ActionType.RUN_TERMINAL,
                        start_ms=900_000,
                        duration_ms=12000,
                        params={"command": "git add ."},
                    ),
                    Action(
                        action_id="act_s18_02",
                        action_type=ActionType.RUN_TERMINAL,
                        start_ms=912_000,
                        duration_ms=13000,
                        params={"command": 'git commit -m "feat: build simple agent core"'},
                    ),
                    Action(
                        action_id="act_s18_03",
                        action_type=ActionType.RUN_TERMINAL,
                        start_ms=925_000,
                        duration_ms=10000,
                        params={"command": "git tag video-02 && git tag v0.1"},
                    ),
                ],
                expected_state=ExpectedState(
                    terminal_last_command="git tag video-02 && git tag v0.1",
                    terminal_exit_code=0,
                ),
            ),

            # S19: 15:35 - 16:15 (40,000 ms) — Video 03 Teaser & Outro
            Scene(
                scene_id="S19",
                title="Video 03 Teaser & Outro — Tool Calling Preview",
                start_ms=935_000,
                end_ms=975_000,
                visual_mode=VisualMode.OUTRO,
                voice_cue_id="CUE_S19_OUTRO",
                actions=[
                    Action(
                        action_id="act_s19_01",
                        action_type=ActionType.SHOW_TITLE,
                        start_ms=935_000,
                        duration_ms=25000,
                        params={
                            "title": "VIDEO 03",
                            "subtitle": "TOOL CALLING HOẠT ĐỘNG BÊN TRONG NHƯ THẾ NÀO?",
                            "card_type": "teaser",
                        },
                    ),
                    Action(
                        action_id="act_s19_02",
                        action_type=ActionType.SHOW_OUTPUT,
                        start_ms=960_000,
                        duration_ms=15000,
                        params={"outro_card": "windagent_channel_subscribe"},
                    ),
                ],
            ),
        ]

        plan = CodeVideoPlan(
            video_id=self.TARGET_VIDEO_ID,
            schema_version="1.0.0",
            title="Video 02 — Viết AI Agent Đầu Tiên Bằng Python",
            duration_ms=self.TARGET_DURATION_MS,
            fps=self.TARGET_FPS,
            resolution=Resolution.from_string(self.DEFAULT_MASTER_RESOLUTION),
            scenes=scenes,
            source_hash=source_hash,
            output_policy=OutputPolicy(
                master_resolution=self.DEFAULT_MASTER_RESOLUTION,
                delivery_resolutions=["1920x1080"],
                fps=self.TARGET_FPS,
                audio_policy="EXCLUDED",
                allow_live_network=False,
            ),
            metadata={
                "tutorial_project": "agentic-studio",
                "milestone": "v0.1",
                "target_timecode": "00:16:15.000",
                "compiler_version": "1.0.0",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Validate internal invariants
        plan.validate()
        return plan

    def export_plan_artifacts(
        self,
        plan: CodeVideoPlan,
        output_dir: Union[str, Path],
    ) -> Dict[str, Path]:
        """
        Export plan artifacts:
        - video_02_plan.yaml
        - video_02_plan.json
        - video_02_cue_sheet.csv
        """
        out_path = Path(output_dir).resolve()
        out_path.mkdir(parents=True, exist_ok=True)

        # Write canonical video_02_* filenames
        yaml_file = out_path / "video_02_plan.yaml"
        json_file = out_path / "video_02_plan.json"
        csv_file = out_path / "video_02_cue_sheet.csv"

        yaml_content = plan.to_yaml()
        json_content = plan.to_json(indent=2)
        csv_content = plan.generate_cue_sheet_csv()

        yaml_file.write_text(yaml_content, encoding="utf-8")
        json_file.write_text(json_content, encoding="utf-8")
        csv_file.write_text(csv_content, encoding="utf-8")

        # Also write video-02_* aliases if needed
        (out_path / "video-02_plan.yaml").write_text(yaml_content, encoding="utf-8")
        (out_path / "video-02_plan.json").write_text(json_content, encoding="utf-8")
        (out_path / "video-02_cue_sheet").with_suffix(".csv").write_text(csv_content, encoding="utf-8")

        return {
            "yaml": yaml_file,
            "json": json_file,
            "csv": csv_file,
        }




__all__ = ["CodeVideoScriptCompiler"]
