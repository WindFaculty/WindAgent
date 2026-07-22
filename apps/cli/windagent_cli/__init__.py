"""
WindAgent CLI entrypoint (doctor, architecture check, workflow run)
"""

from windagent_cli.main import main, doctor, architecture_check

__version__ = "0.3.0"
__all__ = ["main", "doctor", "architecture_check"]
