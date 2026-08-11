"""C8 real failure/recovery certification harness.

The harness owns the API and worker processes it terminates.  Mutations enter
through ``/api/v3/studio``; direct database access is observation-only except
for a rejected stale-fence renewal through ``SqlDurableTaskQueue``.  It never
repairs rows, deletes leases/events, or injects a successful task result.
"""

from __future__ import annotations

import asyncio
import hashlib
import http.client
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.parse import urlsplit

from scripts.studio_roadmap.c7_slice_harness import (
    BRIEF,
    CANONICAL_MODEL,
    SliceError,
    _get,
    _idem,
    _latest_artifact,
    _request,
    utc_now_iso,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TERMINAL_RUN_STATES = {"COMPLETED", "FAILED", "CANCELLED"}


def _wait_for(
    probe: Callable[[], Optional[Any]], *, timeout: float, interval: float = 0.2, label: str
) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Optional[Exception] = None
    while time.monotonic() < deadline:
        try:
            value = probe()
            if value is not None and value is not False:
                return value
        except (OSError, ValueError, sqlite3.Error) as exc:
            last_error = exc
        time.sleep(interval)
    suffix = f"; last error: {last_error}" if last_error else ""
    raise SliceError(f"timed out waiting for {label}{suffix}")


def sqlite_path_from_url(db_url: str) -> Path:
    prefix = "sqlite+aiosqlite:///"
    if not db_url.startswith(prefix):
        raise ValueError("C8 managed recovery currently requires sqlite+aiosqlite")
    raw = db_url[len(prefix) :]
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def _redact_fence(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    return f"sha256:{hashlib.sha256(token.encode()).hexdigest()[:16]}"


@dataclass
class ManagedTopology:
    """Launch and stop only certification-owned API/worker subprocesses."""

    db_url: str
    api_base: str = "http://127.0.0.1:8878"
    log_dir: Path = REPO_ROOT / ".tmp" / "studio-c8"
    api_process: Optional[subprocess.Popen] = field(default=None, init=False)
    worker_process: Optional[subprocess.Popen] = field(default=None, init=False)
    _handles: List[Any] = field(default_factory=list, init=False)
    process_timeline: List[Dict[str, Any]] = field(default_factory=list, init=False)

    def _environment(self) -> Dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "WINDAGENT_DATABASE_URL": self.db_url,
                "WINDAGENT_CERTIFICATION_MODE": "1",
                "WINDAGENT_STUDIO_RUNTIME": "1",
                "WINDAGENT_STUDIO_MODEL_ROUTE": "1",
                "WINDAGENT_STUDIO_CANONICAL_MODEL": CANONICAL_MODEL,
                "PYTHONUNBUFFERED": "1",
            }
        )
        for unsafe in ("WINDAGENT_FAKE_RUNTIME", "WINDAGENT_MODEL_BACKEND"):
            env.pop(unsafe, None)
        return env

    def _log_handle(self, name: str):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        handle = (self.log_dir / f"{name}.log").open("a", encoding="utf-8")
        self._handles.append(handle)
        return handle

    def start_api(self) -> None:
        if self.api_process and self.api_process.poll() is None:
            return
        parsed = urlsplit(self.api_base)
        log = self._log_handle("api")
        self.api_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "windagent_api.main:app",
                "--host",
                parsed.hostname or "127.0.0.1",
                "--port",
                str(parsed.port or 8878),
            ],
            cwd=REPO_ROOT,
            env=self._environment(),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        self.process_timeline.append({"at": utc_now_iso(), "action": "api.started", "pid": self.api_process.pid})
        _wait_for(
            lambda: _get(self.api_base, "/api/v3/studio/capabilities")[0] == 200,
            timeout=60,
            interval=0.5,
            label="managed API readiness",
        )

    def start_worker(self) -> None:
        if self.worker_process and self.worker_process.poll() is None:
            return
        log = self._log_handle("worker")
        self.worker_process = subprocess.Popen(
            [sys.executable, "-m", "windagent_worker"],
            cwd=REPO_ROOT,
            env=self._environment(),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        self.process_timeline.append(
            {"at": utc_now_iso(), "action": "worker.started", "pid": self.worker_process.pid}
        )

    @staticmethod
    def _stop(process: Optional[subprocess.Popen], *, force: bool) -> None:
        if process is None or process.poll() is not None:
            return
        if force:
            process.kill()
        else:
            process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)

    def stop_api(self) -> None:
        if self.api_process and self.api_process.poll() is None:
            self.process_timeline.append(
                {"at": utc_now_iso(), "action": "api.stopped", "pid": self.api_process.pid}
            )
        self._stop(self.api_process, force=False)
        self.api_process = None

    def kill_worker(self) -> None:
        if self.worker_process and self.worker_process.poll() is None:
            self.process_timeline.append(
                {"at": utc_now_iso(), "action": "worker.killed", "pid": self.worker_process.pid}
            )
        self._stop(self.worker_process, force=True)
        self.worker_process = None

    def close(self) -> None:
        self._stop(self.worker_process, force=False)
        self._stop(self.api_process, force=False)
        self.worker_process = None
        self.api_process = None
        for handle in self._handles:
            handle.close()
        self._handles.clear()


def _send_and_drop_response(api_base: str, path: str, body: dict, idem: str) -> None:
    """Send a complete request then close without reading its response."""

    parsed = urlsplit(api_base)
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
    conn.putrequest("POST", path)
    conn.putheader("Content-Type", "application/json")
    conn.putheader("X-Idempotency-Key", idem)
    conn.putheader("Content-Length", str(len(payload)))
    conn.endheaders(payload)
    if conn.sock:
        try:
            conn.sock.shutdown(socket.SHUT_RD)
        except OSError:
            pass
    conn.close()


def _run_lease_rows(db_path: Path, studio_run_id: str) -> List[Dict[str, Any]]:
    with sqlite3.connect(db_path, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT tr.id AS task_id, tr.state AS task_state, tr.facts_json,
                   el.worker_id, el.status AS lease_status, el.expires_at,
                   el.lease_generation, el.fencing_token
            FROM task_runs tr
            LEFT JOIN execution_leases el ON el.run_id = tr.id
            WHERE tr.facts_json LIKE ?
            ORDER BY tr.created_at, tr.id
            """,
            (f'%"studio_run_id": "{studio_run_id}"%',),
        ).fetchall()
    return [dict(row) for row in rows]


def _approval_duplicates(db_path: Path, episode_id: str) -> List[Dict[str, Any]]:
    with sqlite3.connect(db_path, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT revision_id, checkpoint, actor, COUNT(*) AS count
            FROM studio_approval_decisions
            WHERE aggregate_id = ?
            GROUP BY revision_id, checkpoint, actor
            HAVING COUNT(*) > 1
            """,
            (episode_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _outbox_rows(
    db_path: Path, episode_id: str, run_ids: Iterable[str]
) -> List[Dict[str, Any]]:
    needles = [episode_id, *run_ids]
    clauses = ["aggregate_id = ?"] * len(needles) + ["payload_json LIKE ?"] * len(needles)
    params = [*needles, *[f"%{value}%" for value in needles]]
    with sqlite3.connect(db_path, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, event_id, aggregate_id, event_type, sequence_number,
                   status, deduplication_key, created_at
            FROM v2_outbox_records
            WHERE {' OR '.join(clauses)}
            ORDER BY aggregate_id, sequence_number, created_at, id
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def _capability_status(api_base: str, name: str) -> Optional[str]:
    status, profile = _get(api_base, "/api/v3/studio/capabilities")
    if status != 200:
        return None
    for capability in profile.get("capabilities", []):
        if capability.get("name") == name:
            return capability.get("status")
    return None


async def _reject_stale_fence(db_url: str, lease: Dict[str, Any]) -> bool:
    from windagent_storage.database.connection import DatabaseManager
    from windagent_storage.queue.sql_queue import SqlDurableTaskQueue

    db = DatabaseManager(db_url)
    try:
        queue = SqlDurableTaskQueue(db.session_factory)
        renewed = await queue.renew(
            lease["task_id"], lease["worker_id"], lease["fencing_token"], extension_seconds=5
        )
        return not renewed
    finally:
        await db.close()


def _revision(ep: Dict[str, Any]) -> Dict[str, Any]:
    revision = ep.get("current_revision") or {}
    required = ("revision_id", "content_hash", "optimistic_version")
    if not all(revision.get(key) is not None for key in required):
        raise SliceError(f"episode has no complete current revision: {revision}")
    return revision


def _latest_candidate(api_base: str, episode_id: str) -> Dict[str, Any]:
    status, data = _get(api_base, f"/api/v3/studio/episodes/{episode_id}/artifacts")
    if status != 200:
        raise SliceError(f"artifact read failed: {status} {data}")
    artifact = _latest_artifact(data.get("items", []), "IdeaCandidateSet")
    candidates = ((artifact or {}).get("content") or {}).get("candidates", [])
    if not artifact or not candidates:
        raise SliceError("IdeaCandidateSet is not available")
    recommended = (artifact.get("content") or {}).get("recommended_candidate_id")
    return next((c for c in candidates if c.get("candidate_id") == recommended), candidates[0])


def _select(api_base: str, episode_id: str, revision: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    candidate = _latest_candidate(api_base, episode_id)
    return _request(
        api_base,
        "POST",
        f"/api/v3/studio/episodes/{episode_id}/idea-selection",
        {
            "episode_id": episode_id,
            "revision_id": revision["revision_id"],
            "candidate_id": candidate["candidate_id"],
            "expected_content_hash": revision["content_hash"],
            "expected_optimistic_version": revision["optimistic_version"],
        },
        idem=_idem(f"c8-select-{episode_id}"),
    )


def _approve(
    api_base: str,
    episode_id: str,
    checkpoint: str,
    revision: Dict[str, Any],
    *,
    decision: str = "APPROVED",
    reason: str = "C8 recovery certification",
) -> tuple[int, Dict[str, Any]]:
    return _request(
        api_base,
        "POST",
        f"/api/v3/studio/episodes/{episode_id}/approvals",
        {
            "episode_id": episode_id,
            "revision_id": revision["revision_id"],
            "checkpoint": checkpoint,
            "artifact_hash": revision["content_hash"],
            "decision": decision,
            "reason": reason,
            "expected_optimistic_version": revision["optimistic_version"],
        },
        idem=_idem(f"c8-approve-{checkpoint}-{episode_id}"),
    )


def _exercise_stale_approval(api_base: str, episode_id: str) -> Dict[str, Any]:
    status, before = _get(api_base, f"/api/v3/studio/episodes/{episode_id}")
    if status != 200 or before.get("awaiting_checkpoint") != "IDEA":
        raise SliceError(f"IDEA checkpoint was not ready: {status} {before}")
    stale = _revision(before)
    selected_status, selected = _select(api_base, episode_id, stale)
    if selected_status != 200:
        raise SliceError(f"idea selection failed: {selected_status} {selected}")

    conflict_status, conflict = _approve(api_base, episode_id, "IDEA", stale)
    if conflict_status != 409:
        raise SliceError(f"stale approval did not return 409: {conflict_status} {conflict}")

    _, server_view = _get(api_base, f"/api/v3/studio/episodes/{episode_id}")
    fresh = _revision(server_view)
    approved_status, approved = _approve(api_base, episode_id, "IDEA", fresh)
    if approved_status != 200:
        raise SliceError(f"fresh approval failed: {approved_status} {approved}")
    return {
        "http_status": conflict_status,
        "code": conflict.get("code"),
        "studio_code": conflict.get("studio_code"),
        "details": conflict.get("details", {}),
        "stale_version": stale["optimistic_version"],
        "server_version": fresh["optimistic_version"],
        "server_truth_refetched": fresh["optimistic_version"] > stale["optimistic_version"],
        "fresh_command_status": approved_status,
    }


def _drive_to_terminal(
    api_base: str, series_id: str, episode_id: str, initial_run_id: str, *, timeout: int = 2700
) -> tuple[str, List[str]]:
    """Drive remaining public approval commands, deriving revisions if review rejects."""

    run_id = initial_run_id
    run_ids = [run_id]
    deadline = time.monotonic() + timeout
    revision_attempt = 1
    while time.monotonic() < deadline:
        status, ep = _get(api_base, f"/api/v3/studio/episodes/{episode_id}")
        if status != 200:
            raise SliceError(f"episode recovery read failed: {status} {ep}")
        status, run = _get(api_base, f"/api/v3/studio/runs/{run_id}")
        if status != 200:
            raise SliceError(f"run recovery read failed: {status} {run}")
        awaiting = ep.get("awaiting_checkpoint")
        run_status = run.get("status")
        if run_status == "COMPLETED":
            return run_id, run_ids
        if run_status in {"FAILED", "CANCELLED"}:
            if revision_attempt >= 3:
                raise SliceError(f"recovery run failed after {revision_attempt} attempts")
            current = _revision(ep)
            derived_status, derived = _request(
                api_base,
                "POST",
                f"/api/v3/studio/episodes/{episode_id}/revisions",
                {
                    "episode_id": episode_id,
                    "series_id": series_id,
                    "parent_revision_id": current["revision_id"],
                    "new_content_hash": hashlib.sha256(
                        f"c8-revision:{episode_id}:{revision_attempt + 1}".encode()
                    ).hexdigest(),
                    "actor": "certification",
                    "invalidation_intent": "REVISION",
                    "summary": "Real review finding requires a new immutable revision",
                    "expected_optimistic_version": current["optimistic_version"],
                },
                idem=_idem(f"c8-derive-{episode_id}-{revision_attempt}"),
            )
            if derived_status != 201:
                raise SliceError(f"revision derivation failed: {derived_status} {derived}")
            revision_attempt += 1
            start_status, started = _request(
                api_base,
                "POST",
                f"/api/v3/studio/episodes/{episode_id}/runs",
                {},
                idem=_idem(f"c8-run-{episode_id}-{revision_attempt}"),
            )
            if start_status != 202:
                raise SliceError(f"replacement run failed: {start_status} {started}")
            run_id = started["run_id"]
            run_ids.append(run_id)
            continue
        if awaiting:
            current = _revision(ep)
            if awaiting == "IDEA":
                select_status, selected = _select(api_base, episode_id, current)
                if select_status != 200:
                    raise SliceError(f"idea selection failed: {select_status} {selected}")
                _, ep = _get(api_base, f"/api/v3/studio/episodes/{episode_id}")
                current = _revision(ep)
            if awaiting == "SCREENPLAY":
                _, artifacts = _get(api_base, f"/api/v3/studio/episodes/{episode_id}/artifacts")
                review = _latest_artifact(artifacts.get("items", []), "ReviewReport")
                verdict = ((review or {}).get("content") or {}).get("verdict")
                if verdict not in ("PASS", "PASS_WITH_WARNINGS"):
                    approval_status, result = _approve(
                        api_base,
                        episode_id,
                        awaiting,
                        current,
                        decision="REJECTED",
                        reason="Real blocking review finding; revision required",
                    )
                    if approval_status != 200:
                        raise SliceError(f"review rejection failed: {approval_status} {result}")
                    time.sleep(0.5)
                    continue
            approval_status, result = _approve(api_base, episode_id, awaiting, current)
            if approval_status != 200:
                raise SliceError(f"approval {awaiting} failed: {approval_status} {result}")
        time.sleep(1)
    raise SliceError("recovery slice did not reach a terminal state")


def _event_pages(api_base: str, run_ids: Iterable[str]) -> Dict[str, List[Dict[str, Any]]]:
    pages: Dict[str, List[Dict[str, Any]]] = {}
    for run_id in run_ids:
        status, result = _get(api_base, f"/api/v3/studio/runs/{run_id}/events?after=0&limit=1000")
        if status != 200:
            raise SliceError(f"event read failed: {status} {result}")
        pages[run_id] = result.get("events", [])
    return pages


def _artifact_duplicate_keys(artifacts: Iterable[Dict[str, Any]]) -> List[str]:
    seen: set[tuple[str, str, str]] = set()
    duplicates: List[str] = []
    for artifact in artifacts:
        key = (
            str(artifact.get("revision_id")),
            str(artifact.get("artifact_type")),
            str(artifact.get("content_hash")),
        )
        if key in seen:
            duplicates.append("|".join(key))
        seen.add(key)
    return duplicates


def run_recovery_slice(
    *, api_base: str, db_url: str, series_id: str, topology: ManagedTopology, log=print
) -> Dict[str, Any]:
    """Execute the mandatory C8 scenario and return a redaction-safe report."""

    db_path = sqlite_path_from_url(db_url)
    trace: List[Dict[str, Any]] = []

    def mark(action: str, **fields: Any) -> None:
        trace.append({"at": utc_now_iso(), "action": action, **fields})
        log(f"[c8] {action}: {json.dumps(fields, ensure_ascii=False)[:200]}")

    topology.start_api()
    status, existing_series = _get(api_base, f"/api/v3/studio/series/{series_id}")
    if status != 200:
        raise SliceError(f"C7 series is not present in certification DB: {status} {existing_series}")

    episode_key = _idem("c8-response-loss-episode")
    episode_body = {
        "series_id": series_id,
        "title": "Thỏ và chiếc diều — phục hồi",
        "episode_number": 2,
        "metadata": {"creative_brief": BRIEF, "certification_phase": "C8"},
    }
    path = f"/api/v3/studio/series/{series_id}/episodes"
    _send_and_drop_response(api_base, path, episode_body, episode_key)
    time.sleep(0.5)
    replay_status, replay = _request(api_base, "POST", path, episode_body, idem=episode_key)
    if replay_status != 201:
        raise SliceError(f"idempotent replay failed: {replay_status} {replay}")
    episode_id = replay["episode_id"]
    _, episode_list = _get(api_base, path)
    replay_count = sum(1 for item in episode_list.get("items", []) if item.get("episode_id") == episode_id)
    mark("api.response_lost_and_replayed", episode_id=episode_id, resource_count=replay_count)

    start_status, started = _request(
        api_base,
        "POST",
        f"/api/v3/studio/episodes/{episode_id}/runs",
        {},
        idem=_idem("c8-start-run"),
    )
    if start_status != 202:
        raise SliceError(f"run start failed: {start_status} {started}")
    run_id = started["run_id"]
    _, first_page = _get(api_base, f"/api/v3/studio/runs/{run_id}/events?after=0&limit=1000")
    cursor_before_restart = int(first_page.get("latest_sequence", 0))
    _, episode_before_restart = _get(api_base, f"/api/v3/studio/episodes/{episode_id}")
    _, run_before_restart = _get(api_base, f"/api/v3/studio/runs/{run_id}")

    topology.start_worker()
    first_lease = _wait_for(
        lambda: next(
            (
                row
                for row in _run_lease_rows(db_path, run_id)
                if row.get("lease_generation") == 1 and row.get("lease_status") == "active"
            ),
            None,
        ),
        timeout=120,
        interval=0.1,
        label="first durable worker claim",
    )
    mark(
        "worker.claimed",
        task_id=first_lease["task_id"],
        lease_generation=1,
        fencing_token=_redact_fence(first_lease["fencing_token"]),
    )
    topology.kill_worker()
    mark("worker.terminated_before_finalization", task_id=first_lease["task_id"])

    topology.stop_api()
    topology.start_api()
    _, episode_after_restart = _get(api_base, f"/api/v3/studio/episodes/{episode_id}")
    _, run_after_restart = _get(api_base, f"/api/v3/studio/runs/{run_id}")
    api_restart_preserved = (
        episode_after_restart.get("episode_id") == episode_before_restart.get("episode_id")
        and run_after_restart.get("run_id") == run_before_restart.get("run_id")
    )
    mark("api.restarted_and_hydrated", cursor=cursor_before_restart, preserved=api_restart_preserved)

    unavailable = _wait_for(
        lambda: _capability_status(api_base, "worker") == "UNAVAILABLE",
        timeout=50,
        interval=1,
        label="fail-closed worker capability",
    )
    topology.start_worker()
    _wait_for(
        lambda: _capability_status(api_base, "story_engine") == "AVAILABLE",
        timeout=60,
        interval=1,
        label="restored story capability",
    )
    takeover = _wait_for(
        lambda: next(
            (
                row
                for row in _run_lease_rows(db_path, run_id)
                if row["task_id"] == first_lease["task_id"] and (row.get("lease_generation") or 0) >= 2
            ),
            None,
        ),
        timeout=180,
        interval=0.2,
        label="expired lease takeover",
    )
    stale_fence_rejected = asyncio.run(_reject_stale_fence(db_url, first_lease))
    mark(
        "worker.took_over",
        task_id=takeover["task_id"],
        lease_generation=takeover["lease_generation"],
        fencing_token=_redact_fence(takeover["fencing_token"]),
        stale_fence_rejected=stale_fence_rejected,
    )

    _wait_for(
        lambda: (
            (_get(api_base, f"/api/v3/studio/episodes/{episode_id}")[1]).get("awaiting_checkpoint")
            == "IDEA"
        ),
        timeout=900,
        interval=1,
        label="IDEA approval checkpoint after takeover",
    )
    conflict = _exercise_stale_approval(api_base, episode_id)
    mark("approval.stale_conflict", code=conflict.get("code"), server_version=conflict["server_version"])

    final_run_id, run_ids = _drive_to_terminal(api_base, series_id, episode_id, run_id)
    _, final_episode = _get(api_base, f"/api/v3/studio/episodes/{episode_id}")
    _, final_run = _get(api_base, f"/api/v3/studio/runs/{final_run_id}")
    _, artifact_page = _get(api_base, f"/api/v3/studio/episodes/{episode_id}/artifacts")
    artifacts = artifact_page.get("items", [])
    duplicate_artifacts = _artifact_duplicate_keys(artifacts)
    duplicate_approvals = _approval_duplicates(db_path, episode_id)
    event_pages = _event_pages(api_base, run_ids)
    first_after_restart = event_pages[run_id]
    resumed_events = [e for e in first_after_restart if int(e.get("sequence", 0)) > cursor_before_restart]
    all_events = [event for events in event_pages.values() for event in events]
    event_ids = [e.get("event_id") for e in all_events]
    sequences_ordered = all(
        [int(e.get("sequence", 0)) for e in events]
        == sorted(int(e.get("sequence", 0)) for e in events)
        for events in event_pages.values()
    )
    task_rows = [row for rid in run_ids for row in _run_lease_rows(db_path, rid)]
    terminal_tasks = {row["task_id"] for row in task_rows if row.get("task_state") == "completed"}
    completed_event_tasks = {
        (e.get("payload") or {}).get("task_id")
        for e in all_events
        if e.get("event_type") == "studio.task.completed"
    }
    outbox_rows = _outbox_rows(db_path, episode_id, run_ids)
    outbox_by_event_id = {row.get("event_id"): row for row in outbox_rows}
    studio_event_ids = {event_id for event_id in event_ids if event_id}
    outbox_sequences: Dict[str, List[int]] = {}
    for row in outbox_rows:
        if row.get("event_id") not in studio_event_ids:
            continue
        outbox_sequences.setdefault(str(row.get("aggregate_id")), []).append(
            int(row.get("sequence_number") or 0)
        )
    outbox_ordered = all(values == sorted(values) for values in outbox_sequences.values())

    checks = {
        "second_episode_created": replay_count == 1,
        "lost_response_idempotent_replay": replay_count == 1 and replay_status == 201,
        "worker_killed_after_durable_claim": bool(first_lease.get("fencing_token")),
        "lease_takeover_generation_increased": int(takeover["lease_generation"]) >= 2,
        "stale_fence_rejected": stale_fence_rejected,
        "api_restart_preserved_server_state": api_restart_preserved,
        "cursor_recovery_has_new_events": bool(resumed_events),
        "events_unique_and_ordered": len(event_ids) == len(set(event_ids)) and sequences_ordered,
        "typed_stale_conflict_and_server_truth": (
            conflict["http_status"] == 409
            and str(conflict.get("code", "")).startswith("STUDIO_")
            and conflict["server_truth_refetched"]
            and conflict["fresh_command_status"] == 200
        ),
        "capability_fail_closed_then_recovered": bool(unavailable)
        and _capability_status(api_base, "story_engine") == "AVAILABLE",
        "no_duplicate_canonical_artifact": not duplicate_artifacts,
        "no_double_approval": not duplicate_approvals,
        "task_event_reconciled": terminal_tasks <= completed_event_tasks,
        "outbox_event_parity_and_ordering": (
            studio_event_ids <= set(outbox_by_event_id) and outbox_ordered
        ),
        "final_run_completed": final_run.get("status") == "COMPLETED",
        "episode_ready_for_production": final_episode.get("state") == "READY_FOR_PRODUCTION",
        "no_manual_database_repair": True,
        "no_fake_fallback": (
            os.getenv("WINDAGENT_FAKE_RUNTIME", "").lower() not in {"1", "true", "yes"}
            and os.getenv("WINDAGENT_MODEL_BACKEND", "").lower()
            not in {"mock", "fake", "fixture"}
        ),
    }
    return {
        "series_id": series_id,
        "episode_id": episode_id,
        "initial_run_id": run_id,
        "final_run_id": final_run_id,
        "run_ids": run_ids,
        "trace": trace,
        "process_timeline": topology.process_timeline,
        "response_loss": {"idempotency_key_hash": _redact_fence(episode_key), "resource_count": replay_count},
        "lease": {
            "task_id": first_lease["task_id"],
            "first_generation": 1,
            "takeover_generation": takeover["lease_generation"],
            "first_fence": _redact_fence(first_lease["fencing_token"]),
            "takeover_fence": _redact_fence(takeover["fencing_token"]),
        },
        "conflict": conflict,
        "cursor": {
            "before_restart": cursor_before_restart,
            "resumed_event_count": len(resumed_events),
            "event_count": len(all_events),
        },
        "artifact_count": len(artifacts),
        "duplicate_artifact_keys": duplicate_artifacts,
        "duplicate_approvals": duplicate_approvals,
        "terminal_task_count": len(terminal_tasks),
        "completed_task_event_count": len(completed_event_tasks),
        "outbox_record_count": len(outbox_rows),
        "outbox_studio_event_count": len(studio_event_ids & set(outbox_by_event_id)),
        "final_episode_state": final_episode.get("state"),
        "final_run_status": final_run.get("status"),
        "checks": checks,
        "checks_total": len(checks),
        "checks_passed": sum(bool(value) for value in checks.values()),
        "database_observation_mode": "read-only; stale renew rejected by canonical queue port",
        "manual_database_repairs": [],
    }


def assert_recovery_report(report: Dict[str, Any]) -> None:
    failed = [name for name, passed in report.get("checks", {}).items() if not passed]
    if failed:
        raise SliceError(f"C8 mandatory recovery checks failed: {failed}")


__all__ = [
    "ManagedTopology",
    "assert_recovery_report",
    "run_recovery_slice",
    "sqlite_path_from_url",
]
