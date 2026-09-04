"""The API application factory — the only composition root for HTTP.

Composition order (plan sections 12 and 13):

    settings → database → security stack → buses → module bootstrap → app

Module manifests are discovered from ``windagent.modules`` (feature modules)
plus the app-owned manifests (system, debug).  Nothing else in the app may
build infrastructure; routers only ever see the buses through app.state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from windagent import __version__ as WINDAGENT_VERSION
from windagent.platform.configuration.settings import Settings
from windagent.platform.jobs import DurableJobQueue
from windagent.platform.modules import (
    InMemoryModuleRegistry,
    ModuleLoader,
    ModuleManifest,
    PackageModuleDiscovery,
    StaticModuleDiscovery,
)
from windagent.platform.observability import (
    MetricsExporter,
    RuntimeTelemetry,
    Telemetry,
    configure_structured_logging,
)
from windagent.platform.persistence import Database
from windagent.platform.realtime import RealtimeHub
from windagent.platform.security import (
    AuditSink,
    Authenticator,
    EnvironmentSecretStore,
    HmacTokenAuthenticator,
    InMemoryIdentityStore,
    PolicyEngine,
    RateLimiter,
    RuleBasedPolicyEngine,
    SlidingWindowRateLimiter,
)

from ..api import API_VERSION, build_api_router
from ..api.system import build_system_manifest
from ..auth import AuthenticationMiddleware
from ..debug import build_debug_manifest, create_debug_jobs_router
from ..errors import DomainErrorStatusMapper, install_error_handlers
from ..health import create_health_router
from ..middleware import RateLimitMiddleware, RequestContextMiddleware
from ..observability import create_metrics_router
from .audit_outbox import OutboxAuditSink
from .buses import InProcessCommandBus, InProcessQueryBus
from .module_runtime import ApiModuleRuntime


def create_app(
    settings: Settings | None = None,
    *,
    job_queue: DurableJobQueue | None = None,
    realtime_hub: RealtimeHub | None = None,
    database: Database | None = None,
    manifests: Iterable[ModuleManifest] = (),
    authenticator: Authenticator | None = None,
    policy_engine: PolicyEngine | None = None,
    audit_sink: AuditSink | None = None,
    rate_limiter: RateLimiter | None = None,
    telemetry: Telemetry | None = None,
) -> FastAPI:
    """Build the V2 API application.

    Args:
        settings: Optional pre-loaded settings; otherwise loaded from the
            environment (``windagent.platform.configuration``).
        job_queue: Explicit durable queue.  When omitted, no debug surface
            is mounted — production apps never expose it implicitly.
        realtime_hub: Realtime replay hub backing the debug websocket.
        database: Explicit database; otherwise built from settings.
        manifests: Extra app-owned manifests (used by tests and embeddings).
        authenticator: Verified credential checker; when ``None`` and
            ``settings.auth_enabled`` is true, a default HMAC-token stack is
            composed from the environment secret store.
        policy_engine: Authorization authority; defaults to an empty
            (deny-all) rule engine when authentication is enabled.
        audit_sink: Audit destination; defaults to the durable outbox sink.
        rate_limiter: Per-client limiter; defaults from
            ``settings.rate_limit_per_minute`` when positive.
        telemetry: Vendor-neutral logging, metrics, and tracing runtime.
    """
    app_settings = settings if settings is not None else Settings()
    app_database = (
        database if database is not None else Database.from_settings(app_settings)
    )

    if authenticator is None and app_settings.auth_enabled:
        authenticator = HmacTokenAuthenticator(
            EnvironmentSecretStore(), InMemoryIdentityStore()
        )
    if policy_engine is None and app_settings.auth_enabled:
        # No rules yet: fail closed until the composition root or a module
        # contributes explicit authorization policy.
        policy_engine = RuleBasedPolicyEngine(rules=())
    if audit_sink is None:
        audit_sink = OutboxAuditSink(app_database)
    if rate_limiter is None and app_settings.rate_limit_per_minute > 0:
        rate_limiter = SlidingWindowRateLimiter(
            limit=app_settings.rate_limit_per_minute, window_s=60.0
        )
    if telemetry is None:
        configure_structured_logging(level=app_settings.log_level)
        telemetry = RuntimeTelemetry("windagent-api")

    command_bus = InProcessCommandBus(telemetry=telemetry)
    query_bus = InProcessQueryBus(telemetry=telemetry)
    module_registry = InMemoryModuleRegistry()
    api_runtime = ApiModuleRuntime(command_bus, query_bus, module_registry)

    loader = ModuleLoader(module_registry, api_runtime)
    app_owned: list[ModuleManifest] = [
        build_system_manifest(
            api_version=API_VERSION,
            settings=app_settings,
            module_registry=module_registry,
        )
    ]
    if job_queue is not None:
        app_owned.append(build_debug_manifest(job_queue))
    loader.bootstrap(
        (PackageModuleDiscovery(), StaticModuleDiscovery([*app_owned, *manifests]))
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await app_database.dispose()

    app = FastAPI(
        title="WindAgent V2 API",
        version=WINDAGENT_VERSION,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    error_mapper = DomainErrorStatusMapper()
    app.state.settings = app_settings
    app.state.command_bus = command_bus
    app.state.query_bus = query_bus
    app.state.database = app_database
    app.state.realtime_hub = realtime_hub
    app.state.authenticator = authenticator
    app.state.policy_engine = policy_engine
    app.state.audit_sink = audit_sink
    app.state.rate_limiter = rate_limiter
    app.state.telemetry = telemetry
    app.state.domain_error_mapper = error_mapper

    install_error_handlers(
        app,
        error_mapper,
        expose_internals=app_settings.environment != "production",
    )

    # Stacking order (last added is outermost): rate limiting rejects
    # abusive clients before authentication work, and every response —
    # including 401/429 — carries the request identity headers.
    if rate_limiter is not None:
        app.add_middleware(RateLimitMiddleware, limiter=rate_limiter)
    if authenticator is not None:
        app.add_middleware(AuthenticationMiddleware, authenticator=authenticator)
    app.add_middleware(RequestContextMiddleware, telemetry=telemetry)

    # Feature-module routers mount under the single canonical versioned
    # prefix; the app-owned debug surface stays a top-level opt-in.
    module_routers = [router for _, router in api_runtime.routers]
    app.include_router(build_api_router(module_routers))
    if job_queue is not None:
        app.include_router(
            create_debug_jobs_router(include_events=realtime_hub is not None)
        )
    app.include_router(
        create_health_router(
            version=WINDAGENT_VERSION,
            settings=app_settings,
            database=app_database,
        )
    )
    if app_settings.metrics_enabled and isinstance(telemetry, MetricsExporter):
        app.include_router(create_metrics_router(telemetry))
    return app
