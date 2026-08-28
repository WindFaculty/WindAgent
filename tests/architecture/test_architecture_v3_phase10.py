from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_provider_ui_has_no_production_mock_connection_authority():
    source = (
        ROOT / "frontend/app/src/features/routing/pages/RoutingPage.tsx"
    ).read_text(encoding="utf-8")
    for banned in (
        "Math.random",
        "INITIAL_PROVIDERS",
        "INITIAL_MODEL_RULES",
        "INITIAL_ACTIVITIES",
        "simulatedLatency",
        "Simulate realistic network roundtrip",
    ):
        assert banned not in source
    assert "useProviders()" in source
    assert "useTestProviderConnection()" in source
    assert "receipt" in source
    feature_source = "\n".join(
        path.read_text(encoding="utf-8")
        for folder in (
            ROOT / "frontend/app/src/features/providers",
            ROOT / "frontend/app/src/features/routing",
        )
        for path in folder.rglob("*.tsx")
    )
    assert "Math.random" not in feature_source
    assert "status: 'connected'," not in feature_source
    assert "credentialsStatus: 'valid'," not in feature_source


def test_default_provider_test_connect_fails_closed_before_demo_compatibility():
    source = (
        ROOT / "apps/api/windagent_api/routers/v3/providers.py"
    ).read_text(encoding="utf-8")
    production_guard = source.index('!= "demo"')
    demo_catalog = source.index("discovered_map")
    assert production_guard < demo_catalog
    # Catalog-only ids no longer receive a connection receipt: outside the
    # explicit demo profile the test-connect endpoint fails closed with a
    # 404 instead of turning a read-only catalog row into connection authority.
    assert "is not registered." in source


def test_worker_composes_sql_model_rule_projection():
    provider_composer = (
        ROOT / "apps/worker/windagent_worker/composition/providers.py"
    ).read_text(encoding="utf-8")
    studio_composer = (
        ROOT / "apps/worker/windagent_worker/composition/studio.py"
    ).read_text(encoding="utf-8")
    assert "SQLProviderManagementRepository" in provider_composer
    assert "RoutingPolicyProjection" in provider_composer
    assert "ruleset=ruleset" in provider_composer
    assert "settings.studio_canonical_model or None" in studio_composer
    assert "RoutingPolicyProjection" in studio_composer


def test_provider_infrastructure_does_not_import_storage():
    for path in (ROOT / "providers/windagent_providers/management").glob("*.py"):
        assert "windagent_storage" not in path.read_text(encoding="utf-8")
