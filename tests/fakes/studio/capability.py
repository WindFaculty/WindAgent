from __future__ import annotations

from windagent_core.contracts.studio.capabilities import CapabilityStatus, RuntimeCapability, RuntimeCapabilityProfile

class FakeCapabilityPort:
    """Test capability port: everything available, nothing fail-closed."""

    async def get_capabilities(self) -> RuntimeCapabilityProfile:
        return RuntimeCapabilityProfile(
            capabilities=[
                RuntimeCapability(
                    name="durable_db", status=CapabilityStatus.AVAILABLE, source="fake", reason="test double"
                ),
                RuntimeCapability(
                    name="studio_orchestration",
                    status=CapabilityStatus.AVAILABLE,
                    source="fake",
                    reason="test double",
                ),
                RuntimeCapability(
                    name="worker", status=CapabilityStatus.AVAILABLE, source="fake", reason="test double"
                ),
                RuntimeCapability(
                    name="model_route", status=CapabilityStatus.AVAILABLE, source="fake", reason="test double"
                ),
                RuntimeCapability(
                    name="story_engine", status=CapabilityStatus.AVAILABLE, source="fake", reason="test double"
                ),
            ],
            fail_closed_flags=[],
            certification_mode=True,
        )


__all__ = ["FakeCapabilityPort"]
