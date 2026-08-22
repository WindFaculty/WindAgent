#!/usr/bin/env python3
"""
Phase 6 verification — VP6_PREPRODUCTION_KERNEL_CANONICAL (plan 02 §14-§18).

Verifies the canonical video pre-production kernel
(`intelligence/windagent_intelligence/video/`) against the ratified
contracts in `docs/video_production/preproduction/`:

  artifacts/video_production/phase_06/
  ├── capability_matrix.json
  ├── golden_comparison.json
  ├── provider_contract_receipt.json
  ├── no_upstream_import_report.json
  ├── integration_test_receipt.json
  └── phase_verdict.json

Gate conditions (plan 02 §18):
  1. the kernel package is complete — all 9 vertical slices exist with the
     documented methods and typed failures;
  2. the equivalence policy is met — semantic comparison against the three
     Phase 5 golden fixtures passes on blocking fields
     (equivalence_policy.md);
  3. provider neutrality — model-backed capabilities call only the
     `PreproductionModelPort` protocol; no `windagent_providers` /
     `windagent_tools` import in the kernel;
  4. no upstream import — the kernel never imports/launches
     `third_party/videoclaw` and never mutates `sys.path`;
  5. integration — idea → full `VideoProductionPackage v1` assembles and
     passes the Phase 3 canonical validator.

Supports --no-write / --verify-only (runs all checks, writes nothing).
"""

from __future__ import annotations

import asyncio
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_06"
FIXTURES_DIR = (
    ROOT / "tests" / "fixtures" / "video_production"
    / "videoclaw_characterization"
)
KERNEL_DIR = ROOT / "intelligence" / "windagent_intelligence" / "video"

FIXTURE_IDS = (
    "fixture_short_cartoon",
    "fixture_two_character_dialogue",
    "fixture_multi_scene_drama",
)

# Root of the canonical workspace is always importable in the venv; ensure it
# even when this script runs from another cwd.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Evidence writers
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def _load_fixtures() -> list[dict]:
    fixtures = []
    for fx_id in FIXTURE_IDS:
        base = FIXTURES_DIR / fx_id
        brief = json.loads((base / "brief.json").read_text(encoding="utf-8"))
        responses = json.loads((base / "provider_responses.json").read_text(encoding="utf-8"))
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        fixtures.append({
            "fixture_id": fx_id,
            "brief": brief,
            "responses": responses,
            "manifest": manifest,
        })
    return fixtures


# ---------------------------------------------------------------------------
# Deterministic model port (never touches a real provider)
# ---------------------------------------------------------------------------


class DeterministicModelPort:
    """Pinned, deterministic model responses keyed by capability.

    This is a harness fake — it fulfils the `PreproductionModelPort`
    protocol but never performs a network call, so the golden comparison and
    integration receipts are fully deterministic and offline.
    """

    def __init__(self, responses: dict) -> None:
        self._responses = responses

    async def complete(self, request):  # noqa: ANN001
        content = self._responses.get(request.capability, "")
        from windagent_intelligence.video.ports import ModelCompletionResult

        return ModelCompletionResult(
            capability=request.capability,
            content=content,
            provider="deterministic-fake",
        )


def _fixture_pinned_responses(fx: dict) -> dict:
    """Build deterministic per-capability responses from a golden fixture."""
    brief = fx["brief"]
    responses = fx["responses"]
    script = responses["generate_script"]
    title = brief.get("title", "Untitled")
    brief_json = json.dumps({
        "title": title,
        "logline": "Golden fixture logline.",
        "genre": ["Animation", "Adventure"],
        "tone": "Warm",
        "audience": "General",
        "target_duration_seconds": 60,
        "aspect_ratio": brief.get("video_ratio", "16:9"),
        "production_constraints": {"style": brief.get("style", "anime")},
    }, ensure_ascii=False)

    outline_json = json.dumps({
        "title": title,
        "premise": "Golden fixture premise.",
        "synopsis": "Golden fixture synopsis.",
        "themes": ["friendship", "adventure", "growth"],
        "beats": ["Opening", "Conflict", "Resolution"],
    }, ensure_ascii=False)

    style_json = json.dumps({
        "name": f"{brief.get('style', 'anime')} style",
        "visual_style": brief.get("style", "anime"),
        "color_palette": ["#FFD700", "#8B4513"],
        "lighting_rules": ["Warm", "Soft shadows"],
    }, ensure_ascii=False)

    # Continuation response carries ONLY the new episode(s) — the kernel must
    # append them without renumbering or dropping the existing locked content.
    continuation_text = (
        "第2集 新的冒险\n\n"
        "**第2集-第1场 晨 外 森林\n人物：豆豆\n\n"
        "豆豆：天亮了，我们出发吧！\n"
        "<action>豆豆精神抖擞地看向远方。</action>\n"
    )

    return {
        "brief_expansion": brief_json,
        "story_outline": outline_json,
        "screenplay_generation": script,
        "style_design": style_json,
        "continuation": continuation_text,
    }


# ---------------------------------------------------------------------------
# 1. Capability matrix
# ---------------------------------------------------------------------------

SLICE_CONTRACT = [
    # (slice, service name, model-backed, key methods)
    (1, "CreativeBriefExpander", True, ["expand"]),
    (2, "StoryOutliner", True, ["outline"]),
    (3, "ScreenplayWriter", True, ["write"]),
    (4, "DialogueNarrator", False, ["narrate"]),
    (5, "EntityExtractor", False, ["extract"]),
    (6, "StyleDesigner", True, ["design"]),
    (7, "ContinuationService", True, ["continue_screenplay"]),
    (8, "AssetPromptSpecBuilder", False, ["build_character", "build_location", "build_style"]),
    (9, "PackageAssembler", False, ["assemble"]),
]


def build_capability_matrix() -> dict:
    """Assert the kernel exports all 9 slices with the documented methods."""
    from windagent_intelligence.video import (
        AssetPromptSpecBuilder,
        ContinuationService,
        CreativeBriefExpander,
        DialogueNarrator,
        EntityExtractor,
        PackageAssembler,
        ScreenplayWriter,
        StoryOutliner,
        StyleDesigner,
    )

    services = {
        "CreativeBriefExpander": CreativeBriefExpander,
        "StoryOutliner": StoryOutliner,
        "ScreenplayWriter": ScreenplayWriter,
        "DialogueNarrator": DialogueNarrator,
        "EntityExtractor": EntityExtractor,
        "StyleDesigner": StyleDesigner,
        "ContinuationService": ContinuationService,
        "AssetPromptSpecBuilder": AssetPromptSpecBuilder,
        "PackageAssembler": PackageAssembler,
    }
    rows = []
    ok = True
    for slice_no, name, model_backed, methods in SLICE_CONTRACT:
        cls = services.get(name)
        missing = []
        if cls is None:
            missing.append("service not exported")
        else:
            for method in methods:
                if not hasattr(cls, method):
                    missing.append(f"method {method} missing")
        present = cls is not None and not missing
        ok = ok and present
        rows.append({
            "slice": slice_no,
            "capability": name,
            "model_backed": model_backed,
            "present": present,
            "missing": missing,
        })
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "slice_count": len(rows),
        "all_present": ok,
        "slices": rows,
    }


# ---------------------------------------------------------------------------
# 2. Golden semantic comparison (equivalence_policy.md)
# ---------------------------------------------------------------------------


def _expected_names_from_meta(responses: dict) -> tuple[list[str], list[str]]:
    """Golden character/location names from the pinned meta_extract JSON."""
    try:
        meta = json.loads(responses["meta_extract"])
    except (json.JSONDecodeError, KeyError):
        return [], []
    characters = [str(c.get("name")) for c in meta.get("characters", []) if c.get("name")]
    settings = [str(s.get("name")) for s in meta.get("settings", []) if s.get("name")]
    return characters, settings


def _precision_recall(extracted: list[str], golden: list[str]) -> dict:
    extracted_set = set(extracted)
    golden_set = set(golden)
    true_pos = len(extracted_set & golden_set)
    precision = true_pos / len(extracted_set) if extracted_set else 0.0
    recall = true_pos / len(golden_set) if golden_set else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "extracted": sorted(extracted_set),
        "golden": sorted(golden_set),
    }


async def _run_fixture_golden(fx: dict) -> dict:
    """Run offline capabilities + deterministic model path for one fixture."""
    from windagent_core.domain.video_production.enums import (
        InvalidationIntent,
        ScreenplayStatus,
    )
    from windagent_intelligence.video import (
        AssetPromptSpecBuilder,
        ContinuationService,
        CreativeBriefExpander,
        DialogueNarrator,
        EntityExtractor,
        PackageAssembler,
        ScreenplayWriter,
        StoryOutliner,
        StyleDesigner,
    )
    from windagent_intelligence.video.ids import StableIdFactory

    fx_id = fx["fixture_id"]
    brief_data = fx["brief"]
    responses = fx["responses"]
    pinned = _fixture_pinned_responses(fx)
    port = DeterministicModelPort(pinned)
    ids = StableIdFactory(seed=f"phase6-golden-{fx_id}")

    result: dict = {"fixture_id": fx_id, "checks": {}, "blocking_failed": []}

    # --- Slice 1: CreativeBriefExpander ---
    expander = CreativeBriefExpander(port, id_factory=ids)
    expanded = await expander.expand(brief_data.get("idea", ""))
    brief = expanded["brief"]
    brief_ok = bool(brief.title) and brief.title == brief_data.get("title")
    result["checks"]["brief"] = {
        "ok": brief_ok,
        "title_preserved": brief.title == brief_data.get("title"),
        "audience_present": bool(brief.audience),
        "duration_present": brief.target_duration_seconds > 0,
        "constraints_present": bool(brief.production_constraints),
        "prompt_version": expanded["prompt_version"],
        "prompt_hash": expanded["prompt_hash"],
    }
    if not brief_ok:
        result["blocking_failed"].append("brief")

    # --- Slice 2: StoryOutliner ---
    outliner = StoryOutliner(port, id_factory=ids)
    outlined = await outliner.outline(brief)
    concept = outlined["concept"]
    outline_ok = bool(concept.premise) and bool(concept.synopsis) and bool(concept.themes)
    beats_ok = bool(outlined.get("beats"))
    result["checks"]["outline"] = {
        "ok": outline_ok and beats_ok,
        "premise_present": bool(concept.premise),
        "synopsis_present": bool(concept.synopsis),
        "themes_sorted": concept.themes == sorted(concept.themes),
        "beats_present": beats_ok,
        "prompt_version": outlined["prompt_version"],
    }
    if not (outline_ok and beats_ok):
        result["blocking_failed"].append("outline")

    # --- Slice 3: ScreenplayWriter ---
    writer = ScreenplayWriter(port, id_factory=ids)
    written = await writer.write(concept)
    screenplay = written["screenplay"]
    golden_chars, golden_locs = _expected_names_from_meta(responses)
    scene_order_ok = [s.order for s in screenplay.scenes] == list(range(1, len(screenplay.scenes) + 1))
    dialogue_ok = bool(written["dialogue_lines"])
    narration_ok = any(s.action_description for s in screenplay.scenes)
    screenplay_ok = len(screenplay.scenes) >= 1 and scene_order_ok and dialogue_ok and narration_ok
    result["checks"]["screenplay"] = {
        "ok": screenplay_ok,
        "scene_count": len(screenplay.scenes),
        "scene_order_ok": scene_order_ok,
        "dialogue_attributed": dialogue_ok,
        "narration_present": narration_ok,
        "golden_characters": golden_chars,
        "screenplay_characters": screenplay.metadata.get("characters", []),
        "prompt_version": written["prompt_version"],
    }
    if not screenplay_ok:
        result["blocking_failed"].append("screenplay")

    # --- Slice 4: DialogueNarrator (offline) ---
    narrator = DialogueNarrator(id_factory=ids)
    narrated = narrator.narrate(responses["generate_script"], screenplay.scenes)
    narrator_ok = bool(narrated["dialogue_lines"]) and bool(narrated["narration_blocks"])
    result["checks"]["dialogue_narration"] = {
        "ok": narrator_ok,
        "dialogue_count": len(narrated["dialogue_lines"]),
        "narration_scene_count": len(narrated["narration_blocks"]),
        "character_map": sorted(narrated["character_map"].keys()),
    }
    if not narrator_ok:
        result["blocking_failed"].append("dialogue_narration")

    # --- Slice 5: EntityExtractor (offline) ---
    extractor = EntityExtractor(id_factory=ids)
    extracted = extractor.extract(
        screenplay,
        responses["meta_extract"],
        character_id_map=written.get("character_map", {}),
        location_id_map=written.get("location_map", {}),
    )
    char_names = [c.name for c in extracted["characters"]]
    loc_names = [location.name for location in extracted["locations"]]
    char_pr = _precision_recall(char_names, golden_chars)
    loc_pr = _precision_recall(loc_names, golden_locs)
    # Characters: precision+recall blocking. Locations: the kernel folds
    # screenplay scene locations that the meta omits (required so every
    # scene.location_id has a matching LocationBible for package validation),
    # so location equivalence is measured by RECALL (every golden setting
    # present); extra screenplay-derived locations are expected and allowed.
    entity_ok = (
        char_pr["precision"] >= 0.9 and char_pr["recall"] >= 0.9
        and loc_pr["recall"] >= 0.9
    )
    result["checks"]["entity_extraction"] = {
        "ok": entity_ok,
        "characters": char_pr,
        "locations": loc_pr,
        "location_equivalence": "recall>=0.9 (screenplay-derived extras allowed)",
    }
    if not entity_ok:
        result["blocking_failed"].append("entity_extraction")

    # --- Slice 6: StyleDesigner ---
    designer = StyleDesigner(port, id_factory=ids)
    styled = await designer.design(brief, screenplay)
    style = styled["style_bible"]
    style_ok = bool(style.visual_style) and bool(style.name)
    result["checks"]["style"] = {
        "ok": style_ok,
        "visual_style": style.visual_style,
        "constraint_from_brief": style.visual_style == brief_data.get("style", "anime"),
        "prompt_version": styled["prompt_version"],
    }
    if not style_ok:
        result["blocking_failed"].append("style")

    # --- Slice 7: ContinuationService ---
    locked = screenplay.model_copy(update={"status": ScreenplayStatus.LOCKED})
    existing_scene_ids = [str(s.scene_id) for s in locked.scenes]
    existing_order = [s.order for s in locked.scenes]
    continuation = ContinuationService(port, id_factory=ids)
    cont_result = await continuation.continue_screenplay(
        locked,
        brief,
        project_id="proj_phase6",
        parent_revision_id="rev_parent",
        created_by="verifier",
        invalidation_intent=InvalidationIntent.INVALIDATE_SHOT_PLAN,
    )
    proposal_scene_ids = [str(s.scene_id) for s in cont_result.proposal.scenes]
    existing_preserved = all(
        sid in proposal_scene_ids for sid in existing_scene_ids
    )
    order_preserved = [s.order for s in cont_result.proposal.scenes[: len(locked.scenes)]] == existing_order
    existing_episode_count_ok = (
        cont_result.existing_episode_count == int(locked.metadata.get("episode_count", 0) or 0)
    )
    continuation_ok = (
        existing_preserved
        and order_preserved
        and existing_episode_count_ok
        and cont_result.invalidation_intent == InvalidationIntent.INVALIDATE_SHOT_PLAN
        and cont_result.prompt_version
    )
    result["checks"]["continuation"] = {
        "ok": continuation_ok,
        "existing_scenes_preserved": existing_preserved,
        "existing_order_preserved": order_preserved,
        "existing_episode_count": cont_result.existing_episode_count,
        "existing_episode_count_preserved": existing_episode_count_ok,
        "invalidation_intent": cont_result.invalidation_intent.value,
        "proposal_status": cont_result.proposal.status.value,
        "added_scene_count": len(cont_result.proposal.scenes) - len(locked.scenes),
        "prompt_version": cont_result.prompt_version,
    }
    if not continuation_ok:
        result["blocking_failed"].append("continuation")

    # --- Slice 8: AssetPromptSpecBuilder (offline) ---
    builder = AssetPromptSpecBuilder()
    specs = builder.build_all(
        characters=extracted["characters"],
        locations=extracted["locations"],
        style=style,
    )
    specs_ok = bool(specs) and all(r.prompt_spec.version and r.prompt_spec.content_hash for r in specs)
    result["checks"]["asset_prompts"] = {
        "ok": specs_ok,
        "spec_count": len(specs),
        "capabilities": sorted({r.capability for r in specs}),
    }
    if not specs_ok:
        result["blocking_failed"].append("asset_prompts")

    # --- Slice 9: PackageAssembler (offline) ---
    assembler = PackageAssembler()
    receipt = assembler.assemble(
        project_id=f"vp_phase6_{fx_id}",
        revision_id=f"rev_phase6_{fx_id}",
        created_by="phase6-verifier",
        brief=brief,
        concept=concept,
        screenplay=screenplay,
        characters=extracted["characters"],
        locations=extracted["locations"],
        props=extracted["props"],
        style_bible=style,
        dialogue=written["dialogue_lines"],
        asset_prompts=specs,
        source_commit="phase6-golden-fixture",
    )
    package_ok = receipt.valid and len(receipt.content_hash) == 64
    result["checks"]["package_assembly"] = {
        "ok": package_ok,
        "content_hash": receipt.content_hash,
        "schema_version": receipt.package.schema_version,
        "scene_count_in_package": len(receipt.package.screenplay.scenes),
    }
    if not package_ok:
        result["blocking_failed"].append("package_assembly")

    result["all_blocking_passed"] = not result["blocking_failed"]
    return result


async def _safe_fixture_golden(fx: dict) -> dict:
    """Wrap a golden fixture run so a capability failure yields a FAIL entry
    instead of crashing the verifier (clean BLOCKED verdict)."""
    try:
        return await _run_fixture_golden(fx)
    except Exception as exc:  # noqa: BLE001 - verifier must never traceback
        return {
            "fixture_id": fx["fixture_id"],
            "checks": {"capability_error": str(exc)},
            "blocking_failed": ["capability_error"],
            "all_blocking_passed": False,
        }


def build_golden_comparison(fixtures: list[dict]) -> dict:
    """Run golden semantic comparison for every fixture (async, sequential)."""
    async def _run_all():
        results = []
        for fx in fixtures:
            results.append(await _safe_fixture_golden(fx))
        return results

    comparisons = asyncio.run(_run_all())
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "policy": "docs/video_production/preproduction/equivalence_policy.md",
        "fixture_count": len(comparisons),
        "all_blocking_passed": all(c["all_blocking_passed"] for c in comparisons),
        "fixtures": comparisons,
    }


# ---------------------------------------------------------------------------
# 3. Provider contract receipt
# ---------------------------------------------------------------------------

FORBIDDEN_KERNEL_IMPORTS = (
    "windagent_providers",
    "windagent_tools",
    "windagent_workflows",
    "windagent_storage",
    "windagent_api",
    "windagent_cli",
)


def scan_kernel_provider_deps() -> dict:
    """Assert the kernel only depends on core + pydantic (+ stdlib)."""
    forbidden_hits: list[str] = []
    allowed_roots = ("windagent_core", "windagent_intelligence")
    for py in sorted(KERNEL_DIR.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        text = py.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if stripped.startswith(("import ", "from ")) and "windagent" in stripped:
                module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
                if module and module.group(1) not in allowed_roots:
                    forbidden_hits.append(f"{rel}: {stripped}")
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "kernel_package": "intelligence/windagent_intelligence/video/",
        "forbidden_imports_found": forbidden_hits,
        "allowed_roots": sorted(allowed_roots),
        "verdict": "PASS" if not forbidden_hits else "FAIL",
    }


# ---------------------------------------------------------------------------
# 4. No upstream import report
# ---------------------------------------------------------------------------

UPSTREAM_REFERENCE_PATTERNS = (
    re.compile(r"\bvideoclaw\b", re.IGNORECASE),
    re.compile(r"\bthird_party\b", re.IGNORECASE),
)

# Hard violations regardless of context: importing the quarantined package,
# mutating sys.path, or loading modules by file location / name.
KERNEL_HARD_PATTERNS = (
    re.compile(r"^\s*(?:from\s+videoclaw|import\s+videoclaw)\b", re.MULTILINE),
    re.compile(r"^\s*(?:from\s+third_party|import\s+third_party)\b", re.MULTILINE),
    re.compile(r"sys\.path\.(?:insert|append)\s*\(", re.MULTILINE),
    re.compile(r"spec_from_file_location\s*\(", re.MULTILINE),
    re.compile(r"importlib\.import_module\s*\(", re.MULTILINE),
)

# Contextual violations: generic process/module launching counts only when the
# same file also references the quarantined upstream. Bare subprocess use for
# repo tooling (e.g. ffprobe media QC) is not an upstream launch; the earlier
# blanket ban produced false positives once P25/P26 added ffprobe checks.
KERNEL_LAUNCH_PATTERNS = (
    re.compile(r"subprocess\.(?:run|Popen|call)\s*\(", re.MULTILINE),
)


def scan_kernel_upstream_references() -> dict:
    """Assert the kernel never imports/launches the quarantined upstream."""
    hits: list[str] = []
    files = sorted(KERNEL_DIR.rglob("*.py"))
    for py in files:
        rel = py.relative_to(ROOT).as_posix()
        text = py.read_text(encoding="utf-8", errors="ignore")
        references_upstream = any(
            pattern.search(text) for pattern in UPSTREAM_REFERENCE_PATTERNS
        )
        for pattern in KERNEL_HARD_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:80]}")
        if references_upstream:
            for pattern in KERNEL_LAUNCH_PATTERNS:
                for match in pattern.finditer(text):
                    line_no = text[: match.start()].count("\n") + 1
                    hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:80]}")
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "kernel_package": "intelligence/windagent_intelligence/video/",
        "scanned_files": len(files),
        "upstream_imports_found": hits,
        "sys_path_mutations": [h for h in hits if "sys.path" in h],
        "verdict": "PASS" if not hits else "FAIL",
    }


# ---------------------------------------------------------------------------
# 5. Integration receipt
# ---------------------------------------------------------------------------


async def _run_integration(fx: dict) -> dict:
    """idea → full validated package with the deterministic model port."""
    from windagent_core.domain.video_production.validation import (
        VideoProductionPackageValidator,
    )
    from windagent_intelligence.video import (
        AssetPromptSpecBuilder,
        CreativeBriefExpander,
        DialogueNarrator,
        EntityExtractor,
        PackageAssembler,
        ScreenplayWriter,
        StoryOutliner,
        StyleDesigner,
    )
    from windagent_intelligence.video.ids import StableIdFactory

    fx_id = fx["fixture_id"]
    pinned = _fixture_pinned_responses(fx)
    port = DeterministicModelPort(pinned)
    ids = StableIdFactory(seed=f"phase6-integration-{fx_id}")
    steps: list[dict] = []

    expander = CreativeBriefExpander(port, id_factory=ids)
    expanded = await expander.expand(fx["brief"].get("idea", ""))
    brief = expanded["brief"]
    steps.append({"step": 1, "capability": "CreativeBriefExpander", "ok": True})

    outliner = StoryOutliner(port, id_factory=ids)
    outlined = await outliner.outline(brief)
    concept = outlined["concept"]
    steps.append({"step": 2, "capability": "StoryOutliner", "ok": True})

    writer = ScreenplayWriter(port, id_factory=ids)
    written = await writer.write(concept)
    screenplay = written["screenplay"]
    steps.append({"step": 3, "capability": "ScreenplayWriter", "ok": True})

    narrator = DialogueNarrator(id_factory=ids)
    narrator.narrate(fx["responses"]["generate_script"], screenplay.scenes)
    steps.append({"step": 4, "capability": "DialogueNarrator", "ok": True})

    extractor = EntityExtractor(id_factory=ids)
    extracted = extractor.extract(
        screenplay,
        fx["responses"]["meta_extract"],
        character_id_map=written.get("character_map", {}),
        location_id_map=written.get("location_map", {}),
    )
    steps.append({"step": 5, "capability": "EntityExtractor", "ok": True})

    designer = StyleDesigner(port, id_factory=ids)
    styled = await designer.design(brief, screenplay)
    style = styled["style_bible"]
    steps.append({"step": 6, "capability": "StyleDesigner", "ok": True})

    builder = AssetPromptSpecBuilder()
    specs = builder.build_all(
        characters=extracted["characters"],
        locations=extracted["locations"],
        style=style,
    )
    steps.append({"step": 8, "capability": "AssetPromptSpecBuilder", "ok": True})

    assembler = PackageAssembler()
    receipt = assembler.assemble(
        project_id=f"vp_phase6_integration_{fx_id}",
        revision_id=f"rev_phase6_integration_{fx_id}",
        created_by="phase6-verifier",
        brief=brief,
        concept=concept,
        screenplay=screenplay,
        characters=extracted["characters"],
        locations=extracted["locations"],
        props=extracted["props"],
        style_bible=style,
        dialogue=written["dialogue_lines"],
        asset_prompts=specs,
        source_commit="phase6-integration",
    )
    steps.append({"step": 9, "capability": "PackageAssembler", "ok": receipt.valid})

    # Serialization round-trip + validator
    serialized = receipt.package.serialize()
    reparsed = type(receipt.package).deserialize(serialized)
    validator_issues = VideoProductionPackageValidator.validate(reparsed)
    serialization_ok = not validator_issues
    steps.append({"step": 10, "capability": "Serialization+Validation", "ok": serialization_ok})

    # Determinism: same logical content hashes identically on re-assembly.
    receipt2 = assembler.assemble(
        project_id=f"vp_phase6_integration_{fx_id}",
        revision_id=f"rev_phase6_integration_{fx_id}",
        created_by="phase6-verifier",
        brief=brief,
        concept=concept,
        screenplay=screenplay,
        characters=extracted["characters"],
        locations=extracted["locations"],
        props=extracted["props"],
        style_bible=style,
        dialogue=written["dialogue_lines"],
        asset_prompts=specs,
        source_commit="phase6-integration",
    )
    hash_stable = receipt.content_hash == receipt2.content_hash
    steps.append({"step": 11, "capability": "ContentHashDeterminism", "ok": hash_stable})

    all_ok = all(s["ok"] for s in steps)
    return {
        "fixture_id": fx_id,
        "all_ok": all_ok,
        "steps": steps,
        "content_hash": receipt.content_hash,
        "package_valid": receipt.valid,
    }


async def _safe_integration(fx: dict) -> dict:
    """Wrap an integration run so a failure is recorded, not a crash."""
    try:
        return await _run_integration(fx)
    except Exception as exc:  # noqa: BLE001
        return {
            "fixture_id": fx["fixture_id"],
            "all_ok": False,
            "steps": [{"step": 0, "capability": "capability_error", "ok": False}],
            "error": str(exc),
        }


def build_integration_receipt(fixtures: list[dict]) -> dict:
    async def _run_all():
        results = []
        for fx in fixtures:
            results.append(await _safe_integration(fx))
        return results

    runs = asyncio.run(_run_all())
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "idea_to_package_e2e": all(r["all_ok"] for r in runs),
        "fixtures": runs,
    }


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


def main(no_write: bool = False) -> int:
    if not no_write:
        PHASE_DIR.mkdir(parents=True, exist_ok=True)

    fixtures = _load_fixtures()

    capability_matrix = build_capability_matrix()
    golden_comparison = build_golden_comparison(fixtures)
    provider_receipt = scan_kernel_provider_deps()
    upstream_report = scan_kernel_upstream_references()
    integration_receipt = build_integration_receipt(fixtures)

    gate_reasons: list[str] = []
    if not capability_matrix["all_present"]:
        gate_reasons.append("kernel capability matrix incomplete")
    if not golden_comparison["all_blocking_passed"]:
        gate_reasons.append("golden semantic comparison failed blocking fields")
    if provider_receipt["verdict"] != "PASS":
        gate_reasons.append("provider neutrality violated")
    if upstream_report["verdict"] != "PASS":
        gate_reasons.append("kernel imports/launches upstream")
    if not integration_receipt["idea_to_package_e2e"]:
        gate_reasons.append("idea->package integration failed")

    overall_status = "PASSED" if not gate_reasons else "BLOCKED"

    phase_verdict = {
        "schema_version": "1.1.0",
        "phase": 6,
        "status": overall_status,
        "gate": "VP6_PREPRODUCTION_KERNEL_CANONICAL",
        "evidence": [
            {"path": "capability_matrix.json"},
            {"path": "golden_comparison.json"},
            {"path": "provider_contract_receipt.json"},
            {"path": "no_upstream_import_report.json"},
            {"path": "integration_test_receipt.json"},
        ],
        "blocking_reasons": gate_reasons,
        "derived_from": "scripts/verification/verify_phase6_kernel.py",
    }

    if not no_write:
        write_json(PHASE_DIR / "capability_matrix.json", capability_matrix)
        write_json(PHASE_DIR / "golden_comparison.json", golden_comparison)
        write_json(PHASE_DIR / "provider_contract_receipt.json", provider_receipt)
        write_json(PHASE_DIR / "no_upstream_import_report.json", upstream_report)
        write_json(PHASE_DIR / "integration_test_receipt.json", integration_receipt)
        write_json(PHASE_DIR / "phase_verdict.json", phase_verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(
                overall_status,
                capability_matrix,
                golden_comparison,
                provider_receipt,
                upstream_report,
                integration_receipt,
            ),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_06 artifacts untouched (--no-write keeps the tree clean).")

    print(f"Phase 6 verdict: {overall_status}")
    print(f"  capability matrix: {'complete' if capability_matrix['all_present'] else 'INCOMPLETE'}")
    print(f"  golden comparison: {'PASS' if golden_comparison['all_blocking_passed'] else 'FAIL'}")
    print(f"  provider neutrality: {provider_receipt['verdict']}")
    print(f"  no upstream import: {upstream_report['verdict']}")
    print(f"  idea->package e2e: {'PASS' if integration_receipt['idea_to_package_e2e'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(
    status: str,
    capability_matrix: dict,
    golden_comparison: dict,
    provider_receipt: dict,
    upstream_report: dict,
    integration_receipt: dict,
) -> str:
    return f"""# Phase 6 Report — Pre-production Kernel Canonical

- **Gate:** `VP6_PREPRODUCTION_KERNEL_CANONICAL`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Capability matrix

- Slices: {capability_matrix.get('slice_count')}; all present: {capability_matrix.get('all_present')}

## Golden comparison (equivalence_policy.md)

- Fixtures: {golden_comparison.get('fixture_count')}
- All blocking fields passed: {golden_comparison.get('all_blocking_passed')}

## Provider neutrality

- Kernel: `intelligence/windagent_intelligence/video/`
- Forbidden imports: {len(provider_receipt.get('forbidden_imports_found', []))}
- Verdict: {provider_receipt.get('verdict')}

## Upstream retirement

- Scanned files: {upstream_report.get('scanned_files')}
- Upstream imports / sys.path mutations: {len(upstream_report.get('upstream_imports_found', []))}
- Verdict: {upstream_report.get('verdict')}

## Integration

- idea → package e2e: {integration_receipt.get('idea_to_package_e2e')}
- Per-fixture runs: {integration_receipt.get('fixtures')}

## Evidence

- `capability_matrix.json`
- `golden_comparison.json`
- `provider_contract_receipt.json`
- `no_upstream_import_report.json`
- `integration_test_receipt.json`
- `phase_verdict.json`
"""


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
