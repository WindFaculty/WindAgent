"""
Unit Tests for ErrorClassifier, RetryPolicy, and Fail-Closed Unclassified Exceptions (Phase G).
"""

import pytest
from windagent_core.errors.exceptions import RetryableError, NonRetryableError
from windagent_orchestration.retry import RetryPolicy, ErrorClassifier


def test_unclassified_exception_fails_closed():
    # Requirement 12: Do NOT default retry unclassified standard exceptions!
    unclassified_err = ValueError("Invalid json schema parameter")
    assert ErrorClassifier.is_retryable(unclassified_err) is False

    key_err = KeyError("missing_field")
    assert ErrorClassifier.is_retryable(key_err) is False

    runtime_err = RuntimeError("Something unexpected occurred")
    assert ErrorClassifier.is_retryable(runtime_err) is False


def test_classified_exceptions():
    assert ErrorClassifier.is_retryable(RetryableError("Timeout")) is True
    assert ErrorClassifier.is_retryable(TimeoutError("Socket timeout")) is True
    assert ErrorClassifier.is_retryable(NonRetryableError("Auth error")) is False


def test_retry_policy_with_classifier():
    policy = RetryPolicy(max_attempts=3)

    # Retryable error on attempt 1
    assert policy.should_retry(RetryableError("Network error"), attempt=1) is True

    # Unclassified error on attempt 1 -> MUST BE FALSE
    assert policy.should_retry(ValueError("Unclassified error"), attempt=1) is False
