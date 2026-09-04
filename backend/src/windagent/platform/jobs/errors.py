"""Job runtime errors that carry no infrastructure dependency."""


class JobRuntimeError(RuntimeError):
    """Base class for expected job-runtime failures."""


class DuplicateJobHandlerError(JobRuntimeError):
    """Raised when two handlers claim the same stable job type."""


class UnknownJobTypeError(JobRuntimeError):
    """Raised when no handler owns a claimed job type."""


class JobResultValidationError(JobRuntimeError):
    """Raised when a handler result cannot cross the JSON boundary."""
