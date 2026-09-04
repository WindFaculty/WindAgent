"""Infrastructure-free validation for handler results."""

from __future__ import annotations

from windagent.kernel.types.json import JSONValue, freeze_json

from .errors import JobResultValidationError


class JobResultValidator:
    """Freeze a handler result at the durable JSON boundary."""

    def validate(self, result: object) -> JSONValue:
        try:
            return freeze_json(result)
        except (TypeError, ValueError) as error:
            raise JobResultValidationError(str(error)) from error
