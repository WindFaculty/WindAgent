"""
Test Environment Builder and Seed Helper for Stage H verification.

Provides utilities for:
- Initializing database schemas (SQLite / Postgres)
- Seeding canonical fixtures
- Resetting test database state
- Injecting failure modes (latency, API error codes, disconnects)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional


class TestEnvironmentBuilder:
    """Builder for isolated test databases and environment states."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or ":memory:"
        self.conn: Optional[sqlite3.Connection] = None

    def initialize_sqlite_db(self) -> sqlite3.Connection:
        """Create and populate in-memory SQLite schema."""
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()

        # Create core tables for stage H testing
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS revisions (
                revision_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                locked INTEGER NOT NULL DEFAULT 0,
                locked_hash TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(project_id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                license_state TEXT NOT NULL,
                processing_state TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS proposals (
                proposal_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL
            );
        """)
        self.conn.commit()
        return self.conn

    def seed_canonical_bunny(self, canonical_data: Dict[str, Any]) -> None:
        """Seed canonical Bunny Episode 01 into active database connection."""
        if not self.conn:
            self.initialize_sqlite_db()
        assert self.conn is not None
        cursor = self.conn.cursor()

        project_id = canonical_data["project_id"]
        cursor.execute("INSERT OR REPLACE INTO projects VALUES (?, ?, datetime('now'))", (project_id, canonical_data["title"]))

        for rev in canonical_data["revisions"].values():
            cursor.execute(
                "INSERT OR REPLACE INTO revisions VALUES (?, ?, ?, ?, ?)",
                (rev["revision_id"], project_id, rev["version_number"], 1 if rev["locked"] else 0, rev.get("locked_hash")),
            )

        for ast in canonical_data["assets"]:
            cursor.execute(
                "INSERT OR REPLACE INTO assets VALUES (?, ?, ?, ?, ?, ?)",
                (ast["asset_id"], project_id, ast["name"], ast["content_hash"], ast["license_state"], ast["processing_state"]),
            )

        for prop in canonical_data["proposals"]:
            cursor.execute(
                "INSERT OR REPLACE INTO proposals VALUES (?, ?, ?, ?, ?)",
                (prop["proposal_id"], project_id, prop["revision_id"], prop["status"], prop["summary"]),
            )

        self.conn.commit()

    def reset_db(self) -> None:
        """Truncate all tables."""
        if self.conn:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM proposals;")
            cursor.execute("DELETE FROM assets;")
            cursor.execute("DELETE FROM revisions;")
            cursor.execute("DELETE FROM projects;")
            self.conn.commit()

    def close(self) -> None:
        """Close connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
