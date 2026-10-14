from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence

import psycopg
from dotenv import load_dotenv
from pydantic import ValidationError
from psycopg.types.json import Jsonb

from models.schemas import AttemptResult, ExamSession, StudyPackage, TopicStats
from services.mastery_engine import calculate_topic_stats, get_mastery_status


@dataclass(frozen=True)
class PersistenceResult:
    success: bool
    message: str


@dataclass(frozen=True)
class LoadCourseResult:
    success: bool
    package: StudyPackage | None
    message: str


@dataclass(frozen=True)
class SavedCourseSummary:
    course_id: str
    course_name: str


@dataclass(frozen=True)
class SavedCoursesResult:
    success: bool
    courses: list[SavedCourseSummary]
    message: str


@dataclass(frozen=True)
class CourseHistoryResult:
    success: bool
    package: StudyPackage | None
    sessions: list[ExamSession]
    attempts: list[AttemptResult]
    topic_stats: list[TopicStats]
    mastery_statuses: dict[tuple[str, str], str]
    message: str


class _PersistenceError(Exception):
    """An error with a safe message that contains no connection details."""


def _connect() -> psycopg.Connection:
    load_dotenv(
        dotenv_path=Path(__file__).resolve().parents[1] / ".env",
        override=False,
    )

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise _PersistenceError(
            "Database is not configured; progress was not saved."
        )

    sslmode = os.getenv("DATABASE_SSLMODE", "require").strip().lower()
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        raise _PersistenceError(
            "Database TLS must use require, verify-ca, or verify-full."
        )

    return psycopg.connect(
        database_url,
        sslmode=sslmode,
        connect_timeout=5,
        prepare_threshold=None,
    )


def _validate_demo_user_id(demo_user_id: str) -> str:
    if not isinstance(demo_user_id, str):
        raise ValueError("demo_user_id must be text.")

    value = demo_user_id.strip()
    if not value or len(value) > 100:
        raise ValueError("demo_user_id must contain 1 to 100 characters.")

    return value


def _database_failure(action: str) -> PersistenceResult:
    return PersistenceResult(
        success=False,
        message=(
            f"Database could not {action}. Check the database configuration "
            "and connection; no successful operation was reported."
        ),
    )


def _lock_course(
    connection: psycopg.Connection,
    user_id: str,
    course_id: str,
) -> None:
    connection.execute(
        """
        SELECT pg_advisory_xact_lock(
            hashtextextended(jsonb_build_array(%s::text, %s::text)::text, 0)
        )
        """,
        (user_id, course_id),
    )


def _merge_course_packages(
    existing: StudyPackage | None,
    incoming: StudyPackage,
) -> StudyPackage:
    if existing is None:
        return incoming

    topics = list(existing.topics)
    topics_by_id = {topic.id: topic for topic in topics}
    for topic in incoming.topics:
        existing_topic = topics_by_id.get(topic.id)
        if existing_topic is not None:
            if existing_topic != topic:
                raise _PersistenceError(
                    "A saved topic ID was reused with different content."
                )
            continue
        topics.append(topic)
        topics_by_id[topic.id] = topic

    questions = list(existing.questions)
    questions_by_id = {question.id: question for question in questions}
    for question in incoming.questions:
        existing_question = questions_by_id.get(question.id)
        if existing_question is not None:
            if existing_question != question:
                raise _PersistenceError(
                    "A saved question ID was reused with different content."
                )
            continue
        questions.append(question)
        questions_by_id[question.id] = question

    merged_data = incoming.model_dump(mode="json")
    merged_data["topics"] = [topic.model_dump(mode="json") for topic in topics]
    merged_data["questions"] = [
        question.model_dump(mode="json") for question in questions
    ]
    metadata = {**existing.learning_state, **incoming.learning_state}
    reviews = {**existing.learning_state.get("question_reviews", {}), **incoming.learning_state.get("question_reviews", {})}
    if reviews:
        metadata["question_reviews"] = reviews
    merged_data["learning_state"] = metadata
    order = list(existing.learning_state.get("session_order", []))
    for session_id in incoming.learning_state.get("session_order", []):
        if session_id not in order:
            order.append(session_id)
    if order:
        merged_data.setdefault("learning_state", {})["session_order"] = order
    return StudyPackage.model_validate(merged_data)


def initialize_schema() -> PersistenceResult:
    """Create the PostgreSQL tables and index from db/schema.sql."""
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

    try:
        schema_bytes = schema_path.read_bytes()
        with _connect() as connection:
            for statement in schema_bytes.split(b";"):
                if statement.strip():
                    connection.execute(statement)
    except _PersistenceError as exc:
        return PersistenceResult(False, str(exc))
    except (OSError, psycopg.Error):
        return _database_failure("initialize the schema")

    return PersistenceResult(True, "Database schema is ready.")


def _save_course_in_transaction(
    connection: psycopg.Connection, user_id: str, validated_package: StudyPackage,
) -> StudyPackage:
    _lock_course(
        connection, user_id, validated_package.course_id
    )
    existing_row = connection.execute(
        """
        SELECT package_json
        FROM courses
        WHERE demo_user_id = %s AND course_id = %s
        FOR UPDATE
        """,
        (user_id, validated_package.course_id),
    ).fetchone()
    existing_package = None
    if existing_row is not None:
        package_data = existing_row[0]
        if isinstance(package_data, str):
            package_data = json.loads(package_data)
        existing_package = StudyPackage.model_validate(package_data)
        if existing_package.course_id != validated_package.course_id:
            raise _PersistenceError("Stored course identity does not match the requested course.")
    package_to_save = _merge_course_packages(
        existing_package, validated_package
    )

    connection.execute(
        """
        INSERT INTO demo_users (demo_user_id)
        VALUES (%s)
        ON CONFLICT (demo_user_id) DO NOTHING
        """,
        (user_id,),
    )
    connection.execute(
        """
        INSERT INTO courses (
            demo_user_id, course_id, course_name, package_json
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (demo_user_id, course_id)
        DO UPDATE SET
            course_name = EXCLUDED.course_name,
            package_json = EXCLUDED.package_json,
            updated_at = NOW()
        """,
        (
            user_id,
            package_to_save.course_id,
            package_to_save.course_name,
            Jsonb(package_to_save.model_dump(mode="json")),
        ),
    )
    return package_to_save


def _validated_exam(
    session: ExamSession, attempts: Sequence[AttemptResult],
) -> tuple[ExamSession, list[AttemptResult]]:
    validated_session = ExamSession.model_validate(
        session.model_dump(mode="json")
    )
    validated_attempts = [
        AttemptResult.model_validate(attempt.model_dump(mode="json"))
        for attempt in attempts
    ]

    question_ids = validated_session.question_ids
    attempt_question_ids = [
        attempt.question_id for attempt in validated_attempts
    ]

    if not question_ids or len(question_ids) != len(set(question_ids)):
        raise ValueError("Session question IDs must be non-empty and unique.")

    if (
        len(attempt_question_ids) != len(set(attempt_question_ids))
        or set(attempt_question_ids) != set(question_ids)
    ):
        raise ValueError(
            "Attempts must contain exactly one result for every session question."
        )

    for attempt in validated_attempts:
        if attempt.session_id != validated_session.session_id:
            raise ValueError("Attempt session ID does not match the session.")
        if (
            attempt.selected_index is not None
            and (
                isinstance(attempt.selected_index, bool)
                or not isinstance(attempt.selected_index, int)
                or not 0 <= attempt.selected_index <= 3
            )
        ):
            raise ValueError("Selected answer index must be 0–3 or None.")
        if attempt.selected_index is None and attempt.is_correct:
            raise ValueError("An unanswered question cannot be correct.")

    return validated_session, validated_attempts


def _validate_grades(
    package: StudyPackage, session: ExamSession, attempts: Sequence[AttemptResult],
) -> None:
    questions = {question.id: question for question in package.questions}
    for attempt in attempts:
        question = questions.get(attempt.question_id)
        if question is None:
            raise _PersistenceError("Exam contains a question missing from the saved course.")
        correct = attempt.selected_index is not None and attempt.selected_index == question.correct_index
        if attempt.is_correct != correct:
            raise _PersistenceError("Exam grading does not match the saved question answers; nothing was saved or restored.")


def _save_exam_in_transaction(
    connection: psycopg.Connection, user_id: str, course_id: str,
    validated_session: ExamSession, validated_attempts: Sequence[AttemptResult],
) -> None:
    question_ids = validated_session.question_ids
    _lock_course(connection, user_id, course_id)
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(jsonb_build_array('exam-session', %s::text, %s::text)::text, 0))",
        (user_id, validated_session.session_id),
    )
    course_row = connection.execute(
        """
        SELECT package_json
        FROM courses
        WHERE demo_user_id = %s AND course_id = %s
        """,
        (user_id, course_id),
    ).fetchone()

    if course_row is None:
        raise _PersistenceError(
            "Save the course before saving its exam result."
        )

    package_data = course_row[0]
    if isinstance(package_data, str):
        package_data = json.loads(package_data)
    package = StudyPackage.model_validate(package_data)
    if package.course_id != course_id:
        raise _PersistenceError("Stored course identity does not match the requested course.")
    unknown_question_ids = set(question_ids) - {
        question.id for question in package.questions
    }
    if unknown_question_ids:
        raise _PersistenceError(
            "Exam session contains question IDs not found in the course."
        )

    _validate_grades(package, validated_session, validated_attempts)

    existing_session = connection.execute(
        """
        SELECT course_id
        FROM exam_sessions
        WHERE demo_user_id = %s AND session_id = %s
        FOR UPDATE
        """,
        (user_id, validated_session.session_id),
    ).fetchone()

    if existing_session is not None and existing_session[0] != course_id:
        raise _PersistenceError(
            "This session ID already belongs to another course."
        )

    if existing_session is not None:
        saved_session = connection.execute(
            "SELECT mode, question_ids FROM exam_sessions WHERE demo_user_id = %s AND session_id = %s",
            (user_id, validated_session.session_id),
        ).fetchone()
        saved_answers = connection.execute(
            "SELECT question_id, selected_index, is_correct FROM attempt_results WHERE demo_user_id = %s AND session_id = %s ORDER BY question_id",
            (user_id, validated_session.session_id),
        ).fetchall()
        incoming_answers = sorted((a.question_id, a.selected_index, a.is_correct) for a in validated_attempts)
        if saved_session != (validated_session.mode, question_ids) or sorted(saved_answers) != incoming_answers:
            raise _PersistenceError("This practice session was already saved with different content; start a new practice session instead.")
        return

    connection.execute(
        """
        INSERT INTO exam_sessions (
            demo_user_id, session_id, course_id, mode, question_ids
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (demo_user_id, session_id) DO NOTHING
        """,
        (
            user_id,
            validated_session.session_id,
            course_id,
            validated_session.mode,
            Jsonb(question_ids),
        ),
    )

    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO attempt_results (
                demo_user_id, session_id, question_id,
                selected_index, is_correct
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (
                    user_id,
                    attempt.session_id,
                    attempt.question_id,
                    attempt.selected_index,
                    attempt.is_correct,
                )
                for attempt in validated_attempts
            ],
        )



def save_course_history(
    demo_user_id: str, package: StudyPackage,
    results: Sequence[tuple[ExamSession, Sequence[AttemptResult]]],
) -> PersistenceResult:
    """Commit a course and all supplied graded sessions together, or none.

    Identical retries are accepted; a saved session ID cannot change its
    course, mode, question order, answers or grades. New question versions
    must use new IDs, enforced by the append-only package merge.
    """
    try:
        user_id = _validate_demo_user_id(demo_user_id)
        validated_package = StudyPackage.model_validate(package.model_dump(mode="json"))
        validated_results = [_validated_exam(session, attempts) for session, attempts in results]
        ids = [session.session_id for session, _ in validated_results]
        order = list(validated_package.learning_state.get("session_order", []))
        for session_id in ids:
            if session_id not in order:
                order.append(session_id)
        if order:
            validated_package.learning_state["session_order"] = order
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate sessions in one save.")
        with _connect() as connection:
            _save_course_in_transaction(connection, user_id, validated_package)
            for session, attempts in sorted(validated_results, key=lambda item: item[0].session_id):
                _save_exam_in_transaction(connection, user_id, validated_package.course_id, session, attempts)
    except _PersistenceError as exc:
        return PersistenceResult(False, str(exc))
    except (ValueError, TypeError, ValidationError):
        return PersistenceResult(False, "Course or exam data is invalid; nothing was saved.")
    except psycopg.Error:
        return _database_failure("save the course and practice history")
    return PersistenceResult(True, "Course and practice history saved to your account.")


def save_course(
    demo_user_id: str,
    package: StudyPackage,
) -> PersistenceResult:
    """Merge one course package without changing existing question or topic IDs."""
    try:
        user_id = _validate_demo_user_id(demo_user_id)
        validated_package = StudyPackage.model_validate(
            package.model_dump(mode="json")
        )

        with _connect() as connection:
            _save_course_in_transaction(connection, user_id, validated_package)
    except _PersistenceError as exc:
        return PersistenceResult(False, str(exc))
    except (ValueError, TypeError, ValidationError):
        return PersistenceResult(
            False, "Course data or demo user label is invalid; nothing was saved."
        )
    except psycopg.Error:
        return _database_failure("save the course")

    return PersistenceResult(True, "Course saved.")


def load_course(
    demo_user_id: str,
    course_id: str,
) -> LoadCourseResult:
    """Load one course package. A missing course is a successful empty result."""
    try:
        user_id = _validate_demo_user_id(demo_user_id)
        with _connect() as connection:
            row = connection.execute(
                """
                SELECT package_json
                FROM courses
                WHERE demo_user_id = %s AND course_id = %s
                """,
                (user_id, course_id),
            ).fetchone()

        if row is None:
            return LoadCourseResult(True, None, "Course was not found.")

        package_data = row[0]
        if isinstance(package_data, str):
            package_data = json.loads(package_data)

        package = StudyPackage.model_validate(package_data)
        if package.course_id != course_id:
            raise _PersistenceError("Stored course identity does not match the requested course.")
        return LoadCourseResult(True, package, "Course restored.")

    except _PersistenceError as exc:
        return LoadCourseResult(False, None, str(exc))
    except (ValueError, TypeError, ValidationError, json.JSONDecodeError):
        return LoadCourseResult(
            False, None, "Stored course data failed validation."
        )
    except psycopg.Error:
        return LoadCourseResult(
            False,
            None,
            "Database could not load the course. Check configuration and connection.",
        )


def list_saved_courses(user_id: str) -> SavedCoursesResult:
    """List courses for a user ID supplied by the caller's trusted auth context."""
    try:
        validated_user_id = _validate_demo_user_id(user_id)
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT course_id, course_name
                FROM courses
                WHERE demo_user_id = %s
                ORDER BY course_id
                """,
                (validated_user_id,),
            ).fetchall()

        courses = [
            SavedCourseSummary(course_id=course_id, course_name=course_name)
            for course_id, course_name in rows
        ]
        return SavedCoursesResult(True, courses, "Saved courses listed.")

    except _PersistenceError:
        return SavedCoursesResult(
            False,
            [],
            "Database configuration is invalid; saved courses could not be listed.",
        )
    except (ValueError, TypeError):
        return SavedCoursesResult(
            False,
            [],
            "User identifier is invalid; saved courses could not be listed.",
        )
    except psycopg.Error:
        return SavedCoursesResult(
            False,
            [],
            "Database could not list saved courses. Check the database configuration and connection.",
        )


def save_exam_result(
    demo_user_id: str,
    course_id: str,
    session: ExamSession,
    attempts: Sequence[AttemptResult],
) -> PersistenceResult:
    """
    Save one complete exam result as a transaction.

    Re-saving an identical session succeeds without changing its snapshot.
    Conflicting reuse of the session ID is rejected.
    Different sessions remain separate.
    """
    try:
        user_id = _validate_demo_user_id(demo_user_id)
        validated_session, validated_attempts = _validated_exam(session, attempts)
        with _connect() as connection:
            _save_exam_in_transaction(connection, user_id, course_id, validated_session, validated_attempts)

    except _PersistenceError as exc:
        return PersistenceResult(False, str(exc))
    except (ValueError, TypeError, ValidationError):
        return PersistenceResult(
            False, "Exam result is invalid; nothing was saved."
        )
    except psycopg.Error:
        # The connection context rolls the whole transaction back on failure.
        return _database_failure("save the exam result")

    return PersistenceResult(True, "Exam session and answers saved.")


def load_course_history(
    demo_user_id: str,
    course_id: str,
) -> CourseHistoryResult:
    """Restore and validate a course, its sessions, attempts, and mastery."""
    try:
        user_id = _validate_demo_user_id(demo_user_id)

        with _connect() as connection:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
            )
            course_row = connection.execute(
                """
                SELECT package_json
                FROM courses
                WHERE demo_user_id = %s AND course_id = %s
                """,
                (user_id, course_id),
            ).fetchone()

            if course_row is None:
                return CourseHistoryResult(
                    True, None, [], [], [], {}, "Course was not found."
                )

            package_data = course_row[0]
            if isinstance(package_data, str):
                package_data = json.loads(package_data)
            package = StudyPackage.model_validate(package_data)
            if package.course_id != course_id:
                raise _PersistenceError("Stored course identity does not match the requested course.")

            session_rows = connection.execute(
                """
                SELECT session_id, mode, question_ids
                FROM exam_sessions
                WHERE demo_user_id = %s AND course_id = %s
                ORDER BY created_at, session_id
                """,
                (user_id, course_id),
            ).fetchall()

            sessions = []
            for session_id, mode, question_ids in session_rows:
                if isinstance(question_ids, str):
                    question_ids = json.loads(question_ids)
                sessions.append(
                    ExamSession.model_validate(
                        {
                            "session_id": session_id,
                            "mode": mode,
                            "question_ids": question_ids,
                        }
                    )
                )

            saved_order = {sid: index for index, sid in enumerate(package.learning_state.get("session_order", []))}
            fallback_order = {session.session_id: index for index, session in enumerate(sessions)}
            sessions.sort(key=lambda session: (0, saved_order[session.session_id]) if session.session_id in saved_order else (1, fallback_order[session.session_id]))

            question_ids = {question.id for question in package.questions}
            if any(
                not set(session.question_ids).issubset(question_ids)
                for session in sessions
            ):
                raise _PersistenceError(
                    "Stored exam session references questions missing from the course."
                )

            attempt_rows = connection.execute(
                """
                SELECT a.session_id, a.question_id, a.selected_index, a.is_correct
                FROM attempt_results AS a
                JOIN exam_sessions AS s
                  ON s.demo_user_id = a.demo_user_id
                 AND s.session_id = a.session_id
                WHERE s.demo_user_id = %s AND s.course_id = %s
                ORDER BY s.created_at, a.created_at, a.question_id
                """,
                (user_id, course_id),
            ).fetchall()

            attempts = [
                AttemptResult.model_validate(
                    {
                        "session_id": session_id,
                        "question_id": question_id,
                        "selected_index": selected_index,
                        "is_correct": is_correct,
                    }
                )
                for session_id, question_id, selected_index, is_correct
                in attempt_rows
            ]

        attempts_by_session = {session.session_id: [] for session in sessions}
        for attempt in attempts:
            if attempt.session_id not in attempts_by_session:
                raise ValueError("Unmatched stored attempt.")
            attempts_by_session[attempt.session_id].append(attempt)
        for session in sessions:
            validated_session, validated_attempts = _validated_exam(session, attempts_by_session[session.session_id])
            _validate_grades(package, validated_session, validated_attempts)

        # Existing Mastery Engine validates references and recalculates results.
        topic_stats = calculate_topic_stats(
            attempts, sessions, package.questions
        )
        mastery_statuses = {
            (stats.topic_id, stats.mode): get_mastery_status(stats)
            for stats in topic_stats
        }

        return CourseHistoryResult(
            True,
            package,
            sessions,
            attempts,
            topic_stats,
            mastery_statuses,
            "Course history restored and mastery recalculated.",
        )

    except _PersistenceError as exc:
        return CourseHistoryResult(False, None, [], [], [], {}, str(exc))
    except (ValueError, TypeError, ValidationError, json.JSONDecodeError):
        return CourseHistoryResult(
            False,
            None,
            [],
            [],
            [],
            {},
            "Stored course or exam data failed validation.",
        )
    except psycopg.Error:
        return CourseHistoryResult(
            False,
            None,
            [],
            [],
            [],
            {},
            "Database could not restore course history. Check configuration and connection.",
        )
