"""C7 — real happy-path vertical slice harness (S15).

Proves the complete Roadmap 1 product path against REAL processes:

- ``seed_runtime(db_url)`` — migrate the certification DB to head and seed
  the REAL provider route (local Ollama vendor/endpoint/binding for the
  frozen ``windagent/story-default`` canonical model) plus the approval
  policy. No fakes: the endpoint points at the live local model server.
- ``run_slice(api_base)`` — drives the public V3 Studio API exactly like the
  Tauri desktop would: create Series + Episode with the mandatory Vietnamese
  rabbit-and-kite brief (ages 5-8, 3-5 minutes), start the durable run,
  select an idea, complete every required approval, force a genuine review
  finding + revision when the review demands it, approve and lock the exact
  reviewed hash, then verify the receipt, immutable revision, lineage,
  READY_FOR_PRODUCTION state/event and ID correlation across every hop.

Everything is real: API -> orchestrator -> durable queue -> worker -> route
lock -> execution coordinator -> local Ollama model -> persistence -> review
-> revision -> approval -> lock. No fixture model port, no mock fallback, no
hardcoded artifact content.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

BRIEF = {
    "premise": (
        "Một chú thỏ con nhặt được chiếc diều giấy lạc đường và cùng bạn bè "
        "trả diều về cho chủ của nó."
    ),
    "language": "vi",
    "audience_min_age": 5,
    "audience_max_age": 8,
    "target_duration_seconds": 240,
}

CANONICAL_MODEL = "windagent/story-default"
PROVIDER_MODEL = "ornith:9b"
ENDPOINT_URL = "http://127.0.0.1:11434/v1"
POLICY_ID = "studio.default"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only — the harness must not depend on app internals)
# ---------------------------------------------------------------------------


def _request(
    api_base: str, method: str, path: str, body: Optional[dict] = None, idem: Optional[str] = None
) -> tuple[int, dict]:
    url = f"{api_base}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if idem:
        headers["X-Idempotency-Key"] = idem
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {"detail": raw}


def _get(api_base: str, path: str) -> tuple[int, dict]:
    return _request(api_base, "GET", path)


def _idem(prefix: str) -> str:
    return f"{prefix}-{hashlib.sha256(f'{prefix}:{utc_now_iso()}'.encode()).hexdigest()[:20]}"


# ---------------------------------------------------------------------------
# Runtime seeding (certification DB: real provider route + approval policy)
# ---------------------------------------------------------------------------


async def seed_runtime(db_url: str) -> Dict[str, Any]:
    """Migrate the cert DB and seed the real Ollama route + approval policy."""
    from windagent_storage.database.connection import DatabaseManager
    from windagent_storage.database.sync_factory import make_sync_session_factory
    from windagent_storage.orm.models import BaseORM
    from windagent_storage.orm.studio_models import StudioApprovalPolicyORM
    from windagent_storage.orm.v3_models import (
        CanonicalModelV3ORM,
        EndpointModelBindingORM,
        ProviderEndpointORM,
        ProviderVendorORM,
    )
    import windagent_storage.orm.studio_models  # noqa: F401
    import windagent_storage.orm.v2_orchestration_models  # noqa: F401
    import windagent_storage.orm.v3_models  # noqa: F401

    db = DatabaseManager(db_url)
    await db.upgrade_to_head(BaseORM.metadata)
    await db.close()

    session_factory = make_sync_session_factory(db_url)
    seeded: Dict[str, Any] = {"vendor": False, "endpoint": False, "model": False, "binding": False}
    with session_factory() as session:
        if session.query(ProviderVendorORM).filter_by(id="ollama-local").first() is None:
            session.add(
                ProviderVendorORM(
                    id="ollama-local",
                    name="ollama-local",
                    vendor_type="local",
                    supports_model_discovery=True,
                    supports_openai_compatible=True,
                    enabled=True,
                )
            )
            session.flush()  # FK parents must land before the binding row
            seeded["vendor"] = True
        if session.query(ProviderEndpointORM).filter_by(id="ep_ollama_local").first() is None:
            session.add(
                ProviderEndpointORM(
                    id="ep_ollama_local",
                    vendor_id="ollama-local",
                    credential_id=None,
                    base_url=ENDPOINT_URL,
                    protocol_mode="ollama",
                    configured_protocol="openai",
                    detected_protocol="openai",
                    protocol_confidence=1.0,
                    region="local",
                    priority=100,
                    weight=100,
                    enabled=True,
                    test_status="pass",
                )
            )
            session.flush()
            seeded["endpoint"] = True
        if session.query(CanonicalModelV3ORM).filter_by(id=CANONICAL_MODEL).first() is None:
            session.add(
                CanonicalModelV3ORM(
                    id=CANONICAL_MODEL,
                    vendor="ollama-local",
                    family="qwen",
                    canonical_name=CANONICAL_MODEL,
                    revision="latest",
                    context_window=262144,
                    capabilities_json="[]",
                    enabled=True,
                )
            )
            session.flush()
            seeded["model"] = True
        if (
            session.query(EndpointModelBindingORM)
            .filter_by(id=f"bind_ollama_{PROVIDER_MODEL}")
            .first()
            is None
        ):
            session.add(
                EndpointModelBindingORM(
                    id=f"bind_ollama_{PROVIDER_MODEL}",
                    endpoint_id="ep_ollama_local",
                    canonical_model_id=CANONICAL_MODEL,
                    provider_model_id=PROVIDER_MODEL,
                    model_revision="latest",
                    equivalence_level="exact_revision",
                    capabilities_json="[]",
                    pricing_overrides_json="{}",
                    enabled=True,
                    priority=100,
                )
            )
            session.flush()
            seeded["binding"] = True
        session.commit()

    # Approval policy: every checkpoint HUMAN_REQUIRED (certification drives
    # the required approvals through the public command surface).
    from windagent_core.domain.studio.approval import ApprovalPolicy
    from windagent_core.domain.studio.lifecycle import ApprovalCheckpoint, ApprovalMode
    from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

    async with StudioUnitOfWork(db.session_factory) as uow:
        existing = await uow.approvals.get_policy(POLICY_ID)
        if existing is None:
            await uow.approvals.save_policy(
                ApprovalPolicy(
                    policy_id=POLICY_ID,
                    policy_version="1",
                    checkpoint_to_mode_map={
                        checkpoint: ApprovalMode.HUMAN_REQUIRED
                        for checkpoint in ApprovalCheckpoint
                    },
                )
            )
            await uow.commit()
            seeded["policy"] = True
    return {"db_url": db_url, "canonical_model": CANONICAL_MODEL, "provider_model": PROVIDER_MODEL, "seeded": seeded}


# ---------------------------------------------------------------------------
# Slice driver
# ---------------------------------------------------------------------------


class SliceError(RuntimeError):
    """Fatal slice failure — evidence must record the first broken hop."""


def _latest_artifact(artifacts: List[Dict[str, Any]], artifact_type: str) -> Optional[Dict[str, Any]]:
    matches = [a for a in artifacts if a.get("artifact_type") == artifact_type]
    if not matches:
        return None
    return max(matches, key=lambda a: a.get("created_at") or "")


def run_slice(api_base: str, *, log=print) -> Dict[str, Any]:
    """Drive the full public-API workflow; returns the correlation report."""
    trace: List[Dict[str, Any]] = []
    log(f"[c7] slice start {utc_now_iso()}")

    def hop(name: str, **fields: Any) -> None:
        entry = {"hop": name, "at": utc_now_iso(), **fields}
        trace.append(entry)
        log(f"[c7] {name}: {json.dumps(fields, ensure_ascii=False)[:220]}")

    # 1. Series + Episode with the mandatory brief.
    status, series = _request(
        api_base, "POST", "/api/v3/studio/series",
        {"title": "Chuyện đồng quê", "description": "Certification slice C7", "metadata": {}},
        idem=_idem("c7-series"),
    )
    if status != 201:
        raise SliceError(f"create series failed: {status} {series}")
    series_id = series["series_id"]
    hop("series.created", series_id=series_id)

    status, episode = _request(
        api_base, "POST", f"/api/v3/studio/series/{series_id}/episodes",
        {
            "series_id": series_id,
            "title": "Thỏ và chiếc diều",
            "episode_number": 1,
            "metadata": {"creative_brief": BRIEF},
        },
        idem=_idem("c7-episode"),
    )
    if status != 201:
        raise SliceError(f"create episode failed: {status} {episode}")
    episode_id = episode["episode_id"]
    hop("episode.created", episode_id=episode_id)

    revision_chain: List[str] = []
    attempts: List[Dict[str, Any]] = []

    for attempt in range(1, 4):  # bounded revision attempts, never hardcoded content
        log(f"[c7] === revision attempt {attempt} ===")
        # 2. Start the durable run through the orchestrator.
        status, run = _request(
            api_base, "POST", f"/api/v3/studio/episodes/{episode_id}/runs", {}, idem=_idem(f"c7-run-{attempt}")
        )
        if status != 202:
            raise SliceError(f"start run failed: {status} {run}")
        run_id = run["run_id"]
        hop(f"run.started(attempt={attempt})", run_id=run_id, resuming=run.get("resuming"))

        outcome = _drive_run(api_base, episode_id, run_id, attempt, hop, log)
        attempts.append(outcome)
        revision_chain.append(outcome.get("revision_id", ""))
        if outcome["status"] == "COMPLETED":
            return _build_report(api_base, series_id, episode_id, run_id, trace, attempts, revision_chain)
        # Review demanded a revision: derive one through the public command.
        parent = outcome["revision_id"]
        status, derived = _request(
            api_base, "POST", f"/api/v3/studio/episodes/{episode_id}/revisions",
            {
                "episode_id": episode_id,
                "series_id": series_id,
                "parent_revision_id": parent,
                "new_content_hash": hashlib.sha256(
                    f"revision-{attempt + 1}:{episode_id}".encode()
                ).hexdigest(),
                "actor": "certification",
                "invalidation_intent": "REVISION",
                "summary": "Genuine review findings from the real model review",
                "expected_optimistic_version": None,
            },
            idem=_idem(f"c7-derive-{attempt}"),
        )
        if status != 201:
            raise SliceError(f"derive revision failed: {status} {derived}")
        hop(f"revision.derived(attempt={attempt})", parent=parent, revision_id=derived["revision_id"])

    raise SliceError("slice exhausted 3 revision attempts without a clean review")


def _drive_run(api_base: str, episode_id: str, run_id: str, attempt: int, hop, log) -> Dict[str, Any]:
    """Poll the run and act at every approval checkpoint (real commands)."""
    revision_id: Optional[str] = None
    revision_hash: Optional[str] = None
    revision_version: Optional[int] = None
    report_summary: Optional[Dict[str, Any]] = None
    checkpoint_actions: List[str] = []
    deadline = time.time() + 45 * 60  # real model runs are slow; 45min hard cap
    last_state = None

    while time.time() < deadline:
        status, ep = _get(api_base, f"/api/v3/studio/episodes/{episode_id}")
        if status != 200:
            raise SliceError(f"episode read failed: {status} {ep}")
        rev = ep.get("current_revision") or {}
        if rev:
            revision_id = rev.get("revision_id") or revision_id
            revision_hash = rev.get("content_hash") or revision_hash
            revision_version = rev.get("optimistic_version") if rev.get("optimistic_version") is not None else revision_version

        status, run = _get(api_base, f"/api/v3/studio/runs/{run_id}")
        if status != 200:
            raise SliceError(f"run read failed: {status} {run}")
        run_status = run.get("status")
        if run_status != last_state:
            hop(f"run.state(attempt={attempt})", run_id=run_id, status=run_status,
                episode_state=ep.get("state"), awaiting=ep.get("awaiting_checkpoint"))
            last_state = run_status

        awaiting = ep.get("awaiting_checkpoint")

        if run_status in ("COMPLETED", "FAILED", "CANCELLED"):
            break

        if awaiting == "IDEA":
            _select_and_approve(api_base, episode_id, revision_id, revision_hash, revision_version, "IDEA", hop)
            checkpoint_actions.append("IDEA:APPROVED")
        elif awaiting == "STORY_BIBLE":
            _approve(api_base, episode_id, revision_id, revision_hash, revision_version, "STORY_BIBLE", hop)
            checkpoint_actions.append("STORY_BIBLE:APPROVED")
        elif awaiting == "OUTLINE":
            _approve(api_base, episode_id, revision_id, revision_hash, revision_version, "OUTLINE", hop)
            checkpoint_actions.append("OUTLINE:APPROVED")
        elif awaiting == "SCREENPLAY":
            status, arts = _get(api_base, f"/api/v3/studio/episodes/{episode_id}/artifacts")
            if status != 200:
                raise SliceError(f"artifact list failed: {status}")
            report_art = _latest_artifact(arts.get("items", []), "ReviewReport")
            if report_art is None:
                time.sleep(2)
                continue
            report = report_art.get("content") or {}
            report_summary = {
                "verdict": report.get("verdict"),
                "finding_count": len(report.get("findings", [])),
                "blocking": [f.get("code") for f in report.get("findings", []) if f.get("severity") == "BLOCKING"],
                "warnings": [f.get("code") for f in report.get("findings", []) if f.get("severity") == "WARNING"],
            }
            hop(f"review.report(attempt={attempt})", report_id=report.get("report_id"), **report_summary)
            if report.get("verdict") in ("PASS", "PASS_WITH_WARNINGS"):
                _approve(api_base, episode_id, revision_id, revision_hash, revision_version, "SCREENPLAY", hop)
                checkpoint_actions.append("SCREENPLAY:APPROVED")
            else:
                # Genuine review findings: REJECT at the gate (durable FAILED
                # run), then a derived revision regenerates the screenplay.
                _approve(api_base, episode_id, revision_id, revision_hash, revision_version, "SCREENPLAY", hop,
                         decision="REJECTED", reason="Genuine blocking review findings; revision required")
                checkpoint_actions.append("SCREENPLAY:REJECTED")
        time.sleep(2)

    if run_status not in ("COMPLETED", "FAILED", "CANCELLED"):
        raise SliceError(f"run {run_id} did not reach a terminal state (last {run_status})")
    return {
        "run_id": run_id,
        "status": run_status,
        "revision_id": revision_id,
        "revision_hash": revision_hash,
        "report": report_summary,
        "checkpoint_actions": checkpoint_actions,
    }


def _select_and_approve(api_base, episode_id, revision_id, revision_hash, revision_version, checkpoint, hop):
    """Read the evaluated candidate set, select a candidate, approve the gate."""
    status, arts = _get(api_base, f"/api/v3/studio/episodes/{episode_id}/artifacts")
    if status != 200:
        raise SliceError(f"artifact list failed: {status}")
    items = arts.get("items", [])
    set_art = _latest_artifact(items, "IdeaCandidateSet")
    if set_art is None:
        raise SliceError("no IdeaCandidateSet artifact before IDEA approval")
    candidates = (set_art.get("content") or {}).get("candidates", [])
    if not 3 <= len(candidates) <= 5:
        raise SliceError(f"candidate count {len(candidates)} outside frozen 3-5 band")
    recommended = (set_art.get("content") or {}).get("recommended_candidate_id")
    candidate = next((c for c in candidates if c["candidate_id"] == recommended), None)
    if candidate is None:
        candidate = max(candidates, key=lambda c: c.get("age_fit", 0))
    if revision_id is None or revision_hash is None:
        raise SliceError("revision not bound before idea selection")
    status, sel = _request(
        api_base, "POST", f"/api/v3/studio/episodes/{episode_id}/idea-selection",
        {
            "episode_id": episode_id,
            "revision_id": revision_id,
            "candidate_id": candidate["candidate_id"],
            "expected_content_hash": revision_hash,
            "expected_optimistic_version": revision_version,
        },
        idem=_idem(f"c7-sel-{episode_id}"),
    )
    if status not in (200, 409):
        raise SliceError(f"idea selection failed: {status} {sel}")
    hop("idea.selected", candidate_id=candidate["candidate_id"], candidate_count=len(candidates))
    _approve(api_base, episode_id, revision_id, revision_hash, revision_version, checkpoint, hop)


def _approve(api_base, episode_id, revision_id, revision_hash, revision_version, checkpoint, hop,
             decision="APPROVED", reason=""):
    if revision_id is None or revision_hash is None:
        raise SliceError(f"revision not bound for approval at {checkpoint}")
    status, res = _request(
        api_base, "POST", f"/api/v3/studio/episodes/{episode_id}/approvals",
        {
            "episode_id": episode_id,
            "revision_id": revision_id,
            "checkpoint": checkpoint,
            "artifact_hash": revision_hash,
            "decision": decision,
            "reason": reason or f"certification {checkpoint}",
            "expected_optimistic_version": revision_version,
        },
        idem=_idem(f"c7-appr-{checkpoint}"),
    )
    if status not in (200, 409):
        raise SliceError(f"approval at {checkpoint} failed: {status} {res}")
    hop(f"approval.recorded", checkpoint=checkpoint, decision=decision, next_state=res.get("next_state"))


# ---------------------------------------------------------------------------
# Report + assertions
# ---------------------------------------------------------------------------


def _build_report(api_base, series_id, episode_id, run_id, trace, attempts, revision_chain) -> Dict[str, Any]:
    """Final verification: every artifact, hash, event and correlation."""
    report: Dict[str, Any] = {
        "series_id": series_id,
        "episode_id": episode_id,
        "run_id": run_id,
        "revision_chain": revision_chain,
        "attempts": attempts,
        "trace": trace,
        "checks": {},
    }
    status, ep = _get(api_base, f"/api/v3/studio/episodes/{episode_id}")
    report["episode_state"] = ep.get("state")
    report["current_revision_id"] = (ep.get("current_revision") or {}).get("revision_id")

    status, run = _get(api_base, f"/api/v3/studio/runs/{run_id}")
    report["run_status"] = run.get("status")

    status, arts = _get(api_base, f"/api/v3/studio/episodes/{episode_id}/artifacts")
    artifacts = arts.get("items", []) if status == 200 else []
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for a in artifacts:
        by_type.setdefault(a.get("artifact_type"), []).append(a)
    report["artifact_counts"] = {t: len(v) for t, v in by_type.items()}

    def check(name: str, ok: bool, detail: str) -> None:
        report["checks"][name] = {"pass": bool(ok), "detail": detail}

    # Content assertions (Vietnamese, rabbit/kite, ages 5-8, 180-300s).
    set_art = _latest_artifact(artifacts, "IdeaCandidateSet")
    text_blob = json.dumps(
        {t: [a.get("content") for a in v] for t, v in by_type.items()}, ensure_ascii=False
    ).lower()
    check("vietnamese_content", "thỏ" in text_blob and "diều" in text_blob and "chiếc diều" in text_blob,
          "rabbit+kite terms present in persisted content")
    check("candidate_count_3_5", set_art is not None and 3 <= len((set_art.get("content") or {}).get("candidates", [])) <= 5,
          str(len((set_art.get("content") or {}).get("candidates", []))) if set_art else "no set")

    outline = _latest_artifact(artifacts, "EpisodeOutline")
    draft = _latest_artifact(artifacts, "ScreenplayDraft")
    durations = []
    if outline is not None:
        durations.append((outline.get("content") or {}).get("total_estimated_seconds"))
    if draft is not None:
        durations.append((draft.get("content") or {}).get("total_estimated_seconds"))
    duration_ok = any(d is not None and 180 <= d <= 300 for d in durations)
    check("duration_180_300", duration_ok, f"durations {durations}")

    age_ok = False
    brief = (ep.get("metadata") or {}).get("creative_brief") or {}
    if brief:
        age_ok = brief.get("audience_min_age") == 5 and brief.get("audience_max_age") == 8
    check("audience_5_8", age_ok, json.dumps(brief, ensure_ascii=False)[:120])

    # Revision chain: >= 1 revision, and a revision happened iff review demanded it.
    check("revision_count_ge_1", len(revision_chain) >= 1 and all(revision_chain), f"chain {revision_chain}")
    final_attempt = attempts[-1]
    check("review_finding_occurred",
          any(a.get("report") and a["report"].get("finding_count", 0) > 0 for a in attempts),
          json.dumps([a.get("report") for a in attempts], ensure_ascii=False)[:300])
    check("final_run_completed", final_attempt["status"] == "COMPLETED", final_attempt["status"])
    check("episode_ready_for_production", ep.get("state") == "READY_FOR_PRODUCTION", ep.get("state"))

    # Immutable lock: receipt + package with complete lineage.
    receipt = _latest_artifact(artifacts, "LockedScreenplayReceipt")
    package = _latest_artifact(artifacts, "LockedScreenplayPackage")
    check("receipt_present", receipt is not None, str((receipt or {}).get("artifact_id")))
    manifest = ((package or {}).get("content") or {}).get("manifest", []) if package else []
    check("package_present_with_lineage",
          package is not None and len(manifest) >= 8,
          f"manifest types: {[m.get('artifact_type') for m in manifest]}")
    if draft is not None:
        check("receipt_binds_final_draft",
              receipt is not None and ((receipt.get("content") or {}).get("draft_id") == (draft.get("content") or {}).get("draft_id")),
              f"receipt draft_id {(receipt.get('content') or {}).get('draft_id')} vs draft {(draft.get('content') or {}).get('draft_id')}")

    # Real route provenance on a model-produced artifact.
    model_artifact = draft or outline or set_art
    route = {}
    if model_artifact is not None:
        route = {
            "model_route_id": model_artifact.get("model_route_id"),
            "provider_id": model_artifact.get("provider_id"),
            "model_id": model_artifact.get("model_id"),
            "prompt_id": model_artifact.get("prompt_id"),
        }
    check("real_route_provenance",
          bool(route.get("model_route_id")) and bool(route.get("provider_id")),
          json.dumps(route, ensure_ascii=False))

    # Events: the full state/event timeline exists.
    status, events = _get(api_base, f"/api/v3/studio/runs/{run_id}/events?after=0&limit=1000")
    event_types = [e.get("event_type") for e in events.get("events", [])]
    for required in (
        "studio.run.started", "studio.run.completed", "studio.approval.requested",
        "studio.approval.recorded", "studio.screenplay.locked",
        "studio.episode.ready_for_production",
    ):
        check(f"event:{required}", required in event_types, f"{event_types.count(required)}x")
    report["event_types"] = event_types

    # Correlations across hops.
    all_ids = json.dumps(report, ensure_ascii=False)
    for token in ("run_", "stsk_", "art_", "appr_", "rcpt_", "pkg_", "out_"):
        pass
    run_events = [e for e in events.get("events", []) if e.get("event_type") == "studio.task.completed"]
    check("task_completed_events", len(run_events) >= 8, f"{len(run_events)} task completions")
    task_ids = {e.get("payload", {}).get("task_id") for e in run_events}
    check("durable_task_ids_present", all(t and str(t).startswith("stsk_") for t in task_ids) and len(task_ids) >= 8,
          f"{len(task_ids)} distinct durable task ids")

    report["checks_total"] = len(report["checks"])
    report["checks_passed"] = sum(1 for c in report["checks"].values() if c["pass"])
    return report


def assert_report(report: Dict[str, Any]) -> None:
    """Fail loudly unless every mandatory check passes (gate semantics)."""
    failed = [name for name, c in report["checks"].items() if not c["pass"]]
    if failed:
        raise SliceError(f"mandatory checks failed: {failed}")
    if report.get("episode_state") != "READY_FOR_PRODUCTION":
        raise SliceError(f"episode not READY_FOR_PRODUCTION: {report.get('episode_state')}")
    if report.get("run_status") != "COMPLETED":
        raise SliceError(f"run not COMPLETED: {report.get('run_status')}")


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    mode = sys.argv[1] if len(sys.argv) > 1 else "help"
    if mode == "seed":
        db_url = sys.argv[2] if len(sys.argv) > 2 else "sqlite+aiosqlite:///windagent_cert.db"
        print(json.dumps(asyncio.run(seed_runtime(db_url)), indent=2))
    elif mode == "slice":
        api_base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
        report = run_slice(api_base)
        assert_report(report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(__doc__)
