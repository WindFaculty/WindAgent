#!/usr/bin/env python3
"""
Tests for evidence generation pipeline (Phase 2)
"""

import json
import tempfile
import subprocess
import sys
from pathlib import Path

import pytest


def run_evidence_gen(args: list[str]) -> tuple[int, str, str]:
    """Run evidence generator and return (exit_code, stdout, stderr)."""
    cmd = [sys.executable, "scripts/verification/generate_phase7_evidence.py"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return result.returncode, result.stdout, result.stderr


def test_generate_evidence_bundle_valid_commands():
    """Test generating bundle with all passing commands."""
    commands = {
        "test_pass": {
            "command": ["python", "-c", "print('hello')"],
            "expected_exit_codes": [0],
            "timeout": 10,
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        commands_file = Path(tmpdir) / "commands.yaml"
        import yaml
        with open(commands_file, "w") as f:
            yaml.dump({"commands": commands}, f)
        
        output_dir = Path(tmpdir) / "output"
        code, stdout, stderr = run_evidence_gen([
            "--commands-file", str(commands_file),
            "--output-dir", str(output_dir),
            "--cwd", "."
        ])
        assert code == 0, f"Failed: {stderr}"
        assert output_dir.exists()
        
        # Verify bundle
        bundle_file = output_dir / "evidence_bundle.json"
        assert bundle_file.exists()
        with open(bundle_file) as f:
            bundle = json.load(f)
        
        assert bundle["verdict"] in ("PASS", "BLOCKED")
        assert len(bundle["commands"]) == 1
        assert bundle["commands"][0]["result"] == "SUCCESS"


def test_generate_evidence_bundle_failing_command():
    """Test that failing command produces FAIL verdict."""
    commands = {
        "test_fail": {
            "command": ["python", "-c", "import sys; sys.exit(1)"],
            "expected_exit_codes": [0],
            "timeout": 10,
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        commands_file = Path(tmpdir) / "commands.yaml"
        import yaml
        with open(commands_file, "w") as f:
            yaml.dump({"commands": commands}, f)
        
        output_dir = Path(tmpdir) / "output"
        code, stdout, stderr = run_evidence_gen([
            "--commands-file", str(commands_file),
            "--output-dir", str(output_dir),
            "--cwd", "."
        ])
        assert code == 1, f"Expected exit 1, got {code}"
        assert output_dir.exists()
        
        bundle_file = output_dir / "evidence_bundle.json"
        with open(bundle_file) as f:
            bundle = json.load(f)
        
        assert bundle["verdict"] == "FAIL"
        assert len(bundle["failures"]) == 1


def test_generate_evidence_bundle_timeout():
    """Test timeout handling."""
    commands = {
        "test_timeout": {
            "command": ["python", "-c", "import time; time.sleep(10)"],
            "expected_exit_codes": [0],
            "timeout": 1,
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        commands_file = Path(tmpdir) / "commands.yaml"
        import yaml
        with open(commands_file, "w") as f:
            yaml.dump({"commands": commands}, f)
        
        output_dir = Path(tmpdir) / "output"
        code, stdout, stderr = run_evidence_gen([
            "--commands-file", str(commands_file),
            "--output-dir", str(output_dir),
            "--cwd", "."
        ])
        assert code == 1
        
        bundle_file = output_dir / "evidence_bundle.json"
        with open(bundle_file) as f:
            bundle = json.load(f)
        
        assert bundle["verdict"] == "FAIL"
        assert bundle["commands"][0]["result"] == "TIMEOUT"


def test_generate_evidence_bundle_large_output():
    """Test handling large stdout."""
    commands = {
        "test_large": {
            "command": ["python", "-c", "print('x' * 10000)"],
            "expected_exit_codes": [0],
            "timeout": 10,
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        commands_file = Path(tmpdir) / "commands.yaml"
        import yaml
        with open(commands_file, "w") as f:
            yaml.dump({"commands": commands}, f)
        
        output_dir = Path(tmpdir) / "output"
        code, stdout, stderr = run_evidence_gen([
            "--commands-file", str(commands_file),
            "--output-dir", str(output_dir),
            "--cwd", "."
        ])
        assert code == 0
        
        bundle_file = output_dir / "evidence_bundle.json"
        with open(bundle_file) as f:
            bundle = json.load(f)
        
        assert bundle["verdict"] in ("PASS", "BLOCKED")
        # output_sha256 should be computed
        assert "output_sha256" in bundle["commands"][0]
        assert len(bundle["commands"][0]["output_sha256"]) == 64


def test_run_command_receipt_success():
    """Test run_command_receipt.py generates valid receipt."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "receipt.json"
        cmd = [
            sys.executable, "scripts/verification/run_command_receipt.py",
            "--name", "test_echo",
            "--output", str(output),
            "--", "python", "-c", "print('hello')"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, f"Failed: {result.stderr}"
        
        with open(output) as f:
            receipt = json.load(f)
        
        assert receipt["command_id"] == "test_echo"
        assert receipt["result"] == "SUCCESS"
        assert receipt["exit_code"] == 0
        assert "output_sha256" in receipt
        assert len(receipt["output_sha256"]) == 64


def test_run_command_receipt_failure():
    """Test run_command_receipt.py with expected failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "receipt.json"
        cmd = [
            sys.executable, "scripts/verification/run_command_receipt.py",
            "--name", "test_fail",
            "--output", str(output),
            "--expected-exit-codes", "1",
            "--", "python", "-c", "import sys; sys.exit(1)"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0
        
        with open(output) as f:
            receipt = json.load(f)
        
        assert receipt["result"] == "SUCCESS"
        assert receipt["exit_code"] == 1


def test_run_command_receipt_timeout():
    """Test run_command_receipt.py timeout."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "receipt.json"
        cmd = [
            sys.executable, "scripts/verification/run_command_receipt.py",
            "--name", "test_timeout",
            "--output", str(output),
            "--timeout", "1",
            "--", "python", "-c", "import time; time.sleep(5)"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        assert result.returncode == 1
        
        with open(output) as f:
            receipt = json.load(f)
        
        assert receipt["result"] == "TIMEOUT"
        assert receipt["exit_code"] == -1


def test_bundle_passes_schema_validation():
    """Test generated bundle passes artifact schema validation."""
    commands = {
        "test_pass": {
            "command": ["python", "-c", "print('hello')"],
            "expected_exit_codes": [0],
            "timeout": 10,
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        commands_file = Path(tmpdir) / "commands.yaml"
        import yaml
        with open(commands_file, "w") as f:
            yaml.dump({"commands": commands}, f)
        
        output_dir = Path(tmpdir) / "output"
        code, stdout, stderr = run_evidence_gen([
            "--commands-file", str(commands_file),
            "--output-dir", str(output_dir),
            "--cwd", "."
        ])
        assert code == 0
        
        # Validate with schema validator
        bundle_file = output_dir / "evidence_bundle.json"
        val_cmd = [
            sys.executable, "scripts/validate_artifact_schema.py",
            str(bundle_file)
        ]
        val_result = subprocess.run(val_cmd, capture_output=True, text=True, timeout=30)
        assert val_result.returncode == 0, f"Schema validation failed: {val_result.stdout}"


def test_receipt_has_required_fields():
    """Test receipt contains all required fields per schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "receipt.json"
        cmd = [
            sys.executable, "scripts/verification/run_command_receipt.py",
            "--name", "test_fields",
            "--output", str(output),
            "--", "python", "-c", "print('test')"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0
        
        with open(output) as f:
            receipt = json.load(f)
        
        required = [
            "command_id", "command", "cwd", "started_at", "finished_at",
            "duration_ms", "exit_code", "stdout_tail", "stderr_tail",
            "environment", "expected_exit_codes", "result", "output_sha256"
        ]
        for field in required:
            assert field in receipt, f"Missing field: {field}"
        
        # Verify environment has required sub-fields
        env = receipt["environment"]
        for field in ["os", "python", "uv", "git_sha"]:
            assert field in env, f"Missing env field: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

def test_redact_secrets_in_output():
    """Redaction strips common secret patterns."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "verification"))
    from run_command_receipt import redact

    assert "ghp_" not in redact("token ghp_abcdefghijklmnopqrstuvwxyz0123456789 leaked")
    assert "***REDACTED***" in redact("api_key=supersecretvalue123")
    assert "***REDACTED***" in redact("password: hunter2")
    assert redact("normal output") == "normal output"
