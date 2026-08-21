"""
Core protocols for Code Video Tool implementations.

Workflows depend on these protocols, not on concrete tool implementations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Sequence, runtime_checkable

from windagent_core.contracts.code_video.models import CodeVideoPlan
from windagent_core.contracts.code_video.assembly import (
    CueSheet,
    MasterAssemblyResult,
)
from windagent_core.contracts.code_video.capture import TakeReceipt


@runtime_checkable
class AssemblerPort(Protocol):
    """Protocol for visual master assembly."""

    def assemble_master(
        self,
        plan: CodeVideoPlan,
        takes: Sequence[TakeReceipt],
        graphics_manifest: Optional[Dict[str, Any]] = None,
        output_dir: Optional[Path] = None,
    ) -> MasterAssemblyResult:
        ...


@runtime_checkable
class CompilerPort(Protocol):
    """Protocol for code video script compilation."""

    def compile_video_02_plan(self) -> CodeVideoPlan:
        ...


@runtime_checkable
class QCEnginePort(Protocol):
    """Protocol for visual QC engine."""

    @classmethod
    def evaluate_video_02(
        cls,
        plan: CodeVideoPlan,
        assembly_result: MasterAssemblyResult,
        cue_sheet: CueSheet,
        source_code_agent_py: str,
        source_code_test_py: Optional[str] = None,
        terminal_receipts: Optional[Sequence[Dict[str, Any]]] = None,
        artifacts_to_scan: Optional[Dict[str, str]] = None,
        graphics_catalog: Any = None,
        theme: Any = None,
    ) -> Any:
        ...


@runtime_checkable
class ProgramCertificationPort(Protocol):
    """Protocol for program certification engine."""

    def certify_program(
        self,
        plan: CodeVideoPlan,
        qc_report: Any,
        final_dir: Path,
        repo_root: Path,
    ) -> Any:
        ...

    @staticmethod
    def generate_timecoded_script(plan: CodeVideoPlan) -> str:
        ...


@runtime_checkable
class ReplayEnginePort(Protocol):
    """Protocol for deterministic replay engine."""

    def execute_full_plan(self) -> Any:
        ...

    def verify_determinism(self, runs: int = 2) -> tuple[bool, str, Dict[str, str]]:
        ...
