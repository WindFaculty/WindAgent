"""Module manifest: discovered automatically by ``PackageModuleDiscovery``.

The module-level ``manifest`` is deliberately built without constructor
arguments so no API or worker bootstrap file needs to know this module's
name (plan section 7).  Handlers resolve their collaborators through the
ambient services scope, which HTTP routes and worker jobs bind at dispatch
time.
"""

from __future__ import annotations

from windagent.platform.modules import (
    CommandRegistration,
    JobRegistration,
    ModuleManifest,
    QueryRegistration,
)

from .api.routes import MODULE_ID, MODULE_VERSION, create_model_gateway_router
from .application.commands import (
    AddProviderEndpoint,
    DeleteProvider,
    DeleteRoutingRule,
    InvokeModel,
    RegisterProvider,
    RemoveProviderCredential,
    ReselectModel,
    RotateProviderCredential,
    UpdateProvider,
    UpsertRoutingRule,
)
from .application.handlers import (
    AddProviderEndpointHandler,
    DeleteProviderHandler,
    DeleteRoutingRuleHandler,
    GetActiveRouteLockHandler,
    GetProviderHandler,
    GetRouteLockHandler,
    InvokeModelHandler,
    InvokeModelJobHandler,
    ListCanonicalModelsHandler,
    ListEndpointsHandler,
    ListProvidersHandler,
    ListReceiptsHandler,
    ListRoutingRulesHandler,
    RegisterProviderHandler,
    RemoveProviderCredentialHandler,
    ReselectModelHandler,
    RotateProviderCredentialHandler,
    SimulateRouteHandler,
    UpdateProviderHandler,
    UpsertRoutingRuleHandler,
)
from .application.models import ProviderView  # noqa: F401 (public surface docs)
from .application.queries import (
    GetActiveRouteLock,
    GetProvider,
    GetRouteLock,
    ListCanonicalModels,
    ListEndpoints,
    ListProviders,
    ListReceipts,
    ListRoutingRules,
    SimulateRoute,
)
from .application.runtime import ModelGatewayServices

INVOKE_JOB_TYPE = "model_gateway.invoke"


def build_model_gateway_manifest(
    services: ModelGatewayServices | None = None,
) -> ModuleManifest:
    """Build the manifest, optionally binding explicit services (tests)."""
    return ModuleManifest(
        id=MODULE_ID,
        version=MODULE_VERSION,
        commands=(
            CommandRegistration(RegisterProvider, RegisterProviderHandler(services)),
            CommandRegistration(UpdateProvider, UpdateProviderHandler(services)),
            CommandRegistration(DeleteProvider, DeleteProviderHandler(services)),
            CommandRegistration(
                RotateProviderCredential, RotateProviderCredentialHandler(services)
            ),
            CommandRegistration(
                RemoveProviderCredential, RemoveProviderCredentialHandler(services)
            ),
            CommandRegistration(
                AddProviderEndpoint, AddProviderEndpointHandler(services)
            ),
            CommandRegistration(UpsertRoutingRule, UpsertRoutingRuleHandler(services)),
            CommandRegistration(DeleteRoutingRule, DeleteRoutingRuleHandler(services)),
            CommandRegistration(InvokeModel, InvokeModelHandler(services)),
            CommandRegistration(ReselectModel, ReselectModelHandler(services)),
        ),
        queries=(
            QueryRegistration(ListProviders, ListProvidersHandler(services)),
            QueryRegistration(GetProvider, GetProviderHandler(services)),
            QueryRegistration(ListEndpoints, ListEndpointsHandler(services)),
            QueryRegistration(ListCanonicalModels, ListCanonicalModelsHandler(services)),
            QueryRegistration(ListRoutingRules, ListRoutingRulesHandler(services)),
            QueryRegistration(GetRouteLock, GetRouteLockHandler(services)),
            QueryRegistration(GetActiveRouteLock, GetActiveRouteLockHandler(services)),
            QueryRegistration(SimulateRoute, SimulateRouteHandler(services)),
            QueryRegistration(ListReceipts, ListReceiptsHandler(services)),
        ),
        jobs=(JobRegistration(INVOKE_JOB_TYPE, InvokeModelJobHandler(services)),),
        routers=(create_model_gateway_router(),),
        capabilities=("model-gateway",),
    )


manifest = build_model_gateway_manifest()
