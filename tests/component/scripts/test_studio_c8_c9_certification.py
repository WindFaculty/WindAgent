from __future__ import annotations

import io
import json
import sys
import time

import pytest

from scripts.studio_roadmap import c7_desktop_evidence, c7_slice_harness
from tests.support.waiting import deterministic_sleep

from scripts.studio_roadmap.c7_slice_harness import (
    MODEL_PROVENANCE_FIELDS,
    SliceError,
    _correlation_checks,
    _genuine_revision_checks,
    assert_report,
)
from scripts.studio_roadmap.c8_recovery_harness import (
    _artifact_duplicate_keys,
    assert_recovery_report,
    sqlite_path_from_url,
)
from scripts.studio_roadmap.certification_launcher import (
    CertificationLauncher,
    CertificationProcessError,
    configure_utf8_stdio,
    prepare_certification_database,
    sanitize_environment,
)
from scripts.studio_roadmap.produce_c9_evidence import evidence_sha, evidence_verdict
from windagent_core.domain.story.ideation.models import CreativeBrief
from scripts.studio_roadmap.produce_c7_evidence import (
    _blocked_evidence as c7_blocked_evidence,
    _redact_secrets as c7_redact_secrets,
    _redaction_safe as c7_redaction_safe,
    _source_dirty_paths as c7_source_dirty,
)
from scripts.studio_roadmap.produce_c8_evidence import _source_dirty_paths as c8_source_dirty
from scripts.studio_roadmap.produce_c9_evidence import _source_dirty_paths as c9_source_dirty


def test_c8_sqlite_path_is_resolved_inside_repository() -> None:
    path = sqlite_path_from_url("sqlite+aiosqlite:///certification.db")
    assert path.is_absolute()
    assert path.name == "certification.db"


def test_certification_database_parent_is_prepared_without_creating_db(tmp_path) -> None:
    db_path = tmp_path / "fresh-namespace" / "certification.db"

    observed = prepare_certification_database(
        f"sqlite+aiosqlite:///{db_path.as_posix()}"
    )

    assert observed == db_path.resolve()
    assert db_path.parent.is_dir()
    assert not db_path.exists()


def test_c8_duplicate_artifact_detection_is_revision_scoped() -> None:
    artifacts = [
        {"revision_id": "rev_1", "artifact_type": "ScreenplayDraft", "content_hash": "a"},
        {"revision_id": "rev_2", "artifact_type": "ScreenplayDraft", "content_hash": "a"},
        {"revision_id": "rev_1", "artifact_type": "ScreenplayDraft", "content_hash": "a"},
    ]
    assert _artifact_duplicate_keys(artifacts) == ["rev_1|ScreenplayDraft|a"]


def test_c8_gate_assertion_fails_closed() -> None:
    with pytest.raises(SliceError, match="stale_fence_rejected"):
        assert_recovery_report(
            {"checks": {"lease_takeover_generation_increased": True, "stale_fence_rejected": False}}
        )


def test_c9_reads_json_gate_and_integration_sha(tmp_path) -> None:
    path = tmp_path / "evidence.json"
    path.write_text(
        json.dumps(
            {
                "gate": "REAL_VERTICAL_SLICE_GATE",
                "verdict": "PASS",
                "contract": "studio.contract/v0.1",
                "redaction_safe": True,
                "versions": {"integration_sha": "abc123"},
            }
        ),
        encoding="utf-8",
    )
    observed = evidence_verdict(path, "REAL_VERTICAL_SLICE_GATE")
    assert observed["result"] == "PASS"
    assert observed["source_sha"] == "abc123"
    assert evidence_sha(json.loads(path.read_text(encoding="utf-8"))) == "abc123"


def test_c9_rejects_gate_mismatch_even_when_json_says_pass(tmp_path) -> None:
    path = tmp_path / "mixed.json"
    path.write_text(
        json.dumps(
            {
                "gate": "RECOVERY_VERTICAL_SLICE_GATE",
                "verdict": "PASS",
                "integration_sha": "abc123",
            }
        ),
        encoding="utf-8",
    )
    observed = evidence_verdict(path, "REAL_VERTICAL_SLICE_GATE")
    assert observed["result"] == "FAIL"
    assert observed["reason"].startswith("gate_mismatch")


def test_c9_rejects_unredacted_real_slice(tmp_path) -> None:
    path = tmp_path / "unredacted.json"
    path.write_text(
        json.dumps(
            {
                "gate": "RECOVERY_VERTICAL_SLICE_GATE",
                "verdict": "PASS",
                "contract": "studio.contract/v0.1",
                "integration_sha": "abc123",
                "redaction_safe": False,
            }
        ),
        encoding="utf-8",
    )
    assert evidence_verdict(path, "RECOVERY_VERTICAL_SLICE_GATE")["result"] == "FAIL"


def test_c9_markdown_requires_gate_and_pass_on_same_line(tmp_path) -> None:
    path = tmp_path / "gate.md"
    path.write_text("**`IDEA_GATE`: PASS.**\n", encoding="utf-8")
    assert evidence_verdict(path, "IDEA_GATE")["result"] == "PASS"
    assert evidence_verdict(path, "OUTLINE_GATE")["result"] == "FAIL"


def test_certification_reports_do_not_make_the_source_tree_dirty() -> None:
    paths = [
        "artifacts/studio_roadmap_01/c7/evidence.json",
        "artifacts/studio_roadmap_01/c8/evidence.json",
        "artifacts/studio_roadmap_01/c9/evidence.json",
        "apps/api/windagent_api/main.py",
    ]
    assert c7_source_dirty(paths) == [
        "artifacts/studio_roadmap_01/c8/evidence.json",
        "artifacts/studio_roadmap_01/c9/evidence.json",
        "apps/api/windagent_api/main.py",
    ]
    assert c8_source_dirty(paths) == [
        "artifacts/studio_roadmap_01/c9/evidence.json",
        "apps/api/windagent_api/main.py",
    ]
    assert c9_source_dirty(paths) == ["apps/api/windagent_api/main.py"]


def test_certification_environment_manifest_is_redaction_safe() -> None:
    manifest = sanitize_environment(
        {
            "WINDAGENT_DATABASE_URL": "postgresql://user:***@db.local/wind?token=secret",
            "WINDAGENT_CERTIFICATION_MODE": "1",
            "UNRELATED_API_KEY": "must-not-appear",
        }
    )

    assert manifest == {
        "WINDAGENT_DATABASE_URL": "postgresql://db.local/wind",
        "WINDAGENT_CERTIFICATION_MODE": "1",
    }


def test_certification_manifest_redacts_google_api_key() -> None:
    manifest = sanitize_environment(
        {
            "GOOGLE_API_KEY": "AIzaSy-sentinel-key-value",
            "WINDAGENT_STUDIO_PROVIDER_VENDOR": "google",
        }
    )

    assert manifest["GOOGLE_API_KEY"] == "<redacted>"
    assert "AIzaSy" not in json.dumps(manifest)
    assert manifest["WINDAGENT_STUDIO_PROVIDER_VENDOR"] == "google"


def test_sanitize_url_removes_postgres_credentials() -> None:
    url = "postgresql://test-user:test-password-sentinel@db.local/wind?token=test-token-sentinel"
    manifest = sanitize_environment({"WINDAGENT_DATABASE_URL": url})

    assert manifest["WINDAGENT_DATABASE_URL"] == "postgresql://db.local/wind"
    assert "test-password-sentinel" not in manifest["WINDAGENT_DATABASE_URL"]
    assert "test-token-sentinel" not in manifest["WINDAGENT_DATABASE_URL"]


def test_sanitize_url_removes_postgres_query() -> None:
    manifest = sanitize_environment(
        {"WINDAGENT_DATABASE_URL": "postgresql://db.local/wind?sslmode=require&token=test-token-sentinel"}
    )

    assert manifest["WINDAGENT_DATABASE_URL"] == "postgresql://db.local/wind"


def test_sanitize_url_removes_postgres_fragment_and_keeps_port() -> None:
    manifest = sanitize_environment(
        {"WINDAGENT_DATABASE_URL": "postgresql://db.local:5433/wind#frag-sentinel"}
    )

    assert manifest["WINDAGENT_DATABASE_URL"] == "postgresql://db.local:5433/wind"


def test_certification_sqlite_url_keeps_triple_slash_after_sanitize() -> None:
    manifest = sanitize_environment(
        {
            "WINDAGENT_DATABASE_URL": (
                "sqlite+aiosqlite:///D:/repo/.tmp/studio-c7/candidate-x.db"
            ),
            "WINDAGENT_CERTIFICATION_MODE": "1",
        }
    )

    assert manifest["WINDAGENT_DATABASE_URL"] == (
        "sqlite+aiosqlite:///D:/repo/.tmp/studio-c7/candidate-x.db"
    )


def test_sanitize_url_removes_sqlite_query() -> None:
    manifest = sanitize_environment(
        {"WINDAGENT_DATABASE_URL": "sqlite+aiosqlite:///D:/repo/cert.db?token=test-token-sentinel"}
    )

    assert manifest["WINDAGENT_DATABASE_URL"] == "sqlite+aiosqlite:///D:/repo/cert.db"
    assert "test-token-sentinel" not in manifest["WINDAGENT_DATABASE_URL"]


def test_sanitize_url_removes_sqlite_fragment() -> None:
    manifest = sanitize_environment(
        {"WINDAGENT_DATABASE_URL": "sqlite+aiosqlite:///D:/repo/cert.db#frag-sentinel"}
    )

    assert manifest["WINDAGENT_DATABASE_URL"] == "sqlite+aiosqlite:///D:/repo/cert.db"


def test_sanitize_url_removes_sqlite_userinfo_and_keeps_triple_slash() -> None:
    manifest = sanitize_environment(
        {"WINDAGENT_DATABASE_URL": "sqlite+aiosqlite://test-user:test-password-sentinel@/D:/repo/cert.db"}
    )

    assert manifest["WINDAGENT_DATABASE_URL"] == "sqlite+aiosqlite:///D:/repo/cert.db"
    assert "test-password-sentinel" not in manifest["WINDAGENT_DATABASE_URL"]


def test_sanitize_url_fails_closed_on_invalid_url() -> None:
    manifest = sanitize_environment(
        {"WINDAGENT_DATABASE_URL": "postgresql://test-user:test-password-sentinel@[broken"}
    )

    assert manifest["WINDAGENT_DATABASE_URL"] == "<redacted-invalid-url>"
    assert "test-password-sentinel" not in manifest["WINDAGENT_DATABASE_URL"]


def test_sanitize_url_leaves_non_url_values_untouched() -> None:
    manifest = sanitize_environment({"WINDAGENT_CERTIFICATION_MODE": "1"})

    assert manifest["WINDAGENT_CERTIFICATION_MODE"] == "1"


def test_certification_console_streams_are_forced_to_utf8() -> None:
    stdout_bytes = io.BytesIO()
    stderr_bytes = io.BytesIO()
    stdout = io.TextIOWrapper(stdout_bytes, encoding="cp1252")
    stderr = io.TextIOWrapper(stderr_bytes, encoding="cp1252")

    configure_utf8_stdio(stdout, stderr)
    stdout.write("đề")
    stderr.write("thỏ")
    stdout.flush()
    stderr.flush()

    assert stdout_bytes.getvalue().decode("utf-8") == "đề"
    assert stderr_bytes.getvalue().decode("utf-8") == "thỏ"


def test_c7_failure_details_are_redacted_before_persistence() -> None:
    payload = {
        "first_broken_hop": {
            "detail": "provider failed with Authorization='super-secret-value'",
        }
    }

    redacted = c7_redact_secrets(payload)

    assert redacted["first_broken_hop"]["detail"] == "provider failed with [REDACTED]"
    assert c7_redaction_safe(redacted) is True


def test_c7_pre_series_failure_is_blocked_with_first_broken_hop() -> None:
    evidence = c7_blocked_evidence(
        {"checks": {}},
        stage="runtime.seed",
        failure=RuntimeError("database unavailable"),
    )

    assert evidence["verdict"] == "BLOCKED"
    assert evidence["first_broken_hop"] == {
        "stage": "runtime.seed",
        "failure": "RuntimeError",
        "detail": "database unavailable",
    }
    assert evidence["redaction_safe"] is True


def test_c7_desktop_toolchain_is_probed_before_slice(monkeypatch) -> None:
    monkeypatch.setattr(c7_desktop_evidence.sys, "platform", "win32")
    monkeypatch.setattr(
        c7_desktop_evidence,
        "_version",
        lambda command: f"available:{command[0]}",
    )

    observed = c7_desktop_evidence.probe_c7_desktop_environment()

    assert observed == {
        "node": "available:node",
        "npm": "available:npm.cmd",
        "cargo": "available:cargo",
        "rustc": "available:rustc",
        "tauri_cli": "available:npm.cmd",
    }


def test_launcher_records_unexpected_exit_as_first_broken_hop(tmp_path, monkeypatch) -> None:
    launcher = CertificationLauncher(
        db_url="sqlite+aiosqlite:///cert.db",
        log_dir=tmp_path,
        poll_interval=0.01,
    )
    monkeypatch.setattr(
        launcher,
        "_command",
        lambda _name: [sys.executable, "-c", "import sys; sys.stderr.write('boom\\n'); sys.exit(7)"],
    )

    launcher.start("worker")
    deadline = time.monotonic() + 2
    error = None
    while time.monotonic() < deadline:
        try:
            launcher.raise_if_unhealthy()
        except CertificationProcessError as exc:
            error = exc
            break
        deterministic_sleep(0.01)
    launcher.stop_all()

    assert error is not None
    assert error.first_broken_hop["failure"] == "process_exited"
    assert error.first_broken_hop["exit_code"] == 7
    receipt = json.loads((tmp_path / "process-receipts.json").read_text(encoding="utf-8"))
    assert receipt["first_broken_hop"]["process"] == "worker"
    assert receipt["processes"][0]["unexpected_exit"] is True
    assert receipt["processes"][0]["stderr_tail"] == ["boom"]


def test_c7_logical_operation_uses_stable_idempotency_key() -> None:
    assert c7_slice_harness._idem("approve-ep-rev-IDEA") == c7_slice_harness._idem(
        "approve-ep-rev-IDEA"
    )


def test_c7_certification_brief_is_a_complete_canonical_brief() -> None:
    brief = CreativeBrief.model_validate(c7_slice_harness.BRIEF)

    assert str(brief.brief_id) == "br_c7_rabbit_kite"
    assert brief.title == "Thỏ và chiếc diều"


def test_launcher_guard_is_injected_into_long_running_operation(tmp_path) -> None:
    launcher = CertificationLauncher(
        db_url="sqlite+aiosqlite:///cert.db",
        log_dir=tmp_path,
    )

    def operation(health_check):
        launcher._unexpected = {"process": "worker", "failure": "process_exited"}
        health_check()

    with pytest.raises(CertificationProcessError, match="first broken process hop"):
        launcher.run_guarded(operation)


def test_c7_approval_retry_reuses_key_and_never_swallows_409(monkeypatch) -> None:
    observed_keys = []

    def conflict(_api, _method, _path, _body, idem):
        observed_keys.append(idem)
        return 409, {"studio_code": "STALE_REVISION"}

    monkeypatch.setattr(c7_slice_harness, "_request", conflict)
    arguments = (
        "http://api",
        "ep-1",
        "rev-1",
        "a" * 64,
        2,
        "IDEA",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(SliceError, match="approval at IDEA failed: 409"):
        c7_slice_harness._approve(*arguments)
    with pytest.raises(SliceError, match="approval at IDEA failed: 409"):
        c7_slice_harness._approve(*arguments)

    assert observed_keys[0] == observed_keys[1]


def _c7_genuine_report() -> dict:
    return {
        "checks": {},
        "current_revision_id": "rev_new",
        "artifacts": [],
        "durable_evidence": {
            "revisions": [
                {
                    "revision_id": "rev_seed",
                    "parent_revision_id": None,
                    "content_hash": "0" * 64,
                    "metadata": {},
                }
            ],
            "events": [],
            "approvals": [],
        },
    }


def test_c7_initial_revision_alone_fails_genuine_revision_requirement() -> None:
    report = _c7_genuine_report()
    _genuine_revision_checks(report)
    assert report["checks"]["canonical_derived_revision_chain"]["pass"] is False


def test_c7_warning_does_not_count_as_revision_causing_finding() -> None:
    report = _c7_genuine_report()
    report["artifacts"] = [
        {
            "artifact_id": "art_report",
            "artifact_type": "ReviewReport",
            "created_at": "2026-01-01T00:00:00Z",
            "content": {
                "report_id": "report_1",
                "draft_id": "draft_1",
                "verdict": "PASS_WITH_WARNINGS",
                "findings": [
                    {
                        "code": "QUALITY_NOTE",
                        "severity": "WARNING",
                        "source": "model",
                    }
                ],
            },
        },
        {
            "artifact_id": "art_proposal",
            "artifact_type": "RevisionProposal",
            "created_at": "2026-01-01T00:00:01Z",
            "content": {
                "proposal_id": "proposal_1",
                "draft_id": "draft_1",
                "review_report_id": "report_1",
                "accepted_finding_codes": ["QUALITY_NOTE"],
            },
        },
    ]
    _genuine_revision_checks(report)
    assert report["checks"]["genuine_blocking_policy_finding"]["pass"] is False


def _c7_correlation_report() -> dict:
    artifacts = []
    nodes = []
    tasks = []
    leases = []
    attempts = []
    public_events = []
    for index in range(9):
        task_id = f"stsk_{index}"
        node_id = f"node.{index}"
        artifact_id = f"art_{index}"
        provenance = {field: f"{field}_{index}" for field in MODEL_PROVENANCE_FIELDS}
        provenance.update(
            {
                "model_id": provenance["provider_model_id"],
                "artifact_id": artifact_id,
                "artifact_type": "ReviewReport",
                "content_hash": f"{index + 1:064x}",
                "content": {},
            }
        )
        artifacts.append(provenance)
        nodes.append(
            {
                "run_id": "run_1",
                "dag_node_id": node_id,
                "task_type": "studio.story.review",
                "status": "SUCCEEDED",
                "task_id": task_id,
                "attempt": 1,
                "output_artifact_refs": [
                    {
                        "artifact_id": artifact_id,
                        "content_hash": provenance["content_hash"],
                    }
                ],
            }
        )
        tasks.append(
            {
                "task_id": task_id,
                "facts": {
                    "studio_run_id": "run_1",
                    "dag_node_id": node_id,
                    "attempt": 1,
                },
            }
        )
        leases.append(
            {
                "task_id": task_id,
                "dag_node_id": node_id,
                "lease_generation": 1,
                "fencing_token_digest": f"sha256:{index:016x}",
            }
        )
        attempts.append(
            {
                "provider_attempt_id": provenance["provider_attempt_id"],
                "task_id": task_id,
                "route_lock_id": provenance["model_route_id"],
                "provider_binding_id": provenance["provider_binding_id"],
                "status": "success",
            }
        )
        public_events.append(
            {"event_type": "studio.task.completed", "payload": {"task_id": task_id}}
        )
    event = {
        "event_id": "evt_1",
        "event_type": "studio.run.completed",
        "aggregate_id": "run_1",
        "sequence": 1,
        "studio_run_id": "run_1",
    }
    return {
        "checks": {},
        "run_id": "run_1",
        "artifacts": artifacts,
        "public_events": public_events,
        "durable_evidence": {
            "nodes": nodes,
            "tasks": tasks,
            "leases": leases,
            "provider_attempts": attempts,
            "events": [event],
            "outbox": [
                {
                    "event_id": "evt_1",
                    "event_type": event["event_type"],
                    "aggregate_id": event["aggregate_id"],
                    "sequence_number": 1,
                }
            ],
        },
    }


def test_c7_missing_model_id_fails_provider_provenance() -> None:
    report = _c7_correlation_report()
    report["artifacts"][0]["model_id"] = None
    _correlation_checks(report)
    assert report["checks"]["model_stage_provider_attempt_correlation"]["pass"] is False


def test_c7_missing_provider_attempt_fails_correlation() -> None:
    report = _c7_correlation_report()
    report["durable_evidence"]["provider_attempts"] = []
    _correlation_checks(report)
    assert report["checks"]["model_stage_provider_attempt_correlation"]["pass"] is False


def test_c7_broken_task_correlation_fails() -> None:
    report = _c7_correlation_report()
    report["durable_evidence"]["tasks"][0]["facts"]["studio_run_id"] = "run_other"
    _correlation_checks(report)
    assert report["checks"]["dag_node_task_correlation"]["pass"] is False


def test_c7_missing_lease_and_outbox_fail() -> None:
    report = _c7_correlation_report()
    report["durable_evidence"]["leases"] = []
    report["durable_evidence"]["outbox"] = []
    _correlation_checks(report)
    assert report["checks"]["task_claim_lease_fence_correlation"]["pass"] is False
    assert (
        report["checks"]["outbox_domain_event_correlation_and_ordering"]["pass"]
        is False
    )


def test_c7_redaction_failure_is_never_accepted() -> None:
    report = _c7_correlation_report()
    report.update(
        {
            "artifacts": [],
            "durable_evidence": {
                **report["durable_evidence"],
                "revisions": [],
                "approvals": [],
            },
            "current_revision_id": None,
            "episode_state": "READY_FOR_PRODUCTION",
            "run_status": "COMPLETED",
            "redaction_safe": False,
        }
    )
    with pytest.raises(SliceError, match="redaction_safe"):
        assert_report(report)