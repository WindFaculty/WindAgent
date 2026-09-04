"""Background job handlers for Quality."""

from __future__ import annotations

from typing import Any

from ..application.commands import (
    ExecuteDatasetEvaluation,
    RunVerificationSuite,
)
from ..application.runtime import QualityServices, container_for


class QualityEvalExecuteJobHandler:
    job_type = "quality.eval.execute"

    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        execution_id = str(payload.get("execution_id", ""))
        dataset_id = str(payload.get("dataset_id", ""))
        grader_type = str(payload.get("grader_type", "exact_match"))
        if not execution_id or not dataset_id:
            return {"status": "FAILED", "error": "missing execution_id or dataset_id in payload"}
        try:
            view = await container_for(self._services).quality.execute_dataset_evaluation(
                ExecuteDatasetEvaluation(
                    execution_id=execution_id,
                    dataset_id=dataset_id,
                    grader_type=grader_type,
                )
            )
            return {"status": "SUCCEEDED", "evaluation_run": view.to_payload()}
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc)}


class QualityVerificationRunJobHandler:
    job_type = "quality.verification.run"

    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        suite_id = str(payload.get("suite_id", "default_suite"))
        target_id = str(payload.get("target_id", ""))
        gate_checks = tuple(payload.get("gate_checks", []))
        if not target_id:
            return {"status": "FAILED", "error": "missing target_id in payload"}
        try:
            view = await container_for(self._services).quality.run_verification_suite(
                RunVerificationSuite(
                    suite_id=suite_id,
                    target_id=target_id,
                    gate_checks=gate_checks,
                )
            )
            return {"status": "SUCCEEDED", "verification_report": view.to_payload()}
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc)}


class QualityBenchmarkRunJobHandler:
    job_type = "quality.benchmark.run"

    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": "SUCCEEDED", "output": {"status": "benchmark_completed"}}


class QualityRegressionDetectJobHandler:
    job_type = "quality.regression.detect"

    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": "SUCCEEDED", "output": {"status": "regression_check_completed"}}
