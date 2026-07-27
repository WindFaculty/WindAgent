"""
Canonical version service for WindAgent.
Single source of truth for product version derived from package metadata.
Architecture generation and protocol versions are separate constants.
"""

from importlib.metadata import version as _pkg_version, PackageNotFoundError
from typing import Final

# Product version: single source of truth from package metadata
try:
    PRODUCT_VERSION: Final[str] = _pkg_version("windagent-core")
except PackageNotFoundError:
    # Fallback for development / editable installs
    PRODUCT_VERSION: Final[str] = "0.3.0"

# Architecture generation - separate from product version
ARCHITECTURE_GENERATION: Final[str] = "v2"

# API version - separate from product version
API_VERSION: Final[str] = "v2"

# Provider protocol version - separate from product version
PROVIDER_PROTOCOL_VERSION: Final[str] = "1.0.0"

# Artifact protocol version - separate from product version
ARTIFACT_PROTOCOL_VERSION: Final[str] = "1.0.0"


def get_product_version() -> str:
    """Get the canonical product version from package metadata."""
    return PRODUCT_VERSION


def get_architecture_generation() -> str:
    """Get the architecture generation identifier."""
    return ARCHITECTURE_GENERATION


def get_api_version() -> str:
    """Get the API version."""
    return API_VERSION


def get_provider_protocol_version() -> str:
    """Get the provider protocol version."""
    return PROVIDER_PROTOCOL_VERSION


def get_artifact_protocol_version() -> str:
    """Get the artifact protocol version."""
    return ARTIFACT_PROTOCOL_VERSION


def get_version_info() -> dict:
    """Get complete version information as a dictionary."""
    return {
        "product_version": PRODUCT_VERSION,
        "architecture_generation": ARCHITECTURE_GENERATION,
        "api_version": API_VERSION,
        "provider_protocol_version": PROVIDER_PROTOCOL_VERSION,
        "artifact_protocol_version": ARTIFACT_PROTOCOL_VERSION,
    }