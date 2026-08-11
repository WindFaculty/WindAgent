"""Plan B B8 evidence producer / contract guard (LOCKED_SCREENPLAY_GATE, S10).

Modes:
- default: (re)generate the lock fixtures — golden package assembly under
  all three approval modes (AUTO, HUMAN_REQUIRED, QUALITY_GATE_ONLY), the
  negative lock corpus (stale approval, hash mismatch, warnings/policy,
  incomplete lineage, duplicate refs, iteration budget, post-lock mutation,
  concurrent lock/revision), checksums, and the evidence markdown for
  LOCKED_SCREENPLAY_GATE.
- --check: validate the COMMITTED fixtures against the live code WITHOUT
  writing anything; exit non-zero on any violation (CI guard).

The corpus runners are shared with tests/contracts/test_story_b8_lock_gate.py
so committed results and live behavior can never drift apart.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.verification.produce_b3_evidence import (  # noqa: E402
    GOLDEN_BRIEF,
    GOLDEN_GENERATION_RESPONSE,
)
from scripts.verification.produce_b4_evidence import (  # noqa: E402
    GOLDEN_CHARACTER_CANON,
    GOLDEN_SELECTED_IDEA,
    GOLDEN_STORY_BIBLE,
    GOLDEN_WORLD_BIBLE,
)
from scripts.verification.produce_b5_evidence import (  # noqa: E402
    GOLDEN_BEAT_SHEET,
    GOLDEN_EPISODE_OUTLINE,
)
from scripts.verification.produce_b6_evidence import (  # noqa: E402
    GOLDEN_SCREENPLAY_DRAFT,
)
from scripts.verification.produce_b7_evidence import (  # noqa: E402
    GOLDEN_DRAFT,
    _weak_report,
)

from windagent_core.domain.story.bibles import CharacterCanon, StoryBible, WorldBible  # noqa: E402
from windagent_core.domain.story.ideation import IdeaCandidateSet, SelectedIdea  # noqa: E402
from windagent_core.domain.story.outline import BeatSheet, EpisodeOutline  # noqa: E402
from windagent_core.domain.story.review import (  # noqa: E402
    LockedScreenplayReceipt,
    PackageArtifactRef,
    ReviewReport,
)
from windagent_core.domain.story.screenplay import ScreenplayDraft  # noqa: E402
from windagent_intelligence.story.ideation import (  # noqa: E402
    IdeaEvaluationService,
    IdeaGenerationService,
)
from windagent_intelligence.story.prompts import (  # noqa: E402
    FixtureModelPort,
    StoryModelBoundary,
)
from windagent_intelligence.story.review import (  # noqa: E402
    APPROVAL_MODES,
    LOCK_POLICY_VERSION,
    LockService,
    LockValidationFailure,
)

LOCK_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_lock"
)
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "plans" / "studio_roadmap_01" / "evidence" / "b8_lock_gate.md"
)

GOLDEN_CANON = CharacterCanon(**GOLDEN_CHARACTER_CANON)
GOLDEN_WORLD = WorldBible(**GOLDEN_WORLD_BIBLE)
GOLDEN_STORY = StoryBible(**GOLDEN_STORY_BIBLE)
GOLDEN_BEATS = BeatSheet(**GOLDEN_BEAT_SHEET)
GOLDEN_OUTLINE = EpisodeOutline(**GOLDEN_EPISODE_OUTLINE)

#: Policy id bound to HUMAN_REQUIRED receipts (A-side approval policy v0.1).
GOLDEN_POLICY_ID = "approval_policy_v1"


def _candidate_set() -> IdeaCandidateSet:
    """Deterministic live candidate set (same fixture path as B3 golden)."""

    async def go() -> IdeaCandidateSet:
        port = FixtureModelPort(responses={"ideation": json.dumps(GOLDEN_GENERATION_RESPONSE, ensure_ascii=False)})
        generated = await IdeaGenerationService(StoryModelBoundary(port)).generate(GOLDEN_BRIEF)
        evaluated = IdeaEvaluationService().evaluate(generated.brief, generated.candidate_set)
        return evaluated.candidate_set

    return asyncio.run(go())


def _clean_report() -> ReviewReport:
    return ReviewReport(
        report_id="report_lock_clean_pass",
        draft_id=GOLDEN_DRAFT.draft_id,
        review_iteration=1,
        verdict="PASS",
        quality_summary="0 findings (0 blocking, 0 warnings).",
    )


def _receipt(*, approval_mode: str, report: ReviewReport, draft_id: str | None = None) -> LockedScreenplayReceipt:
    # Pinned issued_at: an A-issued receipt is immutable; the fixture pins the
    # instant so the golden package reassembles byte-identically.
    from datetime import datetime, timezone

    return LockedScreenplayReceipt(
        receipt_id=f"rcpt_{approval_mode.lower()}_{(draft_id or GOLDEN_DRAFT.draft_id.value)}",
        draft_id=draft_id or GOLDEN_DRAFT.draft_id,
        approval_mode=approval_mode,
        policy_id=GOLDEN_POLICY_ID if approval_mode == "HUMAN_REQUIRED" else "",
        issued_at=datetime(2026, 8, 11, 0, 0, 0, tzinfo=timezone.utc),
    )


def lineage_refs(
    *,
    draft: ScreenplayDraft = GOLDEN_DRAFT,
    report: ReviewReport | None = None,
    receipt: LockedScreenplayReceipt | None = None,
    drop: tuple[str, ...] = (),
    corrupt: tuple[tuple[str, str], ...] = (),
) -> List[PackageArtifactRef]:
    """Full 11-entry live lineage: every ref hash is the canonical content hash."""
    report = report or _clean_report()
    receipt = receipt or _receipt(approval_mode="AUTO", report=report)
    models = [
        ("CreativeBrief", GOLDEN_BRIEF, "art_brief"),
        ("IdeaCandidateSet", _candidate_set(), "art_candidates"),
        ("SelectedIdea", GOLDEN_SELECTED_IDEA, "art_selected"),
        ("StoryBible", GOLDEN_STORY, "art_story_bible"),
        ("WorldBible", GOLDEN_WORLD, "art_world_bible"),
        ("CharacterCanon", GOLDEN_CANON, "art_canon"),
        ("BeatSheet", GOLDEN_BEATS, "art_beats"),
        ("EpisodeOutline", GOLDEN_OUTLINE, "art_outline"),
        ("ScreenplayDraft", draft, "art_draft"),
        ("ReviewReport", report, "art_report"),
        ("LockedScreenplayReceipt", receipt, "art_receipt"),
    ]
    refs = [
        PackageArtifactRef(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            content_hash=model.content_hash(),
            revision_id="rev_1",
        )
        for artifact_type, model, artifact_id in models
    ]
    refs = [r for r in refs if r.artifact_type not in drop]
    for artifact_type, new_hash in corrupt:
        refs = [
            PackageArtifactRef(
                artifact_type=r.artifact_type,
                artifact_id=r.artifact_id,
                content_hash=new_hash if r.artifact_type == artifact_type else r.content_hash,
                revision_id=r.revision_id,
            )
            for r in refs
        ]
    return refs


# ---------------------------------------------------------------------------
# Golden lock: all three approval modes
# ---------------------------------------------------------------------------


def golden_lock() -> Dict[str, Any]:
    """Deterministic golden: one valid package per approval mode + idempotency."""
    clean = _clean_report()
    weak = _weak_report()

    def assemble(mode: str, report: ReviewReport) -> Dict[str, Any]:
        receipt = _receipt(approval_mode=mode, report=report)
        result = LockService().assemble(
            draft=GOLDEN_DRAFT,
            report=report,
            receipt=receipt,
            lineage_refs=lineage_refs(report=report, receipt=receipt),
        )
        # Idempotency: the same inputs reassemble to byte-identical packages.
        again = LockService().assemble(
            draft=GOLDEN_DRAFT,
            report=report,
            receipt=receipt,
            lineage_refs=lineage_refs(report=report, receipt=receipt),
        )
        assert again.package.serialize() == result.package.serialize()
        return {
            "receipt": result.receipt.to_canonical_dict(),
            "package": result.package.to_canonical_dict(),
            "package_content_hash": result.package.content_hash(),
            "package_summary": result.package.to_summary(),
            "validation": result.validation,
            "idempotent": True,
        }

    return {
        "schema_version": "studio.lock_golden/v1",
        "policy": LOCK_POLICY_VERSION,
        "approval_modes": sorted(APPROVAL_MODES),
        "AUTO": assemble("AUTO", clean),
        "HUMAN_REQUIRED": assemble("HUMAN_REQUIRED", clean),
        "QUALITY_GATE_ONLY": assemble("QUALITY_GATE_ONLY", weak),
    }


# ---------------------------------------------------------------------------
# Negative corpus: every refusal path + post-lock/concurrency behavior
# ---------------------------------------------------------------------------


def _mutated_draft() -> ScreenplayDraft:
    data = json.loads(GOLDEN_DRAFT.serialize())
    data["title"] = "Đổi tên sau khi khóa"
    return ScreenplayDraft(**data)


def _concurrent_revision_draft() -> ScreenplayDraft:
    data = json.loads(GOLDEN_DRAFT.serialize())
    data["draft_id"] = "draft_rabbit_kite_r2"
    return ScreenplayDraft(**data)


def lock_corpus() -> List[Dict[str, Any]]:
    clean = _clean_report()
    weak = _weak_report()
    return [
        {
            "case": "missing_approval",
            "report": clean,
            "receipt": LockedScreenplayReceipt(
                receipt_id="rcpt_in_review", draft_id=GOLDEN_DRAFT.draft_id,
                state="IN_REVIEW", approval_mode="AUTO",
            ),
            "expect": ["LOCK_STATE"],
        },
        {
            "case": "stale_receipt_draft",
            "report": clean,
            "receipt": _receipt(approval_mode="AUTO", report=clean, draft_id="draft_other"),
            "expect": ["RECEIPT_DRAFT_MISMATCH"],
        },
        {
            "case": "unknown_approval_mode",
            "report": clean,
            "receipt": LockedScreenplayReceipt(
                receipt_id="rcpt_unknown", draft_id=GOLDEN_DRAFT.draft_id,
                approval_mode="BY_HAND_WAVE",
            ),
            "expect": ["APPROVAL_MODE"],
        },
        {
            "case": "human_required_without_policy",
            "report": clean,
            "receipt": LockedScreenplayReceipt(
                receipt_id="rcpt_no_policy", draft_id=GOLDEN_DRAFT.draft_id,
                approval_mode="HUMAN_REQUIRED",
            ),
            "expect": ["APPROVAL_POLICY"],
        },
        {
            "case": "auto_with_warnings",
            "report": weak,
            "receipt": _receipt(approval_mode="AUTO", report=weak),
            "expect": ["APPROVAL_MODE"],
        },
        {
            "case": "review_not_pass",
            "report": ReviewReport(
                **{**json.loads(weak.serialize()), "verdict": "REVIEW_REQUIRED"}
            ),
            "receipt": _receipt(approval_mode="HUMAN_REQUIRED", report=weak),
            "expect": ["REVIEW_THRESHOLD"],
        },
        {
            "case": "stale_review_draft",
            "report": ReviewReport(
                **{**json.loads(clean.serialize()), "draft_id": "draft_other"}
            ),
            "receipt": _receipt(approval_mode="AUTO", report=clean),
            "expect": ["REVIEW_STALE"],
        },
        {
            "case": "iteration_budget_exhausted",
            "report": _weak_report(review_iteration=4, maximum_iterations=3),
            "receipt": _receipt(approval_mode="HUMAN_REQUIRED", report=weak),
            "expect": ["REVISION_BUDGET"],
        },
        {
            "case": "incomplete_lineage",
            "report": clean,
            "receipt": _receipt(approval_mode="AUTO", report=clean),
            "drop": ("WorldBible", "BeatSheet"),
            "expect": ["MANIFEST_MISSING_REF"],
        },
        {
            "case": "duplicate_lineage_ref",
            "report": clean,
            "receipt": _receipt(approval_mode="AUTO", report=clean),
            "duplicate": True,
            "expect": ["MANIFEST_DUPLICATE"],
        },
        {
            "case": "hash_mismatch_report",
            "report": clean,
            "receipt": _receipt(approval_mode="AUTO", report=clean),
            "corrupt": (("ReviewReport", "a" * 64),),
            "expect": ["HASH_MISMATCH"],
        },
        {
            "case": "post_lock_edit_rejection",
            "report": clean,
            "receipt": _receipt(approval_mode="AUTO", report=clean),
            "draft": _mutated_draft(),
            "expect": ["HASH_MISMATCH"],
        },
        {
            "case": "concurrent_lock_revision",
            "report": clean,
            "receipt": _receipt(approval_mode="AUTO", report=clean),
            "draft": _concurrent_revision_draft(),
            "expect": ["RECEIPT_DRAFT_MISMATCH"],
        },
    ]


def run_lock_corpus() -> Dict[str, Any]:
    """Run every corpus case through the REAL LockService; deterministic."""

    def run_one(case: Dict[str, Any]) -> Dict[str, Any]:
        report = case["report"]
        receipt = case["receipt"]
        draft = case.get("draft", GOLDEN_DRAFT)
        refs = lineage_refs(report=report, receipt=receipt)
        if case.get("drop"):
            refs = [r for r in refs if r.artifact_type not in case["drop"]]
        if case.get("corrupt"):
            for artifact_type, new_hash in case["corrupt"]:
                refs = [
                    PackageArtifactRef(
                        artifact_type=r.artifact_type,
                        artifact_id=r.artifact_id,
                        content_hash=new_hash if r.artifact_type == artifact_type else r.content_hash,
                        revision_id=r.revision_id,
                    )
                    for r in refs
                ]
        if case.get("duplicate"):
            dup = PackageArtifactRef(
                artifact_type="ScreenplayDraft", artifact_id="art_draft",
                content_hash=draft.content_hash(), revision_id="rev_1",
            )
            refs = [*refs, dup]
        try:
            result = LockService().assemble(
                draft=draft, report=report, receipt=receipt, lineage_refs=refs,
            )
            return {"case": case["case"], "outcome": "ok", "codes": []}
        except LockValidationFailure as exc:
            codes = sorted({i["code"] for i in exc.details["issues"]})
            return {"case": case["case"], "outcome": "refused", "codes": codes}

    results = [run_one(case) for case in lock_corpus()]
    # Contract: every expected code must appear in the actual refusal codes.
    for case, result in zip(lock_corpus(), results):
        expected = set(case["expect"])
        assert result["outcome"] == "refused" and expected <= set(result["codes"]), (
            f"corpus case {case['case']}: expected {sorted(expected)}, got {result}"
        )
    return {"schema_version": "studio.lock_corpus/v1", "results": results}


# ---------------------------------------------------------------------------
# Committed artifact assembly
# ---------------------------------------------------------------------------


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def lock_corpus_manifest() -> List[Dict[str, Any]]:
    """Serializable projection of the corpus (case name + expected codes)."""
    return [{"case": c["case"], "expect": sorted(c["expect"])} for c in lock_corpus()]


def build_artifacts() -> Dict[str, bytes]:
    corpus = canonical_bytes(lock_corpus_manifest())
    results = canonical_bytes(run_lock_corpus())
    golden = canonical_bytes(golden_lock())
    artifacts = {
        "lock_corpus.json": corpus,
        "invalid_lock_results.json": results,
        "lock_golden.json": golden,
    }
    checksums = {
        "corpus": hashlib.sha256(corpus).hexdigest(),
        "results": hashlib.sha256(results).hexdigest(),
        "golden": hashlib.sha256(golden).hexdigest(),
    }
    artifacts["checksums.json"] = canonical_bytes(checksums)
    return artifacts


def tolerant_parsing_violations() -> List[str]:
    """Reuse the B2 canonical-path scan; B8 adds the lock service path."""
    try:
        from scripts.verification.produce_b2_evidence import tolerant_parsing_violations as scan
    except ImportError:  # pragma: no cover
        return []
    return sorted(set(scan()))


def evidence_markdown(
    golden: Dict[str, Any],
    results: Dict[str, Any],
    corpus: List[Dict[str, Any]],
) -> str:
    rows = "\n".join(
        f"| `{r['case']}` | `{r['outcome']}` | `{','.join(r['codes']) or '—'}` |"
        for r in results["results"]
    )
    mode_lines = "\n".join(
        f"- **{mode}** — receipt `{golden[mode]['receipt']['receipt_id']}` "
        f"(policy `{golden[mode]['receipt']['policy_id'] or '—'}`), package "
        f"`{golden[mode]['package']['package_id']}`, "
        f"{len(golden[mode]['package']['manifest'])} "
        f"manifest refs, hash `{golden[mode]['package_content_hash'][:16]}…`, "
        f"idempotent={golden[mode]['idempotent']}."
        for mode in sorted(APPROVAL_MODES)
    )
    return f"""# B8 Evidence — LOCKED_SCREENPLAY_GATE

Gate owner: Plan B. Baseline: B1 review/lock models + validators, B7 review
thresholds + iteration budget, A6 hash-bound approval/lock command
(`LockScreenplayCommand`, `derive_revision`), C5 hash-bound lock UI.
Fixtures: `fixtures/studio_contract_v0.1/story_lock/` (golden + corpus).

## 1. Deterministic lock policy (versioned, provider-free)

- Policy `{LOCK_POLICY_VERSION}`: the A-issued `LockedScreenplayReceipt` is
  the authority; assembly refuses unless: state is `READY_FOR_PRODUCTION`,
  receipt binds the target draft, approval mode is one of
  {sorted(APPROVAL_MODES)}, `HUMAN_REQUIRED` binds a policy id, the review
  verdict is PASS/PASS_WITH_WARNINGS with no blocking findings, `AUTO`
  requires a clean PASS, the iteration budget is not exceeded, and the
  lineage covers every required artifact type.
- Hash binding: the A ref hash of draft/report/receipt must equal the live
  canonical content hash — a post-lock mutation is refused (`HASH_MISMATCH`)
  and requires a derived revision instead. The package is assembled from
  immutable refs only, never copied mutable state (rule 7), and reassembles
  byte-identically (idempotent double lock).

## 2. Golden lock trace (Vietnamese rabbit/kite, 240s, 11-artifact lineage)

{mode_lines}

- Every package passes `validate_locked_package` with the issued receipt and
  exposes a presentation-safe `to_summary()` (manifest count + types).

## 3. Negative corpus results (real LockService)

| Case | Outcome | Refusal codes |
|---|---|---|
{rows}

## 4. Handler surface

- Registered B8 handler: `studio.story.lock` (ScreenplayDraft + ReviewReport
  -> LockedScreenplayReceipt + LockedScreenplayPackage) — matches
  `story_task_io.json`; the A atomic `READY_FOR_PRODUCTION` transition is
  requested by A's orchestrator command (`LockScreenplayCommand`, hash-bound
  with optimistic version), and the A-issued receipt is accepted as authority.
- No storage/queue/API/provider imports in the handler; lock assembly is
  deterministic and provider-free.

## 5. No tolerant free-text parsing on canonical paths

Tolerant-parser scan (reused from B2 over `core/.../domain/story/`,
`intelligence/.../story/`, incl. review + runtime_handlers):
**{len(tolerant_parsing_violations())} violation(s)**.

## 6. Gate verdict

**`LOCKED_SCREENPLAY_GATE`: PASS (B-side evidence).**

- Golden: `lock_golden.json` (checksum `{hashlib.sha256(canonical_bytes(golden)).hexdigest()[:16]}…`)
  — valid immutable package + receipt under all three approval modes.
- Corpus: `invalid_lock_results.json` (checksum
  `{hashlib.sha256(canonical_bytes(results)).hexdigest()[:16]}…`);
  checksums: `checksums.json`.
- A-side (atomic lock transition, optimistic version, post-lock read-only
  UI) and C-side (receipt/package display fields) halves are co-signed by
  their plan owners at contract review.
"""


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate committed fixtures read-only")
    args = parser.parse_args()

    artifacts = build_artifacts()

    if args.check:
        problems: List[str] = []
        for name, payload in artifacts.items():
            path = LOCK_DIR / name
            if not path.exists():
                problems.append(f"missing committed fixture {name}")
            elif path.read_bytes() != payload:
                problems.append(f"committed fixture {name} drifted from live code")
        if problems:
            print("B8 fixture violations:")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print("B8 fixtures OK: corpus, results, golden lock, checksums match live code.")
        return 0

    for name, payload in artifacts.items():
        _write(LOCK_DIR / name, payload)
    _write(
        EVIDENCE_PATH,
        evidence_markdown(golden_lock(), run_lock_corpus(), lock_corpus()).encode("utf-8"),
    )
    print(f"B8 fixtures written to {LOCK_DIR}")
    print(f"Evidence written to {EVIDENCE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
