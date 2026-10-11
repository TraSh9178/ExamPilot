"""PostgreSQL account registration and login.

Create missing account tables with ``python -m services.auth_service``.
Setup runs only ``db/auth_schema_minimal.sql`` and leaves existing permissions,
RLS settings, policies, and learning tables untouched.
The C-managed ``public.demo_users`` parent table must already exist.
Normal login requests never create or alter database tables.
"""

from dataclasses import dataclass
from pathlib import Path
import re
from uuid import uuid4

import psycopg

from services.database import DatabaseConfigurationError, connect_database
from services.password_service import (
    PasswordKDFError,
    hash_password,
    validate_password,
    verify_password,
)


_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]{3,32}\Z", re.ASCII)
_MAX_FAILED_ATTEMPTS = 5
# A valid hash unrelated to any account, used to run the same password KDF when
# a username is absent. A fixed value avoids an extra first-request hash cost.
_DUMMY_PASSWORD_HASH = (
    "scrypt$v1$n=131072,r=8,p=1$-m7z0AHTk2AH4hAEy8O9Lg$"
    "7r-l-mfzYdGaQv-eveyfIjQ5PEBE33OjtEk7bsO-1hw"
)


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    username: str


@dataclass(frozen=True)
class AuthResult:
    success: bool
    user: AuthUser | None
    message: str
    error_code: str | None = None


def _normalize_username(username: str) -> str:
    if not isinstance(username, str):
        raise ValueError("Username must be text.")
    value = username.strip()
    if not _USERNAME_PATTERN.fullmatch(value):
        raise ValueError(
            "Username must contain 3–32 letters, numbers, underscores, periods, or hyphens."
        )
    return value.lower()


def _invalid_credentials() -> AuthResult:
    return AuthResult(
        False,
        None,
        "Unable to sign in. Check your username and password, or try again later.",
        "invalid_credentials",
    )


def _database_failure(error: psycopg.Error) -> AuthResult:
    if isinstance(error, psycopg.errors.UndefinedTable):
        return AuthResult(
            False,
            None,
            "Account setup is incomplete. Please contact the site administrator.",
            "schema_unavailable",
        )
    return AuthResult(
        False,
        None,
        "The account service is temporarily unavailable. Please try again later.",
        "database_unavailable",
    )


def _password_failure() -> AuthResult:
    return AuthResult(
        False,
        None,
        "The account service is temporarily unavailable. Please try again later.",
        "password_service_unavailable",
    )


def initialize_auth_schema() -> AuthResult:
    """Create missing Auth tables, requiring the existing public.demo_users parent."""
    schema_path = (
        Path(__file__).resolve().parents[1] / "db" / "auth_schema_minimal.sql"
    )
    try:
        schema = schema_path.read_bytes()
        with connect_database() as connection:
            for statement in schema.split(b";"):
                if statement.strip():
                    connection.execute(statement)
    except DatabaseConfigurationError as error:
        return AuthResult(False, None, str(error), "database_not_configured")
    except OSError:
        return AuthResult(
            False, None, "Account schema files are unavailable.", "schema_unavailable"
        )
    except psycopg.Error as error:
        return _database_failure(error)
    return AuthResult(True, None, "Account database is ready.")


def register_user(username: str, password: str) -> AuthResult:
    """Register one account and return its authenticated identity on success."""
    try:
        normalized_username = _normalize_username(username)
    except ValueError as error:
        return AuthResult(False, None, str(error), "invalid_username")
    try:
        validate_password(password)
    except ValueError as error:
        return AuthResult(False, None, str(error), "invalid_password")

    try:
        password_hash = hash_password(password)
    except PasswordKDFError:
        return _password_failure()
    user = AuthUser(str(uuid4()), normalized_username)
    try:
        with connect_database() as connection:
            connection.execute(
                "INSERT INTO public.demo_users (demo_user_id) VALUES (%s)",
                (user.user_id,),
            )
            connection.execute(
                """
                INSERT INTO exampilot_auth.users (user_id, username, password_hash)
                VALUES (%s, %s, %s)
                """,
                (user.user_id, user.username, password_hash),
            )
    except DatabaseConfigurationError:
        return AuthResult(
            False,
            None,
            "The account service is temporarily unavailable. Please try again later.",
            "database_not_configured",
        )
    except psycopg.errors.UniqueViolation:
        return AuthResult(
            False, None, "This username is already taken.", "username_taken"
        )
    except psycopg.Error as error:
        return _database_failure(error)
    return AuthResult(True, user, "Account created.")


def login_user(username: str, password: str) -> AuthResult:
    """Authenticate an account and persist a five-minute lock after five failures."""
    try:
        normalized_username = _normalize_username(username)
        validate_password(password)
    except ValueError:
        return _invalid_credentials()

    try:
        with connect_database() as connection:
            row = connection.execute(
                """
                SELECT user_id, username, password_hash, failed_attempts,
                       locked_until, CURRENT_TIMESTAMP
                FROM exampilot_auth.users
                WHERE username = %s
                FOR UPDATE
                """,
                (normalized_username,),
            ).fetchone()
            if row is None:
                verify_password(password, _DUMMY_PASSWORD_HASH)
                return _invalid_credentials()

            user_id, canonical_username, password_hash, failures, locked_until, now = row
            password_matches = verify_password(password, password_hash)
            if locked_until is not None and locked_until > now:
                return _invalid_credentials()

            if password_matches:
                connection.execute(
                    """
                    UPDATE exampilot_auth.users
                    SET failed_attempts = 0, locked_until = NULL
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                return AuthResult(True, AuthUser(user_id, canonical_username), "Signed in.")

            previous_failures = 0 if locked_until is not None else failures
            next_failures = min(previous_failures + 1, _MAX_FAILED_ATTEMPTS)
            connection.execute(
                """
                UPDATE exampilot_auth.users
                SET failed_attempts = %s,
                    locked_until = CASE
                        WHEN %s >= 5
                        THEN CURRENT_TIMESTAMP + INTERVAL '5 minutes'
                        ELSE NULL
                    END
                WHERE user_id = %s
                """,
                (next_failures, next_failures, user_id),
            )
            return _invalid_credentials()
    except PasswordKDFError:
        # Let the connection context roll back before reporting an engine fault.
        return _password_failure()
    except DatabaseConfigurationError:
        return AuthResult(
            False,
            None,
            "The account service is temporarily unavailable. Please try again later.",
            "database_not_configured",
        )
    except psycopg.Error as error:
        return _database_failure(error)


if __name__ == "__main__":
    result = initialize_auth_schema()
    print(result.message)
    raise SystemExit(0 if result.success else 1)
