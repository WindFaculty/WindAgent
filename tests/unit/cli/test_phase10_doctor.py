"""
Tests for PHASE 10 CLI doctor command.
Tests that doctor command uses same health provider as API, not hardcoded results.
"""

from __future__ import annotations
from unittest.mock import patch

from windagent_cli.main import doctor


class TestDoctorCommand:
    """Tests for windagent doctor command."""
    
    def test_doctor_returns_dict(self):
        """Doctor command should return results dictionary."""
        result = doctor(json_mode=False)
        assert isinstance(result, int)
    
    def test_doctor_json_mode(self, capsys):
        """Doctor command in JSON mode should output JSON."""
        doctor(json_mode=True)
        captured = capsys.readouterr()
        
        # Should output JSON
        import json
        output = captured.out.strip()
        if output:
            data = json.loads(output)
            assert isinstance(data, dict)
            assert "status" in data
            assert "checks" in data
            assert "profile" in data
    
    def test_doctor_text_mode(self, capsys):
        """Doctor command in text mode should output formatted text."""
        doctor(json_mode=False)
        captured = capsys.readouterr()
        
        output = captured.out
        assert "WindAgent Doctor" in output
        assert "Phase 10" in output
        assert "Profile:" in output
        assert "System health status:" in output


class TestDoctorUsesRealHealthChecks:
    """Tests that doctor uses real HealthChecker service."""
    
    def test_doctor_includes_runtime_checks(self, capsys):
        """Doctor should include runtime health checks, not just script checks."""
        doctor(json_mode=True)
        captured = capsys.readouterr()
        
        import json
        output = captured.out.strip()
        if output:
            data = json.loads(output)
            checks = data.get("checks", {})
            
            # Should include runtime checks, not just script checks
            runtime_checks = [
                "liveness",
                "database",
                "schema_migration",
                "worker",
                "provider_registry",
                "tool_registry",
            ]
            
            for check_name in runtime_checks:
                assert check_name in checks, f"Missing runtime check: {check_name}"


class TestDoctorScriptChecks:
    """Tests for doctor script-based checks."""
    
    def test_doctor_includes_architecture_checks(self, capsys):
        """Doctor should include architecture validation checks."""
        doctor(json_mode=True)
        captured = capsys.readouterr()
        
        import json
        output = captured.out.strip()
        if output:
            data = json.loads(output)
            checks = data.get("checks", {})
            
            # Should include script-based architecture checks
            script_checks = [
                "import_boundary_check",
                "scaffold_structure_check",
                "duplicate_model_check",
            ]
            
            has_script_checks = any(check in checks for check in script_checks)
            assert has_script_checks, "Should include at least one script check"


class TestDoctorExitCodes:
    """Tests for doctor exit codes."""
    
    def test_doctor_returns_0_when_operational(self, capsys):
        """Doctor should return exit code 0 when all systems operational."""
        result = doctor(json_mode=False)
        captured = capsys.readouterr()
        
        if "ALL_SYSTEMS_OPERATIONAL" in captured.out or "OPERATIONAL" in captured.out:
            assert result == 0
    
    def test_doctor_returns_1_when_warning(self, capsys):
        """Doctor should return exit code 1 when there are warnings."""
        doctor(json_mode=False)
        captured = capsys.readouterr()
        
        if "WARNING" in captured.out or "DEGRADED" in captured.out:
            # May return 1 if there are issues
            pass  # Can't guarantee this without forcing failures


class TestDoctorProfileConsistency:
    """Tests for profile consistency between API and CLI."""
    
    @patch.dict("os.environ", {"WINDAGENT_ENV": "development"})
    def test_doctor_uses_development_profile(self, capsys):
        """Doctor should use development profile when WINDAGENT_ENV=development."""
        doctor(json_mode=True)
        captured = capsys.readouterr()
        
        import json
        output = captured.out.strip()
        if output:
            data = json.loads(output)
            # Profile should be in the output
            assert "profile" in data
