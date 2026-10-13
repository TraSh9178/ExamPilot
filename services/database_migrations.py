"""Explicit, transactional PostgreSQL migrations; never called by page rendering."""

from hashlib import sha256
from pathlib import Path

import psycopg

from services.database import DatabaseConfigurationError, connect_database

MIGRATION_DIRECTORY = Path(__file__).resolve().parents[1] / "db" / "migrations"


class MigrationError(Exception):
    """A safe migration error without database credentials."""


def apply_migrations(connection: psycopg.Connection, directory: Path = MIGRATION_DIRECTORY) -> list[str]:
    files = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    if not files:
        raise MigrationError("No migration files found.")
    versions = [path.name.split("_", 1)[0] for path in files]
    if len(versions) != len(set(versions)):
        raise MigrationError("Duplicate migration versions.")
    sources = {path.name: path.read_bytes() for path in files}
    applied_now = []
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('exampilot-schema-migrations', 0))")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS exampilot_schema_migrations (
                filename TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        applied = dict(connection.execute("SELECT filename, checksum FROM exampilot_schema_migrations").fetchall())
        for filename, checksum in applied.items():
            if filename not in sources or sha256(sources[filename]).hexdigest() != checksum:
                raise MigrationError("Applied migration files were changed or removed; restore their original contents.")
        for filename, source in sources.items():
            if filename in applied:
                continue
            if applied and filename < max(applied):
                raise MigrationError("New migrations must follow all applied versions.")
            connection.execute(source.decode("utf-8"), prepare=False)
            connection.execute(
                "INSERT INTO exampilot_schema_migrations (filename, checksum) VALUES (%s, %s)",
                (filename, sha256(source).hexdigest()),
            )
            applied_now.append(filename)
    return applied_now


def main() -> int:
    try:
        with connect_database() as connection:
            applied = apply_migrations(connection)
    except (DatabaseConfigurationError, MigrationError) as exc:
        print(str(exc))
        return 1
    except (OSError, psycopg.Error):
        print("Migrations failed; the transaction was rolled back. Check configuration and schema compatibility.")
        return 1
    print("Applied: " + (", ".join(applied) if applied else "none; schema already current"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
