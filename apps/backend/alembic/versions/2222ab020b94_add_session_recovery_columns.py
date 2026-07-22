"""Add session recovery columns and snapshot support

Revision ID: 2222ab020b94
Revises: 1111fa010a93
Create Date: 2026-07-13 23:26:00.000000

Adds:
  - chat_sessions.title (nullable)
  - chat_sessions.agent_id (nullable)
  - chat_sessions.last_event_sequence (default 0)
  - chat_sessions.archived_at (nullable)
  - chat_sessions.completed_at (nullable)
  - chat_sessions.error_message (nullable)

All columns are nullable with safe defaults — no data migration needed.
SQLite compatible (ALTER TABLE ADD COLUMN).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2222ab020b94'
down_revision: Union[str, Sequence[str], None] = '1111fa010a93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable columns to chat_sessions for recovery/session management
    # SQLite: ALTER TABLE ADD COLUMN only supports nullable or with a constant default
    with op.batch_alter_table('chat_sessions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('title', sa.String(255), nullable=True, server_default='New Session')
        )
        batch_op.add_column(
            sa.Column('agent_id', sa.String(36), nullable=True)
        )
        batch_op.add_column(
            sa.Column('last_event_sequence', sa.Integer(), nullable=True, server_default='0')
        )
        batch_op.add_column(
            sa.Column('archived_at', sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('completed_at', sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('error_message', sa.Text(), nullable=True)
        )

    # Add index for filtering by agent_id
    op.create_index(
        'ix_chat_sessions_agent_id',
        'chat_sessions',
        ['agent_id'],
        unique=False,
    )

    # Add index for archived_at filtering
    op.create_index(
        'ix_chat_sessions_archived_at',
        'chat_sessions',
        ['archived_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_chat_sessions_archived_at', table_name='chat_sessions')
    op.drop_index('ix_chat_sessions_agent_id', table_name='chat_sessions')

    with op.batch_alter_table('chat_sessions', schema=None) as batch_op:
        batch_op.drop_column('error_message')
        batch_op.drop_column('completed_at')
        batch_op.drop_column('archived_at')
        batch_op.drop_column('last_event_sequence')
        batch_op.drop_column('agent_id')
        batch_op.drop_column('title')
