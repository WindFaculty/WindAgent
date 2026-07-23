"""Tests for provider V3 metrics and observability wiring."""

from __future__ import annotations

import pytest

from services.provider_v3_metrics import ProviderV3Metrics, with_metrics


@pytest.mark.asyncio
async def test_metrics_inc_and_gauge():
    m = ProviderV3Metrics()
    m.inc("provider_requests", labels={"canonical_model_id": "cm-gpt4o"})
    m.gauge("first_token_latency_ms", 120.0, labels={"provider_id": "openai"})
    snap = m.snapshot()
    assert snap["counters"]
    assert snap["gauges"]


@pytest.mark.asyncio
async def test_metrics_secret_labels_redacted():
    m = ProviderV3Metrics()
    m.inc("provider_requests", labels={"api_key": "sk-12345", "provider_id": "openai"})
    prom = m.to_prometheus()
    assert "sk-12345" not in prom
    assert "[REDACTED]" in prom


@pytest.mark.asyncio
async def test_metrics_cardinality_guard():
    m = ProviderV3Metrics()
    m.MAX_CARDINALITY = 5
    for i in range(5):
        m.gauge("test_metric", float(i), labels={"idx": str(i)})
    with pytest.raises(RuntimeError):
        m.gauge("test_metric", 99.0, labels={"idx": "overflow"})
    snap = m.snapshot()
    assert snap["series"] <= 5


@pytest.mark.asyncio
async def test_with_metrics_decorator():
    m = ProviderV3Metrics()

    @with_metrics("test_op", metrics=m)
    async def work():
        return 42

    assert await work() == 42
    snap = m.snapshot()
    assert any("test_op_total" in k for k in snap["counters"])
    assert any("test_op_latency_ms" in k for k in snap["gauges"])
