from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from models.schemas import AttemptResult, ExamSession, StudyPackage
from services import postgres_store


@pytest.fixture
def package() -> StudyPackage:
    return StudyPackage.model_validate(
        {
            "course_id": "course-1",
            "course_name": "Test Course",
            "topics": [
                {"id": "topic-a", "name": "Topic A", "summary": "Summary"},
            ],
            "relationships": [],
            "questions": [
                {
                    "id": f"q-{index}",
                    "topic_id": "topic-a",
                    "question": f"Question {index}",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 0,
                    "explanation": "Explanation",
                }
                for index in range(3)
            ],
        }
    )


class FakeResult:
    def __init__(
        self,
        row: tuple[Any, ...] | None = None,
        rows: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self.row = row
        self.rows = rows or []

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.row

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def executemany(
        self, query: str, parameters: list[tuple[Any, ...]]
    ) -> None:
        self.connection.executemany_calls.append((query, parameters))
        if self.connection.fail_on_executemany:
            raise postgres_store.psycopg.Error("simulated write failure")

        for (
            user_id,
            session_id,
            question_id,
            selected_index,
            is_correct,
        ) in parameters:
            self.connection.attempt_snapshots.setdefault(
                (user_id, session_id), []
            ).append((question_id, selected_index, is_correct))


class FakeConnection:
    def __init__(self) -> None:
        self.course_packages: dict[tuple[str, str], dict[str, Any]] = {}
        self.sessions: dict[
            tuple[str, str], tuple[str, str, list[str]]
        ] = {}
        self.attempt_snapshots: dict[
            tuple[str, str], list[tuple[str, int | None, bool]]
        ] = {}
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.enter_count = 0
        self.fail_on_executemany = False
        self._transaction_snapshot: tuple[Any, ...] | None = None

    def __enter__(self) -> FakeConnection:
        self.enter_count += 1
        self._transaction_snapshot = deepcopy(
            (self.course_packages, self.sessions, self.attempt_snapshots)
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> bool:
        if exc_type is None:
            self.commit_count += 1
        else:
            self.rollback_count += 1
            assert self._transaction_snapshot is not None
            (
                self.course_packages,
                self.sessions,
                self.attempt_snapshots,
            ) = self._transaction_snapshot
        return False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def execute(
        self, query: str, parameters: tuple[Any, ...] = ()
    ) -> FakeResult:
        normalized_query = " ".join(query.lower().split())
        self.execute_calls.append((query, parameters))

        if normalized_query.startswith("select package_json from courses"):
            package_data = self.course_packages.get((parameters[0], parameters[1]))
            return FakeResult(
                (deepcopy(package_data),) if package_data is not None else None
            )

        if normalized_query.startswith("select 1 from courses"):
            key = (parameters[0], parameters[1])
            return FakeResult((1,) if key in self.course_packages else None)

        if normalized_query.startswith("select course_id from exam_sessions"):
            session = self.sessions.get((parameters[0], parameters[1]))
            return FakeResult((session[0],) if session is not None else None)

        if normalized_query.startswith(
            "select session_id, mode, question_ids from exam_sessions"
        ):
            user_id, course_id = parameters
            rows = [
                (session_id, mode, deepcopy(question_ids))
                for (stored_user_id, session_id), (
                    stored_course_id,
                    mode,
                    question_ids,
                ) in self.sessions.items()
                if stored_user_id == user_id and stored_course_id == course_id
            ]
            return FakeResult(rows=rows)

        if normalized_query.startswith("select a.session_id"):
            user_id, course_id = parameters
            rows = []
            for (stored_user_id, session_id), (
                stored_course_id,
                _mode,
                question_ids,
            ) in self.sessions.items():
                if stored_user_id != user_id or stored_course_id != course_id:
                    continue
                for (
                    question_id,
                    selected_index,
                    is_correct,
                ) in self.attempt_snapshots.get((user_id, session_id), []):
                    rows.append(
                        (session_id, question_id, selected_index, is_correct)
                    )
            return FakeResult(rows=rows)

        if normalized_query.startswith("insert into courses"):
            user_id, course_id, _course_name, package_json = parameters
            self.course_packages[(user_id, course_id)] = deepcopy(package_json.obj)
        elif normalized_query.startswith("insert into exam_sessions"):
            user_id, session_id, course_id, mode, question_ids = parameters
            self.sessions[(user_id, session_id)] = (
                course_id,
                mode,
                deepcopy(question_ids.obj),
            )
        elif normalized_query.startswith("delete from attempt_results"):
            self.attempt_snapshots.pop((parameters[0], parameters[1]), None)

        return FakeResult()


def use_connection(
    monkeypatch: pytest.MonkeyPatch, connection: FakeConnection
) -> None:
    monkeypatch.setattr(postgres_store, "_connect", lambda: connection)


def make_attempts(
    session_id: str,
    question_ids: list[str],
    *,
    selected_index: int = 0,
    is_correct: bool = True,
) -> list[AttemptResult]:
    return [
        AttemptResult(
            session_id=session_id,
            question_id=question_id,
            selected_index=selected_index,
            is_correct=is_correct,
        )
        for question_id in question_ids
    ]


def test_missing_database_url_returns_explicit_failure(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    monkeypatch.setattr(postgres_store, "load_dotenv", lambda **_: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        postgres_store.psycopg,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("must not connect"),
    )
    result = postgres_store.save_course("demo-user", package)

    assert result.success is False
    assert "Database is not configured" in result.message


def test_save_and_load_course_validate_study_package(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    connection = FakeConnection()
    use_connection(monkeypatch, connection)

    saved = postgres_store.save_course("demo-user", package)
    loaded = postgres_store.load_course("demo-user", package.course_id)

    assert saved.success is True
    assert loaded.success is True
    assert isinstance(loaded.package, StudyPackage)
    assert loaded.package == package

    invalid_package = package.model_copy(update={"topics": []})
    rejected_save = postgres_store.save_course("demo-user", invalid_package)
    connection.course_packages[("demo-user", package.course_id)]["questions"][0][
        "topic_id"
    ] = "missing-topic"
    rejected_load = postgres_store.load_course("demo-user", package.course_id)

    assert rejected_save.success is False
    assert rejected_load.success is False
    assert rejected_load.package is None


def test_saving_exam_and_answers_uses_one_transaction(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    connection = FakeConnection()
    connection.course_packages[("demo-user", package.course_id)] = (
        package.model_dump(mode="json")
    )
    use_connection(monkeypatch, connection)
    session = ExamSession(
        session_id="session-1",
        mode="mock",
        question_ids=["q-0"],
    )

    result = postgres_store.save_exam_result(
        "demo-user",
        package.course_id,
        session,
        make_attempts(session.session_id, session.question_ids),
    )

    assert result.success is True
    assert connection.enter_count == 1
    assert connection.commit_count == 1
    assert connection.rollback_count == 0
    assert any(
        "insert into exam_sessions" in sql.lower()
        for sql, _ in connection.execute_calls
    )
    assert any(
        "delete from attempt_results" in sql.lower()
        for sql, _ in connection.execute_calls
    )
    assert len(connection.executemany_calls) == 1


def test_resaving_same_session_replaces_its_answer_snapshot(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    connection = FakeConnection()
    connection.course_packages[("demo-user", package.course_id)] = (
        package.model_dump(mode="json")
    )
    use_connection(monkeypatch, connection)
    session = ExamSession(
        session_id="session-1",
        mode="mock",
        question_ids=["q-0", "q-1"],
    )

    first = postgres_store.save_exam_result(
        "demo-user",
        package.course_id,
        session,
        make_attempts(session.session_id, session.question_ids),
    )
    second = postgres_store.save_exam_result(
        "demo-user",
        package.course_id,
        session,
        make_attempts(
            session.session_id,
            session.question_ids,
            selected_index=1,
            is_correct=False,
        ),
    )

    assert first.success is True
    assert second.success is True
    assert connection.attempt_snapshots[("demo-user", "session-1")] == [
        ("q-0", 1, False),
        ("q-1", 1, False),
    ]


def test_database_write_failure_rolls_back_exam_and_answer_changes(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    connection = FakeConnection()
    connection.course_packages[("demo-user", package.course_id)] = (
        package.model_dump(mode="json")
    )
    session = ExamSession(
        session_id="session-1",
        mode="mock",
        question_ids=["q-0"],
    )
    connection.sessions[("demo-user", session.session_id)] = (
        package.course_id,
        session.mode,
        list(session.question_ids),
    )
    connection.attempt_snapshots[("demo-user", session.session_id)] = [
        ("q-0", 0, True)
    ]
    original_sessions = deepcopy(connection.sessions)
    original_attempts = deepcopy(connection.attempt_snapshots)
    connection.fail_on_executemany = True
    use_connection(monkeypatch, connection)

    result = postgres_store.save_exam_result(
        "demo-user",
        package.course_id,
        session,
        make_attempts(
            session.session_id,
            session.question_ids,
            selected_index=1,
            is_correct=False,
        ),
    )

    assert result.success is False
    assert connection.rollback_count == 1
    assert connection.commit_count == 0
    assert connection.sessions == original_sessions
    assert connection.attempt_snapshots == original_attempts


def test_exam_with_question_outside_course_is_not_saved(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    connection = FakeConnection()
    connection.course_packages[("demo-user", package.course_id)] = (
        package.model_dump(mode="json")
    )
    use_connection(monkeypatch, connection)
    session = ExamSession(
        session_id="invalid-session",
        mode="mock",
        question_ids=["not-in-course"],
    )
    attempts = make_attempts(session.session_id, session.question_ids)

    result = postgres_store.save_exam_result(
        "demo-user",
        package.course_id,
        session,
        attempts,
    )

    assert result.success is False
    assert "not found in the course" in result.message
    assert connection.sessions == {}
    assert connection.attempt_snapshots == {}
    assert not any(
        "insert into exam_sessions" in sql.lower()
        or "delete from attempt_results" in sql.lower()
        for sql, _ in connection.execute_calls
    )
    assert connection.executemany_calls == []
    assert connection.rollback_count == 1
    assert connection.commit_count == 0


def test_demo_user_ids_are_scoped_in_sql_parameters_and_results(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    connection = FakeConnection()
    first_package = package.model_copy(update={"course_name": "First User"})
    second_package = package.model_copy(update={"course_name": "Second User"})
    use_connection(monkeypatch, connection)

    assert postgres_store.save_course("user-a", first_package).success is True
    assert postgres_store.save_course("user-b", second_package).success is True
    first_course = postgres_store.load_course("user-a", package.course_id)
    second_course = postgres_store.load_course("user-b", package.course_id)
    first_history = postgres_store.load_course_history("user-a", package.course_id)
    second_history = postgres_store.load_course_history("user-b", package.course_id)

    assert first_course.package is not None
    assert second_course.package is not None
    assert first_course.package.course_name == "First User"
    assert second_course.package.course_name == "Second User"
    assert first_history.package is not None
    assert second_history.package is not None
    assert first_history.package.course_name == "First User"
    assert second_history.package.course_name == "Second User"

    scoped_queries = [
        (sql, parameters)
        for sql, parameters in connection.execute_calls
        if "where demo_user_id = %s" in " ".join(sql.lower().split())
        or "where s.demo_user_id = %s" in " ".join(sql.lower().split())
    ]
    assert scoped_queries
    assert all(
        parameters[0] in {"user-a", "user-b"}
        for _, parameters in scoped_queries
    )
    assert {
        parameters[0] for _, parameters in scoped_queries
    } == {"user-a", "user-b"}


def test_exam_history_is_isolated_for_users_with_same_session_id(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    connection = FakeConnection()
    use_connection(monkeypatch, connection)
    session = ExamSession(
        session_id="shared-session",
        mode="mock",
        question_ids=["q-0"],
    )
    user_a_attempt = AttemptResult(
        session_id=session.session_id,
        question_id="q-0",
        selected_index=0,
        is_correct=True,
    )
    user_b_attempt = AttemptResult(
        session_id=session.session_id,
        question_id="q-0",
        selected_index=None,
        is_correct=False,
    )

    assert postgres_store.save_course("user-a", package).success is True
    assert postgres_store.save_course("user-b", package).success is True
    assert postgres_store.save_exam_result(
        "user-a", package.course_id, session, [user_a_attempt]
    ).success is True
    assert postgres_store.save_exam_result(
        "user-b", package.course_id, session, [user_b_attempt]
    ).success is True

    user_a_history = postgres_store.load_course_history(
        "user-a", package.course_id
    )
    user_b_history = postgres_store.load_course_history(
        "user-b", package.course_id
    )

    assert user_a_history.success is True
    assert user_b_history.success is True
    assert user_a_history.sessions == [session]
    assert user_b_history.sessions == [session]
    assert len(user_a_history.sessions) == len(user_b_history.sessions) == 1
    assert len(user_a_history.attempts) == len(user_b_history.attempts) == 1
    assert user_a_history.attempts[0] == user_a_attempt
    assert user_a_history.attempts[0].selected_index == 0
    assert user_a_history.attempts[0].is_correct is True
    assert user_b_history.attempts[0] == user_b_attempt
    assert user_b_history.attempts[0].selected_index is None
    assert user_b_history.attempts[0].is_correct is False


def test_course_history_validates_models_and_recalculates_mastery(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    connection = FakeConnection()
    connection.course_packages[("demo-user", package.course_id)] = (
        package.model_dump(mode="json")
    )
    session = ExamSession(
        session_id="session-1",
        mode="mock",
        question_ids=["q-0", "q-1", "q-2"],
    )
    connection.sessions[("demo-user", session.session_id)] = (
        package.course_id,
        session.mode,
        list(session.question_ids),
    )
    connection.attempt_snapshots[("demo-user", session.session_id)] = [
        (attempt.question_id, attempt.selected_index, attempt.is_correct)
        for attempt in make_attempts(session.session_id, session.question_ids)
    ]
    use_connection(monkeypatch, connection)

    result = postgres_store.load_course_history("demo-user", package.course_id)

    assert result.success is True
    assert result.package == package
    assert result.sessions == [session]
    assert all(isinstance(restored, ExamSession) for restored in result.sessions)
    assert all(isinstance(restored, AttemptResult) for restored in result.attempts)
    assert len(result.attempts) == 3
    assert result.topic_stats[0].topic_id == "topic-a"
    assert result.topic_stats[0].mode == "mock"
    assert result.topic_stats[0].correct == 3
    assert result.topic_stats[0].attempted == 3
    assert result.topic_stats[0].accuracy == 100
    assert result.mastery_statuses[("topic-a", "mock")] == "mastered"
    assert result.mastery_statuses[("topic-a", "topic")] == "unattempted"


@pytest.mark.parametrize(
    ("session_mode", "selected_index"),
    [
        ("invalid-mode", 0),
        ("mock", "invalid-index"),
    ],
)
def test_course_history_rejects_invalid_restored_models(
    monkeypatch: pytest.MonkeyPatch,
    package: StudyPackage,
    session_mode: str,
    selected_index: Any,
) -> None:
    connection = FakeConnection()
    connection.course_packages[("demo-user", package.course_id)] = (
        package.model_dump(mode="json")
    )
    connection.sessions[("demo-user", "session-1")] = (
        package.course_id,
        session_mode,
        ["q-0"],
    )
    connection.attempt_snapshots[("demo-user", "session-1")] = [
        ("q-0", selected_index, False)
    ]
    use_connection(monkeypatch, connection)

    result = postgres_store.load_course_history("demo-user", package.course_id)

    assert result.success is False
    assert result.sessions == []
    assert result.attempts == []
