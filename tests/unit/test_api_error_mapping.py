"""DomainError-to-HTTP status mapping contracts."""

from __future__ import annotations

import pytest
from windagent.kernel.errors.domain import DomainError
from windagent_api.errors.mapping import (
    DEFAULT_STATUS,
    DomainErrorStatusMapper,
    status_for_domain_error,
)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("unauthorized", 401),
        ("forbidden", 403),
        ("not_found", 404),
        ("conflict", 409),
        ("validation_error", 400),
        ("rate_limited", 429),
        ("domain_error", DEFAULT_STATUS),
    ],
)
def test_default_code_map(code: str, expected: int) -> None:
    error = DomainError("boom", code=code)
    assert status_for_domain_error(error) == expected
    assert DomainErrorStatusMapper().status_for(error) == expected


def test_unknown_codes_fail_closed_on_500() -> None:
    error = DomainError("boom", code="brand_new_code")
    assert DomainErrorStatusMapper().status_for(error) == 500


def test_registered_codes_extend_the_map() -> None:
    mapper = DomainErrorStatusMapper({"budget_exceeded": 402})
    mapper.register("quota_blocked", 403)
    assert mapper.status_for(DomainError("x", code="budget_exceeded")) == 402
    assert mapper.status_for(DomainError("x", code="quota_blocked")) == 403


def test_register_rejects_invalid_input() -> None:
    mapper = DomainErrorStatusMapper()
    with pytest.raises(ValueError):
        mapper.register("  ", 400)
    with pytest.raises(ValueError):
        mapper.register("bad_status", 302)
    with pytest.raises(ValueError):
        mapper.register("bad_status", 600)
