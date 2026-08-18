"""
Pass Definitions and Catalog for Video 02 Recording Pipeline (Phase 9).

Defines the authoritative 16 recording passes corresponding to the scenes and
milestones in Video 02 (Viết AI Agent Đầu Tiên Bằng Python).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from windagent_core.errors.exceptions import NotFoundError, ValidationError
from windagent_workflows.code_video.contracts import (
    Resolution,
    VisualMode,
)


class PassType(str, Enum):
    """Categorical type for each recording pass."""
    COLD_OPEN = "COLD_OPEN"
    REPOSITORY_SETUP = "REPOSITORY_SETUP"
    MESSAGE_DATACLASS = "MESSAGE_DATACLASS"
    CONFIG_DATACLASS = "CONFIG_DATACLASS"
    LLM_PROTOCOL = "LLM_PROTOCOL"
    FAKE_LLM = "FAKE_LLM"
    AGENT_CORE = "AGENT_CORE"
    COGNITIVE_LOOP = "COGNITIVE_LOOP"
    REAL_PROVIDER = "REAL_PROVIDER"
    API_KEY_SECURITY = "API_KEY_SECURITY"
    FIRST_RUN = "FIRST_RUN"
    TESTING = "TESTING"
    SCOPE_CHECKLIST = "SCOPE_CHECKLIST"
    ARCHITECTURE_REVIEW = "ARCHITECTURE_REVIEW"
    GIT_MILESTONE = "GIT_MILESTONE"
    OUTRO_TEASER = "OUTRO_TEASER"


class PassStatus(str, Enum):
    """Execution status of a recording pass."""
    PENDING = "PENDING"
    RECORDING = "RECORDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PassDefinition:
    """
    Authoritative specification for a single recording pass.
    """
    pass_id: str
    pass_number: int
    name: str
    scene_id: str
    start_ms: int
    end_ms: int
    duration_ms: int
    frame_count: int
    pass_type: PassType
    visual_mode: VisualMode
    description: str
    required_graphics: List[str] = field(default_factory=list)
    expected_files: List[str] = field(default_factory=list)
    expected_terminal_command: Optional[str] = None
    expected_terminal_output: Optional[str] = None
    checkpoint_id: Optional[str] = None
    security_check_required: bool = True

    def __post_init__(self) -> None:
        if self.duration_ms != self.end_ms - self.start_ms:
            raise ValidationError(
                f"Pass duration mismatch for {self.pass_id}: "
                f"duration_ms={self.duration_ms} != {self.end_ms - self.start_ms}"
            )
        expected_frames = (self.duration_ms * 30) // 1000
        if self.frame_count != expected_frames:
            raise ValidationError(
                f"Frame count mismatch for {self.pass_id}: "
                f"frame_count={self.frame_count} != expected {expected_frames}"
            )

    @property
    def semantic_hash(self) -> str:
        """Deterministic SHA-256 hash of pass semantic definition."""
        data = {
            "pass_id": self.pass_id,
            "pass_number": self.pass_number,
            "name": self.name,
            "scene_id": self.scene_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "frame_count": self.frame_count,
            "pass_type": self.pass_type.value,
            "visual_mode": self.visual_mode.value,
            "description": self.description,
            "required_graphics": sorted(self.required_graphics),
            "expected_files": sorted(self.expected_files),
            "expected_terminal_command": self.expected_terminal_command,
            "checkpoint_id": self.checkpoint_id,
        }
        serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pass_id": self.pass_id,
            "pass_number": self.pass_number,
            "name": self.name,
            "scene_id": self.scene_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "frame_count": self.frame_count,
            "pass_type": self.pass_type.value,
            "visual_mode": self.visual_mode.value,
            "description": self.description,
            "required_graphics": list(self.required_graphics),
            "expected_files": list(self.expected_files),
            "expected_terminal_command": self.expected_terminal_command,
            "expected_terminal_output": self.expected_terminal_output,
            "checkpoint_id": self.checkpoint_id,
            "security_check_required": self.security_check_required,
            "semantic_hash": self.semantic_hash,
        }


@dataclass
class PassRecord:
    """
    Runtime execution record of a recorded pass.
    """
    pass_id: str
    scene_id: str
    status: PassStatus
    duration_ms: int
    frame_count: int
    source_hash: str
    render_config_hash: str
    output_hash: str
    verified_terminal: bool
    secret_clean: bool
    keyframe_marks: List[Dict[str, Any]] = field(default_factory=list)
    artifacts_produced: List[str] = field(default_factory=list)
    recorded_at: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pass_id": self.pass_id,
            "scene_id": self.scene_id,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "frame_count": self.frame_count,
            "source_hash": self.source_hash,
            "render_config_hash": self.render_config_hash,
            "output_hash": self.output_hash,
            "verified_terminal": self.verified_terminal,
            "secret_clean": self.secret_clean,
            "keyframe_marks": self.keyframe_marks,
            "artifacts_produced": self.artifacts_produced,
            "recorded_at": self.recorded_at,
            "notes": self.notes,
        }


class PassCatalog:
    """
    Authoritative catalog managing all 16 recording passes for Video 02.
    """

    PASS_DEFINITIONS: List[PassDefinition] = [
        # Pass 1 — Cold Open (Scene S01)
        PassDefinition(
            pass_id="PASS_01_COLD_OPEN",
            pass_number=1,
            name="Cold Open",
            scene_id="S01",
            start_ms=0,
            end_ms=25000,
            duration_ms=25000,
            frame_count=750,
            pass_type=PassType.COLD_OPEN,
            visual_mode=VisualMode.SPLIT,
            description="Chạy python -m src.agent, prompt recursion, hiển thị response và flow User → Agent → LLM → Answer",
            required_graphics=["DIAG_01_FINAL_ARCH"],
            expected_files=["src/agent.py"],
            expected_terminal_command="python -m src.agent",
            expected_terminal_output="Recursion là một kỹ thuật trong lập trình nơi một hàm tự gọi chính nó",
            checkpoint_id="STEP_07_FINAL",
        ),
        # Pass 2 — Repository Setup (Scene S05)
        PassDefinition(
            pass_id="PASS_02_REPO_SETUP",
            pass_number=2,
            name="Repository Setup",
            scene_id="S05",
            start_ms=130000,
            end_ms=165000,
            duration_ms=35000,
            frame_count=1050,
            pass_type=PassType.REPOSITORY_SETUP,
            visual_mode=VisualMode.CODE_STUDIO,
            description="Khởi tạo git repository, cấu trúc thư mục agentic-studio (src/, tests/, README.md)",
            required_graphics=[],
            expected_files=["README.md", ".gitignore"],
            expected_terminal_command="git init",
            expected_terminal_output="Initialized empty Git repository",
            checkpoint_id="STEP_00_INIT",
        ),

        # Pass 3 — Message Dataclass (Scene S06)
        PassDefinition(
            pass_id="PASS_03_MESSAGE",
            pass_number=3,
            name="Message Dataclass",
            scene_id="S06",
            start_ms=165000,
            end_ms=220000,
            duration_ms=55000,
            frame_count=1650,
            pass_type=PassType.MESSAGE_DATACLASS,
            visual_mode=VisualMode.CODE_STUDIO,
            description="Replay và highlight @dataclass(frozen=True) Message với role và content",
            required_graphics=["OVR_S06_MESSAGE_DATACLASS"],
            expected_files=["src/message.py"],
            checkpoint_id="STEP_01_MESSAGE",
        ),
        # Pass 4 — AgentConfig (Scene S07)
        PassDefinition(
            pass_id="PASS_04_CONFIG",
            pass_number=4,
            name="AgentConfig",
            scene_id="S07",
            start_ms=220000,
            end_ms=275000,
            duration_ms=55000,
            frame_count=1650,
            pass_type=PassType.CONFIG_DATACLASS,
            visual_mode=VisualMode.CODE_STUDIO,
            description="Replay AgentConfig với name, system_prompt, model, temperature",
            required_graphics=["OVR_S07_CONFIG_FIELDS"],
            expected_files=["src/config.py"],
            checkpoint_id="STEP_02_CONFIG",
        ),
        # Pass 5 — LLMClient Protocol (Scene S08)
        PassDefinition(
            pass_id="PASS_05_LLM_PROTOCOL",
            pass_number=5,
            name="LLMClient Protocol",
            scene_id="S08",
            start_ms=275000,
            end_ms=360000,
            duration_ms=85000,
            frame_count=2550,
            pass_type=PassType.LLM_PROTOCOL,
            visual_mode=VisualMode.CODE_STUDIO,
            description="Replay LLMClient protocol abstraction và diagram đa dạng provider",
            required_graphics=["DIAG_04_LLMCLIENT_ABSTRACTION", "OVR_S08_LLMCLIENT_PROTOCOL"],
            expected_files=["src/llm.py"],
            checkpoint_id="STEP_03_PROTOCOL",
        ),
        # Pass 6 — FakeLLMClient (Scene S09)
        PassDefinition(
            pass_id="PASS_06_FAKE_LLM",
            pass_number=6,
            name="Fake LLM Client",
            scene_id="S09",
            start_ms=360000,
            end_ms=410000,
            duration_ms=50000,
            frame_count=1500,
            pass_type=PassType.FAKE_LLM,
            visual_mode=VisualMode.CODE_STUDIO,
            description="Replay FakeLLMClient offline và callout Unit Test ≠ Real API",
            required_graphics=["OVR_S09_UNIT_TEST_VS_API"],
            expected_files=["src/fake_llm.py"],
            checkpoint_id="STEP_04_FAKE_LLM",
        ),
        # Pass 7 — Agent Core (Scene S10)
        PassDefinition(
            pass_id="PASS_07_AGENT_CORE",
            pass_number=7,
            name="Agent Core Implementation",
            scene_id="S10",
            start_ms=410000,
            end_ms=505000,
            duration_ms=95000,
            frame_count=2850,
            pass_type=PassType.AGENT_CORE,
            visual_mode=VisualMode.CODE_STUDIO,
            description="Replay constructor và run() với system prompt và execution flow overlay",
            required_graphics=["OVR_S10_EXECUTION_FLOW"],
            expected_files=["src/agent.py"],
            checkpoint_id="STEP_05_AGENT",
        ),
        # Pass 8 — Is This An Agent? (Scene S11)
        PassDefinition(
            pass_id="PASS_08_IS_THIS_AGENT",
            pass_number=8,
            name="Is This An Agent?",
            scene_id="S11",
            start_ms=505000,
            end_ms=540000,
            duration_ms=35000,
            frame_count=1050,
            pass_type=PassType.COGNITIVE_LOOP,
            visual_mode=VisualMode.DIAGRAM,
            description="Phân tích cognitive loop Observe → Decide → Act → Observe và làm mờ các phần chưa có",
            required_graphics=["DIAG_05A_COGNITIVE_LOOP", "DIAG_05B_MISSING_CAPABILITIES"],
            expected_files=[],
        ),
        # Pass 9 — Real Provider (Scene S12)
        PassDefinition(
            pass_id="PASS_09_REAL_PROVIDER",
            pass_number=9,
            name="Real Provider Architecture",
            scene_id="S12",
            start_ms=540000,
            end_ms=615000,
            duration_ms=75000,
            frame_count=2250,
            pass_type=PassType.REAL_PROVIDER,
            visual_mode=VisualMode.CODE_STUDIO,
            description="Replay OpenAILLMClient và phân định Clean Architecture Domain vs Infrastructure",
            required_graphics=["DIAG_06_DOMAIN_VS_INFRA"],
            expected_files=["src/provider.py"],
            checkpoint_id="STEP_07_FINAL",
        ),
        # Pass 10 — API Key Security (Scene S13)
        PassDefinition(
            pass_id="PASS_10_API_SECURITY",
            pass_number=10,
            name="API Key Configuration & Security",
            scene_id="S13",
            start_ms=615000,
            end_ms=665000,
            duration_ms=50000,
            frame_count=1500,
            pass_type=PassType.API_KEY_SECURITY,
            visual_mode=VisualMode.CODE_STUDIO,
            description="Replay .env.example, .gitignore và visual cảnh báo không commit API key",
            required_graphics=["OVR_S13_API_KEY_SECURITY"],
            expected_files=[".env.example", ".gitignore"],
            security_check_required=True,
        ),
        # Pass 11 — First Run (Scene S14)
        PassDefinition(
            pass_id="PASS_11_FIRST_RUN",
            pass_number=11,
            name="First Execution",
            scene_id="S14",
            start_ms=665000,
            end_ms=720000,
            duration_ms=55000,
            frame_count=1650,
            pass_type=PassType.FIRST_RUN,
            visual_mode=VisualMode.CODE_STUDIO,
            description="Replay đoạn code khởi chạy Agent và hiển thị kết quả terminal thật",
            required_graphics=[],
            expected_files=["src/agent.py"],
            expected_terminal_command="python -m src.agent",
            expected_terminal_output="Recursion là một kỹ thuật trong lập trình nơi một hàm tự gọi chính nó",
            checkpoint_id="STEP_07_FINAL",

        ),
        # Pass 12 — Testing (Scene S15)
        PassDefinition(
            pass_id="PASS_12_TESTING",
            pass_number=12,
            name="Pytest Execution",
            scene_id="S15",
            start_ms=720000,
            end_ms=800000,
            duration_ms=80000,
            frame_count=2400,
            pass_type=PassType.TESTING,
            visual_mode=VisualMode.CODE_STUDIO,
            description="Replay tests/test_agent.py và chạy pytest ra kết quả 2 passed",
            required_graphics=[],
            expected_files=["tests/test_agent.py"],
            expected_terminal_command="pytest",
            expected_terminal_output="2 passed in 0.04s",
            checkpoint_id="STEP_06_TESTS",
        ),
        # Pass 13 — Not Yet Checklist (Scene S16)
        PassDefinition(
            pass_id="PASS_13_NOT_YET",
            pass_number=13,
            name="Not Yet Scope Checklist",
            scene_id="S16",
            start_ms=800000,
            end_ms=850000,
            duration_ms=50000,
            frame_count=1500,
            pass_type=PassType.SCOPE_CHECKLIST,
            visual_mode=VisualMode.CHECKLIST,
            description="Bảng checklist 7 tính năng chưa có tại v0.1 (Tool Calling, Loop, Memory, RAG...)",
            required_graphics=["CHECKLIST_S16_NOT_YET"],
            expected_files=[],
        ),
        # Pass 14 — Architecture Review (Scene S17)
        PassDefinition(
            pass_id="PASS_14_ARCH_REVIEW",
            pass_number=14,
            name="Architecture Review",
            scene_id="S17",
            start_ms=850000,
            end_ms=900000,
            duration_ms=50000,
            frame_count=1500,
            pass_type=PassType.ARCHITECTURE_REVIEW,
            visual_mode=VisualMode.DIAGRAM,
            description="Tổng quan kiến trúc Clean Architecture hoàn chỉnh toàn màn hình",
            required_graphics=["DIAG_06_DOMAIN_VS_INFRA"],
            expected_files=[],
        ),
        # Pass 15 — Git Milestone (Scene S18)
        PassDefinition(
            pass_id="PASS_15_GIT_MILESTONE",
            pass_number=15,
            name="Git Milestone v0.1",
            scene_id="S18",
            start_ms=900000,
            end_ms=935000,
            duration_ms=35000,
            frame_count=1050,
            pass_type=PassType.GIT_MILESTONE,
            visual_mode=VisualMode.CODE_STUDIO,
            description="Replay git add/commit/tag video-02 và title card Agentic Studio v0.1",
            required_graphics=["CARD_S18_MILESTONE"],
            expected_files=[],
            expected_terminal_command="git tag v0.1",
            expected_terminal_output="",
            checkpoint_id="STEP_07_FINAL",
        ),
        # Pass 16 — Outro & Teaser (Scene S19)
        PassDefinition(
            pass_id="PASS_16_OUTRO_TEASER",
            pass_number=16,
            name="Outro & Video 03 Teaser",
            scene_id="S19",
            start_ms=935000,
            end_ms=975000,
            duration_ms=40000,
            frame_count=1200,
            pass_type=PassType.OUTRO_TEASER,
            visual_mode=VisualMode.OUTRO,
            description="Outro User → Agent → LLM → ?, LLM ≠ Function Executor và teaser Video 03 Tool Calling",
            required_graphics=["DIAG_03_TODAY_VS_NEXT", "OVR_S19_LLM_NOT_EXECUTOR", "CARD_S19_TEASER"],
            expected_files=[],
        ),
    ]

    @classmethod
    def get_all_passes(cls) -> List[PassDefinition]:
        """Return all 16 authoritative pass definitions."""
        return list(cls.PASS_DEFINITIONS)

    @classmethod
    def get_pass(cls, pass_id: str) -> PassDefinition:
        """Lookup pass definition by pass_id."""
        for p in cls.PASS_DEFINITIONS:
            if p.pass_id == pass_id:
                return p
        raise NotFoundError(f"Pass with id '{pass_id}' not found in PassCatalog.")

    @classmethod
    def get_pass_by_scene(cls, scene_id: str) -> Optional[PassDefinition]:
        """Lookup pass definition by associated scene_id."""
        for p in cls.PASS_DEFINITIONS:
            if p.scene_id == scene_id:
                return p
        return None

    @classmethod
    def total_pass_duration_ms(cls) -> int:
        """Total duration of all 16 passes (Note: S02, S03, S04 are preamble scenes)."""
        return sum(p.duration_ms for p in cls.PASS_DEFINITIONS)

    @classmethod
    def total_pass_frames(cls) -> int:
        """Total frames of all 16 passes."""
        return sum(p.frame_count for p in cls.PASS_DEFINITIONS)
