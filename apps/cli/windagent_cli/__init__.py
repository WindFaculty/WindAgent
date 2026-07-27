"""
WindAgent CLI entrypoint (doctor, architecture check, workflow run)
"""

from windagent_core.version import PRODUCT_VERSION

from windagent_cli.main import main, doctor, architecture_check

__version__ = PRODUCT_VERSION
__all__ = ["main", "doctor", "architecture_check"]
