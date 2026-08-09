"""B2 unit tests: fixture model port + fake rejection contract."""

from __future__ import annotations

import pytest

from windagent_intelligence.story.prompts import (
    FIXTURE_PROVIDER,
    FixtureModelPort,
    StoryModelBoundary,
    assert_not_fixture,
    is_fixture_provider,
)
from windagent_intelligence.video.ports import ModelCompletionRequest

VALID_BRIEF = (
    '{"title": "T", "logline": "l", "genre": "g", "tone": "t", '
    '"audience": "5-8", "target_duration_seconds": 60}'
)


def test_fixture_port_returns_pinned_content_by_capability():
    port = FixtureModelPort({"brief_expansion": VALID_BRIEF})
    assert is_fixture_provider(port)

    async def run():
        return await port.complete(
            ModelCompletionRequest(capability="brief_expansion", system="s", user="u")
        )

    import asyncio

    result = asyncio.run(run())
    assert result.content == VALID_BRIEF
    assert result.provider == FIXTURE_PROVIDER
    assert result.usage["completion_tokens"] > 0


def test_fixture_port_default_empty():
    port = FixtureModelPort()
    import asyncio

    result = asyncio.run(
        port.complete(ModelCompletionRequest(capability="unknown", system="s", user="u"))
    )
    assert result.content == ""


def test_fixture_rejection_makes_caller_fail_closed():
    """A refusing fake must surface as a failure, never silent canned output."""
    port = FixtureModelPort({"brief_expansion": VALID_BRIEF}, reject=True)
    boundary = StoryModelBoundary(port)

    async def run():
        return await boundary.invoke(
            "story.brief_expansion.expand", variables={"idea": "x"}
        )

    import asyncio

    with pytest.raises(Exception):
        asyncio.run(run())


def test_fixture_provider_rejected_in_certification():
    port = FixtureModelPort({"brief_expansion": VALID_BRIEF})
    with pytest.raises(RuntimeError, match="fixture"):
        assert_not_fixture(port)


def test_assert_not_fixture_accepts_real_shaped_port():
    class RealPort:
        fixture = False

        async def complete(self, request):  # pragma: no cover - fake
            raise NotImplementedError

    assert_not_fixture(RealPort())


def test_assert_not_fixture_rejects_fixture_provenance():
    import asyncio

    port = FixtureModelPort({"brief_expansion": VALID_BRIEF})
    boundary = StoryModelBoundary(port)
    result = asyncio.run(
        boundary.invoke("story.brief_expansion.expand", variables={"idea": "x"})
    )
    with pytest.raises(RuntimeError, match="fixture"):
        assert_not_fixture(result.provenance)
