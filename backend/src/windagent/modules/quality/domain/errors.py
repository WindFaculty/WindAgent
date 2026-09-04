"""Domain errors for the Quality bounded context."""

from __future__ import annotations

from windagent.kernel.errors import DomainError


class QualityError(DomainError):
    """Base error for all quality domain failures."""


class QualityEvaluationNotFoundError(QualityError):
    """Raised when an evaluation run or record cannot be found."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"Evaluation not found: {identifier}")
        self.identifier = identifier


class DatasetNotFoundError(QualityError):
    """Raised when an evaluation dataset cannot be found."""

    def __init__(self, dataset_id: str) -> None:
        super().__init__(f"Evaluation dataset not found: {dataset_id}")
        self.dataset_id = dataset_id


class QualityGateBlockedError(QualityError):
    """Raised when a blocking quality gate fails closed."""

    def __init__(self, gate_name: str, reason: str) -> None:
        super().__init__(f"Quality gate '{gate_name}' blocked: {reason}")
        self.gate_name = gate_name
        self.reason = reason


class VerificationSuiteFailedError(QualityError):
    """Raised when a mandatory verification suite execution fails."""

    def __init__(self, suite_id: str, failed_gates: list[str]) -> None:
        super().__init__(f"Verification suite '{suite_id}' failed on gates: {', '.join(failed_gates)}")
        self.suite_id = suite_id
        self.failed_gates = failed_gates


class RegressionDetectedError(QualityError):
    """Raised when candidate performance exhibits statistically significant degradation."""

    def __init__(self, candidate_id: str, baseline_id: str, metric: str, delta: float) -> None:
        super().__init__(
            f"Regression detected comparing '{candidate_id}' against baseline '{baseline_id}' on '{metric}': delta={delta:.4f}"
        )
        self.candidate_id = candidate_id
        self.baseline_id = baseline_id
        self.metric = metric
        self.delta = delta


class QualityStaleVersionError(QualityError):
    """Raised on optimistic concurrency version mismatch during quality update."""

    def __init__(self, entity_id: str, expected_version: int, actual_version: int) -> None:
        super().__init__(
            f"Stale quality update on '{entity_id}': expected version {expected_version}, got {actual_version}"
        )
        self.entity_id = entity_id
        self.expected_version = expected_version
        self.actual_version = actual_version
