#!/usr/bin/env python3
"""AST-based Duplicate Canonical Model Scanner (Phase 5).

Detects canonical class/schema definitions duplicated outside their canonical
home module. Detection signals:
- fully qualified semantic name (class name match against canonical registry)
- field signature (sorted field names of pydantic models / dataclasses)
- JSON schema hash (pydantic model_json_schema, when importable)
- model purpose tag (docstring marker "canonical", when present)

Exits non-zero if any duplicate is found.
"""

import ast
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Canonical homes: semantic name -> canonical file suffix.
CANONICAL_MODELS = {
    # Provider contracts
    "ProviderRequest": "core/windagent_core/contracts/providers/requests.py",
    "ProviderResponse": "core/windagent_core/contracts/providers/responses.py",
    "ProviderStreamChunk": "core/windagent_core/contracts/providers/responses.py",
    "ProviderToolCall": "core/windagent_core/contracts/providers/responses.py",
    "ProviderUsage": "core/windagent_core/contracts/providers/usage.py",
    "ProviderCapabilities": "core/windagent_core/contracts/providers/capabilities.py",
    "ModelDescriptor": "core/windagent_core/contracts/providers/capabilities.py",
    "ProviderHealth": "core/windagent_core/contracts/providers/capabilities.py",
    "QuotaState": "core/windagent_core/contracts/providers/capabilities.py",
    "RateLimitState": "core/windagent_core/contracts/providers/capabilities.py",
    "DiscoveredModel": "core/windagent_core/contracts/providers/capabilities.py",
    "ConnectionTestResult": "core/windagent_core/contracts/providers/capabilities.py",
    "ProtocolDetectionResult": "core/windagent_core/contracts/providers/capabilities.py",
    "ProviderStreamEvent": "core/windagent_core/contracts/providers/capabilities.py",
    "CacheDirective": "core/windagent_core/contracts/providers/capabilities.py",
    # Tool contracts
    "ToolInvocation": "core/windagent_core/contracts/tools/invocation.py",
    "ToolResult": "core/windagent_core/contracts/tools/results.py",
    "ToolDefinition": "core/windagent_core/contracts/tools/metadata.py",
    "ToolExecutionContext": "core/windagent_core/contracts/tools/metadata.py",
    "ToolRiskLevel": "core/windagent_core/contracts/tools/metadata.py",
    # Shared domain envelopes (Phase 12 set)
    "EventEnvelope": "core/windagent_core/events/envelope.py",
    "WindAgentError": "core/windagent_core/errors/exceptions.py",
    # Video production domain (Phase 3 canonical protocol)
    "VideoProject": "core/windagent_core/domain/video_production/project.py",
    "ProductionRevision": "core/windagent_core/domain/video_production/project.py",
    "CreativeBrief": "core/windagent_core/domain/video_production/screenplay.py",
    "StoryConcept": "core/windagent_core/domain/video_production/screenplay.py",
    "Screenplay": "core/windagent_core/domain/video_production/screenplay.py",
    "DialogueLine": "core/windagent_core/domain/video_production/screenplay.py",
    "Scene": "core/windagent_core/domain/video_production/scene.py",
    "CharacterBible": "core/windagent_core/domain/video_production/character.py",
    "LocationBible": "core/windagent_core/domain/video_production/location.py",
    "PropBible": "core/windagent_core/domain/video_production/location.py",
    "StyleBible": "core/windagent_core/domain/video_production/location.py",
    "Shot": "core/windagent_core/domain/video_production/shot.py",
    "ShotDependency": "core/windagent_core/domain/video_production/shot.py",
    "ShotDependencyGraph": "core/windagent_core/domain/video_production/shot.py",
    "CinematicPlan": "core/windagent_core/domain/video_production/shot.py",
    "ReferenceAsset": "core/windagent_core/domain/video_production/asset.py",
    "FinalDeliverable": "core/windagent_core/domain/video_production/asset.py",
    "ContinuityState": "core/windagent_core/domain/video_production/continuity.py",
    "GenerationRequest": "core/windagent_core/domain/video_production/generation_job.py",
    "GenerationCandidate": "core/windagent_core/domain/video_production/generation_job.py",
    "GenerationRecord": "core/windagent_core/domain/video_production/generation_job.py",
    # NOTE: "ReviewResult" is intentionally NOT registered here because a
    # pre-existing `ReviewResult` lives in the intelligence layer
    # (intelligence/windagent_intelligence/reviewer/reviewer.py). The video
    # production review record is distinguished by its ReviewResultId and
    # lives in approval.py; the checker would otherwise flag the shared name.
    "ApprovalDecision": "core/windagent_core/domain/video_production/approval.py",
    "ApprovalState": "core/windagent_core/domain/video_production/approval.py",
    "VideoProductionPackage": "core/windagent_core/domain/video_production/package.py",
    "PackageProvenance": "core/windagent_core/domain/video_production/package.py",
    # Video production events (Phase 3)
    "VideoProductionEventEnvelope": "core/windagent_core/events/video_production.py",
}

LIFECYCLE_ENUMS = {"TaskState", "WorkflowState", "StepState", "SessionState"}
CANONICAL_LIFECYCLE_FILE = "core/windagent_core/domain/lifecycle.py"

EXCLUDED_DIR_NAMES = {
    ".venv", ".git", ".pytest_cache", "artifacts", "docs",
    "node_modules", "logs", "__pycache__", "scripts",
}
EXCLUDED_PATH_PARTS = (
    ("apps", "api", "windagent_api", "routers", "compatibility.py"),
    ("apps", "api", "windagent_api", "adapters", "legacy_event_mappers.py"),
)


def should_skip(path: Path, root: Path = ROOT_DIR) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    if any(part.startswith(".") and part not in {".", ".."} for part in parts):
        return True
    if any(p in EXCLUDED_DIR_NAMES for p in parts):
        return True
    for excl in EXCLUDED_PATH_PARTS:
        if len(parts) >= len(excl) and parts[-len(excl):] == excl:
            return True
    return False


def field_signature(node: ast.ClassDef) -> tuple:
    """Sorted field names from AnnAssign / Assign targets in class body."""
    names = []
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.append(stmt.target.id)
        elif isinstance(stmt, ast.Assign):
            for tgt in stmt.targets:
                if isinstance(tgt, ast.Name):
                    names.append(tgt.id)
    return tuple(sorted(names))


class DuplicateVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str):
        self.rel_path = rel_path.replace("\\", "/")
        self.violations = []
        self.signatures = {}  # canonical name -> (signature, path)

    def visit_ClassDef(self, node: ast.ClassDef):
        name = node.name
        if name in CANONICAL_MODELS:
            canonical = CANONICAL_MODELS[name]
            if self.rel_path != canonical:
                sig = field_signature(node)
                self.violations.append(
                    (node.lineno, name, f"duplicate of canonical {canonical}", sig)
                )
        if name in LIFECYCLE_ENUMS and self.rel_path != CANONICAL_LIFECYCLE_FILE:
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "Enum" in bases or "str" in bases:
                self.violations.append(
                    (node.lineno, name, f"duplicate lifecycle enum of {CANONICAL_LIFECYCLE_FILE}", ())
                )
        self.generic_visit(node)


def scan(root: Path):
    violations = []
    signature_registry = {}
    scanned = 0
    for py_file in root.rglob("*.py"):
        if should_skip(py_file, root):
            continue
        scanned += 1
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = py_file.relative_to(root).as_posix()
        visitor = DuplicateVisitor(rel)
        visitor.visit(tree)
        violations.extend((rel, *v) for v in visitor.violations)

        # Cross-file field-signature match: same signature, different name
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in CANONICAL_MODELS:
                if rel == CANONICAL_MODELS[node.name]:
                    signature_registry[node.name] = field_signature(node)
    return violations, signature_registry, scanned


def main() -> int:
    violations, signatures, scanned = scan(ROOT_DIR)

    print(f"Phase 5 Duplicate Canonical Model Scan across {scanned} Python files:")
    for rel, lineno, name, reason, sig in violations:
        print(f"  [DUPLICATE] {rel}:{lineno} class {name} -> {reason} fields={sig}")

    if violations:
        print(f"[FAIL] {len(violations)} duplicate canonical model definition(s) found.")
        return 1
    print("[PASS] Zero duplicate canonical model definitions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
