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
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
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
SCREENPLAY_QUALITY_THRESHOLD = 0.85
REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_CAPABILITIES = frozenset(
    {
        "durable_db",
        "queue",
        "outbox",
        "worker",
        "model_route",
        "studio_orchestration",
        "story_engine",
    }
)
REQUIRED_STORY_HANDLERS = frozenset(
    {
        "studio.story.idea.generate",
        "studio.story.idea.evaluate",
        "studio.story.bible.generate",
        "studio.story.beats.generate",
        "studio.story.outline.generate",
        "studio.story.screenplay.generate",
        "studio.story.review",
        "studio.story.revise",
        "studio.story.lock",
    }
)
MODEL_PROVENANCE_FIELDS = (
    "canonical_model_id",
    "provider_model_id",
    "provider_id",
    "endpoint_id",
    "provider_binding_id",
    "model_route_id",
    "provider_attempt_id",
    "prompt_id",
    "prompt_version",
    "output_schema_contract",
)
CERTIFICATION_NAMESPACE = os.getenv("WINDAGENT_CERTIFICATION_NAMESPACE", "").strip() or (
    f"cert-{uuid.uuid4().hex}"
)


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
    """Stable key for one logical operation within a fresh process namespace."""

    digest = hashlib.sha256(f"{CERTIFICATION_NAMESPACE}:{prefix}".encode()).hexdigest()
    return f"{prefix}-{digest[:20]}"


# ---------------------------------------------------------------------------
# Runtime seeding (certification DB: real provider route + approval policy)
# ---------------------------------------------------------------------------


async def seed_runtime(db_url: str) -> Dict[str, Any]:
    """Migrate the cert DB and seed the real Ollama route + approval policy."""
    from windagent_storage.database.connection import DatabaseManager
    from windagent_storage.database.sync_factory import make_sync_session_factory
    from windagent_storage.orm.models import BaseORM
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

    # The policy is fixed before the Episode exists. The real review model's
    # scores, not the harness, decide whether the threshold requests revision.
    from windagent_core.domain.studio.approval import ApprovalPolicy
    from windagent_core.domain.studio.lifecycle import ApprovalCheckpoint, ApprovalMode
    from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

    async with StudioUnitOfWork(db.session_factory) as uow:
        await uow.approvals.save_policy(
            ApprovalPolicy(
                policy_id=POLICY_ID,
                policy_version="c7-quality-v1",
                checkpoint_to_mode_map={
                    checkpoint: ApprovalMode.HUMAN_REQUIRED
                    for checkpoint in ApprovalCheckpoint
                },
                quality_thresholds={
                    ApprovalCheckpoint.SCREENPLAY: SCREENPLAY_QUALITY_THRESHOLD
                },
                max_review_revision_iterations=2,
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


def _provider_preflight() -> Dict[str, Any]:
    """Prove the configured local provider is reachable and exposes the bound model."""

    request = urllib.request.Request(f"{ENDPOINT_URL.rstrip('/')}/models", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
    except (OSError, ValueError, urllib.error.HTTPError) as exc:
        raise SliceError(f"provider preflight failed: {type(exc).__name__}: {exc}") from exc
    model_ids = sorted(
        str(item.get("id"))
        for item in payload.get("data", [])
        if isinstance(item, dict) and item.get("id")
    )
    if PROVIDER_MODEL not in model_ids:
        raise SliceError(
            f"provider preflight did not expose bound model {PROVIDER_MODEL!r}: {model_ids}"
        )
    return {
        "endpoint": ENDPOINT_URL,
        "provider_model_id": PROVIDER_MODEL,
        "listed_model_count": len(model_ids),
        "reachable": True,
    }


def _certification_preflight(api_base: str, hop) -> Dict[str, Any]:
    """Fail before Series creation unless the live topology attests C7 authority."""

    deadline = time.monotonic() + 60
    status = 0
    profile: Dict[str, Any] = {}
    capabilities: Dict[str, Dict[str, Any]] = {}
    while time.monotonic() < deadline:
        try:
            status, profile = _get(api_base, "/api/v3/studio/capabilities")
        except OSError:
            time.sleep(0.5)
            continue
        capabilities = {
            item.get("name"): item
            for item in profile.get("capabilities", [])
            if isinstance(item, dict) and item.get("name")
        }
        ready = (
            status == 200
            and profile.get("certification_mode") is True
            and not profile.get("fail_closed_flags")
            and all(
                (capabilities.get(name) or {}).get("status") == "AVAILABLE"
                for name in REQUIRED_CAPABILITIES
            )
        )
        if ready:
            break
        time.sleep(0.5)
    else:
        raise SliceError(
            f"capability preflight timed out before Series creation: {status} {profile}"
        )
    missing = sorted(
        name
        for name in REQUIRED_CAPABILITIES
        if (capabilities.get(name) or {}).get("status") != "AVAILABLE"
    )
    if missing:
        raise SliceError(f"capability preflight unavailable: {missing}")
    if profile.get("certification_mode") is not True:
        raise SliceError("capability preflight reports certification_mode=false")
    if profile.get("fail_closed_flags"):
        raise SliceError(
            f"capability preflight reports unsafe flags: {profile['fail_closed_flags']}"
        )

    worker_metadata = capabilities["worker"].get("metadata") or {}
    workers = worker_metadata.get("eligible_studio_workers") or []
    api_sha = worker_metadata.get("api_source_sha")
    if worker_metadata.get("eligible_studio_worker_count") != len(workers) or not workers:
        raise SliceError("capability preflight has no eligible Studio worker attestation")
    if not api_sha:
        raise SliceError("capability preflight has no API candidate SHA")
    for worker in workers:
        handler_names = set(worker.get("handler_names") or [])
        if (
            worker.get("source_sha") != api_sha
            or worker.get("certification_mode") is not True
            or worker.get("runtime_adapter") != "StudioRuntimeAdapter"
            or worker.get("completion_reconciler") != "StudioCompletionReconciler"
            or worker.get("completion_recovery") != "StudioCompletionRecovery"
            or worker.get("model_port_type") != "RouteLockedModelPort"
            or worker.get("canonical_model") != CANONICAL_MODEL
            or worker.get("provider_route_ready") is not True
            or worker.get("durable_route_lock") is not True
            or worker.get("fake_runtime") is not False
            or not worker.get("handler_digest")
            or not REQUIRED_STORY_HANDLERS <= handler_names
            or not worker.get("endpoint_binding_identities")
        ):
            raise SliceError(f"worker attestation is not certification eligible: {worker}")
        for identity in worker["endpoint_binding_identities"]:
            if not all(
                identity.get(field)
                for field in ("binding_id", "endpoint_id", "provider_model_id")
            ):
                raise SliceError(f"worker provider binding identity is incomplete: {identity}")
            if identity.get("provider_model_id") != PROVIDER_MODEL:
                raise SliceError(f"worker attests an unexpected provider model: {identity}")

    provider = _provider_preflight()
    safe_profile = {**profile, "provider_preflight": provider}
    hop(
        "certification.preflight",
        api_source_sha=api_sha,
        eligible_worker_ids=[worker.get("worker_id") for worker in workers],
        canonical_model=CANONICAL_MODEL,
        provider_model_id=PROVIDER_MODEL,
    )
    return safe_profile


def run_slice(api_base: str, *, db_url: str, log=print) -> Dict[str, Any]:
    """Drive the full public-API workflow; returns the correlation report."""
    trace: List[Dict[str, Any]] = []
    log(f"[c7] slice start {utc_now_iso()}")

    def hop(name: str, **fields: Any) -> None:
        entry = {"hop": name, "at": utc_now_iso(), **fields}
        trace.append(entry)
        log(f"[c7] {name}: {json.dumps(fields, ensure_ascii=False)[:220]}")

    capability_profile = _certification_preflight(api_base, hop)

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

    status, run = _request(
        api_base,
        "POST",
        f"/api/v3/studio/episodes/{episode_id}/runs",
        {},
        idem=_idem("c7-run"),
    )
    if status != 202:
        raise SliceError(f"start run failed: {status} {run}")
    run_id = run["run_id"]
    hop("run.started", run_id=run_id, resuming=run.get("resuming"))

    outcome = _drive_run(api_base, episode_id, run_id, 1, hop, log)
    if outcome["status"] != "COMPLETED":
        raise SliceError(
            f"single-run quality workflow ended {outcome['status']}; "
            "the harness never derives a synthetic replacement revision"
        )
    return _build_report(
        api_base,
        series_id,
        episode_id,
        run_id,
        trace,
        [outcome],
        capability_profile,
        db_url,
    )


def _drive_run(api_base: str, episode_id: str, run_id: str, attempt: int, hop, log) -> Dict[str, Any]:
    """Poll the run and act at every approval checkpoint (real commands)."""
    revision_id: Optional[str] = None
    revision_hash: Optional[str] = None
    revision_version: Optional[int] = None
    report_summary: Optional[Dict[str, Any]] = None
    checkpoint_actions: List[str] = []
    handled_review_reports: set[str] = set()
    deadline = time.time() + 45 * 60
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

        if run_status in ("COMPLETED", "FAILED", "CANCELLED", "REVISION_REQUIRED"):
            break

        if awaiting == "IDEA" and "IDEA:APPROVED" not in checkpoint_actions:
            _select_and_approve(api_base, episode_id, revision_id, revision_hash, revision_version, "IDEA", hop)
            checkpoint_actions.append("IDEA:APPROVED")
        elif awaiting == "STORY_BIBLE" and "STORY_BIBLE:APPROVED" not in checkpoint_actions:
            _approve(api_base, episode_id, revision_id, revision_hash, revision_version, "STORY_BIBLE", hop)
            checkpoint_actions.append("STORY_BIBLE:APPROVED")
        elif awaiting == "OUTLINE" and "OUTLINE:APPROVED" not in checkpoint_actions:
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
            report_id = report.get("report_id")
            if not report_id:
                raise SliceError("persisted ReviewReport has no report_id")
            if report_id in handled_review_reports:
                time.sleep(2)
                continue
            report_summary = {
                "report_id": report_id,
                "draft_id": report.get("draft_id"),
                "review_iteration": report.get("review_iteration"),
                "verdict": report.get("verdict"),
                "finding_count": len(report.get("findings", [])),
                "findings": report.get("findings", []),
                "blocking": [
                    f.get("code")
                    for f in report.get("findings", [])
                    if f.get("severity") == "BLOCKING"
                ],
                "warnings": [f.get("code") for f in report.get("findings", []) if f.get("severity") == "WARNING"],
            }
            hop(f"review.report(attempt={attempt})", report_id=report.get("report_id"), **report_summary)
            if report.get("verdict") in ("PASS", "PASS_WITH_WARNINGS"):
                _approve(api_base, episode_id, revision_id, revision_hash, revision_version, "SCREENPLAY", hop)
                checkpoint_actions.append(f"SCREENPLAY:{report_id}:APPROVED")
            else:
                qualifying = [
                    finding
                    for finding in report.get("findings", [])
                    if finding.get("code") == "QUALITY_THRESHOLD_VIOLATION"
                    and finding.get("severity") == "BLOCKING"
                    and finding.get("source") == "model"
                    and finding.get("threshold") == SCREENPLAY_QUALITY_THRESHOLD
                    and finding.get("actual_score") is not None
                    and finding.get("provenance")
                ]
                if not qualifying:
                    raise SliceError(
                        "SCREENPLAY rejection lacks a genuine blocking "
                        "policy-threshold finding"
                    )
                _approve(api_base, episode_id, revision_id, revision_hash, revision_version, "SCREENPLAY", hop,
                         decision="REJECTED", reason="Genuine blocking review findings; revision required")
                checkpoint_actions.append(f"SCREENPLAY:{report_id}:REJECTED")
            handled_review_reports.add(report_id)
        time.sleep(2)

    if run_status not in ("COMPLETED", "FAILED", "CANCELLED", "REVISION_REQUIRED"):
        raise SliceError(f"run {run_id} did not reach a terminal state (last {run_status})")
    return {
        "run_id": run_id,
        "status": run_status,
        "revision_id": revision_id,
        "revision_hash": revision_hash,
        "report": report_summary,
        "checkpoint_actions": checkpoint_actions,
        "review_reports_handled": sorted(handled_review_reports),
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
    if status != 200:
        raise SliceError(f"idea selection failed: {status} {sel}")
    status, authoritative = _get(api_base, f"/api/v3/studio/episodes/{episode_id}")
    if status != 200:
        raise SliceError(f"authoritative revision read after selection failed: {status}")
    current = authoritative.get("current_revision") or {}
    expected_version = revision_version + 1 if revision_version is not None else None
    if (
        current.get("revision_id") != revision_id
        or (current.get("metadata") or {}).get("selected_candidate_id")
        != candidate["candidate_id"]
        or current.get("content_hash") != revision_hash
        or current.get("optimistic_version") != expected_version
        or sel.get("optimistic_version") != expected_version
    ):
        raise SliceError(
            "idea selection did not return/persist the authoritative N+1 revision: "
            f"selection={sel} revision={current}"
        )
    hop(
        "idea.selected",
        candidate_id=candidate["candidate_id"],
        candidate_count=len(candidates),
        optimistic_version=current["optimistic_version"],
    )
    _approve(
        api_base,
        episode_id,
        revision_id,
        revision_hash,
        current["optimistic_version"],
        checkpoint,
        hop,
    )


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
        idem=_idem(
            f"c7-appr-{episode_id}-{revision_id}-{checkpoint}-{decision}-{revision_version}"
        ),
    )
    if status != 200:
        raise SliceError(f"approval at {checkpoint} failed: {status} {res}")
    hop("approval.recorded", checkpoint=checkpoint, decision=decision, next_state=res.get("next_state"))


# ---------------------------------------------------------------------------
# Report + assertions
# ---------------------------------------------------------------------------


def _json_load(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _sqlite_path(db_url: str) -> Path:
    prefix = "sqlite+aiosqlite:///"
    if not db_url.startswith(prefix):
        raise SliceError("C7 durable evidence currently requires sqlite+aiosqlite")
    path = Path(db_url[len(prefix) :])
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def _redact_fencing_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    return f"sha256:{hashlib.sha256(token.encode()).hexdigest()[:16]}"


def _durable_evidence(
    db_url: str, *, series_id: str, episode_id: str, run_id: str
) -> Dict[str, Any]:
    """Read canonical durable rows without mutating certification state."""

    path = _sqlite_path(db_url)
    if not path.is_file():
        raise SliceError(f"certification database does not exist: {path}")
    with sqlite3.connect(path, timeout=5) as connection:
        connection.row_factory = sqlite3.Row

        def rows(sql: str, params: tuple[Any, ...]) -> List[Dict[str, Any]]:
            return [dict(row) for row in connection.execute(sql, params).fetchall()]

        revisions = rows(
            """
            SELECT revision_id, parent_revision_id, content_hash, state, status,
                   lock_state, created_at, metadata_json
            FROM studio_revisions
            WHERE episode_id = ?
            ORDER BY created_at, revision_id
            """,
            (episode_id,),
        )
        nodes = rows(
            """
            SELECT run_id, dag_node_id, task_type, status, task_id, attempt,
                   input_hashes_json, output_hashes_json,
                   output_artifact_refs_json, version, error
            FROM studio_run_nodes
            WHERE run_id = ?
            ORDER BY rowid
            """,
            (run_id,),
        )
        tasks = rows(
            """
            SELECT tr.id AS task_id, tr.state, tr.retry_count, tr.version,
                   tr.facts_json, n.dag_node_id, n.attempt AS node_attempt
            FROM studio_run_nodes n
            JOIN task_runs tr ON tr.id = n.task_id
            WHERE n.run_id = ?
            ORDER BY n.rowid
            """,
            (run_id,),
        )
        leases = rows(
            """
            SELECT el.lease_id, el.run_id AS task_id, el.worker_id, el.status,
                   el.expires_at, el.lease_generation, el.fencing_token,
                   n.dag_node_id
            FROM studio_run_nodes n
            JOIN execution_leases el ON el.run_id = n.task_id
            WHERE n.run_id = ?
            ORDER BY n.rowid, el.lease_generation
            """,
            (run_id,),
        )
        attempts = rows(
            """
            SELECT CAST(ra.id AS TEXT) AS provider_attempt_id,
                   ra.route_lock_id, ra.turn_id AS task_id,
                   ra.attempt_index, ra.provider_binding_id, ra.status,
                   ra.http_status, ra.error_class, ra.started_at,
                   ra.finished_at, ra.prompt_tokens, ra.completion_tokens,
                   n.dag_node_id
            FROM studio_run_nodes n
            JOIN route_attempts_v3 ra ON ra.turn_id = n.task_id
            WHERE n.run_id = ?
            ORDER BY n.rowid, ra.attempt_index
            """,
            (run_id,),
        )
        approvals = rows(
            """
            SELECT approval_id, aggregate_id AS episode_id, revision_id,
                   artifact_hash, checkpoint, actor, role, decision,
                   reason, timestamp
            FROM studio_approval_decisions
            WHERE aggregate_id = ?
            ORDER BY timestamp, approval_id
            """,
            (episode_id,),
        )
        events = rows(
            """
            SELECT event_id, event_type, aggregate_id, sequence, occurred_at,
                   correlation_id, causation_id, studio_run_id, revision_ref,
                   artifact_refs_json, payload_json
            FROM studio_events
            WHERE studio_run_id = ? OR aggregate_id IN (?, ?)
            ORDER BY occurred_at, event_id
            """,
            (run_id, episode_id, series_id),
        )
        outbox = rows(
            """
            SELECT ob.id AS outbox_id, ob.event_id, ob.aggregate_id,
                   ob.event_type, ob.sequence_number, ob.status,
                   ob.attempt_count, ob.deduplication_key, ob.created_at
            FROM v2_outbox_records ob
            JOIN studio_events se ON se.event_id = ob.event_id
            WHERE se.studio_run_id = ? OR se.aggregate_id IN (?, ?)
            ORDER BY ob.created_at, ob.id
            """,
            (run_id, episode_id, series_id),
        )
        policy = rows(
            """
            SELECT policy_id, policy_version, checkpoint_to_mode_json,
                   quality_thresholds_json, max_review_revision_iterations,
                   effective_time
            FROM studio_approval_policies
            WHERE policy_id = ?
            ORDER BY effective_time DESC
            LIMIT 1
            """,
            (POLICY_ID,),
        )

    for revision in revisions:
        revision["metadata"] = _json_load(revision.pop("metadata_json"), {})
    for node in nodes:
        node["input_hashes"] = _json_load(node.pop("input_hashes_json"), [])
        node["output_hashes"] = _json_load(node.pop("output_hashes_json"), [])
        node["output_artifact_refs"] = _json_load(
            node.pop("output_artifact_refs_json"), []
        )
    for task in tasks:
        task["facts"] = _json_load(task.pop("facts_json"), {})
    for lease in leases:
        lease["fencing_token_digest"] = _redact_fencing_token(
            lease.pop("fencing_token")
        )
    for event in events:
        event["artifact_refs"] = _json_load(event.pop("artifact_refs_json"), [])
        event["payload"] = _json_load(event.pop("payload_json"), {})
    if policy:
        policy[0]["checkpoint_to_mode"] = _json_load(
            policy[0].pop("checkpoint_to_mode_json"), {}
        )
        policy[0]["quality_thresholds"] = _json_load(
            policy[0].pop("quality_thresholds_json"), {}
        )
    return {
        "database_path": str(path),
        "revisions": revisions,
        "nodes": nodes,
        "tasks": tasks,
        "leases": leases,
        "provider_attempts": attempts,
        "approvals": approvals,
        "events": events,
        "outbox": outbox,
        "policy": policy[0] if policy else None,
    }


def _values_for_key(value: Any, key: str) -> List[Any]:
    found: List[Any] = []
    if isinstance(value, dict):
        for candidate, child in value.items():
            if candidate == key:
                found.append(child)
            found.extend(_values_for_key(child, key))
    elif isinstance(value, list):
        for child in value:
            found.extend(_values_for_key(child, key))
    return found


def _add_check(report: Dict[str, Any], name: str, ok: bool, detail: Any) -> None:
    report["checks"][name] = {
        "pass": bool(ok),
        "detail": detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False),
    }


def _genuine_revision_checks(report: Dict[str, Any]) -> None:
    artifacts = report["artifacts"]
    durable = report["durable_evidence"]
    revisions = durable["revisions"]
    drafts = [a for a in artifacts if a.get("artifact_type") == "ScreenplayDraft"]
    reports = [a for a in artifacts if a.get("artifact_type") == "ReviewReport"]
    proposals = [a for a in artifacts if a.get("artifact_type") == "RevisionProposal"]
    diffs = [a for a in artifacts if a.get("artifact_type") == "StoryDiff"]
    proposal = _latest_artifact(proposals, "RevisionProposal")
    proposal_content = (proposal or {}).get("content") or {}
    blocking_report = next(
        (
            item
            for item in reports
            if (item.get("content") or {}).get("report_id")
            == proposal_content.get("review_report_id")
        ),
        None,
    )
    blocking_content = (blocking_report or {}).get("content") or {}
    qualifying = [
        finding
        for finding in blocking_content.get("findings", [])
        if finding.get("code") == "QUALITY_THRESHOLD_VIOLATION"
        and finding.get("severity") == "BLOCKING"
        and finding.get("source") == "model"
        and finding.get("dimension")
        and finding.get("threshold") == SCREENPLAY_QUALITY_THRESHOLD
        and finding.get("actual_score") is not None
        and finding.get("provenance")
    ]
    accepted_codes = proposal_content.get("accepted_finding_codes") or []
    _add_check(
        report,
        "genuine_blocking_policy_finding",
        bool(qualifying)
        and blocking_content.get("verdict") not in ("PASS", "PASS_WITH_WARNINGS")
        and all(finding["code"] in accepted_codes for finding in qualifying),
        {
            "review_report_id": blocking_content.get("report_id"),
            "qualifying_findings": qualifying,
            "accepted_finding_codes": accepted_codes,
        },
    )

    old_draft = next(
        (
            item
            for item in drafts
            if (item.get("content") or {}).get("draft_id")
            == proposal_content.get("draft_id")
        ),
        None,
    )
    story_diff = next(
        (
            item
            for item in diffs
            if (item.get("content") or {}).get("from_draft_id")
            == proposal_content.get("draft_id")
        ),
        None,
    )
    diff_content = (story_diff or {}).get("content") or {}
    new_draft = next(
        (
            item
            for item in drafts
            if (item.get("content") or {}).get("draft_id")
            == diff_content.get("to_draft_id")
        ),
        None,
    )
    old_draft_id = ((old_draft or {}).get("content") or {}).get("draft_id")
    new_draft_id = ((new_draft or {}).get("content") or {}).get("draft_id")
    nonempty_diff = bool(diff_content.get("scene_changes")) or bool(
        diff_content.get("dialogue_changes")
    )
    _add_check(
        report,
        "revision_artifact_chain",
        bool(proposal and blocking_report and old_draft and story_diff and new_draft)
        and old_draft_id != new_draft_id
        and old_draft.get("content_hash") != new_draft.get("content_hash")
        and nonempty_diff,
        {
            "review_report_id": blocking_content.get("report_id"),
            "proposal_id": proposal_content.get("proposal_id"),
            "diff_artifact_id": (story_diff or {}).get("artifact_id"),
            "old_draft_id": old_draft_id,
            "new_draft_id": new_draft_id,
            "old_hash": (old_draft or {}).get("content_hash"),
            "new_hash": (new_draft or {}).get("content_hash"),
            "diff_nonempty": nonempty_diff,
        },
    )

    old_revision = next(
        (
            revision
            for revision in revisions
            if revision.get("metadata", {}).get("source_screenplay_artifact_id")
            == (old_draft or {}).get("artifact_id")
        ),
        None,
    )
    new_revision = next(
        (
            revision
            for revision in revisions
            if revision.get("metadata", {}).get("source_screenplay_artifact_id")
            == (new_draft or {}).get("artifact_id")
        ),
        None,
    )
    seed_revisions = [revision for revision in revisions if not revision.get("parent_revision_id")]
    _add_check(
        report,
        "canonical_derived_revision_chain",
        len(revisions) >= 3
        and bool(seed_revisions)
        and bool(old_revision and new_revision)
        and old_revision.get("content_hash") == (old_draft or {}).get("content_hash")
        and new_revision.get("content_hash") == (new_draft or {}).get("content_hash")
        and new_revision.get("parent_revision_id") == old_revision.get("revision_id")
        and report.get("current_revision_id") == new_revision.get("revision_id"),
        revisions,
    )

    final_report = next(
        (
            item
            for item in reports
            if (item.get("content") or {}).get("draft_id") == new_draft_id
            and (item.get("content") or {}).get("verdict")
            in ("PASS", "PASS_WITH_WARNINGS")
            and not [
                finding
                for finding in (item.get("content") or {}).get("findings", [])
                if finding.get("severity") == "BLOCKING"
            ]
        ),
        None,
    )
    _add_check(
        report,
        "revised_draft_re_reviewed",
        bool(final_report)
        and (final_report.get("content") or {}).get("review_iteration", 0)
        > blocking_content.get("review_iteration", 0),
        (final_report or {}).get("content") or {},
    )

    revision_events = [
        event
        for event in durable["events"]
        if event.get("event_type") == "studio.revision.derived"
    ]
    _add_check(
        report,
        "revision_event_binds_revised_artifact",
        bool(new_revision)
        and any(
            event.get("revision_ref") == new_revision.get("revision_id")
            and event.get("payload", {}).get("source_artifact_id")
            == (new_draft or {}).get("artifact_id")
            and event.get("payload", {}).get("content_hash")
            == (new_draft or {}).get("content_hash")
            for event in revision_events
        ),
        revision_events,
    )

    screenplay_approvals = [
        approval
        for approval in durable["approvals"]
        if approval.get("checkpoint") == "SCREENPLAY"
    ]
    _add_check(
        report,
        "review_outcome_caused_revision_then_approval",
        bool(old_revision and new_revision)
        and any(
            item.get("decision") == "REJECTED"
            and item.get("revision_id") == old_revision.get("revision_id")
            and item.get("artifact_hash") == old_revision.get("content_hash")
            for item in screenplay_approvals
        )
        and any(
            item.get("decision") == "APPROVED"
            and item.get("revision_id") == new_revision.get("revision_id")
            and item.get("artifact_hash") == new_revision.get("content_hash")
            for item in screenplay_approvals
        ),
        screenplay_approvals,
    )

    receipt = _latest_artifact(artifacts, "LockedScreenplayReceipt")
    package = _latest_artifact(artifacts, "LockedScreenplayPackage")
    receipt_content = (receipt or {}).get("content") or {}
    package_content = (package or {}).get("content") or {}
    manifest = package_content.get("manifest") or []
    _add_check(
        report,
        "lock_binds_exact_final_reviewed_hash",
        bool(final_report and receipt and package and new_draft and new_revision)
        and receipt_content.get("draft_id") == new_draft_id
        and package_content.get("receipt_id") == receipt_content.get("receipt_id")
        and any(
            item.get("artifact_id") == new_draft.get("artifact_id")
            and item.get("content_hash") == new_draft.get("content_hash")
            for item in manifest
        )
        and any(item.get("artifact_id") == final_report.get("artifact_id") for item in manifest),
        {
            "receipt": receipt_content,
            "manifest": manifest,
            "final_review_report_id": ((final_report or {}).get("content") or {}).get(
                "report_id"
            ),
        },
    )


def _correlation_checks(report: Dict[str, Any]) -> None:
    durable = report["durable_evidence"]
    artifacts = {item.get("artifact_id"): item for item in report["artifacts"]}
    nodes = durable["nodes"]
    tasks = {item.get("task_id"): item for item in durable["tasks"]}
    leases_by_task: Dict[str, List[Dict[str, Any]]] = {}
    for lease in durable["leases"]:
        leases_by_task.setdefault(lease.get("task_id"), []).append(lease)
    attempts_by_task: Dict[str, List[Dict[str, Any]]] = {}
    for attempt in durable["provider_attempts"]:
        attempts_by_task.setdefault(attempt.get("task_id"), []).append(attempt)

    active_nodes = [node for node in nodes if node.get("status") != "SKIPPED"]
    task_links_ok = bool(active_nodes)
    lease_links_ok = bool(active_nodes)
    provider_links_ok = True
    model_stage_evidence: List[Dict[str, Any]] = []
    for node in active_nodes:
        task = tasks.get(node.get("task_id"))
        facts = (task or {}).get("facts") or {}
        task_links_ok = task_links_ok and bool(task) and (
            report["run_id"] in _values_for_key(facts, "studio_run_id")
            and node.get("dag_node_id") in _values_for_key(facts, "dag_node_id")
            and node.get("attempt") in _values_for_key(facts, "attempt")
        )
        task_leases = leases_by_task.get(node.get("task_id"), [])
        lease_links_ok = lease_links_ok and any(
            lease.get("dag_node_id") == node.get("dag_node_id")
            and lease.get("lease_generation", 0) >= 1
            and lease.get("fencing_token_digest")
            for lease in task_leases
        )
        if node.get("task_type") == "studio.story.lock":
            continue
        refs = node.get("output_artifact_refs") or []
        node_attempts = attempts_by_task.get(node.get("task_id"), [])
        node_ok = bool(refs and node_attempts)
        artifact_ids: List[str] = []
        provider_attempt_ids: List[str] = []
        for ref in refs:
            artifact = artifacts.get(ref.get("artifact_id"))
            artifact_ids.append(ref.get("artifact_id"))
            if not artifact or artifact.get("content_hash") != ref.get("content_hash"):
                node_ok = False
                continue
            if not all(artifact.get(field) for field in MODEL_PROVENANCE_FIELDS):
                node_ok = False
            if artifact.get("model_id") != artifact.get("provider_model_id"):
                node_ok = False
            matching_attempt = next(
                (
                    attempt
                    for attempt in node_attempts
                    if attempt.get("provider_attempt_id")
                    == str(artifact.get("provider_attempt_id"))
                ),
                None,
            )
            provider_attempt_ids.append(str(artifact.get("provider_attempt_id") or ""))
            if (
                not matching_attempt
                or matching_attempt.get("status") != "success"
                or matching_attempt.get("route_lock_id") != artifact.get("model_route_id")
                or matching_attempt.get("provider_binding_id")
                != artifact.get("provider_binding_id")
            ):
                node_ok = False
        provider_links_ok = provider_links_ok and node_ok
        model_stage_evidence.append(
            {
                "run_id": report["run_id"],
                "dag_node_id": node.get("dag_node_id"),
                "task_id": node.get("task_id"),
                "task_type": node.get("task_type"),
                "attempt": node.get("attempt"),
                "artifact_ids": artifact_ids,
                "provider_attempt_ids": provider_attempt_ids,
                "correlation_valid": node_ok,
            }
        )
    report["model_stage_provenance"] = model_stage_evidence
    _add_check(report, "dag_node_task_correlation", task_links_ok, durable["tasks"])
    _add_check(report, "task_claim_lease_fence_correlation", lease_links_ok, durable["leases"])
    _add_check(
        report,
        "model_stage_provider_attempt_correlation",
        provider_links_ok and len(model_stage_evidence) >= 9,
        model_stage_evidence,
    )

    public_events = report["public_events"]
    completed_event_tasks = {
        event.get("payload", {}).get("task_id")
        for event in public_events
        if event.get("event_type") == "studio.task.completed"
    }
    active_task_ids = {node.get("task_id") for node in active_nodes}
    _add_check(
        report,
        "task_event_correlation",
        bool(active_task_ids) and completed_event_tasks == active_task_ids,
        {
            "node_task_ids": sorted(str(item) for item in active_task_ids),
            "completed_event_task_ids": sorted(str(item) for item in completed_event_tasks),
        },
    )

    outbox_by_event = {item.get("event_id"): item for item in durable["outbox"]}
    run_events = [
        event for event in durable["events"] if event.get("studio_run_id") == report["run_id"]
    ]
    outbox_ok = bool(run_events) and all(
        event.get("event_id") in outbox_by_event
        and outbox_by_event[event["event_id"]].get("event_type") == event.get("event_type")
        and outbox_by_event[event["event_id"]].get("aggregate_id")
        == event.get("aggregate_id")
        and outbox_by_event[event["event_id"]].get("sequence_number")
        == event.get("sequence")
        for event in run_events
    )
    aggregate_sequences: Dict[str, List[int]] = {}
    for event in durable["events"]:
        aggregate_sequences.setdefault(event.get("aggregate_id"), []).append(
            event.get("sequence")
        )
    ordered = all(
        sequence == sorted(sequence) and len(sequence) == len(set(sequence))
        for sequence in aggregate_sequences.values()
    )
    _add_check(
        report,
        "outbox_domain_event_correlation_and_ordering",
        outbox_ok and ordered,
        {
            "run_event_count": len(run_events),
            "outbox_count": len(durable["outbox"]),
            "aggregate_sequences": aggregate_sequences,
        },
    )


def _build_report(
    api_base: str,
    series_id: str,
    episode_id: str,
    run_id: str,
    trace: List[Dict[str, Any]],
    attempts: List[Dict[str, Any]],
    capability_profile: Dict[str, Any],
    db_url: str,
) -> Dict[str, Any]:
    """Reconstruct the full public/durable authority chain and fail closed."""

    report: Dict[str, Any] = {
        "certification_namespace": CERTIFICATION_NAMESPACE,
        "series_id": series_id,
        "episode_id": episode_id,
        "run_id": run_id,
        "attempts": attempts,
        "trace": trace,
        "capability_profile": capability_profile,
        "checks": {},
    }
    status, episode = _get(api_base, f"/api/v3/studio/episodes/{episode_id}")
    if status != 200:
        raise SliceError(f"final episode read failed: {status} {episode}")
    status, run = _get(api_base, f"/api/v3/studio/runs/{run_id}")
    if status != 200:
        raise SliceError(f"final run read failed: {status} {run}")
    status, artifact_page = _get(
        api_base, f"/api/v3/studio/episodes/{episode_id}/artifacts"
    )
    if status != 200:
        raise SliceError(f"final artifact read failed: {status} {artifact_page}")
    status, event_page = _get(
        api_base, f"/api/v3/studio/runs/{run_id}/events?after=0&limit=1000"
    )
    if status != 200:
        raise SliceError(f"final event read failed: {status} {event_page}")

    artifacts = artifact_page.get("items") or []
    public_events = event_page.get("events") or []
    durable = _durable_evidence(
        db_url, series_id=series_id, episode_id=episode_id, run_id=run_id
    )
    report.update(
        {
            "episode_state": episode.get("state"),
            "current_revision_id": (episode.get("current_revision") or {}).get(
                "revision_id"
            ),
            "run_status": run.get("status"),
            "artifacts": artifacts,
            "artifact_counts": {},
            "public_events": public_events,
            "event_types": [event.get("event_type") for event in public_events],
            "durable_evidence": durable,
            "revision_chain": durable["revisions"],
        }
    )
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for artifact in artifacts:
        by_type.setdefault(artifact.get("artifact_type"), []).append(artifact)
    report["artifact_counts"] = {name: len(items) for name, items in by_type.items()}

    candidate_set = _latest_artifact(artifacts, "IdeaCandidateSet")
    candidate_count = len(((candidate_set or {}).get("content") or {}).get("candidates", []))
    content_blob = json.dumps(
        [artifact.get("content") for artifact in artifacts], ensure_ascii=False
    ).lower()
    _add_check(
        report,
        "vietnamese_rabbit_kite_content",
        "thỏ" in content_blob and "diều" in content_blob,
        "rabbit and kite terms are present in persisted model artifacts",
    )
    _add_check(report, "candidate_count_3_5", 3 <= candidate_count <= 5, candidate_count)
    final_draft = _latest_artifact(artifacts, "ScreenplayDraft")
    final_content = (final_draft or {}).get("content") or {}
    final_duration = final_content.get("total_estimated_seconds")
    if final_duration is None:
        final_duration = sum(
            scene.get("estimated_seconds", 0)
            for scene in final_content.get("scenes", [])
            if isinstance(scene, dict)
        )
    brief = (episode.get("metadata") or {}).get("creative_brief") or {}
    _add_check(
        report,
        "duration_180_300",
        isinstance(final_duration, (int, float)) and 180 <= final_duration <= 300,
        final_duration,
    )
    _add_check(
        report,
        "audience_5_8",
        brief.get("audience_min_age") == 5 and brief.get("audience_max_age") == 8,
        brief,
    )
    _add_check(
        report,
        "certification_policy_persisted_before_run",
        durable.get("policy", {}).get("policy_version") == "c7-quality-v1"
        and durable.get("policy", {}).get("quality_thresholds", {}).get("SCREENPLAY")
        == SCREENPLAY_QUALITY_THRESHOLD
        and durable.get("policy", {}).get("max_review_revision_iterations") == 2,
        durable.get("policy"),
    )
    _add_check(
        report,
        "final_run_completed",
        run.get("status") == "COMPLETED" and attempts[-1].get("status") == "COMPLETED",
        {"public": run.get("status"), "driver": attempts[-1].get("status")},
    )
    _add_check(
        report,
        "episode_ready_for_production",
        episode.get("state") == "READY_FOR_PRODUCTION",
        episode.get("state"),
    )
    _add_check(
        report,
        "capability_profile_attested",
        capability_profile.get("certification_mode") is True
        and not capability_profile.get("fail_closed_flags")
        and capability_profile.get("provider_preflight", {}).get("reachable") is True,
        capability_profile,
    )
    required_events = {
        "studio.run.started",
        "studio.run.completed",
        "studio.approval.requested",
        "studio.approval.recorded",
        "studio.story.revision_requested",
        "studio.screenplay.locked",
        "studio.episode.ready_for_production",
    }
    observed_events = set(report["event_types"])
    _add_check(
        report,
        "mandatory_event_timeline",
        required_events <= observed_events,
        {"missing": sorted(required_events - observed_events)},
    )
    artifact_ids = [artifact.get("artifact_id") for artifact in artifacts]
    content_hashes = [artifact.get("content_hash") for artifact in artifacts]
    _add_check(
        report,
        "no_duplicate_canonical_artifact",
        len(artifact_ids) == len(set(artifact_ids))
        and len(content_hashes) == len(set(content_hashes)),
        {"artifact_count": len(artifact_ids), "content_hash_count": len(content_hashes)},
    )

    _genuine_revision_checks(report)
    _correlation_checks(report)
    report["checks_total"] = len(report["checks"])
    report["checks_passed"] = sum(
        1 for check in report["checks"].values() if check["pass"]
    )
    return report


def assert_report(report: Dict[str, Any]) -> None:
    """Fail loudly unless every mandatory check passes (gate semantics)."""
    # Recompute relational checks so a stale/pre-edited checks dictionary can
    # never be treated as certification authority.
    _genuine_revision_checks(report)
    _correlation_checks(report)
    if report.get("redaction_safe") is False:
        report.setdefault("checks", {})["redaction_safe"] = {
            "pass": False,
            "detail": "evidence redaction scan failed",
        }
    if report.get("source_dirty_paths"):
        report.setdefault("checks", {})["source_worktree_clean"] = {
            "pass": False,
            "detail": json.dumps(report["source_dirty_paths"]),
        }
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
        db_url = (
            sys.argv[3]
            if len(sys.argv) > 3
            else "sqlite+aiosqlite:///windagent_cert.db"
        )
        report = run_slice(api_base, db_url=db_url)
        assert_report(report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(__doc__)
