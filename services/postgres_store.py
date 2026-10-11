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
    load_dotenv(override=False)

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


def save_course(
    demo_user_id: str,
    package: StudyPackage,
) -> PersistenceResult:
    """Save or replace one course package for a demo user."""
    try:
        user_id = _validate_demo_user_id(demo_user_id)
        validated_package = StudyPackage.model_validate(
            package.model_dump(mode="json")
        )

        with _connect() as connection:
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
                    validated_package.course_id,
                    validated_package.course_name,
                    Jsonb(validated_package.model_dump(mode="json")),
                ),
            )
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

    Re-saving the same session replaces its full answer snapshot.
    Different sessions remain separate.
    """
    try:
        user_id = _validate_demo_user_id(demo_user_id)
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

        with _connect() as connection:
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
            unknown_question_ids = set(question_ids) - {
                question.id for question in package.questions
            }
            if unknown_question_ids:
                raise _PersistenceError(
                    "Exam session contains question IDs not found in the course."
                )

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

            connection.execute(
                """
                INSERT INTO exam_sessions (
                    demo_user_id, session_id, course_id, mode, question_ids
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (demo_user_id, session_id)
                DO UPDATE SET
                    mode = EXCLUDED.mode,
                    question_ids = EXCLUDED.question_ids
                """,
                (
                    user_id,
                    validated_session.session_id,
                    course_id,
                    validated_session.mode,
                    Jsonb(question_ids),
                ),
            )

            # Full snapshot replacement: remove this session's previous answers.
            connection.execute(
                """
                DELETE FROM attempt_results
                WHERE demo_user_id = %s AND session_id = %s
                """,
                (user_id, validated_session.session_id),
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
