"""Security foundation: policy, identity, authentication, secrets, audit.

``contracts.py`` stays infrastructure-free (architecture gate); the concrete
implementations beside it use only the kernel and standard library.  The
outbox-backed audit sink lives in the application layer because durability
is a composition concern.
"""

from .audit import AuditEvent, AuditSink, InMemoryAuditSink
from .authentication import (
    DEFAULT_TOKEN_TTL_S,
    TOKEN_KEY_SECRET_NAME,
    Authenticator,
    HmacTokenAuthenticator,
    HmacTokenIssuer,
)
from .contracts import (
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyRequest,
    SecretStore,
    SecretValue,
)
from .errors import (
    AuthenticationFailedError,
    SecurityError,
    TokenConfigurationError,
)
from .identity import Identity, IdentityKind, IdentityStore, InMemoryIdentityStore
from .policy import DEFAULT_DENY_POLICY_ID, PolicyRule, RuleBasedPolicyEngine
from .ratelimit import (
    DEFAULT_MAX_TRACKED_KEYS,
    RateLimitDecision,
    RateLimiter,
    SlidingWindowRateLimiter,
)
from .secrets import EnvironmentSecretStore, InMemorySecretStore

__all__ = [
    "DEFAULT_DENY_POLICY_ID",
    "DEFAULT_MAX_TRACKED_KEYS",
    "DEFAULT_TOKEN_TTL_S",
    "AuthenticationFailedError",
    "Authenticator",
    "AuditEvent",
    "AuditSink",
    "EnvironmentSecretStore",
    "HmacTokenAuthenticator",
    "HmacTokenIssuer",
    "Identity",
    "IdentityKind",
    "IdentityStore",
    "InMemoryAuditSink",
    "InMemoryIdentityStore",
    "InMemorySecretStore",
    "PolicyDecision",
    "PolicyEffect",
    "PolicyEngine",
    "PolicyRequest",
    "PolicyRule",
    "RateLimiter",
    "RateLimitDecision",
    "RuleBasedPolicyEngine",
    "SecurityError",
    "SecretStore",
    "SecretValue",
    "SlidingWindowRateLimiter",
    "TOKEN_KEY_SECRET_NAME",
    "TokenConfigurationError",
]
