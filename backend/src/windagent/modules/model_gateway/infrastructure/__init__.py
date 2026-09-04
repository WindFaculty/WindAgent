"""Infrastructure adapters for the model gateway.

``repository`` is the canonical SQL implementation; ``memory`` exists only
for offline unit tests and tiny development experiments (plan section 8).
"""

from .memory import (
    InMemoryModelGatewayStore,
    InMemoryTransactionScope,
    memory_scope_factory,
)
from .repository import (
    STORE_REPOSITORY_NAME,
    SqlModelGatewayStore,
    SqlTransactionScope,
    make_store,
    sql_scope_factory,
)
from .secret_store import (
    CANONICAL_KEY_ENV,
    ChainedSecretStore,
    EncryptedSecretStore,
    EncryptionKeyMissingError,
    decrypt_secret,
    encrypt_secret,
    get_encryption_key,
)

__all__ = [
    "CANONICAL_KEY_ENV",
    "ChainedSecretStore",
    "EncryptedSecretStore",
    "EncryptionKeyMissingError",
    "InMemoryModelGatewayStore",
    "InMemoryTransactionScope",
    "STORE_REPOSITORY_NAME",
    "SqlModelGatewayStore",
    "SqlTransactionScope",
    "decrypt_secret",
    "encrypt_secret",
    "get_encryption_key",
    "make_store",
    "memory_scope_factory",
    "sql_scope_factory",
]
