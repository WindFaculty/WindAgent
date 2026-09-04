"""PostgreSQL database backup utility for WindAgent V2."""

from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys
from pathlib import Path


def backup_database(output_dir: Path, db_url: str | None = None) -> Path:
    """Trigger pg_dump against the configured PostgreSQL database."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%SZ")
    backup_file = output_dir / f"windagent_backup_{timestamp}.sql.gz"

    db_url = db_url or os.environ.get("DATABASE_URL", "postgresql://windagent:windagent_secret_pass@localhost:5432/windagent_v2")
    # Strip asyncpg dialect if present for pg_dump compatibility
    pg_dump_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    print(f"Starting database backup to {backup_file}...")
    cmd = f"pg_dump --dbname={pg_dump_url} | gzip > {backup_file}"
    try:
        subprocess.run(cmd, shell=True, check=True)
        print(f"[OK] Database backup completed successfully: {backup_file} ({backup_file.stat().st_size} bytes)")
        return backup_file
    except Exception as e:
        print(f"[ERROR] Database backup failed: {e}", file=sys.stderr)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="WindAgent V2 Database Backup Utility")
    parser.add_argument("--output-dir", default="./backups", help="Directory to store compressed SQL dumps")
    parser.add_argument("--db-url", default=None, help="PostgreSQL connection string")

    args = parser.parse_args()
    try:
        backup_database(Path(args.output_dir), args.db_url)
        sys.exit(0)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
