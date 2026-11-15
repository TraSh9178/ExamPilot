"""Learning Radar service tests against an in-memory fake connection.

The fake stores radar_flags rows keyed by the table's primary key and enforces
the primary key, CHECK and foreign key rules of migration 003, so an INSERT
without the ON CONFLICT ... DO UPDATE clause fails here as it would in
PostgreSQL instead of silently overwriting.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import psycopg
import pytest

from services import learning_radar as radar
from services import postgres_store

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_REASONS = {"concept", "calculation", "wording", "start"}
UPSERT_CLAUSE = (
    "on conflict (demo_user_id, course_id, topic_id) "
    "do update set reason = excluded.reason"
)
DEMO_TOPICS = {
    "econ101": ["supply_demand", "elasticity", "price_controls"],
    "calculus-i-demo": [
        "calc_limits",
        "calc_derivatives",
        "calc_derivative_applications",
        "calc_limit_laws",
        "calc_continuity",
        "calc_trig_limits",
        "calc_differentiation_rules",
        "calc_chain_rule",
        "calc_implicit_differentiation",
        "calc_related_rates",
        "calc_mean_value_theorem",
        "calc_curve_sketching",
        "calc_antiderivatives",
        "calc_definite_integrals",
        "calc_fundamental_theorem",
    ],
    "python-basics-demo": [
        "python-basics-topic-1",
        "python-basics-topic-2",
        "python-basics-topic-3",
    ],
}
COURSE = "calculus-i-demo"
TOPIC = "calc_derivatives"


def normalize(query: str) -> str:
    return " ".join(query.lower().split())


class FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]] | None = None) -> None:
        self.rows = rows or []

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)


class FakeRadarConnection:
    """In-memory radar_flags table: {(user_id, course_id, topic_id): reason}."""

    def __init__(self) -> None:
        self.users = {"alice", "bob", "carol", "dave", "erin"}
        self.flags: dict[tuple[str, str, str], str | None] = {}
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.enter_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.fail_with: Exception | None = None
        self._snapshot: dict[tuple[str, str, str], str | None] = {}

    def __enter__(self) -> FakeRadarConnection:
        self.enter_count += 1
        self._snapshot = deepcopy(self.flags)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if exc_type is None:
            self.commit_count += 1
        else:
            self.rollback_count += 1
            self.flags = self._snapshot
        return False

    def calls_starting(self, prefix: str) -> list[tuple[str, tuple[Any, ...]]]:
        return [call for call in self.execute_calls if call[0].startswith(prefix)]

    def execute(self, query: str, parameters: tuple[Any, ...] = ()) -> FakeResult:
        normalized = normalize(query)
        self.execute_calls.append((normalized, parameters))
        if self.fail_with is not None:
            raise self.fail_with

        if normalized.startswith(
            "insert into radar_flags (demo_user_id, course_id, topic_id, reason)"
        ):
            user_id, course_id, topic_id, reason = parameters
            if reason is not None and reason not in ALLOWED_REASONS:
                raise psycopg.errors.CheckViolation("radar_flags_reason_check")
            if user_id not in self.users:
                raise psycopg.errors.ForeignKeyViolation("radar_flags_demo_user_id_fkey")
            key = (user_id, course_id, topic_id)
            if key in self.flags and UPSERT_CLAUSE not in normalized:
                raise psycopg.errors.UniqueViolation("radar_flags_pkey")
            self.flags[key] = reason
            return FakeResult()

        if normalized.startswith(
            "delete from radar_flags where demo_user_id = %s "
            "and course_id = %s and topic_id = %s"
        ):
            self.flags.pop(tuple(parameters), None)
            return FakeResult()

        if normalized.startswith(
            "select topic_id, reason from radar_flags "
            "where demo_user_id = %s and course_id = %s"
        ):
            user_id, course_id = parameters
            return FakeResult(
                [
                    (topic_id, reason)
                    for (row_user, row_course, topic_id), reason in self.flags.items()
                    if row_user == user_id and row_course == course_id
                ]
            )

        if normalized.startswith(
            "select topic_id, reason, count(*) from radar_flags "
            "where course_id = %s group by topic_id, reason"
        ):
            (course_id,) = parameters
            grouped = Counter(
                (topic_id, reason)
                for (_user, row_course, topic_id), reason in self.flags.items()
                if row_course == course_id
            )
            return FakeResult(
                [(topic_id, reason, number) for (topic_id, reason), number in grouped.items()]
            )

        raise AssertionError(f"unexpected SQL: {normalized}")


@pytest.fixture
def connection(monkeypatch: pytest.MonkeyPatch) -> FakeRadarConnection:
    fake = FakeRadarConnection()
    monkeypatch.setattr(postgres_store, "_connect", lambda: fake)
    return fake


@pytest.fixture
def no_sample(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(radar, "SAMPLE_PATH", tmp_path / "missing_sample.json")


@pytest.fixture
def forbid_connect(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def forbidden() -> None:
        calls.append(1)
        pytest.fail("must not open a database connection")

    monkeypatch.setattr(postgres_store, "_connect", forbidden)
    return calls


def use_sample(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, data: object
) -> Path:
    path = tmp_path / "radar_sample.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(radar, "SAMPLE_PATH", path)
    return path


def flag_users(count: int, topic_id: str = TOPIC, course_id: str = COURSE) -> None:
    for index in range(count):
        assert radar.set_flag(f"user-{index}", course_id, topic_id).success


# --- Contract ---------------------------------------------------------------


def test_contract_constants_and_shared_result_type() -> None:
    assert radar.RADAR_COURSE_IDS == frozenset(DEMO_TOPICS)
    assert radar.MIN_VISIBLE_COUNT == 3
    assert radar.REASON_LABELS == {
        "concept": "Concept unclear",
        "calculation": "Calculation errors",
        "wording": "Can't understand the question",
        "start": "Don't know where to start",
    }
    assert radar.PersistenceResult is postgres_store.PersistenceResult


def test_radar_is_enabled_only_for_the_demo_courses() -> None:
    assert all(radar.radar_enabled(course_id) for course_id in DEMO_TOPICS)
    for course_id in ("course-1", "ECON101", "", None, ["econ101"]):
        assert radar.radar_enabled(course_id) is False


@pytest.mark.parametrize("course_id", sorted(DEMO_TOPICS))
def test_topic_ids_are_read_from_each_demo_course_file(course_id: str) -> None:
    file_name = {
        "econ101": "sample_course.json",
        "calculus-i-demo": "calculus_i_demo.json",
        "python-basics-demo": "demo_python_basics.json",
    }[course_id]
    data = json.loads((ROOT / "data" / file_name).read_text(encoding="utf-8"))

    assert radar._course_topic_ids(course_id) == tuple(
        topic["id"] for topic in data["topics"]
    )
    assert list(radar._course_topic_ids(course_id)) == DEMO_TOPICS[course_id]


def test_module_does_not_import_streamlit() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, services.learning_radar; "
            "sys.exit(1 if 'streamlit' in sys.modules else 0)",
        ],
        cwd=ROOT,
        capture_output=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")


# --- Writes -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("course_id", "topic_id"),
    [(course_id, topic_id) for course_id, topics in DEMO_TOPICS.items() for topic_id in topics],
)
def test_every_demo_topic_can_be_flagged(
    connection: FakeRadarConnection, course_id: str, topic_id: str
) -> None:
    result = radar.set_flag("alice", course_id, topic_id, "start")

    assert result.success is True
    assert connection.flags == {("alice", course_id, topic_id): "start"}


def test_repeated_flag_counts_once_and_updates_the_reason(
    connection: FakeRadarConnection, no_sample: None
) -> None:
    first = radar.set_flag("alice", COURSE, TOPIC, "concept")
    second = radar.set_flag("alice", COURSE, TOPIC, "wording")

    assert first.success is True and second.success is True
    assert connection.flags == {("alice", COURSE, TOPIC): "wording"}
    inserts = connection.calls_starting("insert into radar_flags")
    assert len(inserts) == 2
    assert all(UPSERT_CLAUSE in query for query, _ in inserts)
    assert [parameters for _, parameters in inserts] == [
        ("alice", COURSE, TOPIC, "concept"),
        ("alice", COURSE, TOPIC, "wording"),
    ]
    assert connection.enter_count == 2 and connection.commit_count == 2

    topic = radar.get_course_radar(COURSE).topics[TOPIC]
    assert topic.real_count == 1
    assert topic.reasons == {"wording": 1}
    assert radar.get_user_flags("alice", COURSE) == {TOPIC: "wording"}


def test_flag_without_reason_counts_but_adds_no_reason(
    connection: FakeRadarConnection, no_sample: None
) -> None:
    assert radar.set_flag("alice", COURSE, TOPIC, "concept").success
    assert radar.set_flag("bob", COURSE, TOPIC).success
    assert radar.set_flag("carol", COURSE, TOPIC, None).success

    topic = radar.get_course_radar(COURSE).topics[TOPIC]

    assert connection.flags[("bob", COURSE, TOPIC)] is None
    assert topic.real_count == 3
    assert topic.reasons == {"concept": 1}
    assert radar.get_user_flags("bob", COURSE) == {TOPIC: None}


def test_reflagging_without_reason_clears_the_previous_reason(
    connection: FakeRadarConnection,
) -> None:
    assert radar.set_flag("alice", COURSE, TOPIC, "calculation").success
    assert radar.set_flag("alice", COURSE, TOPIC).success

    assert connection.flags == {("alice", COURSE, TOPIC): None}


def test_clear_flag_removes_only_that_users_flag(
    connection: FakeRadarConnection, no_sample: None
) -> None:
    assert radar.set_flag("alice", COURSE, TOPIC, "concept").success
    assert radar.set_flag("bob", COURSE, TOPIC, "start").success

    cleared = radar.clear_flag("alice", COURSE, TOPIC)

    assert cleared.success is True
    assert connection.flags == {("bob", COURSE, TOPIC): "start"}
    deletes = connection.calls_starting("delete from radar_flags")
    assert [parameters for _, parameters in deletes] == [("alice", COURSE, TOPIC)]
    assert radar.get_user_flags("alice", COURSE) == {}
    topic = radar.get_course_radar(COURSE).topics[TOPIC]
    assert topic.real_count == 1 and topic.reasons == {"start": 1}

    # Clearing again is harmless, and the last clear removes the topic.
    assert radar.clear_flag("alice", COURSE, TOPIC).success is True
    assert radar.clear_flag("bob", COURSE, TOPIC).success is True
    assert connection.flags == {}
    assert TOPIC not in radar.get_course_radar(COURSE).topics


def test_flags_are_scoped_by_user_and_course(connection: FakeRadarConnection) -> None:
    assert radar.set_flag("alice", "econ101", "elasticity").success
    assert radar.set_flag("alice", COURSE, "calc_limits", "concept").success

    assert radar.get_user_flags("alice", "econ101") == {"elasticity": None}
    assert radar.get_user_flags("alice", COURSE) == {"calc_limits": "concept"}
    assert radar.get_user_flags("bob", "econ101") == {}
    user_queries = connection.calls_starting("select topic_id, reason from")
    assert [parameters for _, parameters in user_queries] == [
        ("alice", "econ101"),
        ("alice", COURSE),
        ("bob", "econ101"),
    ]

    econ = radar.get_course_radar("econ101")
    count_query = connection.calls_starting("select topic_id, reason, count(*)")[-1]
    assert count_query[1] == ("econ101",)
    assert econ.topics["elasticity"].real_count == 1
    assert all(topic.real_count == 0 for key, topic in econ.topics.items() if key != "elasticity")


def test_user_id_follows_the_store_rule(connection: FakeRadarConnection) -> None:
    longest = "x" * 100
    connection.users.add(longest)

    assert radar.set_flag(longest, COURSE, TOPIC).success is True
    assert radar.set_flag("  alice  ", COURSE, TOPIC).success is True

    assert set(connection.flags) == {(longest, COURSE, TOPIC), ("alice", COURSE, TOPIC)}
    assert radar.get_user_flags("  alice ", COURSE) == {TOPIC: None}


INVALID_REQUESTS = [
    pytest.param("", COURSE, TOPIC, "signed-in", id="empty-user"),
    pytest.param("   ", COURSE, TOPIC, "signed-in", id="blank-user"),
    pytest.param("x" * 101, COURSE, TOPIC, "signed-in", id="long-user"),
    pytest.param(None, COURSE, TOPIC, "signed-in", id="none-user"),
    pytest.param(42, COURSE, TOPIC, "signed-in", id="int-user"),
    pytest.param("alice", "course-1", TOPIC, "demo courses", id="unknown-course"),
    pytest.param("alice", "CALCULUS-I-DEMO", TOPIC, "demo courses", id="wrong-case-course"),
    pytest.param("alice", None, TOPIC, "demo courses", id="none-course"),
    pytest.param("alice", [COURSE], TOPIC, "demo courses", id="list-course"),
    pytest.param("alice", COURSE, "elasticity", "not part of", id="topic-of-other-course"),
    pytest.param("alice", COURSE, "calc_integrals", "not part of", id="unknown-topic"),
    pytest.param("alice", COURSE, "", "not part of", id="empty-topic"),
    pytest.param("alice", COURSE, None, "not part of", id="none-topic"),
]


@pytest.mark.parametrize(("user_id", "course_id", "topic_id", "fragment"), INVALID_REQUESTS)
def test_invalid_writes_fail_without_opening_a_connection(
    forbid_connect: list[int],
    user_id: Any,
    course_id: Any,
    topic_id: Any,
    fragment: str,
) -> None:
    flagged = radar.set_flag(user_id, course_id, topic_id, "concept")
    cleared = radar.clear_flag(user_id, course_id, topic_id)

    assert flagged.success is False and fragment in flagged.message
    assert cleared.success is False and fragment in cleared.message
    assert forbid_connect == []


@pytest.mark.parametrize(
    "reason", ["boredom", "", "Concept unclear", "CONCEPT", " concept", 1, ["concept"]]
)
def test_invalid_reason_fails_without_opening_a_connection(
    forbid_connect: list[int], reason: Any
) -> None:
    result = radar.set_flag("alice", COURSE, TOPIC, reason)

    assert result.success is False
    assert "reason" in result.message
    assert forbid_connect == []


@pytest.mark.parametrize(
    ("user_id", "course_id"),
    [("", COURSE), (None, COURSE), ("x" * 101, COURSE), ("alice", "course-1"), ("alice", None)],
)
def test_invalid_reads_return_empty_without_opening_a_connection(
    forbid_connect: list[int], user_id: Any, course_id: Any
) -> None:
    assert radar.get_user_flags(user_id, course_id) == {}
    assert forbid_connect == []


@pytest.mark.parametrize("course_id", ["course-1", "", None, ["econ101"]])
def test_non_demo_course_radar_is_empty_without_opening_a_connection(
    forbid_connect: list[int], course_id: Any
) -> None:
    assert radar.get_course_radar(course_id) == radar.CourseRadar(
        topics={}, live=False, has_sample=False
    )
    assert forbid_connect == []


def test_database_rejection_is_reported_and_rolled_back(
    connection: FakeRadarConnection,
) -> None:
    # "mallory" has no demo_users row, so the foreign key rejects the flag.
    result = radar.set_flag("mallory", COURSE, TOPIC, "concept")

    assert result.success is False
    assert result.message
    assert connection.flags == {}
    assert connection.rollback_count == 1 and connection.commit_count == 0


# --- Counting ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("real_count", "expected"),
    [
        (1, None),
        (radar.MIN_VISIBLE_COUNT - 1, None),
        (radar.MIN_VISIBLE_COUNT, radar.MIN_VISIBLE_COUNT),
        (radar.MIN_VISIBLE_COUNT + 2, radar.MIN_VISIBLE_COUNT + 2),
    ],
)
def test_privacy_threshold_hides_small_real_only_counts(
    connection: FakeRadarConnection,
    no_sample: None,
    real_count: int,
    expected: int | None,
) -> None:
    connection.users.update(f"user-{index}" for index in range(real_count))
    flag_users(real_count)

    topic = radar.get_course_radar(COURSE).topics[TOPIC]

    assert topic.real_count == real_count
    assert topic.sample_count == 0
    assert topic.display_count == expected


def test_privacy_threshold_does_not_apply_when_sample_data_is_present(
    connection: FakeRadarConnection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    use_sample(
        monkeypatch,
        tmp_path,
        {COURSE: {"calc_limits": {"count": 1, "reasons": {}}, TOPIC: {"count": 2}}},
    )
    assert radar.set_flag("alice", COURSE, "calc_limits").success

    topics = radar.get_course_radar(COURSE).topics

    assert (topics["calc_limits"].real_count, topics["calc_limits"].sample_count) == (1, 1)
    assert topics["calc_limits"].display_count == 2
    assert (topics[TOPIC].real_count, topics[TOPIC].sample_count) == (0, 2)
    assert topics[TOPIC].display_count == 2


def test_sample_and_real_counts_are_kept_separate(
    connection: FakeRadarConnection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sample_path = use_sample(
        monkeypatch,
        tmp_path,
        {
            COURSE: {
                TOPIC: {"count": 8, "reasons": {"concept": 2, "start": 1}},
                "calc_limits": {"count": 0, "reasons": {}},
                "ghost-topic": {"count": 5, "reasons": {}},
            },
            "course-1": {"topic-a": {"count": 4, "reasons": {}}},
        },
    )
    sample_bytes = sample_path.read_bytes()
    assert radar.set_flag("alice", COURSE, TOPIC, "concept").success
    assert radar.set_flag("bob", COURSE, TOPIC, "calculation").success
    assert radar.set_flag("carol", COURSE, "calc_limits").success

    course = radar.get_course_radar(COURSE)

    assert course.live is True and course.has_sample is True
    assert set(course.topics) == {TOPIC, "calc_limits"}
    derivatives = course.topics[TOPIC]
    assert derivatives == radar.TopicRadar(
        topic_id=TOPIC,
        real_count=2,
        sample_count=8,
        reasons={"concept": 3, "calculation": 1, "start": 1},
        display_count=10,
    )
    limits = course.topics["calc_limits"]
    assert (limits.real_count, limits.sample_count, limits.display_count) == (1, 0, None)
    assert sample_path.read_bytes() == sample_bytes


def test_real_only_radar_has_no_sample(
    connection: FakeRadarConnection, no_sample: None
) -> None:
    assert radar.set_flag("alice", COURSE, TOPIC).success

    course = radar.get_course_radar(COURSE)

    assert course.live is True and course.has_sample is False
    assert course.topics[TOPIC].sample_count == 0


def test_rows_for_topics_outside_the_course_are_ignored(
    connection: FakeRadarConnection, no_sample: None
) -> None:
    connection.flags[("alice", "econ101", "ghost-topic")] = "concept"
    connection.flags[("alice", "econ101", "calc_limits")] = None
    connection.flags[("bob", "econ101", "elasticity")] = "wording"

    econ = radar.get_course_radar("econ101")

    assert set(econ.topics) == {"elasticity"}
    assert radar.get_user_flags("alice", "econ101") == {}
    assert radar.get_user_flags("bob", "econ101") == {"elasticity": "wording"}


def make_topic(topic_id: str, real_count: int, sample_count: int) -> radar.TopicRadar:
    return radar.TopicRadar(
        topic_id=topic_id,
        real_count=real_count,
        sample_count=sample_count,
        reasons={},
        display_count=real_count + sample_count,
    )


def test_top_hard_topics_orders_by_real_plus_sample() -> None:
    topics = [
        make_topic("a", 5, 0),
        make_topic("b", 0, 6),
        make_topic("c", 2, 2),
        make_topic("d", 1, 3),
        make_topic("e", 1, 0),
    ]
    course = radar.CourseRadar(
        topics={topic.topic_id: topic for topic in topics}, live=True, has_sample=True
    )

    assert [topic.topic_id for topic in radar.top_hard_topics(course)] == ["b", "a", "c"]
    assert [topic.topic_id for topic in radar.top_hard_topics(course, limit=10)] == [
        "b", "a", "c", "d", "e",
    ]
    assert [topic.topic_id for topic in radar.top_hard_topics(course, limit=1)] == ["b"]
    assert radar.top_hard_topics(course, limit=0) == []
    empty = radar.CourseRadar(topics={}, live=True, has_sample=False)
    assert radar.top_hard_topics(empty) == []


def test_top_hard_topics_uses_live_counts(
    connection: FakeRadarConnection, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    use_sample(monkeypatch, tmp_path, {COURSE: {"calc_limits": {"count": 3}, TOPIC: {"count": 2}}})
    connection.users.update(f"user-{index}" for index in range(2))
    flag_users(2, topic_id=TOPIC)

    top = radar.top_hard_topics(radar.get_course_radar(COURSE), limit=2)

    assert [(topic.topic_id, topic.real_count, topic.sample_count) for topic in top] == [
        (TOPIC, 2, 2),
        ("calc_limits", 0, 3),
    ]


# --- Unavailable database ---------------------------------------------------


def assert_offline_with_shipped_sample(course: radar.CourseRadar) -> None:
    assert course.live is False
    assert course.has_sample is True
    assert set(course.topics) == set(json.loads((ROOT / "data" / "radar_sample.json").read_text(encoding="utf-8"))[COURSE])
    assert course.topics[TOPIC].sample_count == 8
    assert all(topic.real_count == 0 for topic in course.topics.values())


def test_unconfigured_database_reports_failure_and_falls_back_to_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # conftest removes DATABASE_URL, so the real _connect refuses to connect.
    monkeypatch.setattr(
        postgres_store.psycopg,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("must not connect"),
    )

    flagged = radar.set_flag("alice", COURSE, TOPIC, "concept")
    cleared = radar.clear_flag("alice", COURSE, TOPIC)

    assert flagged.success is False and "not configured" in flagged.message
    assert cleared.success is False and "not configured" in cleared.message
    assert radar.get_user_flags("alice", COURSE) == {}
    assert_offline_with_shipped_sample(radar.get_course_radar(COURSE))


@pytest.mark.parametrize(
    "error",
    [
        psycopg.OperationalError("connection failed: password=secret host=db"),
        OSError("network unreachable: secret"),
    ],
    ids=["psycopg", "os"],
)
def test_connection_failure_reports_failure_and_falls_back_to_sample(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    calls: list[int] = []

    def failing_connect() -> None:
        calls.append(1)
        raise error

    monkeypatch.setattr(postgres_store, "_connect", failing_connect)

    flagged = radar.set_flag("alice", COURSE, TOPIC, "concept")
    cleared = radar.clear_flag("alice", COURSE, TOPIC)

    assert flagged.success is False and cleared.success is False
    for message in (flagged.message, cleared.message):
        assert message and "secret" not in message
    assert radar.get_user_flags("alice", COURSE) == {}
    assert_offline_with_shipped_sample(radar.get_course_radar(COURSE))
    assert len(calls) == 4


def test_missing_table_reports_failure_and_falls_back_to_sample(
    connection: FakeRadarConnection,
) -> None:
    connection.fail_with = psycopg.errors.UndefinedTable(
        'relation "radar_flags" does not exist'
    )

    flagged = radar.set_flag("alice", COURSE, TOPIC, "concept")
    cleared = radar.clear_flag("alice", COURSE, TOPIC)

    assert flagged.success is False and "not set up" in flagged.message
    assert cleared.success is False and "not set up" in cleared.message
    assert radar.get_user_flags("alice", COURSE) == {}
    assert_offline_with_shipped_sample(radar.get_course_radar(COURSE))
    assert len(connection.execute_calls) == 4
    assert connection.rollback_count == 4 and connection.commit_count == 0
    assert connection.flags == {}


# --- Sample data ------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        None,
        b"{not json",
        b"\xff\xfe\x00",
        b"[]",
        b'{"calculus-i-demo": []}',
        b'{"calculus-i-demo": {"calc_derivatives": 8}}',
        b'{"calculus-i-demo": {"calc_derivatives": {"count": "8"}}}',
        b'{"calculus-i-demo": {"calc_derivatives": {"count": -1}}}',
        b'{"calculus-i-demo": {"calc_derivatives": {"count": true}}}',
        b'{"calculus-i-demo": {"calc_derivatives": {"count": 2, "reasons": []}}}',
        b'{"calculus-i-demo": {"calc_derivatives": {"count": 2, "reasons": {"boredom": 1}}}}',
        b'{"calculus-i-demo": {"calc_derivatives": {"count": 2, "reasons": {"concept": 3}}}}',
    ],
    ids=[
        "missing",
        "invalid-json",
        "not-utf8",
        "list",
        "course-not-object",
        "topic-not-object",
        "string-count",
        "negative-count",
        "bool-count",
        "reasons-not-object",
        "unknown-reason",
        "reasons-exceed-count",
    ],
)
def test_missing_or_malformed_sample_means_no_sample(
    connection: FakeRadarConnection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    content: bytes | None,
) -> None:
    path = tmp_path / "radar_sample.json"
    if content is not None:
        path.write_bytes(content)
    monkeypatch.setattr(radar, "SAMPLE_PATH", path)
    assert radar.set_flag("alice", COURSE, "calc_limits").success

    course = radar.get_course_radar(COURSE)

    assert course.live is True and course.has_sample is False
    assert set(course.topics) == {"calc_limits"}
    assert course.topics["calc_limits"].sample_count == 0


def test_shipped_sample_covers_every_demo_topic() -> None:
    data = json.loads((ROOT / "data" / "radar_sample.json").read_text(encoding="utf-8"))

    assert set(data) == set(DEMO_TOPICS)
    for course_id, topic_ids in DEMO_TOPICS.items():
        assert set(data[course_id]).issubset(topic_ids)
        for topic_id, entry in data[course_id].items():
            count = entry["count"]
            assert type(count) is int and 2 <= count <= 9
            assert set(entry["reasons"]) <= ALLOWED_REASONS
            assert all(type(number) is int and number >= 0 for number in entry["reasons"].values())
            assert sum(entry["reasons"].values()) <= count
    assert data[COURSE][TOPIC]["count"] == 8
    assert radar._load_sample() == {
        course_id: {
            topic_id: (entry["count"], entry["reasons"])
            for topic_id, entry in topics.items()
        }
        for course_id, topics in data.items()
    }


@pytest.mark.parametrize("course_id", sorted(DEMO_TOPICS))
def test_shipped_sample_is_shown_when_offline(course_id: str) -> None:
    data = json.loads((ROOT / "data" / "radar_sample.json").read_text(encoding="utf-8"))

    course = radar.get_course_radar(course_id)

    assert course.live is False and course.has_sample is True
    assert list(course.topics) == list(data[course_id])
    for topic_id, topic in course.topics.items():
        entry = data[course_id].get(topic_id, {"count": 0, "reasons": {}})
        assert topic.real_count == 0
        assert topic.sample_count == topic.display_count == entry["count"]
        assert topic.reasons == entry["reasons"]


def test_unexpected_value_errors_on_write_are_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # psycopg raises UnicodeEncodeError (a ValueError) when it cannot adapt a
    # parameter; that must become a failed result like any other database error.
    def broken_connect() -> None:
        raise UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogates not allowed")

    monkeypatch.setattr(postgres_store, "_connect", broken_connect)

    saved = radar.set_flag("alice", COURSE, TOPIC)
    removed = radar.clear_flag("alice", COURSE, TOPIC)

    assert saved.success is False and saved.message
    assert removed.success is False and removed.message


def test_top_hard_topics_ranks_hidden_counts_by_their_real_total() -> None:
    # A count hidden by the privacy threshold has display_count None; ranking
    # must still use real_count + sample_count instead of comparing None.
    hidden = radar.TopicRadar(
        topic_id="hidden", real_count=2, sample_count=0, reasons={}, display_count=None
    )
    shown = radar.TopicRadar(
        topic_id="shown", real_count=0, sample_count=1, reasons={}, display_count=1
    )
    course = radar.CourseRadar(
        topics={"shown": shown, "hidden": hidden}, live=True, has_sample=True
    )

    assert [topic.topic_id for topic in radar.top_hard_topics(course)] == ["hidden", "shown"]
