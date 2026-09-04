"""Phase 3 contract tests: platform seams stay generic and usable."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterable, AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from typing import Literal

import pytest
from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.kernel.types.json import JSONValue
from windagent.platform.artifacts import ArtifactReference, ArtifactStore
from windagent.platform.commands import Command, CommandBus, CommandHandler
from windagent.platform.events import EventBus, EventHandler, EventPublisher, EventSubscription
from windagent.platform.jobs import JobHandler, JobQueue, JobReceipt, JobScheduler, JobSubmission
from windagent.platform.modules import ModuleDescriptor, ModuleRegistry
from windagent.platform.observability import Telemetry, TelemetryAttributes, TelemetrySpan
from windagent.platform.persistence import UnitOfWork
from windagent.platform.queries import Query, QueryBus, QueryHandler
from windagent.platform.security import (
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyRequest,
    SecretStore,
    SecretValue,
)


@dataclass(frozen=True)
class EchoCommand(Command[str]):
    value: str


class EchoCommandHandler:
    async def handle(self, command: EchoCommand) -> str:
        return command.value


class EchoCommandBus:
    async def dispatch(self, command: Command[str]) -> str:
        assert isinstance(command, EchoCommand)
        return command.value


@dataclass(frozen=True)
class EchoQuery(Query[str]):
    value: str


class EchoQueryHandler:
    async def handle(self, query: EchoQuery) -> str:
        return query.value


class EchoQueryBus:
    async def ask(self, query: Query[str]) -> str:
        assert isinstance(query, EchoQuery)
        return query.value


@pytest.mark.asyncio
async def test_command_and_query_contracts_are_implementation_neutral() -> None:
    command = EchoCommand("command-result")
    query = EchoQuery("query-result")
    command_handler = EchoCommandHandler()
    command_bus = EchoCommandBus()
    query_handler = EchoQueryHandler()
    query_bus = EchoQueryBus()

    assert isinstance(command_handler, CommandHandler)
    assert isinstance(command_bus, CommandBus)
    assert isinstance(query_handler, QueryHandler)
    assert isinstance(query_bus, QueryBus)
    assert await command_handler.handle(command) == "command-result"
    assert await command_bus.dispatch(command) == "command-result"
    assert await query_handler.handle(query) == "query-result"
    assert await query_bus.ask(query) == "query-result"


@dataclass
class InMemoryModuleRegistry:
    descriptors: dict[str, ModuleDescriptor] = field(default_factory=dict)

    def register(self, descriptor: ModuleDescriptor) -> None:
        self.descriptors[descriptor.module_id] = descriptor

    def get(self, module_id: str) -> ModuleDescriptor | None:
        return self.descriptors.get(module_id)

    def all(self) -> tuple[ModuleDescriptor, ...]:
        return tuple(self.descriptors.values())


def test_module_registry_contract_has_stable_domain_neutral_identity() -> None:
    descriptor = ModuleDescriptor("example.module", "1.0.0", ("sample.read", "sample.write"))
    registry = InMemoryModuleRegistry()

    assert isinstance(registry, ModuleRegistry)
    registry.register(descriptor)
    assert registry.get("example.module") == descriptor
    assert registry.all() == (descriptor,)

    with pytest.raises(ValueError, match="duplicates"):
        ModuleDescriptor("example.module", "1.0.0", ("sample.read", "sample.read"))


class ExampleJobHandler:
    job_type = "example.render"

    async def handle(self, payload: Mapping[str, JSONValue]) -> object:
        return payload["value"]


class ExampleJobQueue:
    async def submit(self, job: JobSubmission) -> JobReceipt:
        assert job.job_type == "example.render"
        return JobReceipt(EntityId.new())


class ExampleJobScheduler:
    async def schedule(self, job: JobSubmission, *, run_at: datetime) -> JobReceipt:
        assert job.job_type == "example.render"
        assert run_at.tzinfo is not None
        return JobReceipt(EntityId.new())


@pytest.mark.asyncio
async def test_job_contracts_accept_json_safe_submission_without_runtime_semantics() -> None:
    job = JobSubmission(" example.render ", {"value": ["one", "two"]})
    handler = ExampleJobHandler()
    queue = ExampleJobQueue()
    scheduler = ExampleJobScheduler()

    assert job.job_type == "example.render"
    assert isinstance(handler, JobHandler)
    assert isinstance(queue, JobQueue)
    assert isinstance(scheduler, JobScheduler)
    assert await handler.handle(job.payload) == ("one", "two")
    assert isinstance(await queue.submit(job), JobReceipt)
    assert isinstance(
        await scheduler.schedule(job, run_at=datetime.now(tz=UTC)), JobReceipt
    )

    with pytest.raises(TypeError):
        job.payload["value"] = "mutated"  # type: ignore[index]


class ExampleSubscription:
    async def unsubscribe(self) -> None:
        return None


class ExampleEventHandler:
    async def handle(self, event: EventEnvelope) -> None:
        assert event.event_type == "example.completed"


class ExampleEventBus:
    async def subscribe(self, event_type: str, handler: EventHandler) -> EventSubscription:
        assert event_type == "example.completed"
        return ExampleSubscription()

    async def publish(self, event: EventEnvelope) -> None:
        assert event.event_type == "example.completed"


class ExampleEventPublisher:
    async def publish(self, event: EventEnvelope) -> None:
        assert event.event_type == "example.completed"


@pytest.mark.asyncio
async def test_event_contracts_keep_delivery_separate_from_envelopes() -> None:
    event = EventEnvelope(
        event_type="example.completed",
        aggregate_type="example",
        aggregate_id=EntityId.new(),
        sequence=0,
    )
    handler = ExampleEventHandler()
    bus = ExampleEventBus()
    publisher = ExampleEventPublisher()

    assert isinstance(handler, EventHandler)
    assert isinstance(bus, EventBus)
    assert isinstance(publisher, EventPublisher)
    await handler.handle(event)
    subscription = await bus.subscribe(event.event_type, handler)
    assert isinstance(subscription, EventSubscription)
    await bus.publish(event)
    await publisher.publish(event)
    await subscription.unsubscribe()


class TrackingUnitOfWork(UnitOfWork):
    committed = False
    rolled_back = False

    async def __aenter__(self) -> TrackingUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        return False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


@pytest.mark.asyncio
async def test_unit_of_work_is_an_explicit_async_transaction_boundary() -> None:
    unit_of_work = TrackingUnitOfWork()

    assert inspect.isabstract(UnitOfWork)
    async with unit_of_work:
        await unit_of_work.commit()
    assert unit_of_work.committed
    assert not unit_of_work.rolled_back


async def _empty_bytes() -> AsyncIterator[bytes]:
    chunks: tuple[bytes, ...] = ()
    for chunk in chunks:
        yield chunk


class ExampleArtifactStore:
    async def put(
        self,
        content: AsyncIterable[bytes],
        *,
        content_type: str,
        filename: str | None = None,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> ArtifactReference:
        async for _ in content:
            pass
        return ArtifactReference(EntityId.new(), content_type, 0, filename, metadata or {})

    def read(self, reference: ArtifactReference) -> AsyncIterator[bytes]:
        return _empty_bytes()

    async def delete(self, reference: ArtifactReference) -> bool:
        return True


def test_artifact_reference_is_validated_and_metadata_is_immutable() -> None:
    reference = ArtifactReference(
        EntityId.new(), " application/octet-stream ", 0, metadata={"source": "test"}
    )

    assert isinstance(ExampleArtifactStore(), ArtifactStore)
    assert reference.content_type == "application/octet-stream"
    with pytest.raises(TypeError):
        reference.metadata["source"] = "mutated"  # type: ignore[index]
    with pytest.raises(ValueError, match="non-negative"):
        ArtifactReference(EntityId.new(), "text/plain", -1)


@dataclass
class ExampleSecretStore:
    values: dict[str, SecretValue] = field(default_factory=dict)

    async def read(self, name: str) -> SecretValue | None:
        return self.values.get(name)

    async def write(self, name: str, value: SecretValue) -> None:
        self.values[name] = value

    async def delete(self, name: str) -> bool:
        return self.values.pop(name, None) is not None


class ExamplePolicyEngine:
    async def decide(self, request: PolicyRequest) -> PolicyDecision:
        assert request.action == "example.execute"
        return PolicyDecision(PolicyEffect.REQUIRE_APPROVAL, policy_id="example-policy")


@pytest.mark.asyncio
async def test_security_contracts_support_explicit_policy_and_redacted_secret_access() -> None:
    request = PolicyRequest(" example.execute ", "example-resource", context={"input": "safe"})
    secret = SecretValue("not-for-logs")
    secret_store = ExampleSecretStore()
    policy_engine = ExamplePolicyEngine()

    assert isinstance(secret_store, SecretStore)
    assert isinstance(policy_engine, PolicyEngine)
    assert str(secret) == "<redacted>"
    assert "not-for-logs" not in repr(secret)
    assert secret.reveal() == "not-for-logs"
    await secret_store.write("example-token", secret)
    assert await secret_store.read("example-token") == secret
    assert (await policy_engine.decide(request)).effect is PolicyEffect.REQUIRE_APPROVAL
    with pytest.raises(TypeError):
        request.context["input"] = "mutated"  # type: ignore[index]


@dataclass
class ExampleSpan:
    attributes: dict[str, object] = field(default_factory=dict)
    ended: bool = False

    def set_attribute(self, name: str, value: str | int | float | bool) -> None:
        self.attributes[name] = value

    def record_exception(self, error: BaseException) -> None:
        self.attributes["exception.type"] = type(error).__name__

    def end(self) -> None:
        self.ended = True


@dataclass
class ExampleTelemetry:
    events: list[tuple[str, TelemetryAttributes | None]] = field(default_factory=list)

    def start_span(
        self, name: str, *, attributes: TelemetryAttributes | None = None
    ) -> TelemetrySpan:
        span = ExampleSpan()
        span.set_attribute("span.name", name)
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        return span

    def emit_event(self, name: str, *, attributes: TelemetryAttributes | None = None) -> None:
        self.events.append((name, attributes))

    def increment_counter(
        self, name: str, *, value: int = 1, attributes: TelemetryAttributes | None = None
    ) -> None:
        self.events.append((f"counter:{name}:{value}", attributes))

    def observe_histogram(
        self, name: str, value: float, *, attributes: TelemetryAttributes | None = None
    ) -> None:
        self.events.append((f"histogram:{name}:{value}", attributes))


def test_telemetry_contract_can_be_implemented_without_a_vendor_sdk() -> None:
    telemetry = ExampleTelemetry()

    assert isinstance(telemetry, Telemetry)
    span = telemetry.start_span("example.operation", attributes={"attempt": 1})
    assert isinstance(span, TelemetrySpan)
    span.record_exception(ValueError("expected"))
    span.end()
    telemetry.emit_event("example.completed")
    telemetry.increment_counter("example.jobs")
    telemetry.observe_histogram("example.duration", 1.25)

    assert len(telemetry.events) == 3
