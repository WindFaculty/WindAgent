"""
Deterministic fixture model port (B2 step 6) — unit tests only.

Implements the frozen ``PreproductionModelPort`` protocol with pinned
responses keyed by capability. NEVER used in production: certification
profiles reject fixture providers via ``assert_not_fixture`` (the fake
rejection contract), and a fixture provider that refuses (``reject=True``)
makes callers fail closed instead of silently accepting canned output.
"""

from __future__ import annotations

from typing import Dict, Optional

from windagent_intelligence.video.ports import (
    ModelCompletionRequest,
    ModelCompletionResult,
    PreproductionModelPort,
)

FIXTURE_PROVIDER = "fixture"


class FixtureModelPort:
    """In-memory deterministic fake of ``PreproductionModelPort``.

    ``responses`` maps capability -> pinned content. ``reject=True`` makes
    ``complete`` raise (proves callers fail closed on a refusing fake).
    """

    #: Marker consumed by ``is_fixture_provider`` / ``assert_not_fixture``.
    fixture = True

    def __init__(
        self,
        responses: Optional[Dict[str, str]] = None,
        *,
        default: str = "",
        reject: bool = False,
    ) -> None:
        self.responses = dict(responses or {})
        self.default = default
        self.reject = reject
        self.requests: list[ModelCompletionRequest] = []

    async def complete(self, request: ModelCompletionRequest) -> ModelCompletionResult:
        if self.reject:
            raise RuntimeError("fixture model port rejected the completion request")
        self.requests.append(request)
        content = self.responses.get(request.capability, self.default)
        return ModelCompletionResult(
            capability=request.capability,
            content=content,
            finish_reason="stop",
            provider=FIXTURE_PROVIDER,
            usage={
                "prompt_tokens": len(request.user) // 4,
                "completion_tokens": len(content) // 4,
            },
        )


def is_fixture_provider(port: object) -> bool:
    """True when the port is a fixture fake (certification rejects those)."""
    return bool(getattr(port, "fixture", False))


def assert_not_fixture(port_or_result: object) -> None:
    """Fail closed when a fixture provider/result would reach certification."""
    if is_fixture_provider(port_or_result):
        raise RuntimeError(
            "fixture model provider must never be used in a certification profile"
        )
    provider = getattr(port_or_result, "provider", None)
    if provider == FIXTURE_PROVIDER:
        raise RuntimeError(
            f"result provenance provider {provider!r} is the fixture fake; "
            "certification rejects canned model output"
        )


__all__ = [
    "FIXTURE_PROVIDER",
    "FixtureModelPort",
    "is_fixture_provider",
    "assert_not_fixture",
]
