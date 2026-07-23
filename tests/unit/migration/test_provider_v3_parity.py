"""
Unit tests for automated V2 vs V3 parity comparator.
"""
from __future__ import annotations

import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parents[3]
backend_dir = root_dir / "apps" / "backend"
for d in (root_dir, backend_dir):
    if d.exists() and str(d) not in sys.path:
        sys.path.insert(0, str(d)) if d == root_dir else sys.path.append(str(d))

import pytest

from db.database import Database
from db.models import ModelCatalogORM, ModelProviderORM, ModelRoutingRuleORM
from services.provider_gateway import ProviderGatewayService
from services.provider_v3_parity import compare_list_models, run_parity_suite
from services.router_execution_service import RouterExecutionService


@pytest.fixture
async def parity_db():
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.init_models()
    yield db
    await db.dispose()


@pytest.fixture
async def parity_services(parity_db):
    db = parity_db
    async with db.session() as session:
        provider = ModelProviderORM(
            id="mock",
            site_name="Mock",
            api_source="openai",
            base_url="http://localhost:9999",
            api_key="key",
            enabled=True,
        )
        catalog = ModelCatalogORM(
            id="mock/gpt-4o",
            provider_id="mock",
            model_id="gpt-4o",
            display_name="GPT-4o",
            type="API",
            enabled=True,
        )
        rule = ModelRoutingRuleORM(
            role="Planner",
            name="Planner",
            primary_model_id="mock/gpt-4o",
            status="Active",
        )
        session.add_all([provider, catalog, rule])
        await session.commit()
    return db


@pytest.mark.asyncio
async def test_list_models_parity(parity_services):
    db = parity_services
    gateway = ProviderGatewayService(db=db, router_service=None, v3_coordinator=None)

    async def legacy():
        return await gateway.list_models()

    async def v3():
        return await gateway.list_models()

    result = await compare_list_models(legacy, v3)
    assert result.passed, result.diff


@pytest.mark.asyncio
async def test_parity_suite_runs(parity_services):
    db = parity_services
    router = RouterExecutionService(
        db=db,
        quota_service=None,
        policy=None,
        model_service=None,
    )

    async def legacy_rules():
        return await router.list_routing_rules()

    async def v3_rules():
        return await router.list_routing_rules()

    results = await run_parity_suite({"list_routing_rules": (legacy_rules, v3_rules)})
    assert all(r.passed for r in results), [r.diff for r in results if not r.passed]
