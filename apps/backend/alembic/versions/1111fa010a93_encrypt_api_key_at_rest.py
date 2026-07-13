"""encrypt api_key at rest

Revision ID: 1111fa010a93
Revises: 
Create Date: 2026-07-12 23:57:25.875532

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import os
import base64
from cryptography.fernet import Fernet, InvalidToken

# revision identifiers, used by Alembic.
revision: str = '1111fa010a93'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_encryption_key_from_env() -> bytes:
    """Get encryption key from environment variable.

    Expected format: base64-encoded 32-byte key (Fernet key).
    Environment variable: WINDAGENT_SECRET_ENCRYPTION_KEY

    Returns:
        bytes: The encryption key.

    Raises:
        ValueError: If the environment variable is not set or invalid.
    """
    key_b64 = os.environ.get("WINDAGENT_SECRET_ENCRYPTION_KEY")
    if not key_b64:
        raise ValueError(
            "Encryption key not set. Set WINDAGENT_SECRET_ENCRYPTION_KEY environment variable."
        )
    try:
        # Fernet expects a base64-encoded 32-byte key
        key = base64.urlsafe_b64decode(key_b64)
        if len(key) != 32:
            raise ValueError("Encryption key must be 32 bytes after base64 decoding")
        return key
    except Exception as exc:
        raise ValueError(f"Invalid encryption key: {exc}") from exc


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string using Fernet (AES-128 in CBC mode with HMAC).

    Args:
        plaintext: The string to encrypt.

    Returns:
        str: Encrypted string with prefix 'enc:v1:' to indicate version.

    Raises:
        ValueError: If encryption key is not set or invalid.
    """
    if not plaintext:
        return plaintext
    try:
        f = Fernet(_get_encryption_key_from_env())
        encrypted_bytes = f.encrypt(plaintext.encode("utf-8"))
        # Return with version prefix for future rotation support
        return f"enc:v1:{encrypted_bytes.decode('utf-8')}"
    except Exception as exc:
        raise ValueError(f"Encryption failed: {exc}") from exc


def decrypt(encrypted_str: str) -> str:
    """Decrypt an encrypted string.

    Args:
        encrypted_str: The encrypted string (may have 'enc:v1:' prefix).

    Returns:
        str: The decrypted plaintext.

    Raises:
        ValueError: If decryption fails (invalid token, missing key, etc.).
    """
    if not encrypted_str:
        return encrypted_str
    # If it doesn't have the prefix, assume it's plaintext (for backward compatibility during migration)
    if not encrypted_str.startswith("enc:v1:"):
        return encrypted_str
    try:
        f = Fernet(_get_encryption_key_from_env())
        encrypted_bytes = encrypted_str[7:].encode("utf-8")  # remove 'enc:v1:' prefix
        decrypted_bytes = f.decrypt(encrypted_bytes)
        return decrypted_bytes.decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(f"Invalid encryption token: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Decryption failed: {exc}") from exc


def upgrade() -> None:
    """Upgrade schema and encrypt existing api_key values."""
    # Get the current connection and inspector
    conn = op.get_bind()
    inspector = sa.engine.Inspector.from_engine(conn)
    
    # If the table doesn't exist, create it using the current model definition
    if not inspector.has_table("model_providers"):
        # Import the model to get the table definition
        # We do this inside the function to avoid import-time issues
        from db.models import ModelProviderORM
        ModelProviderORM.__table__.create(conn)
        # After creating the table, there is no data to encrypt, so we can return
        return

    # If the table exists, check the column type for api_key
    columns = inspector.get_columns("model_providers")
    api_key_column = next((c for c in columns if c['name'] == 'api_key'), None)
    if api_key_column:
        col_type = api_key_column['type']
        # If the column is VARCHAR, we need to alter it to Text to store encrypted values
        if isinstance(col_type, sa.VARCHAR):
            with op.batch_alter_table('model_providers', schema=None) as batch_op:
                batch_op.alter_column('api_key',
                            existing_type=sa.VARCHAR(length=255),
                            type_=sa.Text(),
                            existing_nullable=True)

    # Now, encrypt existing plaintext api_key values.
    # We use a connection to update the rows.
    connection = op.get_bind()
    # Select all rows where api_key is not null and does not already start with our encryption prefix.
    # We assume that any existing value that does not start with 'enc:v1:' is plaintext.
    result = connection.execute(
        sa.text("SELECT id, api_key FROM model_providers WHERE api_key IS NOT NULL AND api_key NOT LIKE 'enc:v1:%'")
    )
    rows = result.fetchall()
    for row in rows:
        row_id, api_key = row
        if api_key is None:
            continue
        # Encrypt the api_key
        encrypted_api_key = encrypt(api_key)
        # Update the row
        connection.execute(
            sa.text("UPDATE model_providers SET api_key = :encrypted WHERE id = :id"),
            {"encrypted": encrypted_api_key, "id": row_id}
        )


def downgrade() -> None:
    """Downgrade schema and decrypt api_key values."""
    # ### commands auto generated by Alembic - please adjust! ###
    # First, decrypt the encrypted api_key values.
    connection = op.get_bind()
    # Select all rows where api_key is not null and starts with our encryption prefix.
    result = connection.execute(
        sa.text("SELECT id, api_key FROM model_providers WHERE api_key IS NOT NULL AND api_key LIKE 'enc:v1:%'")
    )
    rows = result.fetchall()
    for row in rows:
        row_id, api_key = row
        if api_key is None:
            continue
        # Decrypt the api_key
        decrypted_api_key = decrypt(api_key)
        # Update the row
        connection.execute(
            sa.text("UPDATE model_providers SET api_key = :decrypted WHERE id = :id"),
            {"decrypted": decrypted_api_key, "id": row_id}
        )

    # Now, change the column back to VARCHAR(255)
    with op.batch_alter_table('model_providers', schema=None) as batch_op:
        batch_op.alter_column('api_key',
               existing_type=sa.Text(),
               type_=sa.VARCHAR(length=255),
               existing_nullable=True)
    # ### end Alembic commands ###