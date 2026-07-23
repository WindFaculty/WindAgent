"""add_orchestration_v2_tables

Revision ID: 3333ac030c95
Revises: 2222ab020b94
Create Date: 2026-07-24 01:50:00.000000

Additive migration creating durable Orchestration V2 storage tables:
task_runs, v2_workflow_runs_v2, workflow_step_runs, execution_leases,
execution_attempts, workflow_checkpoints, cancellation_requests, worker_registrations.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3333ac030c95'
down_revision: Union[str, None] = '2222ab020b94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. task_runs
    op.create_table(
        'task_runs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('state', sa.String(length=32), nullable=False, server_default='received'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('current_step', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_steps', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pending_permission', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('project_id', sa.String(length=64), nullable=True),
        sa.Column('worktree_id', sa.String(length=64), nullable=True),
        sa.Column('facts_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_task_runs_session_id', 'task_runs', ['session_id'])
    op.create_index('ix_task_runs_session_state', 'task_runs', ['session_id', 'state'])
    op.create_index('ix_task_runs_state_priority_created', 'task_runs', ['state', 'priority', 'created_at'])

    # 2. v2_workflow_runs_v2
    op.create_table(
        'v2_workflow_runs_v2',
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('workflow_id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('task_run_id', sa.String(length=36), nullable=True),
        sa.Column('state', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('checkpoint_cursor', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('definition_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_run_id'], ['task_runs.id']),
        sa.PrimaryKeyConstraint('run_id')
    )
    op.create_index('ix_v2_workflow_runs_v2_session_id', 'v2_workflow_runs_v2', ['session_id'])
    op.create_index('ix_v2_workflow_runs_task_state', 'v2_workflow_runs_v2', ['task_run_id', 'state'])

    # 3. workflow_step_runs
    op.create_table(
        'workflow_step_runs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('workflow_run_id', sa.String(length=36), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('tool_name', sa.String(length=64), nullable=False),
        sa.Column('params_json', sa.Text(), nullable=True),
        sa.Column('state', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('result_json', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('ready_at', sa.DateTime(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['workflow_run_id'], ['v2_workflow_runs_v2.run_id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_workflow_step_runs_run_state', 'workflow_step_runs', ['workflow_run_id', 'state'])
    op.create_index('ix_workflow_step_runs_state_ready_priority', 'workflow_step_runs', ['state', 'ready_at', 'priority'])

    # 4. execution_leases
    op.create_table(
        'execution_leases',
        sa.Column('lease_id', sa.String(length=64), nullable=False),
        sa.Column('step_run_id', sa.String(length=36), nullable=False),
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('worker_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='active'),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['step_run_id'], ['workflow_step_runs.id']),
        sa.PrimaryKeyConstraint('lease_id'),
        sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('ix_execution_leases_status_expires', 'execution_leases', ['status', 'expires_at'])
    op.create_index('ix_execution_leases_step_status', 'execution_leases', ['step_run_id', 'status'])

    # 5. execution_attempts
    op.create_table(
        'execution_attempts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('step_run_id', sa.String(length=36), nullable=False),
        sa.Column('attempt_index', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('worker_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['step_run_id'], ['workflow_step_runs.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_execution_attempts_step_attempt', 'execution_attempts', ['step_run_id', 'attempt_index'])

    # 6. workflow_checkpoints
    op.create_table(
        'workflow_checkpoints',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('step_id', sa.String(length=36), nullable=False),
        sa.Column('cursor', sa.Integer(), nullable=False),
        sa.Column('state_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['v2_workflow_runs_v2.run_id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_workflow_checkpoints_run_cursor', 'workflow_checkpoints', ['run_id', 'cursor'])

    # 7. cancellation_requests
    op.create_table(
        'cancellation_requests',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('target_id', sa.String(length=64), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=False, server_default='task'),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('requested_by', sa.String(length=64), nullable=False, server_default='user'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cancellation_requests_target_id', 'cancellation_requests', ['target_id'])

    # 8. worker_registrations
    op.create_table(
        'worker_registrations',
        sa.Column('worker_id', sa.String(length=64), nullable=False),
        sa.Column('runtime_type', sa.String(length=32), nullable=False, server_default='local'),
        sa.Column('health', sa.String(length=32), nullable=False, server_default='healthy'),
        sa.Column('active_leases', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_heartbeat_at', sa.DateTime(), nullable=False),
        sa.Column('metadata_json', sa.Text(), nullable=False, server_default='{}'),
        sa.PrimaryKeyConstraint('worker_id')
    )
    op.create_index('ix_worker_registrations_type_health', 'worker_registrations', ['runtime_type', 'health'])


def downgrade() -> None:
    op.drop_table('worker_registrations')
    op.drop_table('cancellation_requests')
    op.drop_table('workflow_checkpoints')
    op.drop_table('execution_attempts')
    op.drop_table('execution_leases')
    op.drop_table('workflow_step_runs')
    op.drop_table('v2_workflow_runs_v2')
    op.drop_table('task_runs')
