#!/usr/bin/env python3
"""
Tests for evidence generation pipeline (Phase 2)
"""

import json
import hashlib
import tempfile
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[3]
CANONICAL_REGISTRY = ROOT / "scripts" / "verification" / "command_registry.yaml"


def run_evidence_gen(args: list[str]) -> tuple[int, str, str]:
    """Run evidence generator and return (exit_code, stdout, stderr)."""
    cmd = [sys.executable, "scripts/verification/generate_phase7_evidence.py"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return result.returncode, result.stdout, result.stderr


def find_published_bundle(output_dir: Path) -> Path:
    """Return the single immutable bundle published by a test run."""
    bundles = list(output_dir.glob("runs/*/evidence_bundle.json"))
    bundles.extend(output_dir.glob("quarantine/*/evidence_bundle.json"))
    assert len(bundles) == 1, bundles
    return bundles[0]


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
        assert code in (0, 2), f"Failed: {stderr}"
        assert output_dir.exists()
        
        # Verify bundle
        bundle_file = find_published_bundle(output_dir)
        assert bundle_file.exists()
        with open(bundle_file) as f:
            bundle = json.load(f)
        
        assert bundle["verdict"] in ("PASS", "BLOCKED")
        assert len(bundle["commands"]) == 1
        assert bundle["commands"][0]["result"] == "SUCCESS"
        if bundle["verdict"] == "PASS":
            assert (output_dir / "latest.json").exists()
        else:
            assert not (output_dir / "latest.json").exists()


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
        
        bundle_file = find_published_bundle(output_dir)
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
        
        bundle_file = find_published_bundle(output_dir)
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
        assert code in (0, 2)
        
        bundle_file = find_published_bundle(output_dir)
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
        assert len(receipt["stdout_sha256"]) == 64
        assert len(receipt["stderr_sha256"]) == 64


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
        assert code in (0, 2)
        
        # Validate with schema validator
        bundle_file = find_published_bundle(output_dir)
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
            "environment", "expected_exit_codes", "result", "stdout_sha256",
            "stderr_sha256", "output_sha256"
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


def test_receipt_hashes_exact_persisted_redacted_bytes():
    """Receipt hashes are independently reproducible from persisted logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "receipts" / "receipt.json"
        cmd = [
            sys.executable,
            "scripts/verification/run_command_receipt.py",
            "--name", "redacted_hash",
            "--output", str(output),
            "--", "python", "-c",
            "import sys; print('token=supersecretvalue'); "
            "print('password: hunter2', file=sys.stderr)",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr

        receipt = json.loads(output.read_text(encoding="utf-8"))
        stdout = (Path(tmpdir) / receipt["log_paths"]["stdout_log"]).read_bytes()
        stderr = (Path(tmpdir) / receipt["log_paths"]["stderr_log"]).read_bytes()
        assert b"supersecretvalue" not in stdout
        assert b"hunter2" not in stderr
        assert receipt["stdout_sha256"] == hashlib.sha256(stdout).hexdigest()
        assert receipt["stderr_sha256"] == hashlib.sha256(stderr).hexdigest()
        assert receipt["output_sha256"] == hashlib.sha256(stdout + stderr).hexdigest()


def test_existing_immutable_destination_is_not_overwritten():
    """A repeated run id fails instead of replacing existing evidence."""
    commands = {
        "test_pass": {
            "shell": "process",
            "command": ["python", "-c", "print('hello')"],
            "expected_exit_codes": [0],
            "timeout": 10,
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        commands_file = Path(tmpdir) / "commands.yaml"
        import yaml
        commands_file.write_text(
            yaml.safe_dump({"commands": commands}), encoding="utf-8"
        )
        output_dir = Path(tmpdir) / "output"
        common_args = [
            "--commands-file", str(commands_file),
            "--output-dir", str(output_dir),
            "--cwd", ".",
            "--run-id", "immutable-test",
        ]
        first_code, _, first_stderr = run_evidence_gen(common_args)
        assert first_code in (0, 2), first_stderr
        bundle = find_published_bundle(output_dir)
        before = bundle.read_bytes()

        second_code, _, _ = run_evidence_gen(common_args)
        assert second_code == 1
        assert bundle.read_bytes() == before


def test_evidence_validator_detects_persisted_log_tampering():
    """Changing a persisted log breaks stream, combined, and artifact hashes."""
    commands = {
        "test_pass": {
            "command": ["python", "-c", "print('hash me')"],
            "expected_exit_codes": [0],
            "timeout": 10,
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        commands_file = Path(tmpdir) / "commands.yaml"
        import yaml
        commands_file.write_text(
            yaml.safe_dump({"commands": commands}), encoding="utf-8"
        )
        output_dir = Path(tmpdir) / "output"
        code, _, stderr = run_evidence_gen([
            "--commands-file", str(commands_file),
            "--output-dir", str(output_dir),
            "--cwd", ".",
        ])
        assert code in (0, 2), stderr
        bundle = find_published_bundle(output_dir)

        validator = [
            sys.executable,
            "scripts/verification/validate_evidence_bundle.py",
            str(bundle),
        ]
        valid = subprocess.run(validator, capture_output=True, text=True, timeout=30)
        assert valid.returncode == 0, valid.stdout + valid.stderr

        receipt = json.loads(bundle.read_text(encoding="utf-8"))["commands"][0]
        stdout_log = bundle.parent / receipt["log_paths"]["stdout_log"]
        stdout_log.write_bytes(stdout_log.read_bytes() + b"tampered")
        invalid = subprocess.run(
            validator, capture_output=True, text=True, timeout=30
        )
        assert invalid.returncode == 1
        assert "mismatch" in invalid.stdout


def test_validation_failure_does_not_publish():
    """A non-Git cwd cannot produce schema-valid Git identity evidence."""
    commands = {
        "test_pass": {
            "command": ["python", "-c", "print('hello')"],
            "expected_exit_codes": [0],
            "timeout": 10,
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        commands_file = tmp_path / "commands.yaml"
        import yaml
        commands_file.write_text(
            yaml.safe_dump({"commands": commands}), encoding="utf-8"
        )
        output_dir = tmp_path / "output"
        code, _, stderr = run_evidence_gen([
            "--commands-file", str(commands_file),
            "--output-dir", str(output_dir),
            "--cwd", str(tmp_path),
        ])
        assert code == 1
        assert "not published" in stderr
        assert not list(output_dir.glob("runs/*"))
        assert not list(output_dir.glob("quarantine/*"))
        assert not (output_dir / "latest.json").exists()


def test_failed_command_never_updates_existing_latest_pointer():
    """A FAIL run is quarantined without touching authoritative selection."""
    commands = {
        "test_fail": {
            "command": ["python", "-c", "import sys; sys.exit(7)"],
            "expected_exit_codes": [0],
            "timeout": 10,
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        commands_file = tmp_path / "commands.yaml"
        import yaml
        commands_file.write_text(
            yaml.safe_dump({"commands": commands}), encoding="utf-8"
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        latest = output_dir / "latest.json"
        sentinel = b'{"run_id":"known-good"}\n'
        latest.write_bytes(sentinel)

        code, _, stderr = run_evidence_gen([
            "--commands-file", str(commands_file),
            "--output-dir", str(output_dir),
            "--cwd", ".",
        ])
        assert code == 1, stderr
        assert latest.read_bytes() == sentinel
        assert list(output_dir.glob("quarantine/*/evidence_bundle.json"))


def test_command_registry_is_the_single_canonical_source():
    """The generator and CI must not drift between duplicate registries."""
    import yaml

    legacy_registry = CANONICAL_REGISTRY.with_name("phase7_commands.yaml")
    assert CANONICAL_REGISTRY.is_file()
    assert not legacy_registry.exists()

    payload = yaml.safe_load(CANONICAL_REGISTRY.read_text(encoding="utf-8"))
    for name, spec in payload["commands"].items():
        assert spec["required"] is True, name
        assert spec["shell"] in {"process", "pwsh"}, name
        assert isinstance(spec["argv"], list) and spec["argv"], name
        assert isinstance(spec["timeout"], int) and spec["timeout"] > 0, name
        assert spec["expected_exit_codes"], name

    workflow = (ROOT / ".github" / "workflows" / "ci.yaml").read_text(
        encoding="utf-8"
    )
    assert "scripts/verification/command_registry.yaml" in workflow
    assert "phase7_commands.yaml" not in workflow


def test_optional_commands_do_not_affect_generated_verdict():
    """Only commands explicitly selected as required are executed."""
    commands = {
        "required_pass": {
            "required": True,
            "argv": ["python", "-c", "print('required')"],
            "expected_exit_codes": [0],
            "timeout": 10,
        },
        "optional_fail": {
            "required": False,
            "argv": ["python", "-c", "import sys; sys.exit(9)"],
            "expected_exit_codes": [0],
            "timeout": 10,
        },
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        import yaml

        tmp_path = Path(tmpdir)
        commands_file = tmp_path / "commands.yaml"
        commands_file.write_text(
            yaml.safe_dump({"commands": commands}), encoding="utf-8"
        )
        output_dir = tmp_path / "output"
        code, _, stderr = run_evidence_gen(
            [
                "--commands-file",
                str(commands_file),
                "--output-dir",
                str(output_dir),
                "--cwd",
                ".",
            ]
        )
        assert code in (0, 2), stderr
        bundle = json.loads(
            find_published_bundle(output_dir).read_text(encoding="utf-8")
        )
        assert set(bundle["results"]) == {"required_pass"}
        assert [item["command_id"] for item in bundle["commands"]] == [
            "required_pass"
        ]


def test_finalizer_cannot_promote_missing_required_evidence():
    """A claimed PASS cannot override a missing required gate."""
    sys.path.insert(0, str(ROOT / "scripts" / "verification"))
    from finalize_evidence import derive_verdict

    bundle = {
        "verdict": "PASS",
        "worktree_clean": True,
        "commands": [],
        "results": {},
        "failures": [],
    }
    result = derive_verdict(
        bundle,
        {
            "required_check": {
                "expected_exit_codes": [0],
            }
        },
    )
    assert result["status"] == "FAIL"
    assert result["verdict"] == "FAIL"
    assert result["gates"] == {"required_check": False}


def test_receipt_handles_invalid_utf8_and_paths_with_spaces():
    """Persisted logs are valid UTF-8 and path handling is argv-safe."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "directory with spaces"
        root.mkdir()
        output = root / "receipt output" / "invalid_utf8.json"
        command = [
            sys.executable,
            "scripts/verification/run_command_receipt.py",
            "--name",
            "invalid_utf8",
            "--cwd",
            ".",
            "--output",
            str(output),
            "--",
            sys.executable,
            "-c",
            "import os; os.write(1, b'good\\xffbad')",
        ]
        completed = subprocess.run(
            command, capture_output=True, timeout=30, cwd=ROOT
        )
        assert completed.returncode == 0, completed.stderr

        receipt = json.loads(output.read_text(encoding="utf-8"))
        stdout = (output.parent.parent / receipt["log_paths"]["stdout_log"]).read_bytes()
        assert stdout.decode("utf-8") == "good\ufffdbad"
        assert receipt["stdout_sha256"] == hashlib.sha256(stdout).hexdigest()


def test_receipt_redacts_secrets_from_argv_env_and_logs():
    """No raw secret may reach command output, receipt, or persisted logs."""
    secret = "supersecretvalue123456"
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "receipts" / "secret.json"
        command = [
            sys.executable,
            "scripts/verification/run_command_receipt.py",
            "--name",
            "secret_redaction",
            "--output",
            str(output),
            "--env",
            f"MY_TOKEN={secret}",
            "--",
            sys.executable,
            "-c",
            (
                "import os,sys; "
                "print('token=' + os.environ['MY_TOKEN']); "
                "print('password: ' + os.environ['MY_TOKEN'], file=sys.stderr)"
            ),
            "--token",
            secret,
        ]
        completed = subprocess.run(command, capture_output=True, timeout=30)
        assert completed.returncode == 0, completed.stderr

        receipt_bytes = output.read_bytes()
        receipt = json.loads(receipt_bytes)
        stdout = (output.parent.parent / receipt["log_paths"]["stdout_log"]).read_bytes()
        stderr = (output.parent.parent / receipt["log_paths"]["stderr_log"]).read_bytes()
        assert secret.encode() not in completed.stdout
        assert secret.encode() not in completed.stderr
        assert secret.encode() not in receipt_bytes
        assert secret.encode() not in stdout
        assert secret.encode() not in stderr


def test_receipt_runner_classifies_interrupt_and_execution_error(monkeypatch):
    """Interrupts and launch errors must not be mislabeled as timeouts."""
    sys.path.insert(0, str(ROOT / "scripts" / "verification"))
    import run_command_receipt

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(run_command_receipt.subprocess, "run", interrupt)
    exit_code, _, stderr, _ = run_command_receipt.run_command(
        ["ignored"], ROOT, timeout=1
    )
    assert exit_code == -2
    assert stderr == b"INTERRUPTED"
    assert run_command_receipt.classify_result(exit_code, [0]) == "INTERRUPTED"

    def launch_error(*args, **kwargs):
        raise OSError("launch failed")

    monkeypatch.setattr(run_command_receipt.subprocess, "run", launch_error)
    exit_code, _, stderr, _ = run_command_receipt.run_command(
        ["ignored"], ROOT, timeout=1
    )
    assert exit_code == -3
    assert b"launch failed" in stderr
    assert run_command_receipt.classify_result(exit_code, [0]) == "FAILURE"
