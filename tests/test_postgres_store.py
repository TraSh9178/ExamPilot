from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from models.schemas import AttemptResult, ExamSession, Question, StudyPackage, Topic
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

        if normalized_query.startswith(
            "select course_id, course_name from courses"
        ):
            user_id = parameters[0]
            rows = sorted(
                (
                    (course_id, package_data["course_name"])
                    for (stored_user_id, course_id), package_data
                    in self.course_packages.items()
                    if stored_user_id == user_id
                ),
                key=lambda row: row[0],
            )
            return FakeResult(rows=rows)

        if normalized_query.startswith("select package_json from courses"):
            package_data = self.course_packages.get((parameters[0], parameters[1]))
            return FakeResult(
                (deepcopy(package_data),) if package_data is not None else None
            )

        if normalized_query.startswith("select 1 from courses"):
            key = (parameters[0], parameters[1])
            return FakeResult((1,) if key in self.course_packages else None)

        if normalized_query.startswith("select mode, question_ids from exam_sessions"):
            session = self.sessions.get((parameters[0], parameters[1]))
            return FakeResult((session[1], deepcopy(session[2])) if session else None)
        if normalized_query.startswith("select question_id, selected_index, is_correct from attempt_results"):
            return FakeResult(rows=deepcopy(self.attempt_snapshots.get((parameters[0], parameters[1]), [])))

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


def test_list_saved_courses_returns_sorted_ids_and_names(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    connection = FakeConnection()
    use_connection(monkeypatch, connection)
    for course_id, course_name in [
        ("course-z", "Z Course"),
        ("course-a", "A Course"),
    ]:
        saved_package = package.model_copy(
            update={"course_id": course_id, "course_name": course_name}
        )
        assert postgres_store.save_course("demo-user", saved_package).success

    result = postgres_store.list_saved_courses("demo-user")

    assert result.success is True
    assert result.courses == [
        postgres_store.SavedCourseSummary("course-a", "A Course"),
        postgres_store.SavedCourseSummary("course-z", "Z Course"),
    ]
    query, parameters = connection.execute_calls[-1]
    normalized_query = " ".join(query.lower().split())
    assert "where demo_user_id = %s" in normalized_query
    assert "order by course_id" in normalized_query
    assert parameters == ("demo-user",)


def test_list_saved_courses_empty_list_is_successful(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    use_connection(monkeypatch, connection)

    result = postgres_store.list_saved_courses("demo-user")

    assert result.success is True
    assert result.courses == []


def test_list_saved_courses_are_isolated_by_user(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    connection = FakeConnection()
    use_connection(monkeypatch, connection)
    shared_course = package.model_copy(
        update={"course_id": "shared-id", "course_name": "Same Name"}
    )
    other_course = package.model_copy(
        update={"course_id": "other-id", "course_name": "Other Course"}
    )
    assert postgres_store.save_course("user-a", shared_course).success
    assert postgres_store.save_course("user-b", shared_course).success
    assert postgres_store.save_course("user-b", other_course).success

    user_a_courses = postgres_store.list_saved_courses("user-a")
    user_b_courses = postgres_store.list_saved_courses("user-b")

    assert user_a_courses.success is True
    assert user_a_courses.courses == [
        postgres_store.SavedCourseSummary("shared-id", "Same Name")
    ]
    assert user_b_courses.success is True
    assert user_b_courses.courses == [
        postgres_store.SavedCourseSummary("other-id", "Other Course"),
        postgres_store.SavedCourseSummary("shared-id", "Same Name"),
    ]


def test_list_saved_courses_rejects_invalid_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        postgres_store,
        "_connect",
        lambda: pytest.fail("must not connect for an invalid user ID"),
    )

    result = postgres_store.list_saved_courses("  ")

    assert result.success is False
    assert result.courses == []
    assert "invalid" in result.message.lower()


def test_list_saved_courses_reports_unconfigured_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(postgres_store, "load_dotenv", lambda **_: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        postgres_store.psycopg,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("must not connect"),
    )

    result = postgres_store.list_saved_courses("demo-user")

    assert result.success is False
    assert result.courses == []
    assert "configuration" in result.message.lower()


def test_list_saved_courses_hides_connection_error_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        postgres_store,
        "_connect",
        lambda: (_ for _ in ()).throw(
            postgres_store.psycopg.Error("password=secret connection string")
        ),
    )

    result = postgres_store.list_saved_courses("demo-user")

    assert result.success is False
    assert result.courses == []
    assert "could not list saved courses" in result.message.lower()
    assert "secret" not in result.message
    assert "connection string" not in result.message


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


def test_save_course_appends_new_questions_and_topics_idempotently(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    connection = FakeConnection()
    use_connection(monkeypatch, connection)
    added_topic = Topic(id="topic-b", name="Topic B", summary="New summary")
    added_question = Question(
        id="q-new",
        topic_id=added_topic.id,
        question="New question",
        options=["A", "B", "C", "D"],
        correct_index=1,
        explanation="New explanation",
    )
    incoming_package = StudyPackage(
        course_id=package.course_id,
        course_name=package.course_name,
        topics=[added_topic],
        relationships=[],
        questions=[added_question],
    )

    assert postgres_store.save_course("demo-user", package).success is True
    first_save = postgres_store.save_course("demo-user", incoming_package)
    second_save = postgres_store.save_course("demo-user", incoming_package)
    loaded = postgres_store.load_course("demo-user", package.course_id)

    assert first_save.success is True
    assert second_save.success is True
    assert loaded.success is True
    assert loaded.package is not None
    assert [topic.id for topic in loaded.package.topics] == ["topic-a", "topic-b"]
    assert [question.id for question in loaded.package.questions] == [
        "q-0",
        "q-1",
        "q-2",
        "q-new",
    ]


@pytest.mark.parametrize("changed_entity", ["question", "topic"])
def test_save_course_rejects_changed_existing_ids_without_modifying_data(
    monkeypatch: pytest.MonkeyPatch,
    package: StudyPackage,
    changed_entity: str,
) -> None:
    connection = FakeConnection()
    use_connection(monkeypatch, connection)
    assert postgres_store.save_course("demo-user", package).success is True
    original_data = deepcopy(
        connection.course_packages[("demo-user", package.course_id)]
    )

    if changed_entity == "question":
        changed_question = package.questions[0].model_copy(
            update={"question": "Reused ID with changed content"}
        )
        incoming_package = package.model_copy(
            update={
                "questions": [changed_question, *package.questions[1:]],
            }
        )
        expected_message = "question ID"
    else:
        changed_topic = package.topics[0].model_copy(
            update={"summary": "Reused ID with changed content"}
        )
        incoming_package = package.model_copy(update={"topics": [changed_topic]})
        expected_message = "topic ID"

    result = postgres_store.save_course("demo-user", incoming_package)

    assert result.success is False
    assert expected_message in result.message
    assert connection.course_packages[("demo-user", package.course_id)] == original_data
    assert connection.rollback_count == 1


def test_saving_appended_course_keeps_existing_exam_history(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    connection = FakeConnection()
    use_connection(monkeypatch, connection)
    session = ExamSession(
        session_id="historical-session",
        mode="mock",
        question_ids=["q-0"],
    )
    attempt = AttemptResult(
        session_id=session.session_id,
        question_id="q-0",
        selected_index=0,
        is_correct=True,
    )
    appended_package = package.model_copy(
        update={"questions": [package.questions[0]]}
    )

    assert postgres_store.save_course("demo-user", package).success is True
    assert postgres_store.save_exam_result(
        "demo-user", package.course_id, session, [attempt]
    ).success is True
    assert postgres_store.save_course("demo-user", appended_package).success is True

    history = postgres_store.load_course_history("demo-user", package.course_id)

    assert history.success is True
    assert history.package is not None
    assert [question.id for question in history.package.questions] == [
        "q-0",
        "q-1",
        "q-2",
    ]
    assert history.sessions == [session]
    assert history.attempts == [attempt]
    assert history.topic_stats[0].correct == 1
    assert history.topic_stats[0].attempted == 1
    assert history.topic_stats[0].accuracy == 100
    assert history.mastery_statuses[("topic-a", "mock")] == "insufficient_evidence"


def test_write_entry_points_take_same_course_lock_before_database_access(
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

    assert postgres_store.save_course("demo-user", package).success is True
    save_course_calls = list(connection.execute_calls)
    connection.execute_calls.clear()
    assert postgres_store.save_exam_result(
        "demo-user",
        package.course_id,
        session,
        make_attempts(session.session_id, session.question_ids),
    ).success is True
    save_exam_calls = list(connection.execute_calls)

    lock_calls = [save_course_calls[0], save_exam_calls[0]]
    normalized_lock_queries = [
        " ".join(query.lower().split()) for query, _ in lock_calls
    ]
    assert all("pg_advisory_xact_lock" in query for query in normalized_lock_queries)
    assert normalized_lock_queries[0] == normalized_lock_queries[1]
    assert [parameters for _, parameters in lock_calls] == [
        ("demo-user", package.course_id),
        ("demo-user", package.course_id),
    ]
    assert "select package_json" in " ".join(save_course_calls[1][0].lower().split())
    assert "select package_json" in " ".join(save_exam_calls[2][0].lower().split())
    assert connection.enter_count == 2
    assert connection.commit_count == 2


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
    assert not any(
        "delete from attempt_results" in sql.lower()
        for sql, _ in connection.execute_calls
    )
    assert len(connection.executemany_calls) == 1


def test_resaving_same_session_rejects_changed_answer_snapshot(
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
    assert second.success is False
    assert "different content" in second.message
    assert connection.attempt_snapshots[("demo-user", "session-1")] == [
        ("q-0", 0, True), ("q-1", 0, True),
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
    assert "repeatable read" in connection.execute_calls[0][0].lower()


def test_course_history_rejects_sessions_referencing_missing_questions(
    monkeypatch: pytest.MonkeyPatch, package: StudyPackage
) -> None:
    connection = FakeConnection()
    connection.course_packages[("demo-user", package.course_id)] = (
        package.model_dump(mode="json")
    )
    connection.sessions[("demo-user", "broken-session")] = (
        package.course_id,
        "mock",
        ["missing-question"],
    )
    use_connection(monkeypatch, connection)

    result = postgres_store.load_course_history("demo-user", package.course_id)

    assert result.success is False
    assert "references questions missing" in result.message
    assert result.sessions == []
    assert result.attempts == []
    assert "repeatable read" in connection.execute_calls[0][0].lower()


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
def test_initialize_schema_skips_empty_sql_fragments(
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:
    class RecordingConnection:
        def __init__(self) -> None:
            self.execute_calls: list[bytes] = []

        def __enter__(self) -> RecordingConnection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, query: bytes) -> None:
            self.execute_calls.append(query)

    connection = RecordingConnection()
    schema_bytes = b";  \n; CREATE TABLE test_schema (id INTEGER); ;"

    monkeypatch.setattr(
        postgres_store.Path,
        "read_bytes",
        lambda _path: schema_bytes,
    )
    monkeypatch.setattr(
        postgres_store,
        "_connect",
        lambda: connection,
    )

    result = postgres_store.initialize_schema()

    assert result.success is True
    assert connection.execute_calls == [
        b" CREATE TABLE test_schema (id INTEGER)"
    ]

def test_atomic_course_history_failure_rolls_back_new_course(monkeypatch, package):
    connection = FakeConnection()
    use_connection(monkeypatch, connection)
    connection.fail_on_executemany = True
    session = ExamSession(session_id="new", mode="mock", question_ids=["q-0"])
    result = postgres_store.save_course_history("user", package, [(session, make_attempts("new", ["q-0"]))])
    assert not result.success
    assert connection.course_packages == {} and connection.sessions == {}
    assert connection.rollback_count == 1 and connection.commit_count == 0


def test_identical_retry_does_not_rewrite_saved_answers(monkeypatch, package):
    connection = FakeConnection()
    use_connection(monkeypatch, connection)
    session = ExamSession(session_id="retry", mode="mock", question_ids=["q-0"])
    results = [(session, make_attempts("retry", ["q-0"]))]
    assert postgres_store.save_course_history("user", package, results).success
    writes = len(connection.executemany_calls)
    assert postgres_store.save_course_history("user", package, results).success
    assert len(connection.executemany_calls) == writes
    assert len(connection.sessions) == 1


def test_invalid_grading_cannot_be_saved(monkeypatch, package):
    connection = FakeConnection()
    use_connection(monkeypatch, connection)
    session = ExamSession(session_id="bad", mode="mock", question_ids=["q-0"])
    result = postgres_store.save_course_history("user", package, [(session, make_attempts("bad", ["q-0"], selected_index=1, is_correct=True))])
    assert not result.success and "grading" in result.message
    assert connection.course_packages == {}


def test_incomplete_stored_history_is_not_restored(monkeypatch, package):
    connection = FakeConnection()
    use_connection(monkeypatch, connection)
    session = ExamSession(session_id="incomplete", mode="mock", question_ids=["q-0", "q-1"])
    assert postgres_store.save_course_history("user", package, [(session, make_attempts("incomplete", session.question_ids))]).success
    connection.attempt_snapshots[("user", "incomplete")].pop()
    result = postgres_store.load_course_history("user", package.course_id)
    assert not result.success and result.package is None


def test_stored_incorrect_grading_is_not_restored(monkeypatch, package):
    connection = FakeConnection()
    use_connection(monkeypatch, connection)
    session = ExamSession(session_id="badgrade", mode="mock", question_ids=["q-0"])
    assert postgres_store.save_course_history("user", package, [(session, make_attempts("badgrade", session.question_ids))]).success
    connection.attempt_snapshots[("user", "badgrade")] = [("q-0", 1, True)]
    result = postgres_store.load_course_history("user", package.course_id)
    assert not result.success and "grading" in result.message


def test_corrupt_stored_course_identity_cannot_be_saved_or_restored(monkeypatch, package):
    connection = FakeConnection()
    use_connection(monkeypatch, connection)
    assert postgres_store.save_course("user", package).success
    connection.course_packages[("user", package.course_id)]["course_id"] = "wrong-course"
    assert not postgres_store.load_course("user", package.course_id).success
    assert not postgres_store.load_course_history("user", package.course_id).success
    assert not postgres_store.save_course("user", package).success
