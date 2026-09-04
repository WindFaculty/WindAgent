"""WindAgent V2 foundation — clean baseline.

Revision ID: 0001
Revises:
Create Date: 2026-09-02

Plan section 9: V2 starts from an empty, clean revision instead of
importing the old repository's 31 migration files.  Domain tables arrive
with their own module migrations (0002_identity, 0003_jobs, ...) once the
corresponding phases are implemented; data from the old system flows
through migration importers, never through this schema history.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Intentionally empty.

    The foundation baseline anchors the V2 migration chain; it does not copy
    legacy schema forward.
    """


def downgrade() -> None:
    """Nothing to tear down for the empty baseline."""
