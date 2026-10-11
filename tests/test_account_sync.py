"""Account Save/Restore adaptation, with the PostgreSQL store replaced by a fake."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from models.schemas import AttemptResult, ExamSession, Question, StudyPackage
from services import account_sync, postgres_store
from services.auth_service import AuthUser
from services.exam_engine import grade_exam
from services.mastery_engine import calculate_topic_stats
from tests.auth_helpers import TEST_USER, signed_in_app


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
PRACTICE_PATH = ROOT / "pages" / "2_Practice_Center.py"
OTHER_USER = AuthUser("22222222-2222-4222-8222-222222222222", "otherstudent")


def make_course(course_id="course-1", name="Economics") -> StudyPackage:
    return StudyPackage(
        course_id=course_id,
        course_name=name,
        topics=[{"id": "t1", "name": "Topic", "summary": "Summary."}],
        relationships=[],
        questions=[
            Question(
                id=f"{course_id}-q{i}",
                topic_id="t1",
                question=f"Question {i}?",
                options=["a", "b", "c", "d"],
                correct_index=0,
                explanation="Because.",
            )
            for i in (1, 2)
        ],
    )


def make_exam(course, session_id, mode="mock", picks=(0, 1)):
    session = ExamSession(
        session_id=session_id,
        mode=mode,
        question_ids=[q.id for q in course.questions],
    )
    result = grade_exam(
        session,
        course.questions,
        {q.id: pick for q, pick in zip(course.questions, picks)},
    )
    return session, result["attempts"]


class FakeStore:
    """Per-user in-memory stand-in that records calls and can fail on demand."""

    def __init__(self):
        self.courses: dict[str, dict[str, StudyPackage]] = {}
        self.exams: dict[str, dict[str, tuple]] = {}
        self.calls: list[tuple] = []
        self.fail: set[str] = set()
        self.fail_course_ids: set[str] = set()

    def install(self, monkeypatch):
        for name in (
            "list_saved_courses",
            "load_course_history",
            "save_course",
            "save_exam_result",
        ):
            monkeypatch.setattr(postgres_store, name, getattr(self, name))

    def list_saved_courses(self, user_id):
        self.calls.append(("list", user_id))
        if "list" in self.fail:
            return postgres_store.SavedCoursesResult(False, [], "list failed")
        summaries = [
            postgres_store.SavedCourseSummary(c.course_id, c.course_name)
            for c in self.courses.get(user_id, {}).values()
        ]
        return postgres_store.SavedCoursesResult(True, summaries, "ok")

    def load_course_history(self, user_id, course_id):
        self.calls.append(("load", user_id, course_id))
        if course_id in self.fail_course_ids:
            return postgres_store.CourseHistoryResult(
                False, None, [], [], [], {}, "load failed"
            )
        package = self.courses.get(user_id, {}).get(course_id)
        if package is None:
            return postgres_store.CourseHistoryResult(
                True, None, [], [], [], {}, "missing"
            )
        stored = [
            v for v in self.exams.get(user_id, {}).values() if v[0] == course_id
        ]
        sessions = [v[1] for v in stored]
        attempts = [a for v in stored for a in v[2]]
        stats = calculate_topic_stats(attempts, sessions, package.questions)
        return postgres_store.CourseHistoryResult(
            True, package, sessions, attempts, stats, {}, "restored"
        )

    def save_course(self, user_id, package):
        self.calls.append(("save_course", user_id, package.course_id))
        if "save_course" in self.fail:
            return postgres_store.PersistenceResult(False, "course save failed")
        self.courses.setdefault(user_id, {})[package.course_id] = package
        return postgres_store.PersistenceResult(True, "saved")

    def save_exam_result(self, user_id, course_id, session, attempts):
        self.calls.append(("save_exam", user_id, course_id, session.session_id))
        if "save_exam" in self.fail:
            return postgres_store.PersistenceResult(False, "exam save failed")
        self.exams.setdefault(user_id, {})[session.session_id] = (
            course_id,
            session,
            list(attempts),
        )
        return postgres_store.PersistenceResult(True, "saved")

    def names(self, kind):
        return [call for call in self.calls if call[0] == kind]


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    fake.install(monkeypatch)
    return fake


def signed_in_state(user=TEST_USER) -> dict:
    from services.auth_session import start_authenticated_session

    state: dict = {}
    start_authenticated_session(state, user)
    return state


def seed(store, user, course, *sessions):
    store.courses.setdefault(user.user_id, {})[course.course_id] = course
    for session, attempts in sessions:
        store.exams.setdefault(user.user_id, {})[session.session_id] = (
            course.course_id,
            session,
            attempts,
        )


def stats_from_history(state, course, mode):
    history = state[f"practice_history_{course.course_id}"].values()
    return calculate_topic_stats(
        attempts=[a for r in history for a in r["attempts"]],
        sessions=[r["session"] for r in history],
        questions=course.questions,
    )


def test_anonymous_session_never_touches_the_database(store):
    state: dict = {}
    assert account_sync.restore_all(state) is None
    assert account_sync.save_course_to_account(state, make_course()) is None
    assert store.calls == []


def test_empty_account_is_a_normal_no_records_result(store):
    state = signed_in_state()
    outcome = account_sync.restore_all(state)

    assert outcome.success
    assert state["account_sync"]["restore_errors"] == []
    assert "No saved study records" in state["account_sync"]["restore_message"]
    assert store.names("load") == []


def test_restore_maps_database_history_into_ui_history_and_stats(store):
    course = make_course()
    mock_exam = make_exam(course, "s-mock", "mock", (0, 1))
    topic_exam = make_exam(course, "s-topic", "topic", (0, 0))
    seed(store, TEST_USER, course, mock_exam, topic_exam)
    state = signed_in_state()

    outcome = account_sync.restore_all(state)

    assert outcome.success
    assert [c.course_id for c in state["courses"]] == ["course-1"]
    assert state["current_course"] is None
    history = state["practice_history_course-1"]
    assert set(history) == {"s-mock", "s-topic"}
    record = history["s-mock"]
    assert set(record) == {"session", "questions", "attempts", "result"}
    assert [q.id for q in record["questions"]] == record["session"].question_ids
    assert record["result"]["correct_count"] == 1
    assert record["result"]["total_count"] == 2
    assert record["attempts"] == mock_exam[1]

    # Existing Progress/Graph path: stats per mode stay isolated.
    stats = {
        (s.topic_id, s.mode): s for s in stats_from_history(state, course, None)
    }
    assert (stats[("t1", "mock")].correct, stats[("t1", "mock")].attempted) == (1, 2)
    assert (stats[("t1", "topic")].correct, stats[("t1", "topic")].attempted) == (2, 2)


def test_restore_twice_does_not_duplicate_or_accumulate_answers(store):
    course = make_course()
    seed(store, TEST_USER, course, make_exam(course, "s1"))
    state = signed_in_state()

    account_sync.restore_all(state)
    account_sync.restore_all(state)

    history = state["practice_history_course-1"]
    assert len(history) == 1
    assert len(state["courses"]) == 1
    assert len(history["s1"]["attempts"]) == 2
    assert store.names("save_course") == [] and store.names("save_exam") == []


def test_database_record_replaces_demo_copy_and_keeps_unsaved_local_sessions(store):
    stored = make_course("econ101", "Saved Economics")
    seed(store, TEST_USER, stored, make_exam(stored, "db-session"))
    state = signed_in_state()
    local = make_course("econ101", "Demo Economics")
    local_session = make_exam(local, "local-only")
    state["courses"] = [local]
    state["current_course"] = local
    state["practice_history_econ101"] = {
        "local-only": {
            "session": local_session[0],
            "questions": local.questions,
            "attempts": local_session[1],
            "result": {},
        }
    }

    account_sync.restore_all(state)

    assert [c.course_name for c in state["courses"]] == ["Saved Economics"]
    assert state["current_course"].course_name == "Saved Economics"
    assert set(state["practice_history_econ101"]) == {"db-session", "local-only"}


def test_partial_restore_failure_is_reported_and_keeps_other_data(store):
    good, bad = make_course("good", "Good"), make_course("bad", "Bad")
    seed(store, TEST_USER, good, make_exam(good, "g1"))
    seed(store, TEST_USER, bad)
    store.fail_course_ids.add("bad")
    state = signed_in_state()
    local = make_course("bad", "Local Bad")
    state["courses"] = [local]

    outcome = account_sync.restore_all(state)

    assert not outcome.success
    assert state["account_sync"]["restore_errors"] == ["Bad: load failed"]
    assert {c.course_id for c in state["courses"]} == {"good", "bad"}
    assert next(c for c in state["courses"] if c.course_id == "bad") is local
    assert "g1" in state["practice_history_good"]


def test_list_failure_keeps_local_data_and_retry_can_recover(store):
    course = make_course()
    seed(store, TEST_USER, course, make_exam(course, "s1"))
    store.fail.add("list")
    state = signed_in_state()
    state["courses"] = [make_course("local", "Local")]

    outcome = account_sync.restore_all(state)
    assert not outcome.success
    assert state["account_sync"]["restore_errors"] == ["list failed"]
    assert [c.course_id for c in state["courses"]] == ["local"]

    store.fail.clear()
    assert account_sync.restore_all(state).success
    assert {c.course_id for c in state["courses"]} == {"local", "course-1"}


def test_accounts_are_isolated(store):
    course = make_course()
    seed(store, TEST_USER, course, make_exam(course, "s1"))
    state = signed_in_state(OTHER_USER)

    outcome = account_sync.restore_all(state)

    assert outcome.success
    assert "courses" not in state or state["courses"] == []
    assert "practice_history_course-1" not in state
    assert {call[1] for call in store.calls} == {OTHER_USER.user_id}


def test_exam_save_stores_course_first_then_full_snapshot(store):
    course = make_course()
    session, attempts = make_exam(course, "s1")
    state = signed_in_state()

    outcome = account_sync.save_exam_to_account(state, course, session, attempts)

    assert outcome.success
    assert [c[0] for c in store.calls] == ["save_course", "save_exam"]
    assert all(c[1] == TEST_USER.user_id for c in store.calls)
    assert store.exams[TEST_USER.user_id]["s1"][2] == attempts
    assert state["account_sync"]["unsaved_exams"] == set()


def test_exam_save_failure_is_reported_and_retry_succeeds(store):
    course = make_course()
    session, attempts = make_exam(course, "s1")
    state = signed_in_state()
    state["practice_history_course-1"] = {
        "s1": {"session": session, "questions": course.questions,
               "attempts": attempts, "result": {}}
    }
    store.fail.add("save_exam")

    outcome = account_sync.save_exam_to_account(state, course, session, attempts)
    assert not outcome.success
    assert state["account_sync"]["last_save"] is outcome
    assert state["account_sync"]["unsaved_exams"] == {("course-1", "s1")}
    assert "s1" in state["practice_history_course-1"]

    store.fail.clear()
    retry = account_sync.save_course_with_history(state, course)
    assert retry.success
    assert state["account_sync"]["unsaved_exams"] == set()
    assert "s1" in store.exams[TEST_USER.user_id]


def test_course_save_failure_prevents_exam_write_and_flags_both(store):
    course = make_course()
    session, attempts = make_exam(course, "s1")
    state = signed_in_state()
    store.fail.add("save_course")

    outcome = account_sync.save_exam_to_account(state, course, session, attempts)

    assert not outcome.success
    assert store.names("save_exam") == []
    assert state["account_sync"]["unsaved_courses"] == {"course-1"}
    assert state["account_sync"]["unsaved_exams"] == {("course-1", "s1")}


def test_single_course_restore_failure_does_not_claim_success(store):
    course = make_course()
    seed(store, TEST_USER, course)
    store.fail_course_ids.add("course-1")
    outcome = account_sync.restore_course(signed_in_state(), "course-1")
    assert not outcome.success and "load failed" in outcome.message


def test_app_restores_once_per_login_despite_reruns(store):
    course = make_course()
    seed(store, TEST_USER, course, make_exam(course, "s1"))
    app = signed_in_app(APP_PATH)

    app.run()
    app.run()
    app.run()

    assert not app.exception
    assert len(store.names("list")) == 1
    assert len(store.names("load")) == 1
    assert "s1" in app.session_state["practice_history_course-1"]


def test_failed_login_restore_shows_retry_and_keeps_local_state(store):
    course = make_course()
    seed(store, TEST_USER, course, make_exam(course, "s1"))
    store.fail.add("list")
    app = signed_in_app(APP_PATH)
    app.run()

    assert [w.value for w in app.warning if "could not be restored" in w.value]
    assert len(store.names("list")) == 1

    store.fail.clear()
    app.button(key="retry_restore").click().run()

    assert not app.exception
    assert not [w for w in app.warning if "could not be restored" in w.value]
    assert "s1" in app.session_state["practice_history_course-1"]


def test_logout_and_account_switch_clear_previous_account_state(store):
    course = make_course()
    seed(store, TEST_USER, course, make_exam(course, "s1"))
    app = signed_in_app(APP_PATH)
    app.run()
    assert "practice_history_course-1" in app.session_state

    app.button(key="logout_button").click().run()

    assert "practice_history_course-1" not in app.session_state
    assert "account_sync" not in app.session_state
    assert "auth_user" not in app.session_state

    other = signed_in_app(APP_PATH)
    from services.auth_session import start_authenticated_session

    other_state: dict = {}
    start_authenticated_session(other_state, OTHER_USER)
    for key in list(other.session_state.filtered_state):
        del other.session_state[key]
    for key, value in other_state.items():
        other.session_state[key] = value
    other.run()
    assert "practice_history_course-1" not in other.session_state
    assert store.names("load") == [("load", TEST_USER.user_id, "course-1")]


def test_practice_submit_saves_course_then_exam_for_signed_in_user(store):
    from tests.test_practice_page import make_practice_state

    app = signed_in_app(PRACTICE_PATH)
    for key, value in make_practice_state(graded=False).items():
        app.session_state[key] = value
    app.session_state["practice_history_course-1"] = {}
    app.run()

    app.radio(key="answer_session-1_question-1").set_value(1)
    next(b for b in app.button if b.label == "Submit answers").click().run()

    assert not app.exception
    assert [c[0] for c in store.calls] == ["save_course", "save_exam"]
    assert store.calls[1] == (
        "save_exam", TEST_USER.user_id, "course-1", "session-1",
    )
    saved_attempts = store.exams[TEST_USER.user_id]["session-1"][2]
    assert [a.selected_index for a in saved_attempts] == [1]
    assert not [w for w in app.warning if "Not saved" in w.value]


def test_practice_submit_failure_warns_and_keeps_local_history(store):
    from tests.test_practice_page import make_practice_state

    store.fail.add("save_exam")
    app = signed_in_app(PRACTICE_PATH)
    for key, value in make_practice_state(graded=False).items():
        app.session_state[key] = value
    app.session_state["practice_history_course-1"] = {}
    app.run()

    app.radio(key="answer_session-1_question-1").set_value(1)
    next(b for b in app.button if b.label == "Submit answers").click().run()

    assert not app.exception
    assert "session-1" in app.session_state["practice_history_course-1"]
    assert [w for w in app.warning if "Not saved to your account" in w.value]
    assert not [c for c in app.caption if c.value == "Saved to your account."]


def study_hub_app(course):
    app = signed_in_app(ROOT / "pages" / "1_Study_Hub.py")
    app.session_state["courses"] = [course]
    app.session_state["current_course"] = course
    return app


def test_study_hub_save_button_reports_success_and_failure(store):
    course = make_course()
    app = study_hub_app(course)
    app.run()

    app.button(key="database_save_course-1").click().run()
    assert not app.exception
    assert [s.value for s in app.success] == [
        "Course and practice history saved to your account."
    ]
    assert course.course_id in store.courses[TEST_USER.user_id]

    store.fail.add("save_course")
    app.button(key="database_save_course-1").click().run()
    assert [e.value for e in app.error] == ["course save failed"]
    assert not app.success


def test_study_hub_restore_button_replaces_course_and_reports_failure(store):
    saved = make_course("course-1", "Saved Name")
    seed(store, TEST_USER, saved, make_exam(saved, "s1"))
    app = study_hub_app(make_course("course-1", "Local Name"))
    app.run()

    app.button(key="database_restore_course-1").click().run()
    assert not app.exception
    assert app.session_state["current_course"].course_name == "Saved Name"
    assert "s1" in app.session_state["practice_history_course-1"]

    store.fail_course_ids.add("course-1")
    app.button(key="database_restore_course-1").click().run()
    assert [e.value for e in app.error] == ["course-1: load failed"]
    assert app.session_state["current_course"].course_name == "Saved Name"


def test_regenerated_questions_keep_saved_history_restorable(store):
    old = make_course("course-1", "Economics")
    state = signed_in_state()
    session, attempts = make_exam(old, "s1")
    state["practice_history_course-1"] = {
        "s1": {
            "session": session,
            "questions": list(old.questions),
            "attempts": attempts,
            "result": grade_exam(
                session, old.questions, {a.question_id: a.selected_index for a in attempts}
            ),
        }
    }
    regenerated = old.model_copy(
        update={"questions": [
            q.model_copy(update={"id": f"new-{q.id}"}) for q in old.questions
        ]}
    )
    assert account_sync.save_course_to_account(state, regenerated).success
    saved_ids = {q.id for q in store.courses[TEST_USER.user_id]["course-1"].questions}
    assert {q.id for q in old.questions} <= saved_ids
    assert {q.id for q in regenerated.questions} <= saved_ids
    assert len(regenerated.questions) == 2  # local bank unchanged
