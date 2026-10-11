"""Shared PostgreSQL connection configuration, without exposing credentials."""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


class DatabaseConfigurationError(Exception):
    """A configuration error whose message is safe to display."""


def connect_database() -> psycopg.Connection:
    """Connect using the existing database settings and require transport TLS."""
    load_dotenv(
        dotenv_path=Path(__file__).resolve().parents[1] / ".env",
        override=False,
    )

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise DatabaseConfigurationError("Database is not configured.")

    sslmode = os.getenv("DATABASE_SSLMODE", "require").strip().lower()
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        raise DatabaseConfigurationError(
            "Database TLS must use require, verify-ca, or verify-full."
        )

    return psycopg.connect(
        database_url,
        sslmode=sslmode,
        connect_timeout=5,
        prepare_threshold=None,
    )
