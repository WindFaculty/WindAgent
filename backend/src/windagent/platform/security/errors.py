"""Security errors that carry no infrastructure dependency."""


class SecurityError(RuntimeError):
    """Base class for expected security-subsystem failures."""


class AuthenticationFailedError(SecurityError):
    """Raised when presented credentials cannot be verified."""


class TokenConfigurationError(SecurityError):
    """Raised when the token-signing material is missing or unusable.

    This is a composition/configuration failure, not a client error: it must
    surface as a server error instead of masquerading as a 401.
    """
