"""Learning Radar: students flag demo-course topics where they are stuck.

Counts are anonymous aggregates over the ``radar_flags`` table (migration 003),
shown next to static sample data from ``data/radar_sample.json``. Nothing here
raises to the caller: database problems become a failed PersistenceResult on
writes and an offline radar (``live=False``) on reads.

This module must not import streamlit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import psycopg

from services import postgres_store
from services.postgres_store import PersistenceResult

RADAR_COURSE_IDS = frozenset({"econ101", "calculus-i-demo", "python-basics-demo"})
MIN_VISIBLE_COUNT = 3
REASON_LABELS = {
    "concept": "Concept unclear",
    "calculation": "Calculation errors",
    "wording": "Can't understand the question",
    "start": "Don't know where to start",
}

DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"
SAMPLE_PATH = DATA_DIRECTORY / "radar_sample.json"

# The demo data file names do not match the course IDs.
_COURSE_FILES = {
    "econ101": "sample_course.json",
    "calculus-i-demo": "calculus_i_demo.json",
    "python-basics-demo": "demo_python_basics.json",
}

_UPSERT_FLAG_SQL = """
    INSERT INTO radar_flags (demo_user_id, course_id, topic_id, reason)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (demo_user_id, course_id, topic_id)
    DO UPDATE SET reason = EXCLUDED.reason
"""

_DELETE_FLAG_SQL = """
    DELETE FROM radar_flags
    WHERE demo_user_id = %s AND course_id = %s AND topic_id = %s
"""

_USER_FLAGS_SQL = """
    SELECT topic_id, reason
    FROM radar_flags
    WHERE demo_user_id = %s AND course_id = %s
"""

_COURSE_COUNTS_SQL = """
    SELECT topic_id, reason, COUNT(*)
    FROM radar_flags
    WHERE course_id = %s
    GROUP BY topic_id, reason
"""

# Failures that mean "the database cannot be used right now".
_READ_FAILURES = (postgres_store._PersistenceError, OSError, psycopg.Error)


@dataclass(frozen=True)
class TopicRadar:
    topic_id: str
    real_count: int  # flags from real accounts
    sample_count: int  # count taken from the sample data
    reasons: dict[str, int]  # real plus sample, by reason code
    display_count: int | None  # None: show only "Some students flagged this"


@dataclass(frozen=True)
class CourseRadar:
    topics: dict[str, TopicRadar]  # only topics with at least one flag
    live: bool  # False: the database could not be read; sample data only
    has_sample: bool


def radar_enabled(course_id: str) -> bool:
    """Return True when Learning Radar is available for this course."""
    return isinstance(course_id, str) and course_id in RADAR_COURSE_IDS


@lru_cache(maxsize=None)
def _load_course_topic_ids(course_id: str) -> tuple[str, ...]:
    """Read a demo course's topic IDs in file order (exceptions are not cached)."""
    path = DATA_DIRECTORY / _COURSE_FILES[course_id]
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("course_id") != course_id:
        raise ValueError("Demo course file does not match its course ID.")
    return tuple(topic["id"] for topic in data["topics"])


def _course_topic_ids(course_id: str) -> tuple[str, ...]:
    """Topic IDs of a demo course; empty when the course or its file is unusable."""
    if not radar_enabled(course_id):
        return ()
    try:
        return _load_course_topic_ids(course_id)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return ()


def _normalized_user_id(user_id: str) -> str | None:
    """Apply the store's demo user rule (1 to 100 characters after stripping)."""
    try:
        return postgres_store._validate_demo_user_id(user_id)
    except ValueError:
        return None


def _argument_error(
    user_id: str | None, course_id: str, topic_id: str
) -> str | None:
    """Return a readable reason why a flag request is invalid, or None."""
    if user_id is None:
        return "A signed-in account is required to flag a topic."
    if not radar_enabled(course_id):
        return "Learning Radar is only available for the built-in demo courses."
    if not isinstance(topic_id, str) or topic_id not in _course_topic_ids(course_id):
        return "This topic is not part of the selected demo course."
    return None


def set_flag(
    user_id: str, course_id: str, topic_id: str, reason: str | None = None
) -> PersistenceResult:
    """Flag a topic for this user; flagging it again only replaces the reason."""
    normalized_user_id = _normalized_user_id(user_id)
    error = _argument_error(normalized_user_id, course_id, topic_id)
    if error is None and not (
        reason is None or (isinstance(reason, str) and reason in REASON_LABELS)
    ):
        error = "Choose one of the listed reasons, or no reason."
    if error is not None:
        return PersistenceResult(False, error)

    try:
        with postgres_store._connect() as connection:
            connection.execute(
                _UPSERT_FLAG_SQL, (normalized_user_id, course_id, topic_id, reason)
            )
    except postgres_store._PersistenceError as exc:
        return PersistenceResult(False, str(exc))
    except psycopg.errors.UndefinedTable:
        return PersistenceResult(
            False,
            "Learning Radar is not set up in the database yet; your flag was not saved.",
        )
    except (OSError, psycopg.Error, ValueError, TypeError):
        return PersistenceResult(
            False, "The database could not save your flag; please try again later."
        )
    return PersistenceResult(True, "Flag saved.")


def clear_flag(user_id: str, course_id: str, topic_id: str) -> PersistenceResult:
    """Remove this user's flag on a topic; removing a missing flag also succeeds."""
    normalized_user_id = _normalized_user_id(user_id)
    error = _argument_error(normalized_user_id, course_id, topic_id)
    if error is not None:
        return PersistenceResult(False, error)

    try:
        with postgres_store._connect() as connection:
            connection.execute(
                _DELETE_FLAG_SQL, (normalized_user_id, course_id, topic_id)
            )
    except postgres_store._PersistenceError as exc:
        return PersistenceResult(False, str(exc))
    except psycopg.errors.UndefinedTable:
        return PersistenceResult(
            False,
            "Learning Radar is not set up in the database yet; your flag was not removed.",
        )
    except (OSError, psycopg.Error, ValueError, TypeError):
        return PersistenceResult(
            False, "The database could not remove your flag; please try again later."
        )
    return PersistenceResult(True, "Flag removed.")


def get_user_flags(user_id: str, course_id: str) -> dict[str, str | None]:
    """Map each topic this user flagged in the course to its reason; {} if unreadable."""
    normalized_user_id = _normalized_user_id(user_id)
    if normalized_user_id is None or not radar_enabled(course_id):
        return {}
    topic_ids = frozenset(_course_topic_ids(course_id))
    try:
        with postgres_store._connect() as connection:
            rows = connection.execute(
                _USER_FLAGS_SQL, (normalized_user_id, course_id)
            ).fetchall()
        return {
            topic_id: reason if reason in REASON_LABELS else None
            for topic_id, reason in rows
            if topic_id in topic_ids
        }
    except (*_READ_FAILURES, ValueError, TypeError):
        return {}


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_sample(data: object) -> dict[str, dict[str, tuple[int, dict[str, int]]]]:
    """Validate the sample structure; raise ValueError if any entry is malformed."""
    if not isinstance(data, dict):
        raise ValueError("Sample data must be an object.")
    parsed: dict[str, dict[str, tuple[int, dict[str, int]]]] = {}
    for course_id, course_topics in data.items():
        if not isinstance(course_topics, dict):
            raise ValueError("Sample course entries must be objects.")
        topics: dict[str, tuple[int, dict[str, int]]] = {}
        for topic_id, entry in course_topics.items():
            if not isinstance(entry, dict):
                raise ValueError("Sample topic entries must be objects.")
            count = entry.get("count")
            reasons = entry.get("reasons", {})
            if not _is_count(count) or not isinstance(reasons, dict):
                raise ValueError("Sample counts must be non-negative integers.")
            if any(
                code not in REASON_LABELS or not _is_count(number)
                for code, number in reasons.items()
            ):
                raise ValueError("Sample reasons must use known codes and counts.")
            if sum(reasons.values()) > count:
                raise ValueError("Sample reasons cannot exceed the topic count.")
            topics[topic_id] = (count, dict(reasons))
        parsed[course_id] = topics
    return parsed


def _load_sample() -> dict[str, dict[str, tuple[int, dict[str, int]]]]:
    """Read the sample file; a missing or malformed file means no sample data."""
    try:
        return _parse_sample(json.loads(SAMPLE_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return {}


def _real_counts(
    course_id: str, topic_ids: frozenset[str]
) -> tuple[dict[str, int], dict[str, dict[str, int]], bool]:
    """Count real flags per topic and per reason; the bool is False if unreadable."""
    counts: dict[str, int] = {}
    reasons: dict[str, dict[str, int]] = {}
    try:
        with postgres_store._connect() as connection:
            rows = connection.execute(_COURSE_COUNTS_SQL, (course_id,)).fetchall()
        for topic_id, reason, number in rows:
            if topic_id not in topic_ids:
                continue
            number = int(number)
            counts[topic_id] = counts.get(topic_id, 0) + number
            if reason in REASON_LABELS:
                by_reason = reasons.setdefault(topic_id, {})
                by_reason[reason] = by_reason.get(reason, 0) + number
    except (*_READ_FAILURES, ValueError, TypeError):
        return {}, {}, False
    return counts, reasons, True


def _display_count(real_count: int, sample_count: int) -> int | None:
    if sample_count == 0 and real_count < MIN_VISIBLE_COUNT:
        return None
    return real_count + sample_count


def get_course_radar(course_id: str) -> CourseRadar:
    """Real and sample flag counts for a demo course; never raises."""
    if not radar_enabled(course_id):
        return CourseRadar(topics={}, live=False, has_sample=False)

    topic_order = _course_topic_ids(course_id)
    topic_ids = frozenset(topic_order)
    sample = _load_sample().get(course_id, {})
    real_counts, real_reasons, live = _real_counts(course_id, topic_ids)

    topics: dict[str, TopicRadar] = {}
    for topic_id in topic_order:
        real_count = real_counts.get(topic_id, 0)
        sample_count, sample_reasons = sample.get(topic_id, (0, {}))
        if real_count + sample_count < 1:
            continue
        topic_reasons = real_reasons.get(topic_id, {})
        reasons = {
            code: topic_reasons.get(code, 0) + sample_reasons.get(code, 0)
            for code in REASON_LABELS
        }
        topics[topic_id] = TopicRadar(
            topic_id=topic_id,
            real_count=real_count,
            sample_count=sample_count,
            reasons={code: number for code, number in reasons.items() if number > 0},
            display_count=_display_count(real_count, sample_count),
        )

    return CourseRadar(
        topics=topics,
        live=live,
        has_sample=any(topic.sample_count > 0 for topic in topics.values()),
    )


def top_hard_topics(radar: CourseRadar, limit: int = 3) -> list[TopicRadar]:
    """Most-flagged topics first (real plus sample); ties keep the radar's order."""
    if limit <= 0:
        return []
    ranked = sorted(
        radar.topics.values(),
        key=lambda topic: topic.real_count + topic.sample_count,
        reverse=True,
    )
    return ranked[:limit]
