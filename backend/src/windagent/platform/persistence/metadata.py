"""Shared SQLAlchemy metadata with deterministic constraint naming.

Alembic autogenerate uses ``target_metadata`` (see ``migrations/env.py``);
the naming convention keeps generated constraint names stable across
regenerations so repeated autogenerate runs produce minimal diffs.
"""

from __future__ import annotations

from sqlalchemy import MetaData

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

target_metadata = metadata
