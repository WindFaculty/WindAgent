from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_zero_direct_feature_websockets():
    """Phase 11 requirement: All feature-level realtime must route through @windagent/realtime.
    No feature hook or component is allowed to instantiate ad-hoc new WebSocket().
    """
    feature_dir = ROOT / "frontend/app/src/features"
    for file_path in feature_dir.rglob("*.ts*"):
        text = file_path.read_text(encoding="utf-8")
        assert "new WebSocket" not in text, f"Found direct 'new WebSocket' in {file_path.relative_to(ROOT)}"


def test_zero_fake_metrics_randomness():
    """Gate G11_TRUTHFUL_UI: No Math.random simulated telemetry, jitter, or fake health in frontend."""
    app_src = ROOT / "frontend/app/src"
    for file_path in app_src.rglob("*.ts*"):
        text = file_path.read_text(encoding="utf-8")
        assert "Math.random" not in text, f"Found Math.random in {file_path.relative_to(ROOT)}"


def test_truthful_provider_config_panel():
    """Provider config UI must not show synthetic test latencies or fake success prior to test."""
    panel_source = (
        ROOT / "frontend/app/src/features/routing/components/ProviderConfigPanel.tsx"
    ).read_text(encoding="utf-8")
    assert "289 ms" not in panel_source
    assert "lastTestLatency ||" not in panel_source


def test_truthful_add_provider_modal():
    """Add Provider modal must not default new un-tested providers with fake test latency."""
    modal_source = (
        ROOT / "frontend/app/src/features/routing/components/AddProviderModal.tsx"
    ).read_text(encoding="utf-8")
    assert "lastTestLatency: 180" not in modal_source


def test_shared_app_convergence():
    """Web and Desktop applications must both converge on @windagent/app shared application."""
    web_main = (ROOT / "apps/web/src/main.tsx").read_text(encoding="utf-8")
    desktop_app = (ROOT / "apps/desktop/src/App.tsx").read_text(encoding="utf-8")

    assert "@windagent/app" in web_main
    assert "SharedApp" in web_main

    assert "@windagent/app" in desktop_app
    assert "SharedApp" in desktop_app
