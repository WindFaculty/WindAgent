"""
RFC 7807 Problem Details for HTTP APIs (ApiProblem) for Unified API V3.
"""

from __future__ import annotations
from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ApiProblem(BaseModel):
    """
    Authoritative RFC 7807 error model for all V3 API endpoints.
    """
    type: str = Field(
        default="https://windagent.dev/problems/general",
        description="URI reference identifying the problem type"
    )
    title: str = Field(..., description="Short, human-readable summary of problem")
    status: int = Field(..., description="HTTP status code")
    detail: str = Field(..., description="Detailed explanation specific to this occurrence")
    code: str = Field(..., description="Machine-readable invariant error code")
    correlation_id: Optional[str] = Field(
        default=None, description="End-to-end distributed tracing correlation ID"
    )
    retryable: bool = Field(
        default=False, description="Indicates if client may retry request without modifications"
    )
    details: Dict[str, Any] = Field(
        default_factory=dict, description="Additional context, field errors, or metadata"
    )


class ApiProblemException(Exception):
    """Base exception for raising typed ApiProblems across V3 services."""
    def __init__(
        self,
        status_code: int,
        title: str,
        detail: str,
        code: str,
        type_uri: str = "https://windagent.dev/problems/general",
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ):
        super().__init__(detail)
        self.problem = ApiProblem(
            type=type_uri,
            title=title,
            status=status_code,
            detail=detail,
            code=code,
            retryable=retryable,
            details=details or {},
            correlation_id=correlation_id,
        )


async def api_problem_exception_handler(request: Request, exc: ApiProblemException) -> JSONResponse:
    problem = exc.problem
    if not problem.correlation_id:
        problem.correlation_id = getattr(request.state, "correlation_id", None) or request.headers.get("X-Correlation-ID")
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )
