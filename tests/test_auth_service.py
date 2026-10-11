from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from services import auth_service, database


PASSWORD = "a sufficiently long password"
WRONG_PASSWORD = "a different long password"


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    """Emulate account transactions and counters, retaining SQL for assertions."""

    def __init__(self):
        self.users = {}
        self.demo_users = set()
        self.schemas = {"exampilot_auth"}
        self.tables = {"public.demo_users", "exampilot_auth.users"}
        self.calls = []
        self.now = datetime(2026, 10, 11, 15, 0, tzinfo=timezone.utc)
        self.commits = 0
        self.rollbacks = 0
        self.error = None

    def __enter__(self):
        self.snapshot = deepcopy((self.users, self.demo_users, self.schemas, self.tables))
        return self

    def __exit__(self, error_type, *_):
        if error_type is None:
            self.commits += 1
        else:
            self.users, self.demo_users, self.schemas, self.tables = self.snapshot
            self.rollbacks += 1
        return False

    def execute(self, query, parameters=()):
        text_query = query.decode() if isinstance(query, bytes) else query
        normalized_query = " ".join(text_query.lower().split())
        self.calls.append((query, parameters))
        if self.error is not None:
            raise self.error

        if normalized_query.startswith("create schema if not exists"):
            self.schemas.add(normalized_query.split()[5])
            return FakeResult()
        if normalized_query.startswith("create table if not exists"):
            table = normalized_query.split()[5]
            if table == "exampilot_auth.users" and table not in self.tables:
                assert "exampilot_auth" in self.schemas
                if "public.demo_users" not in self.tables:
                    raise psycopg.errors.UndefinedTable(
                        'relation "public.demo_users" does not exist'
                    )
            self.tables.add(table)
            return FakeResult()
        if normalized_query.startswith("insert into public.demo_users"):
            self.demo_users.add(parameters[0])
        elif normalized_query.startswith("insert into exampilot_auth.users"):
            user_id, username, password_hash = parameters
            if username in self.users:
                raise psycopg.errors.UniqueViolation("private duplicate record")
            self.users[username] = {
                "user_id": user_id,
                "username": username,
                "password_hash": password_hash,
                "failed_attempts": 0,
                "locked_until": None,
            }
        elif normalized_query.startswith("select user_id"):
            assert normalized_query.endswith("for update")
            user = self.users.get(parameters[0])
            if user is None:
                return FakeResult()
            return FakeResult(
                tuple(
                    user[key]
                    for key in (
                        "user_id", "username", "password_hash",
                        "failed_attempts", "locked_until",
                    )
                ) + (self.now,)
            )
        elif normalized_query.startswith("update exampilot_auth.users"):
            user = next(
                user for user in self.users.values()
                if user["user_id"] == parameters[-1]
            )
            if len(parameters) == 1:
                user["failed_attempts"] = 0
                user["locked_until"] = None
            else:
                user["failed_attempts"] = parameters[0]
                user["locked_until"] = (
                    self.now + timedelta(minutes=5)
                    if parameters[1] >= 5 else None
                )
        else:
            pytest.fail(f"Unexpected SQL operation: {normalized_query}")
        return FakeResult()


@pytest.fixture
def backend(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(auth_service, "connect_database", lambda: connection)
    # The password service has separate tests for its actual KDF and policy.
    monkeypatch.setattr(auth_service, "hash_password", lambda value: "hash:" + value)
    verifications = []

    def verify(password, encoded):
        verifications.append((password, encoded))
        return encoded == "hash:" + password

    monkeypatch.setattr(auth_service, "verify_password", verify)
    connection.verifications = verifications
    return connection


def test_registration_normalizes_username_and_creates_both_records_atomically(backend):
    result = auth_service.register_user("  Alice_23  ", PASSWORD)

    assert result.success and result.error_code is None
    assert result.user.username == "alice_23"
    assert UUID(result.user.user_id).version == 4
    assert backend.demo_users == {result.user.user_id}
    assert backend.users["alice_23"]["password_hash"] == "hash:" + PASSWORD
    assert backend.commits == 1 and backend.rollbacks == 0
    assert all(PASSWORD not in query for query, _ in backend.calls)
    assert all("%s" in query for query, _ in backend.calls)
    assert not any("CREATE" in query.upper() for query, _ in backend.calls)


def test_case_insensitive_duplicate_registration_rolls_back_demo_user(backend):
    first = auth_service.register_user("alice", PASSWORD)
    result = auth_service.register_user("ALICE", PASSWORD)

    assert first.success
    assert result.error_code == "username_taken" and result.user is None
    assert backend.demo_users == {first.user.user_id}
    assert len(backend.users) == 1 and backend.rollbacks == 1


@pytest.mark.parametrize("username", ["ab", "a" * 33, "张三", "has space", "' OR 1=1--", None])
def test_invalid_registration_username_never_contacts_database(backend, username):
    result = auth_service.register_user(username, PASSWORD)

    assert result.error_code == "invalid_username"
    assert backend.calls == []


@pytest.mark.parametrize("password", ["short", "x" * 129, None])
def test_invalid_registration_password_never_contacts_database(backend, password):
    result = auth_service.register_user("alice", password)

    assert result.error_code == "invalid_password"
    assert backend.calls == []


def test_registration_kdf_failure_does_not_create_any_records(backend, monkeypatch):
    def unavailable_password_engine(password):
        raise auth_service.PasswordKDFError("private engine details")

    monkeypatch.setattr(auth_service, "hash_password", unavailable_password_engine)

    result = auth_service.register_user("alice", PASSWORD)

    assert not result.success and result.user is None
    assert result.error_code == "password_service_unavailable"
    assert "private" not in result.message
    assert backend.calls == []
    assert backend.users == {} and backend.demo_users == set()
    assert backend.commits == 0 and backend.rollbacks == 0


@pytest.mark.parametrize("username", ["alice", "unknown"])
def test_login_kdf_failure_rolls_back_without_changing_counters(
    backend, monkeypatch, username
):
    auth_service.register_user("alice", PASSWORD)
    backend.users["alice"]["failed_attempts"] = 4
    existing_users = deepcopy(backend.users)
    existing_demo_users = backend.demo_users.copy()
    existing_commits = backend.commits
    backend.calls.clear()

    def unavailable_password_engine(password, encoded):
        raise auth_service.PasswordKDFError("private engine details")

    monkeypatch.setattr(auth_service, "verify_password", unavailable_password_engine)

    result = auth_service.login_user(username, PASSWORD)

    assert not result.success and result.user is None
    assert result.error_code == "password_service_unavailable"
    assert "private" not in result.message
    assert backend.users == existing_users and backend.demo_users == existing_demo_users
    assert backend.commits == existing_commits and backend.rollbacks == 1
    assert len(backend.calls) == 1
    assert backend.calls[0][0].strip().startswith("SELECT")


def test_login_returns_stable_account_id_and_resets_failed_attempts(backend):
    registered = auth_service.register_user("alice", PASSWORD)
    auth_service.login_user("alice", WRONG_PASSWORD)
    result = auth_service.login_user(" ALICE ", PASSWORD)

    assert result.success and result.user == registered.user
    assert backend.users["alice"]["failed_attempts"] == 0
    assert backend.users["alice"]["locked_until"] is None
    assert all("CREATE" not in query.upper() for query, _ in backend.calls)


def test_unknown_user_runs_dummy_verification_without_account_mutation(backend):
    result = auth_service.login_user("unknown", PASSWORD)

    assert result.error_code == "invalid_credentials" and result.user is None
    assert backend.verifications == [(PASSWORD, auth_service._DUMMY_PASSWORD_HASH)]
    assert backend.users == {} and backend.demo_users == set()
    assert len(backend.calls) == 1


def test_unknown_wrong_and_locked_accounts_have_identical_failures(backend):
    unknown = auth_service.login_user("unknown", PASSWORD)
    auth_service.register_user("alice", PASSWORD)
    wrong = auth_service.login_user("alice", WRONG_PASSWORD)
    for _ in range(4):
        auth_service.login_user("alice", WRONG_PASSWORD)
    locked = auth_service.login_user("alice", PASSWORD)

    assert unknown == wrong == locked
    assert backend.users["alice"]["failed_attempts"] == 5
    assert backend.users["alice"]["locked_until"] == backend.now + timedelta(minutes=5)
    assert backend.verifications[-1] == (PASSWORD, "hash:" + PASSWORD)


def test_lock_expires_without_being_extended_by_requests(backend):
    auth_service.register_user("alice", PASSWORD)
    for _ in range(5):
        auth_service.login_user("alice", WRONG_PASSWORD)
    lock_expiry = backend.users["alice"]["locked_until"]
    backend.now += timedelta(minutes=4)
    assert not auth_service.login_user("alice", WRONG_PASSWORD).success
    assert backend.users["alice"]["locked_until"] == lock_expiry

    backend.now = lock_expiry
    assert auth_service.login_user("alice", PASSWORD).success
    assert backend.users["alice"]["failed_attempts"] == 0
    assert backend.users["alice"]["locked_until"] is None


def test_wrong_password_after_expired_lock_starts_new_failure_count(backend):
    auth_service.register_user("alice", PASSWORD)
    for _ in range(5):
        auth_service.login_user("alice", WRONG_PASSWORD)
    backend.now += timedelta(minutes=5)

    assert not auth_service.login_user("alice", WRONG_PASSWORD).success
    assert backend.users["alice"]["failed_attempts"] == 1
    assert backend.users["alice"]["locked_until"] is None


def test_expired_lock_requires_five_new_failures_to_lock_again(backend):
    auth_service.register_user("alice", PASSWORD)
    for _ in range(5):
        auth_service.login_user("alice", WRONG_PASSWORD)
    backend.now = backend.users["alice"]["locked_until"]

    for failure_count in range(1, 5):
        assert not auth_service.login_user("alice", WRONG_PASSWORD).success
        assert backend.users["alice"]["failed_attempts"] == failure_count
        assert backend.users["alice"]["locked_until"] is None

    assert not auth_service.login_user("alice", WRONG_PASSWORD).success
    assert backend.users["alice"]["failed_attempts"] == 5
    assert backend.users["alice"]["locked_until"] == backend.now + timedelta(minutes=5)


@pytest.mark.parametrize("username,password", [("?bad", PASSWORD), ("alice", "short"), (None, PASSWORD)])
def test_invalid_login_input_has_generic_message_and_no_database_access(backend, username, password):
    result = auth_service.login_user(username, password)

    assert result == auth_service._invalid_credentials()
    assert backend.calls == []


@pytest.mark.parametrize("operation", [auth_service.register_user, auth_service.login_user])
def test_database_errors_never_expose_connection_details(backend, operation):
    backend.error = psycopg.OperationalError("password=secret host=private.example")

    result = operation("alice", PASSWORD)

    assert result.error_code == "database_unavailable"
    assert "secret" not in result.message and "private.example" not in result.message
    assert backend.rollbacks == 1


@pytest.mark.parametrize("operation", [auth_service.register_user, auth_service.login_user])
def test_missing_auth_schema_fails_with_actionable_safe_error(backend, operation):
    backend.error = psycopg.errors.UndefinedTable("relation private_auth_users does not exist")

    result = operation("alice", PASSWORD)

    assert result.error_code == "schema_unavailable"
    assert "administrator" in result.message and "private_auth_users" not in result.message


def test_initialization_creates_only_missing_account_schema_and_tables(backend):
    backend.schemas.clear()
    backend.tables = {"public.demo_users"}
    result = auth_service.initialize_auth_schema()

    assert result.success and result.user is None
    assert backend.commits == 1
    queries = [query.decode() for query, _ in backend.calls]
    assert len(queries) == 2
    assert all(query.strip().startswith("CREATE ") for query in queries)
    assert not any("CREATE TABLE IF NOT EXISTS public.demo_users" in query for query in queries)
    assert any("CREATE SCHEMA IF NOT EXISTS exampilot_auth" in query for query in queries)
    assert any("CREATE TABLE IF NOT EXISTS exampilot_auth.users" in query for query in queries)
    assert any("ON DELETE RESTRICT" in query for query in queries)
    assert backend.schemas == {"exampilot_auth"}
    assert backend.tables == {"public.demo_users", "exampilot_auth.users"}
    assert all(isinstance(query, bytes) for query, _ in backend.calls)


def test_initialization_requires_existing_parent_and_rolls_back_auth_schema(backend):
    backend.schemas.clear()
    backend.tables.clear()

    result = auth_service.initialize_auth_schema()

    assert not result.success and result.error_code == "schema_unavailable"
    assert backend.commits == 0 and backend.rollbacks == 1
    assert backend.schemas == set() and backend.tables == set()
    assert len(backend.calls) == 2
    assert all(query.strip().startswith(b"CREATE ") for query, _ in backend.calls)


def test_initialization_preserves_existing_parent_data_and_can_be_repeated(backend):
    backend.tables = {"public.demo_users", "public.courses"}
    backend.schemas.clear()
    backend.demo_users.add("existing-demo-user")

    assert auth_service.initialize_auth_schema().success
    assert auth_service.initialize_auth_schema().success

    assert backend.commits == 2
    assert backend.demo_users == {"existing-demo-user"}
    assert backend.tables == {
        "public.demo_users", "public.courses", "exampilot_auth.users",
    }
    assert all(query.strip().startswith(b"CREATE ") for query, _ in backend.calls)


def test_initialization_reads_only_minimal_schema(monkeypatch, backend):
    original_read = Path.read_bytes
    read_paths = []

    def read_bytes(path):
        read_paths.append(path)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    assert auth_service.initialize_auth_schema().success
    assert read_paths == [
        Path(auth_service.__file__).resolve().parents[1] / "db" / "auth_schema_minimal.sql"
    ]


def test_initialization_rolls_back_created_schema_when_a_later_statement_fails(backend, monkeypatch):
    backend.schemas.clear()
    backend.tables = {"public.demo_users"}
    execute = backend.execute

    def fail_account_table(query, parameters=()):
        if b"CREATE TABLE IF NOT EXISTS exampilot_auth.users" in query:
            raise psycopg.OperationalError("private account schema setup details")
        return execute(query, parameters)

    monkeypatch.setattr(backend, "execute", fail_account_table)
    result = auth_service.initialize_auth_schema()

    assert not result.success and "private" not in result.message
    assert backend.rollbacks == 1
    assert backend.schemas == set() and backend.tables == {"public.demo_users"}


def test_schema_failure_rolls_back_and_hides_credentials(backend):
    backend.error = psycopg.OperationalError("private connection string")

    result = auth_service.initialize_auth_schema()

    assert not result.success and "private" not in result.message
    assert backend.rollbacks == 1


@pytest.mark.parametrize(
    "operation,args",
    [(auth_service.register_user, ("alice", PASSWORD)),
     (auth_service.login_user, ("alice", PASSWORD)),
     (auth_service.initialize_auth_schema, ())],
)
def test_missing_database_configuration_is_reported_safely(monkeypatch, operation, args):
    def unconfigured():
        raise database.DatabaseConfigurationError("Database is not configured.")

    monkeypatch.setattr(auth_service, "connect_database", unconfigured)
    result = operation(*args)

    assert result.error_code == "database_not_configured" and result.user is None
    if operation is not auth_service.initialize_auth_schema:
        assert "not configured" not in result.message


def test_database_connection_requires_configured_url(monkeypatch):
    monkeypatch.setattr(database, "load_dotenv", lambda **kwargs: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(database.DatabaseConfigurationError, match="not configured"):
        database.connect_database()


@pytest.mark.parametrize("sslmode", ["require", "verify-ca", "verify-full"])
def test_connection_preserves_env_and_enforces_supported_tls(monkeypatch, sslmode):
    dotenv_calls = []
    connect_calls = []
    monkeypatch.setattr(database, "load_dotenv", lambda **kwargs: dotenv_calls.append(kwargs))
    monkeypatch.setenv("DATABASE_URL", "postgresql://placeholder.example/exampilot")
    monkeypatch.setenv("DATABASE_SSLMODE", sslmode.upper())
    sentinel = object()

    def connect(*args, **kwargs):
        connect_calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(database.psycopg, "connect", connect)

    assert database.connect_database() is sentinel
    assert dotenv_calls == [{
        "dotenv_path": Path(database.__file__).resolve().parents[1] / ".env",
        "override": False,
    }]
    assert connect_calls == [
        (("postgresql://placeholder.example/exampilot",), {
            "sslmode": sslmode, "connect_timeout": 5, "prepare_threshold": None,
        })
    ]


@pytest.mark.parametrize("sslmode", ["disable", "allow", "prefer", "invalid", ""])
def test_connection_rejects_insecure_tls_before_connecting(monkeypatch, sslmode):
    monkeypatch.setattr(database, "load_dotenv", lambda **kwargs: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://placeholder.example/exampilot")
    monkeypatch.setenv("DATABASE_SSLMODE", sslmode)
    monkeypatch.setattr(database.psycopg, "connect", lambda *args, **kwargs: pytest.fail("Must not connect"))

    with pytest.raises(database.DatabaseConfigurationError, match="TLS"):
        database.connect_database()
