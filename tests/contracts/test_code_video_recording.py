"""
Phase 9 Contract and Unit Test Suite: Master Video 02 Recording Pipeline.

Verifies:
1. PassCatalog 16 passes semantic integrity, scene mapping, duration, and frame precision.
2. SecretScanner strict leak detection for live tokens and safe whitelisting of placeholders.
3. Video02RecordingEngine execution across all 16 passes with deterministic tri-hashes.
4. Terminal command authenticity verification against preflight golden receipts.
5. RecordingVerifier gate certification compliance (CV02_P9_RECORDING_VERIFIED).
6. Manifest export, serialization, and disk round-trip verification.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from typing import Any, Dict, List

from windagent_core.errors.exceptions import NotFoundError, ValidationError
from windagent_tools.code_video.recording import (
    PassCatalog,
    PassDefinition,
    PassRecord,
    PassStatus,
    PassType,
    RecordingManifest,
    RecordingVerificationReport,
    RecordingVerifier,
    SecretExposureMatch,
    SecretPattern,
    SecretScanResult,
    SecretScanner,
    Video02RecordingEngine,
)
from windagent_tools.code_video.renderer import GraphicsCatalog


class TestPassCatalog:
    """Tests for PassCatalog and PassDefinition contracts."""

    def test_pass_catalog_count_and_numbering(self) -> None:
        passes = PassCatalog.get_all_passes()
        assert len(passes) == 16, f"Expected 16 passes, got {len(passes)}"

        numbers = [p.pass_number for p in passes]
        assert numbers == list(range(1, 17)), "Pass numbers must be sequential from 1 to 16"

    def test_pass_duration_and_frame_counts(self) -> None:
        passes = PassCatalog.get_all_passes()
        for p in passes:
            assert p.duration_ms > 0
            assert p.duration_ms == p.end_ms - p.start_ms
            assert p.frame_count == (p.duration_ms * 30) // 1000

    def test_pass_required_graphics_exist(self) -> None:
        graphics_catalog = GraphicsCatalog.build_default_video_02_catalog()
        passes = PassCatalog.get_all_passes()

        for p in passes:
            for g_id in p.required_graphics:
                asset = graphics_catalog.get_asset(g_id)
                assert asset is not None, f"Required graphic {g_id} in {p.pass_id} not found in GraphicsCatalog"

    def test_pass_lookup_and_not_found(self) -> None:
        p1 = PassCatalog.get_pass("PASS_01_COLD_OPEN")
        assert p1.pass_number == 1
        assert p1.scene_id == "S01"

        with pytest.raises(NotFoundError):
            PassCatalog.get_pass("INVALID_PASS_ID")

    def test_pass_by_scene_lookup(self) -> None:
        p7 = PassCatalog.get_pass_by_scene("S10")
        assert p7 is not None
        assert p7.pass_id == "PASS_07_AGENT_CORE"

        none_pass = PassCatalog.get_pass_by_scene("S99_NON_EXISTENT")
        assert none_pass is None

    def test_pass_semantic_hash_determinism(self) -> None:
        p1 = PassCatalog.get_pass("PASS_01_COLD_OPEN")
        hash1 = p1.semantic_hash
        hash2 = p1.semantic_hash
        assert hash1 == hash2
        assert len(hash1) == 64


class TestSecretScanner:
    """Tests for SecretScanner leak detection and educational placeholder handling."""

    @pytest.fixture
    def scanner(self) -> SecretScanner:
        return SecretScanner()

    def test_detect_live_openai_key(self, scanner: SecretScanner) -> None:
        leak_text = 'client = OpenAI(api_key="sk-abc1234567890abcdef1234567890abcdef")'
        matches = scanner.scan_text(leak_text)
        assert len(matches) == 1
        assert matches[0].pattern_name == "OPENAI_API_KEY_LIVE"
        assert "****" in matches[0].redacted_snippet

    def test_detect_live_anthropic_key(self, scanner: SecretScanner) -> None:
        leak_text = 'client = Anthropic(api_key="sk-ant-api03-abcdef1234567890abcdef1234567890")'
        matches = scanner.scan_text(leak_text)
        assert len(matches) == 1
        assert matches[0].pattern_name == "ANTHROPIC_API_KEY_LIVE"

    def test_detect_private_key_block(self, scanner: SecretScanner) -> None:
        leak_text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----"
        matches = scanner.scan_text(leak_text)
        assert len(matches) >= 1
        assert matches[0].pattern_name == "PRIVATE_KEY_BLOCK"

    def test_allow_educational_placeholders(self, scanner: SecretScanner) -> None:
        safe_snippets = [
            'api_key = "sk-..."',
            'api_key = "sk-... ✕"',
            'OPENAI_API_KEY=your_api_key_here',
            'api_key = os.environ.get("OPENAI_API_KEY", "your-api-key-here")',
            'client = OpenAI(api_key="sk-placeholder-for-demo")',
            'test_key = "sk-dummy-key-for-testing"',
        ]
        for snippet in safe_snippets:
            matches = scanner.scan_text(snippet)
            assert len(matches) == 0, f"Expected clean for safe placeholder: {snippet}, got {matches}"

    def test_scan_files_clean_and_dirty(self, scanner: SecretScanner) -> None:
        clean_files = {
            "src/agent.py": "class Agent:\n    def run(self, prompt: str) -> str:\n        return 'answer'\n",
            ".env.example": "OPENAI_API_KEY=your_openai_api_key_here\n",
        }
        res_clean = scanner.scan_files(clean_files)
        assert res_clean.is_clean is True
        assert len(res_clean.matches) == 0

        dirty_files = {
            "src/agent.py": "OPENAI_API_KEY='sk-live9876543210abcdef9876543210'\n",
        }
        res_dirty = scanner.scan_files(dirty_files)
        assert res_dirty.is_clean is False
        assert len(res_dirty.matches) == 1


class TestVideo02RecordingEngine:
    """Tests for Video02RecordingEngine recording execution and manifest generation."""

    @pytest.fixture
    def recording_engine(self) -> Video02RecordingEngine:
        return Video02RecordingEngine()

    def test_record_single_pass_cold_open(self, recording_engine: Video02RecordingEngine) -> None:
        rec = recording_engine.record_pass("PASS_01_COLD_OPEN")
        assert rec.pass_id == "PASS_01_COLD_OPEN"
        assert rec.scene_id == "S01"
        assert rec.status == PassStatus.VERIFIED
        assert rec.duration_ms == 25000
        assert rec.frame_count == 750
        assert rec.verified_terminal is True
        assert rec.secret_clean is True
        assert len(rec.output_hash) == 64

    def test_record_single_pass_agent_core(self, recording_engine: Video02RecordingEngine) -> None:
        rec = recording_engine.record_pass("PASS_07_AGENT_CORE")
        assert rec.pass_id == "PASS_07_AGENT_CORE"
        assert rec.scene_id == "S10"
        assert rec.status == PassStatus.VERIFIED
        assert rec.duration_ms == 95000
        assert rec.frame_count == 2850

    def test_record_all_16_passes(self, recording_engine: Video02RecordingEngine) -> None:
        manifest = recording_engine.record_all_passes()
        assert manifest.total_passes == 16
        assert len(manifest.passes) == 16
        assert manifest.all_secrets_clean is True
        assert manifest.all_terminals_verified is True
        assert manifest.master_resolution == "2560x1440"
        assert manifest.fps == 30
        assert len(manifest.manifest_hash) == 64

        for p in manifest.passes:
            assert p.status == PassStatus.VERIFIED
            assert p.secret_clean is True
            assert p.verified_terminal is True

    def test_export_recording_manifest(self, recording_engine: Video02RecordingEngine, tmp_path: Path) -> None:
        manifest = recording_engine.record_all_passes()
        out_file = recording_engine.export_recording(manifest, target_dir=tmp_path)
        assert out_file.exists()

        # Check that individual pass files are also exported
        for p in manifest.passes:
            pass_file = tmp_path / f"{p.pass_id}.json"
            assert pass_file.exists()
            data = json.loads(pass_file.read_text(encoding="utf-8"))
            assert data["pass_id"] == p.pass_id
            assert data["status"] == "VERIFIED"


class TestRecordingVerifier:
    """Tests for RecordingVerifier and Gate CV02_P9_RECORDING_VERIFIED."""

    def test_verify_valid_manifest(self) -> None:
        engine = Video02RecordingEngine()
        manifest = engine.record_all_passes()

        report = RecordingVerifier.verify_manifest(manifest)
        assert report.gate == "CV02_P9_RECORDING_VERIFIED"
        assert report.is_valid is True
        assert report.total_passes_checked == 16
        assert len(report.violations) == 0
        assert "TOTAL_PASS_COUNT_16_VERIFIED" in report.passed_checks
        assert "ZERO_SECRET_EXPOSURE_VERIFIED" in report.passed_checks
        assert "TERMINAL_OUTPUT_AUTHENTICITY_VERIFIED" in report.passed_checks
        assert report.summary["verdict"] == "PASS"

    def test_reject_manifest_with_secret_violation(self) -> None:
        engine = Video02RecordingEngine()
        manifest = engine.record_all_passes()
        manifest.all_secrets_clean = False

        report = RecordingVerifier.verify_manifest(manifest)
        assert report.is_valid is False
        assert report.summary["verdict"] == "REJECT"
        assert any("Secret exposure detected" in v for v in report.violations)

    def test_reject_manifest_with_missing_pass(self) -> None:
        engine = Video02RecordingEngine()
        manifest = engine.record_all_passes()
        manifest.passes.pop()
        manifest.total_passes = len(manifest.passes)

        report = RecordingVerifier.verify_manifest(manifest)
        assert report.is_valid is False
        assert any("Pass count expected 16" in v for v in report.violations)

    def test_verify_manifest_file(self, tmp_path: Path) -> None:
        engine = Video02RecordingEngine()
        manifest = engine.record_all_passes()
        manifest_path = engine.export_recording(manifest, target_dir=tmp_path)

        report = RecordingVerifier.verify_manifest_file(manifest_path)
        assert report.is_valid is True
        assert report.gate == "CV02_P9_RECORDING_VERIFIED"
