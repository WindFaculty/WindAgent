"""
Optimistic Concurrency Control (OCC) helpers and models for Unified API V3.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from windagent_api.routers.v3.common.problems import ApiProblemException


class ExpectedVersionMutation(BaseModel):
    """
    Base mixin for all mutating requests requiring optimistic concurrency checks.
    """
    expected_version: int = Field(
        ...,
        description="The integer version of the resource the client expects to mutate"
    )


class VersionConflictError(ApiProblemException):
    """Raised when an expected_version mismatch is detected on a mutating request."""
    def __init__(self, resource_id: str, current_version: int, expected_version: int):
        super().__init__(
            status_code=409,
            title="Version Conflict",
            detail=f"Resource '{resource_id}' version mismatch. Current version is {current_version}, but request expected {expected_version}.",
            code="VERSION_CONFLICT",
            type_uri="https://windagent.dev/problems/version-conflict",
            retryable=True,
            details={
                "resource_id": resource_id,
                "current_version": current_version,
                "expected_version": expected_version
            }
        )


def check_optimistic_concurrency(resource_id: str, current_version: int, expected_version: int) -> None:
    """Validate expected_version against current resource version; raise 409 if mismatched."""
    if current_version != expected_version:
        raise VersionConflictError(
            resource_id=resource_id,
            current_version=current_version,
            expected_version=expected_version
        )
