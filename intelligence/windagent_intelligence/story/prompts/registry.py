"""
Story prompt catalog (B2, frozen location: B0 registry freeze).

The registry is the ONLY source of prompt definitions for canonical Story
stages. Every entry declares a stable prompt ID ``story.<capability>.<name>``,
a semantic version, a content hash (SHA-256 over capability+version+template,
reusing ``PromptSpec.content_hash`` semantics), an input schema, an output
schema, and safety constraints.

Frozen rules (b0_registry_and_schema_freeze.md §3):
- Prompts are immutable once versioned; re-registering the same ID+version
  with different content is a registry violation (snapshot test).
- ``content_hash`` = SHA-256 over capability + version + template.
- Legacy video-pipeline prompts are extracted INCREMENTALLY as ``legacy=True``
  entries whose template/hash MUST match the live ``PromptSpec`` they were
  extracted from (equivalence tests); they are replaced stage by stage
  (B3+) and retired with the legacy stages.
- Registry entries never carry secrets or private reasoning.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_intelligence.video.continuation.service import CONTINUATION_PROMPT_V1
from windagent_intelligence.video.ideation.brief_expander import BRIEF_EXPANSION_PROMPT_V1
from windagent_intelligence.video.ideation.outliner import OUTLINE_PROMPT_V1
from windagent_intelligence.video.prompts import PromptSpec
from windagent_intelligence.video.screenplay.writer import SCREENPLAY_PROMPT_V1

from windagent_intelligence.story.prompts.schemas import (
    BIBLE_GENERATION_OUTPUT_SCHEMA,
    BEATS_GENERATION_OUTPUT_SCHEMA,
    BRIEF_EXPANSION_OUTPUT_SCHEMA,
    CONTINUATION_TEXT_SPEC,
    IDEA_GENERATION_OUTPUT_SCHEMA,
    OUTLINE_GENERATION_OUTPUT_SCHEMA,
    OUTLINE_OUTPUT_SCHEMA,
    REVIEW_OUTPUT_SCHEMA,
    REVISION_OUTPUT_SCHEMA,
    SCREENPLAY_GENERATION_OUTPUT_SCHEMA,
    SCREENPLAY_TEXT_SPEC,
)

PROMPT_SCHEMA_VERSION = "studio.prompt/v1alpha1"

#: Prompt IDs are ``story.<capability>.<name>`` (B0 freeze).
_PROMPT_ID_RE = re.compile(r"^story\.[a-z0-9_]+(\.[a-z0-9_]+)*$")

#: Structured (schema-validated JSON) vs text-format (legacy) outputs.
OUTPUT_FORMAT_JSON = "json"
OUTPUT_FORMAT_TEXT = "text"

_DEFAULT_SAFETY_MAX_CHARS = 32_000


@dataclass(frozen=True)
class SafetyConstraints:
    """Declared output safety bounds for one prompt (frozen)."""

    max_output_chars: int = _DEFAULT_SAFETY_MAX_CHARS
    #: Case-insensitive regex patterns that make output fail closed.
    prohibited_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class StoryPromptEntry:
    """One immutable catalog entry: id/version/hash + schemas + safety."""

    prompt_id: str  # story.<capability>.<name>
    capability: str
    version: str  # semantic version, e.g. "1.0.0"
    template: str  # rendered into the user message ({placeholder} slots)
    output_schema: Dict[str, Any]
    input_schema: Optional[Dict[str, Any]] = None
    output_format: str = OUTPUT_FORMAT_JSON
    system: str = ""
    safety: SafetyConstraints = field(default_factory=SafetyConstraints)
    legacy: bool = False
    description: str = ""
    max_tokens: int = 2048
    temperature: float = 0.7
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _PROMPT_ID_RE.match(self.prompt_id):
            raise ValueError(
                f"prompt_id {self.prompt_id!r} must match 'story.<capability>.<name>'"
            )
        if self.output_format not in (OUTPUT_FORMAT_JSON, OUTPUT_FORMAT_TEXT):
            raise ValueError(f"unsupported output_format {self.output_format!r}")
        if self.output_format == OUTPUT_FORMAT_JSON and not self.output_schema:
            raise ValueError(f"prompt {self.prompt_id} must declare an output schema")
        if self.safety.max_output_chars <= 0:
            raise ValueError("safety.max_output_chars must be positive")

    @property
    def content_hash(self) -> str:
        """SHA-256 over capability+version+template (PromptSpec semantics)."""
        payload = f"{self.capability}::{self.version}::{self.template}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_prompt_spec(self) -> PromptSpec:
        """Compatibility projection onto the legacy PromptSpec primitive."""
        return PromptSpec(
            capability=self.capability,
            version=self.version,
            template=self.template,
            description=self.description,
            metadata={"prompt_id": self.prompt_id, **self.metadata},
        )

    def render(self, **kwargs: Any) -> str:
        """Render the template (missing keys left intact, PromptSpec semantics)."""
        return self.to_prompt_spec().render(**kwargs)

    def to_manifest_entry(self) -> Dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "capability": self.capability,
            "version": self.version,
            "content_hash": self.content_hash,
            "output_format": self.output_format,
            "legacy": self.legacy,
            "description": self.description,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": self.system,
            "safety": {
                "max_output_chars": self.safety.max_output_chars,
                "prohibited_patterns": list(self.safety.prohibited_patterns),
            },
            "input_schema_ref": None,
            "output_schema_ref": f"schemas/{self._schema_file_name()}",
        }

    def _schema_file_name(self) -> str:
        if self.output_format == OUTPUT_FORMAT_TEXT:
            name = self.output_schema.get("format", self.prompt_id.rsplit(".", 1)[-1])
        else:
            name = self.output_schema.get("title", self.prompt_id.rsplit(".", 1)[-1])
        return f"{name}.json"


#: Frozen catalog. Register via ``register_prompt``; never mutate in place.
STORY_PROMPT_REGISTRY: Dict[str, StoryPromptEntry] = {}


def register_prompt(entry: StoryPromptEntry) -> None:
    """Register one prompt; fail closed on ID+version content drift.

    Re-registering the same prompt_id with the same version but a different
    content hash (or different metadata) is a registry violation (immutable
    prompts, snapshot test). A new semantic version of the same prompt_id is
    a new entry; re-registering the identical entry is idempotent.
    """
    existing = STORY_PROMPT_REGISTRY.get(entry.prompt_id)
    if existing is not None:
        if existing == entry:
            return  # idempotent re-register
        if existing.version == entry.version:
            raise ValueError(
                f"prompt {entry.prompt_id!r} v{entry.version} already registered "
                f"with different content/metadata; bump the version for changes"
            )
        # new semantic version of the same prompt ID
        STORY_PROMPT_REGISTRY[entry.prompt_id] = entry
        return
    STORY_PROMPT_REGISTRY[entry.prompt_id] = entry


def prompt_for(prompt_id: str) -> StoryPromptEntry:
    """Look up a prompt; fail closed on unknown IDs (never silently default)."""
    try:
        return STORY_PROMPT_REGISTRY[prompt_id]
    except KeyError as exc:
        raise KeyError(f"no prompt registered for {prompt_id!r}") from exc


def registered_prompt_ids() -> List[str]:
    return sorted(STORY_PROMPT_REGISTRY)


def prompt_manifest() -> Dict[str, Any]:
    """Deterministic catalog manifest (sorted entries)."""
    return {
        "prompt_schema_version": PROMPT_SCHEMA_VERSION,
        "entries": {
            prompt_id: STORY_PROMPT_REGISTRY[prompt_id].to_manifest_entry()
            for prompt_id in registered_prompt_ids()
        },
    }


def validate_registry_invariants() -> List[str]:
    """Return catalog violations (empty = catalog is contract-clean)."""
    violations: List[str] = []
    for prompt_id, entry in STORY_PROMPT_REGISTRY.items():
        if entry.prompt_id != prompt_id:
            violations.append(f"{prompt_id}: dict key != entry.prompt_id")
        if not _PROMPT_ID_RE.match(entry.prompt_id):
            violations.append(f"{prompt_id}: malformed prompt ID")
        if not entry.version:
            violations.append(f"{prompt_id}: empty version")
        if not entry.template.strip():
            violations.append(f"{prompt_id}: empty template")
        if entry.output_format == OUTPUT_FORMAT_JSON and not entry.output_schema:
            violations.append(f"{prompt_id}: JSON output without output schema")
        if entry.safety.max_output_chars <= 0:
            violations.append(f"{prompt_id}: non-positive max_output_chars")
    return violations


# ---------------------------------------------------------------------------
# Incremental extraction of the legacy video-pipeline prompts (B2 step 1).
# Templates/hashes MUST equal the live PromptSpec constants (equivalence
# tests in test_story_b2_prompt_catalog.py).
# ---------------------------------------------------------------------------

def _legacy_entry(
    prompt_id: str,
    spec: PromptSpec,
    *,
    output_schema: Dict[str, Any],
    output_format: str,
    system: str,
    max_tokens: int,
    max_output_chars: int,
    description: str,
) -> StoryPromptEntry:
    return StoryPromptEntry(
        prompt_id=prompt_id,
        capability=spec.capability,
        version=spec.version,
        template=spec.template,
        output_schema=output_schema,
        output_format=output_format,
        system=system,
        safety=SafetyConstraints(max_output_chars=max_output_chars),
        legacy=True,
        description=description,
        max_tokens=max_tokens,
        temperature=0.7,
    )


register_prompt(
    _legacy_entry(
        "story.brief_expansion.expand",
        BRIEF_EXPANSION_PROMPT_V1,
        output_schema=BRIEF_EXPANSION_OUTPUT_SCHEMA,
        output_format=OUTPUT_FORMAT_JSON,
        system="You are the WindAgent creative brief expander.",
        max_tokens=1200,
        max_output_chars=8_000,
        description="Expand a raw idea into a creative brief JSON (legacy brief_expansion).",
    )
)
register_prompt(
    _legacy_entry(
        "story.outline.generate",
        OUTLINE_PROMPT_V1,
        output_schema=OUTLINE_OUTPUT_SCHEMA,
        output_format=OUTPUT_FORMAT_JSON,
        system="You are the WindAgent story outliner.",
        max_tokens=1500,
        max_output_chars=8_000,
        description="Turn a creative brief into a story outline JSON (legacy story_outline).",
    )
)
register_prompt(
    _legacy_entry(
        "story.screenplay.write",
        SCREENPLAY_PROMPT_V1,
        output_schema=SCREENPLAY_TEXT_SPEC,
        output_format=OUTPUT_FORMAT_TEXT,
        system="You are the WindAgent screenwriter.",
        max_tokens=4000,
        max_output_chars=30_000,
        description="Generate canonical screenplay TEXT (legacy; structured JSON at B6).",
    )
)
register_prompt(
    _legacy_entry(
        "story.continuation.continue",
        CONTINUATION_PROMPT_V1,
        output_schema=CONTINUATION_TEXT_SPEC,
        output_format=OUTPUT_FORMAT_TEXT,
        system="You are the WindAgent screenwriter (continuation).",
        max_tokens=3000,
        max_output_chars=20_000,
        description="Continue a screenplay in canonical text format (legacy; B6/B7).",
    )
)

# ---------------------------------------------------------------------------
# B3 canonical prompt: ideation (non-legacy, schema-first)
# ---------------------------------------------------------------------------

_IDEATION_TEMPLATE = """Create {target_count} DISTINCT, age-appropriate story idea candidates for one episode.

Creative brief:
- Title: {title}
- Genre: {genre}
- Logline: {logline}
- Tone: {tone}
- Audience: {audience} (ages {audience_min_age}-{audience_max_age})
- Language: {language}
- Theme: {theme}
- Target duration: {target_duration_seconds} seconds
- Constraints: {constraints}
- Prohibited content (NEVER include, even implicitly): {prohibited_content}

Rules:
1. Return EXACTLY {target_count} candidates (between 3 and 5), each with a unique candidate_id ("c1", "c2", ...).
2. Every candidate must be safe and age-appropriate for ages {audience_min_age}-{audience_max_age}.
3. Every candidate must fit roughly {target_duration_seconds} seconds of animation.
4. Respond in {language} for title/summary/premise/logline.
5. age_fit is a 0.0-1.0 estimate of fit for the audience band (use 0.7-1.0).
6. estimated_seconds should be near {target_duration_seconds}; scene_count/character_count/location_count are production-feasibility estimates (positive integers).
7. safety_ok must be true; if a candidate cannot be made safe, do not include it.
8. Candidates must be distinct from each other in premise and title.

Exact output shape (fill this structure; every key is REQUIRED for EVERY candidate; never omit, rename, or add keys; spell key names exactly — especially "candidate_id", "safety_ok"):
{{"language": "{language}", "candidates": [{{"candidate_id": "c1", "title": "...", "summary": "...", "premise": "...", "logline": "...", "themes": ["..."], "age_fit": 0.9, "estimated_seconds": {target_duration_seconds}, "scene_count": 5, "character_count": 2, "location_count": 2, "safety_ok": true}}]}}
Repeat the candidate object EXACTLY {target_count} times inside the "candidates" array, once per idea, with "c1", "c2", ... as candidate_id. Output ONLY the raw JSON object — no markdown code fences, no commentary, no trailing text."""

_IDEATION_SYSTEM = (
    "You are the WindAgent story ideation engine. You produce exactly 3-5 "
    "distinct, safe, age-appropriate idea candidates as structured JSON only."
)

register_prompt(
    StoryPromptEntry(
        prompt_id="story.ideation.generate",
        capability="ideation",
        version="1.1.0",
        template=_IDEATION_TEMPLATE,
        output_schema=IDEA_GENERATION_OUTPUT_SCHEMA,
        system=_IDEATION_SYSTEM,
        safety=SafetyConstraints(max_output_chars=24_000),
        legacy=False,
        description=(
            "B3: generate 3-5 distinct, age-appropriate idea candidates for "
            "a normalized CreativeBrief (structured JSON, schema-first)."
        ),
        max_tokens=6000,
        temperature=0.8,
    )
)

# ---------------------------------------------------------------------------
# B4 canonical prompt: bibles/canon (non-legacy, schema-first)
# ---------------------------------------------------------------------------

_BIBLES_TEMPLATE = """Expand the selected idea into THREE internally consistent canon artifacts for one episode.

Selected idea:
- Title: {title}
- Summary: {summary}
- Language: {language}
- Audience: ages {audience_min_age}-{audience_max_age}

Rules:
1. StoryBible: bible_id (bible_* prefix), title, premise, theme, tone, arc_summary as ONE STRING (beginning -> middle -> end), stakes, and at most 20 story_rules as an array of plain STRINGS.
2. WorldBible: world_id (world_* prefix), setting, 1-6 recurring_locations each with location_id (loc_* prefix) and name; physical_rules and story_rules are arrays of objects with rule_id (rule_* prefix), statement (the rule text), kind (physics|social|magic|constraint).
3. CharacterCanon: canon_id (canon_* prefix) + at least one character; every character has a unique character_id (ch_* prefix) and name; role exactly one of: protagonist, deuteragonist, supporting, antagonist (never "mentor", never Vietnamese). EVERY character MUST have "relationships": [] — do not create a single relationship object, empty arrays only; relationship objects are not allowed in this output.
4. Character age_band must match the audience band (e.g. {audience_min_age}-{audience_max_age}).
5. Respond in {language}; all prose must be age-appropriate and safe for ages {audience_min_age}-{audience_max_age}. Prohibited content never appears, even implicitly.

Exact output shape (fill this structure; every key is REQUIRED; never omit, rename, or add keys — spell key names exactly, especially "bible_id", "world_id", "statement", "location_id"):
{{"story_bible": {{"bible_id": "bible_001", "title": "...", "premise": "...", "theme": "...", "tone": "...", "arc_summary": "beginning ... middle ... end (ONE string)", "stakes": "...", "story_rules": ["rule one as plain string", "rule two as plain string"], "language": "{language}"}}, "world_bible": {{"world_id": "world_001", "setting": "...", "physical_rules": [{{"rule_id": "rule_p1", "statement": "...", "kind": "physics"}}], "story_rules": [{{"rule_id": "rule_s1", "statement": "...", "kind": "social"}}], "recurring_locations": [{{"location_id": "loc_001", "name": "..."}}], "recurring_objects": [{{"prop_id": "prop_001", "name": "..."}}], "style_constraints": {{}}, "language": "{language}"}}, "character_canon": {{"canon_id": "canon_001", "language": "{language}", "characters": [{{"character_id": "ch_001", "name": "...", "role": "protagonist", "goal": "...", "traits": ["..."], "relationships": [], "age_band": "{audience_min_age}-{audience_max_age}"}}]}}}}
Output ONLY the raw JSON object — no markdown code fences, no commentary, no trailing text."""

_BIBLES_SYSTEM = (
    "You are the WindAgent story canon engine. You produce StoryBible, "
    "WorldBible, and CharacterCanon as ONE consistent structured JSON set; "
    "all cross-references use stable canon IDs."
)

register_prompt(
    StoryPromptEntry(
        prompt_id="story.bibles.generate",
        capability="bibles",
        version="1.8.0",
        template=_BIBLES_TEMPLATE,
        output_schema=BIBLE_GENERATION_OUTPUT_SCHEMA,
        system=_BIBLES_SYSTEM,
        safety=SafetyConstraints(max_output_chars=32_000),
        legacy=False,
        description=(
            "B4: expand a SelectedIdea into StoryBible + WorldBible + "
            "CharacterCanon as one cross-validated set (structured JSON, "
            "schema-first)."
        ),
        max_tokens=8000,
        temperature=0.4,
    )
)

# ---------------------------------------------------------------------------
# B5 canonical prompts: beats + outline (non-legacy, schema-first)
# ---------------------------------------------------------------------------

_BEATS_TEMPLATE = """Turn the canon into an ordered beat sheet that fits the episode duration budget.

Canon:
- Title: {title}
- Premise: {premise}
- Arc: {arc_summary}
- Characters: {characters}
- Locations: {locations}
- Language: {language}
- Audience: ages {audience_min_age}-{audience_max_age}
- Target duration: {target_duration_seconds} seconds (tolerance {tolerance_seconds})

Rules:
1. Return between {min_beats} and {max_beats} beats, ordered 1..N with unique beat_id.
2. role from hook|setup|rising|climax|falling|resolution; emotional_beat progresses across beats.
3. character_ids reference canon character IDs ONLY; location_id references a canon location ID.
4. target_seconds sum must be within {tolerance_seconds}s of {target_duration_seconds}.
5. Respond in {language}; content must be age-appropriate and safe for ages {audience_min_age}-{audience_max_age}.

Exact output shape (fill this structure; every key is REQUIRED; never omit, rename, or add keys; spell key names exactly — especially "beat_id", "total_target_seconds"):
{{"beat_sheet_id": "bs_001", "title": "...", "total_target_seconds": {target_duration_seconds}, "beats": [{{"beat_id": "bt_001", "order": 1, "role": "hook", "description": "one short non-empty description", "emotional_beat": "...", "character_ids": ["ch_001"], "location_id": "loc_001", "target_seconds": 30}}]}}
Return exactly as many beats as needed to fill the budget; every beat must include "order". Output ONLY the raw JSON object — no markdown code fences, no commentary, no trailing text."""

_BEATS_SYSTEM = (
    "You are the WindAgent story structure engine. You produce an ordered "
    "BeatSheet as structured JSON only; every reference uses stable canon IDs."
)

register_prompt(
    StoryPromptEntry(
        prompt_id="story.beats.generate",
        capability="beats",
        version="1.1.0",
        template=_BEATS_TEMPLATE,
        output_schema=BEATS_GENERATION_OUTPUT_SCHEMA,
        system=_BEATS_SYSTEM,
        safety=SafetyConstraints(max_output_chars=32_000),
        legacy=False,
        description=(
            "B5: allocate the 180-300 s budget across an ordered BeatSheet "
            "referencing canon IDs (structured JSON, schema-first)."
        ),
        max_tokens=8000,
        temperature=0.7,
    )
)

_OUTLINE_TEMPLATE = """Plan the episode scenes from the beat sheet.

Beat sheet structural ledger (valid JSON; copy structural fields exactly):
{beats_summary}

Allowed character IDs (copy exactly): {characters}
Allowed location IDs (copy exactly): {locations}

Language: {language}
Audience: {audience_band}
Target duration: {target_duration_seconds} seconds (tolerance {tolerance_seconds})

Rules:
1. Return one scene per beat (there will be between {min_scenes} and {max_scenes}), ordered 1..N with unique scene_id.
2. For each beat, copy its beat_id into beat_refs, its location_id into location_id, and its character_ids into character_ids. Never invent or translate an ID.
3. Copy each beat's target_seconds into the corresponding scene's estimated_seconds so the TOTAL stays within {tolerance_seconds}s of {target_duration_seconds} and inside 180-300 seconds.
4. Scene order must follow the beat causal order.
5. dialogue_budget_seconds must not exceed estimated_seconds.
6. Respond in {language}; content must be age-appropriate and safe for ages {audience_band}.

Exact output shape (fill this structure; every key is REQUIRED; never omit, rename, or add keys; spell key names exactly — especially "scene_id", "beat_refs"):
{{"outline_id": "ol_001", "title": "...", "target_duration_seconds": {target_duration_seconds}, "scenes": [{{"scene_id": "sc_001", "order": 1, "intent": "one short non-empty intent", "location_id": "loc_001", "character_ids": ["ch_001"], "conflict_change": "...", "visual_action": "...", "dialogue_budget_seconds": 10, "estimated_seconds": 30, "beat_refs": ["bt_001"]}}]}}
Copy the per-beat numbers (order, target_seconds -> estimated_seconds, location_id, character_ids, beat_refs) VERBATIM from the beat ledger above — they are already correct. Return exactly as many scenes as there are beats. Every scene must include "order". Output ONLY the raw JSON object — no markdown code fences, no commentary, no trailing text."""

_OUTLINE_SYSTEM = (
    "You are the WindAgent episode planner. You produce an EpisodeOutline as "
    "structured JSON only; every scene traces to beats and canon IDs."
)

register_prompt(
    StoryPromptEntry(
        prompt_id="story.outline.structured",
        capability="outline",
        version="1.1.0",
        template=_OUTLINE_TEMPLATE,
        output_schema=OUTLINE_GENERATION_OUTPUT_SCHEMA,
        system=_OUTLINE_SYSTEM,
        safety=SafetyConstraints(max_output_chars=32_000),
        legacy=False,
        description=(
            "B5: structured EpisodeOutline from a BeatSheet (canonical; the "
            "legacy story.outline.generate prompt stays for the old "
            "pipeline)."
        ),
        max_tokens=8000,
        temperature=0.7,
    )
)

# ---------------------------------------------------------------------------
# B6 canonical prompt: structured screenplay (non-legacy, schema-first)
# ---------------------------------------------------------------------------

_SCREENPLAY_TEMPLATE = """Write the episode screenplay as structured JSON scenes.

Episode outline structural ledger (valid JSON; copy structural fields exactly):
{outline_summary}

Beat sheet:
{beats_summary}

Characters: {characters}
Locations: {locations}
Language: {language}
Audience: {audience_band}
Target duration: {target_duration_seconds} seconds (tolerance {tolerance_seconds})

Rules:
1. Return exactly one draft scene per outline scene (the count will be between {min_scenes} and {max_scenes}), ordered 1..N with unique scene_id.
2. For every outline scene, copy outline scene_id into outline_scene_id, location_id into location_id, character_ids into character_ids, beat_refs into source_beat_ids, and estimated_seconds into estimated_seconds. Never invent or translate a referenced ID.
3. scene_id is a NEW draft scene id (dscn_*); keep outline_scene_id separate.
4. Keep output concise: give every scene one short non-empty action_description. dialogue may be [] and narration may be an empty string. When dialogue is present, every line carries a unique dialogue_id, scene_id = the draft scene's own scene_id, character_id from that scene's cast ONLY, order starting at 1, and non-empty text.
5. transition must be one of CUT TO:|DISSOLVE TO:|FADE IN:|FADE OUT:|MATCH CUT:.
6. Copy target_duration_seconds and tolerance_seconds exactly as given; copied per-scene timing must keep the TOTAL within {tolerance_seconds}s of {target_duration_seconds} and inside 180-300 seconds.
7. Scene order follows the outline causal order; every scene must have action or dialogue or narration.
8. Respond in {language}; content must be age-appropriate and safe for ages {audience_band}.

Exact output shape (fill this structure; every key is REQUIRED; never omit, rename, or add keys; spell key names exactly — especially "dialogue_id"):
{{"draft_id": "dscn_<invent a fresh id, never reuse example ids>", "title": "...", "target_duration_seconds": {target_duration_seconds}, "scenes": [{{"scene_id": "dscn_001", "order": 1, "outline_scene_id": "sc_001", "location_id": "lc_01", "character_ids": ["char_001"], "action_description": "one short non-empty action sentence", "dialogue": [{{"dialogue_id": "dlg_001", "scene_id": "dscn_001", "character_id": "char_001", "order": 1, "text": "one non-empty line"}}], "narration": "", "transition": "CUT TO:", "estimated_seconds": 25, "source_beat_ids": ["bt_001"]}}]}}
Copy the per-scene numbers (order, estimated_seconds, location_id, character_ids, source_beat_ids) VERBATIM from the outline ledger above — they are already correct. Return exactly as many scenes as the outline ledger has. Every scene and every dialogue line must include "order". Output ONLY the raw JSON object — no markdown code fences, no commentary, no trailing text."""  # noqa: E501

_SCREENPLAY_SYSTEM = (
    "You are the WindAgent structured screenwriter. You produce the episode "
    "ScreenplayDraft as structured JSON only (action, dialogue, narration, "
    "timing, source refs); canonical text is rendered downstream, never "
    "written by the model. Reply with the raw JSON object only: no markdown "
    "code fences, no commentary, no trailing text."
)

register_prompt(
    StoryPromptEntry(
        prompt_id="story.screenplay.structured",
        capability="screenplay",
        version="1.0.3",
        template=_SCREENPLAY_TEMPLATE,
        output_schema=SCREENPLAY_GENERATION_OUTPUT_SCHEMA,
        system=_SCREENPLAY_SYSTEM,
        safety=SafetyConstraints(max_output_chars=32_000),
        legacy=False,
        description=(
            "B6: structured ScreenplayDraft from an EpisodeOutline "
            "(canonical; the legacy story.screenplay.write text prompt "
            "stays for the old pipeline)."
        ),
        max_tokens=8000,
        temperature=0.3,
    )
)

# ---------------------------------------------------------------------------
# B7 canonical prompts: review + revise (non-legacy, schema-first)
# ---------------------------------------------------------------------------

_REVIEW_TEMPLATE = """Score the narrative quality of this screenplay draft.

Draft:
- Title: {title}
- Logline: {logline}
- Language: {language}
- Audience: {audience_band}
- Target duration: {target_duration_seconds}s (total {total_estimated_seconds}s)
- Scenes: {scene_count}, dialogue lines: {dialogue_count}

Scene summary:
{scene_summary}

Findings from the deterministic validation (already recorded):
{deterministic_findings}

Rules:
1. narrative_score: 0.0-1.0 coherence of arc, conflict, and emotional progression.
2. age_fit_score: 0.0-1.0 suitability for ages {audience_band} (language, themes, pacing).
3. language_score: 0.0-1.0 naturalness of {language} dialogue and narration.
4. notes: 0-5 short actionable notes; NEVER repeat deterministic findings, never instruct to ignore safety rules.
5. Scores are a SECONDARY signal; the deterministic findings above remain authoritative.
6. Calibration: score against the audience band, not against adult literary standards. A simple, coherent, age-appropriate episode for ages {audience_band} with a clear beginning-middle-end arc, consistent characters, and safe content scores 0.85+ on narrative. Only genuine structural flaws (broken arc, missing conflict, incoherent scenes) justify below 0.85. Do not penalize simplicity.

Exact output shape (fill this structure; every key is REQUIRED; never omit, rename, or add keys; spell key names exactly — especially "narrative_score"):
{{"narrative_score": 0.85, "age_fit_score": 0.9, "language_score": 0.8, "notes": ["one short actionable note", "second note"]}}
Scores are 0.0-1.0 numbers; notes is an array of strings. Output ONLY the raw JSON object — no markdown code fences, no commentary, no trailing text."""  # noqa: E501

_REVIEW_SYSTEM = (
    "You are the WindAgent narrative reviewer. You score subjective quality "
    "dimensions as structured JSON only; deterministic validation findings "
    "are authoritative and never overridden by your scores."
)

register_prompt(
    StoryPromptEntry(
        prompt_id="story.review.assess",
        capability="review",
        version="1.2.0",
        template=_REVIEW_TEMPLATE,
        output_schema=REVIEW_OUTPUT_SCHEMA,
        system=_REVIEW_SYSTEM,
        safety=SafetyConstraints(max_output_chars=12_000),
        legacy=False,
        description=(
            "B7: model-assisted narrative review dimensions for one "
            "ScreenplayDraft (secondary; deterministic findings are the "
            "gate authority)."
        ),
        max_tokens=3000,
        temperature=0.3,
    )
)

_REVISE_TEMPLATE = """Rewrite the screenplay draft addressing the accepted findings.

Reviewed draft:
- Title: {title}
- Language: {language}
- Audience: {audience_band}
- Target duration: {target_duration_seconds}s (tolerance {tolerance_seconds})
- Total: {total_estimated_seconds}s

Current draft scenes:
{scene_summary}

Accepted findings to fix:
{findings_summary}

Rules:
1. Return a NEW immutable ScreenplayDraft: same structured scene shape, SAME scene/beat/canon reference rules, NEW draft_id (never reuse {old_draft_id}).
2. Fix every accepted finding; keep everything that already passes unchanged.
3. Keep 180-300s total, within {tolerance_seconds}s of {target_duration_seconds}.
4. Do not weaken age-appropriateness or safety; respond in {language}.

Exact output shape (fill this structure; every key is REQUIRED; never omit, rename, or add keys; spell key names exactly — especially "draft_id", "dialogue_id"):
{{"draft_id": "dscn_<invent a FRESH id, never reuse {old_draft_id} or example ids>", "title": "...", "target_duration_seconds": {target_duration_seconds}, "scenes": [{{"scene_id": "dscn_001", "order": 1, "outline_scene_id": "sc_001", "location_id": "lc_01", "character_ids": ["char_001"], "action_description": "one short non-empty action sentence", "dialogue": [{{"dialogue_id": "dlg_001", "scene_id": "dscn_001", "character_id": "char_001", "order": 1, "text": "one non-empty line"}}], "narration": "", "transition": "CUT TO:", "estimated_seconds": 25, "source_beat_ids": ["bt_001"]}}]}}
Copy the per-scene numbers VERBATIM from the draft above — they are already correct. Return exactly as many scenes as the draft has. Every scene and every dialogue line must include "order". Output ONLY the raw JSON object — no markdown code fences, no commentary, no trailing text."""  # noqa: E501

_REVISE_SYSTEM = (
    "You are the WindAgent bounded revision engine. You produce a NEW "
    "immutable ScreenplayDraft as structured JSON only; you never mutate the "
    "reviewed draft."
)

register_prompt(
    StoryPromptEntry(
        prompt_id="story.revise.rewrite",
        capability="revise",
        version="1.1.0",
        template=_REVISE_TEMPLATE,
        output_schema=REVISION_OUTPUT_SCHEMA,
        system=_REVISE_SYSTEM,
        safety=SafetyConstraints(max_output_chars=32_000),
        legacy=False,
        description=(
            "B7: bounded revision — a NEW immutable ScreenplayDraft fixing "
            "the accepted findings of a review report."
        ),
        max_tokens=8000,
        temperature=0.7,
    )
)

__all__ = [
    "PROMPT_SCHEMA_VERSION",
    "OUTPUT_FORMAT_JSON",
    "OUTPUT_FORMAT_TEXT",
    "SafetyConstraints",
    "StoryPromptEntry",
    "STORY_PROMPT_REGISTRY",
    "register_prompt",
    "prompt_for",
    "registered_prompt_ids",
    "prompt_manifest",
    "validate_registry_invariants",
]
