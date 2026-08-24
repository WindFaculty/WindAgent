"""Unit tests for the Live Record privacy scan (Section 23/33)."""

from __future__ import annotations

from windagent_core.domain.live_record.privacy_scan import (
    mask_secret,
    scan_live_record_plan,
)


def _plan(
    payload_bundles=None,
    scenes=(),
    actions=(),
    extra_secret_values=None,
):
    return scan_live_record_plan(
        payload_bundles=payload_bundles or {},
        scenes=scenes,
        actions=actions,
        extra_secret_values=extra_secret_values,
    )


class _Action:
    def __init__(self, action_id="a1", target_file=None, command_ref=None, browser_semantic_target=None):
        self.action_id = action_id
        self.target_file = target_file
        self.command_ref = command_ref
        self.browser_semantic_target = browser_semantic_target


class _Scene:
    def __init__(self, scene_id="sc_1", title="", narration_text=None):
        self.scene_id = scene_id
        self.title = title
        self.narration_text = narration_text


def test_clean_plan_passes():
    report = _plan(
        payload_bundles={"a1": "print('hello world')\n"},
        scenes=[_Scene(title="Build Agent Core", narration_text="Trong video này chúng ta xây agent.")],
        actions=[_Action(target_file="src/agent.py")],
    )
    assert report.ok is True
    assert report.status == "PASS"
    assert report.scanned_locations >= 3


def test_detects_google_api_key_in_payload():
    report = _plan(payload_bundles={"a1": 'key = "AIzaSyA1234567890abcdefghijklmnopqrstu"\n'})
    assert report.ok is False
    assert report.findings[0].kind == "google_api_key"
    assert report.findings[0].location == "payload_bundles[a1]"


def test_detects_private_key_block_and_jwt():
    report = _plan(
        payload_bundles={
            "pem": "-----BEGIN RSA PRIVATE KEY-----\nabc\n",
            "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
        }
    )
    kinds = {f.kind for f in report.findings}
    assert "private_key_block" in kinds
    assert "jwt" in kinds


def test_exact_match_configured_credential_blocks():
    report = _plan(
        payload_bundles={"a1": "TOKEN = my-live-provider-secret-value\n"},
        extra_secret_values=["my-live-provider-secret-value"],
    )
    assert report.ok is False
    assert any(f.kind == "configured_credential" for f in report.findings)


def test_short_extra_values_are_ignored_to_avoid_false_positives():
    report = _plan(payload_bundles={"a1": "print('ok')"}, extra_secret_values=["ab", ""])
    assert report.ok is True


def test_findings_are_masked():
    raw = "ghp_AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHH"
    report = _plan(payload_bundles={"a1": f"token = {raw}"})
    assert report.ok is False
    previews = [f.masked_preview for f in report.findings]
    assert previews  # at least one finding
    assert all(raw not in p for p in previews)
    assert all(p == "***" or "chars" in p for p in previews)


def test_mask_secret_keeps_only_prefix_and_length():
    masked = mask_secret("supersecretvalue")
    assert masked.startswith("supe")
    assert "16 chars" in masked
    assert "retvalue" not in masked
    assert mask_secret("abc") == "***"
