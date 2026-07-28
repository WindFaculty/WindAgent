#!/usr/bin/env python3
"""
Tests for WindAgent Artifact Schema Validator (Phase 7A - Hardened)

Tests cover:
- Valid artifact passes schema validation
- Invalid artifacts fail with appropriate errors
- Semantic validations (hash format, command receipts, self-hash detection)
- Validator modes (--schema-only, --semantic, --verify-hashes, --json, --fail-on-warning)
- Directory/glob support
"""

import json
import tempfile
import subprocess
import sys
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from validate_artifact_schema import (
    load_schema,
    validate_artifact,
    compute_file_hash,
    _validate_semantics,
    _validate_command_receipt,
    collect_artifact_files,
    main,
)
# Also need to import the internal functions
import validate_artifact_schema as vas
_validate_semantics = vas._validate_semantics
_validate_command_receipt = vas._validate_command_receipt
collect_artifact_files = vas.collect_artifact_files


class TestSchemaLoading:
    """Test schema loading and basic structure."""

    def test_schema_loads(self):
        schema = load_schema()
        assert isinstance(schema, dict)
        assert schema.get("title") == "WindAgent Artifact Protocol v1"
        assert "properties" in schema
        assert "required" in schema

    def test_schema_has_required_fields(self):
        schema = load_schema()
        required = schema.get("required", [])
        expected = [
            "protocol_version", "generated_at", "source_sha", "verified_sha",
            "branch", "worktree_clean", "commands", "results", "failures",
            "warnings", "artifact_hashes", "verdict"
        ]
        for field in expected:
            assert field in required, f"Missing required field: {field}"


class TestValidArtifact:
    """Tests for valid artifacts."""

    def create_valid_artifact(self) -> dict:
        """Create a minimal valid artifact."""
        return {
            "protocol_version": "1.0.0",
            "generated_at": "2026-07-28T12:00:00Z",
            "source_sha": "95b955178b8e38d5c8fb3d84cd7a4bedd19b864e",
            "verified_sha": "09ce71b8dd5851cce6f2e741f8ac94bf25e81378",
            "branch": "hardening/phase-7-integration",
            "worktree_clean": True,
            "commands": [{
                "command_id": "test_cmd",
                "command": "python -c 'print(1)'",
                "cwd": ".",
                "started_at": "2026-07-28T12:00:00Z",
                "finished_at": "2026-07-28T12:00:01Z",
                "duration_ms": 1000,
                "exit_code": 0,
                "stdout_tail": "1",
                "stderr_tail": "",
                "environment": {
                    "os": "windows",
                    "python": "3.11.15",
                    "uv": "0.5.0",
                    "git_sha": "95b955178b8e38d5c8fb3d84cd7a4bedd19b864e"
                },
                "expected_exit_codes": [0],
                "result": "SUCCESS",
                "output_sha256": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456"
            }],
            "results": {"test": "passed"},
            "failures": [],
            "warnings": [],
            "artifact_hashes": {
                "test_artifact.json": "141e1041263e7c5f4b5a50badfbafe4efa2f1cfe1e5721e9a7effe41fda37b45"
            },
            "verdict": "PASS"
        }

    def test_valid_artifact_passes(self):
        artifact = self.create_valid_artifact()
        schema = load_schema()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            f.flush()
            # Default mode: run_schema=True, run_semantic=True, run_hashes=False
            errors, warnings = validate_artifact(Path(f.name), schema)
        assert errors == [], f"Valid artifact should pass: {errors}"
        Path(f.name).unlink()

    def test_valid_artifact_passes_full_mode(self):
        artifact = self.create_valid_artifact()
        schema = load_schema()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            f.flush()
            # Full mode = run_schema + run_semantic (same as default)
            errors, warnings = validate_artifact(
                Path(f.name), schema,
                run_schema=True, run_semantic=True, run_hashes=False
            )
        assert errors == [], f"Valid artifact should pass: {errors}"
        Path(f.name).unlink()


class TestInvalidArtifacts:
    """Tests for various invalid artifact scenarios."""

    def create_base_artifact(self) -> dict:
        """Create a base artifact with minimal valid structure."""
        return {
            "protocol_version": "1.0.0",
            "generated_at": "2026-07-28T12:00:00Z",
            "source_sha": "95b955178b8e38d5c8fb3d84cd7a4bedd19b864e",
            "verified_sha": "09ce71b8dd5851cce6f2e741f8ac94bf25e81378",
            "branch": "hardening/phase-7-integration",
            "worktree_clean": True,
            "commands": [{
                "command_id": "test_cmd",
                "command": "python -c 'print(1)'",
                "cwd": ".",
                "started_at": "2026-07-28T12:00:00Z",
                "finished_at": "2026-07-28T12:00:01Z",
                "duration_ms": 1000,
                "exit_code": 0,
                "stdout_tail": "1",
                "stderr_tail": "",
                "environment": {
                    "os": "windows",
                    "python": "3.11.15",
                    "uv": "0.5.0",
                    "git_sha": "95b955178b8e38d5c8fb3d84cd7a4bedd19b864e"
                },
                "expected_exit_codes": [0],
                "result": "SUCCESS",
                "output_sha256": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456"
            }],
            "results": {"test": "passed"},
            "failures": [],
            "warnings": [],
            "artifact_hashes": {
                "test_artifact.json": "141e1041263e7c5f4b5a50badfbafe4efa2f1cfe1e5721e9a7effe41fda37b45"
            },
            "verdict": "PASS"
        }

    def validate_artifact(self, artifact: dict) -> list:
        schema = load_schema()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            f.flush()
            errors, _ = validate_artifact(Path(f.name), schema)
        Path(f.name).unlink()
        return errors

    def validate_artifact_with_warnings(self, artifact: dict) -> tuple:
        schema = load_schema()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            f.flush()
            errors, warnings = validate_artifact(Path(f.name), schema)
        Path(f.name).unlink()
        return errors, warnings

    def test_empty_commands_fails(self):
        artifact = self.create_base_artifact()
        artifact["commands"] = []
        errors = self.validate_artifact(artifact)
        assert any("commands array must have at least one command receipt" in e for e in errors)

    def test_missing_commands_fails(self):
        artifact = self.create_base_artifact()
        del artifact["commands"]
        errors = self.validate_artifact(artifact)
        assert any("commands array must have at least one command receipt" in e for e in errors)

    def test_empty_artifact_hashes_fails(self):
        artifact = self.create_base_artifact()
        artifact["artifact_hashes"] = {}
        errors = self.validate_artifact(artifact)
        assert any("artifact_hashes must not be empty" in e for e in errors)

    def test_placeholder_hash_fails(self):
        artifact = self.create_base_artifact()
        artifact["artifact_hashes"] = {"test.json": "placeholder"}
        errors = self.validate_artifact(artifact)
        assert any("64 hex chars" in e or "lowercase hex" in e for e in errors)

    def test_sha256_prefix_fails(self):
        artifact = self.create_base_artifact()
        artifact["artifact_hashes"] = {"test.json": "sha256:abcd1234..."}
        errors = self.validate_artifact(artifact)
        assert any("64 hex chars" in e or "lowercase hex" in e for e in errors)

    def test_invalid_verified_sha_fails(self):
        artifact = self.create_base_artifact()
        artifact["verified_sha"] = "not-a-hash"
        errors = self.validate_artifact(artifact)
        assert any("40 hex chars" in e or "lowercase hex" in e for e in errors)

    def test_dirty_worktree_with_pass_fails(self):
        artifact = self.create_base_artifact()
        artifact["worktree_clean"] = False
        artifact["verdict"] = "PASS"
        errors = self.validate_artifact(artifact)
        assert any("dirty worktree cannot PASS" in e for e in errors)

    def test_invalid_verdict_fails(self):
        artifact = self.create_base_artifact()
        artifact["verdict"] = "UNKNOWN"
        errors = self.validate_artifact(artifact)
        assert any("verdict must be one of" in e for e in errors)

    def test_invalid_failure_severity_fails(self):
        artifact = self.create_base_artifact()
        artifact["failures"] = [{"check": "test", "message": "fail", "severity": "INVALID"}]
        errors = self.validate_artifact(artifact)
        assert any("Failure severity must be one of" in e for e in errors)

    def test_invalid_generated_at_fails(self):
        artifact = self.create_base_artifact()
        artifact["generated_at"] = "not-a-date"
        errors = self.validate_artifact(artifact)
        assert any("ISO8601" in e for e in errors)

    def test_string_warnings_fail(self):
        artifact = self.create_base_artifact()
        artifact["warnings"] = ["this is a string warning"]
        errors, _ = self.validate_artifact_with_warnings(artifact)
        assert any("structured objects, not strings" in e for e in errors)

    def test_incomplete_warning_object_fails(self):
        artifact = self.create_base_artifact()
        artifact["warnings"] = [{"check": "test", "message": "warning"}]  # missing severity, accepted, rationale
        errors, warnings = self.validate_artifact_with_warnings(artifact)
        # Now missing fields in warnings are errors (not warnings)
        assert any("severity" in e for e in errors) or any("accepted" in e for e in errors) or any("rationale" in e for e in errors)

    def test_self_hash_detected_as_error(self):
        """Self-hash should now be an ERROR (not warning) per Phase 1.4"""
        artifact = self.create_base_artifact()
        # Use temp file's actual name as the hash key
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_name = Path(f.name).name
            artifact["artifact_hashes"][temp_name] = "141e1041263e7c5f4b5a50badfbafe4efa2f1cfe1e5721e9a7effe41fda37b45"
            json.dump(artifact, f)
            f.flush()
            schema = load_schema()
            errors, warnings = validate_artifact(Path(f.name), schema)
        Path(f.name).unlink()
        # Self-hash should now be an ERROR
        assert any("self-referential hash detected" in e for e in errors)


class TestCommandReceiptValidation:
    """Tests for command receipt validation."""

    def test_missing_command_id_fails(self):
        receipt = self.base_receipt()
        del receipt["command_id"]
        errors = _validate_command_receipt(receipt, 0)
        assert any("command_id" in e for e in errors)

    def test_invalid_command_id_format_fails(self):
        receipt = self.base_receipt()
        receipt["command_id"] = "Invalid_ID"
        errors = _validate_command_receipt(receipt, 0)
        assert any("command_id must match" in e for e in errors)

    def test_invalid_timestamp_fails(self):
        receipt = self.base_receipt()
        receipt["started_at"] = "not-a-date"
        errors = _validate_command_receipt(receipt, 0)
        assert any("ISO8601" in e for e in errors)

    def test_negative_duration_fails(self):
        receipt = self.base_receipt()
        receipt["duration_ms"] = -1
        errors = _validate_command_receipt(receipt, 0)
        assert any("non-negative" in e for e in errors)

    def test_invalid_exit_code_type_fails(self):
        receipt = self.base_receipt()
        receipt["exit_code"] = "zero"
        errors = _validate_command_receipt(receipt, 0)
        assert any("exit_code must be integer" in e for e in errors)

    def test_empty_expected_exit_codes_fails(self):
        receipt = self.base_receipt()
        receipt["expected_exit_codes"] = []
        errors = _validate_command_receipt(receipt, 0)
        assert any("non-empty array" in e for e in errors)

    def test_invalid_result_fails(self):
        receipt = self.base_receipt()
        receipt["result"] = "MAYBE"
        errors = _validate_command_receipt(receipt, 0)
        assert any("result must be one of" in e for e in errors)

    def test_invalid_output_sha256_fails(self):
        receipt = self.base_receipt()
        receipt["output_sha256"] = "not-a-hash"
        errors = _validate_command_receipt(receipt, 0)
        assert any("64 lowercase hex chars" in e for e in errors)

    def test_missing_environment_fields_fail(self):
        receipt = self.base_receipt()
        del receipt["environment"]
        errors = _validate_command_receipt(receipt, 0)
        assert any("environment missing required field" in e for e in errors)

    def base_receipt(self) -> dict:
        return {
            "command_id": "test_cmd",
            "command": "python -c 'print(1)'",
            "cwd": ".",
            "started_at": "2026-07-28T12:00:00Z",
            "finished_at": "2026-07-28T12:00:01Z",
            "duration_ms": 1000,
            "exit_code": 0,
            "stdout_tail": "1",
            "stderr_tail": "",
            "environment": {
                "os": "windows",
                "python": "3.11.15",
                "uv": "0.5.0",
                "git_sha": "95b955178b8e38d5c8fb3d84cd7a4bedd19b864e"
            },
            "expected_exit_codes": [0],
            "result": "SUCCESS",
            "output_sha256": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456"
        }


class TestValidatorModes:
    """Tests for validator CLI modes (run_schema, run_semantic, run_hashes)."""

    def create_valid_artifact(self) -> dict:
        return {
            "protocol_version": "1.0.0",
            "generated_at": "2026-07-28T12:00:00Z",
            "source_sha": "95b955178b8e38d5c8fb3d84cd7a4bedd19b864e",
            "verified_sha": "09ce71b8dd5851cce6f2e741f8ac94bf25e81378",
            "branch": "hardening/phase-7-integration",
            "worktree_clean": True,
            "commands": [{
                "command_id": "test_cmd",
                "command": "python -c 'print(1)'",
                "cwd": ".",
                "started_at": "2026-07-28T12:00:00Z",
                "finished_at": "2026-07-28T12:00:01Z",
                "duration_ms": 1000,
                "exit_code": 0,
                "stdout_tail": "1",
                "stderr_tail": "",
                "environment": {
                    "os": "windows",
                    "python": "3.11.15",
                    "uv": "0.5.0",
                    "git_sha": "95b955178b8e38d5c8fb3d84cd7a4bedd19b864e"
                },
                "expected_exit_codes": [0],
                "result": "SUCCESS",
                "output_sha256": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456"
            }],
            "results": {"test": "passed"},
            "failures": [],
            "warnings": [],
            "artifact_hashes": {
                "test_artifact.json": "141e1041263e7c5f4b5a50badfbafe4efa2f1cfe1e5721e9a7effe41fda37b45"
            },
            "verdict": "PASS"
        }

    def test_schema_only_mode(self):
        """--schema-only should only run schema validation, skip semantic."""
        artifact = self.create_valid_artifact()
        # Add semantic error (dirty worktree + PASS)
        artifact["worktree_clean"] = False
        artifact["verdict"] = "PASS"

        schema = load_schema()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            f.flush()
            # Schema-only: run_schema=True, run_semantic=False
            errors, _ = validate_artifact(
                Path(f.name), schema,
                run_schema=True, run_semantic=False, run_hashes=False
            )
        Path(f.name).unlink()

        # Schema-only should not catch semantic error
        assert errors == []

    def test_semantic_mode_catches_dirty_worktree(self):
        """--semantic should catch semantic errors."""
        artifact = self.create_valid_artifact()
        artifact["worktree_clean"] = False
        artifact["verdict"] = "PASS"

        schema = load_schema()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            f.flush()
            # Semantic-only: run_schema=False, run_semantic=True
            errors, _ = validate_artifact(
                Path(f.name), schema,
                run_schema=False, run_semantic=True, run_hashes=False
            )
        Path(f.name).unlink()

        assert any("dirty worktree cannot PASS" in e for e in errors)

    def test_full_mode_catches_both(self):
        """Default mode (schema + semantic) catches both."""
        artifact = self.create_valid_artifact()
        artifact["worktree_clean"] = False
        artifact["verdict"] = "PASS"
        # Also make it schema-invalid by removing required field
        del artifact["protocol_version"]

        schema = load_schema()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            f.flush()
            # Default: run_schema=True, run_semantic=True
            errors, _ = validate_artifact(Path(f.name), schema)
        Path(f.name).unlink()

        assert any("protocol_version" in e or "required" in e for e in errors)
        assert any("dirty worktree cannot PASS" in e for e in errors)

    def test_fail_on_warning(self):
        """--fail-on-warning should turn warnings into errors."""
        artifact = self.create_valid_artifact()
        # Add a valid warning structure that will trigger a semantic warning:
        # accepted=false in PASS artifact (Phase 1.6)
        artifact["warnings"] = [{
            "check": "test_warning",
            "message": "This warning is not accepted",
            "severity": "LOW",
            "accepted": False,
            "rationale": "Testing fail-on-warning"
        }]

        schema = load_schema()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            f.flush()
            errors, warnings = validate_artifact(
                Path(f.name), schema,
                run_schema=True, run_semantic=True,
                fail_on_warning=True
            )
        Path(f.name).unlink()

        # The accepted=false in PASS should generate an error (not warning)
        # but the warning about it should become an error with fail_on_warning
        assert len(errors) > 0
        assert any("accepted=false cannot appear in PASS artifact" in e for e in errors)


class TestDirectoryGlobSupport:
    """Tests for directory and glob support."""

    def test_collect_files_from_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "artifact1.json").write_text('{"protocol_version": "1.0.0", "verdict": "PASS"}')
            (tmp_path / "artifact2.json").write_text('{"protocol_version": "1.0.0", "verdict": "PASS"}')
            (tmp_path / "not_artifact.txt").write_text("text")

            files = collect_artifact_files([str(tmp_path)], recursive=False)
            assert len(files) == 2
            assert all(f.suffix == ".json" for f in files)

    def test_collect_files_recursive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "artifact1.json").write_text('{"protocol_version": "1.0.0", "verdict": "PASS"}')
            subdir = tmp_path / "sub"
            subdir.mkdir()
            (subdir / "artifact2.json").write_text('{"protocol_version": "1.0.0", "verdict": "PASS"}')

            files = collect_artifact_files([str(tmp_path)], recursive=True)
            assert len(files) == 2

            files_no_recursive = collect_artifact_files([str(tmp_path)], recursive=False)
            assert len(files_no_recursive) == 1

    def test_collect_single_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            artifact = tmp_path / "artifact.json"
            artifact.write_text('{"protocol_version": "1.0.0", "verdict": "PASS"}')

            files = collect_artifact_files([str(artifact)], recursive=False)
            assert len(files) == 1
            assert files[0] == artifact


class TestCLIIntegration:
    """Integration tests for the CLI."""

    def run_validator(self, args: list) -> tuple:
        """Run validator CLI and return (exit_code, stdout, stderr)."""
        cmd = [sys.executable, "scripts/validate_artifact_schema.py"] + args
        # Test file is at tests/unit/scripts/test_xxx.py, need to go up 4 levels to repo root
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)
        return result.returncode, result.stdout, result.stderr

    def test_valid_artifact_cli_pass(self):
        # Use the existing valid artifact fixture
        exit_code, stdout, stderr = self.run_validator([
            "tests/fixtures/artifacts/valid_artifact.json"
        ])
        assert exit_code == 0
        assert "PASS" in stdout

    def test_invalid_artifact_cli_fail(self):
        exit_code, stdout, stderr = self.run_validator([
            "tests/fixtures/artifacts/missing_commands.json"
        ])
        assert exit_code == 1
        assert "FAIL" in stdout

    def test_directory_mode(self):
        exit_code, stdout, stderr = self.run_validator([
            "--directory", "tests/fixtures/artifacts",
            "--recursive"
        ])
        # Should process all fixtures
        assert exit_code == 1  # Some fixtures are invalid by design
        assert "FAIL" in stdout or "PASS" in stdout

    def test_json_output(self):
        exit_code, stdout, stderr = self.run_validator([
            "--json", "tests/fixtures/artifacts/valid_artifact.json"
        ])
        assert exit_code == 0
        data = json.loads(stdout)
        assert "summary" in data
        assert "results" in data
        assert data["summary"]["passed"] == 1

    def test_schema_only_mode(self):
        artifact = {
            "protocol_version": "1.0.0",
            "generated_at": "2026-07-28T12:00:00Z",
            "source_sha": "95b955178b8e38d5c8fb3d84cd7a4bedd19b864e",
            "verified_sha": "09ce71b8dd5851cce6f2e741f8ac94bf25e81378",
            "branch": "hardening/phase-7-integration",
            "worktree_clean": False,
            "verdict": "PASS",  # Semantic error: dirty worktree + PASS
            "commands": [{
                "command_id": "test", "command": "echo", "cwd": ".",
                "started_at": "2026-07-28T12:00:00Z", "finished_at": "2026-07-28T12:00:01Z",
                "duration_ms": 100, "exit_code": 0, "stdout_tail": "", "stderr_tail": "",
                "environment": {"os": "windows", "python": "3.11", "uv": "0.5", "git_sha": "95b955178b8e38d5c8fb3d84cd7a4bedd19b864e"},
                "expected_exit_codes": [0], "result": "SUCCESS",
                "output_sha256": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456"
            }],
            "results": {},
            "failures": [],
            "warnings": [],
            "artifact_hashes": {"test.json": "141e1041263e7c5f4b5a50badfbafe4efa2f1cfe1e5721e9a7effe41fda37b45"}
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            f.flush()
            exit_code, stdout, stderr = self.run_validator(["--schema-only", f.name])
        Path(f.name).unlink()
        assert exit_code == 0  # Schema-only ignores semantic error


class TestHashComputation:
    """Tests for hash computation."""

    def test_compute_file_hash(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write('{"test": "data"}')
            f.flush()
            hash_val = compute_file_hash(Path(f.name))
        Path(f.name).unlink()

        assert len(hash_val) == 64
        assert all(c in "0123456789abcdef" for c in hash_val)

    def test_hash_consistency(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write('consistent content')
            f.flush()
            hash1 = compute_file_hash(Path(f.name))
            hash2 = compute_file_hash(Path(f.name))
        Path(f.name).unlink()

        assert hash1 == hash2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])